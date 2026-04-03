from app.utils.transactions import request_transaction_rollback
from contextlib import suppress
# Backoffice/app/routes/api/users.py
from app.utils.datetime_helpers import utcnow, ensure_utc
from app.utils.sql_utils import safe_ilike_pattern
"""
User and Dashboard API endpoints.
Part of the /api/v1 blueprint.
"""

from flask import request, current_app, session
from flask_login import login_required, current_user
from sqlalchemy import func, case, or_
from sqlalchemy.orm import aliased, joinedload
from datetime import timedelta, datetime

# Import the API blueprint from parent
from app.routes.api import api_bp

# Import models
from app.models import User, Country, AssignedForm, FormSection, FormItem, FormData
from app.models.assignments import AssignmentEntityStatus
from app.models.core import UserEntityPermission
from app.models.enums import EntityType
from app.models.documents import SubmittedDocument
from app.utils.auth import require_api_key
from app.utils.entity_groups import get_allowed_entity_type_codes, get_enabled_entity_groups
from app.utils.form_localization import get_localized_template_name
from app.utils.constants import SELECTED_COUNTRY_ID_SESSION_KEY
from app.services.entity_service import EntityService
from app.utils.api_helpers import json_response, api_error, PAST_ASSIGNMENT_DAYS, get_json_safe
from app.utils.request_validation import enforce_csrf_json
from app import db


@api_bp.route('/users', methods=['GET'])
@require_api_key
def get_users():
    """
    API endpoint to retrieve a list of all users.
    Authentication: API key in Authorization header (Bearer token).
    Query Parameters:
        - page: Page number (default: 1)
        - per_page: Items per page (default: 20)
        - search: Search query for user name or email
    Returns:
        JSON object containing:
        - users: List of user objects
        - total_items: Total number of users
        - total_pages: Total number of pages
        - current_page: Current page number
        - per_page: Items per page
        - search_query: Search query used (if any)
    """
    try:
        current_app.logger.debug("Entering users API endpoint")

        # Get filter parameters
        from app.utils.api_pagination import validate_pagination_params
        page, per_page = validate_pagination_params(request.args, default_per_page=20)
        search_query = request.args.get('search', default='', type=str).strip()

        # Build base query
        query = User.query

        # Apply search filter
        if search_query:
            safe_pattern = safe_ilike_pattern(search_query)
            query = query.filter(
                db.or_(
                    User.name.ilike(safe_pattern),
                    User.email.ilike(safe_pattern),
                    User.title.ilike(safe_pattern)
                )
            )

        # Order by name and paginate
        paginated_users = query.order_by(User.name.asc(), User.email.asc()).paginate(page=page, per_page=per_page, error_out=False)

        # Serialize user data
        users_data = []
        for user in paginated_users.items:
            # Get user's countries
            user_countries = []
            for country in user.countries:
                user_countries.append({
                    'id': country.id,
                    'name': country.name,
                    'iso3': country.iso3
                })

            # Get RBAC roles for this user
            rbac_roles = []
            try:
                from app.models.rbac import RbacUserRole, RbacRole
                user_roles = RbacUserRole.query.filter_by(user_id=user.id).all()
                role_ids = [ur.role_id for ur in user_roles]
                if role_ids:
                    roles = RbacRole.query.filter(RbacRole.id.in_(role_ids)).all()
                    rbac_roles = [{'code': r.code, 'name': r.name} for r in roles]
            except Exception as e:
                current_app.logger.debug("Could not fetch RBAC roles for user %s: %s", user.id, e)
                rbac_roles = []

            users_data.append({
                'id': user.id,
                'email': user.email,
                'name': user.name,
                'title': user.title,
                'countries': user_countries,
                'chatbot_enabled': user.chatbot_enabled,
                # RBAC roles
                'rbac_roles': rbac_roles,
                'has_api_key': user.api_key is not None
            })

        current_app.logger.debug(f"Users API returning {len(users_data)} items")

        return json_response({
            'users': users_data,
            'total_items': paginated_users.total,
            'total_pages': paginated_users.pages,
            'current_page': paginated_users.page,
            'per_page': paginated_users.per_page,
            'search_query': search_query,
        })

    except Exception as e:
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            f"API Error [ID: {error_id}] fetching users: {e}",
            exc_info=True,
            extra={'endpoint': '/users', 'params': dict(request.args)}
        )
        return api_error("Could not fetch users", 500, error_id, None)


@api_bp.route('/users/<int:user_id>', methods=['GET'])
@require_api_key
def get_user_details(user_id):
    """
    API endpoint to retrieve details for a specific user.
    Authentication: API key in Authorization header (Bearer token).

    SECURITY NOTE: API key holders have full read access to user data.
    This is by design for external system integrations.
    API keys should only be issued to trusted integrations.
    """
    try:
        from app.services import UserService

        # SECURITY: Log access for audit trail
        current_app.logger.info(
            f"API user access: user_id={user_id}, remote_addr={request.remote_addr}"
        )

        user = UserService.get_by_id(user_id)

        if not user:
            return api_error('User not found', 404)

        # Get user's countries
        user_countries = []
        for country in user.countries:
            ns = getattr(country, 'primary_national_society', None)
            user_countries.append({
                'id': country.id,
                'name': country.name,
                'iso3': country.iso3,
                'national_society_name': (ns.name if ns else None),
                'region': country.region
            })

        # Get RBAC roles for this user
        rbac_roles = []
        try:
            from app.models.rbac import RbacUserRole, RbacRole
            user_roles = RbacUserRole.query.filter_by(user_id=user.id).all()
            role_ids = [ur.role_id for ur in user_roles]
            if role_ids:
                roles = RbacRole.query.filter(RbacRole.id.in_(role_ids)).all()
                rbac_roles = [{'code': r.code, 'name': r.name} for r in roles]
        except Exception as e:
            current_app.logger.debug("Could not fetch RBAC roles for user %s: %s", user.id, e)
            rbac_roles = []

        user_data = {
            'id': user.id,
            'email': user.email,
            'name': user.name,
            'title': user.title,
            'countries': user_countries,
            'chatbot_enabled': user.chatbot_enabled,
            'has_api_key': user.api_key is not None,
            # RBAC roles
            'rbac_roles': rbac_roles,
        }

        return json_response(user_data)

    except Exception as e:
        current_app.logger.error(f"API Error fetching user {user_id}: {e}", exc_info=True)
        return api_error("Could not fetch user details", 500)


@api_bp.route('/user/profile', methods=['GET'])
@login_required
def get_current_user_profile():
    """
    Get the current user's profile information.
    Authentication: Requires valid Flask-Login session (session cookie).

    Returns JSON with user profile data:
    {
        "id": int,
        "email": string,
        "name": string | null,
        "title": string | null,
        "chatbot_enabled": bool,
        "profile_color": string | null,
        "country_ids": [int],
        "rbac_roles": [{"code": string, "name": string}]
    }
    """
    try:
        user = current_user

        # Get user's country IDs
        country_ids = []
        if hasattr(user, 'countries'):
            try:
                # Handle both relationship types
                if hasattr(user.countries, 'all'):
                    country_ids = [country.id for country in user.countries.all()]
                else:
                    # If it's a list or other iterable
                    country_ids = [country.id for country in user.countries]
            except Exception as e:
                current_app.logger.warning(f"Error extracting country IDs: {e}")
                country_ids = []

        try:
            from app.utils.app_settings import user_is_explicit_beta_tester

            _ai_beta_tester_badge = bool(user_is_explicit_beta_tester(user))
        except Exception as e:
            current_app.logger.debug("ai_beta_tester flag omitted from profile: %s", e)
            _ai_beta_tester_badge = False

        profile_data = {
            'id': user.id,
            'email': user.email,
            'name': user.name,
            'title': user.title,
            'chatbot_enabled': getattr(user, 'chatbot_enabled', True),
            'profile_color': getattr(user, 'profile_color', None),
            'country_ids': country_ids,
            'ai_beta_tester': _ai_beta_tester_badge,
        }

        # Include RBAC roles
        try:
            from app.models.rbac import RbacUserRole, RbacRole
            urs = RbacUserRole.query.filter_by(user_id=user.id).all()
            role_ids = [ur.role_id for ur in urs]
            roles = RbacRole.query.filter(RbacRole.id.in_(role_ids)).all() if role_ids else []
            profile_data["rbac_roles"] = [{"code": r.code, "name": r.name} for r in roles]
        except Exception as e:
            current_app.logger.debug("Could not fetch RBAC roles for profile: %s", e)
            profile_data["rbac_roles"] = []

        return json_response(profile_data)

    except AttributeError as e:
        current_app.logger.error(f"Attribute error fetching user profile: {e}", exc_info=True)
        return api_error('User profile data incomplete', 500)
    except Exception as e:
        current_app.logger.error(f"Error fetching user profile: {e}", exc_info=True)
        return api_error('Could not fetch user profile', 500)


@api_bp.route('/user/profile', methods=['PUT', 'PATCH'])
@login_required
def update_current_user_profile():
    """
    Update the current user's profile information.
    Authentication: Requires valid Flask-Login session (session cookie).

    Accepts JSON with updatable fields:
    {
        "name": string | null (optional),
        "title": string | null (optional),
        "chatbot_enabled": bool (optional),
        "profile_color": string | null (optional)
    }

    Returns JSON with updated user profile data:
    {
        "id": int,
        "email": string,
        "name": string | null,
        "title": string | null,
        "chatbot_enabled": bool,
        "profile_color": string | null,
        "country_ids": [int],
        "rbac_roles": [{"code": string, "name": string}],
        "message": "Profile updated successfully"
    }
    """
    try:
        csrf_error = enforce_csrf_json()
        if csrf_error:
            return csrf_error

        user = current_user

        # Get request data
        from app.utils.api_responses import require_json_content_type, require_json_data
        err = require_json_content_type()
        if err:
            return err

        data = get_json_safe()
        err = require_json_data(data)
        if err:
            return err

        # Update user fields (only if provided)
        updated_fields = []

        if 'name' in data:
            user.name = data['name'] if data['name'] else None
            updated_fields.append('name')

        if 'title' in data:
            user.title = data['title'] if data['title'] else None
            updated_fields.append('title')

        if 'chatbot_enabled' in data:
            user.chatbot_enabled = bool(data['chatbot_enabled'])
            updated_fields.append('chatbot_enabled')

        if 'profile_color' in data:
            user.profile_color = data['profile_color'] if data['profile_color'] else '#3B82F6'
            updated_fields.append('profile_color')

        # Commit changes
        if updated_fields:
            db.session.flush()

            # Log the activity
            try:
                from app.routes.auth import log_user_activity
                log_user_activity(
                    activity_type='profile_update',
                    description=f'User {user.email} updated their profile information',
                    context_data={
                        'user_id': user.id,
                        'updated_fields': {field: getattr(user, field) for field in updated_fields}
                    }
                )
            except Exception as e:
                current_app.logger.warning(f"Failed to log user activity: {e}")
        else:
            # No fields to update
            return api_error('No valid fields provided for update', 400)

        # Get user's country IDs
        country_ids = []
        if hasattr(user, 'countries'):
            try:
                if hasattr(user.countries, 'all'):
                    country_ids = [country.id for country in user.countries.all()]
                else:
                    country_ids = [country.id for country in user.countries]
            except Exception as e:
                current_app.logger.warning(f"Error extracting country IDs: {e}")
                country_ids = []

        # Return updated profile
        try:
            from app.utils.app_settings import user_is_explicit_beta_tester

            _ai_beta_tester_badge = bool(user_is_explicit_beta_tester(user))
        except Exception as e:
            current_app.logger.debug("ai_beta_tester flag omitted from profile update: %s", e)
            _ai_beta_tester_badge = False

        profile_data = {
            'id': user.id,
            'email': user.email,
            'name': user.name,
            'title': user.title,
            'chatbot_enabled': getattr(user, 'chatbot_enabled', True),
            'profile_color': getattr(user, 'profile_color', None),
            'country_ids': country_ids,
            'ai_beta_tester': _ai_beta_tester_badge,
            'message': 'Profile updated successfully'
        }

        # Include RBAC roles
        try:
            from app.models.rbac import RbacUserRole, RbacRole
            urs = RbacUserRole.query.filter_by(user_id=user.id).all()
            role_ids = [ur.role_id for ur in urs]
            roles = RbacRole.query.filter(RbacRole.id.in_(role_ids)).all() if role_ids else []
            profile_data["rbac_roles"] = [{"code": r.code, "name": r.name} for r in roles]
        except Exception as e:
            current_app.logger.debug("Could not fetch RBAC roles for profile update: %s", e)
            profile_data["rbac_roles"] = []

        return json_response(profile_data)

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error updating user profile: {e}", exc_info=True)
        return api_error('Could not update user profile', 500)


@api_bp.route('/dashboard', methods=['GET'])
@login_required
def get_dashboard():
    """
    Get dashboard data for the current user.
    Authentication: Requires valid Flask-Login session (session cookie).

    Returns JSON with dashboard data:
    {
        "current_assignments": [
            {
                "id": int,
                "name": string,
                "status": string,
                "due_date": "YYYY-MM-DD" | null,
                "completion_rate": float (0-100),
                "template_name": string | null,
                "period_name": string | null
            }
        ],
        "past_assignments": [...], // Same structure as current_assignments
        "entities": [
            {
                "entity_type": string,
                "entity_id": int,
                "name": string,
                "display_name": string
            }
        ],
        "selected_entity": {
            "entity_type": string,
            "entity_id": int,
            "name": string,
            "display_name": string
        } | null
    }
    """
    try:
        user = current_user

        # Get user entities (all entity types user has access to)
        user_entities = []

        entity_permissions = UserEntityPermission.query.filter_by(user_id=user.id).all()
        if entity_permissions:
            for perm in entity_permissions:
                entity = EntityService.get_entity(perm.entity_type, perm.entity_id)
                if entity:
                    user_entities.append({
                        'entity_type': perm.entity_type,
                        'entity_id': perm.entity_id,
                        'entity': entity
                    })
        else:
            # Fallback: resolve entities for users who don't yet have explicit entity permissions
            all_entities = EntityService.get_entities_for_user(user)
            for entity in all_entities:
                entity_type = None
                if isinstance(entity, Country):
                    entity_type = EntityType.country.value
                else:
                    for et, model_class in EntityService.ENTITY_MODEL_MAP.items():
                        if isinstance(entity, model_class):
                            entity_type = et
                            break
                if entity_type:
                    entity_id = getattr(entity, 'id', None)
                    if entity_id:
                        user_entities.append({
                            'entity_type': entity_type,
                            'entity_id': entity_id,
                            'entity': entity
                        })

        enabled_entity_groups = get_enabled_entity_groups()
        allowed_entity_types = get_allowed_entity_type_codes(enabled_entity_groups)
        if allowed_entity_types:
            user_entities = [
                entity for entity in user_entities
                if entity['entity_type'] in allowed_entity_types
            ]
        else:
            user_entities = []

        # Format entities for JSON response
        entities_json = []
        for e in user_entities:
            entity_name = EntityService.get_localized_entity_name(e['entity_type'], e['entity_id'], include_hierarchy=False)
            display_name = EntityService.get_localized_entity_name(e['entity_type'], e['entity_id'], include_hierarchy=True)
            entities_json.append({
                'entity_type': e['entity_type'],
                'entity_id': e['entity_id'],
                'name': entity_name or '',
                'display_name': display_name or entity_name or ''
            })

        # Get selected entity from query parameters (preferred) or session
        selected_entity = None
        SELECTED_ENTITY_TYPE_SESSION_KEY = 'selected_entity_type'
        SELECTED_ENTITY_ID_SESSION_KEY = 'selected_entity_id'

        # Check query parameters first (allows direct entity selection without session update)
        entity_type_param = request.args.get('entity_type')
        entity_id_param = request.args.get('entity_id', type=int)

        if entity_type_param and entity_id_param:
            # Validate that the requested entity is one of the user's accessible entities
            user_entity_pairs = {(e['entity_type'], e['entity_id']) for e in user_entities}
            if (entity_type_param, entity_id_param) in user_entity_pairs or user.has_entity_access(entity_type_param, entity_id_param):
                temp_entity = EntityService.get_entity(entity_type_param, entity_id_param)
                if temp_entity and entity_type_param in allowed_entity_types:
                    if user.has_entity_access(entity_type_param, entity_id_param):
                        entity_name = EntityService.get_localized_entity_name(entity_type_param, entity_id_param, include_hierarchy=False)
                        display_name = EntityService.get_localized_entity_name(entity_type_param, entity_id_param, include_hierarchy=True)
                        selected_entity = {
                            'entity_type': entity_type_param,
                            'entity_id': entity_id_param,
                            'name': entity_name or '',
                            'display_name': display_name or entity_name or ''
                        }
                        # Update session with the selected entity for future requests
                        session[SELECTED_ENTITY_TYPE_SESSION_KEY] = entity_type_param
                        session[SELECTED_ENTITY_ID_SESSION_KEY] = entity_id_param
                        # Set legacy country session for compatibility
                        with suppress(Exception):
                            related_country = EntityService.get_country_for_entity(entity_type_param, entity_id_param)
                            if related_country:
                                session[SELECTED_COUNTRY_ID_SESSION_KEY] = related_country.id

        # Fall back to session if no query parameters provided
        if selected_entity is None:
            if SELECTED_ENTITY_TYPE_SESSION_KEY in session and SELECTED_ENTITY_ID_SESSION_KEY in session:
                retrieved_entity_type = session.get(SELECTED_ENTITY_TYPE_SESSION_KEY)
                retrieved_entity_id = session.get(SELECTED_ENTITY_ID_SESSION_KEY)
                temp_entity = EntityService.get_entity(retrieved_entity_type, retrieved_entity_id)
                if temp_entity and retrieved_entity_type in allowed_entity_types:
                    if user.has_entity_access(retrieved_entity_type, retrieved_entity_id):
                        entity_name = EntityService.get_localized_entity_name(retrieved_entity_type, retrieved_entity_id, include_hierarchy=False)
                        display_name = EntityService.get_localized_entity_name(retrieved_entity_type, retrieved_entity_id, include_hierarchy=True)
                        selected_entity = {
                            'entity_type': retrieved_entity_type,
                            'entity_id': retrieved_entity_id,
                            'name': entity_name or '',
                            'display_name': display_name or entity_name or ''
                        }

        # Default to first entity if none selected
        if selected_entity is None and entities_json:
            selected_entity = entities_json[0]

        # Get assignments for selected entity
        current_assignments = []
        past_assignments = []

        if selected_entity:
            selected_entity_type = selected_entity['entity_type']
            selected_entity_id = selected_entity['entity_id']

            # Query AssignmentEntityStatus for the selected entity
            AF = aliased(AssignedForm)
            assigned_forms_statuses = (
                AssignmentEntityStatus.query
                .join(AF, AF.id == AssignmentEntityStatus.assigned_form_id)
                .options(
                    joinedload(AssignmentEntityStatus.assigned_form).joinedload(AssignedForm.template)
                )
                .filter(
                    AssignmentEntityStatus.entity_type == selected_entity_type,
                    AssignmentEntityStatus.entity_id == selected_entity_id
                )
                .order_by(
                    AssignmentEntityStatus.due_date.asc().nulls_last(),
                    AF.assigned_at.desc()
                )
                .all()
            )

            # Pre-compute item counts
            template_ids = {
                aes.assigned_form.template.id
                for aes in assigned_forms_statuses
                if aes.assigned_form and aes.assigned_form.template
            }

            countable_item_counts_by_template = {}
            document_counts_by_template = {}

            if template_ids:
                counts_rows = (
                    db.session.query(
                        FormSection.template_id,
                        func.sum(case((FormItem.item_type != 'document_field', 1), else_=0)).label('countable_count')
                    )
                    .join(FormItem, FormItem.section_id == FormSection.id)
                    .filter(FormSection.template_id.in_(template_ids))
                    .group_by(FormSection.template_id)
                    .all()
                )
                for tpl_id, cnt in counts_rows:
                    countable_item_counts_by_template[tpl_id] = int(cnt or 0)

                document_counts_by_template = dict(
                    db.session.query(FormSection.template_id, func.count())
                    .join(FormItem, FormItem.section_id == FormSection.id)
                    .filter(
                        FormSection.template_id.in_(template_ids),
                        FormItem.item_type == 'document_field'
                    )
                    .group_by(FormSection.template_id)
                    .all()
                )

            # Pre-compute filled counts.
            # Non-matrix items: count if value is set or marked not-applicable.
            # Matrix items are counted separately so that the entire matrix table
            # counts as ONE filled item when ANY cell contains meaningful data.
            aes_ids = [aes.id for aes in assigned_forms_statuses]
            filled_non_matrix_counts = dict(
                db.session.query(FormData.assignment_entity_status_id, func.count(FormData.id))
                .join(FormItem, FormData.form_item_id == FormItem.id)
                .filter(
                    FormData.assignment_entity_status_id.in_(aes_ids),
                    FormItem.item_type != 'matrix',
                    or_(
                        FormData.value.isnot(None),
                        FormData.disagg_data.isnot(None),
                        FormData.not_applicable == True
                    )
                )
                .group_by(FormData.assignment_entity_status_id)
                .all()
            )

            # Matrix items: each matrix counts as 1 filled item if ANY cell has data
            matrix_entries = (
                db.session.query(
                    FormData.assignment_entity_status_id,
                    FormData.disagg_data,
                    FormData.not_applicable,
                )
                .join(FormItem, FormData.form_item_id == FormItem.id)
                .filter(
                    FormData.assignment_entity_status_id.in_(aes_ids),
                    FormItem.item_type == 'matrix',
                    or_(
                        FormData.disagg_data.isnot(None),
                        FormData.not_applicable == True,
                    )
                )
                .all()
            )
            matrix_filled_counts = {}
            for aes_id, disagg, na in matrix_entries:
                is_filled = False
                if na:
                    is_filled = True
                elif disagg and isinstance(disagg, dict):
                    is_filled = any(
                        v is not None and str(v).strip() != ''
                        for k, v in disagg.items()
                        if not k.startswith('_')
                    )
                if is_filled:
                    matrix_filled_counts[aes_id] = matrix_filled_counts.get(aes_id, 0) + 1

            filled_data_counts = dict(filled_non_matrix_counts)
            for aes_id, cnt in matrix_filled_counts.items():
                filled_data_counts[aes_id] = filled_data_counts.get(aes_id, 0) + cnt

            filled_document_counts = dict(
                db.session.query(SubmittedDocument.assignment_entity_status_id, func.count(SubmittedDocument.id))
                .join(FormItem, SubmittedDocument.form_item_id == FormItem.id)
                .filter(
                    SubmittedDocument.assignment_entity_status_id.in_(aes_ids),
                    FormItem.item_type == 'document_field'
                )
                .group_by(SubmittedDocument.assignment_entity_status_id)
                .all()
            )

            # Process assignments
            one_month_ago = utcnow() - timedelta(days=PAST_ASSIGNMENT_DAYS)
            one_year_ago = utcnow() - timedelta(days=365)

            for aes in assigned_forms_statuses:
                assigned_form = aes.assigned_form
                template = assigned_form.template if assigned_form and assigned_form.template else None
                template_id = template.id if template else None

                total_countable_items = countable_item_counts_by_template.get(template_id, 0) if template_id else 0
                total_document_fields = document_counts_by_template.get(template_id, 0) if template_id else 0
                total_possible_items = total_countable_items + total_document_fields

                filled_data_entries_count = filled_data_counts.get(aes.id, 0)
                filled_documents_count = filled_document_counts.get(aes.id, 0)
                filled_items = filled_data_entries_count + filled_documents_count

                if total_possible_items > 0:
                    completion_rate = (filled_items / total_possible_items) * 100
                else:
                    completion_rate = 0.0

                # Get localized template name
                localized_template_name = get_localized_template_name(template) if template else None
                period_name = assigned_form.period_name if assigned_form and assigned_form.period_name else 'Assignment'
                assignment_data = {
                    'id': aes.id,
                    'name': f"{period_name} - {localized_template_name if localized_template_name else 'Template Missing'}",
                    'status': aes.status,
                    'due_date': aes.due_date.isoformat() if aes.due_date else None,
                    'completion_rate': round(completion_rate, 1),
                    'template_name': localized_template_name,
                    'period_name': period_name
                }

                # Categorize as current or past (aligned with dashboard in main.py)
                # Requires Revision -> past; Approved older than 1 month -> past; Pending/In Progress older than 1 year -> past
                status_ts_utc = ensure_utc(aes.status_timestamp) if aes.status_timestamp else None
                if not status_ts_utc and aes.status in ('Pending', 'In Progress') and assigned_form and assigned_form.assigned_at:
                    status_ts_utc = ensure_utc(assigned_form.assigned_at)
                is_past = (
                    aes.status == 'Requires Revision' or
                    (aes.status == 'Approved' and status_ts_utc and status_ts_utc < one_month_ago) or
                    (aes.status in ('Pending', 'In Progress') and status_ts_utc and status_ts_utc < one_year_ago)
                )

                if is_past:
                    past_assignments.append(assignment_data)
                else:
                    current_assignments.append(assignment_data)

        return json_response({
            'current_assignments': current_assignments,
            'past_assignments': past_assignments,
            'entities': entities_json,
            'selected_entity': selected_entity
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching dashboard data: {e}", exc_info=True)
        return api_error('Could not fetch dashboard data', 500)
