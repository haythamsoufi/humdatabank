"""Reusable guidance-document storage for plugins and system owners."""

from __future__ import annotations

import logging
import os
import re
import uuid
from typing import Any, Optional

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import AIDocument, GuidanceDocument
from app.services.platform import storage_service as storage
from app.utils.advanced_validation import validate_upload_extension_and_mime
from app.utils.datetime_helpers import utcnow

logger = logging.getLogger(__name__)

OWNER_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,48}$")
MAX_GUIDANCE_FILE_BYTES = 50 * 1024 * 1024
ALLOWED_GUIDANCE_EXTENSIONS = (
    ".pdf",
    ".docx",
    ".doc",
    ".xlsx",
    ".xls",
    ".csv",
    ".txt",
    ".md",
    ".markdown",
    ".html",
    ".htm",
)


class GuidanceDocumentError(ValueError):
    """User-facing validation error for guidance uploads."""


def normalize_owner_key(owner_key: str | None) -> str:
    key = (owner_key or "").strip().lower()
    if not OWNER_KEY_RE.fullmatch(key):
        raise GuidanceDocumentError("Invalid owner key")
    return key


def _file_size(file_storage: FileStorage) -> int:
    stream = getattr(file_storage, "stream", None)
    if stream is None:
        data = file_storage.read()
        return len(data or b"")
    pos = stream.tell()
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(pos)
    return int(size)


def save_guidance_document(
    file_storage: FileStorage,
    *,
    owner_key: str,
    uploaded_by_user_id: int,
    title: str | None = None,
    description: str | None = None,
) -> GuidanceDocument:
    """Store an uploaded guidance file and persist the row."""
    owner = normalize_owner_key(owner_key)
    ok, error, _ext = validate_upload_extension_and_mime(
        file_storage, ALLOWED_GUIDANCE_EXTENSIONS
    )
    if not ok:
        raise GuidanceDocumentError(error or "Unsupported file type")

    filename = secure_filename(file_storage.filename or "") or "document"
    size = _file_size(file_storage)
    if size > MAX_GUIDANCE_FILE_BYTES:
        raise GuidanceDocumentError(
            f"File too large. Maximum size is {MAX_GUIDANCE_FILE_BYTES // (1024 * 1024)}MB"
        )

    rel_path = f"guidance/{owner}/{uuid.uuid4().hex}/{filename}"
    stored = storage.upload(storage.ADMIN_DOCUMENTS, rel_path, file_storage)

    display_title = (title or "").strip() or filename
    doc = GuidanceDocument(
        owner_key=owner,
        title=display_title,
        filename=filename,
        storage_path=stored,
        file_size_bytes=size,
        description=(description or "").strip() or None,
        uploaded_by_user_id=int(uploaded_by_user_id),
        uploaded_at=utcnow(),
        updated_at=utcnow(),
    )
    db.session.add(doc)
    db.session.commit()
    return doc


def get_guidance_document(doc_id: int) -> Optional[GuidanceDocument]:
    try:
        return GuidanceDocument.query.get(int(doc_id))
    except (TypeError, ValueError):
        return None


def list_guidance_documents(owner_key: str | None = None) -> list[dict[str, Any]]:
    """Return guidance rows with AI-import status (newest first)."""
    query = (
        db.session.query(GuidanceDocument, AIDocument)
        .outerjoin(AIDocument, AIDocument.guidance_document_id == GuidanceDocument.id)
        .order_by(GuidanceDocument.uploaded_at.desc(), GuidanceDocument.id.desc())
    )
    if owner_key:
        query = query.filter(GuidanceDocument.owner_key == normalize_owner_key(owner_key))

    rows = []
    for doc, ai_doc in query.all():
        rows.append(serialize_guidance_document(doc, ai_doc=ai_doc))
    return rows


def serialize_guidance_document(
    doc: GuidanceDocument,
    *,
    ai_doc: AIDocument | None = None,
) -> dict[str, Any]:
    if ai_doc is None:
        ai_doc = AIDocument.query.filter_by(guidance_document_id=doc.id).first()
    uploaded_by = ""
    user = getattr(doc, "uploaded_by_user", None)
    if user:
        uploaded_by = user.name or user.email or ""
    return {
        "id": doc.id,
        "owner_key": doc.owner_key,
        "title": doc.title or doc.filename,
        "filename": doc.filename,
        "file_size_bytes": doc.file_size_bytes,
        "description": doc.description or "",
        "uploaded_by": uploaded_by,
        "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        "ai_processed": ai_doc is not None,
        "ai_document_id": ai_doc.id if ai_doc else None,
        "ai_status": ai_doc.processing_status if ai_doc else None,
    }


def delete_guidance_document(doc: GuidanceDocument) -> None:
    """Delete the stored file and the row (cascades linked AI documents)."""
    rel = (doc.storage_path or "").strip()
    if rel:
        try:
            storage.delete(storage.ADMIN_DOCUMENTS, rel)
        except Exception as exc:
            logger.warning("Failed to delete guidance file %s: %s", rel, exc)
    db.session.delete(doc)
    db.session.commit()
