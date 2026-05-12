"""Who may delete or replace files on ``SubmittedDocument`` rows (approval guard)."""

from __future__ import annotations

from typing import Any

from app.models.enums import DocumentStatus


def submitted_document_is_approved(doc: Any) -> bool:
    s = (getattr(doc, "status", None) or "").strip().casefold()
    return s == DocumentStatus.APPROVED.casefold()


def user_may_delete_or_replace_submitted_document_file(user, doc: Any) -> bool:
    """Focal points cannot delete or replace the stored file once the row is approved.

    System managers and users with ``admin.documents.manage`` may still mutate.
    """
    if not submitted_document_is_approved(doc):
        return True
    from app.services.authorization_service import AuthorizationService

    return AuthorizationService.is_system_manager(user) or AuthorizationService.has_rbac_permission(
        user, "admin.documents.manage"
    )
