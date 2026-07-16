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


class _PreviewEntityStatus:
    """Minimal AES-like object for variable resolution during template preview.

    Provides the attributes that VariableResolutionService reads from a real
    AssignmentEntityStatus without requiring a database record.
    """
    def __init__(self, entity_id, entity_type, period_name):
        self.id = None  # no DB record; cache key becomes (None, version_id, row_id)
        self.entity_id = int(entity_id)
        self.entity_type = str(entity_type)

        class _AF:
            pass
        af = _AF()
        af.period_name = str(period_name)
        self.assigned_form = af

        self._country = _UNSET = object()
        self._entity = _UNSET

    @property
    def country(self):
        # Lazy-load country by entity_id when entity_type == 'country'
        if not hasattr(self, '_country_obj'):
            self._country_obj = None
            if self.entity_type == 'country':
                try:
                    from app.models.core import Country
                    self._country_obj = Country.query.get(self.entity_id)
                except Exception:
                    pass
        return self._country_obj

    @property
    def entity(self):
        if not hasattr(self, '_entity_obj'):
            self._entity_obj = None
        return self._entity_obj


@api_bp.route('/variables/resolve', methods=['POST'])
@login_required
def resolve_variables():
    """
    API endpoint to resolve template variables with optional row entity context.
    Used for matrix variable columns that need to lookup values per row.

    Normal mode request body:
        {
            "assignment_entity_status_id": int,  # current assignment context
            "template_id": int,
            "row_entity_id": int          # optional
            "row_entity_ids": [int, ...]  # optional (batch)
        }

    Preview mode request body (admin only — no real AES available):
        {
            "preview_entity_id": int,
            "preview_entity_type": str,
            "preview_period_name": str,   # optional
            "template_id": int,
            "row_entity_id": int          # optional
            "row_entity_ids": [int, ...]  # optional (batch)
        }
    """
    try:
        csrf_error = enforce_csrf_json()
        if csrf_error:
            return csrf_error

        data = get_json_safe()
        if not data:
            return api_error('Request body required', 400)

        assignment_entity_status_id = data.get('assignment_entity_status_id')
        preview_entity_id = data.get('preview_entity_id')
        preview_entity_type = data.get('preview_entity_type')
        template_id = data.get('template_id')
        row_entity_id = data.get('row_entity_id')
        row_entity_ids = data.get('row_entity_ids')

        if not template_id:
            return api_error('template_id required', 400)

        # Check if this is a batch request
        is_batch = row_entity_ids is not None and isinstance(row_entity_ids, list)

        if assignment_entity_status_id:
            # Normal mode: validate AES and check assignment access
            assignment_entity_status = AssignmentEntityStatus.query.get(assignment_entity_status_id)
            if not assignment_entity_status:
                current_app.logger.warning(
                    f"[VARIABLE API] Assignment entity status {assignment_entity_status_id} not found"
                )
                return api_error('Assignment entity status not found', 404)

            if not AuthorizationService.can_access_assignment(assignment_entity_status, current_user):
                user_id = None
                try:
                    user_id = current_user.get_id()
                except Exception as e:
                    current_app.logger.debug("current_user.get_id failed: %s", e)
                current_app.logger.warning(
                    f"[VARIABLE API] Access denied for user {user_id} to assignment "
                    f"{assignment_entity_status_id}"
                )
                return api_error('Access denied', 403)

        elif preview_entity_id and preview_entity_type:
            # Preview mode: admin-only, no real AES — build a lightweight stub
            if not AuthorizationService.is_admin(current_user):
                return api_error('Admin access required for preview mode', 403)
            assignment_entity_status = _PreviewEntityStatus(
                entity_id=preview_entity_id,
                entity_type=preview_entity_type,
                period_name=data.get('preview_period_name', ''),
            )

        else:
            return api_error(
                'Provide assignment_entity_status_id or preview_entity_id + preview_entity_type', 400
            )

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
