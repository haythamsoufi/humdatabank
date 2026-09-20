"""On-demand fetch of public FDRS document bytes into local submission storage."""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from typing import Optional, Tuple

from app.extensions import db
from app.models.documents import SubmittedDocument
from app.services.platform import storage_service as storage


def _fdrs_imports_dir() -> str:
    from plugins.fdrs.scripts_path import ensure_fdrs_scripts_in_path

    return ensure_fdrs_scripts_in_path()


def download_fdrs_document_to_temp(url: str, filename_hint: str) -> Tuple[str, str, int, str, str]:
    """Download a public FDRS document URL to a temp file for AI processing.

    Used by ``app.services.ai.documents.ingest`` as the FDRS-specific downloader
    behind its generic ``source_url`` resolution hook.

    Returns (temp_path, filename, file_size, content_hash, file_type).
    """
    imports_dir = os.path.abspath(_fdrs_imports_dir())
    if imports_dir not in sys.path:
        sys.path.insert(0, imports_dir)

    from fdrs_documents_sync import fetch_fdrs_document_bytes

    data, status = fetch_fdrs_document_bytes(url)
    if status not in (200, 206) or not data:
        raise FileNotFoundError(
            f"Could not download FDRS document (HTTP {status}). "
            "The file may be private, unavailable, or blocked by IFRC."
        )

    filename = (filename_hint or "document").strip() or "document"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".md", ".html"}:
        ext = ".pdf"
        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}{ext}"

    fd, temp_path = tempfile.mkstemp(suffix=ext)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise

    file_size = len(data)
    content_hash = hashlib.sha256(data).hexdigest()
    file_type = ext.lstrip(".") or "pdf"
    return temp_path, filename, file_size, content_hash, file_type


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
