"""HTTP routes for FDRS admin tools (data sync)."""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import uuid
from contextlib import suppress
from typing import Any, Dict, List, Optional

from flask import after_this_request, current_app, redirect, render_template, request, send_file, url_for
from flask_login import current_user

from app.models import FormTemplate
from app.routes.admin.shared import (
    admin_permission_required,
    admin_required,
    check_template_access,
    permission_required,
    system_manager_required,
)
from app.services.imports.async_import_job_store import (
    cleanup_expired_import_jobs,
    get_import_job,
    update_import_job,
)
from app.services.imports.import_change_log import (
    ImportChangeLogWriter,
    attach_import_change_log_to_activity,
    set_import_audit_details,
)
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.api_responses import (
    json_accepted,
    json_bad_request,
    json_forbidden,
    json_not_found,
    json_ok,
)
from werkzeug.exceptions import HTTPException
from app.utils.error_handling import handle_json_view_exception
from plugins.fdrs import bp
from plugins.fdrs.scripts_path import ensure_fdrs_scripts_in_path
from plugins.fdrs.services.fdrs_data_sync_job import (
    build_fdrs_data_sync_status_payload,
    create_fdrs_data_sync_job,
    ensure_fdrs_data_sync_job_running,
    request_fdrs_data_sync_cancel,
    start_fdrs_data_sync_job,
    _run_fdrs_data_sync_job,
)
from plugins.fdrs.services.fdrs_sync_verify_job import (
    build_fdrs_sync_verify_status_payload,
    create_fdrs_sync_verify_job,
    ensure_fdrs_sync_verify_job_running,
    read_fdrs_sync_verify_workbook,
    request_fdrs_sync_verify_cancel,
    start_fdrs_sync_verify_job,
    _run_fdrs_sync_verify_job,
)
from plugins.fdrs.services import fdrs_tools_artifacts as artifacts

_SYNC_LOCK = threading.Lock()
_SYNC_ALLOWED_STATES = frozenset({0, 100, 200, 300, 400, 500})

# cleanup_expired_import_jobs() scans the AIJob table. Status polls hit this
# route every ~2-5s for the duration of a sync (which can run tens of
# minutes), so without a throttle that scan runs hundreds of times per sync
# for no benefit (the job TTL is 6 hours; see IMPORT_JOB_TTL_SECONDS). Mirrors
# the existing _maybe_cleanup_expired_jobs() throttle in ai_job_runner.py.
_last_import_job_cleanup_ts = 0.0
_CLEANUP_MIN_INTERVAL_SECONDS = 300.0


def _maybe_cleanup_expired_import_jobs() -> None:
    global _last_import_job_cleanup_ts
    now = time.time()
    with _SYNC_LOCK:
        if now - _last_import_job_cleanup_ts < _CLEANUP_MIN_INTERVAL_SECONDS:
            return
        _last_import_job_cleanup_ts = now
    cleanup_expired_import_jobs(now)


def _job_looks_actively_running(job: Dict[str, Any], *, fresh_seconds: float = 60.0) -> bool:
    """True when the job self-reports "running" with a recent heartbeat.

    Lets status polls skip ``ensure_*_job_running`` (thread-liveness probing,
    stuck-item recovery, an extra AIJob lookup) while a sync is actively
    progressing — that reconciliation path exists to resume/fail orphaned
    jobs, not to be re-run on every poll of a healthy one. Reconciliation
    still runs normally whenever the heartbeat goes quiet (worker crashed,
    job stuck, or not started yet), well before the real staleness threshold
    (FDRS_DATA_SYNC_JOB_STALE_SECONDS, default 900s, minimum 60s).
    """
    if job.get("status") != "running":
        return False
    updated_ts = job.get("updated_ts")
    if updated_ts is None:
        return False
    try:
        return (time.time() - float(updated_ts)) < fresh_seconds
    except (TypeError, ValueError):
        return False


def fdrs_imports_dir() -> str:
    return ensure_fdrs_scripts_in_path()


def fdrs_default_years_bounds() -> tuple[int, int]:
    imports_dir = fdrs_imports_dir()
    if imports_dir not in sys.path:
        sys.path.insert(0, imports_dir)
    from fdrs_data_fetcher import DEFAULT_FDRS_YEARS_END, DEFAULT_FDRS_YEARS_START

    return DEFAULT_FDRS_YEARS_START, DEFAULT_FDRS_YEARS_END


def fdrs_sync_script_available() -> bool:
    return os.path.isfile(os.path.join(fdrs_imports_dir(), "import_fdrs_form_data.py"))


def fdrs_settings_status() -> Dict[str, Any]:
    from app.utils.data_quality_constants import FDRS_TEMPLATE_ID

    years_start = years_end = None
    try:
        years_start, years_end = fdrs_default_years_bounds()
    except Exception:
        pass
    return {
        "template_id": FDRS_TEMPLATE_ID,
        "sync_script_available": fdrs_sync_script_available(),
        "years_start": years_start,
        "years_end": years_end,
        "data_source": "data-api.ifrc.org",
    }


@bp.route("/admin/plugins/fdrs/settings", methods=["GET"])
@admin_required
@permission_required("admin.plugins.manage")
def settings_page():
    return render_template("plugins/fdrs/settings.html", settings=fdrs_settings_status())


def parse_reported_import_states(data: Dict[str, Any]) -> Optional[List[int]]:
    if "fdrs_reported_import_states" not in data:
        return None
    raw = data.get("fdrs_reported_import_states")
    if raw is None:
        return None
    out: List[int] = []
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        for p in parts:
            try:
                out.append(int(p))
            except ValueError:
                raise ValueError("Each data status must be a whole number (IFRC State).")
    elif isinstance(raw, (list, tuple)):
        for p in raw:
            try:
                out.append(int(p))
            except (TypeError, ValueError):
                raise ValueError("Each data status must be a whole number (IFRC State).")
    else:
        raise ValueError("Data statuses must be sent as a list or comma-separated numbers.")
    if not out:
        raise ValueError("Select at least one data status to include.")
    bad = [x for x in out if x not in _SYNC_ALLOWED_STATES]
    if bad:
        raise ValueError(
            "Unknown data status value(s): %s. Use only the statuses shown on the Sync tab."
            % (", ".join(str(x) for x in sorted(set(bad))),)
        )
    return out


@bp.route("/admin/fdrs-tools", methods=["GET"])
@admin_required
@system_manager_required
def fdrs_tools():
    """FDRS tools hub: preview, imputation, Sync (run/verify), documents, and publication."""
    from app.routes.admin.data_sync_imputation import render_data_sync_imputation_page
    from app.utils.data_quality_constants import FDRS_TEMPLATE_ID as fdrs_template_id
    from flask import current_app
    from flask_login import current_user
    from plugins.fdrs.services.fdrs_document_status_job import (
        ensure_fdrs_document_status_job_running,
        get_active_fdrs_document_status_jobs_for_user,
    )
    from plugins.fdrs.services.fdrs_publication_job import (
        ensure_fdrs_publication_job_running,
        get_active_fdrs_publication_jobs_for_user,
    )
    from plugins.fdrs.services.fdrs_publication_service import list_fdrs_assignments

    user_id = int(getattr(current_user, "id", 0) or 0)
    active_publication_jobs = get_active_fdrs_publication_jobs_for_user(user_id) if user_id else []
    active_document_jobs = get_active_fdrs_document_status_jobs_for_user(user_id) if user_id else []
    worker_app = current_app._get_current_object()
    for active in active_publication_jobs:
        jid = active.get("job_id")
        if jid:
            ensure_fdrs_publication_job_running(worker_app, str(jid))
    for active in active_document_jobs:
        jid = active.get("job_id")
        if jid:
            ensure_fdrs_document_status_job_running(worker_app, str(jid))

    return render_data_sync_imputation_page(
        fdrs_template_id,
        sync_family="fdrs",
        page_heading="FDRS Tools",
        page_icon="fas fa-cogs",
        extra_tabs=[
            {
                "id": "sync",
                "label": "Sync",
                "icon": "fas fa-sync-alt",
            },
            {
                "id": "documents",
                "label": "Documents",
                "icon": "fas fa-file-alt",
            },
            {
                "id": "publication",
                "label": "Manage Publication",
                "icon": "fas fa-tower-broadcast",
            },
        ],
        extra_panel_templates=[
            {
                "id": "sync",
                "template": "plugins/fdrs/admin/_fdrs_sync_panel.html",
            },
            {
                "id": "documents",
                "template": "plugins/fdrs/admin/_fdrs_documents_panel.html",
            },
            {
                "id": "publication",
                "template": "plugins/fdrs/admin/_fdrs_publication_panel.html",
            },
        ],
        extra_script_templates=[
            "plugins/fdrs/admin/_fdrs_sync_script.html",
            "plugins/fdrs/admin/_fdrs_documents_script.html",
            "plugins/fdrs/admin/_fdrs_publication_script.html",
        ],
        show_template_selector=False,
        extra_context={
            "assignments": list_fdrs_assignments(),
            "active_fdrs_publication_jobs": active_publication_jobs,
            "active_fdrs_document_jobs": active_document_jobs,
            "fdrs_verify_latest": artifacts.load_verify_latest_meta(fdrs_template_id),
            "fdrs_documents_latest": artifacts.load_documents_latest_meta(),
        },
    )


@bp.route("/admin/fdrs-sync-imputation", methods=["GET"])
@admin_required
@system_manager_required
def fdrs_sync_imputation():
    """Legacy URL for the FDRS tools hub."""
    return redirect(url_for("fdrs.fdrs_tools"), code=301)


@bp.route("/admin/templates/data-sync/<int:template_id>/run-data-sync", methods=["POST"])
@admin_permission_required("admin.templates.edit")
def run_data_sync(template_id: int):
    try:
        template = FormTemplate.query.get_or_404(template_id)
        if not check_template_access(template_id, current_user.id):
            return json_forbidden("Access denied")

        data = get_json_safe()
        dry_run = bool(data.get("dry_run", False))
        batch_size_raw = data.get("batch_size", None)
        if batch_size_raw in (None, ""):
            batch_size = 1000
        else:
            try:
                batch_size = int(batch_size_raw)
            except Exception as e:
                current_app.logger.debug("batch_size parse failed: %s", e)
                return json_bad_request("Invalid batch_size: must be an integer (or omit it)")
        if batch_size < 100:
            return json_bad_request("Invalid batch_size: must be >= 100")
        fdrs_years_raw = (data.get("fdrs_years") or "").strip()
        test_mode = bool(data.get("test", False))
        async_mode = bool(data.get("async", False))
        imputed_use_cache = bool(data.get("imputed_use_cache", True))
        sync_documents = bool(data.get("sync_documents", True))
        try:
            fdrs_reported_import_states = parse_reported_import_states(data)
        except ValueError as e:
            return json_bad_request(str(e))

        fdrs_years = None
        test_limit = None
        if test_mode:
            fdrs_years = [2024]
            test_limit = 1000
        elif fdrs_years_raw:
            try:
                fdrs_years = [int(y.strip()) for y in fdrs_years_raw.split(",") if y.strip()]
            except ValueError:
                return json_bad_request("Invalid fdrs_years: use comma-separated integers")

        imports_dir = fdrs_imports_dir()
        if imports_dir not in sys.path:
            sys.path.insert(0, imports_dir)
        from import_fdrs_form_data import run_import

        preview_path = None
        if dry_run:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
            tmp.close()
            preview_path = tmp.name

        if async_mode:
            sync_user_id = int(getattr(current_user, "id", 0) or 0) or None
            _maybe_cleanup_expired_import_jobs()

            job_id = create_fdrs_data_sync_job(
                user_id=int(getattr(current_user, "id", 0) or 0),
                template_id=template_id,
                dry_run=dry_run,
                batch_size=batch_size,
                fdrs_years=fdrs_years,
                test_limit=test_limit,
                imputed_use_cache=imputed_use_cache,
                sync_documents=sync_documents,
                fdrs_reported_import_states=fdrs_reported_import_states,
                preview_path=preview_path,
                sync_user_id=sync_user_id,
            )
            set_import_audit_details(
                log_id=job_id,
                import_kind="fdrs_data_sync",
                templates=[template.name or str(template_id)],
                dry_run=dry_run,
                extra={"years": fdrs_years} if fdrs_years else None,
            )

            worker_app = current_app._get_current_object()
            if current_app.config.get("TESTING"):
                _run_fdrs_data_sync_job(worker_app, job_id)
            else:
                start_fdrs_data_sync_job(worker_app, job_id)
            return json_accepted(job_id=job_id)

        log_id = uuid.uuid4().hex
        set_import_audit_details(
            log_id=log_id,
            import_kind="fdrs_data_sync",
            templates=[template.name or str(template_id)],
            dry_run=dry_run,
            extra={"years": fdrs_years} if fdrs_years else None,
        )
        writer = ImportChangeLogWriter(
            log_id,
            kind="fdrs_data_sync",
            meta={
                "template_id": template_id,
                "dry_run": dry_run,
                "fdrs_years": fdrs_years,
            },
        )
        try:
            stats = run_import(
                input_path=None,
                fdrs_api_url=None,
                fdrs_from_data_api=True,
                fdrs_data_api_base=None,
                fdrs_data_api_key=None,
                fdrs_imputed_url=None,
                fdrs_imputed_from_api=False,
                fdrs_imputed_kpi_codes_path=None,
                fdrs_imputed_use_cache=imputed_use_cache,
                fdrs_years=fdrs_years,
                fdrs_reported_import_states=fdrs_reported_import_states,
                indicator_mapping_path=None,
                indicator_bank_api_base=None,
                indicator_bank_api_key=None,
                databank_base_url=None,
                databank_api_key=None,
                preview_excel_path=preview_path if dry_run else None,
                test_limit=test_limit,
                dry_run=dry_run,
                batch_size=batch_size,
                template_id=template_id,
                sync_user_id=int(getattr(current_user, "id", 0) or 0) or None,
                sync_documents=sync_documents,
                change_recorder=writer.record,
            )
            writer.finalize(dict(stats or {}))
            stats = dict(stats or {})
            stats["change_log_id"] = log_id
        except Exception:
            if not writer._finalized:
                writer.finalize({"success": False, "errors": 1})
            raise
        attach_import_change_log_to_activity(
            log_id=log_id,
            user_id=int(getattr(current_user, "id", 0) or 0) or None,
            extra={
                "rows_inserted": stats.get("inserted"),
                "rows_updated": stats.get("updated"),
                "rows_unchanged": stats.get("unchanged"),
                "rows_skipped": stats.get("skipped"),
                "rows_errors": stats.get("errors"),
            },
        )

        if dry_run and preview_path and os.path.isfile(preview_path):
            @after_this_request
            def _remove_preview(resp):
                try:
                    os.unlink(preview_path)
                except OSError:
                    pass
                return resp
            return send_file(
                preview_path,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                as_attachment=True,
                download_name=f"data_sync_preview_{template_id}.xlsx",
            )

        return json_ok(
            success=True,
            dry_run=dry_run,
            stats=stats,
            change_log_id=log_id,
            message=(
                f"Loaded: {stats['loaded']}, Skipped: {stats['skipped']}, "
                f"Inserted: {stats['inserted']}, Updated: {stats['updated']}, "
                f"Unchanged: {stats.get('unchanged', 0)}, Errors: {stats['errors']}"
                + (
                    f"; Documents: +{stats.get('documents_inserted', 0)} "
                    f"~{stats.get('documents_updated', 0)} "
                    f"approved={stats.get('documents_status_approved', 0)} "
                    f"pending={stats.get('documents_status_pending', 0)} "
                    f"rejected={stats.get('documents_status_rejected', 0)} "
                    f"err={stats.get('documents_errors', 0)}"
                    if stats.get("documents_inserted") is not None or stats.get("documents_updated")
                    else ""
                )
            ),
        )
    except HTTPException:
        raise
    except (ValueError, RuntimeError) as e:
        current_app.logger.error(f"Data sync error: {e}", exc_info=True)
        msg = str(e).strip() or "Sync failed."
        return json_bad_request(msg[:2000] if len(msg) > 2000 else msg)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/admin/templates/data-sync/<int:template_id>/data-sync-status/<job_id>", methods=["GET"])
@admin_permission_required("admin.templates.edit")
def data_sync_status(template_id: int, job_id: str):
    _maybe_cleanup_expired_import_jobs()

    job = get_import_job(job_id)
    if not job or int(job.get("template_id") or 0) != int(template_id):
        return json_not_found("Job not found")
    if int(job.get("user_id") or 0) != int(getattr(current_user, "id", 0) or 0):
        return json_forbidden("Access denied")

    if not _job_looks_actively_running(job):
        ensure_fdrs_data_sync_job_running(current_app._get_current_object(), job_id)
    job_payload = build_fdrs_data_sync_status_payload(job_id, template_id)
    if not job_payload:
        return json_not_found("Job not found")

    resp = {"success": True, "job": job_payload}
    if resp["job"]["download_ready"]:
        resp["job"]["download_url"] = url_for(
            "fdrs.data_sync_download",
            template_id=template_id,
            job_id=job_id,
        )
    return json_ok(**resp)


@bp.route("/admin/templates/data-sync/<int:template_id>/data-sync-cancel/<job_id>", methods=["POST"])
@admin_permission_required("admin.templates.edit")
def data_sync_cancel(template_id: int, job_id: str):
    job = get_import_job(job_id)
    if not job or int(job.get("template_id") or 0) != int(template_id):
        return json_not_found("Job not found")
    if int(job.get("user_id") or 0) != int(getattr(current_user, "id", 0) or 0):
        return json_forbidden("Access denied")

    status = job.get("status")
    if status in ("completed", "failed", "cancelled"):
        return json_ok(status=status)

    final_status = request_fdrs_data_sync_cancel(job_id)
    return json_ok(status=final_status)


@bp.route("/admin/templates/data-sync/<int:template_id>/data-sync-download/<job_id>", methods=["GET"])
@admin_permission_required("admin.templates.edit")
def data_sync_download(template_id: int, job_id: str):
    job = get_import_job(job_id)
    if not job or int(job.get("template_id") or 0) != int(template_id):
        return json_not_found("Job not found")
    if int(job.get("user_id") or 0) != int(getattr(current_user, "id", 0) or 0):
        return json_forbidden("Access denied")
    path = job.get("preview_path")
    if not path or not os.path.isfile(path):
        return json_not_found("Preview file not available")

    @after_this_request
    def _remove_preview(resp):
        with suppress(Exception):
            os.unlink(path)
        update_import_job(job_id, force=True, download_ready=False, preview_path=None)
        return resp

    return send_file(
        path,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"data_sync_preview_{template_id}.xlsx",
    )


def _owned_import_job_or_error(template_id: int, job_id: str):
    job = get_import_job(job_id)
    if not job or int(job.get("template_id") or 0) != int(template_id):
        return None, json_not_found("Job not found")
    if int(job.get("user_id") or 0) != int(getattr(current_user, "id", 0) or 0):
        return None, json_forbidden("Access denied")
    return job, None


@bp.route("/admin/templates/data-sync/<int:template_id>/run-sync-verify", methods=["POST"])
@admin_permission_required("admin.templates.edit")
def run_sync_verify(template_id: int):
    try:
        FormTemplate.query.get_or_404(template_id)
        if not check_template_access(template_id, current_user.id):
            return json_forbidden("Access denied")

        data = get_json_safe()
        test_mode = bool(data.get("test", False))
        skip_imputed = bool(data.get("skip_imputed", False))
        problems_only = bool(data.get("problems_only", False))
        imputed_use_cache = bool(data.get("imputed_use_cache", True))
        fdrs_years_raw = (data.get("fdrs_years") or "").strip()
        try:
            fdrs_reported_import_states = parse_reported_import_states(data)
        except ValueError as e:
            return json_bad_request(str(e))

        fdrs_years = None
        if test_mode:
            fdrs_years = [2024]
        elif fdrs_years_raw:
            try:
                fdrs_years = [int(y.strip()) for y in fdrs_years_raw.split(",") if y.strip()]
            except ValueError:
                return json_bad_request("Invalid fdrs_years: use comma-separated integers")
        if not fdrs_years:
            return json_bad_request("Select at least one reporting year.")

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        tmp.close()
        output_path = tmp.name

        _maybe_cleanup_expired_import_jobs()

        job_id = create_fdrs_sync_verify_job(
            user_id=int(getattr(current_user, "id", 0) or 0),
            template_id=template_id,
            fdrs_years=fdrs_years,
            skip_imputed=skip_imputed,
            fresh_imputed=not imputed_use_cache,
            problems_only=problems_only,
            fdrs_reported_import_states=fdrs_reported_import_states,
            output_path=output_path,
        )
        worker_app = current_app._get_current_object()
        if current_app.config.get("TESTING"):
            _run_fdrs_sync_verify_job(worker_app, job_id)
        else:
            start_fdrs_sync_verify_job(worker_app, job_id)
        return json_accepted(job_id=job_id)
    except HTTPException:
        raise
    except (ValueError, RuntimeError) as e:
        current_app.logger.error("FDRS verify error: %s", e, exc_info=True)
        msg = str(e).strip() or "Verification failed."
        return json_bad_request(msg[:2000] if len(msg) > 2000 else msg)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/admin/templates/data-sync/<int:template_id>/sync-verify-status/<job_id>", methods=["GET"])
@admin_permission_required("admin.templates.edit")
def sync_verify_status(template_id: int, job_id: str):
    _maybe_cleanup_expired_import_jobs()

    _owned, err = _owned_import_job_or_error(template_id, job_id)
    if err is not None:
        return err

    if not _job_looks_actively_running(_owned):
        ensure_fdrs_sync_verify_job_running(current_app._get_current_object(), job_id)
    job_payload = build_fdrs_sync_verify_status_payload(job_id, template_id)
    if not job_payload:
        return json_not_found("Job not found")

    resp = {"success": True, "job": job_payload}
    if resp["job"]["download_ready"]:
        resp["job"]["download_url"] = url_for(
            "fdrs.sync_verify_download",
            template_id=template_id,
            job_id=job_id,
        )
        resp["job"]["results_url"] = url_for(
            "fdrs.sync_verify_results",
            template_id=template_id,
            job_id=job_id,
        )
    return json_ok(**resp)


@bp.route("/admin/templates/data-sync/<int:template_id>/sync-verify-cancel/<job_id>", methods=["POST"])
@admin_permission_required("admin.templates.edit")
def sync_verify_cancel(template_id: int, job_id: str):
    job, err = _owned_import_job_or_error(template_id, job_id)
    if err is not None:
        return err

    status = job.get("status")
    if status in ("completed", "failed", "cancelled"):
        return json_ok(status=status)

    final_status = request_fdrs_sync_verify_cancel(job_id)
    return json_ok(status=final_status)


def _verify_workbook_source(template_id: int, job: Optional[Dict[str, Any]] = None):
    """Prefer the job's temp file, then the durable latest blob."""
    path = (job or {}).get("preview_path")
    if path and os.path.isfile(path):
        return path
    if artifacts.verify_latest_exists(template_id):
        return artifacts.download_bytes(artifacts.verify_xlsx_rel(template_id))
    return None


def _verify_table_args():
    sheet = (request.args.get("sheet") or "data_points").strip()
    status = (request.args.get("status") or "").strip()
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
    return sheet, status, page, per_page


@bp.route("/admin/templates/data-sync/<int:template_id>/sync-verify-download/<job_id>", methods=["GET"])
@admin_permission_required("admin.templates.edit")
def sync_verify_download(template_id: int, job_id: str):
    job, err = _owned_import_job_or_error(template_id, job_id)
    if err is not None:
        return err
    path = job.get("preview_path")
    if path and os.path.isfile(path):
        return send_file(
            path,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"fdrs_sync_verification_{template_id}.xlsx",
        )
    if artifacts.exists(artifacts.verify_xlsx_rel(template_id)):
        return artifacts.stream_xlsx(
            artifacts.verify_xlsx_rel(template_id),
            f"fdrs_sync_verification_{template_id}.xlsx",
        )
    return json_not_found("Verification file not available")


@bp.route("/admin/templates/data-sync/<int:template_id>/sync-verify-results/<job_id>", methods=["GET"])
@admin_permission_required("admin.templates.edit")
def sync_verify_results(template_id: int, job_id: str):
    """JSON table of the verification workbook (same sheets as the Excel)."""
    job, err = _owned_import_job_or_error(template_id, job_id)
    if err is not None:
        return err
    source = _verify_workbook_source(template_id, job)
    if source is None:
        return json_not_found("Verification file not available")

    sheet, status, page, per_page = _verify_table_args()
    try:
        table = read_fdrs_sync_verify_workbook(
            source,
            sheet=sheet,
            status=status,
            page=page,
            per_page=per_page,
        )
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

    latest = artifacts.load_verify_latest_meta(template_id) or {}
    table["stats"] = job.get("stats") or latest.get("stats")
    table["completed_at"] = latest.get("completed_at")
    table["download_url"] = url_for(
        "fdrs.sync_verify_download",
        template_id=template_id,
        job_id=job_id,
    )
    return json_ok(**table)


@bp.route("/admin/templates/data-sync/<int:template_id>/sync-verify-latest", methods=["GET"])
@admin_permission_required("admin.templates.edit")
def sync_verify_latest(template_id: int):
    if not check_template_access(template_id, current_user.id):
        return json_forbidden("Access denied")
    meta = artifacts.load_verify_latest_meta(template_id)
    if not meta:
        return json_ok(exists=False)
    return json_ok(
        exists=True,
        completed_at=meta.get("completed_at"),
        stats=meta.get("stats") or {},
        fdrs_years=meta.get("fdrs_years"),
        skip_imputed=meta.get("skip_imputed"),
        problems_only=meta.get("problems_only"),
        download_url=url_for("fdrs.sync_verify_latest_download", template_id=template_id),
        results_url=url_for("fdrs.sync_verify_latest_results", template_id=template_id),
    )


@bp.route("/admin/templates/data-sync/<int:template_id>/sync-verify-latest/results", methods=["GET"])
@admin_permission_required("admin.templates.edit")
def sync_verify_latest_results(template_id: int):
    if not check_template_access(template_id, current_user.id):
        return json_forbidden("Access denied")
    source = _verify_workbook_source(template_id)
    if source is None:
        return json_not_found("Verification file not available")

    sheet, status, page, per_page = _verify_table_args()
    try:
        table = read_fdrs_sync_verify_workbook(
            source,
            sheet=sheet,
            status=status,
            page=page,
            per_page=per_page,
        )
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

    latest = artifacts.load_verify_latest_meta(template_id) or {}
    table["stats"] = latest.get("stats")
    table["completed_at"] = latest.get("completed_at")
    table["download_url"] = url_for("fdrs.sync_verify_latest_download", template_id=template_id)
    return json_ok(**table)


@bp.route("/admin/templates/data-sync/<int:template_id>/sync-verify-latest/download", methods=["GET"])
@admin_permission_required("admin.templates.edit")
def sync_verify_latest_download(template_id: int):
    if not check_template_access(template_id, current_user.id):
        return json_forbidden("Access denied")
    if artifacts.exists(artifacts.verify_xlsx_rel(template_id)):
        return artifacts.stream_xlsx(
            artifacts.verify_xlsx_rel(template_id),
            f"fdrs_sync_verification_{template_id}.xlsx",
        )
    return json_not_found("Verification file not available")
