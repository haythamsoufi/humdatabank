"""
AI Document workflow documentation routes.
"""

import logging
from flask import request
from flask_login import login_required, current_user

from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_responses import json_bad_request, json_forbidden, json_not_found, json_ok, json_server_error
from app.routes.admin.shared import admin_required

from . import ai_docs_bp

logger = logging.getLogger(__name__)


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

        return json_ok(workflows=[w.to_dict() for w in workflows], total=len(workflows))

    except Exception as e:
        return json_server_error(GENERIC_ERROR_MESSAGE)


@ai_docs_bp.route('/workflows/<workflow_id>', methods=['GET'])
@login_required
def get_workflow_doc(workflow_id: str):
    """
    Get a specific workflow document by ID.
    """
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

        return json_ok(workflow=workflow.to_dict(), tour_config=workflow.to_tour_config())

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
        from app.services.workflow_docs_service import WorkflowDocsService

        language = request.args.get('lang', 'en')

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

        return json_ok(
            workflow_id=workflow_id,
            language=tour_config.get('language', 'en'),
            tour=tour_config,
        )

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

        return json_ok(query=query, results=[w.to_dict() for w in workflows], total=len(workflows))

    except Exception as e:
        return json_server_error(GENERIC_ERROR_MESSAGE)
