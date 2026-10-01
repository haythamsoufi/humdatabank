"""Assignment-level flags for form Excel export/import and PDF export.

Admins only toggle the standard Export/Import Excel buttons. UPR Country
Reporting and Unified Country Plan then resolve to their structured
workbooks; every other template uses the generic item-row workbook.

Dedicated ``enable_upr_country_reporting_excel`` /
``enable_unified_country_plan_excel`` columns are legacy and still honored
when the standard flags are off, so existing assignments keep working.

Plugin helpers are imported lazily so this module can load during
``plugins.upr`` bootstrap without a circular import.
"""


def _legacy_custom_excel_enabled(assigned_form) -> bool:
    return bool(
        getattr(assigned_form, "enable_upr_country_reporting_excel", False)
        or getattr(assigned_form, "enable_unified_country_plan_excel", False)
    )


def _upr_assignment_access():
    from plugins.upr.excel.assignment_access import (
        assignment_uses_unified_country_plan_excel,
        assignment_uses_upr_country_reporting_excel,
        resolve_upr_excel_mode,
        sync_assignment_custom_excel_flags,
    )

    return (
        assignment_uses_upr_country_reporting_excel,
        assignment_uses_unified_country_plan_excel,
        resolve_upr_excel_mode,
        sync_assignment_custom_excel_flags,
    )


def assignment_uses_upr_country_reporting_excel(assigned_form) -> bool:
    uses_upr, _, _, _ = _upr_assignment_access()
    return uses_upr(assigned_form)


def assignment_uses_unified_country_plan_excel(assigned_form) -> bool:
    _, uses_ucp, _, _ = _upr_assignment_access()
    return uses_ucp(assigned_form)


def assignment_excel_export_enabled(assigned_form) -> bool:
    """Return True when the assignment should offer Excel export."""
    if not assigned_form:
        return False
    return bool(getattr(assigned_form, "enable_export_excel", False)) or _legacy_custom_excel_enabled(
        assigned_form
    )


MAX_ASSIGNMENT_EXCEL_BYTES = 10 * 1024 * 1024


def assignment_excel_upload_error(excel_file, *, max_bytes: int = MAX_ASSIGNMENT_EXCEL_BYTES) -> str | None:
    """Return an error message when an assignment Excel upload is empty, not xlsx, or over ``max_bytes``."""
    if not excel_file or not getattr(excel_file, "filename", ""):
        return "No Excel file selected."
    if not excel_file.filename.lower().endswith(".xlsx"):
        return "Invalid file type. Please upload a .xlsx file."
    file_size = excel_file.content_length
    if file_size is None:
        excel_file.seek(0, 2)
        file_size = excel_file.tell()
        excel_file.seek(0)
    if file_size > max_bytes:
        limit_mb = max_bytes / (1024 * 1024)
        return (
            f"File size ({file_size / (1024 * 1024):.2f}MB) exceeds the maximum allowed size of {limit_mb:.0f}MB."
        )
    return None


def assignment_excel_import_enabled(assigned_form) -> bool:
    """Return True when the assignment should offer Excel import."""
    if not assigned_form:
        return False
    return bool(getattr(assigned_form, "enable_import_excel", False)) or _legacy_custom_excel_enabled(
        assigned_form
    )


def assignment_uses_export_excel(assigned_form) -> bool:
    """Return True when this assignment has generic Excel export enabled."""
    _, _, resolve_mode, _ = _upr_assignment_access()
    if resolve_mode(assigned_form):
        return False
    return bool(getattr(assigned_form, "enable_export_excel", False))


def assignment_uses_import_excel(assigned_form) -> bool:
    """Return True when this assignment has generic Excel import enabled."""
    _, _, resolve_mode, _ = _upr_assignment_access()
    if resolve_mode(assigned_form):
        return False
    return bool(getattr(assigned_form, "enable_import_excel", False))


def assignment_uses_export_pdf(assigned_form) -> bool:
    """Return True when this assignment has PDF export enabled."""
    return bool(getattr(assigned_form, "enable_export_pdf", False))


def resolve_assignment_excel_ui(assigned_form) -> dict:
    """Return entry-form Excel UI flags derived from template + standard toggles."""
    _, _, resolve_mode, _ = _upr_assignment_access()
    show_export = assignment_excel_export_enabled(assigned_form)
    show_import = assignment_excel_import_enabled(assigned_form)
    mode = resolve_mode(assigned_form)
    if not mode and (show_export or show_import):
        mode = "generic"
    return {
        "mode": mode,
        "show_export": bool(mode) and show_export,
        "show_import": bool(mode) and show_import,
    }


def sync_assignment_custom_excel_flags(assignment) -> None:
    _, _, _, sync_flags = _upr_assignment_access()
    sync_flags(assignment)


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
