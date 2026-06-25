"""Flask-facing helpers for T33 UPR Country Reporting Excel template export/import."""

from __future__ import annotations

import io
import os
import sys
import tempfile
from typing import Any, Dict, Tuple

from flask import current_app

UPR_COUNTRY_REPORTING_LABEL = "UPR Country Reporting"

_SCRIPTS_DIR: str | None = None


def _ensure_scripts_in_path() -> None:
    global _SCRIPTS_DIR
    if _SCRIPTS_DIR is not None:
        return
    scripts_dir = os.path.normpath(os.path.join(current_app.root_path, "..", "scripts"))
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    _SCRIPTS_DIR = scripts_dir


class UprCountryReportingExcelService:
    TEMPLATE_PATH_CONFIG_KEY = "UPR_COUNTRY_REPORTING_TEMPLATE_PATH"
    LEGACY_TEMPLATE_PATH_CONFIG_KEY = "MYR_REPORTING_TEMPLATE_PATH"
    DEFAULT_TEMPLATE_REL = os.path.join("static", "templates", "upr_country_reporting_template.xlsx")
    LEGACY_TEMPLATE_REL = os.path.join("static", "templates", "myr_reporting_template.xlsx")

    @classmethod
    def get_template_path(cls) -> str:
        configured = current_app.config.get(cls.TEMPLATE_PATH_CONFIG_KEY)
        if configured and os.path.isfile(configured):
            return configured
        legacy = current_app.config.get(cls.LEGACY_TEMPLATE_PATH_CONFIG_KEY)
        if legacy and os.path.isfile(legacy):
            return legacy
        default_path = os.path.join(current_app.root_path, cls.DEFAULT_TEMPLATE_REL)
        if os.path.isfile(default_path):
            return default_path
        legacy_path = os.path.join(current_app.root_path, cls.LEGACY_TEMPLATE_REL)
        if os.path.isfile(legacy_path):
            return legacy_path
        raise FileNotFoundError(
            f"{UPR_COUNTRY_REPORTING_LABEL} template not found. "
            f"Set {cls.TEMPLATE_PATH_CONFIG_KEY} or place the file at {default_path}"
        )

    @classmethod
    def build_workbook(cls, aes) -> Tuple[io.BytesIO, str]:
        """Export assignment data into the UPR Country Reporting Excel template."""
        _ensure_scripts_in_path()
        from upr_country_reporting_excel_template import build_upr_country_reporting_export

        template_path = cls.get_template_path()
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        tmp.close()
        try:
            result = build_upr_country_reporting_export(int(aes.id), template_path, tmp.name)
            with open(tmp.name, "rb") as fh:
                output = io.BytesIO(fh.read())
            output.seek(0)
            filename = result.get("filename") or "UPR_Country_Reporting.xlsx"
            return output, filename
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    @classmethod
    def import_data(cls, aes, file_bytes: bytes) -> Dict[str, Any]:
        """Import a filled UPR Country Reporting workbook into the assignment."""
        _ensure_scripts_in_path()
        from upr_country_reporting_excel_template import run_upr_country_reporting_import

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        try:
            tmp.write(file_bytes)
            tmp.close()
            result = run_upr_country_reporting_import(int(aes.id), tmp.name, dry_run=False)
            result["success"] = int(result.get("errors", 0) or 0) == 0
            result["updated_count"] = int(result.get("inserted", 0) or 0) + int(result.get("updated", 0) or 0)
            return result
        except Exception as exc:
            current_app.logger.error("%s import failed: %s", UPR_COUNTRY_REPORTING_LABEL, exc, exc_info=True)
            return {"success": False, "errors": 1, "message": str(exc), "updated_count": 0}
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
