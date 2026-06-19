"""Flask-facing helpers for the UPR Excel import wizard."""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from typing import Any, Dict, List, Optional

from flask import current_app, session

# Cached resolved scripts directory; set on first use inside an app context.
_SCRIPTS_DIR: Optional[str] = None


def _ensure_scripts_in_path() -> None:
    """Insert the Backoffice/scripts directory into sys.path once per process."""
    global _SCRIPTS_DIR
    if _SCRIPTS_DIR is not None:
        return
    scripts_dir = os.path.normpath(os.path.join(current_app.root_path, "..", "scripts"))
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    _SCRIPTS_DIR = scripts_dir


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
        file_id = uuid.uuid4().hex
        ext = os.path.splitext(original_filename or "")[1].lower() or ".xlsx"
        tmp_path = os.path.join(cls._upload_dir(), f"{file_id}{ext}")
        with open(tmp_path, "wb") as fh:
            fh.write(file_bytes)
        session[cls.SESSION_FILE_KEY] = tmp_path
        session[cls.SESSION_ID_KEY] = file_id
        return file_id

    @classmethod
    def stored_path(cls) -> Optional[str]:
        path = session.get(cls.SESSION_FILE_KEY)
        if path and os.path.isfile(path):
            return path
        return None

    @classmethod
    def analyze_stored(cls) -> Dict[str, Any]:
        path = cls.stored_path()
        if not path:
            return {"success": False, "message": "No uploaded file in session. Upload again."}
        _ensure_scripts_in_path()
        from import_upr_excel_data import analyze_workbook

        try:
            summary = analyze_workbook(path)
            summary["file_id"] = session.get(cls.SESSION_ID_KEY)
            return summary
        except Exception as exc:
            current_app.logger.error("UPR analyze failed: %s", exc, exc_info=True)
            return {"success": False, "message": str(exc)}

    @classmethod
    def preview(
        cls,
        *,
        template_ids: List[int],
        rounds: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        path = cls.stored_path()
        if not path:
            return {"success": False, "message": "No uploaded file in session."}
        _ensure_scripts_in_path()
        from import_upr_excel_data import (
            build_import_context,
            load_upr_data_sheet,
            summarize_warnings,
            transform_to_import_rows,
        )

        try:
            _, rows = load_upr_data_sheet(path)
            round_set = {r.strip().upper() for r in (rounds or []) if r and str(r).strip()} or None
            ctx = build_import_context(template_ids)
            import_rows = transform_to_import_rows(rows, ctx, template_ids=template_ids, rounds=round_set)
            by_item: Dict[str, int] = {}
            by_iso3: Dict[str, int] = {}
            for row in import_rows:
                item = row.get("item_id") or row.get("form_item_id")
                iso3 = row.get("_debug_iso3") or ""
                if item:
                    by_item[str(item)] = by_item.get(str(item), 0) + 1
                if iso3:
                    by_iso3[iso3] = by_iso3.get(iso3, 0) + 1
            warning_summary = summarize_warnings(ctx.warnings)
            return {
                "success": True,
                "transformed_rows": len(import_rows),
                "by_item": by_item,
                "countries": len(by_iso3),
                **warning_summary,
            }
        except Exception as exc:
            current_app.logger.error("UPR preview failed: %s", exc, exc_info=True)
            return {"success": False, "message": str(exc)}

    @classmethod
    def run_import(
        cls,
        *,
        file_path: Optional[str] = None,
        template_ids: List[int],
        rounds: Optional[List[str]] = None,
        dry_run: bool = False,
        batch_size: int = 1000,
        ensure_staff_matrix: bool = True,  # kept for API backward compat, no longer used
        progress_cb=None,
        cancel_check=None,
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
        from import_upr_excel_data import run_upr_import

        stats = run_upr_import(
            path,
            template_ids=template_ids,
            rounds=rounds,
            dry_run=dry_run,
            batch_size=batch_size,
            preview_excel_path=preview_path,
            progress_cb=progress_cb,
            cancel_check=cancel_check,
            ensure_staff_matrix=ensure_staff_matrix,  # backward compat, ignored
        )
        stats["success"] = stats.get("errors", 0) == 0
        if preview_path:
            stats["preview_path"] = preview_path
        return stats
