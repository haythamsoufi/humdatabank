"""FDRS assignment Excel export/import handlers (registered on the core excel blueprint)."""

from __future__ import annotations

from app.services.imports.structured_excel_routes import register_structured_excel_routes
from plugins.fdrs.excel.assignment_access import assignment_uses_fdrs_excel
from plugins.fdrs.excel.fdrs_excel_service import FDRS_EXCEL_LABEL, FdrsExcelService


def register_fdrs_excel_routes(excel_bp):
    register_structured_excel_routes(
        excel_bp,
        url_slug="fdrs",
        endpoint="fdrs_template",
        label=FDRS_EXCEL_LABEL,
        export_type="fdrs",
        uses_assignment=assignment_uses_fdrs_excel,
        service=FdrsExcelService,
    )
