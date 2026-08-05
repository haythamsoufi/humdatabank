"""
Background runner registry for AI batch jobs (import, reprocess, etc.).

Goals:
- Jobs continue when the browser closes (non-daemon worker threads).
- Orphan recovery: resume queued work when a worker thread died (app reload, crash).
- Stale detection: fail stuck items/jobs that stopped making progress.
"""

from __future__ import annotations

import logging
import threading
from datetime import timedelta
from typing import Callable, Optional

from app.utils.datetime_helpers import utcnow

logger = logging.getLogger(__name__)

_JOB_THREADS_LOCK = threading.Lock()
_JOB_THREADS: dict[str, threading.Thread] = {}

_TERMINAL_JOB_STATUSES = frozenset({"completed", "failed", "cancelled"})
_TERMINAL_ITEM_STATUSES = frozenset({"completed", "failed", "cancelled"})
_ACTIVE_ITEM_STATUSES = frozenset({"queued", "downloading", "processing"})

# Job types surfaced to the AI documents UI for resume/polling.
AI_DOCUMENTS_JOB_TYPES = frozenset(
    {
        "docs.bulk_import_system",
        "docs.bulk_reprocess",
        "docs.bulk_reprocess_metadata",
        "ifrc_api_bulk",
    }
)


def _job_stale_seconds() -> int:
    from flask import current_app

    try:
        raw = current_app.config.get("AI_DOCS_JOB_STALE_SECONDS", 180)
        return max(60, min(int(raw or 180), 3600))
    except Exception:
        return 180


def is_job_thread_alive(job_id: str) -> bool:
    with _JOB_THREADS_LOCK:
        thread = _JOB_THREADS.get(str(job_id))
        return thread is not None and thread.is_alive()


def _job_thread_wrapper(app, job_id: str, target: Callable) -> None:
    current = threading.current_thread()
    try:
        target(app, str(job_id))
    except Exception as exc:
        logger.error("AI job thread crashed: job=%s err=%s", job_id, exc, exc_info=True)
    finally:
        with _JOB_THREADS_LOCK:
            if _JOB_THREADS.get(str(job_id)) is current:
                _JOB_THREADS.pop(str(job_id), None)


def start_ai_job_thread(app, job_id: str, target: Callable) -> None:
    """Start a background job thread when one is not already running for *job_id*."""
    job_id = str(job_id)
    with _JOB_THREADS_LOCK:
        existing = _JOB_THREADS.get(job_id)
        if existing is not None and existing.is_alive():
            return
        thread = threading.Thread(
            target=_job_thread_wrapper,
            args=(app, job_id, target),
            name=f"ai-job-{job_id[:8]}",
            daemon=False,
        )
        _JOB_THREADS[job_id] = thread
        thread.start()
    logger.info("AI job thread started: job=%s", job_id)


def _latest_item_activity(job) -> Optional[object]:
    latest = job.started_at or job.created_at
    for item in job.items or []:
        touched = item.updated_at or item.created_at
        if touched and (latest is None or touched > latest):
            latest = touched
    return latest


def _finalize_job_status(job) -> None:
    from app.extensions import db

    items = job.items or []
    if not items:
        if job.status not in _TERMINAL_JOB_STATUSES:
            job.status = "failed"
            job.error = job.error or "Job has no items."
            job.finished_at = utcnow()
            db.session.commit()
        return

    if not all((it.status in _TERMINAL_ITEM_STATUSES) for it in items):
        return

    if job.status in _TERMINAL_JOB_STATUSES:
        return

    if job.status == "cancel_requested":
        job.status = "cancelled"
    elif any(it.status == "failed" for it in items):
        job.status = "failed"
        job.error = job.error or "One or more items failed."
    else:
        job.status = "completed"
    job.finished_at = utcnow()
    db.session.commit()
    logger.info("AI job finalized: job=%s status=%s", job.id, job.status)


def _recover_stuck_job_items(job, *, stale_seconds: int) -> None:
    """Mark long-idle in-flight items as failed when no worker thread is alive."""
    from app.extensions import db
    from app.models import AIDocument

    if is_job_thread_alive(str(job.id)):
        return

    cutoff = utcnow() - timedelta(seconds=stale_seconds)
    changed = False
    for item in job.items or []:
        if item.status not in ("downloading", "processing"):
            continue
        touched = item.updated_at or item.created_at
        if touched and touched > cutoff:
            continue
        item.status = "failed"
        item.error = "Processing interrupted (worker stopped). Re-run import or reprocess."
        changed = True
        doc_id = None
        if item.entity_type == "ai_document" and item.entity_id:
            doc_id = int(item.entity_id)
        else:
            payload = item.payload if isinstance(item.payload, dict) else {}
            raw = payload.get("ai_document_id")
            if raw is not None:
                try:
                    doc_id = int(raw)
                except (TypeError, ValueError):
                    doc_id = None
        if doc_id is not None:
            doc = AIDocument.query.get(doc_id)
            if doc and doc.processing_status in ("pending", "processing"):
                doc.processing_status = "failed"
                doc.processing_error = item.error
    if changed:
        db.session.commit()
        logger.warning("Recovered stuck AI job items: job=%s", job.id)


def reconcile_stale_ai_job(job_id: str) -> bool:
    """
    Recover stuck items, finalize finished jobs, or abandon hopelessly idle jobs.

    Returns True when the job was moved to a terminal status.
    """
    from app.extensions import db
    from app.models import AIJob

    job = AIJob.query.get(str(job_id))
    if not job:
        return False
    if job.status in _TERMINAL_JOB_STATUSES:
        return False

    stale_seconds = _job_stale_seconds()
    abandon_seconds = max(stale_seconds * 10, 1800)

    _recover_stuck_job_items(job, stale_seconds=stale_seconds)
    job = AIJob.query.get(str(job_id))
    if not job or job.status in _TERMINAL_JOB_STATUSES:
        return job is not None and job.status in _TERMINAL_JOB_STATUSES

    items = job.items or []
    has_pending = any((it.status in _ACTIVE_ITEM_STATUSES) for it in items)
    if not has_pending:
        _finalize_job_status(job)
        job = AIJob.query.get(str(job_id))
        return bool(job and job.status in _TERMINAL_JOB_STATUSES)

    if is_job_thread_alive(str(job.id)):
        return False

    last_activity = _latest_item_activity(job) or job.created_at
    if last_activity and last_activity > utcnow() - timedelta(seconds=abandon_seconds):
        # Worker thread may have died recently — caller can resume queued work.
        return False

    try:
        for item in items:
            if item.status in _ACTIVE_ITEM_STATUSES:
                item.status = "failed"
                item.error = "Processing interrupted (worker stopped). Re-run import or reprocess."
        job.status = "failed"
        job.error = "The background worker stopped responding (likely after an app restart). Re-run the job."
        job.finished_at = utcnow()
        db.session.commit()
        logger.warning("Abandoned stale AI job: job=%s", job_id)
        return True
    except Exception as exc:
        db.session.rollback()
        logger.debug("Stale AI job abandon failed: %s", exc)
        return False


def ensure_ai_job_running(app, job_id: str, target: Callable) -> None:
    """
    Reconcile stale state, finalize finished jobs, and resume orphaned runners.

    Safe to call from status polling endpoints and page load.
    """
    from app.extensions import db
    from app.models import AIJob

    job_id = str(job_id)
    reconcile_stale_ai_job(job_id)

    job = AIJob.query.get(job_id)
    if not job:
        return
    if job.status in _TERMINAL_JOB_STATUSES:
        return

    has_pending = any((it.status in _ACTIVE_ITEM_STATUSES) for it in (job.items or []))
    if not has_pending:
        _finalize_job_status(job)
        return

    if job.status == "queued":
        job.status = "running"
        job.started_at = job.started_at or utcnow()
        db.session.commit()

    if is_job_thread_alive(job_id):
        return

    start_ai_job_thread(app, job_id, target)


def get_active_ai_document_jobs_for_user(user_id: int) -> list[dict]:
    """Return non-terminal AI document jobs owned by *user_id* (for UI resume)."""
    from app.models import AIJob

    if not user_id:
        return []

    jobs = (
        AIJob.query.filter(
            AIJob.user_id == int(user_id),
            AIJob.job_type.in_(tuple(AI_DOCUMENTS_JOB_TYPES)),
            AIJob.status.in_(("queued", "running", "cancel_requested")),
        )
        .order_by(AIJob.created_at.desc())
        .all()
    )

    out: list[dict] = []
    for job in jobs:
        items = job.items or []
        completed = sum(1 for it in items if it.status == "completed")
        failed = sum(1 for it in items if it.status == "failed")
        cancelled = sum(1 for it in items if it.status == "cancelled")
        in_progress = sum(1 for it in items if it.status in _ACTIVE_ITEM_STATUSES)
        out.append(
            {
                "job_id": str(job.id),
                "job_type": job.job_type,
                "status": job.status,
                "total_items": int(job.total_items or 0),
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "counts": {
                    "completed": completed,
                    "failed": failed,
                    "cancelled": cancelled,
                    "in_progress": in_progress,
                },
            }
        )
    return out
