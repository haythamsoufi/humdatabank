"""UPR visuals bulk export as a Track A job on AIJob / ai_job_runner.

One AIJob + one AIJobItem per export (shared ZIP). Progress lives in AIJob.meta
so any Gunicorn worker can serve status polls after a browser close or reload.
"""

from __future__ import annotations

import gc
import logging
import shutil
import threading
import time
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from flask import current_app
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.exceptions import NotFound

from app.extensions import db
from app.models import AIJob, AIJobItem
from app.services.ai.ai_job_runner import (
    ensure_ai_job_running,
    is_job_thread_alive,
    job_cancel_requested,
    reconcile_stale_ai_job,
    run_ai_job,
    signal_job_cancel,
    start_ai_job_thread,
)
from app.services.platform import storage_service
from app.utils.datetime_helpers import utcnow
from plugins.upr_visuals.bulk import match_narrative_path, normalize_export_format
from plugins.upr_visuals.catalog import dashboards_for_kind, kind_for_template
from plugins.upr_visuals.data import build_payload, filename_from_visual_title
from plugins.upr_visuals.i18n import export_locale, parse_export_language
from plugins.upr_visuals.render import render_dashboard_html
from app.utils.pg_advisory_lock import acquire_transaction_advisory_lock
from plugins.upr_visuals.service import STORAGE_CATEGORY, UprVisualsService

# Transaction advisory lock for the one-at-a-time bulk queue (clear of digest/RBAC/AI-job ids).
UPR_VISUALS_BULK_CREATE_LOCK_ID = 915100001

logger = logging.getLogger(__name__)

BULK_EXPORT_JOB_TYPE = "upr_visuals.bulk_export"
BULK_EXPORT_JOB_TTL_SECONDS = 6 * 60 * 60
_PERSIST_MIN_INTERVAL = 0.5
_ACTIVE_JOB_STATUSES = ("queued", "running", "cancel_requested")
_TERMINAL_JOB_STATUSES = frozenset({"completed", "failed", "cancelled"})
_ACTIVE_ITEM_STATUSES = frozenset({"queued", "downloading", "processing"})

_persist_lock = threading.Lock()
_last_persist_ts: dict[str, float] = {}
_last_cleanup_ts = 0.0
_last_cleanup_lock = threading.Lock()


def _status_str(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value or "")


@contextmanager
def _isolated_job_session() -> Iterator[Session]:
    session = sessionmaker(bind=db.engine)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _job_dir(job_id: str) -> Path:
    return Path(current_app.instance_path) / "upr_visuals_tmp" / str(job_id)


def _write_narrative_files(job_id: str, narrative_files: dict[str, bytes] | None) -> dict[str, str]:
    job_dir = _job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    narrative_paths: dict[str, str] = {}
    for stem, data in (narrative_files or {}).items():
        if not data:
            continue
        safe = filename_from_visual_title(str(stem) or "narrative", "docx")
        path = job_dir / "narratives" / safe
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        narrative_paths[str(stem).strip().lower()] = str(path)
    return narrative_paths


def _fail_orphaned_bulk_jobs() -> None:
    """Fail in-flight exports whose worker thread is gone.

    The ZIP render loop is not resumable. A leftover queued/running row after a
    process restart must not block every future export.
    """
    jobs = (
        AIJob.query.filter(
            AIJob.job_type == BULK_EXPORT_JOB_TYPE,
            AIJob.status.in_(_ACTIVE_JOB_STATUSES),
        ).all()
    )
    for existing in jobs:
        job_id = str(existing.id)
        reconcile_stale_ai_job(job_id)
        job = AIJob.query.get(job_id)
        if not job or _status_str(job.status) in _TERMINAL_JOB_STATUSES:
            continue
        if is_job_thread_alive(job_id):
            continue
        for item in job.items or []:
            if _status_str(item.status) in _ACTIVE_ITEM_STATUSES:
                item.status = "failed"
                item.error = "Server stopped during export."
        job.status = "failed"
        job.error = "Server stopped during export."
        job.finished_at = utcnow()
        meta = dict(job.meta or {})
        meta["message"] = "Failed"
        meta["error"] = job.error
        job.meta = meta
        flag_modified(job, "meta")
        db.session.commit()
        logger.warning("Failed orphaned UPR visuals export: job=%s", job_id)


def create_bulk_export_job(
    *,
    user_id: int,
    assigned_form_id: int,
    dashboard_ids: list[str],
    aes_ids: list[int] | None = None,
    export_format: str = "png",
    include_narrative: bool = False,
    narrative_files: dict[str, bytes] | None = None,
    lang: str = "en",
) -> str:
    from plugins.upr_visuals.data import get_assigned_form_for_bulk

    _fail_orphaned_bulk_jobs()
    acquire_transaction_advisory_lock(db.session, UPR_VISUALS_BULK_CREATE_LOCK_ID)
    inflight = (
        AIJob.query.filter(
            AIJob.job_type == BULK_EXPORT_JOB_TYPE,
            AIJob.status.in_(_ACTIVE_JOB_STATUSES),
        ).first()
    )
    if inflight:
        raise RuntimeError("A UPR visuals export is already running.")

    assigned = get_assigned_form_for_bulk(int(assigned_form_id))
    kind = kind_for_template(int(assigned.template_id))
    allowed = {spec.id for spec in dashboards_for_kind(kind)}
    export_format = normalize_export_format(export_format)
    include_narrative = bool(include_narrative) and export_format in {"pdf", "idml"}
    selected = [did for did in dashboard_ids if did in allowed] or ["combined"]
    if export_format == "idml" or include_narrative:
        selected = ["combined"]
    lang = parse_export_language(lang)
    job_id = str(uuid.uuid4())
    narrative_paths = _write_narrative_files(job_id, narrative_files)
    now = utcnow()
    meta = {
        "assigned_form_id": assigned.id,
        "template_id": int(assigned.template_id),
        "period_name": assigned.period_name,
        "dashboard_ids": selected,
        "aes_ids": [int(i) for i in (aes_ids or [])],
        "export_format": export_format,
        "include_narrative": include_narrative,
        "lang": lang,
        "progress": 0,
        "total": 0,
        "message": "Queued",
        "zip_key": None,
        "error": None,
    }
    payload = {
        "assigned_form_id": assigned.id,
        "template_id": int(assigned.template_id),
        "period_name": assigned.period_name,
        "dashboard_ids": selected,
        "aes_ids": [int(i) for i in (aes_ids or [])],
        "export_format": export_format,
        "include_narrative": include_narrative,
        "narrative_paths": narrative_paths,
        "lang": lang,
    }
    job = AIJob(
        id=job_id,
        job_type=BULK_EXPORT_JOB_TYPE,
        user_id=int(user_id or 0),
        status="queued",
        total_items=1,
        created_at=now,
        meta=meta,
    )
    item = AIJobItem(
        job_id=job_id,
        item_index=0,
        entity_type="assigned_form",
        entity_id=int(assigned.id),
        status="queued",
        payload=payload,
    )
    db.session.add(job)
    db.session.add(item)
    db.session.commit()
    return job_id


def start_bulk_export_job(app, job_id: str) -> None:
    start_ai_job_thread(app, str(job_id), _run_bulk_export_job)


def ensure_bulk_export_job_running(app, job_id: str) -> None:
    _maybe_cleanup_expired_jobs()
    ensure_ai_job_running(app, str(job_id), _run_bulk_export_job)


def request_bulk_export_cancel(job_id: str) -> str:
    job = AIJob.query.get(str(job_id))
    if not job or job.job_type != BULK_EXPORT_JOB_TYPE:
        return "missing"
    if _status_str(job.status) in _TERMINAL_JOB_STATUSES:
        return _status_str(job.status)

    job.status = "cancel_requested"
    try:
        (
            db.session.query(AIJobItem)
            .filter(AIJobItem.job_id == str(job_id), AIJobItem.status == "queued")
            .update({"status": "cancelled", "error": None}, synchronize_session=False)
        )
    except Exception as exc:
        logger.debug("UPR visuals cancel item update failed: job=%s err=%s", job_id, exc)
        db.session.rollback()
    meta = dict(job.meta or {})
    meta["message"] = "Cancelled"
    job.meta = meta
    flag_modified(job, "meta")
    db.session.commit()
    signal_job_cancel(str(job_id))
    return "cancel_requested"


def build_bulk_export_status_payload(job_id: str | None) -> dict[str, Any] | None:
    if not job_id:
        return None
    job = AIJob.query.get(str(job_id))
    if not job or job.job_type != BULK_EXPORT_JOB_TYPE:
        return None
    meta = dict(job.meta or {})
    payload: dict[str, Any] = {}
    items = job.items or []
    if items:
        first = items[0].payload if isinstance(items[0].payload, dict) else {}
        payload = dict(first)
    status = _status_str(job.status)
    return {
        "job_id": str(job.id),
        "status": status,
        "assigned_form_id": meta.get("assigned_form_id") or payload.get("assigned_form_id"),
        "template_id": meta.get("template_id") or payload.get("template_id"),
        "period_name": meta.get("period_name") or payload.get("period_name"),
        "dashboard_ids": meta.get("dashboard_ids") or payload.get("dashboard_ids") or [],
        "aes_ids": meta.get("aes_ids") or payload.get("aes_ids") or [],
        "export_format": meta.get("export_format") or payload.get("export_format") or "png",
        "include_narrative": bool(meta.get("include_narrative") if "include_narrative" in meta else payload.get("include_narrative")),
        "lang": meta.get("lang") or payload.get("lang") or "en",
        "progress": int(meta.get("progress") or 0),
        "total": int(meta.get("total") or 0),
        "message": meta.get("message") or "",
        "zip_key": meta.get("zip_key"),
        "error": job.error or meta.get("error"),
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def get_latest_bulk_export_job_id() -> str | None:
    job = (
        AIJob.query.filter(AIJob.job_type == BULK_EXPORT_JOB_TYPE)
        .order_by(AIJob.created_at.desc())
        .first()
    )
    return str(job.id) if job else None


def get_active_bulk_export_job() -> dict[str, Any] | None:
    job = (
        AIJob.query.filter(
            AIJob.job_type == BULK_EXPORT_JOB_TYPE,
            AIJob.status.in_(_ACTIVE_JOB_STATUSES),
        )
        .order_by(AIJob.created_at.desc())
        .first()
    )
    if job:
        return build_bulk_export_status_payload(str(job.id))
    latest = (
        AIJob.query.filter(AIJob.job_type == BULK_EXPORT_JOB_TYPE)
        .order_by(AIJob.created_at.desc())
        .first()
    )
    if not latest or _status_str(latest.status) != "completed":
        return None
    payload = build_bulk_export_status_payload(str(latest.id))
    if payload and payload.get("zip_key"):
        return payload
    return None


def serve_bulk_export_zip(job_id: str):
    """Any system manager can download the singleton queue's ZIP."""
    payload = build_bulk_export_status_payload(job_id)
    key = (payload or {}).get("zip_key")
    if not key:
        raise NotFound("Export is not ready.")
    if not storage_service.exists(STORAGE_CATEGORY, key):
        raise NotFound("Export is not ready.")
    return storage_service.stream_response(
        STORAGE_CATEGORY,
        key,
        filename="upr-visuals.zip",
        mimetype="application/zip",
        as_attachment=True,
    )


def cleanup_expired_bulk_export_jobs(now_ts: float | None = None) -> None:
    if now_ts is None:
        now_ts = time.time()
    cutoff = datetime.fromtimestamp(now_ts - BULK_EXPORT_JOB_TTL_SECONDS, tz=timezone.utc).replace(tzinfo=None)
    try:
        with _isolated_job_session() as session:
            expired = (
                session.query(AIJob)
                .filter(
                    AIJob.job_type == BULK_EXPORT_JOB_TYPE,
                    AIJob.status.in_(tuple(_TERMINAL_JOB_STATUSES)),
                    AIJob.created_at < cutoff,
                )
                .all()
            )
            for job in expired:
                zip_key = (job.meta or {}).get("zip_key")
                if zip_key and isinstance(zip_key, str):
                    try:
                        storage_service.delete(STORAGE_CATEGORY, zip_key)
                    except Exception:
                        logger.debug("UPR visuals zip cleanup failed: job=%s", job.id, exc_info=True)
                session.delete(job)
            if expired:
                logger.info("Cleaned up %s expired UPR visuals export jobs", len(expired))
    except Exception:
        logger.exception("Failed to clean up expired UPR visuals export jobs")


def _maybe_cleanup_expired_jobs() -> None:
    global _last_cleanup_ts
    now = time.time()
    with _last_cleanup_lock:
        if now - _last_cleanup_ts < 300:
            return
        _last_cleanup_ts = now
    cleanup_expired_bulk_export_jobs(now)


def _should_persist(job_id: str, *, force: bool) -> bool:
    if force:
        return True
    now = time.time()
    with _persist_lock:
        last = _last_persist_ts.get(job_id, 0.0)
        if now - last < _PERSIST_MIN_INTERVAL:
            return False
        _last_persist_ts[job_id] = now
    return True


def _update_job_progress(job_id: str, item_id: int | None = None, *, force: bool = False, **fields: Any) -> None:
    if not _should_persist(str(job_id), force=force):
        return
    try:
        with _isolated_job_session() as session:
            job = session.get(AIJob, str(job_id))
            if not job:
                return
            meta = dict(job.meta or {})
            for key in (
                "progress",
                "total",
                "message",
                "zip_key",
                "error",
                "assigned_form_id",
                "template_id",
                "period_name",
                "dashboard_ids",
                "aes_ids",
                "export_format",
                "include_narrative",
                "lang",
            ):
                if key in fields:
                    meta[key] = fields[key]
            job.meta = meta
            flag_modified(job, "meta")
            if "error" in fields and fields["error"] is not None:
                job.error = fields["error"]
            if item_id is not None:
                item = session.get(AIJobItem, int(item_id))
                if item:
                    item.updated_at = utcnow()
    except Exception:
        logger.exception("Failed to persist UPR visuals job progress %s", job_id)


def _process_bulk_export_item_sync(app, *, job_id: str, item_id: int) -> None:
    work_root = Path(app.instance_path) / "upr_visuals_tmp"
    job_dir = work_root / str(job_id)
    zip_path = work_root / f"{job_id}.zip"
    with app.app_context():
        item = AIJobItem.query.get(int(item_id))
        if not item or str(item.job_id) != str(job_id):
            return

        if job_cancel_requested(job_id):
            item.status = "cancelled"
            item.error = None
            _update_job_progress(job_id, item_id, force=True, message="Cancelled")
            db.session.commit()
            return

        payload = dict(item.payload or {})
        lang = parse_export_language(payload.get("lang"))
        terminal_item_status = "failed"
        try:
            _update_job_progress(job_id, item_id, force=True, message="Loading assignments…")
            from plugins.upr_visuals.data import list_countries_for_bulk

            assignments = list_countries_for_bulk(int(payload["assigned_form_id"]))
            wanted = set(int(i) for i in (payload.get("aes_ids") or []))
            if wanted:
                assignments = [row for row in assignments if row["aes_id"] in wanted]
            dashboards = payload.get("dashboard_ids") or ["combined"]
            export_format = normalize_export_format(payload.get("export_format") or "png")
            include_narrative = bool(payload.get("include_narrative")) and export_format in {"pdf", "idml"}
            if export_format == "idml" or include_narrative:
                dashboards = ["combined"]
            total = max(len(assignments) * len(dashboards), 1)
            _update_job_progress(job_id, item_id, force=True, total=total, message="Rendering…")
            job_dir.mkdir(parents=True, exist_ok=True)
            done = 0
            errors: list[str] = []
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf, export_locale(lang):
                for row in assignments:
                    if job_cancel_requested(job_id):
                        item.status = "cancelled"
                        item.error = None
                        _update_job_progress(job_id, item_id, force=True, message="Cancelled")
                        db.session.commit()
                        return
                    try:
                        country_payload = build_payload(row["aes_id"], inline_icons=True)
                    except Exception as exc:
                        logger.warning("UPR visuals skip aes %s: %s", row["aes_id"], exc)
                        errors.append(f"aes {row['aes_id']}: could not build visuals")
                        try:
                            db.session.rollback()
                        except Exception:
                            pass
                        done += len(dashboards)
                        _update_job_progress(job_id, item_id, progress=done)
                        continue
                    meta = country_payload["meta"]
                    iso3 = meta.get("iso3") or row.get("iso3") or "UNK"
                    round_code = meta.get("round_code") or "round"
                    folder = filename_from_visual_title(f"{iso3}_{round_code}", "png")[:-4]
                    available = {item_dash.get("id") for item_dash in country_payload.get("dashboards") or []}
                    word_path = None
                    if include_narrative:
                        word_path = match_narrative_path(
                            payload.get("narrative_paths") or {},
                            iso3=str(iso3),
                            country_name=str(meta.get("country_name") or row.get("country_name") or ""),
                            aes_id=row["aes_id"],
                        )
                        if word_path is None or not word_path.is_file():
                            errors.append(f"aes {row['aes_id']}: no matching Word file; exporting visuals only")
                            word_path = None
                    for dashboard_id in dashboards:
                        if job_cancel_requested(job_id):
                            item.status = "cancelled"
                            item.error = None
                            _update_job_progress(job_id, item_id, force=True, message="Cancelled")
                            db.session.commit()
                            return
                        if str(dashboard_id).startswith("emergency_") and dashboard_id not in available:
                            done += 1
                            _update_job_progress(job_id, item_id, progress=done)
                            continue
                        try:
                            html = render_dashboard_html(country_payload, dashboard_id)
                            logger.info(
                                "UPR visuals render aes %s %s %s (%s/%s)",
                                row["aes_id"],
                                export_format,
                                dashboard_id,
                                done + 1,
                                total,
                            )
                            tmp, arcname = UprVisualsService._render_bulk_item(
                                job_dir,
                                payload=country_payload,
                                html=html,
                                dashboard_id=dashboard_id,
                                folder=folder,
                                export_format=export_format,
                                lang=lang,
                                word_path=word_path,
                            )
                            try:
                                zf.write(tmp, arcname=arcname)
                            finally:
                                try:
                                    tmp.unlink()
                                except OSError:
                                    pass
                        except TimeoutError:
                            logger.warning(
                                "UPR visuals render timed out for aes %s dashboard %s",
                                row["aes_id"],
                                dashboard_id,
                            )
                            errors.append(f"aes {row['aes_id']} {dashboard_id}: timed out")
                        except Exception as exc:
                            logger.warning(
                                "UPR visuals skip aes %s dashboard %s: %s",
                                row["aes_id"],
                                dashboard_id,
                                exc,
                            )
                            errors.append(f"aes {row['aes_id']} {dashboard_id}: render failed")
                        finally:
                            gc.collect()
                        done += 1
                        _update_job_progress(
                            job_id,
                            item_id,
                            progress=done,
                            message=f"{iso3} · {dashboard_id}",
                        )
            zip_key = f"exports/{job_id}/upr-visuals.zip"
            storage_service.upload(STORAGE_CATEGORY, zip_key, zip_path.read_bytes())
            error_note = "; ".join(errors) if errors else None
            _update_job_progress(
                job_id,
                item_id,
                force=True,
                progress=total,
                zip_key=zip_key,
                message="Done",
                error=error_note,
            )
            item.status = "completed"
            item.error = error_note
            terminal_item_status = "completed"
        except Exception as exc:
            logger.exception("UPR visuals bulk export failed")
            _update_job_progress(
                job_id, item_id, force=True, message="Failed", error="Could not generate this export."
            )
            item.status = "failed"
            item.error = "Could not generate this export."
            terminal_item_status = "failed"
        finally:
            if item.status not in ("completed", "failed", "cancelled"):
                item.status = terminal_item_status
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                logger.exception("UPR visuals job item commit failed: job=%s", job_id)
            shutil.rmtree(job_dir, ignore_errors=True)
            try:
                zip_path.unlink()
            except OSError:
                pass
            db.session.remove()


def _run_bulk_export_job(app, job_id: str) -> None:
    run_ai_job(
        app,
        str(job_id),
        _process_bulk_export_item_sync,
        concurrency_config_keys=("UPR_VISUALS_BULK_CONCURRENCY",),
        default_concurrency=1,
    )
