# ========== Template Excel Import/Export Service ==========
"""
Thin orchestrator for template Excel export/import.

Implementation is split across excel_base, excel_export, excel_import, and matrix_import.
"""

from app.services.templates.excel_base import TemplateExcelBase
from app.services.templates.excel_export import TemplateExcelExportMixin
from app.services.templates.excel_import import TemplateExcelImportMixin
from app.services.templates.matrix_import import TemplateExcelMatrixMixin


class TemplateExcelService(TemplateExcelImportMixin, TemplateExcelExportMixin):
    """Service for template Excel export/import operations."""

    pass


__all__ = ["TemplateExcelService"]
