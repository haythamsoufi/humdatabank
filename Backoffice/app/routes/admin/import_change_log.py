"""View and download durable import change logs from the audit trail."""

from __future__ import annotations

from flask import Blueprint, abort, render_template
from flask_login import current_user

from app.models.core import UserActivityLog
from app.routes.admin.shared import admin_required, user_has_permission
from app.services.organization.authorization_service import AuthorizationService
from app.services.imports.import_change_log import (
    VIEWER_CHANGE_LIMIT,
    count_import_log_changes,
    count_import_log_noops,
    import_log_file_exists,
    is_valid_import_log_id,
    iter_import_log_changes,
    load_import_log_summary,
    stream_import_log_file,
)

bp = Blueprint("import_change_log", __name__, url_prefix="/admin/import-logs")


def _user_initiated_import_log(user_id: int, log_id: str) -> bool:
    return (
        UserActivityLog.query.filter(
            UserActivityLog.user_id == int(user_id),
            UserActivityLog.context_data["job_id"].as_string() == str(log_id),
        ).first()
        is not None
    )


def _require_log_id(log_id: str) -> str:
    """Validate the id and authorize the caller for this specific log.

    Logs hold row-level before/after values, so a route-level admin permission is not enough:
    only System Managers, audit-trail viewers, or the user who started the import may read one.
    Everyone else gets 404 so log ids cannot be probed.
    """
    if not is_valid_import_log_id(log_id):
        abort(404)
    if AuthorizationService.is_system_manager(current_user) or user_has_permission("admin.audit.view"):
        return log_id
    if not _user_initiated_import_log(current_user.id, log_id):
        abort(404)
    return log_id


@bp.route("/<log_id>", methods=["GET"])
@admin_required
def view_log(log_id: str):
    log_id = _require_log_id(log_id)
    summary = load_import_log_summary(log_id) or {}
    changes = list(iter_import_log_changes(log_id, limit=VIEWER_CHANGE_LIMIT))
    change_total = count_import_log_changes(log_id)
    stats = dict((summary.get("stats") or {}))
    noop_count = count_import_log_noops(log_id)
    if stats.get("unchanged") is None or int(stats.get("unchanged") or 0) < noop_count:
        stats["unchanged"] = noop_count
    inserted = int(stats.get("inserted") or 0)
    real_updates = max(change_total - inserted, 0)
    recorded_updates = int(stats.get("updated") or 0)
    if recorded_updates > real_updates:
        stats["updated"] = real_updates
    summary = {**summary, "stats": stats}
    ready = bool(summary.get("log_id")) or import_log_file_exists(log_id, "jsonl")
    return render_template(
        "admin/analytics/import_change_log.html",
        title="Import change log",
        log_id=log_id,
        summary=summary or {},
        changes=changes,
        change_total=change_total,
        truncated=change_total > len(changes),
        ready=ready,
        viewer_limit=VIEWER_CHANGE_LIMIT,
    )


@bp.route("/<log_id>/summary.json", methods=["GET"])
@admin_required
def download_summary(log_id: str):
    log_id = _require_log_id(log_id)
    return stream_import_log_file(
        log_id,
        "json",
        filename=f"import_change_log_{log_id}.json",
        mimetype="application/json",
    )


@bp.route("/<log_id>/changes.jsonl", methods=["GET"])
@admin_required
def download_changes(log_id: str):
    log_id = _require_log_id(log_id)
    return stream_import_log_file(
        log_id,
        "jsonl",
        filename=f"import_changes_{log_id}.jsonl",
        mimetype="application/x-ndjson",
    )
