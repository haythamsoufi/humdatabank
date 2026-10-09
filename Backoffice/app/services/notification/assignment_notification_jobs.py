"""
Background job tracking for assignment-created notifications.

Sending notifications (in-app + one grouped email per entity) for a large assignment
takes minutes, so it runs outside the request. This module makes that work *observable*:

* One ``AIJob`` row (type ``assignments.notify_created``) per dispatch, one ``AIJobItem``
  per assignment/entity. Rows are created inside the request transaction, so they exist
  if and only if the assignment was saved.
* The generic runner (``run_ai_job``) gives cross-worker locking, atomic item claims,
  cooperative cancel, and stale-worker recovery (see
  ``Backoffice/docs/architecture/background-jobs-and-progress-ui.md``).
* Every entity ends ``completed`` or ``failed`` with a user-readable reason. An email the
  mail service rejected counts as a failure (it used to be logged and forgotten), and an
  entity with nobody to notify is reported as such instead of looking like a success.
* The Communication Center "Background jobs" tab and banner read it via
  ``/admin/api/communications/background-jobs``.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import timedelta
from typing import Any, Dict, Iterable, List, Optional

from flask import current_app

from app.extensions import db
from app.utils.datetime_helpers import ensure_utc, utcnow

logger = logging.getLogger(__name__)

JOB_TYPE = "assignments.notify_created"
ITEM_ENTITY_TYPE = "assignment_entity_status"
RETENTION_DAYS = 30
RECENT_FAILURE_WINDOW_HOURS = 48
RESUME_MIN_AGE_SECONDS = 30

ACTIVE_STATUSES = ("queued", "running", "cancel_requested")
_ACTIVE_ITEM_STATUSES = ("queued", "downloading", "processing")
_MAX_ERROR_LENGTH = 600

_last_cleanup_ts = 0.0

# The runner's generic wording refers to "re-running", which is not an option here.
_RUNNER_STALE_ERRORS = (
    "Processing interrupted (worker stopped).",
    "Processing stalled (no progress).",
    "The background worker stopped responding",
    "Processing did not finish for all items",
)
_INTERRUPTED_MESSAGE = (
    "The background worker stopped before this entity was processed (usually an app "
    "restart). Some notifications for it may not have been sent."
)


def _status_str(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value or "")


def _short(text: Any) -> str:
    value = str(text or "").strip()
    if len(value) > _MAX_ERROR_LENGTH:
        return value[: _MAX_ERROR_LENGTH - 1] + "…"
    return value


def _iso(value) -> Optional[str]:
    value = ensure_utc(value) if value else None
    return value.isoformat() if value else None


# ---------------------------------------------------------------------------
# Creating a job (request thread)
# ---------------------------------------------------------------------------


def create_assignment_notification_job(
    aes_ids: Iterable[int],
    notify_admins: bool,
    actor_user_id: Optional[int],
    *,
    source: str = "create",
) -> Optional[str]:
    """
    Queue a notification job for the given AssignmentEntityStatus ids.

    Must be called inside the request transaction, after the AES rows were flushed. Returns
    the job id, or ``None`` when the job could not be created (the caller must tell the user;
    the assignment itself is unaffected thanks to the savepoint).
    """
    from app.models import AIJob, AIJobItem
    from app.models.assignments import AssignmentEntityStatus

    ids = sorted({int(i) for i in (aes_ids or []) if i})
    if not ids:
        return None
    if not actor_user_id:
        logger.error("Cannot queue assignment notification job without an acting user")
        return None

    try:
        with db.session.begin_nested():
            rows = (
                AssignmentEntityStatus.query.filter(AssignmentEntityStatus.id.in_(ids))
                .order_by(AssignmentEntityStatus.id.asc())
                .all()
            )
            if not rows:
                return None
            assigned_form = rows[0].assigned_form
            label = None
            try:
                label = assigned_form.display_name if assigned_form else None
            except Exception:
                label = None

            job = AIJob(
                id=str(uuid.uuid4()),
                job_type=JOB_TYPE,
                user_id=int(actor_user_id),
                status="queued",
                total_items=len(rows),
                meta={
                    "notify_admins": bool(notify_admins),
                    "assigned_form_id": rows[0].assigned_form_id,
                    "assignment_label": label or "",
                    "source": source,
                },
            )
            db.session.add(job)
            db.session.flush()
            for index, aes in enumerate(rows):
                db.session.add(
                    AIJobItem(
                        job_id=job.id,
                        item_index=index,
                        entity_type=ITEM_ENTITY_TYPE,
                        entity_id=aes.id,
                        status="queued",
                        payload={"entity_type": aes.entity_type, "entity_id": aes.entity_id},
                    )
                )
            db.session.flush()
            return job.id
    except Exception:
        logger.exception("Failed to queue assignment notification job")
        return None


# ---------------------------------------------------------------------------
# Running a job (background thread)
# ---------------------------------------------------------------------------


def start_assignment_notification_job(job_id: str) -> None:
    """
    Start the worker for *job_id*. Register via ``register_post_commit`` so the job rows are
    committed (and visible to the worker's own session) first. Runs inline under TESTING.
    """
    from app.services.ai.ai_job_runner import start_ai_job_thread

    app = current_app._get_current_object()
    if app.config.get("TESTING"):
        run_assignment_notification_job(app, job_id)
        return
    try:
        start_ai_job_thread(app, job_id, run_assignment_notification_job)
    except Exception as exc:
        logger.error("Could not start assignment notification worker for job %s: %s", job_id, exc, exc_info=True)
        mark_job_failed(job_id, f"Could not start the background worker: {exc}")


def run_assignment_notification_job(app, job_id: str) -> None:
    """Blocking worker body (runs inside the background thread)."""
    from app.services.ai.ai_job_runner import run_ai_job

    run_ai_job(
        app,
        str(job_id),
        _process_item,
        concurrency_config_keys=("ASSIGNMENT_NOTIFY_CONCURRENCY",),
        default_concurrency=1,
    )


def mark_job_failed(job_id: str, error: str) -> None:
    """Fail a job (and every unfinished item) using an isolated session."""
    from app.models import AIJob
    from app.services.ai.ai_job_runner import _isolated_job_session

    try:
        with _isolated_job_session() as session:
            job = session.get(AIJob, str(job_id))
            if not job or _status_str(job.status) in ("completed", "failed", "cancelled"):
                return
            for item in job.items or []:
                if _status_str(item.status) in _ACTIVE_ITEM_STATUSES:
                    item.status = "failed"
                    item.error = _short(error)
            job.status = "failed"
            job.error = _short(error)
            job.finished_at = utcnow()
    except Exception:
        logger.exception("Could not mark assignment notification job %s as failed", job_id)


def _process_item(app, *, job_id: str, item_id: int) -> None:
    """Runner callback: notify one entity. Never raises; failures are recorded on the item."""
    try:
        with app.app_context():
            # url_for() needs a request. Worker threads have none and SERVER_NAME is unset,
            # so build one from BASE_URL (otherwise every entity fails before sending anything).
            base_url = (app.config.get("BASE_URL") or "http://127.0.0.1:5000").rstrip("/")
            with app.test_request_context(base_url=base_url):
                _notify_one_entity(job_id, item_id)
    except Exception as exc:  # defensive: context setup failed
        logger.error("Assignment notification item %s crashed: %s", item_id, exc, exc_info=True)
        _finish_item(item_id, "failed", error=_short(f"Unexpected error: {exc}"))


def _notify_one_entity(job_id: str, item_id: int) -> None:
    from app.models import AIJob, AIJobItem
    from app.models.assignments import AssignmentEntityStatus
    from app.services.ai.ai_job_runner import job_cancel_requested
    from app.services.notification.core import notify_assignment_created
    from app.services.organization.entity_service import EntityService

    item = AIJobItem.query.get(item_id)
    job = AIJob.query.get(str(job_id))
    if not item or not job:
        return
    if job_cancel_requested(job_id):
        _finish_item(item_id, "cancelled")
        return

    meta = job.meta if isinstance(job.meta, dict) else {}
    payload = dict(item.payload or {})
    actor_user_id = job.user_id
    notify_admins = bool(meta.get("notify_admins"))
    aes_id = item.entity_id
    outcome: Dict[str, Any] = {}

    try:
        aes = AssignmentEntityStatus.query.get(aes_id) if aes_id else None
        if aes is None:
            _finish_item(
                item_id,
                "completed",
                payload=dict(payload, result={
                    "notifications": 0,
                    "email_status": "skipped",
                    "email_detail": "The entity was removed from the assignment before it was processed.",
                }),
            )
            return
        payload["entity_name"] = EntityService.get_entity_name(
            aes.entity_type, aes.entity_id, include_hierarchy=False
        )
        results = notify_assignment_created(
            aes, notify_admins=notify_admins, actor_user_id=actor_user_id, outcome=outcome
        ) or []
    except Exception as exc:
        db.session.rollback()
        logger.error(
            "Assignment notification failed for AES %s (job %s): %s", aes_id, job_id, exc, exc_info=True
        )
        _finish_item(item_id, "failed", error=_short(f"{type(exc).__name__}: {exc}"), payload=payload)
        return

    result = {
        "notifications": len(results),
        "email_status": outcome.get("email_status") or "skipped",
        "email_detail": _short(outcome.get("email_detail")),
    }
    payload["result"] = result
    if result["email_status"] == "failed":
        _finish_item(
            item_id,
            "failed",
            error=_short(
                f"Email was not delivered: {result['email_detail'] or 'unknown reason'} "
                f"({result['notifications']} in-app notification(s) were created.)"
            ),
            payload=payload,
        )
    else:
        _finish_item(item_id, "completed", payload=payload)


def _finish_item(item_id: int, status: str, *, error: Optional[str] = None, payload: Optional[dict] = None) -> None:
    from app.models import AIJobItem

    try:
        db.session.rollback()
        item = AIJobItem.query.get(item_id)
        if not item:
            return
        item.status = status
        item.error = error
        if payload is not None:
            item.payload = payload
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Could not record result for assignment notification item %s", item_id)


# ---------------------------------------------------------------------------
# Reading / managing jobs (Communication Center)
# ---------------------------------------------------------------------------


def _friendly_error(error: Optional[str]) -> Optional[str]:
    if not error:
        return None
    if any(error.startswith(prefix) for prefix in _RUNNER_STALE_ERRORS):
        return _INTERRUPTED_MESSAGE
    return error


def _item_result(item) -> Dict[str, Any]:
    payload = item.payload if isinstance(item.payload, dict) else {}
    result = payload.get("result")
    return result if isinstance(result, dict) else {}


def _entity_label(item, cache: Dict[Any, str]) -> str:
    payload = item.payload if isinstance(item.payload, dict) else {}
    name = payload.get("entity_name")
    if name:
        return str(name)
    key = (payload.get("entity_type"), payload.get("entity_id"))
    if key in cache:
        return cache[key]
    label = ""
    if key[0] and key[1]:
        try:
            from app.services.organization.entity_service import EntityService

            label = EntityService.get_entity_name(key[0], key[1], include_hierarchy=False) or ""
        except Exception:
            label = ""
    label = label or f"Assignment entity #{item.entity_id}"
    cache[key] = label
    return label


def serialize_job(job, *, include_items: bool = False) -> Dict[str, Any]:
    items = list(job.items or [])
    statuses = [_status_str(it.status) for it in items]
    job_failed = _status_str(job.status) == "failed"
    # A failed job is finished: an item still queued/processing will never run (its worker died).
    # Report it as an interrupted failure rather than as perpetual progress.
    interrupted = {
        it.id for it, st in zip(items, statuses) if job_failed and st in _ACTIVE_ITEM_STATUSES
    }
    statuses = ["failed" if it.id in interrupted else st for it, st in zip(items, statuses)]
    completed = statuses.count("completed")
    failed = statuses.count("failed")
    cancelled = statuses.count("cancelled")
    in_progress = sum(1 for s in statuses if s in ("downloading", "processing"))
    queued = statuses.count("queued")
    total = int(job.total_items or len(items))
    processed = completed + failed + cancelled

    notified = 0
    no_recipients = 0
    emails_sent = 0
    for it, status in zip(items, statuses):
        if status != "completed":
            continue
        result = _item_result(it)
        if result.get("email_status") == "sent":
            emails_sent += 1
        if int(result.get("notifications") or 0) > 0 or result.get("email_status") == "sent":
            notified += 1
        else:
            no_recipients += 1

    status = _status_str(job.status)
    meta = job.meta if isinstance(job.meta, dict) else {}
    error = _friendly_error(job.error)
    if status == "failed" and (not error or error == "One or more items failed."):
        error = f"{failed} of {total} entities could not be fully notified." if failed else (error or "Failed.")

    names: Dict[Any, str] = {}
    failures = [
        {
            "item_id": it.id,
            "entity": _entity_label(it, names),
            "error": (_INTERRUPTED_MESSAGE if it.id in interrupted else _friendly_error(it.error)) or "",
        }
        for it, st in zip(items, statuses)
        if st == "failed"
    ]

    data: Dict[str, Any] = {
        "job_id": str(job.id),
        "status": status,
        "is_active": status in ACTIVE_STATUSES,
        "assignment_label": meta.get("assignment_label") or "",
        "assigned_form_id": meta.get("assigned_form_id"),
        "notify_admins": bool(meta.get("notify_admins")),
        "source": meta.get("source") or "create",
        "created_by": getattr(getattr(job, "user", None), "name", None) or "",
        "created_at": _iso(job.created_at),
        "started_at": _iso(job.started_at),
        "finished_at": _iso(job.finished_at),
        "error": error,
        "dismissed": bool(meta.get("dismissed")),
        "counts": {
            "total": total,
            "processed": processed,
            "completed": completed,
            "failed": failed,
            "cancelled": cancelled,
            "in_progress": in_progress,
            "queued": queued,
            "notified": notified,
            "no_recipients": no_recipients,
            "emails_sent": emails_sent,
        },
        "percent": round(100.0 * processed / total, 1) if total else 100.0,
        "failures": failures[:50],
        "failures_truncated": len(failures) > 50,
    }
    if include_items:
        data["items"] = [
            {
                "item_id": it.id,
                "index": it.item_index,
                "entity": _entity_label(it, names),
                "status": st,
                "error": (_INTERRUPTED_MESSAGE if it.id in interrupted else _friendly_error(it.error)) or "",
                "notifications": int(_item_result(it).get("notifications") or 0),
                "email_status": _item_result(it).get("email_status") or "",
                "email_detail": _item_result(it).get("email_detail") or "",
                "updated_at": _iso(it.updated_at),
            }
            for it, st in zip(items, statuses)
        ]
    return data


def resume_orphaned_jobs(app) -> None:
    """
    Reconcile stale state and restart workers for jobs whose worker died (app restart/crash).
    Safe to call often: the runner's advisory lock prevents duplicate runners.
    """
    from app.models import AIJob
    from app.services.ai.ai_job_runner import ensure_ai_job_running

    cutoff = utcnow() - timedelta(seconds=RESUME_MIN_AGE_SECONDS)
    try:
        jobs = AIJob.query.filter(
            AIJob.job_type == JOB_TYPE,
            AIJob.status.in_(ACTIVE_STATUSES),
            AIJob.created_at < cutoff,
        ).all()
        for job in jobs:
            try:
                ensure_ai_job_running(app, str(job.id), run_assignment_notification_job)
            except Exception:
                db.session.rollback()
                logger.exception("Could not reconcile assignment notification job %s", job.id)
    except Exception:
        db.session.rollback()
        logger.exception("Could not resume assignment notification jobs")


def list_jobs(limit: int = 20) -> List[Dict[str, Any]]:
    from app.models import AIJob

    _maybe_cleanup_old_jobs()
    jobs = (
        AIJob.query.filter(AIJob.job_type == JOB_TYPE)
        .order_by(AIJob.created_at.desc())
        .limit(max(1, min(int(limit), 100)))
        .all()
    )
    return [serialize_job(job) for job in jobs]


def get_job(job_id: str):
    from app.models import AIJob

    job = AIJob.query.get(str(job_id))
    if job is None or job.job_type != JOB_TYPE:
        return None
    return job


def get_banner_summary() -> Dict[str, int]:
    """Cheap counts for the page render: running jobs and recent un-dismissed failures."""
    from app.models import AIJob

    active = AIJob.query.filter(AIJob.job_type == JOB_TYPE, AIJob.status.in_(ACTIVE_STATUSES)).count()
    cutoff = utcnow() - timedelta(hours=RECENT_FAILURE_WINDOW_HOURS)
    recent = (
        AIJob.query.filter(
            AIJob.job_type == JOB_TYPE,
            AIJob.status == "failed",
            AIJob.created_at >= cutoff,
        ).all()
    )
    failed = sum(1 for j in recent if not (isinstance(j.meta, dict) and j.meta.get("dismissed")))
    return {"active": active, "failed": failed}


def request_cancel(job_id: str) -> bool:
    """Ask a running job to stop before the remaining entities are notified."""
    from app.models import AIJob, AIJobItem
    from app.services.ai.ai_job_runner import signal_job_cancel

    job = get_job(job_id)
    if job is None or _status_str(job.status) not in ("queued", "running"):
        return False
    job.status = "cancel_requested"
    db.session.commit()
    signal_job_cancel(str(job_id))
    # No live runner (e.g. the worker died): finish the cancellation right away.
    from app.services.ai.ai_job_runner import is_job_thread_alive

    if not is_job_thread_alive(str(job_id)):
        db.session.query(AIJobItem).filter(
            AIJobItem.job_id == str(job_id), AIJobItem.status == "queued"
        ).update({"status": "cancelled"}, synchronize_session=False)
        job = AIJob.query.get(str(job_id))
        if job and _status_str(job.status) == "cancel_requested":
            job.status = "cancelled"
            job.finished_at = utcnow()
        db.session.commit()
    return True


def dismiss_job(job_id: str) -> bool:
    """Hide a finished job's failure from the banner (it stays in the job list)."""
    from sqlalchemy.orm.attributes import flag_modified

    job = get_job(job_id)
    if job is None or _status_str(job.status) in ACTIVE_STATUSES:
        return False
    meta = dict(job.meta or {})
    meta["dismissed"] = True
    job.meta = meta
    flag_modified(job, "meta")
    db.session.commit()
    return True


def _maybe_cleanup_old_jobs() -> None:
    """Delete finished jobs past the retention window (throttled; best effort)."""
    global _last_cleanup_ts
    now = time.time()
    if now - _last_cleanup_ts < 3600:
        return
    _last_cleanup_ts = now
    from app.models import AIJob
    from app.services.ai.ai_job_runner import _isolated_job_session

    cutoff = utcnow() - timedelta(days=RETENTION_DAYS)
    try:
        with _isolated_job_session() as session:
            for job in (
                session.query(AIJob)
                .filter(
                    AIJob.job_type == JOB_TYPE,
                    AIJob.status.in_(("completed", "failed", "cancelled")),
                    AIJob.created_at < cutoff,
                )
                .all()
            ):
                session.delete(job)
    except Exception:
        logger.exception("Could not clean up old assignment notification jobs")
