"""Build PDF and Excel snapshots for assignment submit/approve emails."""

from __future__ import annotations

from typing import List, Optional, Tuple

from flask import current_app, g, has_app_context

EXCEL_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_CONTENT_TYPE = "application/pdf"
MAX_EMAIL_ATTACHMENT_BYTES = 8 * 1024 * 1024

Attachment = Tuple[str, bytes, str]


def _cache() -> dict:
    if not has_app_context():
        return {}
    store = getattr(g, "_assignment_email_snapshots", None)
    if store is None:
        store = {}
        g._assignment_email_snapshots = store
    return store


def _bytes_from_workbook(output) -> bytes:
    if hasattr(output, "getvalue"):
        data = output.getvalue()
        if data:
            return data
    if hasattr(output, "seek") and hasattr(output, "read"):
        output.seek(0)
        return output.read()
    if isinstance(output, (bytes, bytearray)):
        return bytes(output)
    raise TypeError(f"Unsupported workbook output type: {type(output)!r}")


def _within_size_limit(filename: str, data: bytes, kind: str) -> bool:
    if len(data) <= MAX_EMAIL_ATTACHMENT_BYTES:
        return True
    current_app.logger.warning(
        "Skipping %s email snapshot %s: %s bytes exceeds %s",
        kind,
        filename,
        len(data),
        MAX_EMAIL_ATTACHMENT_BYTES,
    )
    return False


def build_assignment_generic_excel_bytes(assignment_entity_status) -> tuple[bytes, str]:
    """Return ``(xlsx_bytes, filename)`` using the entry-form generic workbook."""
    from app.services.imports.excel_service import ExcelService

    output, filename = ExcelService.build_assignment_workbook(assignment_entity_status)
    return _bytes_from_workbook(output), filename or "assignment.xlsx"


def _build_pdf_attachment(assignment_entity_status) -> Optional[Attachment]:
    try:
        from app.routes.forms.export import build_assignment_pdf_bytes

        pdf_bytes, filename = build_assignment_pdf_bytes(assignment_entity_status)
    except Exception:
        current_app.logger.exception(
            "Failed to build PDF email snapshot for AES %s",
            getattr(assignment_entity_status, "id", None),
        )
        return None
    filename = filename or "assignment.pdf"
    if not pdf_bytes or not _within_size_limit(filename, pdf_bytes, "PDF"):
        return None
    return (filename, pdf_bytes, PDF_CONTENT_TYPE)


def _build_excel_attachment(assignment_entity_status) -> Optional[Attachment]:
    assigned = getattr(assignment_entity_status, "assigned_form", None)
    builder = None
    try:
        from app.services.imports.structured_excel_routes import resolve_structured_excel_builder

        builder = resolve_structured_excel_builder(assigned)
    except Exception:
        current_app.logger.exception(
            "Failed resolving structured Excel builder for AES %s",
            getattr(assignment_entity_status, "id", None),
        )
        return None

    try:
        if builder:
            output, filename = builder(assignment_entity_status)
            excel_bytes = _bytes_from_workbook(output)
        else:
            excel_bytes, filename = build_assignment_generic_excel_bytes(assignment_entity_status)
    except Exception:
        current_app.logger.exception(
            "Failed to build Excel email snapshot for AES %s",
            getattr(assignment_entity_status, "id", None),
        )
        return None

    filename = filename or "assignment.xlsx"
    if not excel_bytes or not _within_size_limit(filename, excel_bytes, "Excel"):
        return None
    return (filename, excel_bytes, EXCEL_CONTENT_TYPE)


def build_assignment_email_attachments(assignment_entity_status) -> List[Attachment]:
    """Return email attachments for an assignment, honouring the assignment flags.

    Files are built once per request and reused for every recipient. A later
    retry rebuilds from the saved form data.
    """
    if assignment_entity_status is None:
        return []
    assigned = getattr(assignment_entity_status, "assigned_form", None)
    if not assigned:
        return []

    cache = _cache()
    cache_key = getattr(assignment_entity_status, "id", None)
    if cache_key is not None and cache_key in cache:
        return list(cache[cache_key])

    attachments: List[Attachment] = []
    if getattr(assigned, "email_attach_pdf", False):
        pdf = _build_pdf_attachment(assignment_entity_status)
        if pdf:
            attachments.append(pdf)
    if getattr(assigned, "email_attach_excel", False):
        excel = _build_excel_attachment(assignment_entity_status)
        if excel:
            attachments.append(excel)

    if cache_key is not None:
        cache[cache_key] = list(attachments)
    return attachments


def attachments_for_assignment_notification(notification) -> List[Attachment]:
    """Attachments for a submitted/approved assignment instant email."""
    if not _notification_uses_assignment_snapshot(notification):
        return []
    aes_id = getattr(notification, "related_object_id", None)
    if not aes_id:
        return []
    try:
        from app.models import AssignmentEntityStatus

        aes = AssignmentEntityStatus.query.get(int(aes_id))
    except Exception:
        current_app.logger.exception(
            "Failed loading AES %s for assignment email snapshot", aes_id
        )
        return []
    return build_assignment_email_attachments(aes)


def _notification_uses_assignment_snapshot(notification) -> bool:
    if getattr(notification, "related_object_type", None) != "assignment":
        return False
    notification_type = getattr(notification, "notification_type", None)
    value = getattr(notification_type, "value", notification_type)
    return value in ("assignment_submitted", "assignment_approved")
