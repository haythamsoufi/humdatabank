# Backoffice/app/routes/api/assignments.py
"""
Assignment and Matrix API endpoints.
Part of the /api/v1 blueprint.
"""

from flask import request, current_app
from flask_login import login_required, current_user
import uuid

# Import the API blueprint from parent
from app.routes.api import api_bp
from app.utils.sql_utils import safe_ilike_pattern

# Import models
from app.models import AssignedForm, FormData, FormItem
from app.models.assignments import AssignmentEntityStatus
from app.services.authorization_service import AuthorizationService
from app.utils.auth import require_api_key
from app.utils.rate_limiting import api_rate_limit

# Import utility functions
from app.utils.api_helpers import json_response, api_error, get_json_safe
from app.utils.api_responses import require_json_keys
from app.services.security.api_authentication import authenticate_api_request, get_user_allowed_template_ids
from app.utils.api_pagination import validate_pagination_params
from app.utils.request_validation import enforce_csrf_json
from app import db


@api_bp.route('/assigned-forms', methods=['GET'])
@api_rate_limit()
def get_assigned_forms():
    """
    API endpoint to retrieve assigned form IDs and their associated country IDs.
    Authentication (one of):
      - Authorization: Bearer YOUR_API_KEY (full access, paginated response)
      - HTTP Basic auth or session (user-scoped access, no pagination)
    Power BI: use Bearer in Web.Contents Headers and set data source credential to Anonymous so the header is not overridden.
    Query Parameters:
        - template_id: Filter by template ID
        - period_name: Filter by period name
        - page: Page number (default: 1, only used with API key auth)
        - per_page: Items per page (default: 20, max 100000, only used with API key auth)
    """
    try:
        # Authenticate request
        auth_result = authenticate_api_request()
        if hasattr(auth_result, 'status_code'):
            return auth_result
        elevated_access, auth_user, api_key_record = auth_result

        # Determine if we should paginate
        should_paginate = elevated_access

        # Validate pagination parameters
        if should_paginate:
            page, per_page = validate_pagination_params(request.args)
        else:
            page = 1
            per_page = None

        current_app.logger.debug("Entering assigned forms API endpoint")

        # Get filter parameters
        template_id = request.args.get('template_id', type=int)
        period_name = request.args.get('period_name', default='', type=str).strip()

        # Build base query
        query = AssignedForm.query

        # Apply RBAC filtering for user auth
        if not elevated_access and auth_user is not None:
            allowed_template_ids = get_user_allowed_template_ids(auth_user.id)
            if not allowed_template_ids:
                # User has no access to any templates
                if should_paginate:
                    return json_response({
                        'assigned_forms': [],
                        'total_items': 0,
                        'total_pages': 0,
                        'current_page': page,
                        'per_page': per_page,
                        'template_id_filter': template_id,
                        'period_name_filter': period_name
                    })
                else:
                    return json_response({
                        'assigned_forms': [],
                        'total_items': 0,
                        'total_pages': None,
                        'current_page': None,
                        'per_page': None,
                        'template_id_filter': template_id,
                        'period_name_filter': period_name
                    })
            query = query.filter(AssignedForm.template_id.in_(allowed_template_ids))

        # Apply filters
        if template_id:
            query = query.filter(AssignedForm.template_id == template_id)
        if period_name:
            query = query.filter(AssignedForm.period_name.ilike(safe_ilike_pattern(period_name)))

        # Order by assigned_at (newest first)
        query = query.order_by(AssignedForm.assigned_at.desc())

        if should_paginate:
            # API key auth: paginate
            paginated_forms = query.paginate(page=page, per_page=per_page, error_out=False)
            forms = paginated_forms.items
            total_items = paginated_forms.total
            total_pages = paginated_forms.pages
        else:
            # User auth: get all accessible forms
            forms = query.all()
            total_items = len(forms)
            total_pages = None

        # Serialize assigned form data
        forms_data = []
        for assigned_form in forms:
            # Get assignment country status information for this assigned form
            country_assignments = []
            for status in assigned_form.country_statuses:
                country_assignments.append({
                    'assignment_entity_status_id': status.id,
                    'country_id': status.country_id,
                    'iso3': status.country.iso3 if status.country else None,
                    'status': status.status,
                    'status_timestamp': status.status_timestamp.isoformat() if status.status_timestamp else None,
                    'due_date': status.due_date.isoformat() if status.due_date else None
                })

            # Sort by country_id for consistent ordering
            country_assignments.sort(key=lambda x: x['country_id'])

            # Get template information
            template = assigned_form.template
            version = template.published_version if template and template.published_version else (template.versions.order_by('created_at').first() if template else None)
            template_info = {
                'id': template.id if template else None,
                'name': template.name if template else None
            }

            forms_data.append({
                'id': assigned_form.id,
                'template_id': assigned_form.template_id,
                'template': template_info,
                'period_name': assigned_form.period_name,
                'assigned_at': assigned_form.assigned_at.isoformat() if assigned_form.assigned_at else None,
                'country_assignments': country_assignments,
                'countries_count': len(country_assignments)
            })

        current_app.logger.debug(f"Assigned forms API returning {len(forms_data)} items")

        if should_paginate:
            return json_response({
                'assigned_forms': forms_data,
                'total_items': total_items,
                'total_pages': total_pages,
                'current_page': page,
                'per_page': per_page,
                'template_id_filter': template_id,
                'period_name_filter': period_name
            })
        else:
            return json_response({
                'assigned_forms': forms_data,
                'total_items': total_items,
                'total_pages': None,
                'current_page': None,
                'per_page': None,
                'template_id_filter': template_id,
                'period_name_filter': period_name
            })

    except Exception as e:
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            f"API Error [ID: {error_id}] fetching assigned forms: {e}",
            exc_info=True,
            extra={'endpoint': '/assigned-forms', 'params': dict(request.args)}
        )
        return api_error("Could not fetch assigned forms", 500, error_id, None)


@api_bp.route('/matrix/auto-load-entities', methods=['POST'])
@login_required
def get_matrix_auto_load_entities():
    """
    API endpoint to fetch saved matrix data and extract entity IDs for auto-loading.

    Request body:
        {
            "source_template_id": int,
            "source_assignment_period": str,
            "source_form_item_id": int,
            "assignment_entity_status_id": int  # Current assignment context for access control
        }

    Returns:
        {
            "entities": [
                {"entity_id": int, "entity_type": str},
                ...
            ],
            "entity_type": str  # From _table field
        }
    """
    try:
        csrf_error = enforce_csrf_json()
        if csrf_error:
            return csrf_error

        data = get_json_safe()
        err = require_json_keys(data, [
            'source_template_id', 'source_assignment_period',
            'source_form_item_id', 'assignment_entity_status_id'
        ])
        if err:
            return err

        source_template_id = data.get('source_template_id')
        source_assignment_period = data.get('source_assignment_period')
        source_form_item_id = data.get('source_form_item_id')
        assignment_entity_status_id = data.get('assignment_entity_status_id')

        # Check access to current assignment
        from app.services import AssignmentService
        assignment_entity_status = AssignmentService.get_assignment_entity_status_by_id(assignment_entity_status_id)
        if not assignment_entity_status:
            return api_error('Assignment entity status not found', 404)

        if not AuthorizationService.can_access_assignment(assignment_entity_status, current_user):
            return api_error('Access denied', 403)

        # Find the source assignment
        source_assigned_form = AssignmentService.get_assigned_forms_by_template(source_template_id).filter_by(
            period_name=source_assignment_period
        ).first()

        if not source_assigned_form:
            return json_response({
                'entities': [],
                'entity_type': None,
                'reason': 'no_source_assignment',
                'detail': f'No assignment found for template {source_template_id} and period "{source_assignment_period}". '
                          'Verify the variable\'s source assignment period exists and is spelled exactly as in the assignment.'
            })

        # Get the current assignment's entity to filter source data
        # Only load entities from source assignments that match the current assignment's entity
        current_entity_id = assignment_entity_status.entity_id
        current_entity_type = assignment_entity_status.entity_type

        # Filter source entity statuses to only include those matching the current assignment's entity
        matching_source_entity_statuses = [
            aes for aes in source_assigned_form.entity_statuses
            if aes.entity_id == current_entity_id and aes.entity_type == current_entity_type
        ]

        if not matching_source_entity_statuses:
            return json_response({
                'entities': [],
                'entity_type': None,
                'reason': 'no_matching_entity_in_source',
                'detail': f'This entity is not assigned in the source period "{source_assignment_period}". '
                          'Auto-load only uses data from the same entity in another assignment.'
            })

        # Get FormData entries for the source form item, but only from entity statuses
        # that match the current assignment's entity
        form_data_entries = FormData.query.filter(
            FormData.assignment_entity_status_id.in_(
                [aes.id for aes in matching_source_entity_statuses]
            ),
            FormData.form_item_id == source_form_item_id
        ).all()

        # Extract unique entity IDs from matrix data
        entity_set = set()
        entity_type = None  # Store most common entity type for backward compatibility

        source_assignment_entity_status_ids = [aes.id for aes in matching_source_entity_statuses]

        if not form_data_entries:
            return json_response({
                'entities': [],
                'entity_type': None,
                'reason': 'no_form_data',
                'detail': f'No saved data for the source matrix (field id {source_form_item_id}) in period '
                          f'"{source_assignment_period}" for this entity. Save the source matrix first.',
                'debug_info': {
                    'current_assignment_entity_status_id': assignment_entity_status_id,
                    'source_assignment_entity_status_ids_queried': source_assignment_entity_status_ids,
                    'source_template_id': source_template_id,
                    'source_assignment_period': source_assignment_period,
                    'source_form_item_id': source_form_item_id,
                }
            })

        # Get optional tick column filter from request
        require_tick_value_1 = data.get('require_tick_value_1', False)
        tick_column_names = data.get('tick_column_names', [])  # Optional list of tick column names to check

        # Track entities with their entity types and tick status
        # entity_id -> {entity_type: str, has_tick: bool}
        entity_info = {}

        for entry in form_data_entries:
            if not entry.disagg_data or not isinstance(entry.disagg_data, dict):
                continue

            # Get entity type from _table field for this entry
            entry_entity_type = entry.disagg_data.get('_table')
            if entry_entity_type:
                # Store entity type for backward compatibility (use most common or first)
                if not entity_type:
                    entity_type = entry_entity_type

            # Extract entity IDs from keys like "61_SP1", "62_SP2", etc.
            # Format: "{entity_id}_{column_name}"
            for key in entry.disagg_data.keys():
                if key == '_table':
                    continue

                # Extract entity ID (first part before underscore)
                if '_' in key:
                    entity_id_str = key.split('_')[0]
                    try:
                        entity_id = int(entity_id_str)

                        # Initialize entity tracking if not exists
                        if entity_id not in entity_info:
                            entity_info[entity_id] = {
                                'entity_type': entry_entity_type,  # Store entity type from this entry's _table
                                'has_tick': False
                            }

                        # Check if this is a tick column with value = 1 (if filtering enabled)
                        if require_tick_value_1 and tick_column_names:
                            column_name = '_'.join(key.split('_')[1:])  # Get column name (rest after first underscore)
                            if column_name in tick_column_names:
                                cell_value = entry.disagg_data.get(key)
                                # Use effective value (modified if present, else original) for variable-column format
                                if isinstance(cell_value, dict) and ('modified' in cell_value or 'original' in cell_value):
                                    cell_value = cell_value.get('modified') if cell_value.get('modified') is not None else cell_value.get('original')
                                # Check if value is 1 (ticked)
                                if cell_value == 1 or cell_value == '1' or cell_value is True:
                                    entity_info[entity_id]['has_tick'] = True
                        elif not require_tick_value_1:
                            # If filtering is disabled, mark entity as valid (will be added later)
                            entity_info[entity_id]['has_tick'] = True
                    except (ValueError, TypeError):
                        continue

        # If disagg_data had no _table, entity_type is None and we would add no entities.
        # Fallback: get entity type from the form item's matrix config (lookup_list_id).
        if entity_type is None and entity_info:
            form_item = FormItem.query.get(source_form_item_id)
            if form_item and form_item.config:
                mc = form_item.config.get('matrix_config') or form_item.config
                entity_type = mc.get('lookup_list_id') or getattr(form_item, 'lookup_list_id', None)
        if not entity_info:
            return json_response({
                'entities': [],
                'entity_type': None,
                'reason': 'no_entity_keys_in_data',
                'detail': 'Source matrix data has no row keys. Ensure the source field is a matrix with '
                          'entity rows and data has been saved.'
            })

        # Add entities to set based on filtering requirements
        for entity_id, info in entity_info.items():
            entity_type_for_entity = info['entity_type'] or entity_type  # Use entry-specific type or fallback to global

            if not require_tick_value_1:
                # No filtering: add all entities
                if entity_type_for_entity:
                    entity_set.add((entity_id, entity_type_for_entity))
            else:
                # Filtering enabled: only add entities with at least one ticked box
                if info['has_tick'] and entity_type_for_entity:
                    entity_set.add((entity_id, entity_type_for_entity))
                else:
                    pass  # Entity filtered out by tick column requirement

        # Convert to list of dicts
        entities = [{'entity_id': eid, 'entity_type': etype} for eid, etype in entity_set]

        response_payload = {
            'entities': entities,
            'entity_type': entity_type
        }
        if len(entities) == 0 and require_tick_value_1 and entity_info:
            response_payload['reason'] = 'all_filtered_by_tick'
            response_payload['detail'] = (
                f'No rows had a tick in the required columns ({tick_column_names}). '
                'Auto-load only includes rows where at least one of these tick columns is checked.'
            )
        return json_response(response_payload)

    except Exception as e:
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            f"API Error [ID: {error_id}] fetching matrix auto-load entities: {e}",
            exc_info=True,
            extra={'endpoint': '/matrix/auto-load-entities', 'data': data if 'data' in locals() else None}
        )
        return api_error("Could not fetch matrix entities", 500, error_id, None)
