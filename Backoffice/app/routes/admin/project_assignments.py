"""Project assignments: one record per project, settings pushed onto its reports.

Lives under /admin/assignments/projects/ so projects sit on the Assignments list.
``/admin/projects/`` redirects here and keeps the old endpoint names.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from typing import Sequence

from flask import Blueprint, Response, abort, current_app, flash, redirect, render_template, request, url_for
from flask_babel import _
from flask_login import current_user
from flask_wtf import FlaskForm
from sqlalchemy.orm import joinedload
from wtforms import DateField, DecimalField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional

from app import db
from app.forms.assignments.assignment_forms import ProjectAssignmentSettingsForm
from app.models import AssignmentEntityStatus, AssignedForm, Country, FormTemplate, NationalSociety, User
from app.models.assignments import (
    SUBMISSION_REVIEW_RECIPIENT_FDS,
    SUBMISSION_REVIEW_RECIPIENT_SPECIFIC,
)
from app.models.enums import AssignmentScope, EntityType
from app.models.projects import Project, ProjectAssignment
from app.routes.admin.shared import permission_required, permission_required_any
from app.services.assignments.service import AssignmentService
from app.services.projects.access import (
    can_manage_projects,
    can_open_project_admin,
    can_see_project,
    can_view_all_projects,
    is_pm_viewer,
    scope_manager,
)
from app.services.projects.assignment_settings import (
    apply_to_reports,
    get_or_create_project_assignment,
    plugin_report_types,
    settings_drift,
)
from app.services.projects.service import (
    ensure_project_cycle_assignment,
    list_project_cycle_assignments,
    parse_cycle_slot,
    sync_cycle_names_for_project,
    sync_project_cycle_closure,
    upsert_project,
)
from app.utils.api.api_responses import json_bad_request, json_ok
from app.utils.common.datetime_helpers import utc_sort_key, utcnow
from app.utils.database.transactions import request_transaction_rollback
from app.utils.http.request_utils import is_json_request

bp = Blueprint("project_assignments", __name__, url_prefix="/admin")

PROJECT_STATUSES = ("Open", "Active", "Closed", "Archived")


def _ns_id(value):
    if value in (None, "", "None"):
        return 0
    return int(value)


class ProjectForm(FlaskForm):
    reference = StringField(_("Reference"), validators=[DataRequired(), Length(max=80)])
    title = StringField(_("Title"), validators=[Optional(), Length(max=500)])
    portfolio = StringField(_("Category"), validators=[Optional(), Length(max=40)])
    fund = StringField(_("Fund / programme"), validators=[Optional(), Length(max=40)])
    country_id = SelectField(_("Country"), coerce=int, validators=[DataRequired()])
    national_society_id = SelectField(_("National Society"), coerce=_ns_id, validators=[Optional()], choices=[])
    status = SelectField(_("Status"), choices=[(s, s) for s in PROJECT_STATUSES], validators=[DataRequired()])
    funding_modality = StringField(_("Funding modality"), validators=[Optional(), Length(max=120)])
    categories = StringField(_("Categories"), validators=[Optional()])
    start_date = DateField(_("Start date"), validators=[Optional()])
    end_date = DateField(_("End date"), validators=[Optional()])
    amount_granted = DecimalField(_("Amount granted"), places=2, validators=[Optional()])
    expected_spending = DecimalField(_("Expected spending"), places=2, validators=[Optional()])
    planned_overview = TextAreaField(_("Overview as planned"), validators=[Optional()])
    focal_name = StringField(_("Focal person"), validators=[Optional(), Length(max=255)])
    focal_email = StringField(_("Focal email"), validators=[Optional(), Email(), Length(max=255)])
    manager_name = StringField(_("Project manager"), validators=[Optional(), Length(max=255)])
    manager_email = StringField(_("Manager email"), validators=[Optional(), Email(), Length(max=255)])
    submit = SubmitField(_("Save"))


def _gate_project_admin():
    if not getattr(current_user, "is_authenticated", False):
        if is_json_request():
            abort(401)
        from app.utils.http.redirect_utils import get_current_relative_url

        abort(redirect(url_for("auth.login", next=get_current_relative_url())))
    if not can_open_project_admin(current_user):
        flash(_("Access denied."), "warning")
        abort(redirect(url_for("main.dashboard")))


def _project_or_404(project_id: int) -> Project:
    _gate_project_admin()
    project = Project.query.get_or_404(project_id)
    if not can_see_project(current_user, project):
        abort(403)
    return project


def _require_edit():
    if not can_manage_projects(current_user):
        abort(403)


def _bind_project_form(form: ProjectForm) -> None:
    form.country_id.choices = [(0, _("— Select country —"))] + [
        (c.id, c.name) for c in Country.query.order_by(Country.name.asc()).all()
    ]
    rows = NationalSociety.query.order_by(NationalSociety.name.asc()).all()
    form.national_society_id.choices = [(0, "—")] + [(row.id, row.name) for row in rows]


def _society_for_form(form: ProjectForm):
    ns_id = form.national_society_id.data or 0
    if not ns_id:
        return None
    return NationalSociety.query.get(int(ns_id))


def _save_project_from_form(form: ProjectForm, *, reference: str | None = None) -> Project:
    society = _society_for_form(form)
    return upsert_project(
        reference=reference or form.reference.data,
        country_id=form.country_id.data,
        title=form.title.data,
        portfolio=form.portfolio.data,
        fund=form.fund.data,
        organization_name=society.name if society is not None else None,
        national_society_id=society.id if society is not None else None,
        status=form.status.data,
        funding_modality=form.funding_modality.data,
        categories=form.categories.data,
        start_date=form.start_date.data,
        end_date=form.end_date.data,
        amount_granted=form.amount_granted.data,
        expected_spending=form.expected_spending.data,
        planned_overview=form.planned_overview.data,
        focal_name=form.focal_name.data,
        focal_email=form.focal_email.data,
        manager_name=form.manager_name.data,
        manager_email=form.manager_email.data,
    )


def _plugin_summary(project: Project) -> dict:
    manager = getattr(current_app, "plugin_manager", None)
    if manager is None:
        return {}
    for _plugin_id, plugin in manager._integrating_plugins().items():
        try:
            summary = plugin.get_project_admin_summary(project)
        except Exception as exc:
            current_app.logger.warning("get_project_admin_summary failed: %s", exc)
            continue
        if isinstance(summary, dict) and summary:
            return summary
    return {}


def _logframe_targets(project: Project) -> list:
    plan = project.plan_data if isinstance(project.plan_data, dict) else {}
    if plan.get("source") != "marc_logframe":
        return []
    indicators = plan.get("indicators")
    if not isinstance(indicators, list):
        return []
    return [row for row in indicators if isinstance(row, dict)]


def _registry_view(project: Project) -> dict:
    summary = _plugin_summary(project)
    categories = project.categories or ""
    country_name = project.country.name if project.country else ""
    return {
        "reference": project.reference,
        "title": project.title or "",
        "ns": (
            project.national_society.name
            if project.national_society is not None
            else (project.organization_name or country_name)
        ),
        "status": project.status or "Open",
        "modality": project.funding_modality or "",
        "categories": categories,
        "categories_list": [part.strip() for part in categories.replace(";", ",").split(",") if part.strip()],
        "start": project.start_date,
        "end": project.end_date,
        "granted": project.amount_granted,
        "expenditure": summary.get("expenditure"),
        "ns_focal": project.focal_name or "",
        "ns_focal_email": project.focal_email or "",
        "pm": project.manager_name or "",
        "pm_email": project.manager_email or "",
        "country_id": project.country_id,
        "overview": summary.get("overview") or project.planned_overview or "",
        "outcomes": summary.get("outcomes") or [],
        "logframe_targets": _logframe_targets(project),
    }


def _report_rows(project: Project) -> tuple[list, list]:
    """(existing report rows, report types that can still be added)."""
    offered = plugin_report_types(project)
    by_slot = {str(item.get("slot") or ""): item for item in offered}
    rows = []
    used = set()
    order = {"Y1Q1": 1, "Y1Q2": 2, "Y1Q3": 3, "Y1Q4": 4, "Final": 90}
    for assignment in list_project_cycle_assignments(project):
        aes = AssignmentEntityStatus.query.filter_by(
            assigned_form_id=assignment.id,
            entity_type=EntityType.project.value,
            entity_id=project.id,
        ).first()
        slot = parse_cycle_slot(assignment.period_name) or assignment.period_name
        used.add(slot)
        meta = by_slot.get(slot) or {}
        template = assignment.template
        rows.append({
            "slot": slot,
            "kind": meta.get("kind") or "",
            "template_name": template.name if template else "",
            "start": assignment.period_start,
            "end": assignment.period_end,
            "due": aes.due_date if aes is not None else None,
            "note": meta.get("note") or "",
            "status": aes.status.value if aes is not None and hasattr(aes.status, "value") else (aes.status if aes is not None else ""),
            "completion": aes.completion_rate if aes is not None else None,
            "aes_id": aes.id if aes is not None else None,
            "assignment_id": assignment.id,
            "closed": bool(assignment.is_closed),
            "_order": order.get(slot, 50),
        })
    rows.sort(key=lambda row: (row["_order"], row["slot"] or ""))
    available = [item for item in offered if str(item.get("slot") or "") not in used]
    return rows, available


def _published_templates():
    rows = FormTemplate.query.filter(FormTemplate.published_version_id.isnot(None)).all()
    rows.sort(key=lambda template: (template.name or "").casefold())
    return rows


def _settings_form(settings: ProjectAssignment) -> ProjectAssignmentSettingsForm:
    form = ProjectAssignmentSettingsForm(obj=settings)
    if not form.is_submitted():
        form.submission_review_recipient_user_ids.data = ",".join(
            str(uid) for uid in settings.reviewer_id_list()
        )
    return form


def _access_context(settings: ProjectAssignment) -> dict:
    from app.routes.admin.assignment_management import _assignment_access_context

    class _Holder:
        pass

    holder = _Holder()
    holder.allowed_role_ids = settings.role_id_list()
    holder.allowed_roles = []
    context = _assignment_access_context(None)
    if not (request.method == "POST" and request.form.get("allowed_roles_submitted")):
        context["selected_allowed_role_ids"] = settings.role_id_list()
    return context


def _apply_settings_form(settings: ProjectAssignment, form: ProjectAssignmentSettingsForm) -> None:
    from app.routes.admin.assignment_management import (
        _apply_submission_review_recipient_from_form,
        _parse_custom_name_translations_from_form,
        _posted_allowed_role_ids,
    )

    settings.custom_name = (form.custom_name.data or "").strip() or None
    posted_translations = _parse_custom_name_translations_from_form()
    if request.form.get("custom_name_translations") is not None or any(
        key.startswith("custom_name_") for key in request.form
    ):
        settings.custom_name_translations = posted_translations or None
    settings.data_owner_id = form.data_owner_id.data or None
    settings.requires_delegation_review = bool(form.requires_delegation_review.data)
    settings.enable_page_submission = bool(form.enable_page_submission.data)
    settings.enable_offline_download = bool(form.enable_offline_download.data)
    settings.enable_export_excel = bool(form.enable_export_excel.data)
    settings.enable_import_excel = bool(form.enable_import_excel.data)
    settings.enable_export_pdf = bool(form.enable_export_pdf.data)
    settings.email_attach_pdf = bool(form.email_attach_pdf.data)
    settings.email_attach_excel = bool(form.email_attach_excel.data)
    mode = form.submission_review_recipient_mode.data or "fds_member"
    settings.submission_review_recipient_mode = mode
    if request.form.get("allowed_roles_submitted"):
        settings.allowed_role_ids = _posted_allowed_role_ids() or None

    class _Proxy:
        """Lets the campaign helper write reviewer ids onto this settings row."""

    proxy = _Proxy()
    proxy.submission_review_recipient_mode = mode
    proxy.submission_review_recipient_users = []
    _apply_submission_review_recipient_from_form(proxy, form)
    settings.submission_review_recipient_mode = proxy.submission_review_recipient_mode
    if settings.submission_review_recipient_mode == SUBMISSION_REVIEW_RECIPIENT_SPECIFIC:
        settings.review_recipient_user_ids = [int(user.id) for user in proxy.submission_review_recipient_users] or None
    else:
        settings.review_recipient_user_ids = None


def _reviewer_users(settings: ProjectAssignment, form) -> list:
    from app.routes.admin.assignment_management import _submission_review_recipient_users_for_template

    if form.is_submitted():
        return _submission_review_recipient_users_for_template(form, None)
    ids = settings.reviewer_id_list()
    if not ids:
        return []
    users = User.query.filter(User.id.in_(ids)).all()
    by_id = {int(user.id): user for user in users}
    return [by_id[uid] for uid in ids if uid in by_id]


def _render_project_page(project: Project, form, *, settings: ProjectAssignment):
    reports, available = _report_rows(project)
    drifted = settings_drift(project)
    entities = []
    for row in reports:
        if row["aes_id"]:
            aes = db.session.get(AssignmentEntityStatus, row["aes_id"])
            if aes is not None:
                entities.append(aes)
    overview = None
    if entities:
        overview = AssignmentService.build_status_overview(entities[0].assigned_form, entities)
        if overview is not None:
            overview["template_name"] = project.name
            overview["period_name"] = _("Project lifetime")
            owner = settings.data_owner_user
            overview["has_data_owner"] = owner is not None
            overview["data_owner_name"] = owner.name if owner else None
            if project.is_open:
                overview["lifecycle"] = "active"
            else:
                overview["lifecycle"] = "closed"
    templates = []
    seen = set()
    for item in plugin_report_types(project):
        template_id = item.get("template_id")
        name = ""
        if template_id and template_id not in seen:
            seen.add(template_id)
            tpl = db.session.get(FormTemplate, int(template_id))
            name = tpl.name if tpl else ""
            if name:
                templates.append(name)
    for row in reports:
        if row["template_name"] and row["template_name"] not in templates:
            templates.append(row["template_name"])
    return render_template(
        "admin/assignments/manage_assignment.html",
        assignment_mode="project",
        assignment=None,
        project=project,
        settings=settings,
        form=form,
        registry=_registry_view(project),
        reports=reports,
        available_report_types=available,
        manual_templates=[] if available or plugin_report_types(project) else _published_templates(),
        drifted_reports=drifted,
        report_template_names=templates,
        assignment_overview=overview,
        ns_options=[
            {"value": "" if ns_id == 0 else str(ns_id), "label": name}
            for ns_id, name in (
                [(0, "—")]
                + [(row.id, row.name) for row in NationalSociety.query.order_by(NationalSociety.name.asc()).all()]
            )
        ],
        can_edit=can_manage_projects(current_user),
        submission_review_recipient_users=_reviewer_users(settings, form),
        title=project.reference,
        **_permission_flags(settings),
    )


def _permission_flags(settings: ProjectAssignment) -> dict:
    from app.routes.admin.assignment_management import _manage_assignment_permission_context

    flags = _manage_assignment_permission_context(assignment=None)
    flags["can_edit_assignment_details"] = can_manage_projects(current_user)
    flags.update(_access_context(settings))
    return flags


@bp.route("/assignments/projects/new", methods=["GET", "POST"])
@permission_required("admin.assignments.edit")
def project_new():
    _gate_project_admin()
    _require_edit()
    form = ProjectForm()
    _bind_project_form(form)
    if form.validate_on_submit():
        if form.country_id.data == 0:
            flash(_("Select a country."), "warning")
        elif Project.query.filter_by(reference=form.reference.data.strip()).first():
            flash(_("A project with this reference already exists."), "warning")
        else:
            try:
                project = _save_project_from_form(form)
                get_or_create_project_assignment(project)
                db.session.commit()
                flash(_("Project %(ref)s created.", ref=project.reference), "success")
                return redirect(url_for("project_assignments.project_page", project_id=project.id))
            except Exception as exc:
                request_transaction_rollback()
                current_app.logger.error("Create project failed: %s", exc, exc_info=True)
                flash(_("Could not create the project."), "danger")
    return render_template(
        "admin/projects/form.html",
        form=form,
        project=None,
        can_edit=True,
        title=_("New project"),
        form_action_url=url_for("project_assignments.project_new"),
        modal=False,
    )


def _monitoring_filter_choices(projects: list) -> dict:
    """Fund, region, country and manager options for one programme's monitoring tab."""
    funds = sorted({(project.fund or "").strip() for project in projects if (project.fund or "").strip()}, key=str.casefold)
    regions = sorted(
        {
            (project.country.region or "").strip()
            for project in projects
            if project.country is not None and (project.country.region or "").strip()
        },
        key=str.casefold,
    )
    countries = sorted(
        {
            (project.country.name or "").strip()
            for project in projects
            if project.country is not None and (project.country.name or "").strip()
        },
        key=str.casefold,
    )
    managers: dict = {}
    for project in projects:
        email = (project.manager_email or "").strip()
        if not email:
            continue
        managers.setdefault(
            email.casefold(),
            {"email": email, "label": (project.manager_name or "").strip() or email},
        )
    return {
        "all_funds": funds,
        "all_regions": regions,
        "all_countries": countries,
        "all_managers": sorted(managers.values(), key=lambda item: item["label"].casefold()),
    }


def _portfolio_settings(projects: list) -> ProjectAssignment:
    """In-memory settings used to show the shared options for one programme."""
    from app.services.projects.assignment_settings import (
        SHARED_FLAG_FIELDS,
        _ids_on_majority,
        _majority_bool,
        _majority_value,
    )

    rows = [project.assignment_settings for project in projects if project.assignment_settings is not None]
    ghost = ProjectAssignment(submission_review_recipient_mode=SUBMISSION_REVIEW_RECIPIENT_FDS)
    if not rows:
        return ghost
    ghost.data_owner_id = _majority_value((row.data_owner_id for row in rows), None)
    ghost.submission_review_recipient_mode = _majority_value(
        (row.submission_review_recipient_mode for row in rows),
        SUBMISSION_REVIEW_RECIPIENT_FDS,
    ) or SUBMISSION_REVIEW_RECIPIENT_FDS
    ghost.allowed_role_ids = _ids_on_majority([row.role_id_list() for row in rows]) or None
    ghost.review_recipient_user_ids = _ids_on_majority([row.reviewer_id_list() for row in rows]) or None
    for name in SHARED_FLAG_FIELDS:
        if name in ("data_owner_id", "submission_review_recipient_mode"):
            continue
        setattr(ghost, name, _majority_bool([bool(getattr(row, name, False)) for row in rows]))
    return ghost


@bp.route("/assignments/projects/portfolio/<path:portfolio_key>", methods=["GET", "POST"])
@permission_required_any("admin.assignments.view", "nsd_funds.pm_overview")
def portfolio_page(portfolio_key: str):
    """One assignment record for a programme, listing every country project inside it."""
    _gate_project_admin()
    key = (portfolio_key or "").strip() or _OTHER_PORTFOLIO
    list_filters = _list_filters()
    list_filters["portfolio"] = ""
    portfolio_projects = [
        project
        for project in _projects_visible_to(current_user)
        if _portfolio_key(project.portfolio) == key
    ]
    projects = [
        project for project in portfolio_projects if _project_matches_list_filters(project, list_filters)
    ]
    if not projects:
        abort(404)
    settings = _portfolio_settings(projects)
    form = _settings_form(settings)
    if request.method == "POST":
        _require_edit()
        if form.validate_on_submit():
            try:
                changed = 0
                for project in projects:
                    row = get_or_create_project_assignment(project)
                    custom_name = row.custom_name
                    translations = row.custom_name_translations
                    _apply_settings_form(row, form)
                    row.custom_name = custom_name
                    row.custom_name_translations = translations
                    changed += apply_to_reports(project, user_id=getattr(current_user, "id", None))
                db.session.commit()
                flash(
                    _("Settings saved for %(countries)s country projects and applied to %(n)s report(s).", countries=len(projects), n=changed),
                    "success",
                )
                return redirect(url_for("project_assignments.portfolio_page", portfolio_key=key))
            except Exception as exc:
                request_transaction_rollback()
                current_app.logger.error("Save portfolio settings failed: %s", exc, exc_info=True)
                flash(_("Could not save these settings."), "danger")
    ids = [project.id for project in projects]
    cycles = (
        AssignedForm.query.options(joinedload(AssignedForm.template))
        .filter(
            AssignedForm.project_id.in_(ids),
            AssignedForm.scope == AssignmentScope.project_cycle.value,
        )
        .all()
    )
    by_project: dict = {}
    for cycle in cycles:
        by_project.setdefault(cycle.project_id, []).append(cycle)
    country_rows = []
    for project in projects:
        project_cycles = by_project.get(project.id, [])
        country_rows.append({
            "project": project,
            "country": project.country.name if project.country else "",
            "reports": len(project_cycles),
            "open_reports": sum(1 for cycle in project_cycles if not cycle.is_closed),
            "url": url_for("project_assignments.project_page", project_id=project.id),
        })
    country_rows.sort(key=lambda row: ((row["country"] or "").casefold(), row["project"].reference.casefold()))
    label = _portfolio_label(key)
    _manager, scoped_to_self = scope_manager(current_user, "")
    return render_template(
        "admin/assignments/project_portfolio.html",
        portfolio_label=label,
        portfolio_key=key,
        projects=projects,
        country_rows=country_rows,
        form=form,
        settings=settings,
        assignment_mode="project",
        assignment=None,
        can_edit=can_manage_projects(current_user),
        submission_review_recipient_users=_reviewer_users(settings, form),
        title=label,
        locked_portfolio=key,
        scoped_to_self=scoped_to_self,
        **_monitoring_filter_choices(portfolio_projects),
        **_permission_flags(settings),
    )


@bp.route("/assignments/projects/<int:project_id>", methods=["GET", "POST"])
@permission_required_any("admin.assignments.view", "nsd_funds.pm_overview")
def project_page(project_id: int):
    project = _project_or_404(project_id)
    settings_existed = ProjectAssignment.query.filter_by(project_id=project.id).first() is not None
    settings = get_or_create_project_assignment(project)
    if request.method == "GET" and not settings_existed:
        db.session.commit()
    form = _settings_form(settings)
    if request.method == "POST":
        _require_edit()
        if form.validate_on_submit():
            try:
                _apply_settings_form(settings, form)
                settings.updated_at = utcnow()
                changed = apply_to_reports(project, user_id=getattr(current_user, "id", None))
                db.session.commit()
                if changed:
                    flash(
                        _("Settings saved and applied to %(n)s report(s).", n=changed),
                        "success",
                    )
                else:
                    flash(_("Settings saved. Every report already matched."), "success")
                return redirect(url_for("project_assignments.project_page", project_id=project.id))
            except Exception as exc:
                request_transaction_rollback()
                current_app.logger.error("Save project settings failed: %s", exc, exc_info=True)
                flash(_("Could not save the project settings."), "danger")
    return _render_project_page(project, form, settings=settings)


@bp.route("/assignments/projects/<int:project_id>/edit", methods=["GET", "POST"])
@permission_required_any("admin.assignments.view", "nsd_funds.pm_overview")
def project_edit(project_id: int):
    """Registry modal used by the NSD explorer. The full page is the project assignment."""
    project = _project_or_404(project_id)
    can_edit = can_manage_projects(current_user)
    if request.method == "POST" and not can_edit:
        abort(403)
    form = ProjectForm(obj=project)
    _bind_project_form(form)
    edit_url = url_for("project_assignments.project_edit", project_id=project.id)
    delete_url = url_for("project_assignments.project_delete", project_id=project.id)
    if request.method == "GET":
        form.country_id.data = project.country_id
        form.national_society_id.data = project.national_society_id or 0
        form.status.data = project.status or "Open"
        return render_template(
            "admin/projects/_form_partial.html",
            form=form,
            project=project,
            can_edit=can_edit,
            form_action_url=edit_url,
            delete_url=delete_url if can_edit else None,
            modal=True,
            modal_title=str(_("Edit project %(ref)s", ref=project.reference)) if can_edit else project.reference,
        )
    if form.validate_on_submit() and form.country_id.data and not Project.query.filter(
        Project.reference == form.reference.data.strip(), Project.id != project.id
    ).first():
        try:
            old_reference = project.reference
            project.reference = form.reference.data.strip()
            _save_project_from_form(form, reference=project.reference)
            if old_reference != project.reference:
                sync_cycle_names_for_project(project)
            sync_project_cycle_closure(project)
            db.session.commit()
            if is_json_request() or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return json_ok(message=_("Project saved."))
            flash(_("Project saved."), "success")
            return redirect(url_for("project_assignments.project_page", project_id=project.id))
        except Exception as exc:
            request_transaction_rollback()
            current_app.logger.error("Update project failed: %s", exc, exc_info=True)
            flash(_("Could not save the project."), "danger")
    elif Project.query.filter(Project.reference == (form.reference.data or "").strip(), Project.id != project.id).first():
        flash(_("A project with this reference already exists."), "warning")
    else:
        flash(_("Select a country."), "warning")
    return redirect(url_for("project_assignments.project_page", project_id=project.id))


_INLINE_LIMITS = {
    "reference": 80, "title": 500, "funding_modality": 120, "categories": 2000,
    "focal_name": 255, "focal_email": 255, "manager_name": 255, "manager_email": 255,
    "planned_overview": 20000,
}


@bp.route("/assignments/projects/<int:project_id>/inline", methods=["POST"])
@permission_required("admin.assignments.edit")
def project_inline_save(project_id: int):
    project = _project_or_404(project_id)
    _require_edit()
    payload = request.get_json(silent=True) or {}
    fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else None
    if not fields:
        return json_bad_request(str(_("Nothing to save.")))
    old_reference = project.reference
    try:
        if "reference" in fields:
            reference = str(fields.get("reference") or "").strip()
            if not reference or len(reference) > _INLINE_LIMITS["reference"]:
                return json_bad_request(str(_("Reference is required.")))
            other = Project.query.filter(Project.reference == reference, Project.id != project.id).first()
            if other:
                return json_bad_request(str(_("A project with this reference already exists.")))
            project.reference = reference
        for key in ("title", "funding_modality", "categories", "focal_name", "manager_name", "planned_overview"):
            if key in fields:
                text = str(fields.get(key) or "").strip()[: _INLINE_LIMITS[key]]
                setattr(project, key, text or None)
        for key in ("focal_email", "manager_email"):
            if key in fields:
                text = str(fields.get(key) or "").strip()
                if text and ("@" not in text or " " in text or len(text) > 255):
                    return json_bad_request(str(_("Enter a valid email address.")))
                setattr(project, key, text or None)
        if "national_society_id" in fields:
            raw = str(fields.get("national_society_id") or "").strip()
            if not raw or raw == "0":
                project.national_society_id = None
                project.organization_name = None
            else:
                society = NationalSociety.query.get(int(raw))
                if society is None:
                    return json_bad_request(str(_("Choose a National Society.")))
                project.national_society_id = society.id
                project.organization_name = society.name
        if "status" in fields:
            status = str(fields.get("status") or "").strip().capitalize()
            if status not in PROJECT_STATUSES:
                return json_bad_request(str(_("Choose a valid status.")))
            project.status = status
        if "start_date" in fields:
            project.start_date = _parse_date(fields.get("start_date"))
        if "end_date" in fields:
            project.end_date = _parse_date(fields.get("end_date"))
        if "amount_granted" in fields:
            project.amount_granted = _parse_money(fields.get("amount_granted"))
    except ValueError as exc:
        code = str(exc)
        if code == "date":
            return json_bad_request(str(_("Enter a valid date.")))
        if code == "money":
            return json_bad_request(str(_("Enter a valid amount.")))
        return json_bad_request(str(_("Could not save the project.")))
    project.updated_at = utcnow()
    if old_reference != project.reference:
        sync_cycle_names_for_project(project)
    if "status" in fields:
        sync_project_cycle_closure(project)
    try:
        db.session.commit()
    except Exception as exc:
        request_transaction_rollback()
        current_app.logger.error("Inline project save failed: %s", exc, exc_info=True)
        return json_bad_request(str(_("Could not save the project.")))
    return json_ok(message=str(_("Project saved.")))


def _parse_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return dt.date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ValueError("date") from exc


def _parse_money(value):
    from decimal import Decimal, InvalidOperation

    text = str(value or "").strip().replace(",", "").replace(" ", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("money") from exc


@bp.route("/assignments/projects/<int:project_id>/delete", methods=["POST"])
@permission_required("admin.assignments.delete")
def project_delete(project_id: int):
    project = _project_or_404(project_id)
    # A project's own reports are removed with it. Block only when a campaign still lists the project.
    in_use = (
        AssignmentEntityStatus.query.join(
            AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id
        )
        .filter(
            AssignmentEntityStatus.entity_type == EntityType.project.value,
            AssignmentEntityStatus.entity_id == project.id,
            AssignedForm.scope != AssignmentScope.project_cycle.value,
        )
        .count()
    )
    if in_use:
        flash(
            _("Cannot delete %(ref)s: a campaign assignment still includes it.", ref=project.reference),
            "warning",
        )
        return redirect(url_for("project_assignments.project_page", project_id=project.id))
    try:
        ref = project.reference
        for cycle in list(project.cycle_assignments or []):
            db.session.delete(cycle)
        if project.assignment_settings is not None:
            db.session.delete(project.assignment_settings)
        db.session.delete(project)
        db.session.commit()
        flash(_("Deleted project %(ref)s.", ref=ref), "success")
    except Exception as exc:
        request_transaction_rollback()
        current_app.logger.error("Delete project failed: %s", exc, exc_info=True)
        flash(_("Could not delete the project."), "danger")
        return redirect(url_for("project_assignments.project_page", project_id=project.id))
    return redirect(url_for("assignment_management.manage_assignments", type="project"))


def _add_report(project: Project, slot: str, template_id: int, *, due, start, end):
    ensure_project_cycle_assignment(
        project,
        int(template_id),
        slot,
        period_start=start,
        period_end=end,
        due_date=due,
    )


@bp.route("/assignments/projects/<int:project_id>/reports", methods=["POST"])
@permission_required("admin.assignments.edit")
def project_add_report(project_id: int):
    project = _project_or_404(project_id)
    slot = (request.form.get("slot") or "").strip()
    offered = {str(item.get("slot") or ""): item for item in plugin_report_types(project)}
    meta = offered.get(slot)
    template_id = None
    start = end = due = None
    if meta is not None:
        template_id = meta.get("template_id")
        start = meta.get("period_start")
        end = meta.get("period_end")
        due = meta.get("due_date")
    else:
        template_id = request.form.get("template_id", type=int)
    due_raw = (request.form.get("due_date") or "").strip()
    if due_raw:
        try:
            due = dt.datetime.combine(dt.date.fromisoformat(due_raw[:10]), dt.datetime.min.time())
        except ValueError:
            due = None
    if not slot or not template_id:
        flash(_("Choose a report and a published template."), "warning")
        return redirect(url_for("project_assignments.project_page", project_id=project.id))
    try:
        _add_report(project, slot, int(template_id), due=due, start=start, end=end)
        db.session.commit()
        flash(_("Added report %(slot)s.", slot=slot), "success")
    except Exception as exc:
        request_transaction_rollback()
        current_app.logger.error("Add project report failed: %s", exc, exc_info=True)
        flash(_("Could not add the report."), "danger")
    return redirect(url_for("project_assignments.project_page", project_id=project.id))


def _cycle_or_404(project: Project, assignment_id: int) -> AssignedForm:
    return AssignedForm.query.filter_by(
        id=assignment_id,
        project_id=project.id,
        scope=AssignmentScope.project_cycle.value,
    ).first_or_404()


@bp.route("/assignments/projects/<int:project_id>/reports/<int:assignment_id>/close", methods=["POST"])
@permission_required("admin.assignments.edit")
def project_report_close(project_id: int, assignment_id: int):
    project = _project_or_404(project_id)
    assignment = _cycle_or_404(project, assignment_id)
    assignment.is_closed = True
    db.session.commit()
    flash(_("Closed report %(name)s.", name=assignment.custom_name or assignment.period_name), "success")
    return redirect(url_for("project_assignments.project_page", project_id=project.id))


@bp.route("/assignments/projects/<int:project_id>/reports/<int:assignment_id>/reopen", methods=["POST"])
@permission_required("admin.assignments.edit")
def project_report_reopen(project_id: int, assignment_id: int):
    project = _project_or_404(project_id)
    assignment = _cycle_or_404(project, assignment_id)
    assignment.is_closed = False
    assignment.is_active = True
    for aes in AssignmentEntityStatus.query.filter_by(assigned_form_id=assignment.id).all():
        aes.reopened_after_close = True
    db.session.commit()
    flash(_("Reopened report %(name)s.", name=assignment.custom_name or assignment.period_name), "success")
    return redirect(url_for("project_assignments.project_page", project_id=project.id))


@bp.route("/assignments/projects/<int:project_id>/reports/<int:assignment_id>/dates", methods=["POST"])
@permission_required("admin.assignments.edit")
def project_report_dates(project_id: int, assignment_id: int):
    project = _project_or_404(project_id)
    assignment = _cycle_or_404(project, assignment_id)
    try:
        assignment.period_start = _parse_date(request.form.get("period_start"))
        assignment.period_end = _parse_date(request.form.get("period_end"))
        due = _parse_date(request.form.get("due_date"))
    except ValueError:
        flash(_("Enter a valid date."), "warning")
        return redirect(url_for("project_assignments.project_page", project_id=project.id))
    aes = AssignmentEntityStatus.query.filter_by(
        assigned_form_id=assignment.id,
        entity_type=EntityType.project.value,
        entity_id=project.id,
    ).first()
    if aes is not None:
        aes.due_date = dt.datetime.combine(due, dt.datetime.min.time()) if due else None
    db.session.commit()
    flash(_("Report dates saved."), "success")
    return redirect(url_for("project_assignments.project_page", project_id=project.id))


def _apply_project_filters(query, *, status="", portfolio="", fund="", country="", region="", manager=""):
    if status:
        if isinstance(status, str):
            query = query.filter(Project.status == status)
        else:
            query = query.filter(Project.status.in_(list(status)))
    if portfolio:
        if portfolio == _OTHER_PORTFOLIO:
            query = query.filter(
                db.or_(
                    Project.portfolio.is_(None),
                    db.func.trim(Project.portfolio) == "",
                    Project.portfolio == _OTHER_PORTFOLIO,
                )
            )
        else:
            query = query.filter(Project.portfolio == portfolio)
    if fund:
        query = query.filter(Project.fund == fund)
    if country or region:
        query = query.join(Country, Project.country_id == Country.id)
        if country:
            query = query.filter(Country.name == country)
        if region:
            query = query.filter(Country.region == region)
    if manager:
        query = query.filter(db.func.lower(Project.manager_email) == manager.casefold())
    return query


def _monitoring_payload() -> dict:
    from app.services.projects import monitoring

    _gate_project_admin()
    args = request.args
    manager, _scoped = scope_manager(current_user, (args.get("manager") or "").strip())
    status_filter = monitoring.statuses_for_filter(args.get("status") or "open")
    query = _apply_project_filters(
        Project.query.options(joinedload(Project.national_society)),
        status=status_filter or "",
        portfolio=(args.get("portfolio") or "").strip(),
        fund=(args.get("fund") or "").strip(),
        country=(args.get("country") or "").strip(),
        region=(args.get("region") or "").strip(),
        manager=manager,
    )
    return monitoring.build_monitoring(query.order_by(Project.reference.asc()).all())


@bp.route("/assignments/projects/monitoring/data", methods=["GET"])
@permission_required_any("admin.assignments.view", "nsd_funds.pm_overview")
def monitoring_data():
    try:
        payload = _monitoring_payload()
    except Exception as exc:
        current_app.logger.error("Project monitoring failed: %s", exc, exc_info=True)
        return json_bad_request(str(_("Could not load project monitoring.")))
    payload.pop("report_rows", None)
    resp = json_ok(payload)
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _csv_safe(value) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@bp.route("/assignments/projects/monitoring/export.csv", methods=["GET"])
@permission_required_any("admin.assignments.view", "nsd_funds.pm_overview")
def monitoring_export():
    try:
        payload = _monitoring_payload()
    except Exception as exc:
        current_app.logger.error("Project monitoring export failed: %s", exc, exc_info=True)
        abort(500)
    columns = [
        ("reference", _("Reference")), ("title", _("Title")), ("country", _("Country")),
        ("period", _("Report")), ("type", _("Type")), ("status", _("Status")), ("bucket", _("Reporting state")),
        ("due", _("Due date")), ("days_overdue", _("Days overdue")), ("days_to_due", _("Days to due")),
        ("completion", _("Completion %")), ("submitted_at", _("Submitted")),
        ("pm", _("Project manager")), ("pm_email", _("Manager email")),
        ("focal", _("Focal person")), ("focal_email", _("Focal email")),
    ]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([str(label) for _key, label in columns])
    for row in payload.get("report_rows", []):
        writer.writerow([_csv_safe(row.get(key)) for key, _label in columns])
    filename = f"project-monitoring-{payload['today']}.csv"
    return Response(
        "\ufeff" + buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
    )


_OTHER_PORTFOLIO = "_"


def _portfolio_key(portfolio: str | None) -> str:
    text = (portfolio or "").strip()
    return text or _OTHER_PORTFOLIO


def _portfolio_label(key: str) -> str:
    if key == _OTHER_PORTFOLIO:
        return _("Other projects")
    return key


def _list_filters() -> dict:
    """Query args the Assignments grid also applies, so a filtered list still finds the programme."""
    args = request.args
    return {
        "manager": (args.get("manager") or args.get("manager_email") or "").strip(),
        "country": (args.get("country") or "").strip(),
        "fund": (args.get("fund") or "").strip(),
        "status": (args.get("project_status") or args.get("status") or "").strip(),
        "portfolio": (args.get("portfolio") or "").strip(),
    }


def _project_matches_list_filters(project, filters: dict) -> bool:
    manager = filters["manager"]
    if manager and (project.manager_email or "").strip().casefold() != manager.casefold():
        return False
    country = filters["country"]
    if country:
        wanted = country.casefold()
        place = project.country
        candidates = []
        if place is not None:
            candidates = [place.name, place.iso3, place.iso2, place.short_name, str(place.id)]
        if wanted not in {(value or "").strip().casefold() for value in candidates}:
            return False
    fund = filters["fund"]
    if fund and (project.fund or "").strip().casefold() != fund.casefold():
        return False
    status = filters["status"].casefold()
    if status in ("open", "active") and not project.is_open:
        return False
    if status in ("closed", "inactive") and project.is_open:
        return False
    portfolio = filters["portfolio"]
    if portfolio and _portfolio_key(project.portfolio).casefold() != portfolio.casefold():
        return False
    return True


def _portfolio_query(filters: dict) -> dict:
    return {name: value for name, value in filters.items() if value and name != "portfolio"}


def _projects_visible_to(user) -> list:
    """Country projects this user may see, scoped to their own when they are a PM viewer."""
    if not can_open_project_admin(user):
        return []
    manager, scoped = scope_manager(user, "")
    query = Project.query.options(
        joinedload(Project.country),
        joinedload(Project.assignment_settings).joinedload(ProjectAssignment.data_owner_user),
    )
    if scoped:
        email = (manager or "").strip().casefold()
        if not email:
            return []
        query = query.filter(db.func.lower(Project.manager_email) == email)
    return query.order_by(Project.reference.asc()).all()


def project_grid_rows(user) -> list:
    """One Assignments-list row per programme. Country projects are listed inside that record."""
    filters = _list_filters()
    projects = [project for project in _projects_visible_to(user) if _project_matches_list_filters(project, filters)]
    if not projects:
        return []
    ids = [project.id for project in projects]
    cycles = (
        AssignedForm.query.options(joinedload(AssignedForm.template))
        .filter(
            AssignedForm.project_id.in_(ids),
            AssignedForm.scope == AssignmentScope.project_cycle.value,
        )
        .all()
    )
    by_project: dict = {}
    for cycle in cycles:
        by_project.setdefault(cycle.project_id, []).append(cycle)
    aes_rows = []
    cycle_ids = [cycle.id for cycle in cycles]
    if cycle_ids:
        aes_rows = AssignmentEntityStatus.query.filter(
            AssignmentEntityStatus.assigned_form_id.in_(cycle_ids),
            AssignmentEntityStatus.entity_type == EntityType.project.value,
        ).all()
    due_by_form = {}
    for aes in aes_rows:
        if aes.due_date is not None:
            current = due_by_form.get(aes.assigned_form_id)
            if current is None or utc_sort_key(aes.due_date) < utc_sort_key(current):
                due_by_form[aes.assigned_form_id] = aes.due_date
    grouped: dict = {}
    for project in projects:
        grouped.setdefault(_portfolio_key(project.portfolio), []).append(project)
    rows = []
    for key in sorted(grouped, key=lambda item: _portfolio_label(item).casefold()):
        members = grouped[key]
        template_names = []
        report_count = 0
        next_due = None
        for project in members:
            for cycle in by_project.get(project.id, []):
                report_count += 1
                name = cycle.template.name if cycle.template else ""
                if name and name not in template_names:
                    template_names.append(name)
                if cycle.is_closed:
                    continue
                due = due_by_form.get(cycle.id)
                if due is not None and (next_due is None or utc_sort_key(due) < utc_sort_key(next_due)):
                    next_due = due
        label = _portfolio_label(key)
        country_count = len(members)
        template_label = _("%(n)s country projects", n=country_count)
        if report_count:
            template_label = f"{template_label} · " + _("%(n)s reports", n=report_count)
        if template_names:
            template_label = f"{template_label} · {', '.join(template_names)}"
        rows.append({
            "row_type": "project",
            "id": members[0].id,
            "period_name": "",
            "custom_name": label,
            "display_name": label,
            "template_name": template_label,
            "country": filters["country"],
            "portfolio": "" if key == _OTHER_PORTFOLIO else key,
            "fund": filters["fund"],
            "manager_name": "",
            "manager_email": filters["manager"],
            "project_status": filters["status"] or ("Open" if any(project.is_open for project in members) else "Closed"),
            "data_owner_user_id": None,
            "data_owner_name": "",
            "data_owner_email": "",
            "data_owner_title": "",
            "data_owner_active": True,
            "data_owner_profile_color": "",
            "allowed_roles": [],
            "allowed_roles_text": "",
            "due_date": next_due.strftime("%Y-%m-%d") if next_due else "",
            "expiry_date": "",
            "is_active": any(project.is_open for project in members),
            "is_closed": not any(project.is_open for project in members),
            "has_public_url": False,
            "is_public_active": False,
            "public_url": "",
            "toggle_url": "",
            "toggle_active_url": "",
            "close_url": "",
            "reopen_closed_url": "",
            "generate_url": "",
            "view_submissions_url": "",
            "edit_url": url_for(
                "project_assignments.portfolio_page",
                portfolio_key=key,
                **_portfolio_query(filters),
            ),
            "delete_url": "",
            "delete_confirm": "",
            "close_confirm": "",
        })
    return rows
