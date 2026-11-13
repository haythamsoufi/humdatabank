"""Admin CRUD for the core project registry (project-based reporting)."""

from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_babel import _
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import DateField, DecimalField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional

from app import db
from app.models import Country
from app.models.projects import Project
from app.routes.admin.shared import permission_required
from app.services.organization.authorization_service import AuthorizationService
from app.services.projects.service import (
    ensure_project_cycle_assignment,
    sync_cycle_names_for_project,
    sync_project_cycle_closure,
    upsert_project,
)
from app.utils.api.api_responses import json_bad_request, json_ok
from app.utils.common.datetime_helpers import utcnow
from app.utils.http.request_utils import is_json_request
from app.utils.database.transactions import request_transaction_rollback

bp = Blueprint("project_management", __name__, url_prefix="/admin/projects")

PROJECT_STATUSES = ("Open", "Active", "Closed", "Archived")


class ProjectForm(FlaskForm):
    reference = StringField(_("Reference"), validators=[DataRequired(), Length(max=80)])
    title = StringField(_("Title"), validators=[Optional(), Length(max=500)])
    portfolio = StringField(_("Category"), validators=[Optional(), Length(max=40)])
    fund = StringField(_("Fund / programme"), validators=[Optional(), Length(max=40)])
    country_id = SelectField(_("Country"), coerce=int, validators=[DataRequired()])
    organization_name = StringField(_("Organization / National Society"), validators=[Optional(), Length(max=255)])
    status = SelectField(
        _("Status"),
        choices=[(s, s) for s in PROJECT_STATUSES],
        validators=[DataRequired()],
    )
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


_PM_PERMISSION = "nsd_funds.pm_overview"
_NSD_ADMIN_PERMISSION = "admin.nsd_funds.manage"


def _can_manage_projects() -> bool:
    return AuthorizationService.is_system_manager(current_user) or AuthorizationService.has_rbac_permission(
        current_user, "admin.assignments.edit"
    )


def _can_view_all_projects() -> bool:
    return (
        AuthorizationService.is_system_manager(current_user)
        or AuthorizationService.has_rbac_permission(current_user, "admin.assignments.view")
        or AuthorizationService.has_rbac_permission(current_user, "admin.assignments.edit")
        or AuthorizationService.has_rbac_permission(current_user, _NSD_ADMIN_PERMISSION)
    )


def _is_pm_viewer() -> bool:
    return AuthorizationService.has_rbac_permission(current_user, _PM_PERMISSION)


def _can_see_project(project: Project) -> bool:
    if _can_view_all_projects():
        return True
    if not _is_pm_viewer():
        return False
    return (project.manager_email or "").strip().casefold() == (getattr(current_user, "email", "") or "").strip().casefold()


def _country_choices():
    return [(0, _("— Select country —"))] + [
        (c.id, c.name) for c in Country.query.order_by(Country.name.asc()).all()
    ]


def _wants_json_post() -> bool:
    return is_json_request() or request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _project_form_partial(
    form: ProjectForm,
    *,
    project: Project | None,
    can_edit: bool,
    form_action_url: str,
    modal_title: str,
    delete_url: str | None = None,
) -> str:
    return render_template(
        "admin/projects/_form_partial.html",
        form=form,
        project=project,
        can_edit=can_edit,
        form_action_url=form_action_url,
        delete_url=delete_url,
        modal=True,
        modal_title=modal_title,
    )


def _populate_project_form(form: ProjectForm, project: Project) -> None:
    form.country_id.data = project.country_id
    form.status.data = project.status or "Open"


@bp.before_request
def _gate():
    if not current_user.is_authenticated:
        abort(401)
    if not (_can_view_all_projects() or _is_pm_viewer()):
        abort(403)


@bp.route("/", methods=["GET"])
def project_list():
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    portfolio = (request.args.get("portfolio") or "").strip()
    fund = (request.args.get("fund") or "").strip()
    country = (request.args.get("country") or "").strip()
    manager = (request.args.get("manager") or "").strip()
    scoped_to_self = False
    if not _can_view_all_projects():
        manager = (getattr(current_user, "email", "") or "").strip()
        scoped_to_self = True
    query = Project.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                Project.reference.ilike(like),
                Project.title.ilike(like),
                Project.organization_name.ilike(like),
            )
        )
    if status:
        query = query.filter(Project.status == status)
    if portfolio:
        query = query.filter(Project.portfolio == portfolio)
    if fund:
        query = query.filter(Project.fund == fund)
    if country:
        query = query.join(Country, Project.country_id == Country.id).filter(Country.name == country)
    if manager:
        query = query.filter(db.func.lower(Project.manager_email) == manager.casefold())
    projects = query.order_by(Project.reference.asc()).all()
    funds = sorted({p.fund for p in Project.query.with_entities(Project.fund).distinct() if p.fund})
    portfolios = sorted({
        p.portfolio for p in Project.query.with_entities(Project.portfolio).distinct() if p.portfolio
    })
    countries = sorted({
        name for (name,) in (
            db.session.query(Country.name)
            .join(Project, Project.country_id == Country.id)
            .distinct()
            .all()
        ) if name
    })
    open_edit_id = request.args.get("edit", type=int)
    return render_template(
        "admin/projects/list.html",
        projects=projects,
        q=q,
        status_filter=status,
        portfolio_filter=portfolio,
        fund_filter=fund,
        country_filter=country,
        manager_filter=manager,
        scoped_to_self=scoped_to_self,
        all_statuses=PROJECT_STATUSES,
        all_portfolios=portfolios,
        all_funds=funds,
        all_countries=countries,
        can_edit=_can_manage_projects(),
        title=_("My projects") if scoped_to_self else _("Projects"),
        open_edit_id=open_edit_id if open_edit_id else None,
    )


@bp.route("/<int:project_id>", methods=["GET"])
def project_detail(project_id: int):
    project = Project.query.get_or_404(project_id)
    if not _can_see_project(project):
        abort(403)
    pm_email = None
    scoped_to_self = False
    if not _can_view_all_projects() and _is_pm_viewer():
        pm_email = (getattr(current_user, "email", "") or "").strip()
        scoped_to_self = True
    from plugins.nsd_report_forms.overview import data as nsd_overview

    overview = nsd_overview.project_detail(project.reference, pm_email=pm_email)
    if overview is None:
        abort(404)
    list_params = {}
    if scoped_to_self and pm_email:
        list_params["manager"] = pm_email
    return render_template(
        "admin/projects/detail.html",
        project=project,
        p=overview,
        can_edit=_can_manage_projects(),
        scoped_to_self=scoped_to_self,
        list_url=url_for("project_management.project_list", **list_params),
        open_edit_id=request.args.get("edit", type=int),
    )


@bp.route("/new", methods=["GET", "POST"])
@permission_required("admin.assignments.edit")
def project_new():
    form = ProjectForm()
    form.country_id.choices = _country_choices()
    if form.validate_on_submit():
        if form.country_id.data == 0:
            flash(_("Select a country."), "warning")
        elif Project.query.filter_by(reference=form.reference.data.strip()).first():
            flash(_("A project with this reference already exists."), "warning")
        else:
            try:
                proj = upsert_project(
                    reference=form.reference.data,
                    country_id=form.country_id.data,
                    title=form.title.data,
                    portfolio=form.portfolio.data,
                    fund=form.fund.data,
                    organization_name=form.organization_name.data,
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
                db.session.commit()
                flash(_("Project %(ref)s created.", ref=proj.reference), "success")
                return redirect(url_for("project_management.project_detail", project_id=proj.id))
            except Exception as e:
                request_transaction_rollback()
                current_app.logger.error("Create project failed: %s", e, exc_info=True)
                flash(_("Could not create the project."), "danger")
    return render_template(
        "admin/projects/form.html",
        form=form,
        project=None,
        can_edit=True,
        title=_("New project"),
        form_action_url=url_for("project_management.project_new"),
        modal=False,
    )


@bp.route("/<int:project_id>/edit", methods=["GET", "POST"])
def project_edit(project_id):
    project = Project.query.get_or_404(project_id)
    if not _can_see_project(project):
        abort(403)
    can_edit = _can_manage_projects()
    if request.method == "POST" and not can_edit:
        abort(403)
    form = ProjectForm(obj=project)
    form.country_id.choices = _country_choices()
    edit_url = url_for("project_management.project_edit", project_id=project.id)
    delete_url = url_for("project_management.project_delete", project_id=project.id)
    modal_title = project.reference
    if can_edit:
        modal_title = str(_("Edit project %(ref)s", ref=project.reference))

    if request.method == "GET":
        if request.args.get("partial") != "1":
            return redirect(url_for("project_management.project_detail", project_id=project_id))
        _populate_project_form(form, project)
        return _project_form_partial(
            form,
            project=project,
            can_edit=can_edit,
            form_action_url=edit_url,
            modal_title=modal_title,
            delete_url=delete_url if can_edit else None,
        )

    if form.validate_on_submit():
        if form.country_id.data == 0:
            msg = _("Select a country.")
            if _wants_json_post():
                return json_bad_request(msg, form_html=_project_form_partial(
                    form, project=project, can_edit=can_edit, form_action_url=edit_url,
                    modal_title=modal_title, delete_url=delete_url if can_edit else None,
                ))
            flash(msg, "warning")
        else:
            other = Project.query.filter(
                Project.reference == form.reference.data.strip(),
                Project.id != project.id,
            ).first()
            if other:
                msg = _("A project with this reference already exists.")
                if _wants_json_post():
                    return json_bad_request(msg, form_html=_project_form_partial(
                        form, project=project, can_edit=can_edit, form_action_url=edit_url,
                        modal_title=modal_title, delete_url=delete_url if can_edit else None,
                    ))
                flash(msg, "warning")
            else:
                try:
                    old_reference = project.reference
                    project.reference = form.reference.data.strip()
                    upsert_project(
                        reference=project.reference,
                        country_id=form.country_id.data,
                        title=form.title.data,
                        portfolio=form.portfolio.data,
                        fund=form.fund.data,
                        organization_name=form.organization_name.data,
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
                    if old_reference != project.reference:
                        sync_cycle_names_for_project(project)
                    sync_project_cycle_closure(project)
                    db.session.commit()
                    if _wants_json_post():
                        return json_ok(message=_("Project saved."))
                    flash(_("Project saved."), "success")
                    return redirect(url_for("project_management.project_detail", project_id=project.id))
                except Exception as e:
                    request_transaction_rollback()
                    current_app.logger.error("Update project failed: %s", e, exc_info=True)
                    if _wants_json_post():
                        return json_bad_request(_("Could not save the project."))
                    flash(_("Could not save the project."), "danger")
    elif _wants_json_post():
        return (
            jsonify(
                {
                    "success": False,
                    "errors": form.errors,
                    "form_html": _project_form_partial(
                        form,
                        project=project,
                        can_edit=can_edit,
                        form_action_url=edit_url,
                        modal_title=modal_title,
                        delete_url=delete_url if can_edit else None,
                    ),
                }
            ),
            400,
        )
    _populate_project_form(form, project)
    return render_template(
        "admin/projects/form.html",
        form=form,
        project=project,
        can_edit=can_edit,
        title=modal_title,
        form_action_url=edit_url,
        modal=False,
    )


@bp.route("/<int:project_id>/delete", methods=["POST"])
@permission_required("admin.assignments.edit")
def project_delete(project_id):
    project = Project.query.get_or_404(project_id)
    from app.models import AssignmentEntityStatus
    from app.models.enums import EntityType

    in_use = AssignmentEntityStatus.query.filter_by(
        entity_type=EntityType.project.value, entity_id=project.id
    ).count()
    if in_use:
        msg = _("Cannot delete %(ref)s: it is on %(n)s assignment submission(s).", ref=project.reference, n=in_use)
        if _wants_json_post():
            return json_bad_request(msg)
        flash(msg, "warning")
        return redirect(url_for("project_management.project_detail", project_id=project.id))
    try:
        ref = project.reference
        db.session.delete(project)
        db.session.commit()
        if _wants_json_post():
            return json_ok(message=_("Deleted project %(ref)s.", ref=ref))
        flash(_("Deleted project %(ref)s.", ref=ref), "success")
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error("Delete project failed: %s", e, exc_info=True)
        if _wants_json_post():
            return json_bad_request(_("Could not delete the project."))
        flash(_("Could not delete the project."), "danger")
    return redirect(url_for("project_management.project_list"))


@bp.route("/<int:project_id>/cycles", methods=["POST"])
@permission_required("admin.assignments.edit")
def project_add_cycle(project_id):
    """Add a report cycle (Y1Q1… / Final) for this project."""
    project = Project.query.get_or_404(project_id)
    payload = request.get_json(silent=True) if request.is_json else None
    slot = ((payload or {}).get("slot") if payload else None) or request.form.get("slot") or ""
    slot = str(slot).strip()
    from plugins.nsd_report_forms.constants import (
        FINAL_SLOT,
        FINAL_TEMPLATE_KEY,
        QUARTER_TEMPLATE_KEY,
        parse_quarter_slot,
    )
    from plugins.nsd_report_forms import schedule as nsd_schedule
    from plugins.nsd_report_forms.importer import restrictions

    if slot != FINAL_SLOT and not parse_quarter_slot(slot):
        flash(_("Choose a valid cycle (Y1Q1…Y3Q4 or Final)."), "warning")
        return redirect(url_for("project_management.project_detail", project_id=project.id))
    try:
        nsd_schedule.ensure_cbf_templates_ready()
        key = FINAL_TEMPLATE_KEY if slot == FINAL_SLOT else QUARTER_TEMPLATE_KEY
        tpl_id = nsd_schedule._template_id(key)
        if tpl_id is None:
            flash(_("NSD report templates are not published yet."), "danger")
            return redirect(url_for("project_management.project_detail", project_id=project.id))
        due_raw = (request.form.get("due_date") or (payload or {}).get("due_date") or "").strip()
        due = None
        if due_raw:
            from datetime import date, datetime
            try:
                due = datetime.combine(date.fromisoformat(due_raw[:10]), datetime.min.time())
            except ValueError:
                due = None
        af, _aes = ensure_project_cycle_assignment(project, tpl_id, slot, due_date=due)
        restrictions.sync_nsd_audience_on_assignment(
            af.id, allow_focal=(slot == FINAL_SLOT), allow_pm=True
        )
        db.session.commit()
        flash(_("Added report cycle %(slot)s.", slot=slot), "success")
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error("Add project cycle failed: %s", e, exc_info=True)
        flash(_("Could not add the report cycle."), "danger")
    return redirect(url_for("project_management.project_detail", project_id=project.id))


@bp.route("/<int:project_id>/cycles/<int:assignment_id>/close", methods=["POST"])
@permission_required("admin.assignments.edit")
def project_cycle_close(project_id, assignment_id):
    project = Project.query.get_or_404(project_id)
    from app.models import AssignedForm
    from app.models.enums import AssignmentScope

    af = AssignedForm.query.filter_by(
        id=assignment_id,
        project_id=project.id,
        scope=AssignmentScope.project_cycle.value,
    ).first_or_404()
    af.is_closed = True
    db.session.commit()
    flash(_("Closed cycle %(name)s.", name=af.custom_name or af.period_name), "success")
    return redirect(url_for("project_management.project_detail", project_id=project.id))


@bp.route("/<int:project_id>/cycles/<int:assignment_id>/reopen", methods=["POST"])
@permission_required("admin.assignments.edit")
def project_cycle_reopen(project_id, assignment_id):
    project = Project.query.get_or_404(project_id)
    from app.models import AssignedForm, AssignmentEntityStatus
    from app.models.enums import AssignmentScope

    af = AssignedForm.query.filter_by(
        id=assignment_id,
        project_id=project.id,
        scope=AssignmentScope.project_cycle.value,
    ).first_or_404()
    af.is_closed = False
    af.is_active = True
    for aes in AssignmentEntityStatus.query.filter_by(assigned_form_id=af.id).all():
        aes.reopened_after_close = True
    db.session.commit()
    flash(_("Reopened cycle %(name)s.", name=af.custom_name or af.period_name), "success")
    return redirect(url_for("project_management.project_detail", project_id=project.id))
