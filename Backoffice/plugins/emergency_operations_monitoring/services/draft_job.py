"""AI drafting as a background job the report pages can poll.

A model call that writes thirteen chapters takes a minute or more, so the request that
starts it returns at once and the page polls the job for progress. Figures-only and
manual drafts take no model and stay in the request.
"""

from __future__ import annotations

import logging
import time
import uuid

from app.extensions import db
from app.models import AIJob, AIJobItem
from app.services.ai import ai_job_runner
from plugins.emergency_operations_monitoring.access import actor_for_user
from plugins.emergency_operations_monitoring.constants import NARRATIVE_AI
from plugins.emergency_operations_monitoring.models import DrefDraft, DrefOperation
from plugins.emergency_operations_monitoring.services.drafts import (
    DraftCancelled,
    generate_draft,
    include_narrative,
    regenerate_section,
)
from plugins.emergency_operations_monitoring.services.go_sync_job import (
    _expire_job,
    _mark_item,
    _status_str,
    _write_progress,
    status_payload as _job_payload,
)

logger = logging.getLogger(__name__)

JOB_TYPE = "emergency_operations.draft"
ACTION_GENERATE = "generate"
ACTION_INCLUDE = "include"
ACTION_SECTION = "section"
_ACTIVE = ("queued", "running", "cancel_requested")
_TERMINAL = {"completed", "failed", "cancelled"}
_FAILURE = "The draft could not be generated. Try again in a moment."
_CANCELLED = "Draft generation was cancelled."

__all__ = [
    "ACTION_GENERATE",
    "ACTION_INCLUDE",
    "ACTION_SECTION",
    "JOB_TYPE",
    "active_draft_job",
    "active_draft_jobs",
    "ensure_draft_job_running",
    "queue_draft_job",
    "request_draft_cancel",
    "status_payload",
]


def status_payload(job: AIJob) -> dict:
    """The job as the page polls it: progress, plus the report type and the chapter a rewrite is for."""
    body = _job_payload(job)
    meta = dict(job.meta or {})
    body["kind"] = meta.get("kind")
    body["section"] = meta.get("section")
    return body


def _key(user_id: int, params: dict) -> str:
    """Two requests with the same key are the same piece of work."""
    parts = (
        user_id,
        params.get("action"),
        params.get("operation_id"),
        params.get("kind"),
        params.get("draft_id"),
        params.get("section"),
    )
    return ":".join(str(part or "") for part in parts)


def active_draft_jobs(
    *,
    user_id: int | None = None,
    operation_id: int | None = None,
    key: str | None = None,
    action: str | None = None,
    draft_id: int | None = None,
) -> list[AIJob]:
    """Every unfinished draft job that matches, oldest first. Few are ever active, so the filter runs here."""
    rows = (
        AIJob.query.filter(AIJob.job_type == JOB_TYPE, AIJob.status.in_(_ACTIVE))
        .order_by(AIJob.created_at.asc(), AIJob.id.asc())
        .all()
    )
    found = []
    for job in rows:
        meta = dict(job.meta or {})
        if user_id is not None and job.user_id != int(user_id):
            continue
        if operation_id is not None and meta.get("operation_id") != int(operation_id):
            continue
        if key is not None and meta.get("key") != key:
            continue
        if action is not None and meta.get("action") != action:
            continue
        if draft_id is not None and meta.get("draft_id") != int(draft_id):
            continue
        found.append(job)
    return found


def active_draft_job(**match) -> AIJob | None:
    """The oldest unfinished draft job that matches, if any."""
    jobs = active_draft_jobs(**match)
    return jobs[0] if jobs else None


def _process_item(app, *, job_id: str, item_id: int) -> None:
    with app.app_context():
        _expire_job(job_id)
        item = db.session.get(AIJobItem, int(item_id))
        params = dict(item.payload or {}) if item is not None else {}
        if ai_job_runner.job_cancel_requested(job_id):
            _mark_item(item_id, "cancelled", None)
            _write_progress(
                job_id,
                {"status": "cancelled", "stage": "cancelled", "message": _CANCELLED, "percent": 0},
                force=True,
            )
            _expire_job(job_id)
            return

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

        def progress(event: dict) -> None:
            if should_stop():
                raise DraftCancelled()
            _write_progress(job_id, {"status": "running", **event})

        try:
            _write_progress(
                job_id,
                {"status": "running", "stage": "starting", "message": "Starting the draft.", "percent": 2},
                force=True,
            )
            outcome = _run(params, progress)
            if outcome.get("ok"):
                _mark_item(item_id, "completed", None)
                summary = {
                    "draft_id": outcome.get("draft_id"),
                    "ai_used": bool(outcome.get("ai_used")),
                    "action": params.get("action"),
                }
                if params.get("action") == ACTION_SECTION:
                    # The page puts the text in its editor. A chapter has no draft to open.
                    summary.update(
                        {
                            "section": outcome.get("key"),
                            "html": outcome.get("html") or "",
                            "sources": outcome.get("sources") or [],
                        }
                    )
                _write_progress(
                    job_id,
                    {
                        "status": "completed",
                        "stage": "completed",
                        "message": "The chapter is ready." if params.get("action") == ACTION_SECTION else "The draft is ready.",
                        "percent": 100.0,
                        "summary": summary,
                    },
                    force=True,
                )
            else:
                error = str(outcome.get("error") or _FAILURE)
                _mark_item(item_id, "failed", error)
                _write_progress(
                    job_id,
                    {"status": "failed", "stage": "failed", "message": error, "error": error, "percent": 0},
                    force=True,
                )
        except DraftCancelled:
            db.session.rollback()
            _mark_item(item_id, "cancelled", None)
            _write_progress(
                job_id,
                {"status": "cancelled", "stage": "cancelled", "message": _CANCELLED, "percent": 0},
                force=True,
            )
        except Exception:
            logger.exception("DREF draft job %s failed", job_id)
            db.session.rollback()
            _mark_item(item_id, "failed", _FAILURE)
            _write_progress(
                job_id,
                {"status": "failed", "stage": "failed", "message": _FAILURE, "error": _FAILURE, "percent": 0},
                force=True,
            )
        finally:
            _expire_job(job_id)


def _run(params: dict, progress) -> dict:
    """Do the drafting the job was queued for, as the person who asked."""
    from app.models.core import User
    from plugins.emergency_operations_monitoring.config_store import ai_enabled
    from plugins.emergency_operations_monitoring.services.context import load_context
    from plugins.emergency_operations_monitoring.services.llm import (
        complete_section_with_engine,
        complete_with_engine,
        configured_model,
    )

    user = db.session.get(User, int(params.get("user_id") or 0))
    operation = db.session.get(DrefOperation, int(params.get("operation_id") or 0))
    if user is None or operation is None:
        return {"ok": False, "error": "Operation not found."}
    actor = actor_for_user(user)
    kind = params.get("kind") or "operational_update"
    complete = complete_with_engine if ai_enabled() else None
    if params.get("action") == ACTION_SECTION:
        draft = db.session.get(DrefDraft, int(params.get("draft_id") or 0))
        if draft is None or draft.operation_id != operation.id:
            return {"ok": False, "error": "Draft not found."}
        return regenerate_section(
            draft,
            operation,
            actor,
            str(params.get("section") or ""),
            complete_section=complete_section_with_engine if complete is not None else None,
            instruction=params.get("instruction") or "",
            current=params.get("current"),
            context_loader=load_context if complete is not None else None,
            progress=progress,
        )
    if params.get("action") == ACTION_INCLUDE:
        draft = db.session.get(DrefDraft, int(params.get("draft_id") or 0))
        if draft is None or draft.operation_id != operation.id:
            return {"ok": False, "error": "Draft not found."}
        outcome = include_narrative(
            draft,
            operation,
            actor,
            params.get("narrative") or NARRATIVE_AI,
            complete=complete,
            model_name=configured_model(draft.report_kind) if complete is not None else "",
            context_loader=load_context if complete is not None else None,
            progress=progress,
        )
        return {**outcome, "draft_id": draft.id}
    return generate_draft(
        operation,
        kind,
        actor,
        complete=complete,
        model_name=configured_model(kind),
        language=params.get("language") or "en",
        narrative=params.get("narrative") or None,
        context_loader=load_context if complete is not None else None,
        progress=progress,
    )


def _run_job(app, job_id: str) -> None:
    ai_job_runner.run_ai_job(app, str(job_id), _process_item, default_concurrency=1)


def ensure_draft_job_running(app, job_id: str) -> None:
    """Resume a job whose worker was lost, such as after a restart."""
    ai_job_runner.ensure_ai_job_running(app, str(job_id), _run_job)


def queue_draft_job(user_id: int, params: dict, app) -> tuple[str, bool]:
    """Start drafting, or return this person's job for the same work. ``created`` is false on reuse."""
    params = {**params, "user_id": int(user_id)}
    key = _key(int(user_id), params)
    existing = active_draft_job(key=key)
    if existing is not None:
        ensure_draft_job_running(app, str(existing.id))
        return str(existing.id), False

    job_id = uuid.uuid4().hex
    db.session.add(
        AIJob(
            id=job_id,
            job_type=JOB_TYPE,
            user_id=int(user_id),
            status="queued",
            total_items=1,
            meta={
                "stage": "queued",
                "message": "Waiting to start the draft.",
                "message_vars": {},
                "current": 0,
                "total": None,
                "percent": 0.0,
                "summary": None,
                "updated_ts": time.time(),
                "operation_id": int(params.get("operation_id") or 0),
                "action": params.get("action"),
                "draft_id": int(params["draft_id"]) if params.get("draft_id") else None,
                "section": str(params.get("section") or "")[:64] or None,
                "kind": str(params.get("kind") or "")[:32] or None,
                "key": key,
            },
        )
    )
    db.session.add(AIJobItem(job_id=job_id, item_index=0, entity_type="dref_draft", status="queued", payload=params))
    db.session.commit()
    ai_job_runner.start_ai_job_thread(app, job_id, _run_job)
    return job_id, True


def request_draft_cancel(job_id: str) -> str:
    """Ask a running job to stop. A job that has not started is cancelled at once."""
    job = db.session.get(AIJob, str(job_id))
    if job is None or str(job.job_type) != JOB_TYPE:
        return "missing"
    status = _status_str(job.status)
    if status in _TERMINAL:
        return status
    job.status = "cancel_requested"
    (
        db.session.query(AIJobItem)
        .filter(AIJobItem.job_id == str(job_id), AIJobItem.status == "queued")
        .update({"status": "cancelled", "error": None}, synchronize_session=False)
    )
    db.session.commit()
    ai_job_runner.signal_job_cancel(str(job_id))
    return "cancel_requested"
