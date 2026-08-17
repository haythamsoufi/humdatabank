"""Assignment-level flags for generic form Excel export/import and PDF export."""


def assignment_uses_export_excel(assigned_form) -> bool:
    """Return True when this assignment has generic Excel export enabled."""
    return bool(getattr(assigned_form, "enable_export_excel", False))


def assignment_uses_import_excel(assigned_form) -> bool:
    """Return True when this assignment has generic Excel import enabled."""
    return bool(getattr(assigned_form, "enable_import_excel", False))


def assignment_uses_export_pdf(assigned_form) -> bool:
    """Return True when this assignment has PDF export enabled."""
    return bool(getattr(assigned_form, "enable_export_pdf", False))
