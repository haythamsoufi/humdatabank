"""Single-assignment PNG/PDF/InDesign export as a background AIJob.

WeasyPrint takes longer than the HTTP stuck-request window, so assignment
routes only queue work. The browser polls status (or a wait page) and downloads
when ready. Download is gated by assignment ACL on the route, not job.user_id,
so anyone who can open the assignment can fetch a completed export.
"""

from __future__ import annotations

import logging
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import current_app, send_file
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.exceptions import NotFound

from app.extensions import db
from app.models import AIJob, AIJobItem
from app.services.ai.ai_job_runner import (
    ensure_ai_job_running,
    is_job_thread_alive,
    reconcile_stale_ai_job,
    start_ai_job_thread,
)
from app.utils.datetime_helpers import utcnow
from plugins.upr_visuals.i18n import parse_export_language
from plugins.upr_visuals.service import UprVisualsService
from plugins.upr_visuals.typography import export_style_token

logger = logging.getLogger(__name__)

ASSIGNMENT_EXPORT_JOB_TYPE = "upr_visuals.assignment_export"
ASSIGNMENT_EXPORT_JOB_TTL_SECONDS = 6 * 60 * 60
REUSE_COMPLETED_SECONDS = 15 * 60
_ACTIVE_JOB_STATUSES = ("queued", "running", "cancel_requested")
_TERMINAL_JOB_STATUSES = frozenset({"completed", "failed", "cancelled"})
_VISUAL_FORMATS = frozenset({"png", "pdf", "idml"})
_last_cleanup_ts = 0.0
_last_cleanup_lock = threading.Lock()


def _status_str(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value or "")


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _job_dir(job_id: str) -> Path:
    return Path(current_app.instance_path) / "upr_visuals_tmp" / str(job_id)


def _read_job_word(job_dir: Path, word_path: str | Path) -> bytes | None:
    raw = str(word_path or "").strip()
    if not raw or raw in {".", ".."}:
        return None
    try:
        resolved = Path(raw).resolve()
    except OSError as exc:
        raise RuntimeError("Export job is missing the Word document.") from exc
    root = job_dir.resolve()
    if root not in resolved.parents and resolved != root:
        raise RuntimeError("Export job is missing the Word document.")
    if not resolved.is_file():
        raise RuntimeError("Export job is missing the Word document.")
    return resolved.read_bytes()


def cleanup_expired_assignment_export_jobs(now_ts: float | None = None) -> None:
    if now_ts is None:
        now_ts = time.time()
    cutoff = datetime.fromtimestamp(now_ts - ASSIGNMENT_EXPORT_JOB_TTL_SECONDS, tz=timezone.utc).replace(
        tzinfo=None
    )
    try:
        expired = (
            AIJob.query.filter(
                AIJob.job_type == ASSIGNMENT_EXPORT_JOB_TYPE,
                AIJob.status.in_(tuple(_TERMINAL_JOB_STATUSES)),
                AIJob.created_at < cutoff,
            ).all()
        )
        for job in expired:
            shutil.rmtree(_job_dir(str(job.id)), ignore_errors=True)
            db.session.delete(job)
        if expired:
            db.session.commit()
            logger.info("Cleaned up %s expired UPR assignment export jobs", len(expired))
    except Exception:
        db.session.rollback()
        logger.exception("Failed to clean up expired UPR assignment export jobs")


def _maybe_cleanup_expired_jobs() -> None:
    global _last_cleanup_ts
    now = time.time()
    with _last_cleanup_lock:
        if now - _last_cleanup_ts < 300:
            return
        _last_cleanup_ts = now
    cleanup_expired_assignment_export_jobs(now)


def create_assignment_export_job(
    *,
    user_id: int,
    aes_id: int,
    export_format: str,
    word_bytes: bytes | None = None,
    lang: str = "en",
    dashboard_id: str = "combined",
) -> str:
    from plugins.upr_visuals.catalog import DASHBOARD_BY_ID
    from plugins.upr_visuals.errors import UprVisualsError

    fmt = str(export_format or "pdf").strip().lower()
    if fmt not in _VISUAL_FORMATS:
        raise UprVisualsError("Choose PNG, PDF, or InDesign.")
    dash = str(dashboard_id or "combined").strip() or "combined"
    if dash not in DASHBOARD_BY_ID:
        raise UprVisualsError(f"Unknown dashboard: {dash}")
    lang = parse_export_language(lang)
    job_id = str(uuid.uuid4())
    job_dir = _job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    word_path = ""
    if word_bytes:
        path = job_dir / "narrative.docx"
        path.write_bytes(word_bytes)
        word_path = str(path)
    now = utcnow()
    meta = {
        "aes_id": int(aes_id),
        "export_format": fmt,
        "dashboard_id": dash,
        "lang": lang,
        "message": "Queued",
        "progress": 0,
        "total": 5,
        "elapsed_s": 0,
        "filename": None,
        "output_path": None,
        "mimetype": None,
        "error": None,
        "has_word": bool(word_bytes),
        "style_rev": export_style_token(),
    }
    payload = {
        "aes_id": int(aes_id),
        "export_format": fmt,
        "dashboard_id": dash,
        "lang": lang,
        "word_path": word_path,
    }
    job = AIJob(
        id=job_id,
        job_type=ASSIGNMENT_EXPORT_JOB_TYPE,
        user_id=int(user_id or 0),
        status="queued",
        total_items=1,
        created_at=now,
        meta=meta,
    )
    item = AIJobItem(
        job_id=job_id,
        item_index=0,
        entity_type="assignment_entity_status",
        entity_id=int(aes_id),
        status="queued",
        payload=payload,
    )
    db.session.add(job)
    db.session.add(item)
    db.session.commit()
    return job_id


def _visual_job_matches(
    job: AIJob,
    *,
    aes_id: int,
    export_format: str,
    dashboard_id: str,
    lang: str,
) -> bool:
    if not job or job.job_type != ASSIGNMENT_EXPORT_JOB_TYPE:
        return False
    meta = dict(job.meta or {})
    if meta.get("has_word"):
        return False
    return (
        int(meta.get("aes_id") or 0) == int(aes_id)
        and str(meta.get("export_format") or "pdf") == export_format
        and str(meta.get("dashboard_id") or "combined") == dashboard_id
        and str(meta.get("lang") or "en") == lang
        and str(meta.get("style_rev") or "") == export_style_token()
    )


def _reusable_job_id(
    jobs: list[Any],
    *,
    aes_id: int,
    export_format: str,
    dashboard_id: str,
    lang: str,
    now: datetime | None = None,
) -> str | None:
    fmt = str(export_format or "pdf").strip().lower()
    dash = str(dashboard_id or "combined").strip() or "combined"
    lang = parse_export_language(lang)
    clock = now or utcnow()
    for job in jobs:
        if not _visual_job_matches(
            job, aes_id=aes_id, export_format=fmt, dashboard_id=dash, lang=lang
        ):
            continue
        status = _status_str(job.status)
        if status in _ACTIVE_JOB_STATUSES:
            return str(job.id)
        if status != "completed":
            continue
        finished = _as_utc(job.finished_at or job.created_at)
        if finished is None:
            continue
        age = (_as_utc(clock) - finished).total_seconds()
        if age < 0 or age > REUSE_COMPLETED_SECONDS:
            continue
        raw_path = (job.meta or {}).get("output_path")
        if not raw_path:
            continue
        try:
            path = Path(str(raw_path)).resolve()
        except OSError:
            continue
        if path.is_file() and path.stat().st_size > 0:
            return str(job.id)
    return None


def find_reusable_assignment_export_job(
    *,
    aes_id: int,
    export_format: str,
    dashboard_id: str = "combined",
    lang: str = "en",
) -> str | None:
    """Return a matching in-flight or freshly completed visual export, if any."""
    jobs = (
        AIJob.query.filter(AIJob.job_type == ASSIGNMENT_EXPORT_JOB_TYPE)
        .order_by(AIJob.created_at.desc())
        .limit(80)
        .all()
    )
    return _reusable_job_id(
        jobs,
        aes_id=aes_id,
        export_format=export_format,
        dashboard_id=dashboard_id,
        lang=lang,
    )


def take_matching_pdf_bytes(
    *,
    aes_id: int,
    dashboard_id: str = "combined",
    lang: str = "en",
    timeout: float = 120.0,
) -> tuple[bytes, str] | None:
    """Return a fresh matching PDF so PNG can skip a second WeasyPrint pass.

    If a PDF export is already running for the same assignment, wait for it.
    """
    job_id = find_reusable_assignment_export_job(
        aes_id=aes_id,
        export_format="pdf",
        dashboard_id=dashboard_id,
        lang=lang,
    )
    if not job_id:
        return None
    deadline = time.monotonic() + max(1.0, float(timeout))
    saw_inflight = False
    while time.monotonic() < deadline:
        job = AIJob.query.get(str(job_id))
        if not job:
            return None
        status = _status_str(job.status)
        if status in _ACTIVE_JOB_STATUSES:
            if not saw_inflight:
                logger.info(
                    "UPR PNG waiting for in-flight PDF job=%s aes=%s dash=%s",
                    job_id,
                    aes_id,
                    dashboard_id,
                )
            saw_inflight = True
            db.session.expire_all()
            time.sleep(0.4)
            continue
        if status != "completed":
            return None
        raw_path = (job.meta or {}).get("output_path")
        filename = str((job.meta or {}).get("filename") or "visuals.pdf")
        if not raw_path:
            return None
        path = Path(str(raw_path))
        if not path.is_file() or path.stat().st_size <= 0:
            return None
        logger.info(
            "UPR PNG reusing PDF job=%s aes=%s dash=%s (%s bytes)",
            job_id,
            aes_id,
            dashboard_id,
            path.stat().st_size,
        )
        return path.read_bytes(), filename
    if saw_inflight:
        logger.warning(
            "UPR PNG timed out waiting for PDF aes=%s dash=%s", aes_id, dashboard_id
        )
    return None


def start_assignment_export_job(app, job_id: str) -> None:
    start_ai_job_thread(app, str(job_id), _run_assignment_export_job)


def ensure_assignment_export_job_running(app, job_id: str) -> None:
    _maybe_cleanup_expired_jobs()
    reconcile_stale_ai_job(str(job_id))
    job = AIJob.query.get(str(job_id))
    if not job or job.job_type != ASSIGNMENT_EXPORT_JOB_TYPE:
        return
    if _status_str(job.status) not in _ACTIVE_JOB_STATUSES:
        return
    if is_job_thread_alive(str(job_id)):
        return
    if _status_str(job.status) == "queued":
        ensure_ai_job_running(app, str(job_id), _run_assignment_export_job)
        return
    job.status = "failed"
    job.error = "Server stopped during export."
    job.finished_at = utcnow()
    meta = dict(job.meta or {})
    meta["message"] = "Failed"
    meta["error"] = job.error
    job.meta = meta
    flag_modified(job, "meta")
    db.session.commit()


def build_assignment_export_status(job_id: str | None) -> dict[str, Any] | None:
    if not job_id:
        return None
    job = AIJob.query.get(str(job_id))
    if not job or job.job_type != ASSIGNMENT_EXPORT_JOB_TYPE:
        return None
    meta = dict(job.meta or {})
    return {
        "job_id": str(job.id),
        "status": _status_str(job.status),
        "aes_id": meta.get("aes_id"),
        "export_format": meta.get("export_format") or "pdf",
        "lang": meta.get("lang") or "en",
        "message": meta.get("message") or "",
        "progress": int(meta.get("progress") or 0),
        "total": int(meta.get("total") or 0),
        "elapsed_s": int(meta.get("elapsed_s") or 0),
        "chunk_done": int(meta.get("chunk_done") or 0),
        "chunk_total": int(meta.get("chunk_total") or 0),
        "filename": meta.get("filename"),
        "error": job.error or meta.get("error"),
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def serve_assignment_export(job_id: str, *, aes_id: int, as_attachment: bool = True):
    """Serve a completed export. Caller must already have assignment ACL."""
    job = AIJob.query.get(str(job_id))
    if not job or job.job_type != ASSIGNMENT_EXPORT_JOB_TYPE:
        raise NotFound("Export is not ready.")
    meta = dict(job.meta or {})
    if int(meta.get("aes_id") or 0) != int(aes_id):
        raise NotFound("Export is not ready.")
    if _status_str(job.status) != "completed":
        raise NotFound("Export is not ready.")
    raw_path = meta.get("output_path")
    filename = str(meta.get("filename") or "UPR visuals.pdf")
    if not raw_path:
        raise NotFound("Export is not ready.")
    path = Path(raw_path)
    job_root = _job_dir(str(job_id)).resolve()
    try:
        resolved = path.resolve()
    except OSError as exc:
        raise NotFound("Export is not ready.") from exc
    if job_root not in resolved.parents and resolved != job_root:
        raise NotFound("Export is not ready.")
    if not resolved.is_file() or resolved.stat().st_size <= 0:
        raise NotFound("Export is not ready.")
    mimetype = str(meta.get("mimetype") or "application/pdf")
    response = send_file(
        resolved,
        mimetype=mimetype,
        as_attachment=as_attachment,
        download_name=filename,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _set_meta(job: AIJob, **fields: Any) -> None:
    meta = dict(job.meta or {})
    meta.update(fields)
    job.meta = meta
    flag_modified(job, "meta")
    if fields.get("error"):
        job.error = fields["error"]


def _report(
    job: AIJob,
    message: str,
    *,
    step: int | None = None,
    total: int | None = None,
    elapsed: int | None = None,
    chunk_done: int | None = None,
    chunk_total: int | None = None,
    log: bool = True,
) -> None:
    if log:
        logger.info(
            "UPR assignment export job=%s step=%s/%s %s",
            job.id,
            step if step is not None else "-",
            total if total is not None else "-",
            message,
        )
    fields: dict[str, Any] = {"message": message}
    if step is not None:
        fields["progress"] = int(step)
    if total is not None:
        fields["total"] = int(total)
    if elapsed is not None:
        fields["elapsed_s"] = int(elapsed)
    if chunk_done is not None:
        fields["chunk_done"] = int(chunk_done)
        fields["chunk_total"] = int(chunk_total or 0)
    elif step is not None:
        fields["chunk_done"] = 0
        fields["chunk_total"] = 0
    _set_meta(job, **fields)
    db.session.commit()


def _run_assignment_export_job(app, job_id: str) -> None:
    with app.app_context():
        job = AIJob.query.get(str(job_id))
        if not job or job.job_type != ASSIGNMENT_EXPORT_JOB_TYPE:
            return
        if _status_str(job.status) in _TERMINAL_JOB_STATUSES:
            return
        item = (job.items or [None])[0]
        job.status = "running"
        job.started_at = job.started_at or utcnow()
        _report(job, "Starting export…", step=0, total=5, elapsed=0)
        if item is not None:
            item.status = "processing"
        db.session.commit()
        payload = dict(item.payload or {}) if item is not None else {}
        aes_id = int(payload.get("aes_id") or (job.meta or {}).get("aes_id") or 0)
        fmt = str(payload.get("export_format") or (job.meta or {}).get("export_format") or "pdf")
        dashboard_id = str(
            payload.get("dashboard_id") or (job.meta or {}).get("dashboard_id") or "combined"
        )
        lang = parse_export_language(payload.get("lang") or (job.meta or {}).get("lang"))
        job_dir = _job_dir(str(job_id))
        word_path = payload.get("word_path") or ""
        started = utcnow()
        logger.info(
            "UPR assignment export start job=%s aes=%s fmt=%s dash=%s lang=%s",
            job_id,
            aes_id,
            fmt,
            dashboard_id,
            lang,
        )
        try:
            if aes_id <= 0:
                raise RuntimeError("Export job is missing the assignment.")
            word_bytes = _read_job_word(job_dir, word_path)
            if word_bytes and fmt == "idml":
                _report(job, "Generating InDesign package…", step=1, total=3)
                data, filename = UprVisualsService.idml_zip_bytes(aes_id, word_bytes=word_bytes, lang=lang)
                mimetype = "application/zip"
            elif word_bytes:
                last_logged_elapsed = {"value": -10}

                def on_progress(
                    *,
                    step: int,
                    total: int,
                    message: str,
                    elapsed: int | None = None,
                    chunk_done: int | None = None,
                    chunk_total: int | None = None,
                    **_extra: Any,
                ) -> None:
                    secs = int(elapsed or 0)
                    chunking = chunk_done is not None
                    should_log = (
                        (chunking and chunk_done in {0, chunk_total})
                        or (not chunking and (elapsed is None or secs - last_logged_elapsed["value"] >= 10))
                    )
                    if should_log and elapsed is not None and not chunking:
                        last_logged_elapsed["value"] = secs
                    _report(
                        job,
                        message,
                        step=step,
                        total=total,
                        elapsed=elapsed,
                        chunk_done=chunk_done,
                        chunk_total=chunk_total,
                        log=should_log,
                    )

                data, filename = UprVisualsService.narrative_pdf_bytes(
                    aes_id,
                    word_bytes,
                    lang=lang,
                    on_progress=on_progress,
                )
                mimetype = "application/pdf"
            elif fmt == "png":
                pdf_job_id = find_reusable_assignment_export_job(
                    aes_id=aes_id,
                    export_format="pdf",
                    dashboard_id=dashboard_id,
                    lang=lang,
                )
                waiting_for_pdf = False
                if pdf_job_id:
                    pdf_job = AIJob.query.get(str(pdf_job_id))
                    waiting_for_pdf = bool(
                        pdf_job and _status_str(pdf_job.status) in _ACTIVE_JOB_STATUSES
                    )
                _report(
                    job,
                    "Waiting for PDF, then generating PNG…" if waiting_for_pdf else "Generating PNG…",
                    step=1,
                    total=2,
                )
                data, filename = UprVisualsService.png_bytes(aes_id, dashboard_id, lang=lang)
                mimetype = "image/png"
            elif fmt == "idml":
                _report(job, "Generating InDesign package…", step=1, total=2)
                data, filename = UprVisualsService.idml_zip_bytes(aes_id, lang=lang)
                mimetype = "application/zip"
            else:
                _report(job, "Generating PDF…", step=1, total=2)
                data, filename = UprVisualsService.pdf_bytes(aes_id, dashboard_id, lang=lang)
                mimetype = "application/pdf"
            output = job_dir / filename
            output.write_bytes(data)
            job.status = "completed"
            job.finished_at = utcnow()
            if item is not None:
                item.status = "completed"
                item.error = None
            elapsed = int((utcnow() - (started or utcnow())).total_seconds())
            _set_meta(
                job,
                message="Ready",
                filename=filename,
                output_path=str(output),
                mimetype=mimetype,
                progress=5,
                total=5,
                elapsed_s=elapsed,
                error=None,
            )
            db.session.commit()
            logger.info(
                "UPR assignment export done job=%s aes=%s fmt=%s (%s bytes, %ss)",
                job_id,
                aes_id,
                fmt,
                len(data),
                elapsed,
            )
        except Exception as exc:
            logger.exception("UPR assignment export failed: job=%s", job_id)
            from plugins.upr_visuals.errors import UprVisualsError

            message = str(exc) if isinstance(exc, UprVisualsError) else "Could not generate this report."
            job.status = "failed"
            job.finished_at = utcnow()
            job.error = message
            if item is not None:
                item.status = "failed"
                item.error = message
            _set_meta(job, message="Failed", error=message)
            db.session.commit()
            shutil.rmtree(job_dir, ignore_errors=True)
        finally:
            db.session.remove()
