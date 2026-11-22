"""DREF monitoring pages. Every route is authenticated."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from io import BytesIO

from app.extensions import db
from app.models import AIJob
from app.plugins.plugin_utils import PLUGIN_MANAGE_PERMISSION, settings_plugin_info
from app.routes.admin.shared import admin_permission_required_any, permission_required_any
from plugins.dref_monitoring.access import current_actor, operations_for
from plugins.dref_monitoring.config_store import ai_enabled, get_config, save_posted_settings
from plugins.dref_monitoring.constants import (
    ACTIVITY_TYPES,
    CARRIED_OUT_BY,
    ENTER_PERMISSION,
    MANAGE_PERMISSION,
    NARRATIVE_AI,
    NARRATIVE_NONE,
    PLAN_VALIDATED,
    PLUGIN_ID,
    PORTFOLIO_PERMISSION,
    REVIEW_PERMISSION,
    VALIDATE_PERMISSION,
)
from plugins.dref_monitoring.i18n import current_language, install_dref_gettext, localize_text, translate
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
    chapter_keys_for,
    delete_draft,
    draft_deletable,
    generate_draft,
    include_narrative,
    narrative_fields,
    narrative_mode_of,
    report_language,
    reset_section,
    save_chapters,
    save_sections,
    validate_draft,
)
from plugins.dref_monitoring.services.sources import narrative_sources, sources_state
from plugins.dref_monitoring.services.draft_job import (
    ACTION_GENERATE,
    ACTION_INCLUDE,
    ACTION_SECTION,
    JOB_TYPE as DRAFT_JOB_TYPE,
    active_draft_job,
    active_draft_jobs,
    ensure_draft_job_running,
    queue_draft_job,
    request_draft_cancel,
    status_payload as draft_status_payload,
)
from plugins.dref_monitoring.services.go_submit import submit_draft
from plugins.dref_monitoring.services.context import load_context
from plugins.dref_monitoring.services.llm import complete_with_engine, configured_model
from plugins.dref_monitoring.services import narrative_format as fmt
from plugins.dref_monitoring.services.docx_export import render_docx
from plugins.dref_monitoring.services.docx_import import DocxImportError, analyze_docx, expected_reference
from plugins.dref_monitoring.services.pdf_export import PdfUnavailable, render_pdf
from plugins.dref_monitoring.services.report_document import (
    blocks_for_export,
    build_report,
    running_header,
    source_for,
)
from plugins.dref_monitoring.services.excel_import import export_workbook, import_activities
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
    go_source_notices,
    latest_baseline,
    latest_plan,
    plan_matches_sync,
    plan_sections,
    plan_source_label,
    plans_for,
    realign_plan_activities,
    refresh_indicator_matches,
    remove_member,
    reset_plan_from_sync,
    restore_plan_version,
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

def _(message, **variables):
    return translate(message, **variables)


bp = Blueprint(PLUGIN_ID, __name__, template_folder="templates")


@bp.before_request
def _ensure_dref_access_group():
    """Create the DREF access group and apply it to reporting assignments already opened."""
    try:
        from plugins.dref_monitoring.services.access_group import ensure_dref_assignment_access

        ensure_dref_assignment_access()
    except Exception:
        current_app.logger.warning("DREF access group setup failed", exc_info=True)
        from plugins.dref_monitoring.services import access_group as access_group_module

        access_group_module._backfilled_for = None
        db.session.rollback()

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


@bp.app_template_global("dref_nodes")
def dref_nodes(text):
    """A stored chapter as paragraphs and lists, so a template draws it without trusting its markup."""
    return fmt.parse(text)


@bp.app_template_global("dref_chapter_outline")
def dref_chapter_outline() -> dict:
    """The chapters of each report type with their labels, for the page that shows drafting progress."""
    from plugins.dref_monitoring.constants import SECTION_LABELS
    from plugins.dref_monitoring.services.prompts import chapter_keys

    return {
        kind: [{"key": key, "label": translate(SECTION_LABELS[key])} for key in chapter_keys(kind)]
        for kind in ("operational_update", "final_report")
    }


@bp.before_app_request
def _install_dref_translations():
    install_dref_gettext()


@bp.app_template_global("dref_cycle_matrix")
def dref_cycle_matrix():
    # A savepoint keeps a failure here from rolling back the rest of the request.
    try:
        with db.session.begin_nested():
            return matrix_for_request()
    except Exception:
        current_app.logger.warning("DREF cycle matrix could not be built", exc_info=True)
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
        "ai_model": "",
        "ai_final_report_model": "",
        "openai_configured": bool(current_app.config.get("OPENAI_API_KEY")),
        "go_token_configured": bool(current_app.config.get("GO_API_TOKEN")),
        "schedule": {},
        "go_url": "",
    }
    try:
        config = get_config()
        payload["ai_enabled"] = bool((config.get("ai") or {}).get("enabled"))
        payload["ai_language"] = report_language((config.get("ai") or {}).get("language"))
        payload["ai_model"] = str((config.get("ai") or {}).get("model") or "")
        payload["ai_final_report_model"] = str((config.get("ai") or {}).get("final_report_model") or "")
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


def _day(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "date") and not isinstance(value, date):
        return value.date().isoformat()
    return value.isoformat()


def _plan_version_rows(operation: DrefOperation, baseline, current_id: int | None) -> list[dict]:
    plans = plans_for(operation.id)
    user_ids = [plan.validated_by_user_id for plan in plans if plan.validated_by_user_id]
    users = {}
    if user_ids:
        from app.models.core import User

        users = {user.id: user for user in User.query.filter(User.id.in_(user_ids)).all()}
    rows = []
    for plan in plans:
        person = users.get(plan.validated_by_user_id)
        rows.append(
            {
                "version": plan.version,
                "status": plan.status,
                "source_label": plan_source_label(plan.source),
                "current": plan.id == current_id,
                "matches_go": plan_matches_sync(plan, operation, baseline),
                "opened_on": _day(plan.created_at),
                "confirmed_on": _day(plan.validated_at),
                "confirmed_by": (person.name or person.email) if person is not None else "",
            }
        )
    return rows


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
    # Tidying older plans writes rows, so only someone who can edit the plan triggers it.
    if plan is not None and actor.allows(operation, "enter"):
        try:
            changed = realign_plan_activities(plan.id)
            changed = refresh_indicator_matches(plan.id) or changed
            if changed:
                db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.warning("DREF plan tidy-up failed for operation %s", operation.id, exc_info=True)
            plan = latest_plan(operation.id)
    view_plan = plan
    plan_history = False
    requested_version = request.args.get("plan_version", type=int)
    if requested_version and (plan is None or requested_version != plan.version):
        chosen = next((item for item in plans_for(operation.id) if item.version == requested_version), None)
        if chosen is None:
            flash(_("That plan version was not found."), "warning")
        else:
            view_plan = chosen
            plan_history = True
    current_sections = plan_sections(plan.id) if plan is not None else []
    sections = current_sections if view_plan is plan else plan_sections(view_plan.id)
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
        from plugins.dref_monitoring.access import capable_users_query

        if members:
            member_users = {
                user.id: user
                for user in User.query.filter(User.id.in_([member.user_id for member in members])).all()
            }
        if can_review:
            # Only people who hold a DREF role can act on an operation, so only they are offered.
            system_users = (
                capable_users_query()
                .order_by(func.lower(func.coalesce(User.name, User.email)))
                .all()
            )
    can_enter = actor.allows(operation, "enter")
    can_validate = actor.allows(operation, "validate")
    baseline = latest_baseline(operation.id)
    plan_versions = _plan_version_rows(operation, baseline, None if plan is None else plan.id)
    current_plan_matches_go = any(row["current"] and row["matches_go"] for row in plan_versions)
    can_reset_plan = baseline is not None and plan is not None and (
        can_validate if plan.status == PLAN_VALIDATED else can_enter
    )
    drafts = DrefDraft.query.filter_by(operation_id=operation.id).order_by(DrefDraft.id.desc()).limit(10).all()
    return render_template(
        f"plugins/{PLUGIN_ID}/operation.html",
        operation=operation,
        active_job=draft_job_for_page(operation.id, ACTION_GENERATE) if can_enter else None,
        actor_can_enter=can_enter,
        can_enter=can_enter,
        actor_can_validate=can_validate,
        actor_can_review=actor.allows(operation, "review"),
        actor_can_portfolio=actor.allows(operation, "portfolio") or actor.is_manager,
        plan=view_plan,
        current_plan=plan,
        plan_history=plan_history,
        plan_editable=can_enter and not plan_history,
        plan_versions=plan_versions,
        current_plan_matches_go=current_plan_matches_go,
        can_reset_plan=can_reset_plan,
        baseline=baseline,
        go_source_notices=go_source_notices(baseline),
        sections=sections,
        snapshot=monitoring_snapshot(operation, plan, current_sections),
        activity_types=ACTIVITY_TYPES,
        carried_out_by=CARRIED_OUT_BY,
        available_sectors=sectors_not_on_plan(view_plan.id) if view_plan is not None else [],
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
        drafts=drafts,
        deletable_draft_ids={row.id for row in drafts if draft_deletable(row, operation, actor)},
        ai_ready=ai_enabled(),
        active_tab=request.args.get("tab") if request.args.get("tab") in _OPERATION_TABS else "overview",
    )


@bp.route("/dref-monitoring/operations/<int:operation_id>/plan/validate", methods=["POST"])
@permission_required_any(*_ANY)
def validate_plan_route(operation_id: int):
    operation = _operation(operation_id, "validate")
    _flash_error(validate_plan(operation, _actor(), date.today())) or flash(_("Plan validated."), "success")
    return _operation_redirect(operation.id)


@bp.route("/dref-monitoring/operations/<int:operation_id>/plan/restore", methods=["POST"])
@permission_required_any(*_ANY)
def restore_plan_route(operation_id: int):
    """Copy a stored plan version into a new draft. The stored version stays."""
    operation = _operation(operation_id, "enter")
    raw = str(request.form.get("version") or "").strip()
    version = int(raw) if raw.isdigit() else 0
    error = restore_plan_version(operation, version, _actor(), date.today())
    if _flash_error(error):
        db.session.rollback()
    else:
        db.session.commit()
        flash(_("Version %(version)s was copied into a new draft.", version=version), "success")
    return _operation_redirect(operation.id)


@bp.route("/dref-monitoring/operations/<int:operation_id>/plan/reset", methods=["POST"])
@permission_required_any(*_ANY)
def reset_plan_route(operation_id: int):
    """Leave the confirmed plan in the version list and open a draft from the GO sync."""
    operation = _operation(operation_id, "enter")
    error = reset_plan_from_sync(operation, _actor(), date.today())
    if _flash_error(error):
        db.session.rollback()
    else:
        db.session.commit()
        flash(
            _("The previous plan was kept. A new draft was built from the latest approved GO stage."),
            "success",
        )
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


@bp.route("/dref-monitoring/operations/<int:operation_id>/export", methods=["GET"])
@permission_required_any(*_ANY)
def export_plan_route(operation_id: int):
    """Download the plan as the Activities workbook an import reads back."""
    operation = _operation(operation_id)
    requested = request.args.get("plan_version", type=int)
    plan = latest_plan(operation.id)
    if requested and (plan is None or requested != plan.version):
        plan = next((item for item in plans_for(operation.id) if item.version == requested), None)
    if plan is None:
        flash(_("There is no monitoring plan to export."), "warning")
        return _operation_redirect(operation.id)
    appeal = re.sub(r"[^A-Za-z0-9._-]+", "-", operation.appeal_code or "plan").strip("-") or "plan"
    return send_file(
        BytesIO(export_workbook(plan)),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"{appeal}-monitoring-plan-v{plan.version}.xlsx",
    )


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


_ASSIGNMENT_PATH = re.compile(r"^/assignment/\d+$")


def _assignment_return(value: str | None) -> str | None:
    """A form page to return to after a failed draft. Only a plain /assignment/<id> path is followed."""
    text = (value or "").strip()
    return text if _ASSIGNMENT_PATH.match(text) else None


@bp.route("/dref-monitoring/operations/<int:operation_id>/drafts", methods=["POST"])
@permission_required_any(*_ANY)
def draft_generate_route(operation_id: int):
    operation = _operation(operation_id, "enter")
    kind = request.form.get("kind") or "operational_update"
    language = report_language(request.form.get("language") or current_language())
    narrative = (request.form.get("narrative") or "").strip() or None
    model_name = configured_model(kind)
    complete = complete_with_engine if ai_enabled() else None
    if _wants_json() and complete is not None and narrative in (None, NARRATIVE_AI):
        return _queue_draft_response(
            operation,
            {
                "action": ACTION_GENERATE,
                "operation_id": operation.id,
                "kind": kind,
                "language": language,
                "narrative": narrative or "",
            },
        )
    result = generate_draft(
        operation,
        kind,
        _actor(),
        complete=complete,
        model_name=model_name,
        language=language,
        narrative=narrative,
        context_loader=load_context if complete is not None else None,
    )
    draft_url = (
        url_for(f"{PLUGIN_ID}.draft_page", operation_id=operation.id, draft_id=result["draft_id"])
        if result.get("ok")
        else ""
    )
    if _wants_json():
        if not result.get("ok"):
            return jsonify({"error": translate(result.get("error") or "Draft failed.")}), 400
        return jsonify({"status": "completed", "redirect_url": draft_url, "summary": {"ai_used": bool(result.get("ai_used"))}})
    if not result.get("ok"):
        flash(translate(result.get("error") or "Draft failed."), "warning")
        return_to = _assignment_return(request.form.get("return_to"))
        return redirect(return_to) if return_to else _operation_redirect(operation.id)
    if narrative == NARRATIVE_AI and not result.get("ai_used"):
        flash(translate("The model did not return text. The chapters are empty, so you can write them here."), "warning")
    return redirect(draft_url)


@bp.route("/dref-monitoring/operations/<int:operation_id>/drafts/<int:draft_id>/narrative", methods=["POST"])
@permission_required_any(*_ANY)
def draft_include_narrative_route(operation_id: int, draft_id: int):
    operation = _operation(operation_id, "enter")
    draft = _draft_row(operation, draft_id)
    narrative = (request.form.get("narrative") or "").strip()
    complete = complete_with_engine if ai_enabled() and narrative == NARRATIVE_AI else None
    draft_url = url_for(f"{PLUGIN_ID}.draft_page", operation_id=operation.id, draft_id=draft.id)
    if _wants_json() and complete is not None:
        return _queue_draft_response(
            operation,
            {
                "action": ACTION_INCLUDE,
                "operation_id": operation.id,
                "kind": draft.report_kind,
                "draft_id": draft.id,
                "narrative": narrative,
            },
        )
    result = include_narrative(
        draft,
        operation,
        _actor(),
        narrative,
        complete=complete,
        model_name=configured_model(draft.report_kind) if complete is not None else "",
        context_loader=load_context if complete is not None else None,
    )
    if _wants_json():
        if not result.get("ok"):
            return jsonify({"error": translate(result.get("error") or "Draft failed.")}), 400
        return jsonify({"status": "completed", "redirect_url": draft_url, "summary": {"ai_used": bool(result.get("ai_used"))}})
    if not result.get("ok"):
        flash(translate(result.get("error") or "Draft failed."), "warning")
    elif narrative == NARRATIVE_AI and not result.get("ai_used"):
        flash(translate("The model did not return text. The chapters are empty, so you can write them here."), "warning")
    return redirect(draft_url)


def _wants_json() -> bool:
    """True for the page script, which sends ``Accept: application/json`` and shows progress itself."""
    return request.accept_mimetypes.best == "application/json"


def _queue_draft_response(operation, params: dict):
    """Queue an AI draft for this person and answer with the job, or the one already running."""
    job_id, created = queue_draft_job(int(_actor().user_id), params, current_app._get_current_object())
    job = db.session.get(AIJob, job_id)
    body = draft_status_payload(job) if job is not None else {"job_id": job_id, "status": "queued"}
    body["created"] = created
    return jsonify(body), 202


def draft_job_for_page(operation_id: int, action: str, draft_id: int | None = None) -> dict | None:
    """This person's unfinished draft job of one kind on the operation, so a reloaded page shows it again."""
    actor = _actor()
    if actor.user_id is None:
        return None
    match = {"user_id": int(actor.user_id), "operation_id": operation_id, "action": action, "draft_id": draft_id}
    job = active_draft_job(**match)
    if job is None:
        return None
    ensure_draft_job_running(current_app._get_current_object(), str(job.id))
    job = active_draft_job(**match)
    if job is None:
        return None
    return draft_status_payload(job)


def _draft_job_or_404(operation_id: int, job_id: str):
    operation = _operation(operation_id, "enter")
    if not job_id or len(job_id) > 36:
        abort(404)
    job = db.session.get(AIJob, job_id)
    meta = dict(job.meta or {}) if job is not None else {}
    if (
        job is None
        or str(job.job_type) != DRAFT_JOB_TYPE
        or meta.get("operation_id") != operation.id
        or job.user_id != _actor().user_id
    ):
        abort(404)
    return operation, job


@bp.route("/dref-monitoring/operations/<int:operation_id>/drafts/jobs/<job_id>", methods=["GET"])
@permission_required_any(*_ANY)
def draft_job_status(operation_id: int, job_id: str):
    operation, job = _draft_job_or_404(operation_id, job_id)
    ensure_draft_job_running(current_app._get_current_object(), str(job.id))
    db.session.expire_all()
    job = db.session.get(AIJob, str(job.id))
    body = draft_status_payload(job)
    draft_id = (body.get("summary") or {}).get("draft_id")
    if body["status"] == "completed" and draft_id:
        body["redirect_url"] = url_for(f"{PLUGIN_ID}.draft_page", operation_id=operation.id, draft_id=draft_id)
    return jsonify(body)


@bp.route("/dref-monitoring/operations/<int:operation_id>/drafts/jobs/<job_id>/cancel", methods=["POST"])
@permission_required_any(*_ANY)
def draft_job_cancel(operation_id: int, job_id: str):
    _, job = _draft_job_or_404(operation_id, job_id)
    outcome = request_draft_cancel(str(job.id))
    db.session.expire_all()
    job = db.session.get(AIJob, str(job.id))
    body = draft_status_payload(job)
    body["outcome"] = outcome
    return jsonify(body), 202 if outcome == "cancel_requested" else 200


@bp.route("/dref-monitoring/operations/<int:operation_id>/drafts/<int:draft_id>", methods=["GET"])
@permission_required_any(*_ANY)
def draft_page(operation_id: int, draft_id: int):
    operation = _operation(operation_id, "enter")
    actor = _actor()
    draft, blocks, header = _draft_blocks(operation, draft_id)
    status = draft.status or "draft"
    can_edit = actor.allows(operation, "enter") and status == "draft" and narrative_mode_of(draft) != NARRATIVE_NONE
    fields = narrative_fields(draft, blocks)
    source_rows = narrative_sources(draft)
    return render_template(
        f"plugins/{PLUGIN_ID}/draft.html",
        operation=operation,
        draft=draft,
        blocks=blocks,
        header=header,
        fields=fields,
        fields_by_key={field["key"]: field for field in fields},
        source_rows=source_rows,
        sources_state=sources_state(draft),
        narrative_mode=narrative_mode_of(draft),
        can_edit=can_edit,
        can_add_narrative=actor.allows(operation, "enter") and status == "draft" and narrative_mode_of(draft) == NARRATIVE_NONE,
        ai_ready=ai_enabled(),
        chapter_limit=fmt.CHAPTER_LIMIT,
        section_jobs=_section_jobs_for_page(operation, draft) if can_edit else [],
        active_job=draft_job_for_page(operation.id, ACTION_INCLUDE, draft.id)
        if actor.allows(operation, "enter") and status == "draft"
        else None,
        can_validate=actor.allows(operation, "validate") and status == "draft",
        can_send=actor.allows(operation, "validate") and status == "validated" and draft.go_status != "sent",
        can_delete=draft_deletable(draft, operation, actor),
    )


@bp.route("/dref-monitoring/operations/<int:operation_id>/drafts/<int:draft_id>", methods=["POST"])
@permission_required_any(*_ANY)
def draft_save_route(operation_id: int, draft_id: int):
    operation = _operation(operation_id, "enter")
    draft = _draft_row(operation, draft_id)
    error = save_sections(draft, operation, request.form, _actor())
    flash(translate(error or "Narrative saved."), "warning" if error else "success")
    return redirect(url_for(f"{PLUGIN_ID}.draft_page", operation_id=operation.id, draft_id=draft.id))


def _section_jobs_for_page(operation, draft) -> list[dict]:
    """Chapter rewrites this person started on the draft that have not finished, so a reload shows them."""
    actor = _actor()
    if actor.user_id is None:
        return []
    rows = []
    for job in active_draft_jobs(
        user_id=int(actor.user_id), operation_id=operation.id, action=ACTION_SECTION, draft_id=draft.id
    ):
        ensure_draft_job_running(current_app._get_current_object(), str(job.id))
        rows.append(draft_status_payload(job))
    return rows


def _json_error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": translate(message)}), status


def _chapter_state(key: str, html: str) -> dict:
    return {"key": key, "html": html, "words": fmt.word_count(html), "chars": fmt.plain_length(html)}


@bp.route("/dref-monitoring/operations/<int:operation_id>/drafts/<int:draft_id>/chapters", methods=["POST"])
@permission_required_any(*_ANY)
def draft_chapters_route(operation_id: int, draft_id: int):
    """Save one or more chapters from the page. The body is ``{"sections": {"needs": "<p>…</p>"}}``."""
    operation = _operation(operation_id, "enter")
    draft = _draft_row(operation, draft_id)
    body = request.get_json(silent=True) or {}
    sections = body.get("sections")
    if not isinstance(sections, dict) or not sections or len(sections) > 20:
        return _json_error("Nothing to save.")
    sources = body.get("sources")
    error, saved, failed = save_chapters(
        draft, operation, sections, _actor(), sources if isinstance(sources, dict) else None
    )
    if error:
        return _json_error(error, 403 if "cannot" in error else 400)
    return jsonify(
        {
            "ok": not failed,
            "saved": {key: _chapter_state(key, html) for key, html in saved.items()},
            "failed": {key: translate(message) for key, message in failed.items()},
        }
    ), (200 if saved or not failed else 400)


@bp.route(
    "/dref-monitoring/operations/<int:operation_id>/drafts/<int:draft_id>/chapters/<key>/reset", methods=["POST"]
)
@permission_required_any(*_ANY)
def draft_chapter_reset_route(operation_id: int, draft_id: int, key: str):
    """Take one chapter back to the text the model first wrote."""
    operation = _operation(operation_id, "enter")
    draft = _draft_row(operation, draft_id)
    error, html = reset_section(draft, operation, key, _actor())
    if error:
        return _json_error(error)
    chapter_sources = [row for row in narrative_sources(draft) if row.get("chapter") == key]
    return jsonify({"ok": True, **_chapter_state(key, html), "sources": chapter_sources})


@bp.route(
    "/dref-monitoring/operations/<int:operation_id>/drafts/<int:draft_id>/chapters/<key>/generate", methods=["POST"]
)
@permission_required_any(*_ANY)
def draft_chapter_generate_route(operation_id: int, draft_id: int, key: str):
    """Queue the model to write one chapter again. The text comes back in the job summary and is not stored."""
    operation = _operation(operation_id, "enter")
    draft = _draft_row(operation, draft_id)
    if not ai_enabled():
        return _json_error("AI drafting is not enabled.")
    if (draft.status or "draft") != "draft":
        return _json_error("This draft is already validated.")
    if narrative_mode_of(draft) == NARRATIVE_NONE:
        return _json_error("This report is figures only and has no narrative to edit.")
    if key not in chapter_keys_for(draft):
        return _json_error("Unknown chapter.", 404)
    body = request.get_json(silent=True) or {}
    current = body.get("current")
    params = {
        "action": ACTION_SECTION,
        "operation_id": operation.id,
        "kind": draft.report_kind,
        "draft_id": draft.id,
        "section": key,
        "instruction": " ".join(str(body.get("instruction") or "").split())[:400],
        "current": str(current)[:20000] if isinstance(current, str) else None,
    }
    response, status = _queue_draft_response(operation, params)
    payload = response.get_json()
    payload["section"] = key
    return jsonify(payload), status


@bp.route("/dref-monitoring/operations/<int:operation_id>/drafts/<int:draft_id>/import.docx", methods=["POST"])
@permission_required_any(*_ANY)
def draft_docx_import_route(operation_id: int, draft_id: int):
    """Read an edited Word export and say what each chapter would become. Nothing is saved here."""
    operation = _operation(operation_id, "enter")
    draft = _draft_row(operation, draft_id)
    if (draft.status or "draft") != "draft":
        return _json_error("This draft is already validated.")
    if narrative_mode_of(draft) == NARRATIVE_NONE:
        return _json_error("This report is figures only and has no narrative to edit.")
    upload = request.files.get("document")
    if upload is None or not upload.filename:
        return _json_error("Choose a Word document.")
    if not upload.filename.lower().endswith(".docx"):
        return _json_error("Use a Word document saved as .docx.")
    raw = upload.read(5 * 1024 * 1024 + 1)
    try:
        result = analyze_docx(raw, draft, operation)
    except DocxImportError as exc:
        return _json_error(str(exc))
    except Exception:
        current_app.logger.warning("DREF Word import failed for draft %s", draft.id, exc_info=True)
        return _json_error("The Word file could not be read.")
    result["warnings"] = [translate(message) for message in result["warnings"]]
    return jsonify(result)


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


@bp.route("/dref-monitoring/operations/<int:operation_id>/drafts/<int:draft_id>/delete", methods=["POST"])
@permission_required_any(*_ANY)
def draft_delete_route(operation_id: int, draft_id: int):
    operation = _operation(operation_id, "enter")
    draft = _draft_row(operation, draft_id)
    error = delete_draft(draft, operation, _actor())
    if error:
        flash(translate(error), "warning")
        return redirect(url_for(f"{PLUGIN_ID}.draft_page", operation_id=operation.id, draft_id=draft.id))
    flash(translate("The draft was deleted."), "success")
    return redirect(url_for(f"{PLUGIN_ID}.operation_page", operation_id=operation.id, tab="drafts"))


def _draft_row(operation, draft_id: int):
    draft = db.session.get(DrefDraft, draft_id)
    if draft is None or draft.operation_id != operation.id:
        abort(404)
    return draft


def _draft_blocks(operation, draft_id: int):
    draft = _draft_row(operation, draft_id)
    source = source_for(operation, draft)
    return draft, build_report(source), running_header(source)


def _export_blocks(operation, draft_id: int):
    """Empty sections stay out of a download unless the preview toggle asked for them."""
    draft, blocks, header = _draft_blocks(operation, draft_id)
    return draft, blocks_for_export(blocks, request.args.get("include_empty") == "1"), header


@bp.route("/dref-monitoring/operations/<int:operation_id>/drafts/<int:draft_id>/export.docx", methods=["GET"])
@permission_required_any(*_ANY)
def draft_docx_route(operation_id: int, draft_id: int):
    operation = _operation(operation_id, "enter")
    draft, blocks, header = _export_blocks(operation, draft_id)
    payload = render_docx(
        blocks,
        header,
        language=draft.language or "en",
        reference=expected_reference(operation.id, draft.id),
    )
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
    draft, blocks, header = _export_blocks(operation, draft_id)
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
