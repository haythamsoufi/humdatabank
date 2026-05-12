"""
AI Document management routes: list, get, update, download, delete.
"""

import os
import logging
from flask import request, send_file, redirect
from flask_login import login_required, current_user

from app.extensions import db, limiter
from app.models import AIDocument, AIDocumentChunk
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.api_responses import json_bad_request, json_forbidden, json_not_found, json_ok, json_server_error
from app.services import storage_service as _storage

from . import ai_docs_bp
from .helpers import _ai_doc_storage_delete, _ai_doc_source_ready, _validate_ifrc_fetch_url

logger = logging.getLogger(__name__)


@ai_docs_bp.route('/', methods=['GET'])
@login_required
def list_documents():
    """
    List all AI-processed documents accessible to the user.

    Query parameters:
    - limit: Max results (default 50, max 200)
    - offset: Pagination offset
    - status: Filter by processing status
    - file_type: Filter by file type

    Returns:
        JSON with list of documents
    """
    try:
        limit = min(int(request.args.get('limit', 50)), 200)
        offset = int(request.args.get('offset', 0))
        status = request.args.get('status', '').strip()
        file_type = request.args.get('file_type', '').strip()

        query = AIDocument.query

        from app.services.authorization_service import AuthorizationService
        can_manage_docs = (
            AuthorizationService.is_admin(current_user)
            or AuthorizationService.has_rbac_permission(current_user, "admin.documents.manage")
            or AuthorizationService.has_rbac_permission(current_user, "admin.ai.manage")
        )
        if not can_manage_docs:
            query = query.filter(
                db.or_(
                    AIDocument.is_public == True,
                    AIDocument.user_id == current_user.id
                )
            )

        if status:
            query = query.filter(AIDocument.processing_status == status)
        if file_type:
            query = query.filter(AIDocument.file_type == file_type)

        total = query.count()

        # Sort by most recently changed so re-imported/reprocessed docs show up immediately in the UI.
        documents = query.order_by(AIDocument.updated_at.desc(), AIDocument.created_at.desc()).offset(offset).limit(limit).all()

        return json_ok(
            documents=[doc.to_dict() for doc in documents],
            total=total,
            limit=limit,
            offset=offset,
        )

    except Exception as e:
        logger.error(f"List documents error: {e}", exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)


@ai_docs_bp.route('/<int:document_id>', methods=['GET'])
@login_required
def get_document(document_id: int):
    """Get details of a specific document."""
    try:
        doc = AIDocument.query.get_or_404(document_id)

        from app.services.authorization_service import AuthorizationService
        can_manage_docs = (
            AuthorizationService.is_admin(current_user)
            or AuthorizationService.has_rbac_permission(current_user, "admin.documents.manage")
            or AuthorizationService.has_rbac_permission(current_user, "admin.ai.manage")
        )
        if not can_manage_docs:
            if not doc.is_public and doc.user_id != current_user.id:
                return json_forbidden('Access denied')

        include_chunks = request.args.get('include_chunks', 'false').lower() == 'true'

        result = doc.to_dict()

        if include_chunks:
            chunks = AIDocumentChunk.query.filter_by(document_id=document_id).order_by(AIDocumentChunk.chunk_index).all()
            result['chunks'] = [chunk.to_dict(include_content=False) for chunk in chunks]

        return json_ok(document=result)

    except Exception as e:
        logger.error(f"Get document error: {e}", exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)


@ai_docs_bp.route('/<int:document_id>', methods=['PATCH'])
@login_required
@limiter.limit("60 per minute")
def update_document(document_id: int):
    """Update document metadata (e.g. is_public). Only admins can set is_public to True."""
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

        from app.services.ai_metadata_extractor import DOCUMENT_CATEGORIES

        data = get_json_safe()
        if "is_public" in data:
            is_public = data.get("is_public")
            if isinstance(is_public, str):
                is_public = is_public.lower() in ("true", "1", "yes")
            else:
                is_public = bool(is_public)
            if is_public and not AuthorizationService.is_admin(current_user):
                return json_forbidden('Only admins can make documents public')
            doc.is_public = is_public

        if "document_category" in data:
            cat = (data.get("document_category") or "").strip() or None
            if cat is not None and cat not in DOCUMENT_CATEGORIES:
                return json_bad_request(f'Invalid category. Allowed: {", ".join(DOCUMENT_CATEGORIES)}')
            doc.document_category = cat

        db.session.commit()
        return json_ok(document=doc.to_dict())
    except Exception as e:
        logger.error("Update document error: %s", e, exc_info=True)
        db.session.rollback()
        return json_server_error(GENERIC_ERROR_MESSAGE)


@ai_docs_bp.route('/<int:document_id>/download', methods=['GET'])
@login_required
def download_document(document_id: int):
    """Download the original file for a document, or redirect to source_url when set."""
    try:
        doc = AIDocument.query.get_or_404(document_id)

        from app.services.authorization_service import AuthorizationService
        can_manage_docs = (
            AuthorizationService.is_admin(current_user)
            or AuthorizationService.has_rbac_permission(current_user, "admin.documents.manage")
            or AuthorizationService.has_rbac_permission(current_user, "admin.ai.manage")
        )
        if not can_manage_docs:
            if not doc.is_public and doc.user_id != current_user.id:
                return json_forbidden('Access denied')

        if doc.source_url:
            ok, reason = _validate_ifrc_fetch_url(doc.source_url)
            if not ok:
                logger.warning(f"Blocked redirect to untrusted/invalid URL: {doc.source_url} ({reason})")
                return json_bad_request('External document URL is not from a trusted source')
            return redirect(doc.source_url, code=302)

        if not doc.storage_path or not _ai_doc_source_ready(doc):
            return json_not_found('File not found')

        if getattr(doc, "submitted_document_id", None):
            p = doc.storage_path.strip()
            cr = _storage.category_rel_for_submitted_storage_path(p)
            if cr is None:
                if p and os.path.exists(p):
                    return send_file(
                        p,
                        as_attachment=True,
                        download_name=doc.filename,
                        mimetype='application/octet-stream',
                    )
                return json_not_found('File not found')
            cat, rel = cr
            return _storage.stream_response(
                cat,
                rel,
                filename=doc.filename,
                mimetype='application/octet-stream',
                as_attachment=True,
            )

        if os.path.isabs(doc.storage_path):
            return send_file(doc.storage_path, as_attachment=True,
                             download_name=doc.filename, mimetype='application/octet-stream')
        return _storage.stream_response(
            _storage.AI_DOCUMENTS, doc.storage_path,
            filename=doc.filename, mimetype='application/octet-stream',
            as_attachment=True,
        )

    except Exception as e:
        logger.error(f"Download document error: {e}", exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)


@ai_docs_bp.route('/<int:document_id>', methods=['DELETE'])
@login_required
@limiter.limit("20 per minute")
def delete_document(document_id: int):
    """Delete a document and all its embeddings."""
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

        # Do not delete underlying SubmittedDocument blob when removing the AI index row.
        if doc.storage_path and not getattr(doc, "submitted_document_id", None):
            try:
                _ai_doc_storage_delete(doc.storage_path)
            except Exception as e:
                logger.warning(f"Failed to delete file: {e}")

        db.session.delete(doc)
        db.session.commit()

        logger.info(f"Deleted document {document_id}: {doc.filename}")

        return json_ok(message='Document deleted successfully')

    except Exception as e:
        logger.error(f"Delete document error: {e}", exc_info=True)
        db.session.rollback()
        return json_server_error(GENERIC_ERROR_MESSAGE)
