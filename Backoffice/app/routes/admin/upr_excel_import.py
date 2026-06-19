"""UPR Master Excel import wizard routes."""

import os
import sys
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from flask import Blueprint, render_template, request, send_file, current_app
from flask_login import current_user

from app.routes.admin.shared import admin_permission_required, system_manager_required
from app.services.upr_excel_import_service import UprExcelImportService
from app.utils.advanced_validation import validate_upload_extension_and_mime
from app.utils.api_helpers import get_json_safe
from app.utils.api_responses import json_accepted, json_bad_request, json_ok, json_server_error
from app.utils.file_parsing import EXCEL_EXTENSIONS

from app.routes.admin.data_sync_imputation import (
    _DATA_SYNC_CANCEL_EVENTS,
    _DATA_SYNC_JOBS,
    _DATA_SYNC_LOCK,
    _cleanup_data_sync_jobs_locked,
    _get_data_sync_cancel_event,
    _utc_iso,
)

bp = Blueprint("upr_excel_import", __name__, url_prefix="/admin/templates/upr-excel-import")

UPR_TEMPLATE_CHOICES = [
    {"id": 24, "name": "Unified Country Plan (planning country data)"},
    {"id": 22, "name": "Annual Planning - International Bilateral Support (PNS staff)"},
]


@bp.route("/", methods=["GET"])
@admin_permission_required("admin.templates.view")
@system_manager_required
def wizard():
    return render_template(
        "admin/templates/upr_excel_import.html",
        title="UPR Excel Sync",
        template_choices=UPR_TEMPLATE_CHOICES,
    )


@bp.route("/upload", methods=["POST"])
@admin_permission_required("admin.templates.edit")
@system_manager_required
def upload():
    if "file" not in request.files:
        return json_bad_request("No file provided")
    f = request.files["file"]
    if not f or not f.filename:
        return json_bad_request("No file selected")
    valid, error_msg, _ext = validate_upload_extension_and_mime(f, EXCEL_EXTENSIONS)
    if not valid:
        return json_bad_request(error_msg or "Invalid file type")
    data = f.read()
    if len(data) > 80 * 1024 * 1024:
        return json_bad_request("File too large (max 80 MB)")
    file_id = UprExcelImportService.store_upload(data, f.filename)
    return json_ok(success=True, file_id=file_id, filename=f.filename)


@bp.route("/analyze", methods=["POST"])
@admin_permission_required("admin.templates.edit")
@system_manager_required
def analyze():
    result = UprExcelImportService.analyze_stored()
    if not result.get("success"):
        return json_bad_request(result.get("message") or "Analysis failed")
    return json_ok(**result)


@bp.route("/preview", methods=["POST"])
@admin_permission_required("admin.templates.edit")
@system_manager_required
def preview():
    data = get_json_safe()
    template_ids = [int(x) for x in (data.get("template_ids") or [24, 22])]
    rounds = data.get("rounds") or []
    result = UprExcelImportService.preview(template_ids=template_ids, rounds=rounds)
    if not result.get("success"):
        return json_bad_request(result.get("message") or "Preview failed")
    return json_ok(**result)


@bp.route("/run", methods=["POST"])
@admin_permission_required("admin.templates.edit")
@system_manager_required
def run_import():
    data = get_json_safe()
    template_ids = [int(x) for x in (data.get("template_ids") or [24, 22])]
    rounds = data.get("rounds") or []
    dry_run = bool(data.get("dry_run", False))
    batch_size = int(data.get("batch_size") or 1000)
    ensure_staff_matrix = bool(data.get("ensure_staff_matrix", True))  # kept for backward compat
    async_mode = bool(data.get("async", True))

    if batch_size < 100:
        return json_bad_request("Batch size must be >= 100")

    # Resolve the uploaded file path while still in the request context;
    # the session is not accessible inside the background worker thread.
    file_path = UprExcelImportService.stored_path()
    if not file_path:
        return json_bad_request("No uploaded file in session. Please upload again.")

    if not async_mode:
        try:
            stats = UprExcelImportService.run_import(
                file_path=file_path,
                template_ids=template_ids,
                rounds=rounds,
                dry_run=dry_run,
                batch_size=batch_size,
                ensure_staff_matrix=ensure_staff_matrix,
            )
            if not stats.get("success", True):
                return json_server_error(stats.get("message") or "Import failed")
            return json_ok(**stats)
        except Exception as exc:
            current_app.logger.error("UPR import failed: %s", exc, exc_info=True)
            return json_server_error(str(exc))

    job_id = uuid.uuid4().hex
    now_ts = time.time()

    with _DATA_SYNC_LOCK:
        _cleanup_data_sync_jobs_locked(now_ts)
        _DATA_SYNC_JOBS[job_id] = {
            "job_id": job_id,
            "kind": "upr_excel",
            "user_id": int(getattr(current_user, "id", 0) or 0),
            "status": "queued",
            "stage": "queued",
            "message": "Queued",
            "current": 0,
            "total": None,
            "percent": 0.0,
            "stats": None,
            "error": None,
            # preview_path is set from stats["preview_path"] after the worker completes
            "preview_path": None,
            "download_ready": False,
            "started_at": _utc_iso(),
            "updated_at": _utc_iso(),
            "started_ts": now_ts,
            "updated_ts": now_ts,
        }

    cancel_ev = _get_data_sync_cancel_event(job_id)
    logger = current_app.logger

    def _worker() -> None:
        from app import create_app

        app = create_app()

        def _progress_cb(payload: Dict[str, Any]) -> None:
            with _DATA_SYNC_LOCK:
                job = _DATA_SYNC_JOBS.get(job_id)
                if not job:
                    return
                job["status"] = "running"
                job["stage"] = payload.get("stage") or job.get("stage")
                job["message"] = payload.get("message") or job.get("message")
                job["current"] = payload.get("current")
                job["total"] = payload.get("total")
                if payload.get("percent") is not None:
                    job["percent"] = float(payload["percent"])
                if payload.get("stats"):
                    job["stats"] = dict(payload["stats"])
                job["updated_at"] = _utc_iso()
                job["updated_ts"] = time.time()

        def _cancel_check() -> bool:
            return cancel_ev.is_set()

        with app.app_context():
            try:
                with _DATA_SYNC_LOCK:
                    job = _DATA_SYNC_JOBS.get(job_id)
                    if job:
                        job["status"] = "running"
                        job["stage"] = "starting"
                        job["message"] = "Starting UPR import..."
                stats = UprExcelImportService.run_import(
                    file_path=file_path,
                    template_ids=template_ids,
                    rounds=rounds,
                    dry_run=dry_run,
                    batch_size=batch_size,
                    ensure_staff_matrix=ensure_staff_matrix,
                    progress_cb=_progress_cb,
                    cancel_check=_cancel_check,
                )
                with _DATA_SYNC_LOCK:
                    job = _DATA_SYNC_JOBS.get(job_id)
                    if not job:
                        return
                    preview_file = stats.get("preview_path")
                    job["status"] = "completed"
                    job["stage"] = "complete"
                    job["message"] = "Import completed"
                    job["percent"] = 100.0
                    job["stats"] = stats
                    job["preview_path"] = preview_file
                    job["download_ready"] = bool(dry_run and preview_file)
                    if job["download_ready"]:
                        job["download_url"] = f"/admin/templates/upr-excel-import/download/{job_id}"
                    job["updated_at"] = _utc_iso()
                    job["updated_ts"] = time.time()
            except Exception as exc:
                logger.error("UPR async import failed: %s", exc, exc_info=True)
                with _DATA_SYNC_LOCK:
                    job = _DATA_SYNC_JOBS.get(job_id)
                    if job:
                        job["status"] = "failed"
                        job["error"] = str(exc)
                        job["message"] = str(exc)
                        job["updated_at"] = _utc_iso()
                        job["updated_ts"] = time.time()
            finally:
                _DATA_SYNC_CANCEL_EVENTS.pop(job_id, None)

    threading.Thread(target=_worker, daemon=True).start()
    return json_accepted(success=True, job_id=job_id)


@bp.route("/status/<job_id>", methods=["GET"])
@admin_permission_required("admin.templates.view")
@system_manager_required
def job_status(job_id: str):
    with _DATA_SYNC_LOCK:
        job = _DATA_SYNC_JOBS.get(job_id)
    if not job or job.get("kind") != "upr_excel":
        return json_bad_request("Job not found")
    return json_ok(success=True, job=job)


@bp.route("/cancel/<job_id>", methods=["POST"])
@admin_permission_required("admin.templates.edit")
@system_manager_required
def cancel_job(job_id: str):
    with _DATA_SYNC_LOCK:
        job = _DATA_SYNC_JOBS.get(job_id)
        if not job or job.get("kind") != "upr_excel":
            return json_bad_request("Job not found")
        job["status"] = "cancel_requested"
    ev = _get_data_sync_cancel_event(job_id)
    ev.set()
    return json_ok(success=True)


@bp.route("/download/<job_id>", methods=["GET"])
@admin_permission_required("admin.templates.view")
@system_manager_required
def download_preview(job_id: str):
    with _DATA_SYNC_LOCK:
        job = _DATA_SYNC_JOBS.get(job_id)
    if not job or not job.get("download_ready"):
        return json_bad_request("Preview not available")
    path = job.get("preview_path")
    if not path or not os.path.isfile(path):
        return json_bad_request("Preview file missing")
    return send_file(path, as_attachment=True, download_name=f"upr_import_preview_{job_id}.xlsx")
