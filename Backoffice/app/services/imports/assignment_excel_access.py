"""Assignment-level flags for form Excel export/import and PDF export.

Admins only toggle the standard Export/Import Excel buttons. Template 33
(UPR Country Reporting) and template 24 (Unified Country Plan) then resolve
to their structured workbooks; every other template uses the generic
item-row workbook.

Dedicated ``enable_upr_country_reporting_excel`` /
``enable_unified_country_plan_excel`` columns are legacy and still honored
when the standard flags are off, so existing assignments keep working.
"""

from app.utils.data_quality_constants import (
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


def assignment_excel_export_enabled(assigned_form) -> bool:
    """Return True when the assignment should offer Excel export."""
    if not assigned_form:
        return False
    return bool(getattr(assigned_form, "enable_export_excel", False)) or _legacy_custom_excel_enabled(
        assigned_form
    )


def assignment_excel_import_enabled(assigned_form) -> bool:
    """Return True when the assignment should offer Excel import."""
    if not assigned_form:
        return False
    return bool(getattr(assigned_form, "enable_import_excel", False)) or _legacy_custom_excel_enabled(
        assigned_form
    )


def assignment_uses_upr_country_reporting_excel(assigned_form) -> bool:
    """Return True when this assignment should use the T33 structured workbook."""
    if _template_id(assigned_form) != UPR_REPORTING_TEMPLATE_ID:
        return False
    return assignment_excel_export_enabled(assigned_form) or assignment_excel_import_enabled(
        assigned_form
    )


def assignment_uses_unified_country_plan_excel(assigned_form) -> bool:
    """Return True when this assignment should use the T24 structured workbook."""
    if _template_id(assigned_form) != UPR_PLANNING_TEMPLATE_ID:
        return False
    return assignment_excel_export_enabled(assigned_form) or assignment_excel_import_enabled(
        assigned_form
    )


def assignment_uses_export_excel(assigned_form) -> bool:
    """Return True when this assignment has generic Excel export enabled."""
    if assignment_uses_upr_country_reporting_excel(assigned_form):
        return False
    if assignment_uses_unified_country_plan_excel(assigned_form):
        return False
    return bool(getattr(assigned_form, "enable_export_excel", False))


def assignment_uses_import_excel(assigned_form) -> bool:
    """Return True when this assignment has generic Excel import enabled."""
    if assignment_uses_upr_country_reporting_excel(assigned_form):
        return False
    if assignment_uses_unified_country_plan_excel(assigned_form):
        return False
    return bool(getattr(assigned_form, "enable_import_excel", False))


def assignment_uses_export_pdf(assigned_form) -> bool:
    """Return True when this assignment has PDF export enabled."""
    return bool(getattr(assigned_form, "enable_export_pdf", False))


def resolve_assignment_excel_ui(assigned_form) -> dict:
    """Return entry-form Excel UI flags derived from template + standard toggles."""
    show_export = assignment_excel_export_enabled(assigned_form)
    show_import = assignment_excel_import_enabled(assigned_form)
    if assignment_uses_upr_country_reporting_excel(assigned_form):
        mode = "upr"
    elif assignment_uses_unified_country_plan_excel(assigned_form):
        mode = "ucp"
    elif show_export or show_import:
        mode = "generic"
    else:
        mode = None
    return {
        "mode": mode,
        "show_export": bool(mode) and show_export,
        "show_import": bool(mode) and show_import,
    }


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


def populate_standard_excel_flags_from_legacy(assignment, form) -> None:
    """Check standard Excel boxes when only a legacy dedicated flag is set."""
    if not assignment or not form:
        return
    if getattr(assignment, "enable_export_excel", False) or getattr(
        assignment, "enable_import_excel", False
    ):
        return
    if not _legacy_custom_excel_enabled(assignment):
        return
    if hasattr(form, "enable_export_excel"):
        form.enable_export_excel.data = True
    if hasattr(form, "enable_import_excel"):
        form.enable_import_excel.data = True
