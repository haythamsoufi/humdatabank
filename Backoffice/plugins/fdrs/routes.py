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

from flask import after_this_request, current_app, redirect, render_template, send_file, url_for
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

_SYNC_LOCK = threading.Lock()
_SYNC_ALLOWED_STATES = frozenset({0, 100, 200, 300, 400, 500})


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
            "Unknown data status value(s): %s. Use only the statuses shown in the sync dialog."
            % (", ".join(str(x) for x in sorted(set(bad))),)
        )
    return out


@bp.route("/admin/fdrs-sync-imputation", methods=["GET"])
@admin_required
@system_manager_required
def fdrs_sync_imputation():
    from app.routes.admin.data_sync_imputation import render_data_sync_imputation_page
    from app.utils.data_quality_constants import FDRS_TEMPLATE_ID as fdrs_template_id

    return render_data_sync_imputation_page(fdrs_template_id, sync_family="fdrs")


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
            with _SYNC_LOCK:
                cleanup_expired_import_jobs(time.time())

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
                f"Inserted: {stats['inserted']}, Updated: {stats['updated']}, Errors: {stats['errors']}"
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
    with _SYNC_LOCK:
        cleanup_expired_import_jobs(time.time())

    job = get_import_job(job_id)
    if not job or int(job.get("template_id") or 0) != int(template_id):
        return json_not_found("Job not found")
    if int(job.get("user_id") or 0) != int(getattr(current_user, "id", 0) or 0):
        return json_forbidden("Access denied")

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
