"""Single-assignment narrative/InDesign export as a background AIJob.

WeasyPrint + Word merge take longer than the HTTP stuck-request window, so the
assignment POST only queues work. The browser polls status and downloads when ready.
"""

from __future__ import annotations

import logging
import shutil
import uuid
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

logger = logging.getLogger(__name__)

ASSIGNMENT_EXPORT_JOB_TYPE = "upr_visuals.assignment_export"
_ACTIVE_JOB_STATUSES = ("queued", "running", "cancel_requested")
_TERMINAL_JOB_STATUSES = frozenset({"completed", "failed", "cancelled"})


def _status_str(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value or "")


def _job_dir(job_id: str) -> Path:
    return Path(current_app.instance_path) / "upr_visuals_tmp" / str(job_id)


def create_assignment_export_job(
    *,
    user_id: int,
    aes_id: int,
    export_format: str,
    word_bytes: bytes,
    lang: str = "en",
) -> str:
    fmt = "idml" if str(export_format or "").strip().lower() == "idml" else "pdf"
    lang = parse_export_language(lang)
    job_id = str(uuid.uuid4())
    job_dir = _job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    word_path = job_dir / "narrative.docx"
    word_path.write_bytes(word_bytes)
    now = utcnow()
    meta = {
        "aes_id": int(aes_id),
        "export_format": fmt,
        "lang": lang,
        "message": "Queued",
        "progress": 0,
        "total": 5,
        "elapsed_s": 0,
        "filename": None,
        "output_path": None,
        "mimetype": None,
        "error": None,
    }
    payload = {
        "aes_id": int(aes_id),
        "export_format": fmt,
        "lang": lang,
        "word_path": str(word_path),
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


def start_assignment_export_job(app, job_id: str) -> None:
    start_ai_job_thread(app, str(job_id), _run_assignment_export_job)


def ensure_assignment_export_job_running(app, job_id: str) -> None:
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


def serve_assignment_export(job_id: str, *, aes_id: int):
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
        as_attachment=True,
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
        lang = parse_export_language(payload.get("lang") or (job.meta or {}).get("lang"))
        word_path = Path(str(payload.get("word_path") or ""))
        job_dir = _job_dir(str(job_id))
        started = utcnow()
        logger.info(
            "UPR assignment export start job=%s aes=%s fmt=%s lang=%s",
            job_id,
            aes_id,
            fmt,
            lang,
        )
        try:
            if aes_id <= 0 or not word_path.is_file():
                raise RuntimeError("Export job is missing the Word document.")
            word_bytes = word_path.read_bytes()
            if fmt == "idml":
                _report(job, "Generating InDesign package…", step=1, total=3)
                data, filename = UprVisualsService.idml_zip_bytes(aes_id, word_bytes=word_bytes, lang=lang)
                mimetype = "application/zip"
            else:
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
