# Backoffice/app/routes/api/variables.py
"""
API endpoints for template variable operations.
Part of the /api/v1 blueprint.

This module handles:
- Variable resolution for form templates
- Matrix variable lookups with row entity context
"""

from flask import request, current_app
from flask_login import login_required, current_user
import uuid

# Import the API blueprint from api module
from app.routes.api import api_bp

# Import utility functions from utility modules
from app.utils.api_helpers import json_response, api_error, get_json_safe
from app.utils.api_responses import require_json_keys

# Import models and services
from app.models import FormTemplate
from app.models.assignments import AssignmentEntityStatus
from app.services.variable_resolution_service import VariableResolutionService
from app.services.authorization_service import AuthorizationService
from app.utils.request_validation import enforce_csrf_json


@api_bp.route('/variables/resolve', methods=['POST'])
@login_required
def resolve_variables():
    """
    API endpoint to resolve template variables with optional row entity context.
    Used for matrix variable columns that need to lookup values per row.

    Request body (single row):
        {
            "assignment_entity_status_id": int,  # Required: current assignment context
            "template_id": int,  # Required: template ID
            "row_entity_id": int  # Optional: entity ID for matrix row (e.g., country ID 61)
        }

    Request body (batch - preferred for multiple rows):
        {
            "assignment_entity_status_id": int,  # Required: current assignment context
            "template_id": int,  # Required: template ID
            "row_entity_ids": [int, ...]  # Optional: list of entity IDs for matrix rows
        }

    Returns (single row):
        {
            "variables": {
                "variable_name": resolved_value,
                ...
            }
        }

    Returns (batch):
        {
            "results": {
                "row_entity_id": {
                    "variable_name": resolved_value,
                    ...
                },
                ...
            }
        }
    """
    try:
        csrf_error = enforce_csrf_json()
        if csrf_error:
            return csrf_error

        data = get_json_safe()
        err = require_json_keys(data, ['assignment_entity_status_id', 'template_id'])
        if err:
            return err

        assignment_entity_status_id = data.get('assignment_entity_status_id')
        template_id = data.get('template_id')
        row_entity_id = data.get('row_entity_id')
        row_entity_ids = data.get('row_entity_ids')

        # Check if this is a batch request
        is_batch = row_entity_ids is not None and isinstance(row_entity_ids, list)

        # Get assignment entity status
        assignment_entity_status = AssignmentEntityStatus.query.get(assignment_entity_status_id)
        if not assignment_entity_status:
            current_app.logger.warning(f"[VARIABLE API] Assignment entity status {assignment_entity_status_id} not found")
            return api_error('Assignment entity status not found', 404)

        # Check access using AuthorizationService
        if not AuthorizationService.can_access_assignment(assignment_entity_status, current_user):
            # Use Flask-Login's stable identifier accessor to avoid SQLAlchemy
            # DetachedInstanceError in test/edge cases.
            user_id = None
            try:
                user_id = current_user.get_id()
            except Exception as e:
                current_app.logger.debug("current_user.get_id failed: %s", e)
                user_id = None
            current_app.logger.warning(
                f"[VARIABLE API] Access denied for user {user_id} to assignment {assignment_entity_status_id}"
            )
            return api_error('Access denied', 403)

        # Get template version
        template = FormTemplate.query.get(template_id)
        if not template:
            current_app.logger.warning(f"[VARIABLE API] Template {template_id} not found")
            return api_error('Template not found', 404)

        template_version = template.published_version
        if not template_version:
            current_app.logger.warning(f"[VARIABLE API] Template {template_id} has no published version")
            return api_error('Template version not found', 404)

        if is_batch:
            # Batch resolution for multiple rows
            batch_results = VariableResolutionService.resolve_variables_batch(
                template_version,
                assignment_entity_status,
                row_entity_ids=row_entity_ids
            )
            return json_response({
                'results': batch_results
            })
        else:
            # Single row resolution (backward compatibility)
            resolved_variables = VariableResolutionService.resolve_variables(
                template_version,
                assignment_entity_status,
                row_entity_id=row_entity_id
            )

            return json_response({
                'variables': resolved_variables
            })

    except Exception as e:
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            f"API Error [ID: {error_id}] resolving variables: {e}",
            exc_info=True,
            extra={'endpoint': '/variables/resolve', 'data': data if 'data' in locals() else None}
        )
        return api_error("Could not resolve variables", 500, error_id, None)
