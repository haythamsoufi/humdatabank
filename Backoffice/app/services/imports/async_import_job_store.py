"""Cross-worker async import job state (PostgreSQL via AIJob).

In-memory job dicts are not visible across Gunicorn/uWSGI workers on Azure App
Service. Long-running FDRS / UPR imports store progress here so status polling
works from any worker.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import contextmanager, suppress
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Optional

from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from app.extensions import db
from app.models import AIJob
from app.utils.datetime_helpers import utcnow

logger = logging.getLogger(__name__)

FDRS_DATA_SYNC_JOB_TYPE = "fdrs.data_sync"
UPR_EXCEL_IMPORT_JOB_TYPE = "upr.excel_import"
IMPORT_JOB_TYPES = frozenset({FDRS_DATA_SYNC_JOB_TYPE, UPR_EXCEL_IMPORT_JOB_TYPE})
IMPORT_JOB_TTL_SECONDS = 6 * 60 * 60
_PERSIST_MIN_INTERVAL = 0.5
_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})

_persist_lock = threading.Lock()
_last_persist_ts: Dict[str, float] = {}
_logging_state: Dict[str, Dict[str, Any]] = {}


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status_str(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value or "")


@contextmanager
def _isolated_job_session() -> Iterator[Session]:
    """Session scoped to AIJob persistence, isolated from the request/import session.

    Long-running imports keep uncommitted FormData rows on ``db.session``. Progress
    polling and cancel checks must not query or commit through that session or
    SQLAlchemy autoflush will flush partial import batches prematurely.
    """
    session = sessionmaker(bind=db.engine)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def job_record_to_dict(job: AIJob) -> Dict[str, Any]:
    meta = dict(job.meta or {})
    return {
        "job_id": job.id,
        "kind": meta.get("kind"),
        "template_id": meta.get("template_id"),
        "user_id": int(job.user_id or 0),
        "status": _status_str(job.status),
        "stage": meta.get("stage") or "",
        "message": meta.get("message") or "",
        "current": meta.get("current", 0),
        "total": meta.get("total"),
        "percent": float(meta.get("percent") or 0.0),
        "stats": meta.get("stats"),
        "error": job.error or meta.get("error"),
        "preview_path": meta.get("preview_path"),
        "download_ready": bool(meta.get("download_ready")),
        "started_at": meta.get("started_at")
        or (job.started_at.isoformat() if job.started_at else None),
        "updated_at": meta.get("updated_at"),
        "started_ts": meta.get("started_ts"),
        "updated_ts": meta.get("updated_ts"),
        "last_logged_pct": meta.get("last_logged_pct"),
        "download_url": meta.get("download_url"),
    }


def create_import_job(
    *,
    job_id: str,
    job_type: str,
    user_id: int,
    initial: Optional[Dict[str, Any]] = None,
) -> None:
    now_ts = time.time()
    payload = dict(initial or {})
    payload.setdefault("started_at", utc_iso())
    payload.setdefault("updated_at", payload["started_at"])
    payload.setdefault("started_ts", now_ts)
    payload.setdefault("updated_ts", now_ts)

    with _isolated_job_session() as session:
        session.add(
            AIJob(
                id=str(job_id),
                job_type=str(job_type),
                user_id=int(user_id or 0),
                status="queued",
                total_items=0,
                meta=payload,
            )
        )
    _logging_state[job_id] = {}


def get_import_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _isolated_job_session() as session:
        job = session.get(AIJob, str(job_id))
        if not job or job.job_type not in IMPORT_JOB_TYPES:
            return None
        return job_record_to_dict(job)


def get_import_job_logging_state(job_id: str) -> Dict[str, Any]:
    return _logging_state.setdefault(job_id, {})


def clear_import_job_logging_state(job_id: str) -> None:
    _logging_state.pop(job_id, None)
    with _persist_lock:
        _last_persist_ts.pop(job_id, None)


def _should_persist(job_id: str, *, force: bool, status: Optional[str]) -> bool:
    if force or status in _TERMINAL_STATUSES:
        return True
    now = time.time()
    with _persist_lock:
        last = _last_persist_ts.get(job_id, 0.0)
        if now - last < _PERSIST_MIN_INTERVAL:
            return False
        _last_persist_ts[job_id] = now
    return True


def update_import_job(
    job_id: str,
    *,
    force: bool = False,
    **fields: Any,
) -> bool:
    """Merge fields into job meta; returns False if the job row is missing."""
    status = fields.get("status")
    if not _should_persist(job_id, force=force, status=status):
        log_state = get_import_job_logging_state(job_id)
        log_state.update({k: v for k, v in fields.items() if k == "last_logged_pct"})
        return True

    try:
        with _isolated_job_session() as session:
            job = session.get(AIJob, str(job_id))
            if not job:
                return False

            meta = dict(job.meta or {})
            meta_keys = (
                "kind",
                "template_id",
                "stage",
                "message",
                "current",
                "total",
                "percent",
                "stats",
                "preview_path",
                "download_ready",
                "last_logged_pct",
                "download_url",
                "started_at",
                "started_ts",
            )
            for key in meta_keys:
                if key not in fields:
                    continue
                value = fields[key]
                if value is None and key not in ("preview_path", "download_url", "stats", "error"):
                    continue
                meta[key] = value

            now_ts = time.time()
            meta["updated_at"] = utc_iso()
            meta["updated_ts"] = now_ts

            if "status" in fields and fields["status"] is not None:
                job.status = str(fields["status"])
                if job.status == "running" and not job.started_at:
                    job.started_at = utcnow()
                if job.status in _TERMINAL_STATUSES:
                    job.finished_at = utcnow()

            if "error" in fields:
                job.error = fields["error"]

            job.meta = meta
            flag_modified(job, "meta")
    except Exception:
        logger.exception("Failed to persist async import job %s", job_id)
        raise
    return True


def request_import_job_cancel(job_id: str) -> bool:
    return update_import_job(job_id, force=True, status="cancel_requested", message="Cancellation requested...")


def is_import_job_cancel_requested(job_id: str) -> bool:
    with _isolated_job_session() as session:
        job = session.get(AIJob, str(job_id))
        if not job:
            return False
        return _status_str(job.status) == "cancel_requested"


def cleanup_expired_import_jobs(now_ts: Optional[float] = None) -> None:
    """Delete finished import jobs older than TTL."""
    if now_ts is None:
        now_ts = time.time()
    cutoff = datetime.fromtimestamp(now_ts - IMPORT_JOB_TTL_SECONDS, tz=timezone.utc).replace(tzinfo=None)
    try:
        with _isolated_job_session() as session:
            expired = (
                session.query(AIJob)
                .filter(
                    AIJob.job_type.in_(tuple(IMPORT_JOB_TYPES)),
                    AIJob.status.in_(tuple(_TERMINAL_STATUSES)),
                    AIJob.created_at < cutoff,
                )
                .all()
            )
            for job in expired:
                path = (job.meta or {}).get("preview_path")
                if path and isinstance(path, str):
                    with suppress(Exception):
                        if os.path.isfile(path):
                            os.unlink(path)
                clear_import_job_logging_state(job.id)
            for job in expired:
                session.delete(job)
    except Exception:
        logger.exception("Failed to clean up expired async import jobs")
