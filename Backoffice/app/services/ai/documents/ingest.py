"""Background AI/RAG ingest for SubmittedDocument (library and assignment uploads)."""

import logging
import os
import zlib
from typing import Any, Dict, Optional, Tuple

from flask import current_app
from sqlalchemy import text

from app.extensions import db

logger = logging.getLogger(__name__)


def ai_auto_process_approved_documents_enabled() -> bool:
    """True when approved documents should be queued for the AI knowledge base."""
    try:
        return bool(current_app.config.get("AI_AUTO_PROCESS_APPROVED_DOCUMENTS", True))
    except Exception:
        return True


def _normalize_document_status(raw) -> str:
    from app.models.enums import DocumentStatus

    if raw is None:
        return DocumentStatus.PENDING
    if hasattr(raw, "value"):
        raw = raw.value
    return DocumentStatus.normalize(str(raw))


def sync_ai_document_from_submitted(
    submitted,
    *,
    status_changed_from=None,
    ai_doc=None,
) -> bool:
    """
    Mirror ``SubmittedDocument`` privacy, metadata, and approval status onto linked ``AIDocument``.

    When ``status_changed_from`` is set (from SQLAlchemy attribute history), toggles
    ``searchable`` on approval transitions without affecting rows that never changed status.
    """
    from app.models import AIDocument
    from app.models.enums import DocumentStatus
    from app.services.ai.documents.submitted_metadata import apply_submitted_document_metadata_to_ai_doc

    if not submitted or not getattr(submitted, "id", None):
        return False
    try:
        sid = int(submitted.id)
    except (TypeError, ValueError):
        return False

    if ai_doc is None:
        ai_doc = AIDocument.query.filter_by(submitted_document_id=sid).first()
    if not ai_doc:
        return False

    changed = False
    want_public = _submitted_is_ai_public(submitted)
    if ai_doc.is_public is not want_public:
        ai_doc.is_public = want_public
        changed = True

    apply_submitted_document_metadata_to_ai_doc(ai_doc, submitted)
    changed = True

    new_status = _normalize_document_status(getattr(submitted, "status", None))
    if status_changed_from is not None:
        prev_status = _normalize_document_status(status_changed_from)
        if prev_status == DocumentStatus.APPROVED and new_status != DocumentStatus.APPROVED:
            if ai_doc.searchable is not False:
                ai_doc.searchable = False
                changed = True
                logger.info(
                    "Set AI document %s searchable=False (submitted_document %s status %s -> %s)",
                    ai_doc.id,
                    sid,
                    prev_status,
                    new_status,
                )
        elif prev_status != DocumentStatus.APPROVED and new_status == DocumentStatus.APPROVED:
            proc = (getattr(ai_doc, "processing_status", None) or "").strip().lower()
            if proc == "completed" and ai_doc.searchable is not True:
                ai_doc.searchable = True
                changed = True
                logger.info(
                    "Restored AI document %s searchable=True (submitted_document %s re-approved)",
                    ai_doc.id,
                    sid,
                )

    if changed:
        logger.info(
            "Synced AI document %s from submitted_document %s (is_public=%s, status=%s)",
            ai_doc.id,
            sid,
            want_public,
            new_status,
        )
    return True


def _submitted_is_ai_public(submitted) -> bool:
    """An AI document is world-readable only while its source is both flagged public AND approved."""
    from app.models.enums import DocumentStatus

    if not bool(getattr(submitted, "is_public", False)):
        return False
    return _normalize_document_status(getattr(submitted, "status", None)) == DocumentStatus.APPROVED


def _processing_status_str(doc) -> str:
    raw = getattr(doc, "processing_status", None)
    if raw is None:
        return ""
    if hasattr(raw, "value"):
        raw = raw.value
    return str(raw).strip().lower()


def _chunk_count(doc) -> int:
    try:
        return int(getattr(doc, "total_chunks", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _ai_document_is_embedded(doc) -> bool:
    """True when this row already has a completed embedding and must not be re-embedded."""
    return _processing_status_str(doc) == "completed" and _chunk_count(doc) > 0


def _parallel_import_should_skip(doc) -> bool:
    """Another worker inserted this row while we were downloading the same file."""
    return _processing_status_str(doc) in ("pending", "processing", "completed")


def _hash_lock_key(content_hash: str) -> int:
    crc = zlib.crc32((content_hash or "").strip().lower().encode("utf-8")) & 0xFFFFFFFF
    if crc >= 2**31:
        crc -= 2**32
    return int(crc)


def _advisory_xact_lock(namespace: int, key: int) -> None:
    db.session.execute(
        text("SELECT pg_advisory_xact_lock(:ns, :key)"),
        {"ns": int(namespace), "key": int(key)},
    )


def _lock_import_keys(
    *,
    submitted_document_id: Optional[int] = None,
    guidance_document_id: Optional[int] = None,
    content_hash: Optional[str] = None,
) -> None:
    """
    Serialize imports that would insert the same submitted row or the same file bytes.

    Hash is locked first, then the catalog id, so two workers cannot deadlock.
    """
    try:
        if content_hash:
            _advisory_xact_lock(2, _hash_lock_key(content_hash))
        if submitted_document_id:
            _advisory_xact_lock(1, int(submitted_document_id))
        if guidance_document_id:
            _advisory_xact_lock(3, int(guidance_document_id))
    except Exception as e:
        logger.debug("AI import advisory lock skipped: %s", e)
        try:
            db.session.rollback()
        except Exception:
            pass


def _discard_temp_import_file(prep: Dict[str, Any]) -> None:
    if not prep.get("cleanup_temp"):
        return
    file_path = prep.get("file_path")
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass


def _import_skip_result(
    ai_doc,
    *,
    file_path: str,
    filename: str,
    cleanup_temp: bool,
    code: str,
    message: str,
) -> Dict[str, Any]:
    return {
        "ok": True,
        "code": code,
        "message": message,
        "ai_document_id": int(ai_doc.id),
        "file_path": file_path,
        "filename": filename,
        "cleanup_temp": cleanup_temp,
        "skip_processing": True,
    }


def _reuse_submitted_ai_document(
    existing_ai_doc,
    submitted_doc,
    *,
    file_path: str,
    filename: str,
    cleanup_temp: bool,
    from_url: bool,
    source_url: str,
    resolved: Dict[str, Any],
) -> Dict[str, Any]:
    """Re-queue an AIDocument that is already linked to this submitted document."""
    existing_ai_doc.processing_status = "pending"
    existing_ai_doc.processing_error = None
    sync_ai_document_from_submitted(submitted_doc, ai_doc=existing_ai_doc)
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
        "skip_processing": False,
    }


def _attach_submitted_catalog_entry(
    keeper,
    submitted_doc,
    *,
    submitted_doc_id: int,
    file_path: str,
    filename: str,
    cleanup_temp: bool,
    from_url: bool,
    source_url: str,
    content_hash: Optional[str],
    file_type: Optional[str],
    file_size,
    storage_path_for_ai,
    derived_country,
    uid: Optional[int],
) -> Dict[str, Any]:
    """
    Point a submitted-document catalog row at an AIDocument that already has these bytes.

    The first catalog row becomes the primary link. Later years, document types, and
    ``_1`` filenames are stored on that row and are not embedded again.
    """
    from app.services.ai.documents.submitted_metadata import (
        apply_submitted_document_metadata_to_ai_doc,
        record_submitted_catalog_entry,
    )

    as_primary = not getattr(keeper, "submitted_document_id", None)
    if as_primary:
        keeper.submitted_document_id = submitted_doc_id
        keeper.filename = filename or keeper.filename
        keeper.file_type = file_type or keeper.file_type
        keeper.file_size_bytes = file_size or keeper.file_size_bytes
        if content_hash:
            keeper.content_hash = content_hash
        if from_url:
            keeper.source_url = source_url or keeper.source_url
            keeper.storage_path = None
        elif storage_path_for_ai:
            keeper.storage_path = storage_path_for_ai
        if not keeper.user_id and uid:
            keeper.user_id = uid
        keeper.is_public = _submitted_is_ai_public(submitted_doc)
        keeper.searchable = True
        if derived_country and not keeper.country_id:
            keeper.country_id = int(getattr(derived_country, "id", 0)) or None
            keeper.country_name = getattr(derived_country, "name", None)
        sync_ai_document_from_submitted(submitted_doc, ai_doc=keeper)
        apply_submitted_document_metadata_to_ai_doc(keeper, submitted_doc)
    elif _submitted_is_ai_public(submitted_doc):
        keeper.is_public = True

    record_submitted_catalog_entry(keeper, submitted_doc)
    embedded = _ai_document_is_embedded(keeper)
    if embedded:
        db.session.commit()
        logger.info(
            "Linked submitted document %s to existing AI document %s (same file bytes)",
            submitted_doc_id,
            keeper.id,
        )
        return _import_skip_result(
            keeper,
            file_path=file_path,
            filename=filename,
            cleanup_temp=cleanup_temp,
            code="catalog_alias",
            message=(
                "This file is already in the knowledge base. "
                "The extra catalog entry was linked to the existing document."
            ),
        )

    keeper.processing_status = "pending"
    keeper.processing_error = None
    db.session.commit()
    logger.info(
        "Reused AI document %s for submitted document %s (same file bytes, primary=%s)",
        keeper.id,
        submitted_doc_id,
        as_primary,
    )
    return {
        "ok": True,
        "code": "reclaimed" if as_primary else "catalog_alias",
        "message": "Processing started",
        "ai_document_id": keeper.id,
        "file_path": file_path,
        "filename": filename,
        "cleanup_temp": cleanup_temp,
        "skip_processing": False,
    }


def sync_ai_document_is_public_from_submitted(submitted) -> None:
    """Backward-compatible wrapper; prefer ``sync_ai_document_from_submitted``."""
    sync_ai_document_from_submitted(submitted)


def _download_submitted_document_from_source_url(submitted_doc) -> Tuple[str, str, int, str, str]:
    """
    Download bytes for a submitted document that only has ``source_url`` (FDRS / IFRC API).

    Generic dispatch hook: this module stays provenance-agnostic and defers to the
    FDRS plugin's downloader (``plugins.fdrs.services.fdrs_document_fetch_service``)
    only when the document looks FDRS-sourced, falling back to the generic IFRC
    fetch either way.

    Returns (temp_path, filename, file_size, content_hash, file_type).
    """
    from app.routes.ai_documents.helpers import _download_ifrc_document
    from plugins.fdrs.services.fdrs_document_fetch_service import download_fdrs_document_to_temp

    source_url = (getattr(submitted_doc, "source_url", None) or "").strip()
    if not source_url:
        raise FileNotFoundError("Document has no source URL")

    filename_hint = submitted_doc.filename or "document"
    prefer_fdrs = bool(getattr(submitted_doc, "fdrs_import_key", None)) or bool(
        getattr(submitted_doc, "file_pending", False)
    )

    if prefer_fdrs:
        try:
            return download_fdrs_document_to_temp(source_url, filename_hint)
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
        return download_fdrs_document_to_temp(source_url, filename_hint)


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
        return _reuse_submitted_ai_document(
            existing_ai_doc,
            submitted_doc,
            file_path=file_path,
            filename=filename,
            cleanup_temp=cleanup_temp,
            from_url=from_url,
            source_url=source_url,
            resolved=resolved,
        )

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

    # One knowledge-base row per file. Another year, document type, or filename of the
    # same bytes is recorded on the existing row. The lock closes the check-then-insert
    # race that imported the same submitted document twice.
    from app.services.ai.documents.duplicates import (
        find_reclaimable_ai_document,
        find_same_content_ai_document,
    )
    from app.services.ai.documents.submitted_metadata import apply_submitted_document_metadata_to_ai_doc

    _lock_import_keys(submitted_document_id=submitted_doc_id, content_hash=content_hash)
    raced = AIDocument.query.filter_by(submitted_document_id=submitted_doc_id).first()
    if raced is not None:
        if _parallel_import_should_skip(raced):
            logger.info(
                "Skipped parallel AI import for submitted document %s; AI doc %s already exists",
                submitted_doc_id,
                raced.id,
            )
            return _import_skip_result(
                raced,
                file_path=file_path,
                filename=filename,
                cleanup_temp=cleanup_temp,
                code="already_importing",
                message="This document is already imported.",
            )
        return _reuse_submitted_ai_document(
            raced,
            submitted_doc,
            file_path=file_path,
            filename=filename,
            cleanup_temp=cleanup_temp,
            from_url=from_url,
            source_url=source_url,
            resolved=resolved,
        )

    keeper = find_same_content_ai_document(content_hash) if content_hash else None
    if keeper is None:
        keeper = find_reclaimable_ai_document(
            content_hash=content_hash,
            source_url=source_url or getattr(submitted_doc, "source_url", None),
            exclude_submitted_document_id=submitted_doc_id,
        )
    if keeper is not None:
        return _attach_submitted_catalog_entry(
            keeper,
            submitted_doc,
            submitted_doc_id=submitted_doc_id,
            file_path=file_path,
            filename=filename,
            cleanup_temp=cleanup_temp,
            from_url=from_url,
            source_url=source_url,
            content_hash=content_hash,
            file_type=file_type,
            file_size=file_size,
            storage_path_for_ai=storage_path_for_ai,
            derived_country=derived_country,
            uid=uid,
        )

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
        is_public=_submitted_is_ai_public(submitted_doc),
        searchable=True,
        country_id=(int(getattr(derived_country, "id", 0)) or None) if derived_country else None,
        country_name=(getattr(derived_country, "name", None) if derived_country else None),
    )

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


def _prepare_guidance_document_ai_import(
    guidance_doc_id: int,
    *,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Resolve a guidance file and create/update the linked AIDocument (staff-only)."""
    from app.models import AIDocument, GuidanceDocument
    from app.services.platform import storage_service as _ai_storage
    from app.services.ai.documents.processor import AIDocumentProcessor

    guidance = GuidanceDocument.query.get(guidance_doc_id)
    if not guidance:
        return {
            "ok": False,
            "code": "guidance_document_not_found",
            "message": "Guidance document not found",
        }

    rel = (guidance.storage_path or "").strip()
    if not rel or not _ai_storage.exists(_ai_storage.ADMIN_DOCUMENTS, rel):
        return {
            "ok": False,
            "code": "file_not_found",
            "message": "Guidance file not found in storage",
        }

    file_path = _ai_storage.get_absolute_path(_ai_storage.ADMIN_DOCUMENTS, rel)
    cleanup_temp = bool(_ai_storage.is_azure())
    filename = guidance.filename or "document"

    existing_ai_doc = AIDocument.query.filter_by(guidance_document_id=int(guidance_doc_id)).first()
    if existing_ai_doc:
        existing_ai_doc.processing_status = "pending"
        existing_ai_doc.processing_error = None
        existing_ai_doc.title = guidance.title or filename
        existing_ai_doc.filename = filename
        existing_ai_doc.is_public = False
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

    content_hash = processor.calculate_content_hash(file_path)
    file_type = processor.get_file_type(filename)
    try:
        file_size = os.path.getsize(file_path)
    except OSError:
        file_size = guidance.file_size_bytes

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
            uid = int(getattr(guidance, "uploaded_by_user_id", 0) or 0) or None
        except (TypeError, ValueError):
            uid = None

    from app.services.ai.documents.duplicates import find_same_content_ai_document
    from app.services.ai.documents.submitted_metadata import record_guidance_catalog_entry

    _lock_import_keys(guidance_document_id=int(guidance_doc_id), content_hash=content_hash)
    raced = AIDocument.query.filter_by(guidance_document_id=int(guidance_doc_id)).first()
    if raced is not None:
        if _parallel_import_should_skip(raced):
            return _import_skip_result(
                raced,
                file_path=file_path,
                filename=filename,
                cleanup_temp=cleanup_temp,
                code="already_importing",
                message="This guidance document is already imported.",
            )
        raced.processing_status = "pending"
        raced.processing_error = None
        raced.title = guidance.title or filename
        raced.filename = filename
        raced.is_public = False
        db.session.commit()
        return {
            "ok": True,
            "code": "reprocessing",
            "message": "Processing started",
            "ai_document_id": raced.id,
            "file_path": file_path,
            "filename": filename,
            "cleanup_temp": cleanup_temp,
            "skip_processing": False,
        }

    keeper = find_same_content_ai_document(content_hash) if content_hash else None
    if keeper is not None:
        if not getattr(keeper, "guidance_document_id", None):
            keeper.guidance_document_id = int(guidance_doc_id)
        record_guidance_catalog_entry(keeper, guidance)
        if _ai_document_is_embedded(keeper):
            db.session.commit()
            logger.info(
                "Linked guidance document %s to existing AI document %s (same file bytes)",
                guidance_doc_id,
                keeper.id,
            )
            return _import_skip_result(
                keeper,
                file_path=file_path,
                filename=filename,
                cleanup_temp=cleanup_temp,
                code="catalog_alias",
                message=(
                    "This file is already in the knowledge base. "
                    "The guidance entry was linked to the existing document."
                ),
            )
        keeper.processing_status = "pending"
        keeper.processing_error = None
        db.session.commit()
        return {
            "ok": True,
            "code": "catalog_alias",
            "message": "Processing started",
            "ai_document_id": keeper.id,
            "file_path": file_path,
            "filename": filename,
            "cleanup_temp": cleanup_temp,
            "skip_processing": False,
        }

    extra_metadata = {
        "source": "guidance_document",
        "guidance_owner_key": guidance.owner_key,
    }
    ai_doc = AIDocument(
        guidance_document_id=int(guidance_doc_id),
        title=guidance.title or filename,
        filename=filename,
        file_type=file_type,
        file_size_bytes=file_size,
        storage_path=rel,
        content_hash=content_hash,
        processing_status="pending",
        user_id=uid,
        is_public=False,
        searchable=True,
        document_category="guideline",
        extra_metadata=extra_metadata,
    )
    db.session.add(ai_doc)
    db.session.commit()
    logger.info(
        "Prepared AI import for guidance document %s -> AI doc %s (user_id=%s, owner=%s)",
        guidance_doc_id,
        ai_doc.id,
        uid,
        guidance.owner_key,
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
    if prep.get("skip_processing"):
        _discard_temp_import_file(prep)
        return {
            "ok": True,
            "code": prep.get("code") or "catalog_alias",
            "message": prep.get("message") or "Already imported",
            "ai_document_id": prep.get("ai_document_id"),
        }
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
    if prep.get("skip_processing"):
        _discard_temp_import_file(prep)
        return {
            "ok": True,
            "code": prep.get("code") or "catalog_alias",
            "message": prep.get("message") or "Already imported",
            "ai_document_id": prep.get("ai_document_id"),
        }

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
