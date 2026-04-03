"""
AI Management Routes

Admin interface for managing AI documents, viewing reasoning traces,
and monitoring AI system usage.
"""

import os
import logging
import uuid
import zipfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, current_app, send_file, after_this_request
from flask_login import current_user
from werkzeug.utils import secure_filename
from sqlalchemy import func, desc
from sqlalchemy.orm import joinedload

from app.extensions import db, limiter
from app.routes.admin.shared import admin_permission_required
from app.utils.datetime_helpers import utcnow, ensure_utc
from app.utils.sql_utils import safe_ilike_pattern
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.request_utils import is_json_request, parse_ids_from_request
from app.utils.api_pagination import validate_pagination_params
from app.utils.api_responses import json_accepted, json_bad_request, json_error, json_forbidden, json_not_found, json_ok, json_server_error
from app.utils.error_handling import handle_json_view_exception
from app.services import storage_service as _storage

logger = logging.getLogger(__name__)

bp = Blueprint("ai_management", __name__, url_prefix="/admin/ai")

_REPROCESS_JOB_CANCEL_EVENTS: dict[str, threading.Event] = {}
_REPROCESS_JOB_CANCEL_LOCK = threading.Lock()


def _get_reprocess_job_cancel_event(job_id: str) -> threading.Event:
    with _REPROCESS_JOB_CANCEL_LOCK:
        ev = _REPROCESS_JOB_CANCEL_EVENTS.get(job_id)
        if ev is None:
            ev = threading.Event()
            _REPROCESS_JOB_CANCEL_EVENTS[job_id] = ev
        return ev


def _clear_reprocess_job_cancel_event(job_id: str) -> None:
    with _REPROCESS_JOB_CANCEL_LOCK:
        _REPROCESS_JOB_CANCEL_EVENTS.pop(job_id, None)


def _process_reprocess_job_item_sync(app, *, job_id: str, item_id: int) -> None:
    """Process one bulk reprocess job item (download if needed, clear chunks, re-chunk + re-embed)."""
    with app.app_context():
        from app.models import (
            AIDocument,
            AIDocumentChunk,
            AIEmbedding,
            AIJobItem,
        )
        from app.routes.ai_documents import _process_document_sync, _download_ifrc_document

        cancel_ev = _get_reprocess_job_cancel_event(job_id)
        item = AIJobItem.query.get(int(item_id))
        if not item:
            return

        if cancel_ev.is_set():
            item.status = "cancelled"
            item.error = None
            db.session.commit()
            return

        doc_id = int(item.entity_id) if (item.entity_type == "ai_document" and item.entity_id) else None
        doc = AIDocument.query.get(doc_id) if doc_id else None
        if not doc:
            item.status = "failed"
            item.error = "Document not found"
            db.session.commit()
            return

        temp_path = None
        file_path = None
        filename = doc.filename or "document"

        try:
            item.status = "downloading" if doc.source_url else "processing"
            item.error = None
            db.session.commit()

            # Set pending immediately so status polls show "in progress"
            doc.processing_status = "pending"
            doc.processing_error = None
            db.session.commit()

            if doc.source_url:
                temp_path, filename, file_size, content_hash, file_type = _download_ifrc_document(doc.source_url)
                file_path = temp_path
                doc.file_size_bytes = file_size
                doc.content_hash = content_hash
                doc.file_type = file_type
                doc.filename = filename
                db.session.commit()
            else:
                if not doc.storage_path or not os.path.exists(doc.storage_path):
                    raise FileNotFoundError(
                        "Source file not found. This document has no source URL; reprocess requires a local file or a document imported from IFRC API."
                    )
                file_path = doc.storage_path

            if cancel_ev.is_set():
                item = AIJobItem.query.get(int(item_id))
                if item:
                    item.status = "cancelled"
                    item.error = None
                    db.session.commit()
                return

            # Clear old chunks and embeddings before reprocessing
            AIDocumentChunk.query.filter_by(document_id=int(doc.id)).delete()
            AIEmbedding.query.filter_by(document_id=int(doc.id)).delete()
            doc.total_chunks = 0
            doc.total_embeddings = 0
            doc.processing_status = "pending"
            doc.processing_error = None
            db.session.commit()

            item = AIJobItem.query.get(int(item_id))
            if item:
                item.status = "processing"
                item.error = None
                db.session.commit()

            _process_document_sync(int(doc.id), file_path, filename)

            # Finalize item status based on document status
            doc = AIDocument.query.get(int(doc.id))
            item = AIJobItem.query.get(int(item_id))
            if item:
                if cancel_ev.is_set():
                    item.status = "cancelled"
                    item.error = None
                elif doc and doc.processing_status == "completed":
                    item.status = "completed"
                    item.error = None
                else:
                    item.status = "failed"
                    item.error = (doc.processing_error if doc else None) or "Processing failed"
                db.session.commit()

        except Exception as e:
            logger.error("Bulk reprocess item failed: job=%s item=%s err=%s", job_id, item_id, e, exc_info=True)
            try:
                # Best-effort: reflect failure on the document row as well, so the grid/status endpoint
                # doesn't keep showing "pending" forever when we fail before calling the processor.
                try:
                    if doc is not None:
                        doc.processing_status = "failed"
                        doc.processing_error = "Processing failed."
                        db.session.commit()
                except Exception as e:
                    current_app.logger.debug("AI job item error update failed: %s", e)
                    db.session.rollback()
                item = AIJobItem.query.get(int(item_id))
                if item:
                    item.status = "failed"
                    item.error = "Processing failed."
                    db.session.commit()
            except Exception as e:
                current_app.logger.debug("AI job item error update (2) failed: %s", e)
                db.session.rollback()
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            # Clear storage_path for source_url docs (keep reference-only behavior)
            try:
                if doc and getattr(doc, "source_url", None):
                    doc = AIDocument.query.get(int(doc.id))
                    if doc:
                        doc.storage_path = None
                        db.session.commit()
            except Exception as e:
                current_app.logger.debug("AI storage_path clear failed: %s", e)
                db.session.rollback()


def _run_bulk_reprocess_job(app, job_id: str) -> None:
    """Background runner for bulk reprocess jobs."""
    with app.app_context():
        from app.models import AIJob

        job = AIJob.query.get(str(job_id))
        if not job:
            return
        if job.status in ("completed", "failed", "cancelled"):
            return
        job.status = "running"
        job.started_at = utcnow()
        db.session.commit()

    cancel_ev = _get_reprocess_job_cancel_event(str(job_id))
    try:
        with app.app_context():
            from app.models import AIJob

            job = AIJob.query.get(str(job_id))
            if not job:
                return
            concurrency = int((job.meta or {}).get("concurrency") or current_app.config.get("AI_DOCS_REPROCESS_CONCURRENCY", 1))
            concurrency = max(1, min(concurrency, 4))
            item_ids = [it.id for it in (job.items or []) if (it.status or "queued") == "queued"]

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = []
            for item_id in item_ids:
                if cancel_ev.is_set():
                    break
                futures.append(pool.submit(_process_reprocess_job_item_sync, app, job_id=str(job_id), item_id=int(item_id)))
            for _f in as_completed(futures):
                if cancel_ev.is_set():
                    continue

        with app.app_context():
            from app.models import AIJob

            job = AIJob.query.get(str(job_id))
            if not job:
                return
            if cancel_ev.is_set() or job.status == "cancel_requested":
                try:
                    for it in (job.items or []):
                        if it.status == "queued":
                            it.status = "cancelled"
                    db.session.commit()
                except Exception as e:
                    current_app.logger.debug("AI job cancel commit failed: %s", e)
                    db.session.rollback()
                job.status = "cancelled"
            else:
                terminal = {"completed", "failed", "cancelled"}
                all_terminal = all((it.status in terminal) for it in (job.items or []))
                job.status = "completed" if all_terminal else "failed"
            job.finished_at = utcnow()
            db.session.commit()
    except Exception as e:
        logger.error("Bulk reprocess job failed: job=%s err=%s", job_id, e, exc_info=True)
        with app.app_context():
            from app.models import AIJob

            job = AIJob.query.get(str(job_id))
            if job:
                job.status = "failed"
                job.error = "Processing failed."
                job.finished_at = utcnow()
                db.session.commit()
    finally:
        _clear_reprocess_job_cancel_event(str(job_id))


def _check_ai_tables_exist():
    """
    Check if AI tables exist in database.

    Includes RAG tables (documents, embeddings, traces, tool_usage) and
    chat persistence (conversation, message) so both admin and chat endpoints
    can rely on a consistent "AI feature available" check.
    """
    try:
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        required_tables = [
            'ai_documents',
            'ai_embeddings',
            'ai_reasoning_traces',
            'ai_tool_usage',
            'ai_conversation',
            'ai_message',
        ]
        existing_tables = inspector.get_table_names()
        return all(table in existing_tables for table in required_tables)
    except Exception as e:
        current_app.logger.debug("_has_required_tables check failed: %s", e)
        return False


def _check_ai_reprocess_job_tables_exist() -> bool:
    """Check if generic AI job tables exist (after migrations)."""
    try:
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        required_tables = [
            "ai_jobs",
            "ai_job_items",
        ]
        existing_tables = inspector.get_table_names()
        return all(t in existing_tables for t in required_tables)
    except Exception as e:
        current_app.logger.debug("_has_tables check failed: %s", e)
        return False


# ============================================================================
# DOCUMENT LIBRARY
# ============================================================================

def _get_default_doc_stats():
    """Return default document stats structure."""
    return {
        'total_documents': 0,
        'completed': 0,
        'pending': 0,
        'processing': 0,
        'failed': 0,
        'total_chunks': 0,
        'total_embeddings': 0,
    }


def _auto_recover_stale_processing_documents() -> int:
    """
    Best-effort recovery for stale `processing` rows when opening AI documents page.
    Marks long-stale rows as failed if there is no active in-process stage and no
    active import/reprocess job item linked to the document.
    """
    try:
        from app.models import AIDocument

        timeout_seconds = int(
            current_app.config.get("AI_DOCS_AUTOFIX_STALE_PROCESSING_TIMEOUT_SECONDS", 900) or 900
        )
        timeout_seconds = max(60, min(timeout_seconds, 86400))
        cutoff = utcnow() - timedelta(seconds=timeout_seconds)

        stale_candidates = (
            db.session.query(AIDocument.id)
            .filter(AIDocument.processing_status == "processing")
            .filter(
                db.or_(
                    db.and_(AIDocument.updated_at.is_(None), AIDocument.created_at <= cutoff),
                    AIDocument.updated_at <= cutoff,
                )
            )
            .all()
        )
        candidate_ids = [int(r[0]) for r in stale_candidates if r and r[0] is not None]
        if not candidate_ids:
            return 0

        # Keep docs that have an active in-process stage (same worker/process).
        try:
            from app.routes.ai_documents import get_document_processing_stage

            candidate_ids = [doc_id for doc_id in candidate_ids if not get_document_processing_stage(int(doc_id))]
        except Exception as e:
            current_app.logger.debug("Document processing stage filter failed: %s", e)
        if not candidate_ids:
            return 0

        # Keep docs that are still tied to active queue/job items (best-effort).
        if _check_ai_reprocess_job_tables_exist():
            try:
                from app.models import AIJobItem

                active_job_ids = {
                    int(r[0]) for r in (
                        db.session.query(AIJobItem.entity_id)
                        .filter(
                            AIJobItem.entity_type == "ai_document",
                            AIJobItem.entity_id.isnot(None),
                            AIJobItem.status.in_(("queued", "downloading", "processing")),
                        )
                        .distinct()
                        .all()
                    ) if r and r[0] is not None
                }
                if active_job_ids:
                    candidate_ids = [doc_id for doc_id in candidate_ids if int(doc_id) not in active_job_ids]
            except Exception as e:
                current_app.logger.debug("Active job filter failed: %s", e)
        if not candidate_ids:
            return 0

        updated = (
            db.session.query(AIDocument)
            .filter(AIDocument.id.in_(candidate_ids))
            .filter(AIDocument.processing_status == "processing")
            .update(
                {
                    AIDocument.processing_status: "failed",
                    AIDocument.processing_error: "Recovered from stale processing state on page load.",
                },
                synchronize_session=False,
            )
        )
        if updated:
            db.session.commit()
            logger.info(
                "Auto-recovered stale AI docs on documents page: count=%s timeout_seconds=%s",
                int(updated),
                timeout_seconds,
            )
        return int(updated or 0)
    except Exception as e:
        db.session.rollback()
        logger.warning("Auto-recover stale processing skipped due to error: %s", e)
        return 0


@bp.route("/documents", methods=["GET"])
@admin_permission_required('admin.ai.manage')
def document_library():
    """AI Document Library - manage documents for RAG system."""
    if not _check_ai_tables_exist():
        return render_template(
            "admin/ai/documents.html",
            documents=[],
            stats=_get_default_doc_stats(),
            file_types=[],
            categories=[],
            languages=[],
            current_status='',
            current_file_type='',
            current_category='',
            current_language='',
            search_query='',
            error="AI tables not found. Please run 'flask db upgrade' to create them.",
            title="AI Knowledge Base"
        )

    try:
        from app.models import AIDocument, AIDocumentChunk, AIEmbedding

        # Self-heal stale "processing" rows before rendering the page.
        _auto_recover_stale_processing_documents()

        # Get query parameters (filters still supported for bookmarkable URLs)
        status_filter = request.args.get('status', '')
        file_type_filter = request.args.get('file_type', '')
        category_filter = request.args.get('category', '')
        language_filter = request.args.get('language', '')
        search_query = request.args.get('q', '').strip()

        # Build query – load ALL documents so AG Grid can handle
        # client-side pagination, sorting, and filtering.
        query = db.session.query(AIDocument).options(
            joinedload(AIDocument.country),
            joinedload(AIDocument.countries),
        )

        if status_filter:
            query = query.filter(AIDocument.processing_status == status_filter)
        if file_type_filter:
            query = query.filter(AIDocument.file_type == file_type_filter)
        if category_filter:
            query = query.filter(AIDocument.document_category == category_filter)
        if language_filter:
            query = query.filter(AIDocument.document_language == language_filter)
        if search_query:
            from app.utils.sql_utils import safe_ilike_pattern
            safe_pattern = safe_ilike_pattern(search_query)
            query = query.filter(
                db.or_(
                    AIDocument.title.ilike(safe_pattern),
                    AIDocument.filename.ilike(safe_pattern)
                )
            )

        # Order by most recently changed so re-imported/reprocessed docs show up immediately.
        query = query.order_by(AIDocument.updated_at.desc(), AIDocument.created_at.desc())

        # Fetch all documents (AG Grid handles client-side pagination)
        documents = query.all()
        logger.info(
            "AI document library loaded: user_id=%s total=%s filters(status=%s file_type=%s q=%s)",
            getattr(current_user, "id", None),
            len(documents),
            status_filter or "",
            file_type_filter or "",
            search_query or "",
        )

        # Get statistics
        stats = {
            'total_documents': db.session.query(AIDocument).count(),
            'completed': db.session.query(AIDocument).filter_by(processing_status='completed').count(),
            'pending': db.session.query(AIDocument).filter_by(processing_status='pending').count(),
            'processing': db.session.query(AIDocument).filter_by(processing_status='processing').count(),
            'failed': db.session.query(AIDocument).filter_by(processing_status='failed').count(),
            'total_chunks': db.session.query(AIDocumentChunk).count(),
            'total_embeddings': db.session.query(AIEmbedding).count(),
        }

        # Get unique file types for filter
        file_types = db.session.query(AIDocument.file_type).distinct().all()
        file_types = [ft[0] for ft in file_types if ft[0]]

        # Get unique categories and languages for new filters
        categories = db.session.query(AIDocument.document_category).distinct().all()
        categories = sorted([c[0] for c in categories if c[0]])
        languages = db.session.query(AIDocument.document_language).distinct().all()
        languages = sorted([la[0] for la in languages if la[0]])

        return render_template(
            "admin/ai/documents.html",
            documents=documents,
            stats=stats,
            file_types=file_types,
            categories=categories,
            languages=languages,
            current_status=status_filter,
            current_file_type=file_type_filter,
            current_category=category_filter,
            current_language=language_filter,
            search_query=search_query,
            title="AI Knowledge Base",
        )

    except Exception as e:
        logger.error(f"Error loading document library: {e}", exc_info=True)
        return render_template(
            "admin/ai/documents.html",
            documents=[],
            stats=_get_default_doc_stats(),
            file_types=[],
            categories=[],
            languages=[],
            current_status='',
            current_file_type='',
            current_category='',
            current_language='',
            search_query='',
            error="An error occurred.",
            title="AI Knowledge Base",
        )


@bp.route("/documents/<int:document_id>/delete", methods=["POST"])
@admin_permission_required('admin.ai.manage')
@limiter.limit("20 per minute")
def delete_document(document_id):
    """Delete a document and all its embeddings."""
    try:
        from app.models import AIDocument

        doc = AIDocument.query.get_or_404(document_id)

        if doc.storage_path:
            try:
                from app.routes.ai_documents import _ai_doc_storage_delete
                _ai_doc_storage_delete(doc.storage_path)
            except Exception as e:
                logger.warning(f"Failed to delete file: {e}")

        # Delete from database (cascades to chunks and embeddings)
        db.session.delete(doc)
        db.session.commit()

        logger.info(f"Admin {current_user.email} deleted AI document {document_id}: {doc.filename}")

        return json_ok(message='Document deleted successfully')

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/documents/<int:document_id>/reprocess", methods=["POST"])
@admin_permission_required('admin.ai.manage')
@limiter.limit("5 per minute")
def reprocess_document(document_id):
    """Reprocess a document (re-chunk and re-embed). Uses source_url for IFRC API docs when no local file."""
    try:
        import requests
        from app.models import AIDocument, AIDocumentChunk, AIEmbedding
        from app.routes.ai_documents import _process_document_sync, _download_ifrc_document

        doc = AIDocument.query.get_or_404(document_id)
        # Set pending immediately so status polls show "in progress" instead of stale "completed"
        doc.processing_status = 'pending'
        doc.processing_error = None
        db.session.commit()

        # Capture before processing — _process_document_sync commits
        # internally and may detach current_user from the session.
        admin_email = current_user.email

        temp_path = None
        file_path = None
        filename = doc.filename or 'document'

        if doc.source_url:
            # Document has source URL (e.g. IFRC API): re-fetch, temp save, process, delete temp
            try:
                temp_path, filename, file_size, content_hash, file_type = _download_ifrc_document(doc.source_url)
                file_path = temp_path
                doc.file_size_bytes = file_size
                doc.content_hash = content_hash
                doc.file_type = file_type
                doc.filename = filename
            except requests.exceptions.RequestException as e:
                return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)
        else:
            # Local file only: require stored path and file to exist
            if not doc.storage_path or not os.path.exists(doc.storage_path):
                return json_not_found('Source file not found. This document has no source URL; reprocess requires a local file or a document imported from IFRC API.')
            file_path = doc.storage_path

        # Clear old chunks and embeddings before reprocessing
        AIDocumentChunk.query.filter_by(document_id=document_id).delete()
        AIEmbedding.query.filter_by(document_id=document_id).delete()
        doc.total_chunks = 0
        doc.total_embeddings = 0
        db.session.commit()

        has_source_url = bool(doc.source_url)

        try:
            _process_document_sync(document_id, file_path, filename)
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError as e:
                    logger.warning(f"Could not remove temp file {temp_path}: {e}")
            if has_source_url:
                fresh_doc = db.session.get(AIDocument, document_id)
                if fresh_doc:
                    fresh_doc.storage_path = None
                    db.session.commit()

        logger.info(f"Admin {admin_email} reprocessed AI document {document_id}")
        return json_ok(message='Document reprocessed successfully')

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/documents/<int:document_id>/redetect-country", methods=["POST"])
@admin_permission_required('admin.ai.manage')
@limiter.limit("30 per minute")
def redetect_country_document(document_id):
    """Re-run country detection for a document (extract first page/content, then detect country). No re-chunk or re-embed."""
    try:
        import requests
        from app.models import AIDocument, Country
        from app.routes.ai_documents import _apply_country_detection_to_doc, _download_ifrc_document
        from app.services.ai_document_processor import AIDocumentProcessor

        doc = AIDocument.query.get_or_404(document_id)

        temp_path = None
        file_path = None
        filename = doc.filename or 'document'

        if doc.source_url:
            try:
                temp_path, filename, file_size, content_hash, file_type = _download_ifrc_document(doc.source_url)
                file_path = temp_path
            except requests.exceptions.RequestException as e:
                return handle_json_view_exception(e, 'Failed to download document', status_code=500)
        else:
            if not doc.storage_path or not os.path.exists(doc.storage_path):
                return json_not_found('Source file not found. Redetect country requires a local file or a document imported from IFRC API.')
            file_path = doc.storage_path

        try:
            processor = AIDocumentProcessor()
            extracted = processor.process_document(
                file_path=file_path,
                filename=filename,
                extract_images=False,
                ocr_enabled=current_app.config.get('AI_OCR_ENABLED', False),
            )
            _apply_country_detection_to_doc(doc, extracted, document_id)
            db.session.commit()
            db.session.refresh(doc)
            country_iso3 = None
            if getattr(doc, 'country_id', None):
                c = db.session.get(Country, doc.country_id)
                if c:
                    country_iso3 = getattr(c, 'iso3', None)
            return json_ok(
                message='Country redetected successfully',
                country_id=getattr(doc, 'country_id', None),
                country_name=getattr(doc, 'country_name', None),
                country_iso3=country_iso3,
                geographic_scope=getattr(doc, 'geographic_scope', None),
            )
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError as e:
                    logger.warning("Could not remove temp file %s: %s", temp_path, e)

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/documents/<int:document_id>/reprocess-metadata", methods=["POST"])
@admin_permission_required('admin.ai.manage')
@limiter.limit("30 per minute")
def reprocess_document_metadata(document_id):
    """
    Re-run metadata enrichment (date, language, category, quality, source_org) for a
    single document without re-chunking or re-embedding.  Reads the file, extracts
    text/PDF metadata, then applies enrich_document_metadata().
    """
    try:
        import requests as _requests
        from app.models import AIDocument
        from app.routes.ai_documents import _download_ifrc_document
        from app.services.ai_document_processor import AIDocumentProcessor
        from app.services.ai_metadata_extractor import enrich_document_metadata

        doc = AIDocument.query.get_or_404(document_id)

        temp_path = None
        file_path = None
        filename = doc.filename or 'document'

        if doc.source_url:
            try:
                temp_path, filename, _size, _hash, _ftype = _download_ifrc_document(doc.source_url)
                file_path = temp_path
            except _requests.exceptions.RequestException as e:
                return handle_json_view_exception(e, 'Failed to download document', status_code=500)
        else:
            if not doc.storage_path or not os.path.exists(doc.storage_path):
                return json_not_found('Source file not found. Reprocess metadata requires a local file or a document imported from IFRC API.')
            file_path = doc.storage_path

        try:
            processor = AIDocumentProcessor()
            extracted = processor.process_document(
                file_path=file_path,
                filename=filename,
                extract_images=False,
                ocr_enabled=current_app.config.get('AI_OCR_ENABLED', False),
            )
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
            return json_ok(
                message='Metadata reprocessed successfully',
                document_date=doc.document_date.isoformat() if doc.document_date else None,
                document_language=doc.document_language,
                document_category=doc.document_category,
                quality_score=doc.quality_score,
                source_organization=doc.source_organization,
            )
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError as e:
                    logger.warning("Could not remove temp file %s: %s", temp_path, e)

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/documents/bulk-reprocess", methods=["POST"])
@admin_permission_required('admin.ai.manage')
@limiter.limit("10 per minute")
def bulk_reprocess_documents():
    """
    Start a server-side bulk reprocess job for selected AI documents.

    Accepts JSON {ids:[...], concurrency?:int} or form ids="1,2,3".
    Returns 202 with job_id to poll via /admin/ai/documents/bulk-reprocess/<job_id>/status
    """
    try:
        if not _check_ai_reprocess_job_tables_exist():
            return json_server_error("AI job tables not found. Please run 'flask db upgrade' and try again.")

        from app.models import AIDocument, AIJob, AIJobItem

        ids = parse_ids_from_request("ids")
        concurrency = None
        if is_json_request():
            payload = get_json_safe() or {}
            try:
                concurrency = int(payload.get("concurrency")) if payload.get("concurrency") is not None else None
            except (TypeError, ValueError):
                concurrency = None
        if not ids:
            return json_bad_request("No document IDs provided")
        if len(ids) > 200:
            return json_bad_request("Too many documents selected (max 200)")

        # Concurrency guardrails (reprocess is heavier than import)
        if concurrency is None:
            concurrency = int(current_app.config.get("AI_DOCS_REPROCESS_CONCURRENCY", 1) or 1)
        concurrency = max(1, min(int(concurrency), 4))

        job_id = str(uuid.uuid4())
        job = AIJob(
            id=job_id,
            job_type="docs.bulk_reprocess",
            user_id=int(current_user.id),
            status="queued",
            total_items=len(ids),
            meta={"concurrency": concurrency},
        )
        db.session.add(job)
        db.session.flush()

        # Pre-fetch docs so we can mark missing ones as failed items (stable ordering)
        docs = AIDocument.query.filter(AIDocument.id.in_(ids)).all()
        doc_ids_existing = {int(d.id) for d in docs}

        # Flip selected docs to "pending" immediately to avoid stale "completed" during job queueing.
        # (UI polls `/admin/ai/documents/<id>/status` and would otherwise revert after warmup.)
        try:
            (
                AIDocument.query
                .filter(AIDocument.id.in_(list(doc_ids_existing)))
                .filter(AIDocument.processing_status != "processing")
                .update(
                    {
                        AIDocument.processing_status: "pending",
                        AIDocument.processing_error: None,
                    },
                    synchronize_session=False,
                )
            )
            db.session.commit()
        except Exception as e:
            current_app.logger.debug("AI batch update commit failed: %s", e)
            db.session.rollback()

        for idx, doc_id in enumerate(ids):
            exists = int(doc_id) in doc_ids_existing
            it = AIJobItem(
                job_id=job_id,
                item_index=idx,
                entity_type="ai_document",
                entity_id=int(doc_id) if exists else None,
                status="queued" if exists else "failed",
                error=None if exists else "Document not found",
                payload={"document_id": int(doc_id)},
            )
            db.session.add(it)

        db.session.commit()

        # Kick off background job runner
        t = threading.Thread(
            target=_run_bulk_reprocess_job,
            args=(current_app._get_current_object(), job_id),
            daemon=True,
        )
        t.start()

        return json_accepted(
            success=True,
            job_id=job_id,
            total=len(ids),
            concurrency=concurrency,
            message="Bulk reprocess started",
        )
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/documents/bulk-reprocess/<job_id>/status", methods=["GET"])
@admin_permission_required('admin.ai.manage')
def bulk_reprocess_status(job_id: str):
    """Return job + item statuses for a bulk reprocess job."""
    try:
        if not _check_ai_reprocess_job_tables_exist():
            return json_not_found("not_found")

        from app.models import AIDocument, AIJob

        job = AIJob.query.get(str(job_id))
        if not job:
            return json_not_found("not_found")

        items = job.items or []
        completed = sum(1 for it in items if it.status == "completed")
        failed = sum(1 for it in items if it.status == "failed")
        cancelled = sum(1 for it in items if it.status == "cancelled")
        processing = sum(1 for it in items if it.status in ("downloading", "processing", "queued"))

        doc_ids = [int(it.entity_id) for it in items if (it.entity_type == "ai_document" and it.entity_id)]
        docs_by_id: dict[int, dict] = {}
        if doc_ids:
            docs = AIDocument.query.filter(AIDocument.id.in_(doc_ids)).all()
            for d in docs:
                docs_by_id[int(d.id)] = {
                    "processing_status": d.processing_status,
                    "processing_error": d.processing_error,
                    "total_chunks": d.total_chunks,
                    "processed_at": d.processed_at.isoformat() if d.processed_at else None,
                }

        return json_ok(
            success=True,
            job={
                "id": job.id,
                "job_type": job.job_type,
                "status": job.status,
                "total_items": job.total_items,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                "error": job.error,
                "meta": job.meta or {},
                "counts": {
                    "completed": completed,
                    "failed": failed,
                    "cancelled": cancelled,
                    "in_progress": processing,
                },
            },
            items=[
                    {
                        "id": it.id,
                        "index": it.item_index,
                        "requested_document_id": (it.payload or {}).get("document_id") if isinstance(it.payload, dict) else None,
                        "ai_document_id": (int(it.entity_id) if (it.entity_type == "ai_document" and it.entity_id) else None),
                        "reprocess_status": it.status,
                        "reprocess_error": it.error,
                        "document": docs_by_id.get(int(it.entity_id)) if (it.entity_type == "ai_document" and it.entity_id) else None,
                    }
                for it in items
            ],
        )
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/documents/bulk-reprocess/<job_id>/cancel", methods=["POST"])
@admin_permission_required('admin.ai.manage')
def bulk_reprocess_cancel(job_id: str):
    """Request cancellation for a running bulk reprocess job (best-effort)."""
    try:
        if not _check_ai_reprocess_job_tables_exist():
            return json_not_found("not_found")

        from app.models import AIJob, AIJobItem

        job = AIJob.query.get(str(job_id))
        if not job:
            return json_not_found("not_found")
        if job.status in ("completed", "failed", "cancelled"):
            return json_ok(status=job.status, message="Job already finished")

        job.status = "cancel_requested"
        # Immediately mark still-queued items as cancelled so UI reflects cancellation right away.
        try:
            (
                db.session.query(AIJobItem)
                .filter(
                    AIJobItem.job_id == str(job_id),
                    AIJobItem.status == "queued",
                )
                .update(
                    {
                        AIJobItem.status: "cancelled",
                        AIJobItem.error: None,
                    },
                    synchronize_session=False,
                )
            )
        except Exception as e:
            current_app.logger.debug("AI document update failed: %s", e)
            db.session.rollback()
        db.session.commit()

        _get_reprocess_job_cancel_event(str(job_id)).set()
        return json_ok(status="cancel_requested")
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

def _process_metadata_reprocess_job_item_sync(app, job_id: str, item_id: int) -> None:
    """Run metadata enrichment for a single AIJobItem (metadata-only, no re-chunk/re-embed)."""
    with app.app_context():
        from app.models import AIDocument, AIJobItem
        from app.routes.ai_documents import _download_ifrc_document
        from app.services.ai_document_processor import AIDocumentProcessor
        from app.services.ai_metadata_extractor import enrich_document_metadata

        cancel_ev = _get_reprocess_job_cancel_event(job_id)
        item = AIJobItem.query.get(int(item_id))
        if not item:
            return

        if cancel_ev.is_set():
            item.status = "cancelled"
            db.session.commit()
            return

        doc_id = int(item.entity_id) if (item.entity_type == "ai_document" and item.entity_id) else None
        doc = AIDocument.query.get(doc_id) if doc_id else None
        if not doc:
            item.status = "failed"
            item.error = "Document not found"
            db.session.commit()
            return

        temp_path = None
        file_path = None
        filename = doc.filename or "document"

        try:
            item.status = "downloading" if doc.source_url else "processing"
            item.error = None
            db.session.commit()

            if doc.source_url:
                import requests as _req
                temp_path, filename, _size, _hash, _ftype = _download_ifrc_document(doc.source_url)
                file_path = temp_path
            else:
                if not doc.storage_path or not os.path.exists(doc.storage_path):
                    raise FileNotFoundError("Source file not found for metadata reprocess")
                file_path = doc.storage_path

            if cancel_ev.is_set():
                item = AIJobItem.query.get(int(item_id))
                if item:
                    item.status = "cancelled"
                    db.session.commit()
                return

            item = AIJobItem.query.get(int(item_id))
            if item:
                item.status = "processing"
                db.session.commit()

            processor = AIDocumentProcessor()
            extracted = processor.process_document(
                file_path=file_path,
                filename=filename,
                extract_images=False,
                ocr_enabled=current_app.config.get("AI_OCR_ENABLED", False),
            )
            tables = extracted.get("tables") or []
            enriched_meta = enrich_document_metadata(
                title=getattr(doc, "title", filename),
                filename=filename,
                text=extracted.get("text", ""),
                total_pages=extracted.get("metadata", {}).get("total_pages"),
                pdf_metadata=extracted.get("metadata"),
                has_tables=len(tables) > 0,
                table_extraction_success=len(tables) > 0,
                source_url=getattr(doc, "source_url", None),
            )
            doc = AIDocument.query.get(doc_id)
            doc.document_date = enriched_meta.get("document_date")
            doc.document_language = enriched_meta.get("document_language")
            doc.document_category = enriched_meta.get("document_category")
            doc.quality_score = enriched_meta.get("quality_score")
            doc.source_organization = enriched_meta.get("source_organization")
            db.session.commit()

            item = AIJobItem.query.get(int(item_id))
            if item:
                item.status = "cancelled" if cancel_ev.is_set() else "completed"
                db.session.commit()

        except Exception as e:
            logger.error("Metadata reprocess item failed: job=%s item=%s err=%s", job_id, item_id, e, exc_info=True)
            try:
                item = AIJobItem.query.get(int(item_id))
                if item:
                    item.status = "failed"
                    item.error = str(e)[:500]
                    db.session.commit()
            except Exception:
                db.session.rollback()
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass


def _run_bulk_metadata_reprocess_job(app, job_id: str) -> None:
    """Background runner for bulk metadata reprocess jobs."""
    with app.app_context():
        from app.models import AIJob

        job = AIJob.query.get(str(job_id))
        if not job or job.status in ("completed", "failed", "cancelled"):
            return
        job.status = "running"
        job.started_at = utcnow()
        db.session.commit()

    cancel_ev = _get_reprocess_job_cancel_event(str(job_id))
    try:
        with app.app_context():
            from app.models import AIJob

            job = AIJob.query.get(str(job_id))
            if not job:
                return
            concurrency = max(1, min(int((job.meta or {}).get("concurrency") or 2), 4))
            item_ids = [it.id for it in (job.items or []) if (it.status or "queued") == "queued"]

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = []
            for item_id in item_ids:
                if cancel_ev.is_set():
                    break
                futures.append(pool.submit(_process_metadata_reprocess_job_item_sync, app, str(job_id), int(item_id)))
            for _f in as_completed(futures):
                pass  # errors handled inside item worker

        with app.app_context():
            from app.models import AIJob

            job = AIJob.query.get(str(job_id))
            if not job:
                return
            if cancel_ev.is_set() or job.status == "cancel_requested":
                try:
                    for it in (job.items or []):
                        if it.status == "queued":
                            it.status = "cancelled"
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                job.status = "cancelled"
            else:
                terminal = {"completed", "failed", "cancelled"}
                job.status = "completed" if all((it.status in terminal) for it in (job.items or [])) else "failed"
            job.finished_at = utcnow()
            db.session.commit()
    except Exception as e:
        logger.error("Bulk metadata reprocess job failed: job=%s err=%s", job_id, e, exc_info=True)
        with app.app_context():
            from app.models import AIJob

            job = AIJob.query.get(str(job_id))
            if job:
                job.status = "failed"
                job.error = "Processing failed."
                job.finished_at = utcnow()
                db.session.commit()
    finally:
        _clear_reprocess_job_cancel_event(str(job_id))


@bp.route("/documents/bulk-reprocess-metadata", methods=["POST"])
@admin_permission_required('admin.ai.manage')
@limiter.limit("10 per minute")
def bulk_reprocess_metadata_documents():
    """
    Start a server-side bulk metadata-reprocess job.
    Updates document_date, document_language, document_category, quality_score,
    source_organization without re-chunking or re-embedding.
    Returns 202 with job_id to poll via /admin/ai/documents/bulk-reprocess-metadata/<job_id>/status
    """
    try:
        if not _check_ai_reprocess_job_tables_exist():
            return json_server_error("AI job tables not found. Please run 'flask db upgrade' and try again.")

        from app.models import AIDocument, AIJob, AIJobItem

        ids = parse_ids_from_request("ids")
        if not ids:
            return json_bad_request("No document IDs provided")
        if len(ids) > 200:
            return json_bad_request("Too many documents selected (max 200)")

        job_id = str(uuid.uuid4())
        job = AIJob(
            id=job_id,
            job_type="docs.bulk_reprocess_metadata",
            user_id=int(current_user.id),
            status="queued",
            total_items=len(ids),
            meta={"concurrency": 2},
        )
        db.session.add(job)
        db.session.flush()

        docs = AIDocument.query.filter(AIDocument.id.in_(ids)).all()
        doc_ids_existing = {int(d.id) for d in docs}

        for idx, doc_id in enumerate(ids):
            exists = int(doc_id) in doc_ids_existing
            it = AIJobItem(
                job_id=job_id,
                item_index=idx,
                entity_type="ai_document",
                entity_id=int(doc_id) if exists else None,
                status="queued" if exists else "failed",
                error=None if exists else "Document not found",
                payload={"document_id": int(doc_id)},
            )
            db.session.add(it)

        db.session.commit()

        t = threading.Thread(
            target=_run_bulk_metadata_reprocess_job,
            args=(current_app._get_current_object(), job_id),
            daemon=True,
        )
        t.start()

        return json_accepted(
            success=True,
            job_id=job_id,
            total=len(ids),
            message="Bulk metadata reprocess started",
        )
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/documents/bulk-reprocess-metadata/<job_id>/status", methods=["GET"])
@admin_permission_required('admin.ai.manage')
def bulk_reprocess_metadata_status(job_id: str):
    """Return job + item statuses for a bulk metadata reprocess job."""
    try:
        if not _check_ai_reprocess_job_tables_exist():
            return json_not_found("not_found")

        from app.models import AIJob

        job = AIJob.query.get(str(job_id))
        if not job:
            return json_not_found("not_found")

        items = job.items or []
        completed = sum(1 for it in items if it.status == "completed")
        failed = sum(1 for it in items if it.status == "failed")
        cancelled = sum(1 for it in items if it.status == "cancelled")
        in_progress = sum(1 for it in items if it.status in ("downloading", "processing", "queued"))

        return json_ok(
            success=True,
            job={
                "id": job.id,
                "job_type": job.job_type,
                "status": job.status,
                "total_items": job.total_items,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                "error": job.error,
                "counts": {
                    "completed": completed,
                    "failed": failed,
                    "cancelled": cancelled,
                    "in_progress": in_progress,
                },
            },
            items=[
                {
                    "id": it.id,
                    "index": it.item_index,
                    "ai_document_id": int(it.entity_id) if (it.entity_type == "ai_document" and it.entity_id) else None,
                    "status": it.status,
                    "error": it.error,
                }
                for it in items
            ],
        )
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/documents/bulk-reprocess-metadata/<job_id>/cancel", methods=["POST"])
@admin_permission_required('admin.ai.manage')
def bulk_reprocess_metadata_cancel(job_id: str):
    """Request cancellation for a running bulk metadata reprocess job (best-effort)."""
    try:
        if not _check_ai_reprocess_job_tables_exist():
            return json_not_found("not_found")

        from app.models import AIJob, AIJobItem

        job = AIJob.query.get(str(job_id))
        if not job:
            return json_not_found("not_found")
        if job.status in ("completed", "failed", "cancelled"):
            return json_ok(status=job.status, message="Job already finished")

        job.status = "cancel_requested"
        try:
            (
                db.session.query(AIJobItem)
                .filter(AIJobItem.job_id == str(job_id), AIJobItem.status == "queued")
                .update({AIJobItem.status: "cancelled", AIJobItem.error: None}, synchronize_session=False)
            )
        except Exception:
            db.session.rollback()
        db.session.commit()
        _get_reprocess_job_cancel_event(str(job_id)).set()
        return json_ok(status="cancel_requested")
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/documents/bulk-download", methods=["POST"])
@admin_permission_required('admin.ai.manage')
@limiter.limit("10 per minute")
def bulk_download_documents():
    """
    Download selected AI documents as a ZIP.

    Supports:
    - Local documents with storage_path
    - IFRC API documents that only have source_url (downloaded server-side via validated IFRC fetch helper)
    """
    try:
        from app.models import AIDocument
        from app.routes.ai_documents import _download_ifrc_document
        from app.utils.file_paths import (
            get_upload_base_path,
            get_temp_upload_path,
            ensure_dir,
            normalize_stored_relative_path,
            resolve_under,
        )

        ids = parse_ids_from_request("ids")
        if not ids:
            return json_bad_request('No document IDs provided')

        # Guardrail to avoid overly large zips / accidental huge selections
        if len(ids) > 200:
            return json_bad_request('Too many documents selected (max 200)')

        docs = AIDocument.query.filter(AIDocument.id.in_(ids)).all()
        doc_map = {d.id: d for d in docs}

        ensure_dir(get_temp_upload_path())
        zip_basename = f"ai_documents_bulk_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.zip"
        zip_path = os.path.join(get_temp_upload_path(), zip_basename)

        upload_base = get_upload_base_path()
        upload_folder_cfg = current_app.config.get('UPLOAD_FOLDER', 'uploads')
        upload_folder_rel = None
        try:
            if upload_folder_cfg and not os.path.isabs(str(upload_folder_cfg)):
                upload_folder_rel = normalize_stored_relative_path(str(upload_folder_cfg))
        except Exception as e:
            current_app.logger.debug("upload_folder normalize failed: %s", e)
            upload_folder_rel = None

        def _resolve_local_path(storage_path: str | None) -> str | None:
            sp = (storage_path or '').strip()
            if not sp:
                return None
            if os.path.isabs(sp):
                # Safety: only allow files under uploads base
                try:
                    base_real = os.path.realpath(upload_base)
                    cand_real = os.path.realpath(sp)
                    if not cand_real.startswith(base_real + os.sep) and cand_real != base_real:
                        return None
                except Exception as e:
                    current_app.logger.debug("resolve_under path check failed: %s", e)
                    return None
                return sp
            rel = normalize_stored_relative_path(sp)
            # Some legacy rows may store "uploads/<...>" even though UPLOAD_FOLDER already points at uploads.
            if upload_folder_rel and rel.startswith(upload_folder_rel + '/'):
                rel = rel[len(upload_folder_rel) + 1:]
            try:
                return resolve_under(upload_base, rel)
            except Exception as e:
                current_app.logger.debug("resolve_under failed: %s", e)
                return None

        errors: list[str] = []
        added_count = 0
        used_names: set[str] = set()

        def _unique_arcname(name: str) -> str:
            base = name or 'document'
            if base not in used_names:
                used_names.add(base)
                return base
            root, ext = os.path.splitext(base)
            i = 2
            while True:
                candidate = f"{root}_{i}{ext}"
                if candidate not in used_names:
                    used_names.add(candidate)
                    return candidate
                i += 1

        with zipfile.ZipFile(zip_path, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
            for doc_id in ids:
                doc = doc_map.get(doc_id)
                if not doc:
                    errors.append(f"{doc_id}: not found")
                    continue

                temp_path = None
                try:
                    if doc.source_url:
                        # IFRC API doc: fetch to temp file (validated + authenticated), then zip it
                        temp_path, fetched_filename, _, _, _ = _download_ifrc_document(doc.source_url)
                        arc = secure_filename(f"{doc.id}_{fetched_filename}") or f"{doc.id}_document"
                        arc = _unique_arcname(arc)
                        zf.write(temp_path, arcname=arc)
                        added_count += 1
                    else:
                        if doc.storage_path and not os.path.isabs(doc.storage_path):
                            if not _storage.exists(_storage.AI_DOCUMENTS, doc.storage_path):
                                errors.append(f"{doc.id}: file not found (filename={doc.filename})")
                                continue
                            temp_path = _storage.get_absolute_path(_storage.AI_DOCUMENTS, doc.storage_path)
                            arc = secure_filename(f"{doc.id}_{doc.filename}") or f"{doc.id}_document"
                            arc = _unique_arcname(arc)
                            zf.write(temp_path, arcname=arc)
                            added_count += 1
                        else:
                            file_path = _resolve_local_path(doc.storage_path)
                            if not file_path or not os.path.exists(file_path):
                                errors.append(f"{doc.id}: file not found (filename={doc.filename}, storage_path={doc.storage_path})")
                                continue
                            arc = secure_filename(f"{doc.id}_{doc.filename}") or f"{doc.id}_document"
                            arc = _unique_arcname(arc)
                            zf.write(file_path, arcname=arc)
                            added_count += 1
                except Exception as e:
                    errors.append(f"{doc.id}: failed to include ({e})")
                finally:
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except Exception as e:
                            logger.debug("Temp file cleanup failed: %s", e)

            if errors:
                zf.writestr('__errors.txt', '\n'.join(errors) + '\n')

            if added_count == 0 and not errors:
                zf.writestr('__errors.txt', 'No documents were added to this zip.\n')

        @after_this_request
        def _cleanup(response):
            try:
                if os.path.exists(zip_path):
                    os.remove(zip_path)
            except Exception as e:
                logger.debug("Zip cleanup failed: %s", e)
            return response

        download_name = f"ai_documents_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
        return send_file(
            zip_path,
            as_attachment=True,
            download_name=download_name,
            mimetype='application/zip'
        )

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/documents/<int:document_id>/status", methods=["GET"])
@admin_permission_required('admin.ai.manage')
def document_processing_status(document_id):
    """Return processing status and inferred stage for a document."""
    try:
        from app.models import AIDocument

        # Use get() (not get_or_404) so deleted docs don't spam error logs
        doc = AIDocument.query.get(document_id)
        if not doc:
            return json_not_found(
                "not_found",
                success=False,
                error="not_found",
                document={"id": document_id},
                stage="Not Found",
                progress=100,
            )

        # In-memory step (set during _process_document_sync) for accurate banner during process
        from app.routes.ai_documents import get_document_processing_stage
        current_stage = get_document_processing_stage(document_id)

        # Stuck detection:
        # If DB says 'processing' but there's no active in-memory stage in THIS process, the work may be:
        # - interrupted (server restart), OR
        # - running in another worker/process (stage is in-memory and not shared).
        #
        # To avoid false-failing valid jobs (multi-worker) and to avoid duplicate logs (concurrent polls),
        # only mark as failed after a configurable grace period, and do it with an atomic UPDATE.
        #
        if doc.processing_status == 'processing' and current_stage is None:
            timeout_seconds = int(current_app.config.get("AI_DOCS_STUCK_NO_STAGE_TIMEOUT_SECONDS", 3600))
            # Prefer updated_at; it changes on commits during processing. Fall back to created_at.
            last_touched = ensure_utc(doc.updated_at or doc.created_at or utcnow())
            age_seconds = (utcnow() - last_touched).total_seconds()

            if age_seconds >= timeout_seconds:
                updated = (
                    db.session.query(AIDocument)
                    .filter(
                        AIDocument.id == document_id,
                        AIDocument.processing_status == 'processing',
                    )
                    .update(
                        {
                            AIDocument.processing_status: 'failed',
                            AIDocument.processing_error: 'Processing appears stuck or was interrupted (no active stage).',
                        },
                        synchronize_session=False,
                    )
                )
                if updated:
                    db.session.commit()
                    logger.info("Marked document %s as failed (stuck processing, no active stage)", document_id)
                    # Refresh doc so the response matches the DB.
                    doc = AIDocument.query.get(document_id)

        # Pending can also become stale (e.g., server restart, abandoned job queue).
        # If it remains pending for too long with no active stage, mark as failed so
        # the frontend banner doesn't remain stuck forever.
        if doc.processing_status == 'pending' and current_stage is None:
            pending_timeout_seconds = int(current_app.config.get("AI_DOCS_STUCK_PENDING_TIMEOUT_SECONDS", 900))
            last_touched = ensure_utc(doc.updated_at or doc.created_at or utcnow())
            pending_age_seconds = (utcnow() - last_touched).total_seconds()
            has_active_job_item = False
            try:
                from app.models import AIJobItem
                has_active_job_item = (
                    db.session.query(AIJobItem.id)
                    .filter(
                        AIJobItem.entity_type == "ai_document",
                        AIJobItem.entity_id == int(document_id),
                        AIJobItem.status.in_(("queued", "downloading", "processing")),
                    )
                    .first()
                    is not None
                )
            except Exception as e:
                current_app.logger.debug("has_active_job_item check failed: %s", e)
                has_active_job_item = False

            should_mark_pending_failed = (
                pending_age_seconds >= pending_timeout_seconds
                or (pending_age_seconds >= 120 and not has_active_job_item)
            )

            if should_mark_pending_failed:
                updated = (
                    db.session.query(AIDocument)
                    .filter(
                        AIDocument.id == document_id,
                        AIDocument.processing_status == 'pending',
                    )
                    .update(
                        {
                            AIDocument.processing_status: 'failed',
                            AIDocument.processing_error: 'Processing queue appears stale or interrupted.',
                        },
                        synchronize_session=False,
                    )
                )
                if updated:
                    db.session.commit()
                    logger.info(
                        "Marked document %s as failed (stale pending, no active stage, age=%.0fs, active_job=%s)",
                        document_id,
                        pending_age_seconds,
                        has_active_job_item,
                    )
                    doc = AIDocument.query.get(document_id)

        _STAGE_PROGRESS = {
            'extracting': ('Extracting text', 15),
            'chunking': ('Chunking', 35),
            'creating_chunks': ('Creating chunks', 50),
            'embedding': ('Generating embeddings', 70),
            'storing_embeddings': ('Storing embeddings', 90),
        }
        if doc.processing_status == 'processing' and current_stage:
            stage, progress = _STAGE_PROGRESS.get(current_stage, ('Processing', 25))
        elif doc.processing_status == 'processing':
            if doc.total_chunks and doc.embedding_model:
                stage, progress = 'Embedding', 75
            elif doc.total_chunks:
                stage, progress = 'Chunking', 50
            else:
                stage, progress = 'Extracting text', 25
        elif doc.processing_status == 'pending':
            stage, progress = 'Queued', 10
        elif doc.processing_status == 'completed':
            stage, progress = 'Done', 100
        else:
            stage, progress = 'Failed', 100

        return json_ok(
            document={
                'id': doc.id,
                'processing_status': doc.processing_status,
                'processing_error': doc.processing_error,
                'total_chunks': doc.total_chunks,
                'embedding_model': doc.embedding_model,
                'processed_at': doc.processed_at.isoformat() if doc.processed_at else None
            },
            stage=stage,
            progress=progress,
        )

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/documents/process-submitted/<int:submitted_doc_id>", methods=["POST"])
@admin_permission_required('admin.ai.manage')
@limiter.limit("10 per minute")
def process_submitted_document(submitted_doc_id):
    """Process a submitted document through the AI system."""
    try:
        from app.models import SubmittedDocument, AIDocument
        from app.routes.ai_documents import _process_document_sync
        from app.services.ai_document_processor import AIDocumentProcessor

        # Get submitted document
        submitted_doc = SubmittedDocument.query.get(submitted_doc_id)
        if not submitted_doc:
            # For this AJAX endpoint, prefer an application-level error over an HTTP 404
            # so the frontend can display a clean per-document failure without logging a
            # confusing "route not found" network error.
            return json_error(f'Submitted document not found: {submitted_doc_id}', 200, success=False, code='submitted_document_not_found')

        # Check if file exists
        if not (submitted_doc.storage_path or '').strip():
            return json_error('Document has no storage path', 200, success=False, code='missing_storage_path')

        # Build full file path using proper path resolution
        # storage_path is relative to either submissions or admin_documents root.
        from app.utils.file_paths import (
            resolve_submitted_document_file,
            resolve_admin_document,
            normalize_stored_relative_path,
        )
        storage_path = (submitted_doc.storage_path or '').strip()
        file_path = None
        resolve_error = None
        try:
            from app.services import storage_service as _ai_storage
            if os.path.isabs(storage_path):
                file_path = storage_path
            else:
                rel_norm = storage_path.replace("\\", "/").strip()
                cat = _ai_storage.submitted_document_rel_storage_category(rel_norm)
                if cat in (_ai_storage.SUBMISSIONS, _ai_storage.ENTITY_REPO_ROOT):
                    file_path = resolve_submitted_document_file(storage_path)
                else:
                    normalized_rel = normalize_stored_relative_path(storage_path, root_folder='admin_documents')
                    file_path = resolve_admin_document(normalized_rel)
        except Exception as e:
            resolve_error = e
            logger.error(f"Error resolving file path for document {submitted_doc_id}: {e}", exc_info=True)

        if not file_path or not os.path.exists(file_path):
            logger.error(
                "File not found for submitted document: id=%s filename=%s storage_path=%s resolved_path=%s",
                submitted_doc_id,
                submitted_doc.filename,
                storage_path,
                file_path,
            )
            details = f"path: {file_path}" if file_path else "path: unresolved"
            if resolve_error:
                details += f" (resolve error: {resolve_error})"
            return json_error(
                f'File not found: {submitted_doc.filename} ({details})',
                200,
                success=False,
                code='file_not_found',
                filename=submitted_doc.filename,
                storage_path=storage_path,
                resolved_path=file_path,
            )

        # Check if already processed
        existing_ai_doc = AIDocument.query.filter_by(submitted_document_id=submitted_doc_id).first()
        if existing_ai_doc:
            # Reprocess existing in background so frontend can poll status and show stages
            existing_ai_doc.processing_status = 'pending'
            existing_ai_doc.processing_error = None
            db.session.commit()
            from app.routes.ai_documents import _run_import_process_in_thread
            _run_import_process_in_thread(
                current_app._get_current_object(),
                existing_ai_doc.id,
                file_path,
                submitted_doc.filename,
                cleanup_temp=False,
                clear_storage_path=False,
            )
            return json_accepted(
                message='Processing started; poll document status for progress.',
                ai_document_id=existing_ai_doc.id,
                status='processing',
            )

        # Create new AI document
        processor = AIDocumentProcessor()

        # Check if file type is supported
        if not processor.is_supported_file(submitted_doc.filename):
            return json_bad_request(f'Unsupported file type. Supported: {", ".join(processor.SUPPORTED_TYPES.keys())}')

        # Calculate content hash
        content_hash = processor.calculate_content_hash(file_path)

        # Get file type and size
        file_type = processor.get_file_type(submitted_doc.filename)
        file_size = os.path.getsize(file_path)

        # Create AI document record
        derived_country = None
        try:
            derived_country = getattr(submitted_doc, "document_country", None)
        except Exception as e:
            logger.debug("AI doc import: document_country resolution failed for %s: %s", submitted_doc_id, e)
            derived_country = None

        ai_doc = AIDocument(
            submitted_document_id=submitted_doc_id,
            title=submitted_doc.filename,
            filename=submitted_doc.filename,
            file_type=file_type,
            file_size_bytes=file_size,
            storage_path=file_path,
            content_hash=content_hash,
            processing_status='pending',
            user_id=current_user.id,
            is_public=submitted_doc.is_public,
            searchable=True,
            country_id=(int(getattr(derived_country, "id", 0)) or None) if derived_country else None,
            country_name=(getattr(derived_country, "name", None) if derived_country else None),
        )
        db.session.add(ai_doc)
        db.session.commit()
        # Process in background so frontend can poll status and show stages
        from app.routes.ai_documents import _run_import_process_in_thread
        _run_import_process_in_thread(
            current_app._get_current_object(),
            ai_doc.id,
            file_path,
            submitted_doc.filename,
            cleanup_temp=False,
            clear_storage_path=False,
        )
        logger.info(f"Admin {current_user.email} started processing submitted document {submitted_doc_id} -> AI doc {ai_doc.id}")
        return json_accepted(
            message='Processing started; poll document status for progress.',
            ai_document_id=ai_doc.id,
            status='processing',
        )

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/documents/check-ai-status/<int:submitted_doc_id>", methods=["GET"])
@admin_permission_required('admin.ai.manage')
def check_submitted_document_ai_status(submitted_doc_id):
    """Check if a submitted document has been processed by AI."""
    try:
        from app.models import AIDocument

        ai_doc = AIDocument.query.filter_by(submitted_document_id=submitted_doc_id).first()

        if not ai_doc:
            return json_ok(processed=False)

        return json_ok(
            processed=True,
            ai_document_id=ai_doc.id,
            status=ai_doc.processing_status,
            error=ai_doc.processing_error,
            chunks=ai_doc.total_chunks,
            embeddings=getattr(ai_doc, 'total_embeddings', None) or 0,
        )

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/documents/list-system-documents", methods=["GET"])
@admin_permission_required('admin.ai.manage')
def list_system_documents():
    """List submitted documents from the system for import into AI."""
    try:
        from app.models import SubmittedDocument, AIDocument
        from sqlalchemy import or_

        # Get query parameters
        search_query = request.args.get('q', '').strip()
        limit = min(int(request.args.get('limit', 100)), 500)

        # Build query
        query = db.session.query(SubmittedDocument).outerjoin(
            AIDocument,
            AIDocument.submitted_document_id == SubmittedDocument.id
        )

        # Apply search filter
        if search_query:
            safe_pattern = safe_ilike_pattern(search_query)
            query = query.filter(
                or_(
                    SubmittedDocument.filename.ilike(safe_pattern),
                    SubmittedDocument.document_type.ilike(safe_pattern)
                )
            )

        # Order by most recent, not processed first
        query = query.order_by(
            AIDocument.id.is_(None).desc(),  # Unprocessed first
            SubmittedDocument.uploaded_at.desc()
        )

        # Limit results
        documents = query.limit(limit).all()

        # Format response
        result = []
        for doc in documents:
            # Get AI document if exists
            ai_doc = AIDocument.query.filter_by(submitted_document_id=doc.id).first()

            # Get file size if possible (use correct storage root)
            file_size = 0
            if doc.storage_path:
                try:
                    from app.utils.file_paths import (
                        resolve_submitted_document_file,
                        resolve_admin_document,
                        normalize_stored_relative_path,
                    )
                    storage_path = (doc.storage_path or '').strip()
                    file_path = None
                    from app.services import storage_service as _ai_storage
                    if os.path.isabs(storage_path):
                        file_path = storage_path
                    else:
                        rel_norm = storage_path.replace("\\", "/").strip()
                        cat = _ai_storage.submitted_document_rel_storage_category(rel_norm)
                        if cat in (_ai_storage.SUBMISSIONS, _ai_storage.ENTITY_REPO_ROOT):
                            file_path = resolve_submitted_document_file(storage_path)
                        else:
                            normalized_rel = normalize_stored_relative_path(storage_path, root_folder='admin_documents')
                            file_path = resolve_admin_document(normalized_rel)
                    if file_path and os.path.exists(file_path):
                        file_size = os.path.getsize(file_path)
                except Exception as e:
                    current_app.logger.debug("file_size get failed: %s", e)

            result.append({
                'id': doc.id,
                'filename': doc.filename,
                'document_type': doc.document_type,
                'language': doc.language,
                'period': doc.period,
                'is_public': doc.is_public,
                'uploaded_at': doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                'file_size': file_size,
                'ai_processed': ai_doc is not None,
                'ai_document_id': ai_doc.id if ai_doc else None,
                'ai_status': ai_doc.processing_status if ai_doc else None
            })

        return json_ok(documents=result, total=len(result))

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


# ============================================================================
# REASONING TRACES
# ============================================================================

def _get_default_trace_stats():
    """Return default trace stats structure."""
    return {
        'total_traces': 0,
        'recent_traces': 0,
        'total_cost_30d': 0,
        'avg_cost': 0,
        'top_tools': [],
    }


def _is_llm_quality_judge_enabled() -> bool:
    """Return effective LLM quality judge toggle for admin views.

    DB-stored AI settings override runtime config for non-sensitive keys.
    """
    def _to_bool(value, default=False):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "y", "on"}:
                return True
            if lowered in {"0", "false", "no", "n", "off", ""}:
                return False
        return bool(default)

    fallback = _to_bool(current_app.config.get("AI_GROUNDING_LLM_ENABLED", False), False)
    try:
        from app.utils.app_settings import get_ai_settings

        ai_db = get_ai_settings()
        raw = ai_db.get("AI_GROUNDING_LLM_ENABLED")
        if raw is not None and (not isinstance(raw, str) or raw.strip()):
            return _to_bool(raw, fallback)
    except Exception as e:
        logger.debug("Could not resolve DB AI_GROUNDING_LLM_ENABLED: %s", e)
    return fallback


@bp.route("/traces", methods=["GET"])
@admin_permission_required('admin.ai.manage')
def reasoning_traces():
    """View AI agent reasoning traces."""
    if not _check_ai_tables_exist():
        return render_template(
            "admin/ai/reasoning_traces.html",
            traces=[],
            conversations=[],
            pagination=None,
            stats=_get_default_trace_stats(),
            statuses=[],
            current_status='',
            current_user_filter='',
            days_filter=0,
            view_mode='message',
            llm_quality_judge_enabled=_is_llm_quality_judge_enabled(),
            error="AI tables not found. Please run 'flask db upgrade' to create them.",
            title="AI Reasoning Traces"
        )

    try:
        from app.models import AIReasoningTrace, AIToolUsage

        # Get query parameters
        page, per_page = validate_pagination_params(request.args, default_per_page=25, max_per_page=100)
        status_filter = request.args.get('status', '')
        user_filter = request.args.get('user_id', '', type=str)
        days_filter = request.args.get('days', 0, type=int)
        view_mode = request.args.get('view', 'message', type=str)
        if view_mode not in ('message', 'conversation'):
            view_mode = 'message'

        # Build base filters (shared by both views)
        base_filter = db.session.query(AIReasoningTrace)
        if days_filter:
            cutoff = utcnow() - timedelta(days=days_filter)
            base_filter = base_filter.filter(AIReasoningTrace.created_at >= cutoff)
        if status_filter:
            base_filter = base_filter.filter(AIReasoningTrace.status == status_filter)
        if user_filter:
            base_filter = base_filter.filter(AIReasoningTrace.user_id == int(user_filter))

        if view_mode == 'conversation':
            # View by conversation: group by conversation_id (only traces with conversation_id)
            conv_filter = base_filter.filter(AIReasoningTrace.conversation_id.isnot(None))
            conv_subq = conv_filter.with_entities(AIReasoningTrace.id).scalar_subquery()
            grouped = db.session.query(
                AIReasoningTrace.conversation_id,
                func.count(AIReasoningTrace.id).label('trace_count'),
                func.min(AIReasoningTrace.created_at).label('first_at'),
                func.max(AIReasoningTrace.created_at).label('last_at'),
                func.sum(AIReasoningTrace.total_cost_usd).label('total_cost_usd'),
            ).filter(AIReasoningTrace.id.in_(conv_subq)).group_by(
                AIReasoningTrace.conversation_id
            ).order_by(desc(func.max(AIReasoningTrace.created_at)))
            total_conversations = db.session.query(
                func.count(func.distinct(AIReasoningTrace.conversation_id))
            ).filter(AIReasoningTrace.id.in_(conv_subq)).scalar() or 0
            # Paginate manually
            offset = (page - 1) * per_page
            group_rows = grouped.limit(per_page).offset(offset).all()
            conversation_ids = [r[0] for r in group_rows]
            # First-query preview per conversation (first trace by created_at)
            first_queries = {}
            if conversation_ids:
                first_traces = db.session.query(AIReasoningTrace.conversation_id, AIReasoningTrace.query).filter(
                    AIReasoningTrace.conversation_id.in_(conversation_ids)
                ).order_by(AIReasoningTrace.created_at.asc()).all()
                for cid, q in first_traces:
                    if cid not in first_queries:
                        first_queries[cid] = (q or '')[:200]
            conversations = []
            for row in group_rows:
                cid, trace_count, first_at, last_at, total_cost = row
                conversations.append({
                    'conversation_id': cid,
                    'trace_count': trace_count,
                    'first_at': first_at,
                    'last_at': last_at,
                    'total_cost_usd': total_cost,
                    'first_query_preview': first_queries.get(cid, ''),
                })
            def _iter_pages(left_edge=2, right_edge=2, left_current=2, right_current=3):
                total_pages = max(1, (total_conversations + per_page - 1) // per_page) if per_page else 1
                last = 0
                for num in range(1, total_pages + 1):
                    if (
                        num <= left_edge
                        or (num >= page - left_current and num <= page + right_current)
                        or num > total_pages - right_edge
                    ):
                        if last + 1 != num:
                            yield None
                        yield num
                        last = num
                if last != total_pages:
                    yield None

            _pages = max(1, (total_conversations + per_page - 1) // per_page) if per_page else 1
            pagination = type('Pagination', (), {
                'page': page,
                'per_page': per_page,
                'total': total_conversations,
                'pages': _pages,
                'items': conversations,
                'has_prev': page > 1,
                'has_next': page * per_page < total_conversations,
                'prev_num': page - 1 if page > 1 else None,
                'next_num': page + 1 if page < _pages else None,
                'iter_pages': _iter_pages,
            })()
            traces = []
        else:
            # View by message (default): one row per trace
            query = base_filter.options(joinedload(AIReasoningTrace.user)).order_by(
                AIReasoningTrace.created_at.desc()
            )
            pagination = query.paginate(page=page, per_page=per_page, error_out=False)
            traces = pagination.items
            conversations = []

        # Get statistics
        total_traces = db.session.query(AIReasoningTrace).count()
        # Count traces matching current filters (all-time by default when days_filter=0)
        recent_traces = base_filter.count()

        # Cost stats
        cost_stats = db.session.query(
            func.sum(AIReasoningTrace.total_cost_usd),
            func.avg(AIReasoningTrace.total_cost_usd)
        ).filter(
            AIReasoningTrace.created_at >= utcnow() - timedelta(days=30)
        ).first()

        # Tool usage stats
        tool_stats = db.session.query(
            AIToolUsage.tool_name,
            func.count(AIToolUsage.id).label('count')
        ).group_by(AIToolUsage.tool_name).order_by(
            func.count(AIToolUsage.id).desc()
        ).limit(10).all()

        stats = {
            'total_traces': total_traces,
            'recent_traces': recent_traces,
            'total_cost_30d': cost_stats[0] or 0,
            'avg_cost': cost_stats[1] or 0,
            'top_tools': [{'name': t[0], 'count': t[1]} for t in tool_stats],
        }

        # Get status options for filter
        statuses = db.session.query(AIReasoningTrace.status).distinct().all()
        statuses = [s[0] for s in statuses if s[0]]

        return render_template(
            "admin/ai/reasoning_traces.html",
            traces=traces,
            conversations=conversations if view_mode == 'conversation' else [],
            pagination=pagination,
            stats=stats,
            statuses=statuses,
            current_status=status_filter,
            current_user_filter=user_filter,
            days_filter=days_filter,
            view_mode=view_mode,
            llm_quality_judge_enabled=_is_llm_quality_judge_enabled(),
            title="AI Reasoning Traces"
        )

    except Exception as e:
        logger.error(f"Error loading reasoning traces: {e}", exc_info=True)
        return render_template(
            "admin/ai/reasoning_traces.html",
            traces=[],
            conversations=[],
            pagination=None,
            stats=_get_default_trace_stats(),
            statuses=[],
            current_status='',
            current_user_filter='',
            days_filter=0,
            view_mode='message',
            llm_quality_judge_enabled=_is_llm_quality_judge_enabled(),
            error="An error occurred.",
            title="AI Reasoning Traces"
        )


@bp.route("/traces/conversation/<conversation_id>", methods=["GET"])
@admin_permission_required('admin.ai.manage')
def conversation_traces(conversation_id):
    """View all reasoning traces for a conversation (thread view)."""
    if not _check_ai_tables_exist():
        return render_template(
            "admin/ai/reasoning_traces.html",
            traces=[],
            conversations=[],
            pagination=None,
            stats=_get_default_trace_stats(),
            statuses=[],
            current_status='',
            current_user_filter='',
            days_filter=0,
            view_mode='message',
            llm_quality_judge_enabled=_is_llm_quality_judge_enabled(),
            error="AI tables not found. Please run 'flask db upgrade' to create them.",
            title="AI Reasoning Traces"
        )
    try:
        from app.models import AIReasoningTrace, AIToolUsage, User

        traces = (
            db.session.query(AIReasoningTrace)
            .options(joinedload(AIReasoningTrace.user))
            .filter(AIReasoningTrace.conversation_id == conversation_id)
            .order_by(AIReasoningTrace.created_at.asc())
            .all()
        )
        if not traces:
            return render_template(
                "admin/ai/reasoning_traces.html",
                traces=[],
                conversations=[],
                pagination=None,
                stats=_get_default_trace_stats(),
                statuses=[],
                current_status='',
                current_user_filter='',
                days_filter=0,
                view_mode='message',
                llm_quality_judge_enabled=_is_llm_quality_judge_enabled(),
                error=f"No traces found for conversation {conversation_id}.",
                title="AI Reasoning Traces"
            )

        # Tool usages keyed by trace_id for each trace
        trace_ids = [t.id for t in traces]
        tool_usages_by_trace = {}
        for usage in db.session.query(AIToolUsage).filter(
            AIToolUsage.trace_id.in_(trace_ids)
        ).order_by(AIToolUsage.created_at.asc()).all():
            tool_usages_by_trace.setdefault(usage.trace_id, []).append(usage)

        def _display_answer(t):
            return (t.display_answer or t.final_answer or '').strip()

        conversation_summary_data = [
            {
                'id': t.id,
                'created_at': t.created_at.strftime('%Y-%m-%d %H:%M:%S') if t.created_at else '',
                'original_query': t.original_query or '',
                'query': t.query or '',
                'final_answer': (_display_answer(t) or '')[:2000],
                'error_message': t.error_message or '',
                'status': t.status or '',
                'execution_path': t.execution_path or '',
                'llm_model': t.llm_model or '',
                'actual_iterations': t.actual_iterations or 0,
                'execution_time_ms': t.execution_time_ms,
                'total_cost_usd': float(t.total_cost_usd) if t.total_cost_usd is not None else None,
                'grounding_score': float(t.grounding_score) if t.grounding_score is not None else None,
                'confidence_level': t.confidence_level or '',
            }
            for t in traces
        ]

        # Full data including steps for "Copy full" (debug/share)
        conversation_full_data = [
            {
                'id': t.id,
                'created_at': t.created_at.strftime('%Y-%m-%d %H:%M:%S') if t.created_at else '',
                'original_query': t.original_query or '',
                'query': t.query or '',
                'final_answer': _display_answer(t) or t.final_answer or '',
                'error_message': t.error_message or '',
                'status': t.status or '',
                'execution_path': t.execution_path or '',
                'llm_model': t.llm_model or '',
                'actual_iterations': t.actual_iterations or 0,
                'execution_time_ms': t.execution_time_ms,
                'total_cost_usd': float(t.total_cost_usd) if t.total_cost_usd is not None else None,
                'grounding_score': float(t.grounding_score) if t.grounding_score is not None else None,
                'confidence_level': t.confidence_level or '',
                'steps': t.steps if isinstance(t.steps, list) else [],
            }
            for t in traces
        ]

        return render_template(
            "admin/ai/conversation_traces.html",
            conversation_id=conversation_id,
            traces=traces,
            tool_usages_by_trace=tool_usages_by_trace,
            conversation_summary_data=conversation_summary_data,
            conversation_full_data=conversation_full_data,
            title=f"Conversation traces: {conversation_id[:16]}..."
        )
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/traces/bulk-delete", methods=["POST"])
@admin_permission_required('admin.ai.manage')
def traces_bulk_delete():
    """Delete multiple reasoning traces by ID. Requires JSON body: { \"trace_ids\": [1, 2, ...] }."""
    if not _check_ai_tables_exist():
        return json_bad_request("AI tables not found.")
    if not is_json_request():
        return json_bad_request("Content-Type must be application/json.")
    try:
        from app.models import AIReasoningTrace, AIToolUsage, AITraceReview

        payload = get_json_safe(request)
        trace_ids = payload.get("trace_ids")
        if not trace_ids or not isinstance(trace_ids, list):
            return json_bad_request("trace_ids array is required.")
        trace_ids = [int(x) for x in trace_ids if x is not None and str(x).strip() != ""]
        if not trace_ids:
            return json_bad_request("At least one trace ID is required.")

        # Delete related records first (DB may have CASCADE; explicit delete is safe)
        AIToolUsage.query.filter(AIToolUsage.trace_id.in_(trace_ids)).delete(synchronize_session=False)
        AITraceReview.query.filter(AITraceReview.trace_id.in_(trace_ids)).delete(synchronize_session=False)
        deleted = db.session.query(AIReasoningTrace).filter(AIReasoningTrace.id.in_(trace_ids)).delete(
            synchronize_session=False
        )
        db.session.commit()
        logger.info("Admin %s bulk-deleted %d AI reasoning trace(s): %s", current_user.email, deleted, trace_ids)
        return json_ok(deleted=deleted, message=f"Deleted {deleted} trace(s).")
    except (ValueError, TypeError) as e:
        return json_bad_request("Invalid trace_ids.")
    except Exception as e:
        db.session.rollback()
        logger.exception("Bulk delete traces failed: %s", e)
        return json_server_error(GENERIC_ERROR_MESSAGE)


@bp.route("/traces/<int:trace_id>", methods=["GET"])
@admin_permission_required('admin.ai.manage')
def trace_detail(trace_id):
    """View detailed reasoning trace."""
    if not _check_ai_tables_exist():
        return render_template(
            "admin/ai/reasoning_traces.html",
            traces=[],
            pagination=None,
            stats=_get_default_trace_stats(),
            statuses=[],
            current_status='',
            current_user_filter='',
            days_filter=0,
            llm_quality_judge_enabled=_is_llm_quality_judge_enabled(),
            error="AI tables not found. Please run 'flask db upgrade' to create them.",
            title="AI Reasoning Traces"
        )

    try:
        from app.models import AIReasoningTrace, AIToolUsage, User

        trace = db.session.query(AIReasoningTrace).get(trace_id)
        if not trace:
            return render_template(
                "admin/ai/reasoning_traces.html",
                traces=[],
                pagination=None,
                stats=_get_default_trace_stats(),
                statuses=[],
                current_status='',
                current_user_filter='',
                days_filter=0,
                llm_quality_judge_enabled=_is_llm_quality_judge_enabled(),
                error=f"Trace #{trace_id} not found.",
                title="AI Reasoning Traces"
            )

        # Get user info if available
        user = None
        if trace.user_id:
            user = db.session.query(User).get(trace.user_id)

        # Get tool usage for this trace
        tool_usages = db.session.query(AIToolUsage).filter_by(trace_id=trace_id).order_by(
            AIToolUsage.created_at.asc()
        ).all()

        # Build compact quality-debug payload for easier diagnostics in UI.
        quality_debug = {
            "analysis_mode": None,
            "llm_synthesis_used": None,
            "llm_synthesis_debug": None,
            "quality_debug": None,
            "semantic_config": None,
            "semantic_concept_stats": None,
            "excluded_no_target_areas": None,
            "run_elapsed_ms": None,
        }
        try:
            steps = trace.steps if isinstance(trace.steps, list) else []
            for s in reversed(steps):
                if not isinstance(s, dict):
                    continue
                if str(s.get("action") or "").strip().lower() == "finish":
                    obs = s.get("observation")
                    if isinstance(obs, dict):
                        quality_debug["analysis_mode"] = obs.get("analysis_mode")
                        quality_debug["llm_synthesis_debug"] = obs.get("llm_synthesis_debug")
                        if isinstance(obs.get("llm_synthesis_debug"), dict):
                            quality_debug["llm_synthesis_used"] = bool(obs["llm_synthesis_debug"].get("used"))
                    break
        except Exception as e:
            logger.debug("Quality debug extraction failed: %s", e)

        try:
            for usage in tool_usages:
                if str(getattr(usage, "tool_name", "")).strip() != "analyze_unified_plans_focus_areas":
                    continue
                out = getattr(usage, "tool_output", None)
                if not isinstance(out, dict):
                    continue
                result_payload = out.get("result") if isinstance(out.get("result"), dict) else {}
                qd = result_payload.get("quality_debug") if isinstance(result_payload.get("quality_debug"), dict) else None
                if qd:
                    quality_debug["quality_debug"] = qd
                    quality_debug["run_elapsed_ms"] = qd.get("run_elapsed_ms")
                    filters = qd.get("filters") if isinstance(qd.get("filters"), dict) else {}
                    quality_debug["excluded_no_target_areas"] = filters.get("excluded_no_target_areas")
                    sem_dbg = qd.get("semantic_debug") if isinstance(qd.get("semantic_debug"), dict) else {}
                    quality_debug["semantic_config"] = sem_dbg.get("config") if isinstance(sem_dbg.get("config"), dict) else None
                    quality_debug["semantic_concept_stats"] = sem_dbg.get("concept_stats") if isinstance(sem_dbg.get("concept_stats"), dict) else None
                    break
        except Exception as e:
            logger.debug("Semantic concept stats extraction failed: %s", e)

        has_quality_debug = any(v is not None for v in quality_debug.values())

        return render_template(
            "admin/ai/trace_detail.html",
            trace=trace,
            user=user,
            tool_usages=tool_usages,
            quality_debug=quality_debug if has_quality_debug else None,
            title=f"Trace #{trace_id}"
        )

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


# ============================================================================
# AI DASHBOARD / OVERVIEW
# ============================================================================

def _get_default_stats():
    """Return default stats structure for when tables don't exist or errors occur."""
    return {
        'documents': {
            'total': 0,
            'completed': 0,
            'pending': 0,
            'failed': 0,
        },
        'embeddings': 0,
        'traces': {
            'total': 0,
            'last_30_days': 0,
            'completed': 0,
            'errors': 0,
            'flagged_for_review': 0,
            'judged': 0,
        },
        'reviews': {
            'total': 0,
            'pending': 0,
            'in_review': 0,
            'completed': 0,
            'dismissed': 0,
        },
        'total_cost_30d': 0,
        'top_tools': [],
        'agent_enabled': current_app.config.get('AI_AGENT_ENABLED', True),
        'openai_configured': bool(current_app.config.get('OPENAI_API_KEY')),
        'llm_quality_judge_enabled': _is_llm_quality_judge_enabled(),
    }


@bp.route("/analytics", methods=["GET"])
@admin_permission_required('admin.ai.manage')
def ai_chat_analytics():
    """Get AI/chatbot analytics and telemetry data (admin only). JSON API.
    Optional query params: days (7|30|90), breakdown_by_path (bool).
    """
    try:
        from app.services.chatbot_telemetry import get_chatbot_analytics
        analytics = get_chatbot_analytics()

        # Enhance with quality metrics
        days = request.args.get("days", 30, type=int)
        if days not in (7, 30, 90):
            days = 30
        cutoff = utcnow() - timedelta(days=days)

        # Failure rate trend (daily error count vs total, last N days)
        try:
            from sqlalchemy import func as _func, case as _case
            daily_stats = (
                db.session.query(
                    _func.date(AIReasoningTrace.created_at).label("day"),
                    _func.count(AIReasoningTrace.id).label("total"),
                    _func.sum(
                        _case((AIReasoningTrace.status.in_(["error", "llm_error"]), 1), else_=0)
                    ).label("errors"),
                    _func.avg(AIReasoningTrace.grounding_score).label("avg_grounding"),
                    _func.avg(AIReasoningTrace.total_cost_usd).label("avg_cost"),
                )
                .filter(AIReasoningTrace.created_at >= cutoff)
                .group_by(_func.date(AIReasoningTrace.created_at))
                .order_by(_func.date(AIReasoningTrace.created_at).asc())
                .all()
            )
            analytics["daily_stats"] = [
                {
                    "day": str(row.day),
                    "total": row.total,
                    "errors": int(row.errors or 0),
                    "failure_rate": round((row.errors or 0) / max(row.total, 1), 3),
                    "avg_grounding": round(float(row.avg_grounding), 3) if row.avg_grounding else None,
                    "avg_cost": round(float(row.avg_cost or 0), 6),
                }
                for row in daily_stats
            ]
        except Exception as _e:
            logger.debug("daily_stats analytics failed: %s", _e)
            analytics["daily_stats"] = []

        # Quality distribution
        try:
            quality_dist = {
                "high": db.session.query(AIReasoningTrace).filter(
                    AIReasoningTrace.confidence_level == "high",
                    AIReasoningTrace.created_at >= cutoff,
                ).count(),
                "medium": db.session.query(AIReasoningTrace).filter(
                    AIReasoningTrace.confidence_level == "medium",
                    AIReasoningTrace.created_at >= cutoff,
                ).count(),
                "low": db.session.query(AIReasoningTrace).filter(
                    AIReasoningTrace.confidence_level == "low",
                    AIReasoningTrace.created_at >= cutoff,
                ).count(),
            }
            analytics["quality_distribution"] = quality_dist
        except Exception as _e:
            logger.debug("quality_dist analytics failed: %s", _e)

        # Execution path breakdown
        try:
            path_rows = (
                db.session.query(
                    AIReasoningTrace.execution_path,
                    func.count(AIReasoningTrace.id).label("count"),
                )
                .filter(AIReasoningTrace.created_at >= cutoff)
                .group_by(AIReasoningTrace.execution_path)
                .all()
            )
            analytics["execution_path_breakdown"] = {
                (row.execution_path or "unknown"): row.count for row in path_rows
            }
        except Exception as _e:
            logger.debug("path_breakdown analytics failed: %s", _e)

        # Top failing queries (by error count)
        try:
            failing = (
                db.session.query(AIReasoningTrace.query)
                .filter(
                    AIReasoningTrace.status.in_(["error", "llm_error"]),
                    AIReasoningTrace.created_at >= cutoff,
                )
                .order_by(AIReasoningTrace.created_at.desc())
                .limit(10)
                .all()
            )
            analytics["top_failing_queries"] = [r.query[:120] for r in failing]
        except Exception as _e:
            logger.debug("failing_queries analytics failed: %s", _e)

        analytics["days"] = days
        return json_ok(analytics=analytics)
    except Exception as e:
        return handle_json_view_exception(e, 'Failed to retrieve analytics', status_code=500)


@bp.route("/", methods=["GET"])
@admin_permission_required('admin.ai.manage')
def ai_dashboard():
    """AI System Overview Dashboard."""
    if not _check_ai_tables_exist():
        return render_template(
            "admin/ai/dashboard.html",
            stats=_get_default_stats(),
            recent_docs=[],
            recent_traces=[],
            error="AI tables not found. Please run 'flask db upgrade' to create them.",
            title="AI System Dashboard"
        )

    try:
        from app.models import AIDocument, AIReasoningTrace, AIToolUsage, AIEmbedding, AITraceReview

        # Document stats
        doc_stats = {
            'total': db.session.query(AIDocument).count(),
            'completed': db.session.query(AIDocument).filter_by(processing_status='completed').count(),
            'pending': db.session.query(AIDocument).filter_by(processing_status='pending').count(),
            'failed': db.session.query(AIDocument).filter_by(processing_status='failed').count(),
        }

        # Embedding stats
        embedding_count = db.session.query(AIEmbedding).count()

        # Trace stats (last 30 days)
        thirty_days_ago = utcnow() - timedelta(days=30)
        success_statuses = ['completed', 'completed_without_tools', 'agent_disabled']
        error_statuses = ['error', 'llm_error']
        trace_stats = {
            'total': db.session.query(AIReasoningTrace).count(),
            'last_30_days': db.session.query(AIReasoningTrace).filter(
                AIReasoningTrace.created_at >= thirty_days_ago
            ).count(),
            'completed': db.session.query(AIReasoningTrace).filter(
                AIReasoningTrace.status.in_(success_statuses)
            ).count(),
            'errors': db.session.query(AIReasoningTrace).filter(
                AIReasoningTrace.status.in_(error_statuses)
            ).count(),
            'flagged_for_review': db.session.query(AIReasoningTrace).filter(
                AIReasoningTrace.llm_needs_review.is_(True)
            ).count(),
            'judged': db.session.query(AIReasoningTrace).filter(
                AIReasoningTrace.llm_quality_score.isnot(None)
            ).count(),
        }

        review_stats = {
            'total': db.session.query(AITraceReview).count(),
            'pending': db.session.query(AITraceReview).filter_by(status='pending').count(),
            'in_review': db.session.query(AITraceReview).filter_by(status='in_review').count(),
            'completed': db.session.query(AITraceReview).filter_by(status='completed').count(),
            'dismissed': db.session.query(AITraceReview).filter_by(status='dismissed').count(),
        }

        # Cost stats
        cost_result = db.session.query(
            func.sum(AIReasoningTrace.total_cost_usd)
        ).filter(
            AIReasoningTrace.created_at >= thirty_days_ago
        ).scalar()
        total_cost_30d = cost_result or 0

        # Tool usage (top 5)
        top_tools = db.session.query(
            AIToolUsage.tool_name,
            func.count(AIToolUsage.id).label('count')
        ).group_by(AIToolUsage.tool_name).order_by(
            func.count(AIToolUsage.id).desc()
        ).limit(5).all()

        # Recent documents
        recent_docs = db.session.query(AIDocument).order_by(
            AIDocument.created_at.desc()
        ).limit(5).all()

        # Recent traces
        recent_traces = db.session.query(AIReasoningTrace).order_by(
            AIReasoningTrace.created_at.desc()
        ).limit(5).all()

        # Agent enabled status
        agent_enabled = current_app.config.get('AI_AGENT_ENABLED', True)
        openai_configured = bool(current_app.config.get('OPENAI_API_KEY'))
        llm_quality_judge_enabled = _is_llm_quality_judge_enabled()

        stats = {
            'documents': doc_stats,
            'embeddings': embedding_count,
            'traces': trace_stats,
            'reviews': review_stats,
            'total_cost_30d': total_cost_30d,
            'top_tools': [{'name': t[0], 'count': t[1]} for t in top_tools],
            'agent_enabled': agent_enabled,
            'openai_configured': openai_configured,
            'llm_quality_judge_enabled': llm_quality_judge_enabled,
        }

        return render_template(
            "admin/ai/dashboard.html",
            stats=stats,
            recent_docs=recent_docs,
            recent_traces=recent_traces,
            title="AI System Dashboard"
        )

    except Exception as e:
        logger.error(f"Error loading AI dashboard: {e}", exc_info=True)
        return render_template(
            "admin/ai/dashboard.html",
            stats=_get_default_stats(),
            recent_docs=[],
            recent_traces=[],
            error="An error occurred.",
            title="AI System Dashboard"
        )


# ---------------------------------------------------------------------------
# Trace Comparison (Phase 3D)
# ---------------------------------------------------------------------------

@bp.route("/traces/compare")
@admin_permission_required('admin.ai.manage')
def trace_compare():
    """Side-by-side comparison of two reasoning traces. ?left=<id>&right=<id>."""
    try:
        left_id = request.args.get("left", type=int)
        right_id = request.args.get("right", type=int)

        if not left_id or not right_id:
            return render_template(
                "admin/ai/trace_compare.html",
                left=None, right=None,
                error="Provide ?left=<trace_id>&right=<trace_id>",
                title="Compare Traces",
            )

        left = AIReasoningTrace.query.get(left_id)
        right = AIReasoningTrace.query.get(right_id)
        missing = []
        if not left:
            missing.append(str(left_id))
        if not right:
            missing.append(str(right_id))
        if missing:
            return render_template(
                "admin/ai/trace_compare.html",
                left=None, right=None,
                error=f"Trace(s) not found: {', '.join(missing)}",
                title="Compare Traces",
            )

        return render_template(
            "admin/ai/trace_compare.html",
            left=left, right=right,
            title=f"Compare Traces #{left_id} vs #{right_id}",
        )
    except Exception as e:
        logger.error("Trace compare failed: %s", e, exc_info=True)
        return render_template(
            "admin/ai/trace_compare.html",
            left=None, right=None,
            error="An error occurred.",
            title="Compare Traces",
        )


# ---------------------------------------------------------------------------
# Review Queue (Phase 3B)
# ---------------------------------------------------------------------------

@bp.route("/reviews")
@admin_permission_required('admin.ai.manage')
def ai_review_queue():
    """Expert review queue for AI reasoning traces with low grounding or dislike rating."""
    from app.models.embeddings import AITraceReview
    try:
        status_filter = request.args.get('status', 'pending')
        page = int(request.args.get('page', 1))
        per_page = 25

        query = (
            db.session.query(AITraceReview)
            .join(AITraceReview.trace)
            .order_by(AITraceReview.created_at.desc())
        )
        if status_filter and status_filter != 'all':
            query = query.filter(AITraceReview.status == status_filter)

        total = query.count()
        reviews = query.offset((page - 1) * per_page).limit(per_page).all()

        return render_template(
            "admin/ai/review_queue.html",
            reviews=reviews,
            total=total,
            page=page,
            per_page=per_page,
            status_filter=status_filter,
            title="AI Review Queue",
        )
    except Exception as e:
        logger.error("Error loading AI review queue: %s", e, exc_info=True)
        return render_template(
            "admin/ai/review_queue.html",
            reviews=[],
            total=0,
            page=1,
            per_page=25,
            status_filter='pending',
            error="An error occurred.",
            title="AI Review Queue",
        )


@bp.route("/reviews/<int:review_id>", methods=["GET", "POST"])
@admin_permission_required('admin.ai.manage')
def ai_review_detail(review_id):
    """View and annotate a single trace review."""
    from app.models.embeddings import AITraceReview
    from app.utils.datetime_helpers import utcnow

    review = AITraceReview.query.get_or_404(review_id)

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        status = data.get("status") or "completed"
        allowed_verdicts = ("correct", "partially_correct", "incorrect", "needs_improvement", "")

        if status not in ("completed", "dismissed", "pending", "in_review"):
            from app.utils.api_responses import json_bad_request
            return json_bad_request("Invalid status")

        # Dismiss should not implicitly rewrite annotation fields.
        if status != "dismissed":
            verdict = data.get("verdict") or ""
            notes = data.get("reviewer_notes") or ""
            ground_truth = data.get("ground_truth_answer") or ""

            if verdict not in allowed_verdicts:
                from app.utils.api_responses import json_bad_request
                return json_bad_request("Invalid verdict")

            review.verdict = verdict or None
            review.reviewer_notes = notes or None
            review.ground_truth_answer = ground_truth or None

        review.status = status
        review.reviewer_id = current_user.id
        if status == "completed" and not review.completed_at:
            review.completed_at = utcnow()
        db.session.commit()
        from app.utils.api_responses import json_ok
        return json_ok(message="Review saved")

    return render_template(
        "admin/ai/review_detail.html",
        review=review,
        trace=review.trace,
        title="Review Trace",
    )


@bp.route("/reviews/auto-queue", methods=["POST"])
@admin_permission_required('admin.ai.manage')
@limiter.limit("5 per minute")
def ai_review_auto_queue():
    """Auto-queue traces with low grounding score or dislike rating that don't have a review yet."""
    from app.models.embeddings import AITraceReview
    from app.utils.api_responses import json_ok, json_server_error

    try:
        threshold = float(request.get_json(silent=True, force=True).get("threshold", 0.5) if request.data else 0.5)

        subq = db.select(AITraceReview.trace_id)
        candidates = (
            db.session.query(AIReasoningTrace)
            .filter(
                db.or_(
                    db.and_(
                        AIReasoningTrace.grounding_score.isnot(None),
                        AIReasoningTrace.grounding_score < threshold,
                    ),
                    AIReasoningTrace.user_rating == "dislike",
                )
            )
            .filter(AIReasoningTrace.id.notin_(subq))
            .limit(200)
            .all()
        )

        count = 0
        for trace in candidates:
            review = AITraceReview(trace_id=trace.id, status="pending")
            db.session.add(review)
            count += 1

        db.session.commit()
        return json_ok(queued=count, threshold=threshold)
    except Exception as e:
        logger.error("Auto-queue failed: %s", e, exc_info=True)
        with suppress(Exception):
            db.session.rollback()
        return json_server_error("Auto-queue failed")
