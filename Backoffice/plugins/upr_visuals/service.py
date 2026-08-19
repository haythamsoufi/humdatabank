"""Bulk PNG generation jobs and single-dashboard PNG/PDF export for UPR visuals."""

from __future__ import annotations

import io
import logging
import threading
import uuid
import zipfile
from pathlib import Path
from typing import Any, ClassVar

from flask import current_app
from werkzeug.exceptions import NotFound

from app.services.platform import storage_service
from app.utils.datetime_helpers import utcnow
from plugins.upr_visuals.catalog import DASHBOARD_BY_ID, dashboards_for_kind, kind_for_template
from plugins.upr_visuals.data import UprVisualsError, build_payload
from plugins.upr_visuals.raster import render_pdf_bytes, render_png
from plugins.upr_visuals.render import render_dashboard_html

logger = logging.getLogger(__name__)

STORAGE_CATEGORY = "upr_visuals"
STATUS_NAME = "status.json"

_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}
_threads: dict[str, threading.Thread] = {}


def visual_export_filename(meta: dict[str, Any], dashboard_id: str, ext: str) -> str:
    iso3 = str(meta.get("iso3") or "UNK").replace("/", "-")
    round_code = str(meta.get("round_code") or meta.get("period_name") or "round").replace("/", "-")
    suffix = ext.lstrip(".").lower()
    return f"{iso3}_{round_code}_{dashboard_id}.{suffix}"


class UprVisualsService:
    _lock: ClassVar[threading.Lock] = _lock

    @classmethod
    def start_bulk(
        cls,
        *,
        template_id: int,
        period_name: str,
        dashboard_ids: list[str],
        aes_ids: list[int] | None = None,
    ) -> str:
        job_id = str(uuid.uuid4())
        kind = kind_for_template(int(template_id))
        allowed = {spec.id for spec in dashboards_for_kind(kind)}
        selected = [did for did in dashboard_ids if did in allowed] or ["combined"]
        now = utcnow().isoformat()
        status = {
            "job_id": job_id,
            "status": "queued",
            "template_id": int(template_id),
            "period_name": period_name,
            "dashboard_ids": selected,
            "aes_ids": [int(i) for i in (aes_ids or [])],
            "progress": 0,
            "total": 0,
            "message": "Queued",
            "zip_key": None,
            "error": None,
            "created_at": now,
            "finished_at": None,
        }
        with cls._lock:
            if any(job.get("status") in {"queued", "running"} for job in _jobs.values()):
                raise RuntimeError("A UPR visuals export is already running.")
            _jobs[job_id] = status

        app = current_app._get_current_object()
        thread = threading.Thread(
            target=cls._run_bulk,
            args=(app, job_id),
            daemon=True,
            name=f"upr-visuals-{job_id[:8]}",
        )
        _threads[job_id] = thread
        thread.start()
        return job_id

    @classmethod
    def get_status(cls, job_id: str | None = None) -> dict[str, Any]:
        with cls._lock:
            if job_id:
                return dict(_jobs.get(job_id) or {})
            running = [job for job in _jobs.values() if job.get("status") in {"queued", "running"}]
            if running:
                return dict(running[-1])
            if _jobs:
                latest = max(_jobs.values(), key=lambda job: job.get("created_at") or "")
                return dict(latest)
        return {}

    @classmethod
    def cancel(cls, job_id: str) -> bool:
        with cls._lock:
            job = _jobs.get(job_id)
            if not job or job.get("status") not in {"queued", "running"}:
                return False
            job["status"] = "cancelled"
            job["finished_at"] = utcnow().isoformat()
            job["message"] = "Cancelled"
            return True

    @classmethod
    def serve_zip(cls, job_id: str):
        job = cls.get_status(job_id)
        key = job.get("zip_key")
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

    @classmethod
    def png_bytes(cls, aes_id: int, dashboard_id: str) -> tuple[bytes, str]:
        payload, html = cls._dashboard_html(aes_id, dashboard_id)
        filename = visual_export_filename(payload.get("meta") or {}, dashboard_id, "png")
        tmp = Path(current_app.instance_path) / "upr_visuals_tmp" / f"{uuid.uuid4().hex}_{filename}"
        render_png(html, tmp, dashboard_id=dashboard_id)
        data = tmp.read_bytes()
        try:
            tmp.unlink()
        except OSError:
            pass
        return data, filename

    @classmethod
    def pdf_bytes(cls, aes_id: int, dashboard_id: str) -> tuple[bytes, str]:
        payload, html = cls._dashboard_html(aes_id, dashboard_id)
        filename = visual_export_filename(payload.get("meta") or {}, dashboard_id, "pdf")
        return render_pdf_bytes(html, dashboard_id=dashboard_id), filename

    @classmethod
    def _dashboard_html(cls, aes_id: int, dashboard_id: str) -> tuple[dict[str, Any], str]:
        payload = build_payload(aes_id)
        if dashboard_id not in DASHBOARD_BY_ID:
            raise UprVisualsError(f"Unknown dashboard: {dashboard_id}")
        return payload, render_dashboard_html(payload, dashboard_id)

    @classmethod
    def _run_bulk(cls, app, job_id: str) -> None:
        with app.app_context():
            job = cls.get_status(job_id)
            try:
                cls._update(job_id, status="running", message="Loading assignments…")
                from plugins.upr_visuals.data import list_assignments_for_bulk

                assignments = list_assignments_for_bulk(job["template_id"], job.get("period_name"))
                wanted = set(job.get("aes_ids") or [])
                if wanted:
                    assignments = [row for row in assignments if row["aes_id"] in wanted]
                dashboards = job.get("dashboard_ids") or ["combined"]
                total = max(len(assignments) * len(dashboards), 1)
                cls._update(job_id, total=total, message="Rendering…")
                buffer = io.BytesIO()
                done = 0
                with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for row in assignments:
                        if cls.get_status(job_id).get("status") == "cancelled":
                            return
                        try:
                            payload = build_payload(row["aes_id"])
                        except Exception as exc:
                            logger.warning("UPR visuals skip aes %s: %s", row["aes_id"], exc)
                            done += len(dashboards)
                            cls._update(job_id, progress=done)
                            continue
                        meta = payload["meta"]
                        iso3 = meta.get("iso3") or "UNK"
                        round_code = meta.get("round_code") or "round"
                        folder = f"{iso3}_{round_code}"
                        available = {item.get("id") for item in payload.get("dashboards") or []}
                        for dashboard_id in dashboards:
                            if str(dashboard_id).startswith("emergency_") and dashboard_id not in available:
                                done += 1
                                cls._update(job_id, progress=done)
                                continue
                            html = render_dashboard_html(payload, dashboard_id)
                            tmp = Path(app.instance_path) / "upr_visuals_tmp" / job_id / f"{dashboard_id}.png"
                            render_png(html, tmp, dashboard_id=dashboard_id)
                            zf.write(tmp, arcname=f"{folder}/{dashboard_id}.png")
                            try:
                                tmp.unlink()
                            except OSError:
                                pass
                            done += 1
                            cls._update(job_id, progress=done, message=f"{iso3} · {dashboard_id}")
                zip_key = f"exports/{job_id}/upr-visuals.zip"
                storage_service.upload(STORAGE_CATEGORY, zip_key, buffer.getvalue())
                cls._update(
                    job_id,
                    status="completed",
                    progress=total,
                    zip_key=zip_key,
                    message="Done",
                    finished_at=utcnow().isoformat(),
                )
            except Exception as exc:
                logger.exception("UPR visuals bulk export failed")
                cls._update(
                    job_id,
                    status="failed",
                    error=str(exc),
                    message="Failed",
                    finished_at=utcnow().isoformat(),
                )

    @classmethod
    def _update(cls, job_id: str, **fields: Any) -> None:
        with cls._lock:
            job = _jobs.get(job_id)
            if not job:
                return
            job.update(fields)
