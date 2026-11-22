"""Manual GO sync as a background job the settings page can poll."""

from __future__ import annotations

import logging
import time
import uuid

from sqlalchemy.orm.attributes import flag_modified

from app.extensions import db
from app.models import AIJob, AIJobItem
from app.services.ai import ai_job_runner
from app.utils.common.datetime_helpers import utcnow
from plugins.dref_monitoring.i18n import translate
from plugins.dref_monitoring.models import DrefSyncLog
from plugins.dref_monitoring.services.go_sync import (
    GoSyncBusy,
    GoSyncCancelled,
    go_sync_lock_held,
    isolated_session,
)

logger = logging.getLogger(__name__)

JOB_TYPE = "dref.go_sync"
_ACTIVE = ("queued", "running", "cancel_requested")
_TERMINAL = {"completed", "failed", "cancelled"}
_FAILURE = "GO sync failed. The public dref3 service did not return data."
_STATUS_LABELS = {
    "queued": "Running",
    "running": "Running",
    "cancel_requested": "Running",
    "completed": "Succeeded",
    "failed": "Failed",
    "cancelled": "Cancelled",
}
_write_state: dict[str, dict] = {}


def _status_str(value) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value or "")


def active_go_sync_job() -> AIJob | None:
    """Oldest sync that has not finished. One sync runs at a time."""
    return (
        AIJob.query.filter(AIJob.job_type == JOB_TYPE, AIJob.status.in_(_ACTIVE))
        .order_by(AIJob.created_at.asc(), AIJob.id.asc())
        .first()
    )


def status_payload(job: AIJob) -> dict:
    meta = dict(job.meta or {})
    raw_vars = meta.get("message_vars") if isinstance(meta.get("message_vars"), dict) else {}
    variables = {str(key): value for key, value in raw_vars.items() if isinstance(value, (int, float, str))}
    status = _status_str(job.status)
    error = str(job.error or "")
    summary = meta.get("summary") if isinstance(meta.get("summary"), dict) else None
    total = meta.get("total")
    try:
        percent = float(meta.get("percent") or 0.0)
    except (TypeError, ValueError):
        percent = 0.0
    try:
        current = int(meta.get("current") or 0)
    except (TypeError, ValueError):
        current = 0
    payload = {
        "job_id": str(job.id),
        "status": status,
        "status_label": translate(_STATUS_LABELS.get(status, status)),
        "stage": str(meta.get("stage") or ""),
        "message": translate(str(meta.get("message") or ""), **variables),
        "current": current,
        "total": total,
        "percent": max(0.0, min(100.0, percent)),
        "summary": summary,
        "error": translate(error) if error else None,
    }
    # Drafting jobs add the chapter being written, so a page can show the text as it forms.
    if isinstance(meta.get("live"), dict) and status not in _TERMINAL:
        payload["live"] = meta["live"]
    return payload


def _expire_job(job_id: str) -> None:
    job = db.session.get(AIJob, str(job_id))
    if job is not None:
        db.session.expire(job)


def _write_progress(job_id: str, payload: dict, *, force: bool = False) -> None:
    """Store stage, percent, and message where the status poll can read them."""
    status = payload.get("status")
    terminal = str(status or "") in _TERMINAL
    now = time.time()
    state = _write_state.setdefault(str(job_id), {})
    if not force and not terminal:
        try:
            percent = float(payload.get("percent") or 0.0)
        except (TypeError, ValueError):
            percent = 0.0
        previous = float(state.get("percent") or 0.0)
        same_stage = state.get("stage") == payload.get("stage")
        if same_stage and now - float(state.get("ts") or 0.0) < 1.0 and abs(percent - previous) < 2:
            return
    state["ts"] = now
    state["stage"] = payload.get("stage")
    state["percent"] = payload.get("percent")
    try:
        with isolated_session() as session:
            job = session.get(AIJob, str(job_id))
            if job is None:
                return
            meta = dict(job.meta or {})
            for key in ("stage", "message", "message_vars", "current", "total", "percent", "summary", "live"):
                if key not in payload or payload[key] is None:
                    continue
                meta[key] = payload[key]
            meta["updated_ts"] = now
            job.meta = meta
            flag_modified(job, "meta")
            if status:
                job.status = str(status)
                if terminal and job.finished_at is None:
                    job.finished_at = utcnow()
            if payload.get("error"):
                job.error = str(payload["error"])[:2000]
            item = session.query(AIJobItem).filter_by(job_id=str(job_id)).first()
            if item is not None:
                item.updated_at = utcnow()
    except Exception:
        logger.exception("DREF GO sync progress update failed for %s", job_id)
    if terminal:
        _write_state.pop(str(job_id), None)


def _mark_item(item_id: int, status: str, error: str | None) -> None:
    item = db.session.get(AIJobItem, int(item_id))
    if item is None:
        return
    item.status = status
    item.error = error
    db.session.commit()


def _process_go_sync_item(app, *, job_id: str, item_id: int) -> None:
    with app.app_context():
        _expire_job(job_id)
        if ai_job_runner.job_cancel_requested(job_id):
            _mark_item(item_id, "cancelled", None)
            _write_progress(
                job_id,
                {
                    "status": "cancelled",
                    "stage": "cancelled",
                    "message": "GO sync was cancelled.",
                },
                force=True,
            )
            _expire_job(job_id)
            return

        from plugins.dref_monitoring.services.go_sync import completion_progress, sync_from_go

        def progress(payload: dict) -> None:
            _write_progress(job_id, payload)

        checked = {"at": 0.0, "stop": False}

        def should_stop() -> bool:
            if checked["stop"]:
                return True
            now = time.time()
            if now - checked["at"] < 1.0:
                return False
            checked["at"] = now
            checked["stop"] = bool(ai_job_runner.job_cancel_requested(job_id))
            return checked["stop"]

        try:
            summary = sync_from_go(progress=progress, should_stop=should_stop)
            _mark_item(item_id, "completed", None)
            finished = completion_progress(summary)
            _write_progress(
                job_id,
                {
                    "status": "completed",
                    "stage": "completed",
                    "message": finished["message"],
                    "message_vars": finished["message_vars"],
                    "current": int(summary.get("appeals") or 0),
                    "total": int(summary.get("appeals") or 0),
                    "percent": 100.0,
                    "summary": {
                        "created": int(summary.get("created") or 0),
                        "updated": int(summary.get("updated") or 0),
                        "unchanged": int(summary.get("unchanged") or 0),
                        "removed": int(summary.get("removed") or 0),
                        "appeals": int(summary.get("appeals") or 0),
                    },
                },
                force=True,
            )
        except GoSyncCancelled:
            _mark_item(item_id, "cancelled", None)
            _write_progress(
                job_id,
                {
                    "status": "cancelled",
                    "stage": "cancelled",
                    "message": "GO sync was cancelled.",
                },
                force=True,
            )
        except GoSyncBusy:
            logger.info("DREF GO sync %s skipped; another sync is running.", job_id)
            _mark_item(item_id, "failed", "A GO sync is already running.")
            _write_progress(
                job_id,
                {
                    "status": "failed",
                    "stage": "failed",
                    "message": "A GO sync is already running.",
                    "error": "A GO sync is already running.",
                    "percent": 0,
                },
                force=True,
            )
        except Exception:
            logger.exception("DREF GO sync %s failed", job_id)
            _mark_item(item_id, "failed", _FAILURE)
            _write_progress(
                job_id,
                {
                    "status": "failed",
                    "stage": "failed",
                    "message": _FAILURE,
                    "error": _FAILURE,
                    "percent": 0,
                },
                force=True,
            )
        finally:
            _expire_job(job_id)


def _run_go_sync_job(app, job_id: str) -> None:
    ai_job_runner.run_ai_job(
        app,
        str(job_id),
        _process_go_sync_item,
        default_concurrency=1,
    )


def ensure_go_sync_job_running(app, job_id: str) -> None:
    ai_job_runner.ensure_ai_job_running(app, str(job_id), _run_go_sync_job)


def queue_go_sync(user_id: int, app) -> tuple[str, bool]:
    """Start a sync, or return the one already queued or running. ``created`` is false on reuse."""
    existing = active_go_sync_job()
    if existing is not None:
        ensure_go_sync_job_running(app, str(existing.id))
        return str(existing.id), False

    job_id = uuid.uuid4().hex
    now = time.time()
    job = AIJob(
        id=job_id,
        job_type=JOB_TYPE,
        user_id=int(user_id),
        status="queued",
        total_items=1,
        meta={
            "stage": "queued",
            "message": "Waiting to start the GO sync.",
            "message_vars": {},
            "current": 0,
            "total": None,
            "percent": 0.0,
            "summary": None,
            "updated_ts": now,
        },
    )
    item = AIJobItem(
        job_id=job_id,
        item_index=0,
        entity_type="dref_go_sync",
        status="queued",
        payload={},
    )
    db.session.add(job)
    db.session.add(item)
    db.session.commit()

    winner = active_go_sync_job()
    if winner is not None and str(winner.id) != job_id:
        _cancel_unstarted(job_id)
        ensure_go_sync_job_running(app, str(winner.id))
        return str(winner.id), False

    ai_job_runner.start_ai_job_thread(app, job_id, _run_go_sync_job)
    return job_id, True


def _cancel_unstarted(job_id: str) -> None:
    """Drop a job that lost the race before its thread started."""
    job = db.session.get(AIJob, str(job_id))
    if job is None or _status_str(job.status) in _TERMINAL:
        return
    job.status = "cancelled"
    job.finished_at = utcnow()
    (
        db.session.query(AIJobItem)
        .filter(AIJobItem.job_id == str(job_id), AIJobItem.status.in_(("queued", "processing")))
        .update({"status": "cancelled", "error": None}, synchronize_session=False)
    )
    db.session.commit()


def request_go_sync_cancel(job_id: str) -> str:
    job = db.session.get(AIJob, str(job_id))
    if job is None or str(job.job_type) != JOB_TYPE:
        return "missing"
    status = _status_str(job.status)
    if status in _TERMINAL:
        return status
    job.status = "cancel_requested"
    try:
        (
            db.session.query(AIJobItem)
            .filter(AIJobItem.job_id == str(job_id), AIJobItem.status == "queued")
            .update({"status": "cancelled", "error": None}, synchronize_session=False)
        )
    except Exception:
        logger.debug("DREF GO sync cancel could not update queued items", exc_info=True)
        db.session.rollback()
        job = db.session.get(AIJob, str(job_id))
        if job is None:
            return "missing"
        job.status = "cancel_requested"
    db.session.commit()
    ai_job_runner.signal_job_cancel(str(job_id))
    return "cancel_requested"


def settle_orphan_logs() -> None:
    """Close a 'running' history row when no sync is actually in progress."""
    if active_go_sync_job() is not None or go_sync_lock_held():
        return
    rows = DrefSyncLog.query.filter_by(status="running").all()
    if not rows:
        return
    now = utcnow()
    for row in rows:
        row.status = "error"
        row.finished_at = now
        row.message = "The background worker stopped responding (likely after an app restart). Re-run the job."
    db.session.commit()


def prepare_settings_sync(app) -> dict | None:
    """Resume an orphaned runner, then return the live job for the page."""
    current = active_go_sync_job()
    if current is not None:
        ensure_go_sync_job_running(app, str(current.id))
    settle_orphan_logs()
    current = active_go_sync_job()
    if current is None:
        return None
    return status_payload(current)
