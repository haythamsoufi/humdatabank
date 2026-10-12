"""Flask-facing helpers for the UPR Excel import wizard."""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import uuid
from typing import Any, Dict, List, Optional

from flask import current_app, session

from plugins.upr.excel._scripts_path import ensure_scripts_in_path as _ensure_scripts_in_path

logger = logging.getLogger(__name__)
_ANALYZE_LOCK = threading.Lock()
_ANALYZE_RUNNING: set[str] = set()
_ANALYZE_ERRORS: Dict[str, str] = {}


class UprExcelImportService:
    SESSION_FILE_KEY = "upr_excel_import_file"
    SESSION_ID_KEY = "upr_excel_import_id"

    @classmethod
    def _upload_dir(cls) -> str:
        path = os.path.join(current_app.instance_path, "upr_import_uploads")
        os.makedirs(path, exist_ok=True)
        return path

    @classmethod
    def store_upload(cls, file_bytes: bytes, original_filename: str) -> str:
        old_path = session.get(cls.SESSION_FILE_KEY)
        file_id = uuid.uuid4().hex
        ext = os.path.splitext(original_filename or "")[1].lower() or ".xlsx"
        tmp_path = os.path.join(cls._upload_dir(), f"{file_id}{ext}")
        with open(tmp_path, "wb") as fh:
            fh.write(file_bytes)
        if old_path and old_path != tmp_path:
            _ensure_scripts_in_path()
            from import_upr_excel_data import clear_upr_import_caches

            clear_upr_import_caches(old_path)
        session[cls.SESSION_FILE_KEY] = tmp_path
        session[cls.SESSION_ID_KEY] = file_id
        cls.start_background_analyze(tmp_path)
        return file_id

    @classmethod
    def stored_path(cls) -> Optional[str]:
        path = session.get(cls.SESSION_FILE_KEY)
        if path and os.path.isfile(path):
            return path
        return None

    @classmethod
    def start_background_analyze(cls, path: str) -> None:
        """Parse the workbook off the request thread so /analyze can poll."""
        if not path or current_app.config.get("TESTING"):
            return
        _ensure_scripts_in_path()
        from import_upr_excel_data import load_workbook_summary_cached

        if load_workbook_summary_cached(path):
            return
        with _ANALYZE_LOCK:
            if path in _ANALYZE_RUNNING:
                return
            _ANALYZE_RUNNING.add(path)
            _ANALYZE_ERRORS.pop(path, None)

        def _worker(workbook_path: str = path) -> None:
            try:
                from import_upr_excel_data import analyze_workbook

                analyze_workbook(workbook_path, use_cache=True)
            except Exception as exc:
                logger.exception("UPR background analyze failed for %s", workbook_path)
                with _ANALYZE_LOCK:
                    _ANALYZE_ERRORS[workbook_path] = str(exc)
            finally:
                with _ANALYZE_LOCK:
                    _ANALYZE_RUNNING.discard(workbook_path)

        threading.Thread(target=_worker, daemon=True, name="upr-excel-analyze").start()

    @classmethod
    def analyze_stored(cls) -> Dict[str, Any]:
        path = cls.stored_path()
        if not path:
            return {"success": False, "message": "No uploaded file in session. Upload again."}
        _ensure_scripts_in_path()
        from import_upr_excel_data import analyze_workbook, load_workbook_summary_cached

        cached = load_workbook_summary_cached(path)
        if cached:
            cached["file_id"] = session.get(cls.SESSION_ID_KEY)
            cached["pending"] = False
            return cached

        with _ANALYZE_LOCK:
            error = _ANALYZE_ERRORS.get(path)
        if error:
            return {"success": False, "message": error}

        if current_app.config.get("TESTING"):
            try:
                summary = analyze_workbook(path, use_cache=True)
                summary["file_id"] = session.get(cls.SESSION_ID_KEY)
                summary["pending"] = False
                return summary
            except Exception as exc:
                current_app.logger.error("UPR analyze failed: %s", exc, exc_info=True)
                return {"success": False, "message": str(exc)}

        with _ANALYZE_LOCK:
            running = path in _ANALYZE_RUNNING
        if not running:
            cls.start_background_analyze(path)
        return {"success": True, "pending": True, "file_id": session.get(cls.SESSION_ID_KEY)}

    @classmethod
    def plan(cls) -> Dict[str, Any]:
        """Verify every legal (template, round) target against the workbook and live data."""
        path = cls.stored_path()
        if not path:
            return {"success": False, "message": "No uploaded file in session."}
        _ensure_scripts_in_path()
        from upr_import_targets import build_import_plan_from_db

        try:
            plan = build_import_plan_from_db(path)
        except Exception as exc:
            current_app.logger.error("UPR import plan failed: %s", exc, exc_info=True)
            return {"success": False, "message": str(exc)}
        plan["file_id"] = session.get(cls.SESSION_ID_KEY)
        return plan

    @classmethod
    def preview(cls, *, targets: List[Any]) -> Dict[str, Any]:
        path = cls.stored_path()
        if not path:
            return {"success": False, "message": "No uploaded file in session."}
        _ensure_scripts_in_path()
        from upr_import_targets import ImportTargetError, preview_targets

        try:
            return preview_targets(path, targets)
        except ImportTargetError as exc:
            return {"success": False, "message": str(exc), "errors": exc.errors}
        except Exception as exc:
            current_app.logger.error("UPR preview failed: %s", exc, exc_info=True)
            return {"success": False, "message": str(exc)}

    @classmethod
    def run_import(
        cls,
        *,
        file_path: Optional[str] = None,
        targets: List[Any],
        dry_run: bool = False,
        batch_size: int = 1000,
        progress_cb=None,
        cancel_check=None,
        change_recorder=None,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        path = file_path or cls.stored_path()
        if not path:
            return {"success": False, "message": "No uploaded file in session."}

        preview_path = None
        if dry_run:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
            tmp.close()
            preview_path = tmp.name

        _ensure_scripts_in_path()
        from upr_import_targets import run_import_targets

        stats = run_import_targets(
            path,
            targets,
            dry_run=dry_run,
            batch_size=batch_size,
            preview_excel_path=preview_path,
            progress_cb=progress_cb,
            cancel_check=cancel_check,
            use_row_cache=True,
            use_transform_cache=True,
            change_recorder=change_recorder,
            user_id=user_id,
        )
        stats["success"] = stats.get("errors", 0) == 0
        if preview_path and stats.get("preview_path"):
            stats["preview_path"] = preview_path
        return stats
