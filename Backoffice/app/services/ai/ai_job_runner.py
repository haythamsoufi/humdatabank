"""
Background runner registry for AI batch jobs (import, reprocess, etc.).

Goals:
- Jobs continue when the browser closes (non-daemon worker threads).
- Orphan recovery: resume queued work when a worker thread died (app reload, crash).
- Stale detection: fail stuck items/jobs that stopped making progress.
- Cross-worker safety: DB-checked cancellation and PostgreSQL advisory locks.
"""

from __future__ import annotations

import logging
import threading
import time
import zlib
from concurrent.futures import ThreadPoolExecutor, wait as wait_futures
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterator, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.utils.datetime_helpers import ensure_utc, utcnow

logger = logging.getLogger(__name__)

_JOB_THREADS_LOCK = threading.Lock()
_JOB_THREADS: dict[str, threading.Thread] = {}

_JOB_CANCEL_EVENTS: dict[str, threading.Event] = {}
_JOB_CANCEL_LOCK = threading.Lock()

_TERMINAL_JOB_STATUSES = frozenset({"completed", "failed", "cancelled"})
_TERMINAL_ITEM_STATUSES = frozenset({"completed", "failed", "cancelled"})
_ACTIVE_ITEM_STATUSES = frozenset({"queued", "downloading", "processing"})

AI_DOCUMENTS_JOB_TTL_SECONDS = 6 * 60 * 60
_AI_DOCS_JOB_LOCK_BASE = 950_000_000
_last_cleanup_ts = 0.0
_last_cleanup_lock = threading.Lock()

# How often run_ai_job's wait loop pings the advisory-lock-holding connection while a
# batch of items is in flight. Keeps that connection from sitting fully idle for the
# whole (potentially long) job, well under typical idle/pool-recycle timeouts.
_LOCK_KEEPALIVE_SECONDS = 60

# Job types surfaced to the AI documents UI for resume/polling.
AI_DOCUMENTS_JOB_TYPES = frozenset(
    {
        "docs.bulk_import_system",
        "docs.bulk_reprocess",
        "docs.bulk_reprocess_metadata",
        "ifrc_api_bulk",
    }
)

try:
    from app.services.imports.async_import_job_store import FDRS_DATA_SYNC_JOB_TYPE, IMPORT_JOB_TYPES
except ImportError:  # pragma: no cover - import cycle guard during partial loads
    FDRS_DATA_SYNC_JOB_TYPE = "fdrs.data_sync"
    IMPORT_JOB_TYPES = frozenset({FDRS_DATA_SYNC_JOB_TYPE})

# Shared batch job types using this runner (AI docs + cross-domain imports).
BACKOFFICE_BATCH_JOB_TYPES = frozenset(set(AI_DOCUMENTS_JOB_TYPES) | set(IMPORT_JOB_TYPES))


def _status_str(value) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value or "")


@contextmanager
def _isolated_job_session() -> Iterator[Session]:
    """Session scoped to AIJob persistence, isolated from request/import sessions."""
    from app.extensions import db

    session = sessionmaker(bind=db.engine)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _job_stale_seconds() -> int:
    from flask import current_app

    try:
        raw = current_app.config.get("AI_DOCS_JOB_STALE_SECONDS", 180)
        return max(60, min(int(raw or 180), 3600))
    except Exception:
        return 180


def _import_job_stale_seconds() -> int:
    from flask import current_app

    try:
        raw = current_app.config.get("FDRS_DATA_SYNC_JOB_STALE_SECONDS", 900)
        return max(60, min(int(raw or 900), 7200))
    except Exception:
        return 900


def _stale_seconds_for_job(job) -> int:
    if job and getattr(job, "job_type", None) in IMPORT_JOB_TYPES:
        return _import_job_stale_seconds()
    return _job_stale_seconds()


def _job_lock_id(job_id: str) -> int:
    """Stable advisory-lock id for *job_id* (namespace clear of digest/RBAC locks)."""
    digest = zlib.crc32(str(job_id).encode("utf-8")) & 0xFFFFFFFF
    return int(_AI_DOCS_JOB_LOCK_BASE + (digest % 49_000_000))


def _get_job_cancel_event(job_id: str) -> threading.Event:
    with _JOB_CANCEL_LOCK:
        ev = _JOB_CANCEL_EVENTS.get(str(job_id))
        if ev is None:
            ev = threading.Event()
            _JOB_CANCEL_EVENTS[str(job_id)] = ev
        return ev


def signal_job_cancel(job_id: str) -> None:
    """Same-process fast-path cancel signal (used by cancel endpoints)."""
    _get_job_cancel_event(str(job_id)).set()


def clear_job_cancel_event(job_id: str) -> None:
    with _JOB_CANCEL_LOCK:
        _JOB_CANCEL_EVENTS.pop(str(job_id), None)


def job_cancel_requested(job_id: str) -> bool:
    """True when cancel was requested in DB or via the in-process Event."""
    job_id = str(job_id)
    if _get_job_cancel_event(job_id).is_set():
        return True
    try:
        with _isolated_job_session() as session:
            from app.models import AIJob

            job = session.get(AIJob, job_id)
            if not job:
                return False
            return _status_str(job.status) == "cancel_requested"
    except Exception as exc:
        logger.debug("job_cancel_requested check failed for %s: %s", job_id, exc)
        return False


@contextmanager
def _job_runner_lock(app, job_id: str) -> Iterator[bool]:
    """Acquire a session advisory lock for running *job_id* (PostgreSQL only)."""
    from app.extensions import db
    from app.utils.pg_advisory_lock import release_session_advisory_lock, try_session_advisory_lock

    acquired = False
    lock_id = _job_lock_id(job_id)
    with app.app_context():
        if db.engine.dialect.name == "postgresql":
            acquired = try_session_advisory_lock(db.session, lock_id)
            if not acquired:
                logger.debug("AI job runner lock held elsewhere: job=%s lock=%s", job_id, lock_id)
                yield False
                return
        else:
            acquired = True
        try:
            yield True
        finally:
            if db.engine.dialect.name == "postgresql":
                try:
                    release_session_advisory_lock(db.session, lock_id, acquired=acquired)
                except Exception as exc:
                    logger.debug("AI job runner unlock failed: job=%s err=%s", job_id, exc)


def _touch_lock_connection(job_id: str) -> None:
    """
    Lightweight keepalive query on the *current* app context's session.

    Must be called from within the same outer app context that _job_runner_lock opened
    (i.e. not from inside one of run_ai_job's nested `with app.app_context()` blocks) so
    it lands on the connection actually holding the advisory lock, not a fresh one — a
    long batch would otherwise leave that connection sitting untouched for the whole
    wait, which is the exact situation that can trip an infra-level idle timeout and
    silently drop the lock mid-job.
    """
    from app.extensions import db

    try:
        db.session.execute(text("SELECT 1"))
        db.session.commit()
    except Exception as exc:
        logger.debug("AI job lock keepalive failed: job=%s err=%s", job_id, exc)
        try:
            db.session.rollback()
        except Exception:
            pass


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


def _resolve_concurrency(job, *, config_keys: Sequence[str], default: int) -> int:
    from flask import current_app

    meta = job.meta if isinstance(job.meta, dict) else {}
    raw = meta.get("concurrency")
    if raw is None:
        for key in config_keys:
            if key and current_app.config.get(key) is not None:
                raw = current_app.config.get(key)
                break
    try:
        value = int(raw if raw is not None else default)
    except (TypeError, ValueError):
        value = int(default)
    return max(1, min(value, 4))


def _claim_job_item(item_id: int) -> bool:
    """Atomically claim a queued item before processing."""
    from app.extensions import db
    from app.models import AIJobItem

    updated = (
        db.session.query(AIJobItem)
        .filter(AIJobItem.id == int(item_id), AIJobItem.status == "queued")
        .update({"status": "processing", "error": None}, synchronize_session=False)
    )
    if updated:
        db.session.commit()
        return True
    db.session.rollback()
    return False


def _finalize_running_job(job_id: str, *, cancelled: bool) -> None:
    from app.extensions import db
    from app.models import AIJob, AIJobItem

    job = AIJob.query.get(str(job_id))
    if not job:
        return
    if job.status in _TERMINAL_JOB_STATUSES:
        return

    if cancelled or job.status == "cancel_requested" or job_cancel_requested(job_id):
        try:
            (
                db.session.query(AIJobItem)
                .filter(AIJobItem.job_id == str(job_id), AIJobItem.status == "queued")
                .update({"status": "cancelled", "error": None}, synchronize_session=False)
            )
            db.session.commit()
        except Exception as exc:
            logger.debug("AI job cancel item update failed: job=%s err=%s", job_id, exc)
            db.session.rollback()
        job.status = "cancelled"
    else:
        items = job.items or []
        terminal = set(_TERMINAL_ITEM_STATUSES)
        all_terminal = all((it.status in terminal) for it in items)
        # NOTE: all_terminal only means every item *reached* a final state — it says
        # nothing about which one. Must check for "failed" explicitly, or a batch where
        # every single item failed would still get reported to the user as "completed".
        if not all_terminal:
            job.status = "failed"
            job.error = job.error or "Processing did not finish for all items (worker stopped unexpectedly)."
        elif any(_status_str(it.status) == "failed" for it in items):
            job.status = "failed"
            job.error = job.error or "One or more items failed."
        else:
            job.status = "completed"

    job.finished_at = utcnow()
    db.session.commit()
    logger.info("AI job finished: job=%s status=%s", job_id, job.status)


def run_ai_job(
    app,
    job_id: str,
    item_processor: Callable,
    *,
    concurrency_config_keys: Sequence[str] = ("AI_DOCS_REPROCESS_CONCURRENCY",),
    default_concurrency: int = 1,
    stagger_seconds: float = 0,
) -> None:
    """
    Generic background runner for AI document batch jobs.

    *item_processor* signature: ``(app, *, job_id: str, item_id: int) -> None``
    """
    job_id = str(job_id)
    with _job_runner_lock(app, job_id) as acquired:
        if not acquired:
            return

        with app.app_context():
            from app.extensions import db
            from app.models import AIJob

            job = AIJob.query.get(job_id)
            if not job:
                return
            if job.status in _TERMINAL_JOB_STATUSES:
                return
            job.status = "running"
            job.started_at = job.started_at or utcnow()
            db.session.commit()
            concurrency = _resolve_concurrency(
                job,
                config_keys=concurrency_config_keys,
                default=default_concurrency,
            )

        try:
            while not job_cancel_requested(job_id):
                with app.app_context():
                    from app.models import AIJob

                    job = AIJob.query.get(job_id)
                    if not job or job.status in _TERMINAL_JOB_STATUSES:
                        break
                    queued_ids = [
                        int(it.id)
                        for it in (job.items or [])
                        if _status_str(it.status) == "queued"
                    ]

                if not queued_ids:
                    break

                # Claim at most *concurrency* items per batch. _claim_job_item flips status to
                # "processing" immediately, so claiming the entire queue in one go makes every
                # row look in-flight in the UI even though the pool only runs concurrency workers.
                batch_ids = queued_ids[:concurrency]

                with ThreadPoolExecutor(max_workers=concurrency) as pool:
                    futures = []
                    for item_id in batch_ids:
                        if job_cancel_requested(job_id):
                            break
                        if not _claim_job_item(item_id):
                            continue
                        futures.append(
                            pool.submit(item_processor, app, job_id=job_id, item_id=int(item_id))
                        )
                        if stagger_seconds > 0:
                            time.sleep(stagger_seconds)

                    # Wait for the batch in slices (instead of a plain as_completed/pool-exit
                    # block) so we can ping the lock-holding connection periodically — see
                    # _touch_lock_connection.
                    pending = set(futures)
                    while pending:
                        _done, pending = wait_futures(pending, timeout=_LOCK_KEEPALIVE_SECONDS)
                        if pending:
                            _touch_lock_connection(job_id)

            _finalize_running_job(job_id, cancelled=job_cancel_requested(job_id))
        except Exception as exc:
            logger.error("AI job failed: job=%s err=%s", job_id, exc, exc_info=True)
            with app.app_context():
                from app.extensions import db
                from app.models import AIJob

                job = AIJob.query.get(job_id)
                if job and job.status not in _TERMINAL_JOB_STATUSES:
                    job.status = "failed"
                    job.error = job.error or "Processing failed."
                    job.finished_at = utcnow()
                    db.session.commit()
        finally:
            clear_job_cancel_event(job_id)


def cleanup_expired_ai_document_jobs(now_ts: Optional[float] = None) -> None:
    """Delete finished AI document jobs older than TTL."""
    if now_ts is None:
        now_ts = time.time()
    cutoff = datetime.fromtimestamp(now_ts - AI_DOCUMENTS_JOB_TTL_SECONDS, tz=timezone.utc).replace(tzinfo=None)
    try:
        with _isolated_job_session() as session:
            from app.models import AIJob

            expired = (
                session.query(AIJob)
                .filter(
                    AIJob.job_type.in_(tuple(AI_DOCUMENTS_JOB_TYPES)),
                    AIJob.status.in_(tuple(_TERMINAL_JOB_STATUSES)),
                    AIJob.created_at < cutoff,
                )
                .all()
            )
            for job in expired:
                session.delete(job)
            if expired:
                logger.info("Cleaned up %s expired AI document jobs", len(expired))
    except Exception:
        logger.exception("Failed to clean up expired AI document jobs")


def _maybe_cleanup_expired_jobs() -> None:
    global _last_cleanup_ts
    now = time.time()
    with _last_cleanup_lock:
        if now - _last_cleanup_ts < 300:
            return
        _last_cleanup_ts = now
    cleanup_expired_ai_document_jobs(now)


def _latest_item_activity(job) -> Optional[object]:
    latest = ensure_utc(job.started_at or job.created_at)
    for item in job.items or []:
        touched = ensure_utc(item.updated_at or item.created_at)
        if touched and (latest is None or touched > latest):
            latest = touched
    return latest


def _latest_job_activity(job) -> Optional[object]:
    """Latest activity timestamp for stale detection (items + import meta heartbeat)."""
    latest = ensure_utc(_latest_item_activity(job))
    if getattr(job, "job_type", None) in IMPORT_JOB_TYPES:
        meta = job.meta if isinstance(job.meta, dict) else {}
        updated_ts = meta.get("updated_ts")
        if updated_ts is not None:
            try:
                meta_dt = datetime.fromtimestamp(float(updated_ts), tz=timezone.utc)
                if latest is None or meta_dt > latest:
                    latest = meta_dt
            except (TypeError, ValueError, OSError):
                pass
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

    stale_seconds = _stale_seconds_for_job(job)
    cutoff = utcnow() - timedelta(seconds=stale_seconds)
    changed = False
    for item in job.items or []:
        if item.status not in ("downloading", "processing"):
            continue
        touched = ensure_utc(item.updated_at or item.created_at)
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

    stale_seconds = _stale_seconds_for_job(job)
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

    last_activity = ensure_utc(_latest_job_activity(job) or job.created_at)
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
    _maybe_cleanup_expired_jobs()
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
