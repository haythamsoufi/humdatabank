"""FDRS publication background job (Track A — single-item batch via ai_job_runner)."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from app.extensions import db
from app.models import AIJob, AIJobItem, AssignmentEntityStatus
from app.services.ai.ai_job_runner import (
    ensure_ai_job_running,
    job_cancel_requested,
    run_ai_job,
    signal_job_cancel,
    start_ai_job_thread,
)
from app.services.imports.async_import_job_store import (
    FDRS_PUBLICATION_JOB_TYPE,
    clear_import_job_logging_state,
    get_import_job,
    update_import_job,
)
from app.utils.data_quality_constants import FDRS_TEMPLATE_ID
from plugins.fdrs.services.fdrs_publication_service import (
    ALL_DIFF_KINDS,
    _empty_counts,
    _get_fdrs_assigned_form_or_404,
    publish_assignment,
)

logger = logging.getLogger(__name__)


def _summarize_error(exc: BaseException) -> str:
    err_msg = str(exc).strip() or type(exc).__name__
    if len(err_msg) > 2000:
        return err_msg[:1997] + "..."
    return err_msg


def _merge_totals(acc: Dict[str, int], part: Dict[str, int]) -> None:
    for kind in ALL_DIFF_KINDS:
        acc[kind] += int(part.get(kind) or 0)


def _target_aes_ids(
    assigned_form_id: int,
    assignment_entity_status_ids: Optional[List[int]],
) -> List[int]:
    valid_ids = [
        aes_id for (aes_id,) in (
            AssignmentEntityStatus.query
            .filter_by(assigned_form_id=assigned_form_id, entity_type="country")
            .with_entities(AssignmentEntityStatus.id)
            .all()
        )
    ]
    if not assignment_entity_status_ids:
        return valid_ids
    valid_set = set(valid_ids)
    return [aid for aid in assignment_entity_status_ids if aid in valid_set]


def create_fdrs_publication_job(
    *,
    user_id: int,
    assigned_form_id: int,
    assignment_entity_status_ids: Optional[List[int]],
) -> str:
    """Create AIJob + single AIJobItem for an async FDRS publish."""
    job_id = uuid.uuid4().hex
    now_ts = time.time()
    meta = {
        "template_id": int(FDRS_TEMPLATE_ID),
        "assigned_form_id": int(assigned_form_id),
        "stage": "queued",
        "message": "Queued",
        "current": 0,
        "total": None,
        "percent": 0.0,
        "stats": None,
        "error": None,
        "started_ts": now_ts,
        "updated_ts": now_ts,
    }
    payload = {
        "assigned_form_id": int(assigned_form_id),
        "assignment_entity_status_ids": assignment_entity_status_ids,
        "user_id": int(user_id or 0) or None,
    }
    job = AIJob(
        id=job_id,
        job_type=FDRS_PUBLICATION_JOB_TYPE,
        user_id=int(user_id or 0),
        status="queued",
        total_items=1,
        meta=meta,
    )
    item = AIJobItem(
        job_id=job_id,
        item_index=0,
        entity_type="assigned_form",
        entity_id=int(assigned_form_id),
        status="queued",
        payload=payload,
    )
    db.session.add(job)
    db.session.add(item)
    db.session.commit()
    return job_id


def get_active_fdrs_publication_jobs_for_user(
    user_id: int,
    *,
    assigned_form_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    if not user_id:
        return []

    jobs = (
        AIJob.query
        .filter(
            AIJob.user_id == int(user_id),
            AIJob.job_type == FDRS_PUBLICATION_JOB_TYPE,
            AIJob.status.in_(("queued", "running", "cancel_requested")),
        )
        .order_by(AIJob.created_at.desc())
        .all()
    )
    out: List[Dict[str, Any]] = []
    for job in jobs:
        meta = dict(job.meta or {})
        job_assignment_id = int(meta.get("assigned_form_id") or 0)
        if assigned_form_id is not None and job_assignment_id != int(assigned_form_id):
            continue
        out.append(
            {
                "job_id": str(job.id),
                "job_type": job.job_type,
                "status": str(job.status),
                "assigned_form_id": job_assignment_id,
                "stage": meta.get("stage") or "",
                "message": meta.get("message") or "",
                "percent": float(meta.get("percent") or 0.0),
                "current": meta.get("current") or 0,
                "total": meta.get("total"),
            }
        )
    return out


def start_fdrs_publication_job(app, job_id: str) -> None:
    start_ai_job_thread(app, job_id, _run_fdrs_publication_job)


def ensure_fdrs_publication_job_running(app, job_id: str) -> None:
    ensure_ai_job_running(app, job_id, _run_fdrs_publication_job)


def request_fdrs_publication_cancel(job_id: str) -> str:
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
        logger.debug("FDRS publication cancel item update failed: job=%s err=%s", job_id, exc)
        db.session.rollback()
    db.session.commit()
    signal_job_cancel(str(job_id))
    return "cancel_requested"


def build_fdrs_publication_status_payload(
    job_id: str,
    assigned_form_id: int,
) -> Optional[Dict[str, Any]]:
    job = get_import_job(job_id)
    if not job or int(job.get("assigned_form_id") or 0) != int(assigned_form_id):
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
    }


def _process_fdrs_publication_item(app, *, job_id: str, item_id: int) -> None:
    with app.app_context():
        item = AIJobItem.query.get(int(item_id))
        if not item or str(item.job_id) != str(job_id):
            return

        if job_cancel_requested(job_id):
            item.status = "cancelled"
            db.session.commit()
            return

        payload = dict(item.payload or {})
        assigned_form_id = int(payload.get("assigned_form_id") or 0)
        raw_ids = payload.get("assignment_entity_status_ids")
        user_id = payload.get("user_id")
        item.status = "processing"
        db.session.commit()

        try:
            _get_fdrs_assigned_form_or_404(assigned_form_id)
            targets = _target_aes_ids(assigned_form_id, raw_ids)
            totals = _empty_counts()
            published_countries = 0
            total = len(targets)
            update_import_job(
                job_id,
                force=True,
                stage="publishing",
                message="Publishing…" if total else "Nothing to publish",
                current=0,
                total=total,
                percent=0.0,
            )

            for index, aes_id in enumerate(targets, start=1):
                if job_cancel_requested(job_id):
                    item.status = "cancelled"
                    update_import_job(
                        job_id,
                        force=True,
                        stage="cancelled",
                        message=f"Cancelled after {index - 1} of {total} countries",
                        current=index - 1,
                        total=total,
                        percent=(100.0 * (index - 1) / total) if total else 100.0,
                        stats={
                            "published_countries": published_countries,
                            "totals": totals,
                        },
                    )
                    db.session.commit()
                    return

                stats = publish_assignment(
                    assigned_form_id,
                    assignment_entity_status_ids=[aes_id],
                    user_id=user_id,
                )
                published_countries += int(stats.get("published_countries") or 0)
                _merge_totals(totals, stats.get("totals") or {})
                update_import_job(
                    job_id,
                    force=True,
                    stage="publishing",
                    message=f"Published {index} of {total} countries",
                    current=index,
                    total=total,
                    percent=(100.0 * index / total) if total else 100.0,
                    stats={
                        "published_countries": published_countries,
                        "totals": totals,
                    },
                )

            item.status = "completed"
            update_import_job(
                job_id,
                force=True,
                stage="completed",
                message=f"Published {published_countries} countries",
                current=total,
                total=total,
                percent=100.0,
                stats={
                    "published_countries": published_countries,
                    "totals": totals,
                },
            )
            db.session.commit()
        except Exception as exc:
            logger.exception("FDRS publication %s: failed", job_id)
            item.status = "failed"
            item.error = _summarize_error(exc)
            update_import_job(
                job_id,
                force=True,
                stage="failed",
                message="Publication failed",
                error=_summarize_error(exc),
            )
            db.session.commit()
        finally:
            clear_import_job_logging_state(job_id)


def _run_fdrs_publication_job(app, job_id: str) -> None:
    run_ai_job(
        app,
        str(job_id),
        _process_fdrs_publication_item,
        concurrency_config_keys=("FDRS_PUBLICATION_CONCURRENCY",),
        default_concurrency=1,
    )
