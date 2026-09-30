"""UPR structured Excel mode for country reporting (T33) and country plan (T24)."""

from __future__ import annotations

from plugins.upr.catalog import (
    UPR_PLANNING_TEMPLATE_ID,
    UPR_REPORTING_TEMPLATE_ID,
)


def _template_id(assigned_form) -> int:
    if not assigned_form:
        return 0
    return int(getattr(assigned_form, "template_id", 0) or 0)


def _legacy_custom_excel_enabled(assigned_form) -> bool:
    return bool(
        getattr(assigned_form, "enable_upr_country_reporting_excel", False)
        or getattr(assigned_form, "enable_unified_country_plan_excel", False)
    )


def _excel_enabled(assigned_form) -> bool:
    if not assigned_form:
        return False
    return bool(getattr(assigned_form, "enable_export_excel", False)) or bool(
        getattr(assigned_form, "enable_import_excel", False)
    ) or _legacy_custom_excel_enabled(assigned_form)


def assignment_uses_upr_country_reporting_excel(assigned_form) -> bool:
    """Return True when this assignment should use the T33 structured workbook."""
    if _template_id(assigned_form) != UPR_REPORTING_TEMPLATE_ID:
        return False
    return _excel_enabled(assigned_form)


def assignment_uses_unified_country_plan_excel(assigned_form) -> bool:
    """Return True when this assignment should use the T24 structured workbook."""
    if _template_id(assigned_form) != UPR_PLANNING_TEMPLATE_ID:
        return False
    return _excel_enabled(assigned_form)


def resolve_upr_excel_mode(assigned_form) -> str | None:
    """Return ``upr`` or ``ucp`` when a structured UPR workbook applies."""
    if assignment_uses_upr_country_reporting_excel(assigned_form):
        return "upr"
    if assignment_uses_unified_country_plan_excel(assigned_form):
        return "ucp"
    return None


def sync_assignment_custom_excel_flags(assignment) -> None:
    """Keep legacy dedicated columns aligned with the standard Excel toggles."""
    excel_on = bool(
        getattr(assignment, "enable_export_excel", False)
        or getattr(assignment, "enable_import_excel", False)
    )
    template_id = _template_id(assignment)
    assignment.enable_upr_country_reporting_excel = (
        excel_on and template_id == UPR_REPORTING_TEMPLATE_ID
    )
    assignment.enable_unified_country_plan_excel = (
        excel_on and template_id == UPR_PLANNING_TEMPLATE_ID
    )
