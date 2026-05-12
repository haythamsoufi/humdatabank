"""Background AI/RAG ingest for SubmittedDocument (library and assignment uploads)."""

import logging
import os
from typing import Any, Dict, Optional

from flask import current_app

from app.extensions import db

logger = logging.getLogger(__name__)


def ai_auto_process_approved_documents_enabled() -> bool:
    """True when approved documents should be queued for the AI knowledge base."""
    try:
        return bool(current_app.config.get("AI_AUTO_PROCESS_APPROVED_DOCUMENTS", True))
    except Exception:
        return True


def sync_ai_document_is_public_from_submitted(submitted) -> None:
    """Mirror ``SubmittedDocument.is_public`` onto the linked ``AIDocument`` (search visibility)."""
    from app.models import AIDocument

    if not submitted or not getattr(submitted, "id", None):
        return
    try:
        sid = int(submitted.id)
    except (TypeError, ValueError):
        return
    ai_doc = AIDocument.query.filter_by(submitted_document_id=sid).first()
    if not ai_doc:
        return
    want = bool(getattr(submitted, "is_public", False))
    if ai_doc.is_public is want:
        return
    ai_doc.is_public = want
    logger.info(
        "Synced AI document %s is_public=%s from submitted_document %s",
        ai_doc.id,
        want,
        sid,
    )


def enqueue_submitted_document_ai_processing(
    submitted_doc_id: int,
    *,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Start background AI import for a submitted document (new AIDocument or reprocess).

    Returns dict keys: ok (bool), code (str), message (str), ai_document_id (optional int).
    """
    from app.models import AIDocument, SubmittedDocument
    from app.routes.ai_documents.upload import _run_import_process_in_thread
    from app.services import storage_service as _ai_storage
    from app.services.ai_document_processor import AIDocumentProcessor

    submitted_doc = SubmittedDocument.query.get(submitted_doc_id)
    if not submitted_doc:
        return {
            "ok": False,
            "code": "submitted_document_not_found",
            "message": "Submitted document not found",
        }

    storage_path = (submitted_doc.storage_path or "").strip()
    if not storage_path:
        return {"ok": False, "code": "missing_storage_path", "message": "Document has no storage path"}

    file_path = None
    cleanup_temp = False
    try:
        file_path, cleanup_temp = _ai_storage.local_path_for_submitted_document_processing(
            storage_path
        )
    except Exception as e:
        logger.error("Error resolving file path for document %s: %s", submitted_doc_id, e, exc_info=True)

    if not file_path:
        logger.error(
            "File not found for submitted document: id=%s filename=%s storage_path=%s resolved_path=%s",
            submitted_doc_id,
            submitted_doc.filename,
            storage_path,
            file_path,
        )
        return {"ok": False, "code": "file_not_found", "message": "File not found"}

    existing_ai_doc = AIDocument.query.filter_by(submitted_document_id=submitted_doc_id).first()
    if existing_ai_doc:
        existing_ai_doc.processing_status = "pending"
        existing_ai_doc.processing_error = None
        existing_ai_doc.is_public = bool(submitted_doc.is_public)
        db.session.commit()
        _run_import_process_in_thread(
            current_app._get_current_object(),
            existing_ai_doc.id,
            file_path,
            submitted_doc.filename,
            cleanup_temp=cleanup_temp,
            clear_storage_path=False,
        )
        return {
            "ok": True,
            "code": "reprocessing",
            "message": "Processing started",
            "ai_document_id": existing_ai_doc.id,
        }

    processor = AIDocumentProcessor()
    if not processor.is_supported_file(submitted_doc.filename):
        return {
            "ok": False,
            "code": "unsupported_file_type",
            "message": f'Unsupported file type. Supported: {", ".join(processor.SUPPORTED_TYPES.keys())}',
        }

    storage_path_for_ai = _ai_storage.ai_aidoc_storage_path_for_submitted(submitted_doc.storage_path or "")

    content_hash = processor.calculate_content_hash(file_path)
    file_type = processor.get_file_type(submitted_doc.filename)
    file_size = os.path.getsize(file_path)

    derived_country = None
    try:
        derived_country = getattr(submitted_doc, "document_country", None)
    except Exception as e:
        logger.debug("AI doc import: document_country resolution failed for %s: %s", submitted_doc_id, e)

    uid: Optional[int] = None
    if user_id is not None:
        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            uid = None
        if uid is not None and uid <= 0:
            uid = None
    if uid is None:
        try:
            uid = int(getattr(submitted_doc, "uploaded_by_user_id", 0) or 0) or None
        except (TypeError, ValueError):
            uid = None

    ai_doc = AIDocument(
        submitted_document_id=submitted_doc_id,
        title=submitted_doc.filename,
        filename=submitted_doc.filename,
        file_type=file_type,
        file_size_bytes=file_size,
        storage_path=storage_path_for_ai,
        content_hash=content_hash,
        processing_status="pending",
        user_id=uid,
        is_public=submitted_doc.is_public,
        searchable=True,
        country_id=(int(getattr(derived_country, "id", 0)) or None) if derived_country else None,
        country_name=(getattr(derived_country, "name", None) if derived_country else None),
    )
    db.session.add(ai_doc)
    db.session.commit()
    _run_import_process_in_thread(
        current_app._get_current_object(),
        ai_doc.id,
        file_path,
        submitted_doc.filename,
        cleanup_temp=cleanup_temp,
        clear_storage_path=False,
    )
    logger.info(
        "Started AI processing for submitted document %s -> AI doc %s (user_id=%s)",
        submitted_doc_id,
        ai_doc.id,
        uid,
    )
    return {"ok": True, "code": "processing", "message": "Processing started", "ai_document_id": ai_doc.id}


def maybe_enqueue_submitted_document_ai_processing_after_approval(
    submitted_doc_id: int,
    *,
    user_id: Optional[int] = None,
) -> None:
    """
    If settings allow, queue AI ingest after a document becomes Approved.

    Skips when an index job is already pending/processing or successfully completed
    (manual reprocess remains available from AI admin).
    """
    if not ai_auto_process_approved_documents_enabled():
        return

    from app.models import AIDocument

    existing = AIDocument.query.filter_by(submitted_document_id=submitted_doc_id).first()
    if existing:
        st = (existing.processing_status or "").strip().lower()
        if st in ("pending", "processing"):
            logger.debug(
                "Auto AI processing skipped (already %s) submitted_document_id=%s",
                st,
                submitted_doc_id,
            )
            return
        if st == "completed":
            logger.debug(
                "Auto AI processing skipped (already completed) submitted_document_id=%s",
                submitted_doc_id,
            )
            return

    result = enqueue_submitted_document_ai_processing(submitted_doc_id, user_id=user_id)
    if not result.get("ok"):
        logger.info(
            "Auto AI processing not started for submitted_document_id=%s: %s",
            submitted_doc_id,
            result.get("code"),
        )
    else:
        logger.info(
            "Auto AI processing started for submitted_document_id=%s ai_document_id=%s",
            submitted_doc_id,
            result.get("ai_document_id"),
        )
