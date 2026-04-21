"""
AI Document upload, reprocess, and background processing pipeline routes.
"""

import os
import logging
import threading
import time
import requests
from typing import Dict, Any, Optional

from flask import request, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import or_, null

from app.extensions import db, limiter
from app.models import AIDocument, AIDocumentChunk, AIEmbedding, Country
from app.services.ai_document_processor import AIDocumentProcessor, DocumentProcessingError
from app.services.ai_chunking_service import AIChunkingService
from app.services.ai_metadata_extractor import enrich_document_metadata, classify_chunk_semantic_type, build_heading_hierarchy
from app.services.ai_embedding_service import AIEmbeddingService, EmbeddingError
from app.services.ai_vector_store import AIVectorStore
from app.utils.datetime_helpers import utcnow
from app.routes.admin.shared import admin_required, permission_required
from app.utils.advanced_validation import AdvancedValidator
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_responses import json_accepted, json_bad_request, json_forbidden, json_not_found, json_ok, json_server_error
from app.services import storage_service as _storage

from . import ai_docs_bp
from .helpers import (
    MAX_AI_DOCUMENT_SIZE,
    _ai_doc_exists,
    _ai_doc_storage_delete,
    _try_claim_inflight_document,
    _release_inflight_document,
    _summarize_processing_error,
    _validate_ifrc_fetch_url,
    _download_ifrc_document,
)

logger = logging.getLogger(__name__)


# In-memory current step during sync (status endpoint reads this; no DB column)
_document_processing_stage: Dict[int, str] = {}


def get_document_processing_stage(document_id: int) -> Optional[str]:
    """Return current processing step for document_id if processing in this process."""
    return _document_processing_stage.get(document_id)


@ai_docs_bp.route('/upload', methods=['POST'])
@admin_required
@permission_required('admin.documents.manage')
@limiter.limit("10 per minute")
def upload_document():
    """
    Upload and process a document for AI search.

    Accepts multipart/form-data with:
    - file: Document file (PDF, Word, Excel, etc.)
    - title: Optional title (defaults to filename)
    - is_public: Boolean - whether document is searchable by all users
    - searchable: Boolean - whether to enable AI search

    Returns:
        JSON with document ID and processing status
    """
    try:
        if 'file' not in request.files:
            return json_bad_request('No file provided')

        file = request.files['file']
        if file.filename == '':
            return json_bad_request('No file selected')

        title = request.form.get('title', '').strip() or file.filename
        is_public = request.form.get('is_public', 'false').lower() == 'true'
        searchable = request.form.get('searchable', 'true').lower() == 'true'

        from app.services.authorization_service import AuthorizationService
        if is_public and not AuthorizationService.is_admin(current_user):
            return json_forbidden('Only admins can create public documents')

        processor = AIDocumentProcessor()

        if not processor.is_supported_file(file.filename):
            return json_bad_request(f'Unsupported file type. Supported: {", ".join(processor.SUPPORTED_TYPES.keys())}')

        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)

        if file_size > MAX_AI_DOCUMENT_SIZE:
            return json_bad_request(f'File too large. Maximum size is {MAX_AI_DOCUMENT_SIZE // (1024*1024)}MB')

        file_ext = os.path.splitext(file.filename)[1].lower() if file.filename else ''
        if file_ext:
            mime_valid, detected_mime = AdvancedValidator.validate_mime_type(file, [file_ext])
            if not mime_valid:
                logger.warning(f"MIME type mismatch for {file.filename}: expected {file_ext}, detected {detected_mime}")
                return json_bad_request(f'File content does not match extension. Detected type: {detected_mime or "unknown"}')

        filename = secure_filename(file.filename)
        rel_path = f"temp_{utcnow().timestamp()}_{filename}"
        _storage.upload(_storage.AI_DOCUMENTS, rel_path, file)
        temp_path = _storage.get_absolute_path(_storage.AI_DOCUMENTS, rel_path)

        try:
            content_hash = processor.calculate_content_hash(temp_path)

            existing = AIDocument.query.filter_by(content_hash=content_hash).first()
            if existing:
                os.remove(temp_path)
                return json_ok(
                    document_id=existing.id,
                    message='Document already exists',
                    duplicate=True,
                )

            file_type = processor.get_file_type(filename)
            file_size = os.path.getsize(temp_path)

            detected_country_id = None
            detected_country_name = None
            detected_countries = []
            detected_scope = None
            try:
                from app.services.ai_country_detection import detect_countries

                det = detect_countries(filename=filename, title=title, text=None)
                detected_country_id = det.primary_country_id
                detected_country_name = det.primary_country_name
                detected_countries = det.countries
                detected_scope = det.scope
            except Exception as e:
                logger.debug("country detection failed: %s", e)
                detected_country_id, detected_country_name = None, None

            doc = AIDocument(
                title=title,
                filename=filename,
                file_type=file_type,
                file_size_bytes=file_size,
                storage_path=rel_path,
                content_hash=content_hash,
                processing_status='pending',
                user_id=current_user.id,
                is_public=is_public,
                searchable=searchable,
                country_id=detected_country_id,
                country_name=detected_country_name,
                geographic_scope=detected_scope,
            )
            db.session.add(doc)
            db.session.flush()

            if detected_countries:
                from app.models import Country as CountryModel
                for cid, _cname in detected_countries:
                    c = db.session.get(CountryModel, cid)
                    if c and c not in doc.countries:
                        doc.countries.append(c)

            db.session.commit()
            document_id = doc.id
            _run_import_process_in_thread(
                current_app._get_current_object(),
                document_id,
                temp_path,
                filename,
                cleanup_temp=False,
                clear_storage_path=False,
            )
            return json_accepted(
                document_id=document_id,
                status='processing',
                message='Upload started; poll document status for progress.',
            )

        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

    except Exception as e:
        logger.error(f"Document upload error: {e}", exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)


@ai_docs_bp.route('/<int:document_id>/reprocess', methods=['POST'])
@login_required
@limiter.limit("5 per minute")
def reprocess_document(document_id: int):
    """Reprocess a document (re-chunk and re-embed)."""
    try:
        doc = AIDocument.query.get_or_404(document_id)

        from app.services.authorization_service import AuthorizationService
        can_manage_docs = (
            AuthorizationService.is_admin(current_user)
            or AuthorizationService.has_rbac_permission(current_user, "admin.documents.manage")
            or AuthorizationService.has_rbac_permission(current_user, "admin.ai.manage")
        )
        if not can_manage_docs:
            if doc.user_id != current_user.id:
                return json_forbidden('Access denied')

        doc.processing_status = 'pending'
        doc.processing_error = None
        db.session.commit()

        temp_path = None
        file_path = None
        filename = doc.filename or 'document'

        if doc.source_url:
            try:
                temp_path, filename, file_size, content_hash, file_type = _download_ifrc_document(doc.source_url)
                file_path = temp_path
                doc.file_size_bytes = file_size
                doc.content_hash = content_hash
                doc.file_type = file_type
                doc.filename = filename
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to download URL for reprocess: {e}", exc_info=True)
                return json_server_error('Failed to download document.')
        else:
            if not doc.storage_path or not _ai_doc_exists(doc.storage_path):
                return json_not_found('Source file not found')
            if os.path.isabs(doc.storage_path):
                file_path = doc.storage_path
            else:
                file_path = _storage.get_absolute_path(_storage.AI_DOCUMENTS, doc.storage_path)

        try:
            _process_document_sync(document_id, file_path, filename)
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError as e:
                    logger.warning(f"Could not remove temp file {temp_path}: {e}")
            if doc.source_url:
                doc.storage_path = None
                db.session.commit()

        return json_ok(message='Document reprocessed successfully', status='completed')

    except Exception as e:
        logger.error(f"Reprocess document error: {e}", exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)


# ---------------------------------------------------------------------------
# Background processing pipeline
# ---------------------------------------------------------------------------


def _run_import_process_in_thread(
    app,
    document_id: int,
    file_path: str,
    filename: str,
    *,
    cleanup_temp: bool = True,
    clear_storage_path: bool = True,
):
    """
    Run _process_document_sync in a background thread with app context.
    - cleanup_temp: remove file_path after processing (use True for IFRC import temp files).
    - clear_storage_path: set doc.storage_path = None after processing (use True for URL-only IFRC docs).
    """
    def run():
        with app.app_context():
            try:
                doc = AIDocument.query.get(document_id)
                if not doc:
                    return
                try:
                    _process_document_sync(document_id, file_path, filename)
                except Exception as e:
                    logger.error(f"Background process failed: {e}", exc_info=True)
                    try:
                        db.session.rollback()
                    except Exception as rb_e:
                        logger.debug("Rollback after process failure: %s", rb_e)
                    try:
                        doc2 = AIDocument.query.get(document_id)
                        if doc2:
                            doc2.processing_status = 'failed'
                            doc2.processing_error = GENERIC_ERROR_MESSAGE
                            db.session.commit()
                    except Exception as update_e:
                        logger.debug("Status update after process failure: %s", update_e)
                        db.session.rollback()
            finally:
                if cleanup_temp and file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except OSError as e:
                        logger.warning(f"Could not remove temp file {file_path}: {e}")
                if clear_storage_path:
                    try:
                        doc = AIDocument.query.get(document_id)
                        if doc:
                            doc.storage_path = None
                            db.session.commit()
                    except Exception as e:
                        logger.error(f"Cleanup error: {e}", exc_info=True)

    t = threading.Thread(target=run, daemon=True)
    t.start()


def _apply_country_detection_to_doc(doc: AIDocument, extracted: dict | None, document_id: int) -> None:
    """
    Run country detection from extracted content and update doc's country_id, country_name,
    geographic_scope, and ai_document_countries M2M. Used by processing and by redetect-country.
    """
    if not isinstance(extracted, dict):
        return
    try:
        linked_country = None
        try:
            if getattr(doc, "submitted_document", None):
                linked_country = getattr(doc.submitted_document, "document_country", None)
        except Exception as e:
            logger.debug("Linked country lookup failed: %s", e)
            linked_country = None

        if linked_country and getattr(linked_country, "id", None):
            logger.info(
                "Country detection bypassed for AI document %s due to linked submitted country id=%s name=%r (existing_scope=%r)",
                document_id,
                int(getattr(linked_country, "id", 0) or 0),
                getattr(linked_country, "name", None),
                getattr(doc, "geographic_scope", None),
            )
            doc.country_id = int(linked_country.id)
            doc.country_name = getattr(linked_country, "name", None)
            if linked_country not in doc.countries:
                doc.countries.append(linked_country)
        else:
            from app.services.ai_country_detection import (
                detect_countries,
                strip_ns_org_references,
            )

            detection_text = extracted.get("text") if isinstance(extracted, dict) else None
            detection_mode = "full_text"
            _src_for_ifrc = str(getattr(doc, "source_url", "") or "").strip()
            is_ifrc_source = bool(_src_for_ifrc) and bool(_validate_ifrc_fetch_url(_src_for_ifrc)[0])
            try:
                if is_ifrc_source and isinstance(extracted, dict):
                    pages = extracted.get("pages") or []
                    if isinstance(pages, list) and pages:
                        first_page = pages[0] if isinstance(pages[0], dict) else {}
                        first_page_text = (first_page.get("text") or "").strip()
                        if first_page_text:
                            _exclude_last_n_lines = 8
                            lines = first_page_text.splitlines()
                            if len(lines) > _exclude_last_n_lines:
                                first_page_text = "\n".join(lines[:-_exclude_last_n_lines]).strip()
                            if first_page_text:
                                _exclude_bottom_fraction = 0.25
                                cut = max(0, int(len(first_page_text) * (1.0 - _exclude_bottom_fraction)))
                                detection_text = first_page_text[:cut].strip() or first_page_text
                            else:
                                raw = (first_page.get("text") or "").strip()
                                cut = max(0, int(len(raw) * 0.75))
                                detection_text = raw[:cut].strip() or raw
                            detection_mode = "ifrc_page_1_exclude_bottom"
            except Exception as e:
                logger.debug("IFRC page detection text extraction failed: %s", e)

            if is_ifrc_source and detection_text:
                _before = len(str(detection_text))
                detection_text = strip_ns_org_references(detection_text)
                if detection_text is not None and len(str(detection_text)) < _before:
                    logger.debug(
                        "Country detection: stripped NS org references from IFRC text (%s -> %s chars)",
                        _before,
                        len(str(detection_text)),
                    )

            logger.info(
                "Country detection input mode for AI document %s: mode=%s source_url=%r text_chars=%s",
                document_id,
                detection_mode,
                getattr(doc, "source_url", None),
                len(str(detection_text)) if detection_text is not None else 0,
            )

            det = detect_countries(
                filename=getattr(doc, "filename", None),
                title=getattr(doc, "title", None),
                text=detection_text,
            )
            doc.country_id = det.primary_country_id
            doc.country_name = det.primary_country_name
            doc.geographic_scope = det.scope
            logger.info(
                "Country detection applied for AI document %s: primary_country_id=%r primary_country_name=%r scope=%r countries=%s",
                document_id,
                det.primary_country_id,
                det.primary_country_name,
                det.scope,
                [name for _cid, name in (det.countries or [])],
            )

            try:
                from app.models.embeddings import ai_document_countries
                from sqlalchemy.dialects.postgresql import insert as pg_insert

                raw = det.countries or []
                country_ids: list[int] = []
                for cid, _cname in raw:
                    try:
                        if cid is not None:
                            country_ids.append(int(cid))
                    except Exception as e:
                        logger.debug("country_id parse failed: %s", e)
                        continue

                db.session.execute(
                    ai_document_countries.delete().where(ai_document_countries.c.ai_document_id == int(document_id))
                )

                if country_ids:
                    seen: set[int] = set()
                    values = []
                    for cid in country_ids:
                        if cid in seen:
                            continue
                        seen.add(cid)
                        values.append({"ai_document_id": int(document_id), "country_id": int(cid)})

                    stmt = pg_insert(ai_document_countries).values(values)
                    stmt = stmt.on_conflict_do_nothing(index_elements=["ai_document_id", "country_id"])
                    db.session.execute(stmt)

                try:
                    db.session.expire(doc, ["countries"])
                except Exception as expire_e:
                    logger.debug("Expire countries after update failed: %s", expire_e)
            except Exception as e:
                logger.warning("Failed to update ai_document_countries for AI document %s: %s", document_id, e)
    except Exception as e:
        logger.warning("Country detection failed for AI document %s: %s", document_id, e)


def _process_document_sync(document_id: int, file_path: str, filename: str):
    """
    Process a document synchronously.

    Steps:
    1. Extract text and metadata
    2. Chunk the document
    3. Generate embeddings
    4. Store in vector database

    Args:
        document_id: ID of the AIDocument record
        file_path: Path to the file
        filename: Original filename
    """
    doc = AIDocument.query.get(document_id)
    if not doc:
        raise ValueError(f"Document {document_id} not found")

    if not _try_claim_inflight_document(int(document_id)):
        logger.warning("Skipping duplicate processing for document %s (already running in this process)", document_id)
        try:
            wait_seconds = int(current_app.config.get("AI_DOCS_DUPLICATE_WAIT_SECONDS", 600) or 600)
        except Exception as e:
            logger.debug("AI_DOCS_DUPLICATE_WAIT_SECONDS config invalid: %s", e)
            wait_seconds = 600
        deadline = time.time() + max(5, min(wait_seconds, 3600))
        while time.time() < deadline:
            try:
                db.session.rollback()
            except Exception as rb_e:
                logger.debug("rollback after claim failed: %s", rb_e)
            d = AIDocument.query.get(document_id)
            if not d:
                return
            status = getattr(d, "processing_status", None)
            if status and status != "processing":
                return
            time.sleep(1)
        return

    try:
        try:
            claim_count = (
                AIDocument.query
                .filter(AIDocument.id == document_id)
                .filter(db.or_(AIDocument.processing_status.is_(None), AIDocument.processing_status != 'processing'))
                .update(
                    {
                        'processing_status': 'processing',
                        'processing_error': None,
                    },
                    synchronize_session=False,
                )
            )
            db.session.commit()
        except Exception as _claim_err:
            db.session.rollback()
            try:
                if getattr(doc, "processing_status", None) == 'processing':
                    logger.warning("Skipping duplicate processing for document %s (already processing)", document_id)
                    return
                doc.processing_status = 'processing'
                doc.processing_error = None
            except Exception as _inner_err:
                logger.debug("claim fallback update failed: %s", _inner_err)
                raise
            db.session.commit()
            claim_count = 1

        if claim_count == 0:
            logger.warning("Skipping duplicate processing for document %s (already claimed by another worker)", document_id)
            try:
                wait_seconds = int(current_app.config.get("AI_DOCS_DUPLICATE_WAIT_SECONDS", 600) or 600)
            except Exception as e:
                logger.debug("wait_seconds config parse failed: %s", e)
                wait_seconds = 600
            deadline = time.time() + max(5, min(wait_seconds, 3600))
            while time.time() < deadline:
                try:
                    db.session.rollback()
                except Exception as rb_e:
                    logger.debug("Rollback during duplicate wait: %s", rb_e)
                d = AIDocument.query.get(document_id)
                if not d:
                    return
                status = getattr(d, "processing_status", None)
                if status and status != "processing":
                    return
                time.sleep(2)
            return

        doc = AIDocument.query.get(document_id)

        _document_processing_stage[document_id] = 'resetting'
        AIDocumentChunk.query.filter_by(document_id=document_id).delete()
        AIEmbedding.query.filter_by(document_id=document_id).delete()
        doc.total_chunks = 0
        doc.total_embeddings = 0
        doc.total_tokens = 0
        doc.total_pages = None
        db.session.commit()

        _document_processing_stage[document_id] = 'extracting'
        logger.info(f"Processing document {document_id}: {filename}")
        processor = AIDocumentProcessor()

        extracted = processor.process_document(
            file_path=file_path,
            filename=filename,
            extract_images=current_app.config.get('AI_MULTIMODAL_ENABLED', False),
            ocr_enabled=current_app.config.get('AI_OCR_ENABLED', False)
        )
        import time as _time_proc
        _time_proc.sleep(0)

        _apply_country_detection_to_doc(doc, extracted, document_id)

        try:
            tables = extracted.get('tables') or []
            enriched_meta = enrich_document_metadata(
                title=getattr(doc, 'title', filename),
                filename=filename,
                text=extracted.get('text', ''),
                total_pages=extracted.get('metadata', {}).get('total_pages'),
                pdf_metadata=extracted.get('metadata'),
                has_tables=len(tables) > 0,
                table_extraction_success=len(tables) > 0,
                source_url=getattr(doc, 'source_url', None),
            )
            doc.document_date = enriched_meta.get('document_date')
            doc.document_language = enriched_meta.get('document_language')
            doc.document_category = enriched_meta.get('document_category')
            doc.quality_score = enriched_meta.get('quality_score')
            doc.source_organization = enriched_meta.get('source_organization')
            db.session.commit()
        except Exception as _meta_err:
            logger.warning("Metadata enrichment failed for doc %s: %s", document_id, _meta_err)

        _document_processing_stage[document_id] = 'chunking'

        logger.info(f"Chunking document {document_id}")
        chunker = AIChunkingService()

        text_chunks = chunker.chunk_document(
            text=extracted['text'],
            pages=extracted.get('pages'),
            sections=extracted.get('sections'),
            strategy='semantic'
        )

        table_chunks = chunker.chunk_tables(extracted.get('tables') or [])

        upr_visual_chunks = chunker.chunk_upr_visuals(
            pages=extracted.get("pages"),
            document_title=getattr(doc, "title", None),
            document_filename=getattr(doc, "filename", None),
        )

        chunks = list(text_chunks) + list(table_chunks) + list(upr_visual_chunks)
        for idx, ch in enumerate(chunks):
            try:
                ch.chunk_index = idx
            except Exception as e:
                logger.debug("Setting chunk_index failed: %s", e)

        doc.total_chunks = len(chunks)
        doc.total_tokens = sum(c.token_count for c in chunks)
        doc.total_pages = extracted['metadata'].get('total_pages')
        _document_processing_stage[document_id] = 'creating_chunks'
        db.session.commit()

        logger.info(f"Creating {len(chunks)} chunk records for document {document_id}")
        chunk_records = []

        for chunk in chunks:
            extra = chunk.metadata
            extra_metadata = (
                extra
                if (extra is not None and isinstance(extra, dict) and len(extra) > 0)
                else null()
            )
            chunk_record = AIDocumentChunk(
                document_id=document_id,
                content=chunk.content,
                content_length=chunk.char_count,
                token_count=chunk.token_count,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                section_title=chunk.section_title,
                chunk_type=chunk.chunk_type,
                overlap_with_previous=chunk.overlap_chars,
                extra_metadata=extra_metadata,
                semantic_type=classify_chunk_semantic_type(chunk.content, chunk.chunk_type),
                heading_hierarchy=build_heading_hierarchy(
                    section_title=chunk.section_title,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    document_title=getattr(doc, 'title', None),
                ),
            )
            db.session.add(chunk_record)
            chunk_records.append(chunk_record)

        db.session.commit()
        _doc_searchable = bool(getattr(doc, "searchable", True))
        db.session.remove()
        import time as _time_inner
        _time_inner.sleep(0)

        if _doc_searchable:
            _document_processing_stage[document_id] = 'embedding'
            logger.info(f"Generating embeddings for document {document_id}")
            embedder = AIEmbeddingService()

            texts = [chunk.content for chunk in chunks]
            embeddings, total_cost = embedder.generate_embeddings_batch(texts, batch_size=100)

            doc = AIDocument.query.get(document_id)
            if doc is None:
                raise ValueError(f"Document {document_id} disappeared during embedding generation")

            doc.embedding_model = embedder.model
            doc.embedding_dimensions = embedder.dimensions
            _document_processing_stage[document_id] = 'storing_embeddings'

            logger.info(f"Storing {len(embeddings)} embeddings for document {document_id}")
            vector_store = AIVectorStore()

            chunks_with_embeddings = [
                (chunk_records[i], embeddings[i], total_cost / len(embeddings))
                for i in range(len(chunks))
            ]

            vector_store.store_document_embeddings(document_id, chunks_with_embeddings)

            logger.info(f"Document {document_id} processing complete. Cost: ${total_cost:.4f}")
        else:
            doc = AIDocument.query.get(document_id)

        if doc is None:
            doc = AIDocument.query.get(document_id)
        doc.processing_status = 'completed'
        doc.processed_at = utcnow()
        db.session.commit()

    except DocumentProcessingError as e:
        logger.error(f"Document processing error: {e}")
        try:
            db.session.rollback()
        except Exception as rb_e:
            logger.debug("Rollback after processing error: %s", rb_e)
        try:
            doc2 = AIDocument.query.get(document_id)
            if doc2:
                doc2.processing_status = 'failed'
                doc2.processing_error = _summarize_processing_error(e)
                db.session.commit()
        except Exception as update_e:
            logger.debug("Status update after processing error: %s", update_e)
            db.session.rollback()
        raise

    except EmbeddingError as e:
        logger.error(f"Embedding generation error: {e}")
        try:
            db.session.rollback()
        except Exception as rb_e:
            logger.debug("Rollback after embedding error: %s", rb_e)
        try:
            doc2 = AIDocument.query.get(document_id)
            if doc2:
                doc2.processing_status = 'failed'
                doc2.processing_error = _summarize_processing_error(e)
                db.session.commit()
        except Exception as update_e:
            logger.debug("Status update after embedding error: %s", update_e)
            db.session.rollback()
        raise

    except Exception as e:
        logger.error(f"Unexpected error processing document: {e}", exc_info=True)
        try:
            db.session.rollback()
        except Exception as rb_e:
            logger.debug("Rollback after unexpected error: %s", rb_e)
        try:
            doc2 = AIDocument.query.get(document_id)
            if doc2:
                doc2.processing_status = 'failed'
                doc2.processing_error = _summarize_processing_error(e)
                db.session.commit()
        except Exception as commit_e:
            logger.debug("commit processing_error failed: %s", commit_e)
            db.session.rollback()
        raise

    finally:
        _document_processing_stage.pop(document_id, None)
        _release_inflight_document(int(document_id))
