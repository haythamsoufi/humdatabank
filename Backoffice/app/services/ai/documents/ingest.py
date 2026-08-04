"""Background AI/RAG ingest for SubmittedDocument (library and assignment uploads)."""

import hashlib
import logging
import os
import sys
import tempfile
from typing import Any, Dict, Optional, Tuple

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


def _fdrs_imports_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "scripts", "imports")


def _download_fdrs_document_to_temp(url: str, filename_hint: str) -> Tuple[str, str, int, str, str]:
    """Download a public FDRS document URL to a temp file for AI processing."""
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


def _download_submitted_document_from_source_url(submitted_doc) -> Tuple[str, str, int, str, str]:
    """
    Download bytes for a submitted document that only has ``source_url`` (FDRS / IFRC API).

    Returns (temp_path, filename, file_size, content_hash, file_type).
    """
    from app.routes.ai_documents.helpers import _download_ifrc_document

    source_url = (getattr(submitted_doc, "source_url", None) or "").strip()
    if not source_url:
        raise FileNotFoundError("Document has no source URL")

    filename_hint = submitted_doc.filename or "document"
    prefer_fdrs = bool(getattr(submitted_doc, "fdrs_import_key", None)) or bool(
        getattr(submitted_doc, "file_pending", False)
    )

    if prefer_fdrs:
        try:
            return _download_fdrs_document_to_temp(source_url, filename_hint)
        except Exception as fdrs_err:
            logger.warning(
                "FDRS download failed for submitted_document %s, trying IFRC fetch: %s",
                getattr(submitted_doc, "id", None),
                fdrs_err,
            )

    try:
        return _download_ifrc_document(source_url)
    except Exception as ifrc_err:
        logger.warning(
            "IFRC download failed for submitted_document %s, trying FDRS fetch: %s",
            getattr(submitted_doc, "id", None),
            ifrc_err,
        )
        return _download_fdrs_document_to_temp(source_url, filename_hint)


def _resolve_submitted_document_for_ai_processing(submitted_doc) -> Dict[str, Any]:
    """
    Resolve a local temp or stored path for AI ingest.

    Supports local storage and reference-only rows (``source_url`` / ``file_pending`` FDRS docs).
    """
    from app.services.platform import storage_service as _ai_storage

    storage_path = (submitted_doc.storage_path or "").strip()
    source_url = (getattr(submitted_doc, "source_url", None) or "").strip()
    file_pending = bool(getattr(submitted_doc, "file_pending", False))

    if storage_path and not file_pending:
        try:
            file_path, cleanup_temp = _ai_storage.local_path_for_submitted_document_processing(
                storage_path
            )
            if file_path:
                return {
                    "ok": True,
                    "file_path": file_path,
                    "cleanup_temp": cleanup_temp,
                    "filename": submitted_doc.filename or "document",
                    "from_url": False,
                }
        except Exception as e:
            logger.error(
                "Error resolving local file for submitted document %s: %s",
                getattr(submitted_doc, "id", None),
                e,
                exc_info=True,
            )

    if storage_path and not source_url:
        return {
            "ok": False,
            "code": "file_not_found",
            "message": "File not found on server",
        }

    if source_url:
        try:
            temp_path, filename, file_size, content_hash, file_type = _download_submitted_document_from_source_url(
                submitted_doc
            )
            return {
                "ok": True,
                "file_path": temp_path,
                "cleanup_temp": True,
                "filename": filename,
                "file_size": file_size,
                "content_hash": content_hash,
                "file_type": file_type,
                "from_url": True,
                "source_url": source_url,
            }
        except Exception as e:
            logger.error(
                "Failed to download submitted document %s from source_url: %s",
                getattr(submitted_doc, "id", None),
                e,
                exc_info=True,
            )
            return {
                "ok": False,
                "code": "download_failed",
                "message": str(e) or "Failed to download document from source URL",
            }

    if not storage_path:
        return {
            "ok": False,
            "code": "missing_storage_path",
            "message": "Document has no storage path or source URL",
        }

    return {"ok": False, "code": "file_not_found", "message": "File not found"}


def resolve_ai_document_source_for_processing(ai_doc) -> Dict[str, Any]:
    """
    Resolve a local or temp file for AI reprocess, metadata enrichment, or country detection.

    Uses ``AIDocument.source_url`` when set; otherwise resolves via linked
    ``SubmittedDocument`` (FDRS / IFRC URL or storage) or standalone AI upload storage.
    """
    from app.models import SubmittedDocument
    from app.routes.ai_documents.helpers import _ai_doc_source_ready, _download_ifrc_document
    from app.services.platform import storage_service as _ai_storage

    source_url = (getattr(ai_doc, "source_url", None) or "").strip()
    submitted_doc = None
    submitted_doc_id = getattr(ai_doc, "submitted_document_id", None)
    if submitted_doc_id:
        try:
            submitted_doc = SubmittedDocument.query.get(int(submitted_doc_id))
        except (TypeError, ValueError):
            submitted_doc = None

    if source_url:
        if submitted_doc and (
            getattr(submitted_doc, "fdrs_import_key", None)
            or getattr(submitted_doc, "file_pending", False)
        ):
            return _resolve_submitted_document_for_ai_processing(submitted_doc)
        try:
            temp_path, filename, file_size, content_hash, file_type = _download_ifrc_document(source_url)
            return {
                "ok": True,
                "file_path": temp_path,
                "cleanup_temp": True,
                "filename": filename,
                "file_size": file_size,
                "content_hash": content_hash,
                "file_type": file_type,
                "from_url": True,
                "source_url": source_url,
            }
        except Exception as e:
            logger.error(
                "Failed to download AI document %s from source_url: %s",
                getattr(ai_doc, "id", None),
                e,
                exc_info=True,
            )
            return {
                "ok": False,
                "code": "download_failed",
                "message": str(e) or "Failed to download document from source URL",
            }

    if submitted_doc:
        resolved = _resolve_submitted_document_for_ai_processing(submitted_doc)
        if resolved.get("ok") and resolved.get("from_url") and resolved.get("source_url"):
            resolved["backfill_source_url"] = resolved["source_url"]
        return resolved

    storage_path = (getattr(ai_doc, "storage_path", None) or "").strip()
    if storage_path and _ai_doc_source_ready(ai_doc):
        cleanup_temp = False
        if submitted_doc_id:
            file_path, cleanup_temp = _ai_storage.local_path_for_submitted_document_processing(storage_path)
        elif os.path.isabs(storage_path):
            file_path = storage_path
        else:
            file_path = _ai_storage.get_absolute_path(_ai_storage.AI_DOCUMENTS, storage_path)
        if file_path:
            return {
                "ok": True,
                "file_path": file_path,
                "cleanup_temp": cleanup_temp,
                "filename": getattr(ai_doc, "filename", None) or "document",
                "from_url": False,
            }

    return {
        "ok": False,
        "code": "file_not_found",
        "message": (
            "Source file not found. Reprocess requires a local file, source URL, "
            "or a linked system document with downloadable content."
        ),
    }


def apply_resolved_source_metadata_to_ai_doc(ai_doc, resolved: Dict[str, Any]) -> None:
    """Persist filename/hash/size/source_url from a resolved download onto ``AIDocument``."""
    if not ai_doc or not resolved.get("ok"):
        return
    if resolved.get("filename"):
        ai_doc.filename = resolved["filename"]
    if resolved.get("file_size") is not None:
        ai_doc.file_size_bytes = resolved["file_size"]
    if resolved.get("content_hash"):
        ai_doc.content_hash = resolved["content_hash"]
    if resolved.get("file_type"):
        ai_doc.file_type = resolved["file_type"]
    source_url = (resolved.get("backfill_source_url") or resolved.get("source_url") or "").strip()
    if source_url and not (getattr(ai_doc, "source_url", None) or "").strip():
        ai_doc.source_url = source_url


def _prepare_submitted_document_ai_import(
    submitted_doc_id: int,
    *,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Resolve file and create/update AIDocument row for a submitted-document import.

    Returns ok=True with ai_document_id, file_path, filename, cleanup_temp, code, message.
    On failure returns ok=False with code and message.
    """
    from app.models import AIDocument, SubmittedDocument
    from app.services.platform import storage_service as _ai_storage
    from app.services.ai.documents.processor import AIDocumentProcessor

    submitted_doc = SubmittedDocument.query.get(submitted_doc_id)
    if not submitted_doc:
        return {
            "ok": False,
            "code": "submitted_document_not_found",
            "message": "Submitted document not found",
        }

    if getattr(submitted_doc, "source_url_unreachable", False):
        status = getattr(submitted_doc, "source_url_http_status", None)
        detail = f" (HTTP {status})" if status is not None else ""
        return {
            "ok": False,
            "code": "source_url_unreachable",
            "message": (
                "This document's FDRS file URL is not reachable yet"
                f"{detail}. Re-run FDRS sync after IFRC fixes the URL."
            ),
        }

    resolved = _resolve_submitted_document_for_ai_processing(submitted_doc)
    if not resolved.get("ok"):
        return {
            "ok": False,
            "code": resolved.get("code") or "file_not_found",
            "message": resolved.get("message") or "File not found",
        }

    file_path = resolved["file_path"]
    cleanup_temp = bool(resolved.get("cleanup_temp"))
    filename = resolved.get("filename") or submitted_doc.filename or "document"
    from_url = bool(resolved.get("from_url"))
    source_url = (resolved.get("source_url") or "").strip() if from_url else ""

    existing_ai_doc = AIDocument.query.filter_by(submitted_document_id=submitted_doc_id).first()
    if existing_ai_doc:
        existing_ai_doc.processing_status = "pending"
        existing_ai_doc.processing_error = None
        existing_ai_doc.is_public = bool(submitted_doc.is_public)
        from app.services.ai.documents.submitted_metadata import apply_submitted_document_metadata_to_ai_doc

        apply_submitted_document_metadata_to_ai_doc(existing_ai_doc, submitted_doc)
        if from_url:
            existing_ai_doc.source_url = source_url or existing_ai_doc.source_url
            existing_ai_doc.filename = filename
            if resolved.get("file_size") is not None:
                existing_ai_doc.file_size_bytes = resolved["file_size"]
            if resolved.get("content_hash"):
                existing_ai_doc.content_hash = resolved["content_hash"]
            if resolved.get("file_type"):
                existing_ai_doc.file_type = resolved["file_type"]
        db.session.commit()
        return {
            "ok": True,
            "code": "reprocessing",
            "message": "Processing started",
            "ai_document_id": existing_ai_doc.id,
            "file_path": file_path,
            "filename": filename,
            "cleanup_temp": cleanup_temp,
        }

    processor = AIDocumentProcessor()
    if not processor.is_supported_file(filename):
        if cleanup_temp and file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
        return {
            "ok": False,
            "code": "unsupported_file_type",
            "message": f'Unsupported file type. Supported: {", ".join(processor.SUPPORTED_TYPES.keys())}',
        }

    if from_url:
        content_hash = resolved.get("content_hash") or processor.calculate_content_hash(file_path)
        file_type = resolved.get("file_type") or processor.get_file_type(filename)
        file_size = resolved.get("file_size") or os.path.getsize(file_path)
        storage_path_for_ai = None
    else:
        storage_path_for_ai = _ai_storage.ai_aidoc_storage_path_for_submitted(
            submitted_doc.storage_path or ""
        )
        content_hash = processor.calculate_content_hash(file_path)
        file_type = processor.get_file_type(filename)
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
        title=filename,
        filename=filename,
        file_type=file_type,
        file_size_bytes=file_size,
        storage_path=storage_path_for_ai,
        source_url=source_url or None,
        content_hash=content_hash,
        processing_status="pending",
        user_id=uid,
        is_public=submitted_doc.is_public,
        searchable=True,
        country_id=(int(getattr(derived_country, "id", 0)) or None) if derived_country else None,
        country_name=(getattr(derived_country, "name", None) if derived_country else None),
    )
    from app.services.ai.documents.submitted_metadata import apply_submitted_document_metadata_to_ai_doc

    apply_submitted_document_metadata_to_ai_doc(ai_doc, submitted_doc)
    db.session.add(ai_doc)
    db.session.commit()
    logger.info(
        "Prepared AI import for submitted document %s -> AI doc %s (user_id=%s, from_url=%s)",
        submitted_doc_id,
        ai_doc.id,
        uid,
        from_url,
    )
    return {
        "ok": True,
        "code": "processing",
        "message": "Processing started",
        "ai_document_id": ai_doc.id,
        "file_path": file_path,
        "filename": filename,
        "cleanup_temp": cleanup_temp,
    }


def enqueue_submitted_document_ai_processing(
    submitted_doc_id: int,
    *,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Start background AI import for a submitted document (new AIDocument or reprocess).

    Returns dict keys: ok (bool), code (str), message (str), ai_document_id (optional int).
    """
    from app.routes.ai_documents.upload import _run_import_process_in_thread

    prep = _prepare_submitted_document_ai_import(submitted_doc_id, user_id=user_id)
    if not prep.get("ok"):
        return prep
    _run_import_process_in_thread(
        current_app._get_current_object(),
        prep["ai_document_id"],
        prep["file_path"],
        prep["filename"],
        cleanup_temp=bool(prep.get("cleanup_temp")),
        clear_storage_path=False,
    )
    return {
        "ok": True,
        "code": prep.get("code") or "processing",
        "message": prep.get("message") or "Processing started",
        "ai_document_id": prep.get("ai_document_id"),
    }


def process_submitted_document_ai_import_sync(
    submitted_doc_id: int,
    *,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Import one submitted document synchronously (for server-side bulk jobs).

    Returns dict keys: ok (bool), code (str), message (str), ai_document_id (optional int).
    """
    from app.models import AIDocument
    from app.routes.ai_documents.upload import _process_document_sync

    prep = _prepare_submitted_document_ai_import(submitted_doc_id, user_id=user_id)
    if not prep.get("ok"):
        return prep

    ai_doc_id = int(prep["ai_document_id"])
    file_path = prep["file_path"]
    filename = prep["filename"]
    cleanup_temp = bool(prep.get("cleanup_temp"))
    try:
        _process_document_sync(ai_doc_id, file_path, filename)
        doc = AIDocument.query.get(ai_doc_id)
        if doc and doc.processing_status == "completed":
            return {
                "ok": True,
                "code": "completed",
                "message": "Processing completed",
                "ai_document_id": ai_doc_id,
            }
        err = (doc.processing_error if doc else None) or "Processing failed"
        return {
            "ok": False,
            "code": "failed",
            "message": err,
            "ai_document_id": ai_doc_id,
        }
    except Exception as e:
        logger.error(
            "Sync AI import failed for submitted document %s (ai_doc=%s): %s",
            submitted_doc_id,
            ai_doc_id,
            e,
            exc_info=True,
        )
        try:
            doc = AIDocument.query.get(ai_doc_id)
            if doc:
                doc.processing_status = "failed"
                doc.processing_error = "Processing failed."
                db.session.commit()
        except Exception as update_e:
            logger.debug("Sync import failure status update failed: %s", update_e)
            db.session.rollback()
        return {
            "ok": False,
            "code": "failed",
            "message": "Processing failed.",
            "ai_document_id": ai_doc_id,
        }
    finally:
        if cleanup_temp and file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass


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
