"""On-demand fetch of public FDRS document bytes into local submission storage."""

from __future__ import annotations

import os
import sys
from typing import Optional, Tuple

from app.extensions import db
from app.models.documents import SubmittedDocument
from app.services.platform import storage_service as storage


def _fdrs_imports_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "imports")


def try_materialize_public_fdrs_document(document: SubmittedDocument) -> Tuple[bool, Optional[str]]:
    """
    Download a public FDRS document from ``source_url`` when no local copy exists.

    Returns ``(success, user_message)``. *user_message* is set when ``success`` is False.
    """
    if document.fdrs_import_key is None and not (document.source_url or "").strip():
        return False, None

    if not document.is_public:
        return False, (
            "This is a private FDRS document. File download is not available through the databank."
        )

    if document.storage_path and storage.submitted_source_exists(document.storage_path):
        return True, None

    source_url = (document.source_url or "").strip()
    if not source_url:
        return False, "File not found on server."

    imports_dir = os.path.abspath(_fdrs_imports_dir())
    if imports_dir not in sys.path:
        sys.path.insert(0, imports_dir)

    from fdrs_documents_sync import _save_fdrs_document_bytes, fetch_fdrs_document_bytes

    data, status = fetch_fdrs_document_bytes(source_url)
    if status not in (200, 206) or not data:
        if status == 403:
            return False, (
                "The public FDRS file could not be downloaded (HTTP 403). "
                "Ask IFRC to enable access for this document URL, or upload the file manually."
            )
        return False, (
            "The public FDRS file could not be downloaded from IFRC. "
            "Re-run FDRS sync later or upload the file manually."
        )

    aes = document.assignment_entity_status
    if aes is None:
        return False, "File not found on server."

    rel_path = _save_fdrs_document_bytes(
        data=data,
        filename=document.filename,
        assignment_entity_status_id=aes.id,
        entity_type=aes.entity_type,
        entity_id=aes.entity_id,
    )
    document.storage_path = rel_path
    document.file_pending = False
    db.session.add(document)
    db.session.commit()
    return True, None
