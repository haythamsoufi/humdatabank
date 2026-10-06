"""FDRS structured Excel mode for template 21."""

from __future__ import annotations

from app.utils.data_quality_constants import FDRS_TEMPLATE_ID


def _template_id(assigned_form) -> int:
    if not assigned_form:
        return 0
    return int(getattr(assigned_form, "template_id", 0) or 0)


def assignment_uses_fdrs_excel(assigned_form) -> bool:
    """Return True when this assignment should use the FDRS data-collection workbook."""
    if _template_id(assigned_form) != FDRS_TEMPLATE_ID:
        return False
    if not assigned_form:
        return False
    return bool(getattr(assigned_form, "enable_export_excel", False)) or bool(
        getattr(assigned_form, "enable_import_excel", False)
    )


def resolve_fdrs_excel_mode(assigned_form) -> str | None:
    if assignment_uses_fdrs_excel(assigned_form):
        return "fdrs"
    return None
