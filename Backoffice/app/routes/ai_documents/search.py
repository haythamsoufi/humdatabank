"""
AI Document search routes.
"""

import logging
from typing import Dict, Any
from flask import request
from flask_login import login_required, current_user

from app.extensions import limiter
from app.services.ai_vector_store import AIVectorStore
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.api_responses import json_bad_request, json_ok, json_server_error

from . import ai_docs_bp
from .helpers import _query_prefers_upr_documents

logger = logging.getLogger(__name__)


@ai_docs_bp.route('/search', methods=['POST'])
@login_required
@limiter.limit("30 per minute")
def search_documents():
    """
    Search documents using vector similarity.

    Body:
        {
            "query": "search query",
            "top_k": 5,
            "file_type": "pdf" (optional)
        }

    Returns:
        JSON with matching document chunks
    """
    try:
        from app.services.authorization_service import AuthorizationService
        data = get_json_safe()
        query = data.get('query', '').strip()
        query_preview = (query[:200] + '...') if len(query) > 200 else query

        if not query:
            return json_bad_request('Query is required')

        top_k = min(int(data.get('top_k', 5)), 20)
        file_type = data.get('file_type', '').strip() or None
        search_mode = (data.get('search_mode') or 'hybrid').strip().lower()
        if search_mode not in {'hybrid', 'vector'}:
            search_mode = 'hybrid'

        logger.info(
            "AI search request: user_id=%s role=%s mode=%s top_k=%s file_type=%s query=%s",
            current_user.id,
            (
                "system_manager"
                if AuthorizationService.is_system_manager(current_user)
                else "admin"
                if AuthorizationService.is_admin(current_user)
                else "focal_point"
                if AuthorizationService.has_role(current_user, "assignment_editor_submitter")
                else "user"
            ),
            search_mode,
            top_k,
            file_type,
            query_preview
        )

        vector_store = AIVectorStore()
        keyword_cache: Dict[str, list[Dict[str, Any]]] = {}
        filters = {'file_type': file_type} if file_type else {}
        if _query_prefers_upr_documents(query):
            filters["is_api_import"] = True
            filters["is_system_document"] = False
        if not filters:
            filters = None

        user_role = (
            "system_manager"
            if AuthorizationService.is_system_manager(current_user)
            else "admin"
            if AuthorizationService.is_admin(current_user)
            else "focal_point"
            if AuthorizationService.has_role(current_user, "assignment_editor_submitter")
            else "user"
        )

        if search_mode == 'vector':
            results = vector_store.search_similar(
                query_text=query,
                top_k=top_k,
                filters=filters,
                user_id=current_user.id,
                user_role=user_role
            )
        else:
            results = vector_store.hybrid_search(
                query_text=query,
                top_k=top_k,
                filters=filters,
                user_id=current_user.id,
                user_role=user_role
            )

        logger.info(
            "AI search response: user_id=%s role=%s mode=%s results=%s query=%s",
            current_user.id,
            user_role,
            search_mode,
            len(results),
            query_preview
        )

        return json_ok(results=results, count=len(results))

    except Exception as e:
        logger.error(f"Document search error: {e}", exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)
