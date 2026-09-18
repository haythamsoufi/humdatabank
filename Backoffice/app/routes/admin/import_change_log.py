"""View and download durable import change logs from the audit trail."""

from __future__ import annotations

import os

from flask import Blueprint, abort, render_template, send_file

from app.routes.admin.shared import permission_required_any
from app.services.imports.import_change_log import (
    VIEWER_CHANGE_LIMIT,
    changes_path,
    count_import_log_changes,
    is_valid_import_log_id,
    iter_import_log_changes,
    load_import_log_summary,
    summary_path,
)

bp = Blueprint("import_change_log", __name__, url_prefix="/admin/import-logs")


def _require_log_id(log_id: str) -> str:
    if not is_valid_import_log_id(log_id):
        abort(404)
    return log_id


@bp.route("/<log_id>", methods=["GET"])
@permission_required_any("admin.audit.view", "admin.templates.view")
def view_log(log_id: str):
    log_id = _require_log_id(log_id)
    summary = load_import_log_summary(log_id)
    changes = list(iter_import_log_changes(log_id, limit=VIEWER_CHANGE_LIMIT))
    change_total = int((summary or {}).get("change_count") or 0) or count_import_log_changes(log_id)
    ready = bool(summary) or os.path.isfile(changes_path(log_id))
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
@permission_required_any("admin.audit.view", "admin.templates.view")
def download_summary(log_id: str):
    log_id = _require_log_id(log_id)
    path = summary_path(log_id)
    if not os.path.isfile(path):
        abort(404)
    return send_file(
        path,
        mimetype="application/json",
        as_attachment=True,
        download_name=f"import_change_log_{log_id}.json",
    )


@bp.route("/<log_id>/changes.jsonl", methods=["GET"])
@permission_required_any("admin.audit.view", "admin.templates.view")
def download_changes(log_id: str):
    log_id = _require_log_id(log_id)
    path = changes_path(log_id)
    if not os.path.isfile(path):
        abort(404)
    return send_file(
        path,
        mimetype="application/x-ndjson",
        as_attachment=True,
        download_name=f"import_changes_{log_id}.jsonl",
    )
