"""Flask-facing helpers for T33 UPR Country Reporting Excel template export/import."""

from __future__ import annotations

import io
import os
import tempfile
from typing import Any, Dict, Tuple

from flask import current_app

from app.services.imports.assignment_excel_access import (  # noqa: F401
    assignment_uses_upr_country_reporting_excel,
)
from app.services.upr._scripts_path import ensure_scripts_in_path as _ensure_scripts_in_path

UPR_COUNTRY_REPORTING_LABEL = "UPR Country Reporting"


class UprCountryReportingExcelService:
    TEMPLATE_PATH_CONFIG_KEY = "UPR_COUNTRY_REPORTING_TEMPLATE_PATH"
    LEGACY_TEMPLATE_PATH_CONFIG_KEY = "MYR_REPORTING_TEMPLATE_PATH"
    DEFAULT_TEMPLATE_REL = os.path.join("static", "templates", "unified_country_report.xlsx")
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
    def validate_import_file(cls, aes, file_bytes: bytes) -> Dict[str, Any]:
        """Validate a filled workbook before UPR Country Reporting import."""
        _ensure_scripts_in_path()
        from upr_country_reporting_excel_template import (
            validate_upr_country_reporting_import_file,
            _load_assignment_meta,
        )

        import openpyxl

        _, country_name, _iso3, period = _load_assignment_meta(int(aes.id))
        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        except Exception as exc:
            current_app.logger.error("%s validate: failed to load workbook: %s", UPR_COUNTRY_REPORTING_LABEL, exc)
            return {
                "valid": False,
                "message": "Invalid Excel file. Check the file format and try again.",
                "errors": ["Failed to load Excel file."],
                "warnings": [],
                "preview": {},
            }
        try:
            return validate_upr_country_reporting_import_file(
                wb,
                expected_country=country_name,
                expected_period=period,
            )
        finally:
            wb.close()

    @classmethod
    def import_data(cls, aes, file_bytes: bytes, *, persist: bool = True) -> Dict[str, Any]:
        """Import a filled UPR Country Reporting workbook into the assignment.

        When ``persist`` is False, returns a client payload for staging in the form UI
        without writing to the database.
        """
        _ensure_scripts_in_path()
        from upr_country_reporting_excel_template import run_upr_country_reporting_import

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        try:
            tmp.write(file_bytes)
            tmp.close()
            result = run_upr_country_reporting_import(int(aes.id), tmp.name, dry_run=False, persist=persist)
            if result.get("stage_only"):
                result["success"] = True
                return result
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

    @classmethod
    def import_data_for_form(cls, aes, file_bytes: bytes) -> Dict[str, Any]:
        """Parse workbook and return a client payload (no database writes)."""
        return cls.import_data(aes, file_bytes, persist=False)
