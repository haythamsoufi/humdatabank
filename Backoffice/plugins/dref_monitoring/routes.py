"""DREF monitoring pages. Every route is authenticated."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from io import BytesIO

from app.extensions import db
from app.plugins.plugin_utils import PLUGIN_MANAGE_PERMISSION, settings_plugin_info
from app.routes.admin.shared import admin_permission_required_any, permission_required_any
from plugins.dref_monitoring.access import current_actor, operations_for
from plugins.dref_monitoring.config_store import ai_enabled, get_config, save_posted_settings
from plugins.dref_monitoring.constants import (
    ACTIVITY_TYPES,
    CARRIED_OUT_BY,
    ENTER_PERMISSION,
    MANAGE_PERMISSION,
    PLUGIN_ID,
    PORTFOLIO_PERMISSION,
    REVIEW_PERMISSION,
    VALIDATE_PERMISSION,
)
from plugins.dref_monitoring.i18n import current_language, install_dref_gettext, localize_text, translate


def _(message, **variables):
    return translate(message, **variables)


from plugins.dref_monitoring.models import (
    DrefActivity,
    DrefChangeRequest,
    DrefDelay,
    DrefDraft,
    DrefFeedback,
    DrefFundsEvent,
    DrefMember,
    DrefOperation,
    DrefProcurement,
    DrefRisk,
    DrefSyncLog,
)
from plugins.dref_monitoring.services.assignment_sync import assignment_url
from plugins.dref_monitoring.services.drafts import (
    generate_draft,
    narrative_fields,
    report_language,
    save_sections,
    validate_draft,
)
from plugins.dref_monitoring.services.go_submit import submit_draft
from plugins.dref_monitoring.services.llm import complete_with_engine
from plugins.dref_monitoring.services.docx_export import render_docx
from plugins.dref_monitoring.services.pdf_export import PdfUnavailable, render_pdf
from plugins.dref_monitoring.services.report_document import build_report, running_header, source_for
from plugins.dref_monitoring.services.excel_import import import_activities
from plugins.dref_monitoring.services.go_parse import is_imminent
from plugins.dref_monitoring.services.go_sync_job import (
    prepare_settings_sync,
    queue_go_sync,
    request_go_sync_cancel,
    status_payload,
)
from plugins.dref_monitoring.services.plans import (
    decide_change,
    edit_activity,
    generate_plan,
    latest_baseline,
    latest_plan,
    plan_sections,
    realign_plan_activities,
    refresh_indicator_matches,
    remove_member,
    sectors_not_on_plan,
    save_plan_activities,
    set_member,
    update_governance,
    validate_plan,
)
from plugins.dref_monitoring.services.reporting import (
    add_delay,
    add_feedback,
    add_procurement,
    add_risk,
    matrix_for_request,
    monitoring_snapshot,
    periods_for,
    report_for_period,
    reporting_period_badge,
    set_funds,
)

bp = Blueprint(PLUGIN_ID, __name__, template_folder="templates")

_ANY = (
    ENTER_PERMISSION,
    VALIDATE_PERMISSION,
    REVIEW_PERMISSION,
    PORTFOLIO_PERMISSION,
    MANAGE_PERMISSION,
)


@bp.app_template_global("dref_tr")
def dref_tr(message: str) -> str:
    return translate(message)


@bp.app_template_global("dref_language")
def dref_language() -> str:
    return current_language()


@bp.app_template_global("dref_label")
def dref_label(value) -> str:
    return localize_text(value)


@bp.before_app_request
def _install_dref_translations():
    install_dref_gettext()


@bp.app_template_global("dref_cycle_matrix")
def dref_cycle_matrix():
    try:
        return matrix_for_request()
    except Exception:
        db.session.rollback()
        return None


def settings_status() -> dict:
    payload = {
        "operation_count": 0,
        "plan_count": 0,
        "overdue_hint": 0,
        "last_sync": None,
        "last_sync_status": "",
        "ai_enabled": False,
        "ai_language": "en",
        "openai_configured": bool(current_app.config.get("OPENAI_API_KEY")),
        "go_token_configured": bool(current_app.config.get("GO_API_TOKEN")),
        "schedule": {},
        "go_url": "",
    }
    try:
        config = get_config()
        payload["ai_enabled"] = bool((config.get("ai") or {}).get("enabled"))
        payload["ai_language"] = report_language((config.get("ai") or {}).get("language"))
        payload["schedule"] = config.get("schedule") or {}
        payload["go_url"] = (config.get("go") or {}).get("base_url") or ""
        payload["operation_count"] = DrefOperation.query.count()
        from plugins.dref_monitoring.models import DrefPlan

        payload["plan_count"] = DrefPlan.query.count()
        last = DrefSyncLog.query.order_by(DrefSyncLog.id.desc()).first()
        if last is not None:
            payload["last_sync"] = last.finished_at or last.started_at
            payload["last_sync_status"] = last.status
            payload["last_sync_message"] = last.message
    except Exception:
        db.session.rollback()
    return payload


def sync_history() -> list:
    """Recent GO pulls. Kept off ``settings_status`` so the settings API stays small."""
    try:
        return DrefSyncLog.query.order_by(DrefSyncLog.id.desc()).limit(25).all()
    except Exception:
        db.session.rollback()
        return []


def _actor():
    return current_actor()


def _operation(operation_id: int, action: str = "view") -> DrefOperation:
    actor = _actor()
    operation = db.session.get(DrefOperation, operation_id)
    if operation is None or not actor.allows(operation, action):
        abort(404)
    return operation


_OPERATION_TABS = {"overview", "plan", "reporting", "changes", "drafts", "team"}
_SETTINGS_TABS = {"overview", "settings", "sync"}


def _operation_redirect(operation_id: int, *, plan_draft: bool = False):
    tab = (request.values.get("tab") or "").strip()
    kwargs = {"operation_id": operation_id}
    if tab in _OPERATION_TABS:
        kwargs["tab"] = tab
    if plan_draft:
        kwargs["plan_draft"] = 1
    return redirect(url_for(f"{PLUGIN_ID}.operation_page", **kwargs))


def _settings_redirect():
    tab = (request.values.get("tab") or "").strip()
    kwargs = {}
    if tab in _SETTINGS_TABS and tab != "overview":
        kwargs["tab"] = tab
    return redirect(url_for(f"{PLUGIN_ID}.settings_page", **kwargs))


def _flash_error(message: str | None) -> bool:
    if message:
        flash(translate(message), "warning")
        return True
    return False


@bp.route(f"/admin/plugins/{PLUGIN_ID}/settings", methods=["GET", "POST"])
@admin_permission_required_any(PLUGIN_MANAGE_PERMISSION, MANAGE_PERMISSION)
def settings_page():
    if request.method == "POST":
        if request.form.get("action") == "sync":
            _job_id, created = queue_go_sync(int(current_user.id), current_app._get_current_object())
            if created:
                flash(_("Sync from GO is running."), "success")
            else:
                flash(_("A GO sync is already running."), "warning")
        else:
            save_posted_settings(request.form)
            flash(_("Settings saved."), "success")
        return _settings_redirect()
    return render_template(
        f"plugins/{PLUGIN_ID}/settings.html",
        settings=settings_status(),
        plugin_info=settings_plugin_info(PLUGIN_ID),
        operations_url=url_for(f"{PLUGIN_ID}.operations_page"),
        sync_history=sync_history(),
        active_sync=prepare_settings_sync(current_app._get_current_object()),
    )


def _sync_job_or_404(job_id: str):
    from app.models import AIJob
    from plugins.dref_monitoring.services.go_sync_job import JOB_TYPE

    if not job_id or len(job_id) > 36:
        abort(404)
    job = db.session.get(AIJob, job_id)
    if job is None or str(job.job_type) != JOB_TYPE:
        abort(404)
    return job


@bp.route(f"/admin/plugins/{PLUGIN_ID}/sync", methods=["POST"])
@admin_permission_required_any(PLUGIN_MANAGE_PERMISSION, MANAGE_PERMISSION)
def sync_start():
    """Queue a GO sync and return immediately so the page can poll progress."""
    job_id, created = queue_go_sync(int(current_user.id), current_app._get_current_object())
    job = _sync_job_or_404(job_id)
    payload = status_payload(job)
    payload["created"] = created
    return jsonify(payload), 202


@bp.route(f"/admin/plugins/{PLUGIN_ID}/sync/jobs/<job_id>", methods=["GET"])
@admin_permission_required_any(PLUGIN_MANAGE_PERMISSION, MANAGE_PERMISSION)
def sync_status(job_id: str):
    """Status and progress for one GO sync. Resumes the runner if the worker died."""
    from plugins.dref_monitoring.services.go_sync_job import ensure_go_sync_job_running

    job = _sync_job_or_404(job_id)
    ensure_go_sync_job_running(current_app._get_current_object(), str(job.id))
    job = _sync_job_or_404(job_id)
    return jsonify(status_payload(job))


@bp.route(f"/admin/plugins/{PLUGIN_ID}/sync/jobs/<job_id>/cancel", methods=["POST"])
@admin_permission_required_any(PLUGIN_MANAGE_PERMISSION, MANAGE_PERMISSION)
def sync_cancel(job_id: str):
    """Ask a running GO sync to stop. Work already saved in this pull is rolled back."""
    job = _sync_job_or_404(job_id)
    request_go_sync_cancel(str(job.id))
    job = _sync_job_or_404(job_id)
    return jsonify(status_payload(job))


@bp.route("/dref-monitoring/assignment/<int:aes_id>/activities", methods=["GET"])
@login_required
def assignment_activities(aes_id):
    """Activities on the plan for this cycle. The entry form lists them and does not add any."""
    from app.models.assignments import AssignmentEntityStatus
    from app.services.organization.authorization_service import AuthorizationService
    from plugins.dref_monitoring.services.entry_activities import assignment_activity_payload, resolve_cycle

    aes = db.session.get(AssignmentEntityStatus, aes_id)
    if aes is None or not AuthorizationService.can_access_assignment(aes, current_user):
        abort(404)
    operation, period = resolve_cycle(aes)
    if operation is None:
        abort(404)
    return jsonify(assignment_activity_payload(operation, period))


@bp.route("/dref-monitoring/operations", methods=["GET"])
@permission_required_any(*_ANY)
def operations_page():
    actor = _actor()
    include_closed = request.args.get("include_closed") == "1"
    query = operations_for(actor)
    if not include_closed:
        query = query.filter(DrefOperation.operation_status.notin_(("closed", "unspecified")))
    operations = query.order_by(DrefOperation.end_date.desc()).all()
    return render_template(
        f"plugins/{PLUGIN_ID}/operations.html",
        operations=operations,
        include_closed=include_closed,
    )


@bp.route("/dref-monitoring/operations/<int:operation_id>", methods=["GET"])
@permission_required_any(*_ANY)
def operation_page(operation_id: int):
    operation = _operation(operation_id)
    actor = _actor()
    plan = latest_plan(operation.id)
    if plan is not None:
        changed = realign_plan_activities(plan.id)
        changed = refresh_indicator_matches(plan.id) or changed
        if changed:
            db.session.commit()
    sections = plan_sections(plan.id) if plan is not None else []
    periods = []
    for period in periods_for(operation.id):
        href = assignment_url(operation.id, period)
        report = report_for_period(period.id)
        periods.append(
            {
                "period": period,
                "report": report,
                "display_status": reporting_period_badge(period, report),
                "assignment_href": href if href.startswith("/assignment/") else None,
            }
        )
    members = DrefMember.query.filter_by(operation_id=operation.id).order_by(DrefMember.id).all()
    member_users = {}
    system_users = []
    can_review = actor.allows(operation, "review")
    if members or can_review:
        from sqlalchemy import func

        from app.models.core import User

        if members:
            member_users = {
                user.id: user
                for user in User.query.filter(User.id.in_([member.user_id for member in members])).all()
            }
        if can_review:
            system_users = (
                User.query.filter(User.active.is_(True))
                .order_by(func.lower(func.coalesce(User.name, User.email)))
                .all()
            )
    return render_template(
        f"plugins/{PLUGIN_ID}/operation.html",
        operation=operation,
        actor_can_enter=actor.allows(operation, "enter"),
        actor_can_validate=actor.allows(operation, "validate"),
        actor_can_review=actor.allows(operation, "review"),
        actor_can_portfolio=actor.allows(operation, "portfolio") or actor.is_manager,
        plan=plan,
        baseline=latest_baseline(operation.id),
        sections=sections,
        snapshot=monitoring_snapshot(operation),
        activity_types=ACTIVITY_TYPES,
        carried_out_by=CARRIED_OUT_BY,
        available_sectors=sectors_not_on_plan(plan.id) if plan is not None else [],
        plan_imminent=is_imminent(operation.appeal_type, operation.pillar),
        changes=DrefChangeRequest.query.filter_by(operation_id=operation.id).order_by(DrefChangeRequest.id.desc()).limit(30).all(),
        periods=periods,
        procurement=DrefProcurement.query.filter_by(operation_id=operation.id).order_by(DrefProcurement.id).all(),
        delays=DrefDelay.query.filter_by(operation_id=operation.id).order_by(DrefDelay.id.desc()).limit(20).all(),
        members=members,
        member_users=member_users,
        system_users=system_users,
        feedback=DrefFeedback.query.filter_by(operation_id=operation.id).order_by(DrefFeedback.id.desc()).limit(20).all(),
        risks=DrefRisk.query.filter_by(operation_id=operation.id).all(),
        funds=DrefFundsEvent.query.filter_by(operation_id=operation.id).order_by(DrefFundsEvent.id.desc()).limit(5).all(),
        drafts=DrefDraft.query.filter_by(operation_id=operation.id).order_by(DrefDraft.id.desc()).limit(10).all(),
        active_tab=request.args.get("tab") if request.args.get("tab") in _OPERATION_TABS else "overview",
    )


@bp.route("/dref-monitoring/operations/<int:operation_id>/plan/generate", methods=["POST"])
@permission_required_any(*_ANY)
def generate_plan_route(operation_id: int):
    operation = _operation(operation_id, "enter")
    baseline = latest_baseline(operation.id)
    if baseline is None:
        flash(_("There is no approved GO baseline to build a plan from."), "warning")
    else:
        generate_plan(operation, baseline, date.today())
        db.session.commit()
        flash(_("A draft monitoring plan was created."), "success")
    return _operation_redirect(operation.id)


@bp.route("/dref-monitoring/operations/<int:operation_id>/plan/validate", methods=["POST"])
@permission_required_any(*_ANY)
def validate_plan_route(operation_id: int):
    operation = _operation(operation_id, "validate")
    _flash_error(validate_plan(operation, _actor(), date.today())) or flash(_("Plan validated."), "success")
    return _operation_redirect(operation.id)


def _figure(value) -> str:
    if value is None or value == "":
        return ""
    try:
        number = Decimal(str(value))
    except Exception:
        return str(value)
    if number == number.to_integral():
        return f"{int(number):,}"
    return f"{number:,.2f}"


def _sign_off_message(held) -> str:
    """Name the activity, the figure, and the ceiling that blocked it."""
    details = []
    for item in held:
        title = item.get("title") or _("an activity")
        field = item.get("field")
        value = _figure(item.get("value"))
        limit = item.get("limit") or ""
        if field == "budget_chf":
            details.append(
                _(
                    "%(title)s: the budget of %(value)s CHF is above the approved sector budget of %(limit)s CHF",
                    title=title,
                    value=value,
                    limit=_figure(limit),
                )
            )
        elif field == "target":
            details.append(
                _(
                    "%(title)s: the people target of %(value)s is above the approved %(limit)s",
                    title=title,
                    value=value,
                    limit=_figure(limit),
                )
            )
        elif field == "start_date":
            details.append(
                _(
                    "%(title)s: the start date %(value)s is outside the approved operation (%(limit)s)",
                    title=title,
                    value=value,
                    limit=limit,
                )
            )
        elif field == "end_date":
            details.append(
                _(
                    "%(title)s: the end date %(value)s is outside the approved operation (%(limit)s)",
                    title=title,
                    value=value,
                    limit=limit,
                )
            )
        else:
            details.append(_("%(title)s: this value is outside the approved operation", title=title))
    if not details:
        return _("Part of this edit is outside the approved operation and is waiting for sign-off. Everything else was saved.")
    return _(
        "Waiting for sign-off. %(details)s. Everything else was saved.",
        details=" ".join(details),
    )


@bp.route("/dref-monitoring/operations/<int:operation_id>/activities/<int:activity_id>", methods=["POST"])
@permission_required_any(*_ANY)
def edit_activity_route(operation_id: int, activity_id: int):
    operation = _operation(operation_id, "enter")
    activity = db.session.get(DrefActivity, activity_id)
    if activity is None:
        abort(404)
    result = edit_activity(operation, activity, request.form, _actor())
    if not result.get("ok"):
        flash(translate(result.get("error") or "The activity could not be saved."), "warning")
    elif result.get("pending"):
        flash(_sign_off_message(result.get("held") or []), "warning")
    else:
        flash(_("Activity saved."), "success")
    return _operation_redirect(operation.id)


@bp.route("/dref-monitoring/operations/<int:operation_id>/plan", methods=["POST"])
@permission_required_any(*_ANY)
def save_plan_route(operation_id: int):
    operation = _operation(operation_id, "enter")
    result = save_plan_activities(operation, request.form, _actor())
    if not result.get("ok"):
        flash(translate(result.get("error") or "The activity could not be saved."), "warning")
        return _operation_redirect(operation.id, plan_draft=True)
    else:
        for error in result.get("errors") or []:
            flash(translate(error), "warning")
        if result.get("pending"):
            flash(_sign_off_message(result.get("held") or []), "warning")
        elif not result.get("errors"):
            flash(_("Plan saved."), "success")
    return _operation_redirect(operation.id)


@bp.route("/dref-monitoring/operations/<int:operation_id>/changes/<int:change_id>", methods=["POST"])
@permission_required_any(*_ANY)
def decide_change_route(operation_id: int, change_id: int):
    operation = _operation(operation_id)
    change = db.session.get(DrefChangeRequest, change_id)
    if change is None or change.operation_id != operation.id:
        abort(404)
    approve = request.form.get("decision") == "approve"
    _flash_error(decide_change(change, operation, _actor(), approve)) or flash(_("Change request updated."), "success")
    return _operation_redirect(operation.id)


@bp.route("/dref-monitoring/operations/<int:operation_id>/governance", methods=["POST"])
@permission_required_any(*_ANY)
def governance_route(operation_id: int):
    operation = _operation(operation_id)
    _flash_error(update_governance(operation, request.form.get("sign_off", ""), request.form.get("frequency", ""), _actor())) or flash(
        _("Governance updated."), "success"
    )
    return _operation_redirect(operation.id)


@bp.route("/dref-monitoring/operations/<int:operation_id>/members", methods=["POST"])
@permission_required_any(*_ANY)
def member_route(operation_id: int):
    operation = _operation(operation_id)
    try:
        user_id = int(request.form.get("user_id") or 0)
    except ValueError:
        user_id = 0
    _flash_error(set_member(operation, user_id, request.form.get("tier", ""), _actor())) or flash(_("Member saved."), "success")
    return _operation_redirect(operation.id)


@bp.route("/dref-monitoring/operations/<int:operation_id>/members/<int:member_id>/remove", methods=["POST"])
@permission_required_any(*_ANY)
def member_remove_route(operation_id: int, member_id: int):
    operation = _operation(operation_id)
    _flash_error(remove_member(operation, member_id, _actor())) or flash(_("Member removed."), "success")
    return _operation_redirect(operation.id)


@bp.route("/dref-monitoring/operations/<int:operation_id>/import", methods=["POST"])
@permission_required_any(*_ANY)
def excel_route(operation_id: int):
    operation = _operation(operation_id, "enter")
    upload = request.files.get("workbook")
    if upload is None or not upload.filename:
        flash(_("Choose an Excel workbook."), "warning")
    elif not upload.filename.lower().endswith(".xlsx"):
        flash(_("Use an .xlsx workbook with an Activities sheet."), "warning")
    else:
        raw = upload.read(5 * 1024 * 1024 + 1)
        if len(raw) > 5 * 1024 * 1024:
            flash(_("The workbook is larger than 5 MB."), "warning")
        else:
            result = import_activities(operation, raw, _actor(), date.today())
            if not result.get("ok"):
                flash(translate(result.get("error") or "Import failed."), "warning")
            else:
                flash(_("Imported %(count)s activity rows.", count=result["rows"]), "success")
    return _operation_redirect(operation.id)


@bp.route("/dref-monitoring/operations/<int:operation_id>/funds", methods=["POST"])
@permission_required_any(*_ANY)
def funds_route(operation_id: int):
    operation = _operation(operation_id, "enter")
    _flash_error(set_funds(operation, request.form, _actor())) or flash(_("Funds status saved."), "success")
    return _operation_redirect(operation.id)


@bp.route("/dref-monitoring/operations/<int:operation_id>/procurement", methods=["POST"])
@permission_required_any(*_ANY)
def procurement_route(operation_id: int):
    operation = _operation(operation_id, "enter")
    _flash_error(add_procurement(operation, request.form, _actor())) or flash(_("Procurement updated."), "success")
    return _operation_redirect(operation.id)


@bp.route("/dref-monitoring/operations/<int:operation_id>/delays", methods=["POST"])
@permission_required_any(*_ANY)
def delay_route(operation_id: int):
    operation = _operation(operation_id, "enter")
    _flash_error(add_delay(operation, request.form, _actor())) or flash(_("Delay recorded."), "success")
    return _operation_redirect(operation.id)


@bp.route("/dref-monitoring/operations/<int:operation_id>/feedback", methods=["POST"])
@permission_required_any(*_ANY)
def feedback_route(operation_id: int):
    operation = _operation(operation_id, "enter")
    _flash_error(add_feedback(operation, request.form, _actor())) or flash(_("Feedback recorded."), "success")
    return _operation_redirect(operation.id)


@bp.route("/dref-monitoring/operations/<int:operation_id>/risks", methods=["POST"])
@permission_required_any(*_ANY)
def risk_route(operation_id: int):
    operation = _operation(operation_id, "enter")
    _flash_error(add_risk(operation, request.form, _actor())) or flash(_("Risk saved."), "success")
    return _operation_redirect(operation.id)


@bp.route("/dref-monitoring/operations/<int:operation_id>/drafts", methods=["POST"])
@permission_required_any(*_ANY)
def draft_generate_route(operation_id: int):
    operation = _operation(operation_id, "enter")
    kind = request.form.get("kind") or "operational_update"
    language = report_language(request.form.get("language") or current_language())
    model_name = str(current_app.config.get("OPENAI_MODEL") or "")
    complete = complete_with_engine if ai_enabled() else None
    result = generate_draft(
        operation,
        kind,
        _actor(),
        complete=complete,
        model_name=model_name,
        language=language,
    )
    if not result.get("ok"):
        flash(translate(result.get("error") or "Draft failed."), "warning")
        return _operation_redirect(operation.id)
    return redirect(url_for(f"{PLUGIN_ID}.draft_page", operation_id=operation.id, draft_id=result["draft_id"]))


@bp.route("/dref-monitoring/operations/<int:operation_id>/drafts/<int:draft_id>", methods=["GET"])
@permission_required_any(*_ANY)
def draft_page(operation_id: int, draft_id: int):
    operation = _operation(operation_id, "enter")
    actor = _actor()
    draft, blocks, header = _draft_blocks(operation, draft_id)
    status = draft.status or "draft"
    return render_template(
        f"plugins/{PLUGIN_ID}/draft.html",
        operation=operation,
        draft=draft,
        blocks=blocks,
        header=header,
        fields=narrative_fields(draft),
        can_edit=actor.allows(operation, "enter") and status == "draft",
        can_validate=actor.allows(operation, "validate") and status == "draft",
        can_send=actor.allows(operation, "validate") and status == "validated" and draft.go_status != "sent",
    )


@bp.route("/dref-monitoring/operations/<int:operation_id>/drafts/<int:draft_id>", methods=["POST"])
@permission_required_any(*_ANY)
def draft_save_route(operation_id: int, draft_id: int):
    operation = _operation(operation_id, "enter")
    draft = _draft_row(operation, draft_id)
    error = save_sections(draft, operation, request.form, _actor())
    flash(translate(error or "Narrative saved."), "warning" if error else "success")
    return redirect(url_for(f"{PLUGIN_ID}.draft_page", operation_id=operation.id, draft_id=draft.id))


@bp.route("/dref-monitoring/operations/<int:operation_id>/drafts/<int:draft_id>/validate", methods=["POST"])
@permission_required_any(*_ANY)
def draft_validate_route(operation_id: int, draft_id: int):
    operation = _operation(operation_id, "validate")
    draft = _draft_row(operation, draft_id)
    error = validate_draft(draft, operation, _actor())
    if error:
        flash(translate(error), "warning")
        return redirect(url_for(f"{PLUGIN_ID}.draft_page", operation_id=operation.id, draft_id=draft.id))
    result = submit_draft(operation, draft)
    if result.get("ok"):
        flash(translate("Report sent to GO."), "success")
    else:
        flash(translate(result.get("error") or "GO did not accept the report."), "warning")
    return redirect(url_for(f"{PLUGIN_ID}.draft_page", operation_id=operation.id, draft_id=draft.id))


@bp.route("/dref-monitoring/operations/<int:operation_id>/drafts/<int:draft_id>/send", methods=["POST"])
@permission_required_any(*_ANY)
def draft_send_route(operation_id: int, draft_id: int):
    operation = _operation(operation_id, "validate")
    draft = _draft_row(operation, draft_id)
    result = submit_draft(operation, draft)
    if result.get("ok"):
        flash(translate("Report sent to GO."), "success")
    else:
        flash(translate(result.get("error") or "GO did not accept the report."), "warning")
    return redirect(url_for(f"{PLUGIN_ID}.draft_page", operation_id=operation.id, draft_id=draft.id))


def _draft_row(operation, draft_id: int):
    draft = db.session.get(DrefDraft, draft_id)
    if draft is None or draft.operation_id != operation.id:
        abort(404)
    return draft


def _draft_blocks(operation, draft_id: int):
    draft = _draft_row(operation, draft_id)
    source = source_for(operation, draft)
    return draft, build_report(source), running_header(source)


@bp.route("/dref-monitoring/operations/<int:operation_id>/drafts/<int:draft_id>/export.docx", methods=["GET"])
@permission_required_any(*_ANY)
def draft_docx_route(operation_id: int, draft_id: int):
    operation = _operation(operation_id, "enter")
    draft, blocks, header = _draft_blocks(operation, draft_id)
    payload = render_docx(blocks, header, language=draft.language or "en")
    return send_file(
        BytesIO(payload),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=f"{operation.appeal_code}-{draft.report_kind}.docx",
    )


@bp.route("/dref-monitoring/operations/<int:operation_id>/drafts/<int:draft_id>/export.pdf", methods=["GET"])
@permission_required_any(*_ANY)
def draft_pdf_route(operation_id: int, draft_id: int):
    operation = _operation(operation_id, "enter")
    draft, blocks, header = _draft_blocks(operation, draft_id)
    try:
        payload = render_pdf(blocks, header, language=draft.language or "en")
    except PdfUnavailable:
        abort(503)
    return send_file(
        BytesIO(payload),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{operation.appeal_code}-{draft.report_kind}.pdf",
    )
