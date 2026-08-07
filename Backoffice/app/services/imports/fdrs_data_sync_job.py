"""FDRS data sync background job (Track A — single-item batch via ai_job_runner)."""

from __future__ import annotations

import logging
import os
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

from app.extensions import db
from app.models import AIJob, AIJobItem
from app.services.imports.async_import_job_store import (
    FDRS_DATA_SYNC_JOB_TYPE,
    clear_import_job_logging_state,
    get_import_job,
    get_import_job_logging_state,
    update_import_job,
    _isolated_job_session,
)
from app.services.ai.ai_job_runner import (
    ensure_ai_job_running,
    job_cancel_requested,
    run_ai_job,
    signal_job_cancel,
    start_ai_job_thread,
)
from app.utils.datetime_helpers import utcnow

logger = logging.getLogger(__name__)


def _fdrs_imports_dir() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "imports"))


def _touch_sync_item_heartbeat(item_id: int) -> None:
    """Keep AIJobItem.updated_at fresh so stale recovery works during long syncs."""
    try:
        with _isolated_job_session() as session:
            item = session.get(AIJobItem, int(item_id))
            if item:
                item.updated_at = utcnow()
    except Exception as exc:
        logger.debug("FDRS sync item heartbeat failed: item=%s err=%s", item_id, exc)


def _summarize_error(exc: BaseException) -> str:
    err_msg = str(exc).strip() or type(exc).__name__
    if len(err_msg) > 2000:
        return err_msg[:1997] + "..."
    return err_msg


def create_fdrs_data_sync_job(
    *,
    user_id: int,
    template_id: int,
    dry_run: bool,
    batch_size: int,
    fdrs_years: Optional[List[int]],
    test_limit: Optional[int],
    imputed_use_cache: bool,
    sync_documents: bool,
    fdrs_reported_import_states: Optional[List[int]],
    preview_path: Optional[str],
    sync_user_id: Optional[int],
) -> str:
    """Create AIJob + single AIJobItem for an async FDRS data sync."""
    job_id = uuid.uuid4().hex
    now_ts = time.time()
    meta = {
        "template_id": int(template_id),
        "stage": "queued",
        "message": "Queued",
        "current": 0,
        "total": None,
        "percent": 0.0,
        "stats": None,
        "error": None,
        "preview_path": preview_path,
        "download_ready": False,
        "last_logged_pct": None,
        "started_ts": now_ts,
        "updated_ts": now_ts,
    }
    payload = {
        "template_id": int(template_id),
        "dry_run": bool(dry_run),
        "batch_size": int(batch_size),
        "fdrs_years": fdrs_years,
        "test_limit": test_limit,
        "imputed_use_cache": bool(imputed_use_cache),
        "sync_documents": bool(sync_documents),
        "fdrs_reported_import_states": fdrs_reported_import_states,
        "preview_path": preview_path,
        "sync_user_id": sync_user_id,
    }
    job = AIJob(
        id=job_id,
        job_type=FDRS_DATA_SYNC_JOB_TYPE,
        user_id=int(user_id or 0),
        status="queued",
        total_items=1,
        meta=meta,
    )
    item = AIJobItem(
        job_id=job_id,
        item_index=0,
        entity_type="form_template",
        entity_id=int(template_id),
        status="queued",
        payload=payload,
    )
    db.session.add(job)
    db.session.add(item)
    db.session.commit()
    return job_id


def get_active_fdrs_data_sync_jobs_for_user(
    user_id: int,
    *,
    template_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Return non-terminal FDRS sync jobs for resume UI."""
    if not user_id:
        return []

    query = AIJob.query.filter(
        AIJob.user_id == int(user_id),
        AIJob.job_type == FDRS_DATA_SYNC_JOB_TYPE,
        AIJob.status.in_(("queued", "running", "cancel_requested")),
    )

    jobs = query.order_by(AIJob.created_at.desc()).all()
    out: List[Dict[str, Any]] = []
    for job in jobs:
        meta = dict(job.meta or {})
        if template_id is not None and int(meta.get("template_id") or 0) != int(template_id):
            continue
        out.append(
            {
                "job_id": str(job.id),
                "job_type": job.job_type,
                "status": str(job.status),
                "template_id": int(meta.get("template_id") or 0),
                "stage": meta.get("stage") or "",
                "message": meta.get("message") or "",
                "percent": float(meta.get("percent") or 0.0),
                "total_items": int(job.total_items or 1),
            }
        )
    return out


def start_fdrs_data_sync_job(app, job_id: str) -> None:
    """Kick off (or noop if already running) the FDRS sync runner thread."""
    start_ai_job_thread(app, job_id, _run_fdrs_data_sync_job)


def ensure_fdrs_data_sync_job_running(app, job_id: str) -> None:
    """Reconcile stale state and resume orphaned FDRS sync jobs."""
    ensure_ai_job_running(app, job_id, _run_fdrs_data_sync_job)


def request_fdrs_data_sync_cancel(job_id: str) -> str:
    """Request cooperative cancellation; returns current/previous terminal status if any."""
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
        logger.debug("FDRS sync cancel item update failed: job=%s err=%s", job_id, exc)
        db.session.rollback()
    db.session.commit()
    signal_job_cancel(str(job_id))
    return "cancel_requested"


def build_fdrs_data_sync_status_payload(job_id: str, template_id: int) -> Optional[Dict[str, Any]]:
    """Build the job dict for the status poll endpoint."""
    job = get_import_job(job_id)
    if not job or int(job.get("template_id") or 0) != int(template_id):
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


def _process_fdrs_data_sync_item_sync(app, *, job_id: str, item_id: int) -> None:
    """Run the FDRS import pipeline for a single claimed job item."""
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
                error="Sync cancelled by user.",
            )
            db.session.commit()
            return

        payload = dict(item.payload or {})
        template_id = int(payload.get("template_id") or 0)
        dry_run = bool(payload.get("dry_run"))
        preview_path = payload.get("preview_path")
        sync_user_id = payload.get("sync_user_id")
        last_cancel_db_check = 0.0

        def _progress_cb(progress_payload: Dict[str, Any]) -> None:
            stage = progress_payload.get("stage") or ""
            pct = progress_payload.get("percent")
            msg = progress_payload.get("message") or ""
            existing = get_import_job(job_id) or {}
            if stage.startswith(("documents", "assignment_status")):
                current = progress_payload.get("current")
                total = progress_payload.get("total")
            else:
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
            _touch_sync_item_heartbeat(item_id)

            try:
                pct_f = float(pct) if pct is not None else None
            except Exception:
                pct_f = None
            log_state = get_import_job_logging_state(job_id)
            last_logged = log_state.get("last_logged_pct")
            should_log = (
                stage
                in (
                    "documents_plan",
                    "documents_done",
                    "assignment_status_plan",
                    "assignment_status_done",
                    "complete",
                    "failed",
                    "cancelled",
                )
                or (stage and stage != "upsert" and not stage.endswith("_upsert"))
                or (
                    pct_f is not None
                    and (last_logged is None or abs(pct_f - float(last_logged)) >= 5.0)
                )
            )
            if should_log and pct_f is not None:
                log_state["last_logged_pct"] = pct_f
                update_import_job(job_id, last_logged_pct=pct_f)
            if should_log:
                app.logger.info(
                    "Data sync %s: %s %s%% %s",
                    job_id,
                    stage or "-",
                    f"{pct_f:.1f}" if pct_f is not None else "-",
                    msg,
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
        _touch_sync_item_heartbeat(item_id)
        app.logger.info(
            "Data sync %s: starting (template_id=%s, dry_run=%s, test=%s, sync_documents=%s)",
            job_id,
            template_id,
            dry_run,
            payload.get("test_limit") is not None,
            payload.get("sync_documents"),
        )

        terminal_item_status = "failed"
        FdrsSyncCancelled = None
        try:
            imports_dir = _fdrs_imports_dir()
            if imports_dir not in sys.path:
                sys.path.insert(0, imports_dir)
            from import_fdrs_form_data import FdrsSyncCancelled, run_import

            stats = run_import(
                input_path=None,
                fdrs_api_url=None,
                fdrs_from_data_api=True,
                fdrs_data_api_base=None,
                fdrs_data_api_key=None,
                fdrs_imputed_url=None,
                fdrs_imputed_from_api=False,
                fdrs_imputed_kpi_codes_path=None,
                fdrs_imputed_use_cache=bool(payload.get("imputed_use_cache", True)),
                fdrs_years=payload.get("fdrs_years"),
                fdrs_reported_import_states=payload.get("fdrs_reported_import_states"),
                indicator_mapping_path=None,
                indicator_bank_api_base=None,
                indicator_bank_api_key=None,
                databank_base_url=None,
                databank_api_key=None,
                preview_excel_path=preview_path if dry_run else None,
                test_limit=payload.get("test_limit"),
                dry_run=dry_run,
                batch_size=int(payload.get("batch_size") or 1000),
                template_id=template_id,
                progress_cb=_progress_cb,
                cancel_check=_cancel_check,
                sync_user_id=sync_user_id,
                sync_documents=bool(payload.get("sync_documents", True)),
            )
            update_import_job(
                job_id,
                force=True,
                status="completed",
                stage="complete",
                message="Completed",
                percent=100.0,
                stats=dict(stats or {}),
                download_ready=bool(dry_run and preview_path and os.path.isfile(preview_path)),
            )
            item.status = "completed"
            item.error = None
            terminal_item_status = "completed"
            app.logger.info(
                "Data sync %s: completed loaded=%s skipped=%s inserted=%s updated=%s errors=%s",
                job_id,
                (stats or {}).get("loaded"),
                (stats or {}).get("skipped"),
                (stats or {}).get("inserted"),
                (stats or {}).get("updated"),
                (stats or {}).get("errors"),
            )
        except FdrsSyncCancelled:
            update_import_job(
                job_id,
                force=True,
                status="cancelled",
                stage="cancelled",
                message="Cancelled",
                error="Sync cancelled by user.",
            )
            item.status = "cancelled"
            item.error = None
            terminal_item_status = "cancelled"
            app.logger.info("Data sync %s: cancelled", job_id)
        except Exception as exc:
            logger.exception("Async data sync job failed: %s", exc)
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
            app.logger.error("Data sync %s: failed: %s", job_id, exc, exc_info=True)
        finally:
            if item.status not in ("completed", "failed", "cancelled"):
                item.status = terminal_item_status
            db.session.commit()
            clear_import_job_logging_state(job_id)
            db.session.remove()


def _run_fdrs_data_sync_job(app, job_id: str) -> None:
    run_ai_job(
        app,
        str(job_id),
        _process_fdrs_data_sync_item_sync,
        concurrency_config_keys=("FDRS_DATA_SYNC_CONCURRENCY",),
        default_concurrency=1,
    )
