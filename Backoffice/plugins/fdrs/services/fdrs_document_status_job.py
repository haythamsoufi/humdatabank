"""FDRS document-status scan background job (AIJob + single item)."""

from __future__ import annotations

import logging
import os
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

from app.extensions import db
from app.models import AIJob, AIJobItem
from app.services.ai.ai_job_runner import (
    ensure_ai_job_running,
    job_cancel_requested,
    run_ai_job,
    signal_job_cancel,
    start_ai_job_thread,
)
from app.services.imports.async_import_job_store import (
    FDRS_DOCUMENT_STATUS_JOB_TYPE,
    clear_import_job_logging_state,
    get_import_job,
    get_import_job_logging_state,
    update_import_job,
    _isolated_job_session,
)
from app.utils.datetime_helpers import utcnow

logger = logging.getLogger(__name__)


def _fdrs_imports_dir() -> str:
    from plugins.fdrs.scripts_path import ensure_fdrs_scripts_in_path

    return ensure_fdrs_scripts_in_path()


def _touch_item_heartbeat(item_id: int) -> None:
    try:
        with _isolated_job_session() as session:
            item = session.get(AIJobItem, int(item_id))
            if item:
                item.updated_at = utcnow()
    except Exception as exc:
        logger.debug("FDRS document-status heartbeat failed: item=%s err=%s", item_id, exc)


def _summarize_error(exc: BaseException) -> str:
    err_msg = str(exc).strip() or type(exc).__name__
    if len(err_msg) > 2000:
        return err_msg[:1997] + "..."
    return err_msg


def create_fdrs_document_status_job(
    *,
    user_id: int,
    output_path: str,
    limit: Optional[int] = None,
    workers: int = 20,
) -> str:
    job_id = uuid.uuid4().hex
    now_ts = time.time()
    meta = {
        "stage": "queued",
        "message": "Queued",
        "current": 0,
        "total": None,
        "percent": 0.0,
        "stats": None,
        "error": None,
        "preview_path": output_path,
        "download_ready": False,
        "last_logged_pct": None,
        "started_ts": now_ts,
        "updated_ts": now_ts,
        "limit": limit,
    }
    payload = {
        "output_path": output_path,
        "limit": limit,
        "workers": int(workers),
    }
    job = AIJob(
        id=job_id,
        job_type=FDRS_DOCUMENT_STATUS_JOB_TYPE,
        user_id=int(user_id or 0),
        status="queued",
        total_items=1,
        meta=meta,
    )
    item = AIJobItem(
        job_id=job_id,
        item_index=0,
        entity_type="fdrs_documents",
        entity_id=0,
        status="queued",
        payload=payload,
    )
    db.session.add(job)
    db.session.add(item)
    db.session.commit()
    return job_id


def get_active_fdrs_document_status_jobs_for_user(user_id: int) -> List[Dict[str, Any]]:
    if not user_id:
        return []
    jobs = (
        AIJob.query.filter(
            AIJob.user_id == int(user_id),
            AIJob.job_type == FDRS_DOCUMENT_STATUS_JOB_TYPE,
            AIJob.status.in_(("queued", "running", "cancel_requested")),
        )
        .order_by(AIJob.created_at.desc())
        .all()
    )
    out: List[Dict[str, Any]] = []
    for job in jobs:
        meta = dict(job.meta or {})
        out.append(
            {
                "job_id": str(job.id),
                "job_type": job.job_type,
                "status": str(job.status),
                "stage": meta.get("stage") or "",
                "message": meta.get("message") or "",
                "percent": float(meta.get("percent") or 0.0),
                "total_items": int(job.total_items or 1),
            }
        )
    return out


def start_fdrs_document_status_job(app, job_id: str) -> None:
    start_ai_job_thread(app, job_id, _run_fdrs_document_status_job)


def ensure_fdrs_document_status_job_running(app, job_id: str) -> None:
    ensure_ai_job_running(app, job_id, _run_fdrs_document_status_job)


def request_fdrs_document_status_cancel(job_id: str) -> str:
    job = AIJob.query.get(str(job_id))
    if not job:
        return "missing"
    if job.status in ("completed", "failed", "cancelled"):
        return str(job.status)

    job.status = "cancel_requested"
    try:
        (
            db.session.query(AIJobItem)
            .filter(
                AIJobItem.job_id == str(job_id),
                AIJobItem.status == "queued",
            )
            .update({"status": "cancelled", "error": None}, synchronize_session=False)
        )
    except Exception as exc:
        logger.debug("FDRS document-status cancel item update failed: job=%s err=%s", job_id, exc)
        db.session.rollback()
    db.session.commit()
    signal_job_cancel(str(job_id))
    return "cancel_requested"


def build_fdrs_document_status_payload(job_id: str) -> Optional[Dict[str, Any]]:
    job = get_import_job(job_id)
    if not job:
        return None
    return {
        "job_id": job_id,
        "status": job.get("status"),
        "stage": job.get("stage"),
        "message": job.get("message"),
        "current": job.get("current"),
        "total": job.get("total"),
        "percent": job.get("percent"),
        "stats": job.get("stats"),
        "error": job.get("error"),
        "started_at": job.get("started_at"),
        "updated_at": job.get("updated_at"),
        "download_ready": bool(job.get("download_ready")),
    }


def _process_fdrs_document_status_item(app, *, job_id: str, item_id: int) -> None:
    with app.app_context():
        item = AIJobItem.query.get(int(item_id))
        if not item or str(item.job_id) != str(job_id):
            return

        if job_cancel_requested(job_id):
            item.status = "cancelled"
            item.error = None
            update_import_job(
                job_id,
                force=True,
                status="cancelled",
                stage="cancelled",
                message="Cancelled",
                error="Document scan cancelled by user.",
            )
            db.session.commit()
            return

        payload = dict(item.payload or {})
        output_path = payload.get("output_path")
        last_cancel_db_check = 0.0

        def _progress_cb(progress_payload: Dict[str, Any]) -> None:
            existing = get_import_job(job_id) or {}
            current = (
                progress_payload.get("current")
                if progress_payload.get("current") is not None
                else existing.get("current")
            )
            total = (
                progress_payload.get("total")
                if progress_payload.get("total") is not None
                else existing.get("total")
            )
            update_import_job(
                job_id,
                status="running",
                stage=progress_payload.get("stage") or existing.get("stage"),
                message=progress_payload.get("message") or existing.get("message"),
                current=current,
                total=total,
                percent=float(progress_payload.get("percent") or existing.get("percent") or 0.0),
                stats=(
                    progress_payload.get("stats")
                    if progress_payload.get("stats") is not None
                    else existing.get("stats")
                ),
            )
            _touch_item_heartbeat(item_id)

            try:
                pct_f = float(progress_payload.get("percent")) if progress_payload.get("percent") is not None else None
            except Exception:
                pct_f = None
            log_state = get_import_job_logging_state(job_id)
            last_logged = log_state.get("last_logged_pct")
            stage = progress_payload.get("stage") or ""
            should_log = (
                stage in ("complete", "failed", "cancelled", "fetch_catalog", "write_excel")
                or (pct_f is not None and (last_logged is None or abs(pct_f - float(last_logged)) >= 5.0))
            )
            if should_log and pct_f is not None:
                update_import_job(job_id, last_logged_pct=pct_f)
            if should_log:
                app.logger.info(
                    "FDRS document status %s: %s %s%% %s",
                    job_id,
                    stage or "-",
                    f"{pct_f:.1f}" if pct_f is not None else "-",
                    progress_payload.get("message") or "",
                )

        def _cancel_check() -> bool:
            nonlocal last_cancel_db_check
            if job_cancel_requested(job_id):
                return True
            now = time.time()
            if now - last_cancel_db_check >= 1.0:
                last_cancel_db_check = now
                if job_cancel_requested(job_id):
                    return True
            return False

        update_import_job(
            job_id,
            force=True,
            status="running",
            stage="starting",
            message="Starting...",
            worker_pid=os.getpid(),
        )
        _touch_item_heartbeat(item_id)
        app.logger.info("FDRS document status %s: starting (limit=%s)", job_id, payload.get("limit"))

        terminal_item_status = "failed"
        FdrsDocumentScanCancelled = None
        try:
            imports_dir = _fdrs_imports_dir()
            if imports_dir not in sys.path:
                sys.path.insert(0, imports_dir)
            from export_fdrs_document_url_status import (
                FdrsDocumentScanCancelled,
                execute_document_url_status_scan,
            )

            api_key = (app.config.get("FDRS_DATA_API_KEY") or os.environ.get("FDRS_DATA_API_KEY") or "").strip()
            stats = execute_document_url_status_scan(
                output_path=str(output_path),
                api_key=api_key or None,
                workers=int(payload.get("workers") or 20),
                limit=payload.get("limit"),
                progress_cb=_progress_cb,
                cancel_check=_cancel_check,
            )
            persisted = False
            if output_path and os.path.isfile(output_path):
                try:
                    from plugins.fdrs.services import fdrs_tools_artifacts as artifacts

                    artifacts.persist_documents_latest(
                        local_xlsx_path=str(output_path),
                        stats=dict(stats or {}),
                        extra={"job_id": job_id, "limit": payload.get("limit")},
                    )
                    persisted = True
                except Exception:
                    logger.exception(
                        "FDRS document status %s: failed to persist workbook to storage", job_id
                    )
            update_import_job(
                job_id,
                force=True,
                status="completed",
                stage="complete",
                message="Completed",
                percent=100.0,
                stats=dict(stats or {}),
                download_ready=bool(
                    persisted or (output_path and os.path.isfile(output_path))
                ),
            )
            item.status = "completed"
            item.error = None
            terminal_item_status = "completed"
            app.logger.info(
                "FDRS document status %s: completed total=%s downloadable=%s",
                job_id,
                (stats or {}).get("total_documents"),
                (stats or {}).get("downloadable_count"),
            )
        except FdrsDocumentScanCancelled:
            update_import_job(
                job_id,
                force=True,
                status="cancelled",
                stage="cancelled",
                message="Cancelled",
                error="Document scan cancelled by user.",
            )
            item.status = "cancelled"
            item.error = None
            terminal_item_status = "cancelled"
            app.logger.info("FDRS document status %s: cancelled", job_id)
        except Exception as exc:
            logger.exception("Async FDRS document-status job failed: %s", exc)
            err_msg = _summarize_error(exc)
            update_import_job(
                job_id,
                force=True,
                status="failed",
                stage="failed",
                message="Failed",
                error=err_msg,
            )
            item.status = "failed"
            item.error = err_msg
            app.logger.error("FDRS document status %s: failed: %s", job_id, exc, exc_info=True)
        finally:
            if item.status not in ("completed", "failed", "cancelled"):
                item.status = terminal_item_status
            db.session.commit()
            clear_import_job_logging_state(job_id)
            db.session.remove()


def _run_fdrs_document_status_job(app, job_id: str) -> None:
    run_ai_job(
        app,
        str(job_id),
        _process_fdrs_document_status_item,
        concurrency_config_keys=("FDRS_DATA_SYNC_CONCURRENCY",),
        default_concurrency=1,
    )
