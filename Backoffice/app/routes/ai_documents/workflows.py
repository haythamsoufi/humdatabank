"""
AI Document workflow documentation routes.
"""

import base64
import logging
from flask import request
from flask_login import login_required, current_user

from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_responses import json_bad_request, json_forbidden, json_not_found, json_ok, json_server_error
from app.routes.admin.shared import admin_required

from . import ai_docs_bp

logger = logging.getLogger(__name__)


def _decode_workflow_id(encoded: str) -> str:
    """
    Decode a URL-safe base64 workflow ID sent by the client.

    Client encodes slugs to avoid Azure WAF rules that block keywords like
    "submit-data" in URL path segments. Standard base64 with + → - and / → _
    substitution; padding is re-added before decoding.
    """
    # Restore standard base64 alphabet and padding.
    b64 = encoded.replace('-', '+').replace('_', '/')
    b64 += '=' * (-len(b64) % 4)
    return base64.b64decode(b64).decode('utf-8')


@ai_docs_bp.route('/workflows/sync', methods=['POST'])
@admin_required
def sync_workflow_docs():
    """
    Sync workflow documentation to the vector store.

    This indexes all workflow markdown files from docs/workflows/
    for semantic search by the chatbot.
    """
    try:
        from app.services.workflow_docs_service import WorkflowDocsService

        service = WorkflowDocsService()
        service.reload()  # Force reload from disk

        results = service.sync_to_vector_store()

        return json_ok(
            message='Workflow documentation synced successfully',
            synced=results.get('synced', 0),
            updated=results.get('updated', 0),
            errors=results.get('errors', []),
            total_cost_usd=results.get('total_cost', 0),
        )

    except Exception as e:
        return json_server_error(GENERIC_ERROR_MESSAGE)


@ai_docs_bp.route('/workflows', methods=['GET'])
@login_required
def list_workflow_docs():
    """
    List all available workflow documentation.

    Filters by user role if not admin.
    """
    try:
        from app.services.workflow_docs_service import WorkflowDocsService

        service = WorkflowDocsService()

        from app.services.authorization_service import AuthorizationService
        role = AuthorizationService.access_level(current_user)

        if role in ['admin', 'system_manager']:
            workflows = service.get_all_workflows()
        else:
            workflows = service.get_workflows_for_role(role)

        resp = json_ok(workflows=[w.to_dict() for w in workflows], total=len(workflows))
        # Role-filtered; cache per-browser only (not on a shared/proxy cache).
        resp.headers['Cache-Control'] = 'private, max-age=300'
        return resp

    except Exception as e:
        return json_server_error(GENERIC_ERROR_MESSAGE)


@ai_docs_bp.route('/workflows/<workflow_id>', methods=['GET'])
@login_required
def get_workflow_doc(workflow_id: str):
    """
    Get a specific workflow document by ID.
    """
    try:
        workflow_id = _decode_workflow_id(workflow_id)
    except Exception:
        return json_not_found('Workflow not found')

    try:
        from app.services.workflow_docs_service import WorkflowDocsService

        service = WorkflowDocsService()
        workflow = service.get_workflow_by_id(workflow_id)

        if not workflow:
            return json_not_found(f'Workflow "{workflow_id}" not found')

        from app.services.authorization_service import AuthorizationService
        role = AuthorizationService.access_level(current_user)
        if role not in ['admin', 'system_manager']:
            if role not in workflow.roles and 'all' not in workflow.roles:
                return json_forbidden('Access denied')

        resp = json_ok(workflow=workflow.to_dict(), tour_config=workflow.to_tour_config())
        # Role-filtered (403 above for unauthorized roles); cache per-browser only.
        resp.headers['Cache-Control'] = 'private, max-age=300'
        return resp

    except Exception as e:
        return json_server_error(GENERIC_ERROR_MESSAGE)


@ai_docs_bp.route('/workflows/<workflow_id>/tour', methods=['GET'])
@login_required
def get_workflow_tour(workflow_id: str):
    """
    Get the interactive tour configuration for a workflow.

    Query params:
    - lang: Language code (en, fr, es, ar). Defaults to 'en'.

    Returns the tour config in a format ready for InteractiveTour.js
    """
    try:
        workflow_id = _decode_workflow_id(workflow_id)
    except Exception:
        return json_not_found('Tour not found')

    try:
        from app.services.workflow_docs_service import WorkflowDocsService

        language = request.args.get('lang', 'en')

        # [WORKFLOW_TOUR_DYNAMIC_HIT] confirms the static/CDN offload
        # (`flask workflows generate-static`) is doing its job: after that
        # deploy, most tour requests should be served by the browser/CDN cache
        # and never reach this dynamic endpoint. Rising volume here signals a
        # CDN or cache-key mismatch worth investigating.
        logger.info(
            "[WORKFLOW_TOUR_DYNAMIC_HIT] workflow_id=%s lang=%s user_id=%s",
            workflow_id, language, getattr(current_user, 'id', None),
        )

        service = WorkflowDocsService()

        service._ensure_loaded()

        tour_config = service.get_workflow_for_tour(workflow_id, language)

        if not tour_config:
            workflow = service.get_workflow_by_id(workflow_id)
            if workflow:
                logger.warning(f"Workflow '{workflow_id}' exists but has no steps or tour config")
                return json_not_found(f'Workflow "{workflow_id}" exists but has no tour steps configured')
            else:
                return json_not_found(f'Tour for workflow "{workflow_id}" not found')

        resp = json_ok(
            workflow_id=workflow_id,
            language=tour_config.get('language', 'en'),
            tour=tour_config,
        )
        # Same content for every user (no role filtering); safe to cache publicly.
        # This is also the fallback path when the pre-generated static/CDN file
        # (see `flask workflows generate-static`) is missing or stale, so most
        # traffic should hit that instead - this header protects the remainder.
        resp.headers['Cache-Control'] = 'public, max-age=3600'
        return resp

    except Exception as e:
        logger.exception(f"Error getting tour for workflow '{workflow_id}': {e}")
        return json_server_error(GENERIC_ERROR_MESSAGE)


@ai_docs_bp.route('/workflows/search', methods=['GET'])
@login_required
def search_workflow_docs():
    """
    Search workflow documentation.

    Query params:
    - q: Search query (required)
    - category: Filter by category (optional)
    """
    try:
        from app.services.workflow_docs_service import WorkflowDocsService

        query = request.args.get('q', '').strip()
        category = request.args.get('category', '').strip() or None

        if not query:
            return json_bad_request('Search query is required')

        service = WorkflowDocsService()

        from app.services.authorization_service import AuthorizationService
        role = AuthorizationService.access_level(current_user)
        if role in ['admin', 'system_manager']:
            role = None

        workflows = service.search_workflows(query, role=role, category=category)

        resp = json_ok(query=query, results=[w.to_dict() for w in workflows], total=len(workflows))
        resp.headers['Cache-Control'] = 'private, max-age=60'
        return resp

    except Exception as e:
        return json_server_error(GENERIC_ERROR_MESSAGE)
