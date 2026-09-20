"""Admin routes for the FDRS document URL / availability scan."""

from __future__ import annotations

import os
import tempfile

from flask import current_app, request
from flask_login import current_user
from werkzeug.exceptions import HTTPException

from app.routes.admin.shared import admin_permission_required
from app.services.imports.async_import_job_store import get_import_job
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.api_responses import (
    json_accepted,
    json_bad_request,
    json_forbidden,
    json_not_found,
    json_ok,
)
from app.utils.error_handling import handle_json_view_exception
from plugins.fdrs import bp
from plugins.fdrs.routes import _job_looks_actively_running, _maybe_cleanup_expired_import_jobs
from plugins.fdrs.services import fdrs_tools_artifacts as artifacts
from plugins.fdrs.services.fdrs_document_status_job import (
    _run_fdrs_document_status_job,
    build_fdrs_document_status_payload,
    create_fdrs_document_status_job,
    ensure_fdrs_document_status_job_running,
    request_fdrs_document_status_cancel,
    start_fdrs_document_status_job,
)
from plugins.fdrs.services.fdrs_tools_artifacts import read_xlsx_sheet

_DOCUMENT_SHEET_ALIASES = {
    "documents": "documents",
    "document": "documents",
    "summary": "summary",
    "meta": "meta",
}


def _owned_document_job_or_error(job_id: str):
    job = get_import_job(job_id)
    if not job:
        return None, json_not_found("Job not found")
    if int(job.get("user_id") or 0) != int(getattr(current_user, "id", 0) or 0):
        return None, json_forbidden("Access denied")
    return job, None


def _latest_table_payload():
    if not artifacts.documents_latest_exists():
        return None
    return artifacts.download_bytes(artifacts.documents_xlsx_rel())


def _parse_table_args():
    sheet = (request.args.get("sheet") or "documents").strip()
    search = (request.args.get("q") or request.args.get("search") or "").strip()
    try:
        page = int(request.args.get("page") or 1)
    except (TypeError, ValueError):
        page = 1
    all_rows = (request.args.get("all") or "").strip().lower() in ("1", "true", "yes")
    try:
        per_page = int(request.args.get("per_page") or (0 if all_rows else 200))
    except (TypeError, ValueError):
        per_page = 0 if all_rows else 200
    if all_rows:
        per_page = 0
    filters = {}
    for key in ("http_status", "downloadable", "is_public", "year", "document_type"):
        val = (request.args.get(key) or "").strip()
        if val:
            filters[key] = val
    return sheet, search, page, per_page, filters


@bp.route("/admin/fdrs-tools/documents/run", methods=["POST"])
@admin_permission_required("admin.templates.edit")
def run_document_status():
    try:
        data = get_json_safe()
        test_mode = bool(data.get("test", False))
        limit_raw = data.get("limit")
        limit = 50 if test_mode else None
        if limit_raw not in (None, ""):
            try:
                limit = max(1, int(limit_raw))
            except (TypeError, ValueError):
                return json_bad_request("Invalid limit")

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        tmp.close()
        _maybe_cleanup_expired_import_jobs()
        job_id = create_fdrs_document_status_job(
            user_id=int(getattr(current_user, "id", 0) or 0),
            output_path=tmp.name,
            limit=limit,
        )
        worker_app = current_app._get_current_object()
        if current_app.config.get("TESTING"):
            _run_fdrs_document_status_job(worker_app, job_id)
        else:
            start_fdrs_document_status_job(worker_app, job_id)
        return json_accepted(job_id=job_id)
    except HTTPException:
        raise
    except (ValueError, RuntimeError) as e:
        current_app.logger.error("FDRS document status error: %s", e, exc_info=True)
        msg = str(e).strip() or "Document scan failed."
        return json_bad_request(msg[:2000] if len(msg) > 2000 else msg)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/admin/fdrs-tools/documents/status/<job_id>", methods=["GET"])
@admin_permission_required("admin.templates.edit")
def document_status_job_status(job_id: str):
    _maybe_cleanup_expired_import_jobs()
    _owned, err = _owned_document_job_or_error(job_id)
    if err is not None:
        return err
    if not _job_looks_actively_running(_owned):
        ensure_fdrs_document_status_job_running(current_app._get_current_object(), job_id)
    job_payload = build_fdrs_document_status_payload(job_id)
    if not job_payload:
        return json_not_found("Job not found")
    resp = {"success": True, "job": job_payload}
    if job_payload.get("download_ready"):
        from flask import url_for

        resp["job"]["download_url"] = url_for("fdrs.document_status_latest_download")
        resp["job"]["results_url"] = url_for("fdrs.document_status_latest_results")
    return json_ok(**resp)


@bp.route("/admin/fdrs-tools/documents/cancel/<job_id>", methods=["POST"])
@admin_permission_required("admin.templates.edit")
def document_status_cancel(job_id: str):
    job, err = _owned_document_job_or_error(job_id)
    if err is not None:
        return err
    status = job.get("status")
    if status in ("completed", "failed", "cancelled"):
        return json_ok(status=status)
    return json_ok(status=request_fdrs_document_status_cancel(job_id))


@bp.route("/admin/fdrs-tools/documents/latest", methods=["GET"])
@admin_permission_required("admin.templates.edit")
def document_status_latest():
    meta = artifacts.load_documents_latest_meta()
    if not meta:
        return json_ok(exists=False)
    from flask import url_for

    return json_ok(
        exists=True,
        completed_at=meta.get("completed_at"),
        stats=meta.get("stats") or {},
        filter_options=(meta.get("stats") or {}).get("filter_options") or meta.get("filter_options") or {},
        download_url=url_for("fdrs.document_status_latest_download"),
        results_url=url_for("fdrs.document_status_latest_results"),
    )


@bp.route("/admin/fdrs-tools/documents/latest/results", methods=["GET"])
@admin_permission_required("admin.templates.edit")
def document_status_latest_results():
    source = _latest_table_payload()
    if source is None:
        path = None
        job_id = (request.args.get("job_id") or "").strip()
        if job_id:
            job = get_import_job(job_id)
            path = (job or {}).get("preview_path")
        if not path or not os.path.isfile(path):
            return json_not_found("Document status file not available")
        source = path

    sheet, search, page, per_page, filters = _parse_table_args()
    try:
        table = read_xlsx_sheet(
            source,
            sheet=sheet,
            aliases=_DOCUMENT_SHEET_ALIASES,
            page=page,
            per_page=per_page,
            filters=filters or None,
            search=search,
            search_columns=["iso3", "don_code", "name", "document_type", "url"],
        )
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

    meta = artifacts.load_documents_latest_meta() or {}
    stats = meta.get("stats") or {}
    from flask import url_for

    table["stats"] = stats
    table["completed_at"] = meta.get("completed_at")
    table["filter_options"] = stats.get("filter_options") or {}
    table["download_url"] = url_for("fdrs.document_status_latest_download")
    return json_ok(**table)


@bp.route("/admin/fdrs-tools/documents/latest/download", methods=["GET"])
@admin_permission_required("admin.templates.edit")
def document_status_latest_download():
    if artifacts.exists(artifacts.documents_xlsx_rel()):
        return artifacts.stream_xlsx(
            artifacts.documents_xlsx_rel(),
            "fdrs_document_url_status.xlsx",
        )
    return json_not_found("Document status file not available")
