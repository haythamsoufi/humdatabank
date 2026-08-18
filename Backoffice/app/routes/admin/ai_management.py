"""
AI Management Routes

Admin interface for managing AI documents, viewing reasoning traces,
and monitoring AI system usage.
"""

import os
import logging
import uuid
import zipfile
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, current_app, send_file, after_this_request, redirect, abort
from flask_login import current_user
from werkzeug.utils import secure_filename
from sqlalchemy import func, desc, and_
from sqlalchemy.orm import joinedload, selectinload

from app.extensions import db, limiter
from app.routes.admin.shared import admin_permission_required
from app.utils.datetime_helpers import utcnow, ensure_utc
from app.utils.sql_utils import safe_ilike_pattern
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.request_utils import is_json_request, parse_ids_from_request
from app.utils.api_pagination import validate_pagination_params
from app.utils.api_responses import json_accepted, json_bad_request, json_error, json_forbidden, json_not_found, json_ok, json_server_error
from app.utils.error_handling import handle_json_view_exception
from app.services.platform import storage_service as _storage
from app.services.ai.ai_job_runner import (
    ensure_ai_job_running,
    get_active_ai_document_jobs_for_user,
    job_cancel_requested,
    run_ai_job,
    signal_job_cancel,
    start_ai_job_thread,
)

logger = logging.getLogger(__name__)

bp = Blueprint("ai_management", __name__, url_prefix="/admin/ai")


def _job_item_ai_document_id(item) -> int | None:
    """Resolve linked AIDocument id from a job item (entity or payload)."""
    if item.entity_type == "ai_document" and item.entity_id:
        try:
            return int(item.entity_id)
        except (TypeError, ValueError):
            pass
    payload = item.payload if isinstance(item.payload, dict) else {}
    raw = payload.get("ai_document_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _resolve_ai_doc_file_for_processing(doc):
    """
    Return (file_path, temp_path, filename, from_url) for an AIDocument.

    *temp_path* is set when the caller must delete a downloaded temp file afterward.
    """
    from app.services.ai.documents.ingest import (
        apply_resolved_source_metadata_to_ai_doc,
        resolve_ai_document_source_for_processing,
    )

    resolved = resolve_ai_document_source_for_processing(doc)
    if not resolved.get("ok"):
        raise FileNotFoundError(resolved.get("message") or "Source file not found")
    apply_resolved_source_metadata_to_ai_doc(doc, resolved)
    db.session.commit()
    file_path = resolved["file_path"]
    temp_path = file_path if resolved.get("cleanup_temp") else None
    filename = resolved.get("filename") or doc.filename or "document"
    return file_path, temp_path, filename, bool(resolved.get("from_url"))


def _get_text_from_chunks(doc_id: int) -> str:
    """
    Reassemble document text from stored chunks ordered by chunk_index.

    Used as a fallback for metadata enrichment when the original source file
    is no longer available on disk and there is no downloadable source_url.
    """
    from app.models import AIDocumentChunk
    chunks = (
        AIDocumentChunk.query
        .filter_by(document_id=doc_id)
        .order_by(AIDocumentChunk.chunk_index)
        .all()
    )
    return "\n".join(c.content for c in chunks if c.content)


def _process_reprocess_job_item_sync(app, *, job_id: str, item_id: int) -> None:
    """Process one bulk reprocess job item (download if needed, clear chunks, re-chunk + re-embed)."""
    with app.app_context():
        from app.models import (
            AIDocument,
            AIDocumentChunk,
            AIEmbedding,
            AIJobItem,
        )
        from app.routes.ai_documents.upload import _process_document_sync

        cancel_requested = job_cancel_requested(job_id)
        item = AIJobItem.query.get(int(item_id))
        if not item:
            return

        if cancel_requested:
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
        from_url = False

        try:
            item.status = "processing"
            item.error = None
            db.session.commit()

            # Set pending immediately so status polls show "in progress"
            doc.processing_status = "pending"
            doc.processing_error = None
            db.session.commit()

            file_path, temp_path, filename, from_url = _resolve_ai_doc_file_for_processing(doc)

            if job_cancel_requested(job_id):
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
                if job_cancel_requested(job_id):
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
            # Clear storage_path for URL-backed docs (keep reference-only behavior)
            try:
                if doc and from_url:
                    doc = AIDocument.query.get(int(doc.id))
                    if doc:
                        doc.storage_path = None
                        db.session.commit()
            except Exception as e:
                current_app.logger.debug("AI storage_path clear failed: %s", e)
                db.session.rollback()


def _run_bulk_reprocess_job(app, job_id: str) -> None:
    """Background runner for bulk reprocess jobs."""
    run_ai_job(
        app,
        job_id,
        _process_reprocess_job_item_sync,
        concurrency_config_keys=("AI_DOCS_REPROCESS_CONCURRENCY",),
        default_concurrency=1,
    )


def _process_system_import_job_item_sync(app, *, job_id: str, item_id: int) -> None:
    """Process one system-document bulk import job item synchronously."""
    with app.app_context():
        from app.models import AIJobItem
        from app.routes.ai_documents.upload import _process_document_sync
        from app.services.ai.documents.ingest import _prepare_submitted_document_ai_import

        item = AIJobItem.query.get(int(item_id))
        if not item:
            return

        if job_cancel_requested(job_id):
            item.status = "cancelled"
            item.error = None
            db.session.commit()
            return

        payload = item.payload if isinstance(item.payload, dict) else {}
        submitted_doc_id = payload.get("submitted_document_id")
        if submitted_doc_id is None and item.entity_type == "submitted_document" and item.entity_id:
            submitted_doc_id = int(item.entity_id)
        try:
            submitted_doc_id = int(submitted_doc_id)
        except (TypeError, ValueError):
            item.status = "failed"
            item.error = "Invalid submitted document ID"
            db.session.commit()
            return

        job = None
        try:
            from app.models import AIJob

            job = AIJob.query.get(str(job_id))
        except Exception as e:
            current_app.logger.debug("System import job lookup failed: %s", e)

        job_user_id = int(job.user_id) if job and job.user_id else None

        item.status = "processing"
        item.error = None
        db.session.commit()

        prep = _prepare_submitted_document_ai_import(submitted_doc_id, user_id=job_user_id)
        if not prep.get("ok"):
            item.status = "failed"
            item.error = prep.get("message") or prep.get("code") or "Processing failed"
            db.session.commit()
            return

        ai_doc_id = int(prep["ai_document_id"])
        file_path = prep["file_path"]
        filename = prep["filename"]
        cleanup_temp = bool(prep.get("cleanup_temp"))

        item.entity_type = "ai_document"
        item.entity_id = ai_doc_id
        try:
            base_payload = item.payload if isinstance(item.payload, dict) else {}
            new_payload = dict(base_payload)
            new_payload["ai_document_id"] = ai_doc_id
            item.payload = new_payload
        except Exception as e:
            current_app.logger.debug("System import item payload update failed: %s", e)
        item.status = "processing"
        item.error = None
        db.session.commit()
        db.session.remove()

        try:
            if job_cancel_requested(job_id):
                item = AIJobItem.query.get(int(item_id))
                if item:
                    item.status = "cancelled"
                    item.error = None
                    db.session.commit()
                return

            _process_document_sync(ai_doc_id, file_path, filename)

            from app.models import AIDocument

            doc = AIDocument.query.get(ai_doc_id)
            item = AIJobItem.query.get(int(item_id))
            if not item:
                return

            if job_cancel_requested(job_id):
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
            logger.error(
                "Bulk system import item failed: job=%s item=%s err=%s",
                job_id,
                item_id,
                e,
                exc_info=True,
            )
            try:
                from app.models import AIDocument

                doc = AIDocument.query.get(ai_doc_id)
                if doc:
                    doc.processing_status = "failed"
                    doc.processing_error = "Processing failed."
                item = AIJobItem.query.get(int(item_id))
                if item:
                    item.status = "failed"
                    item.error = "Processing failed."
                    db.session.commit()
            except Exception as update_e:
                current_app.logger.debug("System import item failure update failed: %s", update_e)
                db.session.rollback()
        finally:
            if cleanup_temp and file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass


def _run_system_bulk_import_job(app, job_id: str) -> None:
    """Background runner for system-document bulk import jobs."""
    run_ai_job(
        app,
        job_id,
        _process_system_import_job_item_sync,
        concurrency_config_keys=(
            "AI_DOCS_SYSTEM_IMPORT_CONCURRENCY",
            "AI_DOCS_IFRC_IMPORT_CONCURRENCY",
        ),
        default_concurrency=2,
        stagger_seconds=0.5,
    )


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
            from app.routes.ai_documents.upload import get_document_processing_stage

            candidate_ids = [doc_id for doc_id in candidate_ids if not get_document_processing_stage(int(doc_id))]
        except Exception as e:
            current_app.logger.debug("Document processing stage filter failed: %s", e)
        if not candidate_ids:
            return 0

        # Keep docs with a recent cross-worker heartbeat.
        try:
            heartbeat_cutoff = utcnow() - timedelta(seconds=timeout_seconds)
            fresh_ids = {
                int(r[0])
                for r in (
                    db.session.query(AIDocument.id)
                    .filter(AIDocument.id.in_(candidate_ids))
                    .filter(AIDocument.processing_heartbeat_at.isnot(None))
                    .filter(AIDocument.processing_heartbeat_at > heartbeat_cutoff)
                    .all()
                )
                if r and r[0] is not None
            }
            if fresh_ids:
                candidate_ids = [doc_id for doc_id in candidate_ids if int(doc_id) not in fresh_ids]
        except Exception as e:
            current_app.logger.debug("Processing heartbeat filter failed: %s", e)
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


@bp.route("/documents/active-jobs", methods=["GET"])
@admin_permission_required('admin.ai.manage')
def ai_documents_active_jobs():
    """Return in-flight AI document batch jobs for the current user (UI resume)."""
    try:
        if not _check_ai_reprocess_job_tables_exist():
            return json_ok(success=True, jobs=[])
        user_id = int(getattr(current_user, "id", 0) or 0)
        jobs = get_active_ai_document_jobs_for_user(user_id)
        return json_ok(success=True, jobs=jobs)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/documents", methods=["GET"])
@admin_permission_required('admin.ai.manage')
def document_library():
    """AI Document Library - manage documents for RAG system."""
    if not _check_ai_tables_exist():
        return render_template(
            "admin/ai/documents.html",
            processing_doc_ids=[],
            active_jobs=[],
            stats=_get_default_doc_stats(),
            file_types=[],
            categories=[],
            languages=[],
            current_status='',
            current_file_type='',
            current_category='',
            current_language='',
            search_query='',
            has_active_filters=False,
            stats_global=None,
            error="AI tables not found. Please run 'flask db upgrade' to create them.",
            title="AI Knowledge Base"
        )

    try:
        from app.models import AIDocument, AIDocumentChunk, AIEmbedding
        from app.routes.ai_documents.helpers import (
            parse_ai_document_library_filters,
            apply_ai_document_library_filters,
            ai_document_library_filters_active,
            compute_ai_document_status_stats,
        )

        # Self-heal stale "processing" rows before rendering the page.
        _auto_recover_stale_processing_documents()

        filters = parse_ai_document_library_filters(request.args)
        has_active_filters = ai_document_library_filters_active(filters)

        filtered_count = (
            apply_ai_document_library_filters(db.session.query(AIDocument), filters).count()
            if has_active_filters else None
        )
        logger.info(
            "AI document library page: user_id=%s filtered_total=%s filters(status=%s file_type=%s category=%s language=%s q=%s)",
            getattr(current_user, "id", None),
            filtered_count if filtered_count is not None else "all",
            filters.get("status") or "",
            filters.get("file_type") or "",
            filters.get("category") or "",
            filters.get("language") or "",
            filters.get("q") or "",
        )

        processing_doc_ids = [
            int(r[0]) for r in (
                db.session.query(AIDocument.id)
                .filter(AIDocument.processing_status.in_(("processing", "pending")))
                .all()
            )
            if r and r[0] is not None
        ]

        active_jobs = []
        if _check_ai_reprocess_job_tables_exist():
            user_id = int(getattr(current_user, "id", 0) or 0)
            active_jobs = get_active_ai_document_jobs_for_user(user_id)
            worker_app = current_app._get_current_object()
            for active in active_jobs:
                job_type = active.get("job_type")
                jid = active.get("job_id")
                if not jid:
                    continue
                if job_type == "docs.bulk_import_system":
                    ensure_ai_job_running(worker_app, jid, _run_system_bulk_import_job)
                elif job_type == "docs.bulk_reprocess":
                    ensure_ai_job_running(worker_app, jid, _run_bulk_reprocess_job)
                elif job_type == "docs.bulk_reprocess_metadata":
                    ensure_ai_job_running(worker_app, jid, _run_bulk_metadata_reprocess_job)
                elif job_type == "ifrc_api_bulk":
                    from app.routes.ai_documents.ifrc import _run_ifrc_bulk_import_job

                    ensure_ai_job_running(worker_app, jid, _run_ifrc_bulk_import_job)

        # Global stats (always unfiltered) + filtered counts when URL filters are active.
        global_stats = {
            'total_documents': db.session.query(AIDocument).count(),
            'completed': db.session.query(AIDocument).filter_by(processing_status='completed').count(),
            'pending': db.session.query(AIDocument).filter_by(processing_status='pending').count(),
            'processing': db.session.query(AIDocument).filter_by(processing_status='processing').count(),
            'failed': db.session.query(AIDocument).filter_by(processing_status='failed').count(),
            'total_chunks': db.session.query(AIDocumentChunk).count(),
            'total_embeddings': db.session.query(AIEmbedding).count(),
        }
        if has_active_filters:
            filtered_counts = compute_ai_document_status_stats(
                apply_ai_document_library_filters(db.session.query(AIDocument), filters)
            )
            stats = {
                **filtered_counts,
                'total_chunks': global_stats['total_chunks'],
                'total_embeddings': global_stats['total_embeddings'],
            }
        else:
            stats = global_stats

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
            processing_doc_ids=processing_doc_ids,
            active_jobs=active_jobs,
            stats=stats,
            file_types=file_types,
            categories=categories,
            languages=languages,
            current_status=filters.get('status', ''),
            current_file_type=filters.get('file_type', ''),
            current_category=filters.get('category', ''),
            current_language=filters.get('language', ''),
            search_query=filters.get('q', ''),
            has_active_filters=has_active_filters,
            stats_global=global_stats,
            title="AI Knowledge Base",
        )

    except Exception as e:
        logger.error(f"Error loading document library: {e}", exc_info=True)
        db.session.rollback()
        return render_template(
            "admin/ai/documents.html",
            processing_doc_ids=[],
            active_jobs=[],
            stats=_get_default_doc_stats(),
            file_types=[],
            categories=[],
            languages=[],
            current_status='',
            current_file_type='',
            current_category='',
            current_language='',
            search_query='',
            has_active_filters=False,
            stats_global=None,
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
                from app.routes.ai_documents.helpers import _ai_doc_storage_delete
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
        from app.models import AIDocument
        from app.routes.ai_documents.upload import start_single_document_processing

        doc = AIDocument.query.get_or_404(document_id)
        doc.processing_status = 'pending'
        doc.processing_error = None
        db.session.commit()

        admin_email = current_user.email

        def resolve_file():
            # Deferred onto the background thread: resolving the source (which may
            # download a source_url over the network) can be slow and must not block
            # this request's 202 response.
            fresh_doc = AIDocument.query.get(int(document_id))
            if not fresh_doc:
                raise FileNotFoundError("Document not found")
            return _resolve_ai_doc_file_for_processing(fresh_doc)

        start_single_document_processing(
            current_app._get_current_object(),
            document_id,
            resolve_file=resolve_file,
            pre_clear_chunks=True,
        )

        logger.info(f"Admin {admin_email} started reprocess for AI document {document_id}")
        return json_accepted(
            document_id=document_id,
            status='processing',
            message='Reprocess started; poll document status for progress.',
        )

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/documents/<int:document_id>/redetect-country", methods=["POST"])
@admin_permission_required('admin.ai.manage')
@limiter.limit("30 per minute")
def redetect_country_document(document_id):
    """Re-run country detection for a document (extract first page/content, then detect country). No re-chunk or re-embed."""
    try:
        from app.models import AIDocument, Country
        from app.routes.ai_documents.upload import _apply_country_detection_to_doc
        from app.services.ai.documents.processor import AIDocumentProcessor

        doc = AIDocument.query.get_or_404(document_id)

        temp_path = None
        file_path, temp_path, filename, _from_url = _resolve_ai_doc_file_for_processing(doc)

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

    except FileNotFoundError as e:
        return json_not_found(str(e))
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
        from app.models import AIDocument
        from app.services.ai.documents.processor import AIDocumentProcessor
        from app.services.ai.documents.submitted_metadata import (
            apply_enriched_metadata_to_ai_doc,
            enrich_ai_document_metadata_from_content,
        )

        doc = AIDocument.query.get_or_404(document_id)

        effective_source_url = (getattr(doc, "source_url", None) or "").strip() or None
        filename = doc.filename or "document"
        temp_path = None
        text = None
        total_pages = None
        pdf_metadata = None
        has_tables = False

        try:
            file_path, temp_path, filename, _from_url = _resolve_ai_doc_file_for_processing(doc)
            try:
                processor = AIDocumentProcessor()
                extracted = processor.process_document(
                    file_path=file_path,
                    filename=filename,
                    extract_images=False,
                    ocr_enabled=current_app.config.get('AI_OCR_ENABLED', False),
                )
                tables = extracted.get('tables') or []
                text = extracted.get('text', '')
                total_pages = extracted.get('metadata', {}).get('total_pages')
                pdf_metadata = extracted.get('metadata')
                has_tables = len(tables) > 0
            finally:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except OSError as e:
                        logger.warning("Could not remove temp file %s: %s", temp_path, e)
        except FileNotFoundError:
            # Source file gone — fall back to stored chunk text for heuristic enrichment.
            chunk_text = _get_text_from_chunks(document_id)
            if not chunk_text:
                return json_not_found(
                    "Source file not found and no stored chunk text available for this document."
                )
            logger.info(
                "reprocess_document_metadata: source file unavailable for doc %s, "
                "falling back to %d chars of stored chunk text",
                document_id, len(chunk_text),
            )
            text = chunk_text

        enriched_meta = enrich_ai_document_metadata_from_content(
            doc,
            filename=filename,
            text=text,
            total_pages=total_pages,
            pdf_metadata=pdf_metadata,
            has_tables=has_tables,
            table_extraction_success=has_tables,
            source_url=effective_source_url,
        )
        apply_enriched_metadata_to_ai_doc(doc, enriched_meta)
        db.session.commit()
        return json_ok(
            message='Metadata reprocessed successfully',
            document_date=doc.document_date.isoformat() if doc.document_date else None,
            document_language=doc.document_language,
            document_category=doc.document_category,
            quality_score=doc.quality_score,
            source_organization=doc.source_organization,
        )

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/documents/mine-terminology", methods=["POST"])
@admin_permission_required('admin.ai.manage')
@limiter.limit("10 per minute")
def mine_document_terminology():
    """Mine glossary candidates from selected Knowledge Base documents."""
    from app.services.translation.glossary_mining import mine_selected_documents
    from app.utils.request_utils import parse_ids_from_request

    try:
        ids = parse_ids_from_request("ids")
    except Exception:
        ids = []
        if is_json_request():
            payload = get_json_safe() or {}
            raw = payload.get("ids") or []
            if isinstance(raw, str):
                ids = [int(x) for x in raw.split(",") if x.strip().isdigit()]
            elif isinstance(raw, list):
                ids = [int(x) for x in raw if str(x).isdigit() or isinstance(x, int)]
    if not ids:
        return json_bad_request("No document IDs provided")
    result = mine_selected_documents(ids)
    message = result.get("message") or "Terminology mining complete"
    if result.get("documents", 0) == 0:
        message = (
            "No completed documents in the selection. Wait until processing finishes, "
            "then mine again."
        )
    elif result.get("candidates", 0) == 0:
        reason = result.get("reason") or ""
        if reason == "same_language":
            message = (
                "No new glossary candidates. Every completed file has the same "
                "detected language. Reprocess metadata if these are different "
                "language versions."
            )
        elif reason == "openai_unavailable":
            message = (
                "No new glossary candidates. LLM pairing needs OPENAI_API_KEY. "
                "Regex acronym join also found no shared (ACRONYM) expansions."
            )
        elif reason == "llm_no_grounded_pairs":
            message = (
                "The model extracted English terms but could not attest a target "
                "wording in retrieved chunks. Nothing was added to the inbox."
            )
        elif reason == "llm_no_source_terms":
            message = (
                "The model did not find glossary-length terms in the English document."
            )
        elif reason == "no_english_source":
            message = (
                "LLM pairing needs an English file in the selection (or mark English "
                "via Reprocess metadata)."
            )
        else:
            message = (
                "No new glossary candidates. Acronym join found no shared expansions, "
                "and LLM pairing did not produce grounded term pairs."
            )
    return json_ok(message=message, **result)


@bp.route("/documents/translation-pair", methods=["POST"])
@admin_permission_required('admin.ai.manage')
def mark_translation_document_pair():
    """Record an opt-in document pair. Sentence-level TM is deferred."""
    from app.models.translation_quality import TranslationDocumentPair
    from app.extensions import db

    payload = get_json_safe() or {}
    try:
        source_id = int(payload.get("source_document_id"))
        target_id = int(payload.get("target_document_id"))
    except (TypeError, ValueError):
        return json_bad_request("source_document_id and target_document_id are required")
    if source_id == target_id:
        return json_bad_request("Pair must be two different documents")
    existing = TranslationDocumentPair.query.filter_by(
        source_document_id=source_id, target_document_id=target_id
    ).first()
    if existing is None:
        db.session.add(
            TranslationDocumentPair(
                source_document_id=source_id,
                target_document_id=target_id,
                source_lang=str(payload.get("source_lang") or "en")[:10],
                target_lang=str(payload.get("target_lang") or "fr")[:10],
                status="deferred",
                note="Sentence-level TM is deferred until glossary mining is proven. Re-segment with LaBSE/Bertalign; do not align 512-token chunks.",
                created_by_user_id=getattr(current_user, "id", None),
            )
        )
        db.session.commit()
    return json_ok(
        deferred=True,
        message="Pair recorded. Sentence-level translation memory is deferred.",
    )


@bp.route("/documents/translation-group", methods=["POST"])
@admin_permission_required('admin.ai.manage')
def mark_translation_document_group():
    """Mark 2+ selected documents as the same publication in different languages."""
    from app.models.embeddings import AIDocument
    from app.models.translation_quality import TranslationDocumentPair
    from app.extensions import db

    payload = get_json_safe() or {}
    raw_ids = payload.get("ids") or []
    try:
        ids = sorted({int(x) for x in raw_ids})
    except (TypeError, ValueError):
        return json_bad_request("ids must be a list of document IDs")
    if len(ids) < 2:
        return json_bad_request("Select at least two documents")

    docs = AIDocument.query.filter(AIDocument.id.in_(ids)).all()
    if len(docs) < 2:
        return json_bad_request("Could not load the selected documents")

    lang_overrides = payload.get("languages") if isinstance(payload.get("languages"), dict) else {}

    def _lang(doc):
        override = lang_overrides.get(str(doc.id)) or lang_overrides.get(doc.id)
        return str(override or doc.document_language or "en").lower()[:10]

    english = [d for d in docs if _lang(d) == "en"]
    hub = english[0] if english else docs[0]
    created = 0
    pairs = []
    for doc in docs:
        if int(doc.id) == int(hub.id):
            continue
        existing = TranslationDocumentPair.query.filter_by(
            source_document_id=int(hub.id),
            target_document_id=int(doc.id),
        ).first()
        if existing is None:
            db.session.add(
                TranslationDocumentPair(
                    source_document_id=int(hub.id),
                    target_document_id=int(doc.id),
                    source_lang=_lang(hub),
                    target_lang=_lang(doc),
                    status="deferred",
                    note="Same publication marked from the Knowledge Base. Sentence-level TM stays deferred.",
                    created_by_user_id=getattr(current_user, "id", None),
                )
            )
            created += 1
        pairs.append({
            "source_document_id": int(hub.id),
            "target_document_id": int(doc.id),
            "source_lang": _lang(hub),
            "target_lang": _lang(doc),
        })
    db.session.commit()
    langs = sorted({_lang(d) for d in docs})
    message = (
        "Marked as the same publication. "
        f"{created} language pair(s) recorded. "
        "Sentence-level translation memory stays deferred; terminology mining can use the group."
    )
    if len(langs) < 2:
        message += (
            " Every file has the same detected language. "
            "Use Reprocess metadata if these are different language versions, then mark again."
        )
    return json_ok(
        created=created,
        pairs=pairs,
        hub_document_id=int(hub.id),
        languages=langs,
        deferred=True,
        message=message,
    )


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

        # Kick off background job runner (survives browser close; orphan-resumable).
        start_ai_job_thread(current_app._get_current_object(), job_id, _run_bulk_reprocess_job)

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

        ensure_ai_job_running(current_app._get_current_object(), job_id, _run_bulk_reprocess_job)

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

        signal_job_cancel(str(job_id))
        return json_ok(status="cancel_requested")
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

def _process_metadata_reprocess_job_item_sync(app, job_id: str, item_id: int) -> None:
    """Run metadata enrichment for a single AIJobItem (metadata-only, no re-chunk/re-embed)."""
    with app.app_context():
        from app.models import AIDocument, AIJobItem
        from app.services.ai.documents.processor import AIDocumentProcessor

        cancel_requested = job_cancel_requested(job_id)
        item = AIJobItem.query.get(int(item_id))
        if not item:
            return

        if cancel_requested:
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
        filename = doc.filename or "document"

        try:
            item.status = "processing"
            item.error = None
            db.session.commit()

            effective_source_url = (getattr(doc, "source_url", None) or "").strip() or None
            text = None
            total_pages = None
            pdf_metadata = None
            has_tables = False

            try:
                file_path, temp_path, filename, _from_url = _resolve_ai_doc_file_for_processing(doc)
                try:
                    processor = AIDocumentProcessor()
                    extracted = processor.process_document(
                        file_path=file_path,
                        filename=filename,
                        extract_images=False,
                        ocr_enabled=current_app.config.get("AI_OCR_ENABLED", False),
                    )
                    tables = extracted.get("tables") or []
                    text = extracted.get("text", "")
                    total_pages = extracted.get("metadata", {}).get("total_pages")
                    pdf_metadata = extracted.get("metadata")
                    has_tables = len(tables) > 0
                finally:
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except OSError:
                            pass
                    temp_path = None
            except FileNotFoundError:
                # Source file gone — fall back to stored chunk text for heuristic enrichment.
                chunk_text = _get_text_from_chunks(doc_id)
                if not chunk_text:
                    raise FileNotFoundError(
                        "Source file not found and no stored chunk text available."
                    )
                logger.info(
                    "_process_metadata_reprocess_job_item_sync: source file unavailable for "
                    "doc %s, falling back to %d chars of stored chunk text",
                    doc_id, len(chunk_text),
                )
                text = chunk_text

            if job_cancel_requested(job_id):
                item = AIJobItem.query.get(int(item_id))
                if item:
                    item.status = "cancelled"
                    db.session.commit()
                return

            item = AIJobItem.query.get(int(item_id))
            if item:
                item.status = "processing"
                db.session.commit()

            from app.services.ai.documents.submitted_metadata import (
                apply_enriched_metadata_to_ai_doc,
                enrich_ai_document_metadata_from_content,
            )
            enriched_meta = enrich_ai_document_metadata_from_content(
                doc,
                filename=filename,
                text=text,
                total_pages=total_pages,
                pdf_metadata=pdf_metadata,
                has_tables=has_tables,
                table_extraction_success=has_tables,
                source_url=effective_source_url,
            )
            doc = AIDocument.query.get(doc_id)
            apply_enriched_metadata_to_ai_doc(doc, enriched_meta)
            db.session.commit()

            item = AIJobItem.query.get(int(item_id))
            if item:
                item.status = "cancelled" if job_cancel_requested(job_id) else "completed"
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
    run_ai_job(
        app,
        job_id,
        _process_metadata_reprocess_job_item_sync,
        concurrency_config_keys=(),
        default_concurrency=2,
    )


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

        start_ai_job_thread(current_app._get_current_object(), job_id, _run_bulk_metadata_reprocess_job)

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

        ensure_ai_job_running(current_app._get_current_object(), job_id, _run_bulk_metadata_reprocess_job)

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
        signal_job_cancel(str(job_id))
        return json_ok(status="cancel_requested")
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/documents/import-system-bulk", methods=["POST"])
@admin_permission_required('admin.ai.manage')
@limiter.limit("10 per minute")
def import_system_bulk():
    """
    Start a server-side bulk import job for selected submitted (system) documents.

    Accepts JSON {submitted_document_ids:[...], concurrency?:int}.
    Returns 202 with job_id to poll via /admin/ai/documents/import-system-bulk/<job_id>/status
    """
    try:
        if not _check_ai_reprocess_job_tables_exist():
            return json_server_error("AI job tables not found. Please run 'flask db upgrade' and try again.")

        from app.models import AIJob, AIJobItem, SubmittedDocument

        ids: list[int] = []
        concurrency = None
        if is_json_request():
            payload = get_json_safe() or {}
            raw_ids = payload.get("submitted_document_ids") or payload.get("ids")
            if isinstance(raw_ids, list):
                for raw in raw_ids:
                    try:
                        ids.append(int(raw))
                    except (TypeError, ValueError):
                        continue
            try:
                concurrency = int(payload.get("concurrency")) if payload.get("concurrency") is not None else None
            except (TypeError, ValueError):
                concurrency = None
        if not ids:
            ids = parse_ids_from_request("submitted_document_ids") or parse_ids_from_request("ids")
        if not ids:
            return json_bad_request("No submitted document IDs provided")
        if len(ids) > 500:
            return json_bad_request("Too many documents selected (max 500)")

        if concurrency is None:
            concurrency = int(
                current_app.config.get("AI_DOCS_SYSTEM_IMPORT_CONCURRENCY")
                or current_app.config.get("AI_DOCS_IFRC_IMPORT_CONCURRENCY", 2)
                or 2
            )
        concurrency = max(1, min(int(concurrency), 4))

        docs = SubmittedDocument.query.filter(SubmittedDocument.id.in_(ids)).all()
        docs_by_id = {int(d.id): d for d in docs}

        job_id = str(uuid.uuid4())
        job = AIJob(
            id=job_id,
            job_type="docs.bulk_import_system",
            user_id=int(current_user.id),
            status="queued",
            total_items=len(ids),
            meta={"concurrency": concurrency},
        )
        db.session.add(job)
        db.session.flush()

        for idx, sid in enumerate(ids):
            doc = docs_by_id.get(int(sid))
            status = "queued"
            err = None
            if not doc:
                status = "failed"
                err = "Submitted document not found"
            elif getattr(doc, "source_url_unreachable", False):
                status = "failed"
                err = "Source URL unreachable"

            it = AIJobItem(
                job_id=job_id,
                item_index=idx,
                entity_type="submitted_document" if doc else None,
                entity_id=int(sid) if doc else None,
                status=status,
                error=err,
                payload={"submitted_document_id": int(sid)},
            )
            db.session.add(it)

        db.session.commit()

        start_ai_job_thread(current_app._get_current_object(), job_id, _run_system_bulk_import_job)

        return json_accepted(
            success=True,
            job_id=job_id,
            total=len(ids),
            concurrency=concurrency,
            message="Bulk system import started",
        )
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/documents/import-system-bulk/<job_id>/status", methods=["GET"])
@admin_permission_required('admin.ai.manage')
def import_system_bulk_status(job_id: str):
    """Return job + item statuses for a bulk system-document import job."""
    try:
        if not _check_ai_reprocess_job_tables_exist():
            return json_not_found("not_found")

        ensure_ai_job_running(current_app._get_current_object(), job_id, _run_system_bulk_import_job)

        from app.models import AIDocument, AIJob

        job = AIJob.query.get(str(job_id))
        if not job:
            return json_not_found("not_found")

        items = job.items or []
        completed = sum(1 for it in items if it.status == "completed")
        failed = sum(1 for it in items if it.status == "failed")
        cancelled = sum(1 for it in items if it.status == "cancelled")
        processing = sum(1 for it in items if it.status in ("downloading", "processing", "queued"))

        doc_ids = []
        for it in items:
            aid = _job_item_ai_document_id(it)
            if aid is not None:
                doc_ids.append(aid)
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
                    "submitted_document_id": (
                        (it.payload or {}).get("submitted_document_id")
                        if isinstance(it.payload, dict)
                        else None
                    ),
                    "ai_document_id": _job_item_ai_document_id(it),
                    "import_status": it.status,
                    "import_error": it.error,
                    "document": (
                        docs_by_id.get(int(_job_item_ai_document_id(it)))
                        if _job_item_ai_document_id(it) is not None
                        else None
                    ),
                }
                for it in items
            ],
        )
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/documents/import-system-bulk/<job_id>/cancel", methods=["POST"])
@admin_permission_required('admin.ai.manage')
def import_system_bulk_cancel(job_id: str):
    """Request cancellation for a running bulk system-document import job (best-effort)."""
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
        except Exception:
            db.session.rollback()
        db.session.commit()
        signal_job_cancel(str(job_id))
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
        from app.routes.ai_documents.helpers import _download_ifrc_document
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
        from app.routes.ai_documents.upload import (
            get_document_processing_stage,
            get_document_processing_stage_from_db,
        )
        current_stage = get_document_processing_stage(document_id)
        if not current_stage:
            current_stage = get_document_processing_stage_from_db(document_id)

        # Stuck detection:
        # If DB says 'processing' but there's no active stage in THIS process, the work may be:
        # - interrupted (server restart), OR
        # - running in another worker/process (stage is in-memory and not shared).
        #
        # Use whichever timestamp is most recent (not just the first non-null one) —
        # processing_heartbeat_at is never cleared between runs, so a document reprocessed
        # after finishing hours/days ago would otherwise have its stale old heartbeat beat
        # out a fresh updated_at/created_at from the current run.
        if doc.processing_status == 'processing' and current_stage is None:
            timeout_seconds = int(current_app.config.get("AI_DOCS_STUCK_NO_STAGE_TIMEOUT_SECONDS", 3600))
            touch_candidates = [
                ts for ts in (
                    ensure_utc(doc.processing_heartbeat_at),
                    ensure_utc(doc.updated_at),
                    ensure_utc(doc.created_at),
                )
                if ts is not None
            ]
            last_touched = max(touch_candidates) if touch_candidates else utcnow()
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
            'resetting': ('Resetting', 10),
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
        from app.services.ai.documents.ingest import enqueue_submitted_document_ai_processing

        result = enqueue_submitted_document_ai_processing(
            submitted_doc_id,
            user_id=getattr(current_user, "id", None),
        )
        if not result.get("ok"):
            code = result.get("code")
            msg = result.get("message") or GENERIC_ERROR_MESSAGE
            if code == "submitted_document_not_found":
                return json_error(
                    f"Submitted document not found: {submitted_doc_id}",
                    200,
                    success=False,
                    code="submitted_document_not_found",
                )
            if code == "missing_storage_path":
                return json_error(
                    "Document has no storage path or source URL",
                    200,
                    success=False,
                    code="missing_storage_path",
                )
            if code == "file_not_found":
                return json_error(msg, 200, success=False, code="file_not_found")
            if code == "download_failed":
                return json_error(msg, 200, success=False, code="download_failed")
            if code == "source_url_unreachable":
                return json_error(msg, 200, success=False, code="source_url_unreachable")
            if code == "unsupported_file_type":
                return json_bad_request(msg)
            return json_server_error(msg)

        logger.info(
            "Admin %s started processing submitted document %s -> AI doc %s",
            getattr(current_user, "email", None),
            submitted_doc_id,
            result.get("ai_document_id"),
        )
        return json_accepted(
            message="Processing started; poll document status for progress.",
            ai_document_id=result.get("ai_document_id"),
            status="processing",
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


def _language_display_name_for_import(language_code: str | None) -> str:
    """Display label for a document language code (import grid)."""
    from config import Config

    lang = (language_code or "").split("_")[0].split("-")[0]
    if lang == "zz":
        return "Unknown"
    return (
        Config.LANGUAGE_DISPLAY_NAMES.get(lang)
        or Config.ALL_LANGUAGES_DISPLAY_NAMES.get(lang)
        or language_code
        or ""
    )


def _serialize_system_document_for_ai_import(
    doc,
    ai_doc,
    *,
    aes_countries=None,
    entity_names=None,
) -> dict:
    """Serialize a SubmittedDocument row for the AI import modal grid."""
    from app.utils.api_serialization import _country_for_aes

    source = "standalone"
    assignment_name = ""
    template_name = ""
    assignment_period = ""

    if doc.assignment_entity_status_id:
        source = "assignment"
        aes = doc.assignment_entity_status
        assigned_form = aes.assigned_form if aes else None
        if assigned_form:
            assignment_name = assigned_form.display_name or ""
            template_name = (assigned_form.template.name if assigned_form.template else "") or ""
            assignment_period = assigned_form.period_name or ""
    elif doc.public_submission_id:
        source = "public"
        public_submission = doc.public_submission
        assigned_form = public_submission.assigned_form if public_submission else None
        if assigned_form:
            assignment_name = assigned_form.display_name or ""
            template_name = (assigned_form.template.name if assigned_form.template else "") or ""
            assignment_period = assigned_form.period_name or ""

    country_name = ""
    if doc.assignment_entity_status_id:
        aes = doc.assignment_entity_status
        if aes:
            country = _country_for_aes(aes, aes_countries)
            if country and getattr(country, "name", None):
                country_name = country.name
    elif doc.public_submission_id:
        public_submission = doc.public_submission
        if public_submission and public_submission.country and public_submission.country.name:
            country_name = public_submission.country.name
    elif doc.country and doc.country.name:
        country_name = doc.country.name
    elif doc.linked_entity_type and doc.linked_entity_id:
        if entity_names:
            country_name = entity_names.get(
                (doc.linked_entity_type, doc.linked_entity_id), ""
            ) or ""
        else:
            country_name = doc.standalone_linked_display or ""

    period_display = (doc.period or "").strip() or assignment_period or ""

    uploaded_by = ""
    if doc.uploaded_by_user:
        uploaded_by = doc.uploaded_by_user.name or doc.uploaded_by_user.email or ""

    status_raw = doc.status.value if hasattr(doc.status, "value") else doc.status

    return {
        "id": doc.id,
        "filename": doc.filename,
        "document_type": doc.document_label or doc.document_type or "",
        "country_name": country_name,
        "source": source,
        "assignment_name": assignment_name,
        "template_name": template_name,
        "period": period_display,
        "language": doc.language or "",
        "language_display": _language_display_name_for_import(doc.language),
        "uploaded_by": uploaded_by,
        "status": str(status_raw or ""),
        "is_public": bool(doc.is_public),
        "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        "file_size": None,
        "file_pending": bool(getattr(doc, "file_pending", False)),
        "source_url": (getattr(doc, "source_url", None) or "").strip() or None,
        "source_url_http_status": getattr(doc, "source_url_http_status", None),
        "source_url_unreachable": bool(getattr(doc, "source_url_unreachable", False)),
        "ai_processed": ai_doc is not None,
        "ai_document_id": ai_doc.id if ai_doc else None,
        "ai_status": ai_doc.processing_status if ai_doc else None,
    }


@bp.route("/documents/list-system-documents", methods=["GET"])
@admin_permission_required('admin.ai.manage')
def list_system_documents():
    """List submitted documents from the system for import into AI."""
    try:
        from app.models import SubmittedDocument, AIDocument, AssignmentEntityStatus, AssignedForm, PublicSubmission
        from sqlalchemy import or_

        # Get query parameters
        search_query = request.args.get('q', '').strip()
        limit = min(int(request.args.get('limit', 5000)), 5000)

        # Build query
        query = (
            db.session.query(SubmittedDocument, AIDocument)
            .outerjoin(AIDocument, AIDocument.submitted_document_id == SubmittedDocument.id)
            .options(
                selectinload(SubmittedDocument.assignment_entity_status)
                .selectinload(AssignmentEntityStatus.assigned_form)
                .selectinload(AssignedForm.template),
                selectinload(SubmittedDocument.public_submission).options(
                    selectinload(PublicSubmission.assigned_form).selectinload(AssignedForm.template),
                    selectinload(PublicSubmission.country),
                ),
                selectinload(SubmittedDocument.form_item),
                selectinload(SubmittedDocument.country),
                selectinload(SubmittedDocument.uploaded_by_user),
            )
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

        total_matching = query.with_entities(SubmittedDocument.id).distinct().count()

        # Order by most recent, not processed first
        query = query.order_by(
            AIDocument.id.is_(None).desc(),  # Unprocessed first
            SubmittedDocument.uploaded_at.desc()
        )

        # Limit results
        documents = query.limit(limit).all()

        from app.utils.api_serialization import batch_countries_for_aes_list
        from app.services.organization.entity_service import EntityService

        aes_list = [
            doc.assignment_entity_status
            for doc, _ai in documents
            if doc.assignment_entity_status
        ]
        aes_countries = batch_countries_for_aes_list(aes_list)

        entity_pairs = {
            (doc.linked_entity_type, doc.linked_entity_id)
            for doc, _ai in documents
            if not doc.assignment_entity_status_id
            and not doc.public_submission_id
            and doc.linked_entity_type
            and doc.linked_entity_id
        }
        entity_names = (
            EntityService.batch_entity_names(
                entity_pairs,
                prefetched=EntityService.prefetch_entities(entity_pairs, include_hierarchy=False),
            )
            if entity_pairs
            else {}
        )

        result = [
            _serialize_system_document_for_ai_import(
                doc,
                ai_doc,
                aes_countries=aes_countries,
                entity_names=entity_names,
            )
            for doc, ai_doc in documents
        ]

        return json_ok(documents=result, total=total_matching, returned=len(result))

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/documents/download-system-document/<int:doc_id>", methods=["GET"])
@admin_permission_required('admin.ai.manage')
def download_system_document_for_import(doc_id):
    """Stream a submitted document for the AI import modal (plain 404, no HTML redirects)."""
    from app.models import SubmittedDocument
    from app.services.imports.fdrs_document_fetch_service import try_materialize_public_fdrs_document
    from werkzeug.exceptions import NotFound

    document = SubmittedDocument.query.get_or_404(doc_id)

    def _has_local_file() -> bool:
        return bool(
            document.storage_path
            and _storage.submitted_source_exists(document.storage_path)
        )

    if not _has_local_file():
        materialized, _user_msg = try_materialize_public_fdrs_document(document)
        if not materialized and not _has_local_file():
            source_url = (document.source_url or "").strip()
            if getattr(document, "file_pending", False) and source_url:
                from app.routes.ai_documents.helpers import _validate_ifrc_fetch_url

                ok, _reason = _validate_ifrc_fetch_url(source_url)
                if ok:
                    return redirect(source_url, code=302)
            abort(404)

    try:
        return _storage.stream_submitted_document_response(
            document.storage_path,
            filename=document.filename,
            as_attachment=True,
        )
    except NotFound:
        abort(404)


# ============================================================================
# REASONING TRACES
# ============================================================================

def _get_default_trace_stats():
    """Return default trace stats structure."""
    return {
        'total_traces': 0,
        'recent_traces': 0,
        'filtered_completed': 0,
        'filtered_failed': 0,
        'success_rate_pct': None,
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
        from app.services.platform.app_settings_service import get_ai_settings

        ai_db = get_ai_settings()
        raw = ai_db.get("AI_GROUNDING_LLM_ENABLED")
        if raw is not None and (not isinstance(raw, str) or raw.strip()):
            return _to_bool(raw, fallback)
    except Exception as e:
        logger.debug("Could not resolve DB AI_GROUNDING_LLM_ENABLED: %s", e)
    return fallback


def _format_merged_trace_query_security(merged: dict) -> dict:
    """Turn merged analyze_ai_user_query output into UI fields (translated strings)."""
    from flask_babel import gettext as _

    if not merged.get("suspicious"):
        return {"suspicious": False, "signals": [], "summary": "", "detail_lines": []}

    labels = {
        "event_handler_attribute": _(
            "HTML event handler (onerror=, onload=, …) — common in XSS probes"
        ),
        "script_tag": _("Script tag or closing script tag in the text"),
        "dangerous_html_tag": _("Potentially active HTML element (iframe, object, embed, …)"),
        "html_img_tag": _("Image tag in raw text — sometimes used with onerror/onload probes"),
        "dangerous_url_protocol": _("javascript: or vbscript: URL pattern"),
        "data_html_protocol": _("data:text/html URL pattern"),
        "html_markup_fragment": _("Markup-like angle brackets and tags in the query"),
        "encoded_markup": _("HTML or script markup appears in encoded form"),
        "js_sink_pattern": _("JavaScript sink pattern (e.g. eval() or document.cookie)"),
    }
    codes = merged.get("signals") or []
    detail_lines = [labels.get(code, code) for code in codes]
    summary = "; ".join(detail_lines[:2])
    if len(detail_lines) > 2:
        summary += " …"
    return {
        "suspicious": True,
        "signals": codes,
        "summary": summary,
        "detail_lines": detail_lines,
    }


def _admin_trace_query_security(trace) -> dict:
    """Suspicion summary for a trace (agent query + optional original user query)."""
    from app.utils.ai_query_security import analyze_ai_user_query, merge_ai_query_security_results

    analyses = [analyze_ai_user_query(getattr(trace, "query", None) or "")]
    if getattr(trace, "original_query", None):
        analyses.append(analyze_ai_user_query(trace.original_query or ""))
    merged = merge_ai_query_security_results(analyses)
    return _format_merged_trace_query_security(merged)


def _admin_trace_query_security_text(text) -> dict:
    """Suspicion summary for a single string (e.g. first message in a conversation)."""
    from app.utils.ai_query_security import analyze_ai_user_query, merge_ai_query_security_results

    merged = merge_ai_query_security_results([analyze_ai_user_query(text or "")])
    return _format_merged_trace_query_security(merged)


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
        from app.models import AIReasoningTrace, AIToolUsage, AIConversation

        # Get query parameters (AG Grid paginates client-side; no server page/per_page)
        status_filter = request.args.get('status', '')
        user_filter = request.args.get('user_id', '', type=str)
        days_filter = request.args.get('days', 0, type=int)
        view_mode = request.args.get('view', 'message', type=str)
        if view_mode not in ('message', 'conversation'):
            view_mode = 'message'

        total_conversations = None

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
            _CONV_LIST_MAX = 2000
            group_rows = grouped.limit(_CONV_LIST_MAX).all()
            conversation_ids = [r[0] for r in group_rows]
            # First-query preview per conversation (earliest trace by created_at; bounded join)
            first_queries = {}
            if conversation_ids:
                earliest_sub = (
                    db.session.query(
                        AIReasoningTrace.conversation_id.label("conv_cid"),
                        func.min(AIReasoningTrace.created_at).label("earliest_at"),
                    )
                    .filter(AIReasoningTrace.conversation_id.in_(conversation_ids))
                    .group_by(AIReasoningTrace.conversation_id)
                    .subquery()
                )
                first_trace_rows = (
                    db.session.query(
                        AIReasoningTrace.conversation_id,
                        AIReasoningTrace.query,
                        AIReasoningTrace.id,
                    )
                    .join(
                        earliest_sub,
                        and_(
                            AIReasoningTrace.conversation_id == earliest_sub.c.conv_cid,
                            AIReasoningTrace.created_at == earliest_sub.c.earliest_at,
                        ),
                    )
                    .order_by(AIReasoningTrace.conversation_id.asc(), AIReasoningTrace.id.asc())
                    .all()
                )
                for cid, q, _tid in first_trace_rows:
                    if cid not in first_queries:
                        first_queries[cid] = (q or "")[:200]
            titles_by_cid = {}
            if conversation_ids:
                for conv_id, conv_title in (
                    db.session.query(AIConversation.id, AIConversation.title)
                    .filter(AIConversation.id.in_(conversation_ids))
                    .all()
                ):
                    titles_by_cid[conv_id] = (conv_title or "").strip()
            conversations = []
            for row in group_rows:
                cid, trace_count, first_at, last_at, total_cost = row
                fq_preview = first_queries.get(cid, "")
                conversations.append({
                    "conversation_id": cid,
                    "conversation_title": titles_by_cid.get(cid, ""),
                    "trace_count": trace_count,
                    "first_at": first_at,
                    "last_at": last_at,
                    "total_cost_usd": total_cost,
                    "first_query_preview": fq_preview,
                    "first_query_security": _admin_trace_query_security_text(fq_preview),
                })
            traces = []
            pagination = None
        else:
            # View by message (default): one row per trace — load a bounded set for AG Grid
            # client-side pagination (see admin/ai/reasoning_traces.html).
            _TRACE_LIST_MAX = 2000
            query = base_filter.options(joinedload(AIReasoningTrace.user)).order_by(
                AIReasoningTrace.created_at.desc()
            )
            traces = query.limit(_TRACE_LIST_MAX).all()
            for _t in traces:
                _t._admin_query_security = _admin_trace_query_security(_t)
            conversations = []
            pagination = None

        # Get statistics
        total_traces = db.session.query(AIReasoningTrace).count()
        # Count traces matching current filters (all-time by default when days_filter=0)
        recent_traces = base_filter.count()
        from app.services.ai.quality.reasoning_trace import TRACE_COMPLETED_STATUSES, TRACE_FAILURE_STATUSES

        filtered_completed = base_filter.filter(
            AIReasoningTrace.status.in_(TRACE_COMPLETED_STATUSES)
        ).count()
        filtered_failed = base_filter.filter(
            AIReasoningTrace.status.in_(TRACE_FAILURE_STATUSES)
        ).count()
        success_rate_pct = (
            round(100.0 * filtered_completed / recent_traces, 1) if recent_traces else None
        )

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
            'filtered_completed': filtered_completed,
            'filtered_failed': filtered_failed,
            'success_rate_pct': success_rate_pct,
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
            conversations=conversations if view_mode == "conversation" else [],
            pagination=pagination,
            conversation_total=total_conversations if view_mode == "conversation" else None,
            stats=stats,
            statuses=statuses,
            current_status=status_filter,
            current_user_filter=user_filter,
            days_filter=days_filter,
            view_mode=view_mode,
            llm_quality_judge_enabled=_is_llm_quality_judge_enabled(),
            title="AI Reasoning Traces",
        )

    except Exception as e:
        logger.error(f"Error loading reasoning traces: {e}", exc_info=True)
        db.session.rollback()
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
                'created_at': ensure_utc(t.created_at).isoformat() if t.created_at else '',
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
                'created_at': ensure_utc(t.created_at).isoformat() if t.created_at else '',
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
            trace_query_security=_admin_trace_query_security(trace),
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
        from app.services.ai.chat.telemetry import get_chatbot_analytics
        analytics = get_chatbot_analytics()

        # Enhance with quality metrics
        days = request.args.get("days", 30, type=int)
        if days not in (7, 30, 90):
            days = 30
        cutoff = utcnow() - timedelta(days=days)

        # Failure rate trend (daily error count vs total, last N days)
        try:
            from sqlalchemy import func as _func, case as _case
            from app.services.ai.quality.reasoning_trace import TRACE_FAILURE_STATUSES

            daily_stats = (
                db.session.query(
                    _func.date(AIReasoningTrace.created_at).label("day"),
                    _func.count(AIReasoningTrace.id).label("total"),
                    _func.sum(
                        _case((AIReasoningTrace.status.in_(TRACE_FAILURE_STATUSES), 1), else_=0)
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
            from app.services.ai.quality.reasoning_trace import TRACE_FAILURE_STATUSES

            failing = (
                db.session.query(AIReasoningTrace.query)
                .filter(
                    AIReasoningTrace.status.in_(TRACE_FAILURE_STATUSES),
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
        from app.services.ai.quality.reasoning_trace import TRACE_COMPLETED_STATUSES, TRACE_FAILURE_STATUSES

        trace_stats = {
            'total': db.session.query(AIReasoningTrace).count(),
            'last_30_days': db.session.query(AIReasoningTrace).filter(
                AIReasoningTrace.created_at >= thirty_days_ago
            ).count(),
            'completed': db.session.query(AIReasoningTrace).filter(
                AIReasoningTrace.status.in_(TRACE_COMPLETED_STATUSES)
            ).count(),
            'errors': db.session.query(AIReasoningTrace).filter(
                AIReasoningTrace.status.in_(TRACE_FAILURE_STATUSES)
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
        db.session.rollback()
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
        db.session.rollback()
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
        page, per_page = validate_pagination_params(request.args, default_per_page=25, max_per_page=100)

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
        db.session.rollback()
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
        data = get_json_safe()
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
