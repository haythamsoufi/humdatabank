"""UPR structured Excel mode for country plan (T24), country reporting (T33), and PNS forms (T22, T23)."""

from __future__ import annotations

from plugins.upr.catalog import (
    PNS_PLAN_TEMPLATE_ID,
    PNS_REPORT_TEMPLATE_ID,
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


def assignment_uses_pns_planning_excel(assigned_form) -> bool:
    """Return True when this assignment should use the T22 PNS Planning workbook."""
    if _template_id(assigned_form) != PNS_PLAN_TEMPLATE_ID:
        return False
    return _excel_enabled(assigned_form)


def assignment_uses_pns_reporting_excel(assigned_form) -> bool:
    """Return True when this assignment should use the T23 PNS Reporting workbook."""
    if _template_id(assigned_form) != PNS_REPORT_TEMPLATE_ID:
        return False
    return _excel_enabled(assigned_form)


def resolve_upr_excel_mode(assigned_form) -> str | None:
    """Return the structured UPR workbook mode, or None for the generic workbook."""
    if assignment_uses_upr_country_reporting_excel(assigned_form):
        return "upr"
    if assignment_uses_unified_country_plan_excel(assigned_form):
        return "ucp"
    if assignment_uses_pns_planning_excel(assigned_form):
        return "pns_plan"
    if assignment_uses_pns_reporting_excel(assigned_form):
        return "pns_report"
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
