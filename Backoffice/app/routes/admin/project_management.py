"""Admin CRUD for the core project registry (project-based reporting)."""

from __future__ import annotations

import csv
import io
from typing import Sequence

from flask import Blueprint, Response, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_babel import _
from flask_login import current_user
from flask_wtf import FlaskForm
from sqlalchemy.orm import joinedload
from wtforms import DateField, DecimalField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional

from app import db
from app.models import Country, NationalSociety
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
    national_society_id = SelectField(
        _("National Society"),
        coerce=_ns_id,
        validators=[Optional()],
        choices=[],
    )
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


def _ns_choices():
    rows = NationalSociety.query.order_by(NationalSociety.name.asc()).all()
    return [(0, "—")] + [(row.id, row.name) for row in rows]


def _ns_inline_options():
    return [
        {"value": "" if ns_id == 0 else str(ns_id), "label": name}
        for ns_id, name in _ns_choices()
    ]


def _society_for_form(form: ProjectForm) -> NationalSociety | None:
    ns_id = form.national_society_id.data or 0
    if not ns_id:
        return None
    return NationalSociety.query.get(int(ns_id))


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


def _bind_project_form(form: ProjectForm) -> None:
    form.country_id.choices = _country_choices()
    form.national_society_id.choices = _ns_choices()


def _populate_project_form(form: ProjectForm, project: Project) -> None:
    form.country_id.data = project.country_id
    form.national_society_id.data = project.national_society_id or 0
    form.status.data = project.status or "Open"


@bp.before_request
def _gate():
    if not current_user.is_authenticated:
        abort(401)
    if not (_can_view_all_projects() or _is_pm_viewer()):
        abort(403)


def _apply_project_filters(
    query,
    *,
    q: str = "",
    status: str | Sequence[str] = "",
    portfolio: str = "",
    fund: str = "",
    country: str = "",
    region: str = "",
    manager: str = "",
):
    """Filters shared by the registry grid and the monitoring tab."""
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
        if isinstance(status, str):
            query = query.filter(Project.status == status)
        else:
            query = query.filter(Project.status.in_(list(status)))
    if portfolio:
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


def _scope_manager(requested: str) -> tuple[str, bool]:
    """(manager email filter, scoped_to_self). PM-only viewers always see their own projects."""
    if _can_view_all_projects():
        return requested, False
    return (getattr(current_user, "email", "") or "").strip(), True


@bp.route("/", methods=["GET"])
def project_list():
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    portfolio = (request.args.get("portfolio") or "").strip()
    fund = (request.args.get("fund") or "").strip()
    country = (request.args.get("country") or "").strip()
    manager, scoped_to_self = _scope_manager((request.args.get("manager") or "").strip())
    query = _apply_project_filters(
        Project.query, q=q, status=status, portfolio=portfolio, fund=fund, country=country, manager=manager
    )
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
    regions = sorted({
        name for (name,) in (
            db.session.query(Country.region)
            .join(Project, Project.country_id == Country.id)
            .distinct()
            .all()
        ) if name
    })
    managers = []
    if not scoped_to_self:
        seen = set()
        for email, name in (
            db.session.query(Project.manager_email, Project.manager_name)
            .filter(Project.manager_email.isnot(None), Project.manager_email != "")
            .order_by(Project.manager_name.asc(), Project.manager_email.asc())
            .all()
        ):
            key = (email or "").strip().casefold()
            if key and key not in seen:
                seen.add(key)
                managers.append({"email": email.strip(), "label": (name or "").strip() or email.strip()})
    open_edit_id = request.args.get("edit", type=int)
    return render_template(
        "admin/projects/list.html",
        all_managers=managers,
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
        all_regions=regions,
        can_edit=_can_manage_projects(),
        title=_("My projects") if scoped_to_self else _("Projects"),
        open_edit_id=open_edit_id if open_edit_id else None,
    )


# --------------------------------------------------------------------------- monitoring tab
def _monitoring_payload() -> dict:
    """Monitoring data for the projects the viewer may see, filtered by the query string."""
    from app.services.projects import monitoring

    args = request.args
    manager, _scoped = _scope_manager((args.get("manager") or "").strip())
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


@bp.route("/monitoring/data", methods=["GET"])
def monitoring_data():
    """JSON for the Monitoring tab (KPIs, chart series, worklists)."""
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


@bp.route("/monitoring/export.csv", methods=["GET"])
def monitoring_export():
    """One row per project report with its due date, bucket and project contacts."""
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


def _logframe_targets(project: Project) -> list:
    plan = project.plan_data if isinstance(project.plan_data, dict) else {}
    if plan.get("source") != "marc_logframe":
        return []
    indicators = plan.get("indicators")
    if not isinstance(indicators, list):
        return []
    return [row for row in indicators if isinstance(row, dict)]


def _cycle_rows(project: Project) -> list:
    """Report rows for cycles stored on the project, in slot order."""
    from app.models import AssignmentEntityStatus
    from app.models.enums import EntityType
    from app.services.projects.service import list_project_cycle_assignments, parse_cycle_slot
    from plugins.global_awards.constants import PORTFOLIO
    from plugins.global_awards.importer.schedule import cycle_by_slot

    order = {"Y1Q1": 1, "Y1Q2": 2, "Y1Q3": 3, "Final": 4}
    rows = []
    for assignment in list_project_cycle_assignments(project):
        aes = AssignmentEntityStatus.query.filter_by(
            assigned_form_id=assignment.id,
            entity_type=EntityType.project.value,
            entity_id=project.id,
        ).first()
        slot = parse_cycle_slot(assignment.period_name) or assignment.period_name
        official = cycle_by_slot(slot) if (project.portfolio or "") == PORTFOLIO else None
        review_note = ""
        kind = "quarter"
        if official is not None:
            kind = official.kind
            review_note = (
                f"Region {official.region_due.strftime('%d/%m/%Y')}"
                f" · Geneva {official.geneva_due.strftime('%d/%m/%Y')}"
                f" · DHR {official.dhr_due.strftime('%d/%m/%Y')}"
            )
        rows.append({
            "label": slot,
            "kind": kind,
            "start": assignment.period_start,
            "end": assignment.period_end,
            "due": aes.due_date if aes is not None else None,
            "review_note": review_note,
            "done": False,
            "deadline_status": None,
            "submitted": None,
            "aes_id": aes.id if aes is not None else None,
            "overall": None,
            "rate": None,
            "activities": None,
            "assignment_id": assignment.id,
            "closed": bool(assignment.is_closed),
            "_order": order.get(slot, 50),
        })
    rows.sort(key=lambda row: (row["_order"], row["label"] or ""))
    return rows


def _page_from_project(project: Project) -> dict:
    """Project page when the NSD overview has no row for this reference."""
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
        "expenditure": None,
        "ns_focal": project.focal_name or "",
        "ns_focal_email": project.focal_email or "",
        "pm": project.manager_name or "",
        "pm_email": project.manager_email or "",
        "country_id": project.country_id,
        "reports": _cycle_rows(project),
        "outcomes": [],
        "overview": project.planned_overview or "",
        "logframe_targets": _logframe_targets(project),
    }


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
        overview = _page_from_project(project)
    elif _logframe_targets(project) or (
        isinstance(project.plan_data, dict) and project.plan_data.get("source") == "marc_logframe"
    ):
        overview["logframe_targets"] = _logframe_targets(project)
        overview["overview"] = overview.get("overview") or project.planned_overview or ""
        overview["start"] = project.start_date or overview.get("start")
        overview["end"] = project.end_date or overview.get("end")
        overview["reports"] = _cycle_rows(project)
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
        ns_options=_ns_inline_options(),
    )


@bp.route("/new", methods=["GET", "POST"])
@permission_required("admin.assignments.edit")
def project_new():
    form = ProjectForm()
    _bind_project_form(form)
    if form.validate_on_submit():
        if form.country_id.data == 0:
            flash(_("Select a country."), "warning")
        elif Project.query.filter_by(reference=form.reference.data.strip()).first():
            flash(_("A project with this reference already exists."), "warning")
        else:
            try:
                society = _society_for_form(form)
                proj = upsert_project(
                    reference=form.reference.data,
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


_INLINE_LIMITS = {
    "reference": 80,
    "title": 500,
    "organization_name": 255,
    "funding_modality": 120,
    "categories": 2000,
    "focal_name": 255,
    "focal_email": 255,
    "manager_name": 255,
    "manager_email": 255,
    "planned_overview": 20000,
}


def _clean_inline_email(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if "@" not in text or " " in text or len(text) > 255:
        raise ValueError("email")
    return text


@bp.route("/<int:project_id>/inline", methods=["POST"])
def project_inline_save(project_id):
    """Save fields edited in place on the project page."""
    project = Project.query.get_or_404(project_id)
    if not _can_see_project(project):
        abort(403)
    if not _can_manage_projects():
        abort(403)
    payload = request.get_json(silent=True) or {}
    fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else None
    if not fields:
        return json_bad_request(str(_("Nothing to save.")))

    old_reference = project.reference
    updates = {}
    try:
        if "reference" in fields:
            reference = str(fields.get("reference") or "").strip()
            if not reference:
                return json_bad_request(str(_("Reference is required.")))
            if len(reference) > _INLINE_LIMITS["reference"]:
                return json_bad_request(str(_("Reference is too long.")))
            other = Project.query.filter(Project.reference == reference, Project.id != project.id).first()
            if other:
                return json_bad_request(str(_("A project with this reference already exists.")))
            updates["reference"] = reference
        if "title" in fields:
            updates["title"] = str(fields.get("title") or "").strip()[: _INLINE_LIMITS["title"]] or None
        if "national_society_id" in fields:
            raw = str(fields.get("national_society_id") or "").strip()
            if not raw or raw == "0":
                updates["national_society_id"] = None
                updates["organization_name"] = None
            else:
                try:
                    ns_id = int(raw)
                except ValueError:
                    return json_bad_request(str(_("Choose a National Society.")))
                society = NationalSociety.query.get(ns_id)
                if society is None:
                    return json_bad_request(str(_("Choose a National Society.")))
                updates["national_society_id"] = society.id
                updates["organization_name"] = society.name
        if "funding_modality" in fields:
            updates["funding_modality"] = str(fields.get("funding_modality") or "").strip()[: _INLINE_LIMITS["funding_modality"]] or None
        if "categories" in fields:
            updates["categories"] = str(fields.get("categories") or "").strip()[: _INLINE_LIMITS["categories"]] or None
        if "status" in fields:
            status = str(fields.get("status") or "").strip().capitalize()
            if status not in PROJECT_STATUSES:
                return json_bad_request(str(_("Choose a valid status.")))
            updates["status"] = status
        if "start_date" in fields:
            updates["start_date"] = _inline_date(fields.get("start_date"))
        if "end_date" in fields:
            updates["end_date"] = _inline_date(fields.get("end_date"))
        if "amount_granted" in fields:
            updates["amount_granted"] = _inline_money(fields.get("amount_granted"))
        if "focal_name" in fields:
            updates["focal_name"] = str(fields.get("focal_name") or "").strip()[: _INLINE_LIMITS["focal_name"]] or None
        if "focal_email" in fields:
            updates["focal_email"] = _clean_inline_email(str(fields.get("focal_email") or "")) or None
        if "manager_name" in fields:
            updates["manager_name"] = str(fields.get("manager_name") or "").strip()[: _INLINE_LIMITS["manager_name"]] or None
        if "manager_email" in fields:
            updates["manager_email"] = _clean_inline_email(str(fields.get("manager_email") or "")) or None
        if "planned_overview" in fields:
            updates["planned_overview"] = str(fields.get("planned_overview") or "").strip()[: _INLINE_LIMITS["planned_overview"]] or None
    except ValueError as exc:
        if str(exc) == "email":
            return json_bad_request(str(_("Enter a valid email address.")))
        if str(exc) == "date":
            return json_bad_request(str(_("Enter a valid date.")))
        if str(exc) == "money":
            return json_bad_request(str(_("Enter a valid amount.")))
        return json_bad_request(str(_("Could not save the project.")))
    if not updates:
        return json_bad_request(str(_("Nothing to save.")))

    for key, value in updates.items():
        setattr(project, key, value)
    project.updated_at = utcnow()
    if old_reference != project.reference:
        sync_cycle_names_for_project(project)
    if "status" in updates:
        sync_project_cycle_closure(project)
    try:
        db.session.commit()
    except Exception as exc:
        request_transaction_rollback()
        current_app.logger.error("Inline project save failed: %s", exc, exc_info=True)
        return json_bad_request(str(_("Could not save the project.")))
    return json_ok(message=str(_("Project saved.")))


def _inline_date(value):
    import datetime as dt

    text = str(value or "").strip()
    if not text:
        return None
    try:
        return dt.date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ValueError("date") from exc


def _inline_money(value):
    from decimal import Decimal, InvalidOperation

    text = str(value or "").strip().replace(",", "").replace(" ", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("money") from exc


@bp.route("/<int:project_id>/edit", methods=["GET", "POST"])
def project_edit(project_id):
    project = Project.query.get_or_404(project_id)
    if not _can_see_project(project):
        abort(403)
    can_edit = _can_manage_projects()
    if request.method == "POST" and not can_edit:
        abort(403)
    form = ProjectForm(obj=project)
    _bind_project_form(form)
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
                    society = _society_for_form(form)
                    upsert_project(
                        reference=project.reference,
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
