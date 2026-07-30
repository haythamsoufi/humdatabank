from app.routes.forms.helpers import parse_csv_id_set
from app.utils.datetime_helpers import utcnow
from app.utils.sql_utils import safe_ilike_pattern
"""
API endpoints for form-related operations.
Extracted from forms.py for better organization and separation of concerns.

This blueprint handles:
- Indicator bank search API
- Dynamic indicators management API
- Repeat instances management API

All endpoints require authentication and maintain JavaScript compatibility.
"""

from flask import Blueprint, request, current_app, render_template
from flask_login import login_required, current_user
from flask_limiter.util import get_remote_address
from app.extensions import csrf, limiter
from app.models import (
    db, IndicatorBank, DynamicIndicatorData,
    FormSection, RepeatGroupInstance, LookupList, LookupListRow,
    User, Country, NationalSociety, Config, SubmissionDiscussionComment,
)
from app.utils.form_localization import (
    get_localized_indicator_name, get_localized_sector_name, get_localized_subsector_name,
    get_localized_indicator_definition, get_localized_indicator_type, get_localized_indicator_unit,
    get_translation_key
)
from sqlalchemy import or_, inspect
from sqlalchemy.orm import joinedload
from datetime import datetime
import base64
import re
import json
from app.services.platform.presence_store import (
    get_active_presence,
    record_presence,
    remove_presence,
)
from sqlalchemy import select

from app.models import (
    AssignmentEntityStatus, AssignedForm, FormTemplate, FormTemplateVersion,
    FormItem, FormData,
)
from app.services import check_aes_access_light
from app.services import check_country_access
from app.services import ensure_aes_access
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.request_utils import get_json_or_form, is_json_request
from app.utils.api_responses import json_bad_request, json_error, json_forbidden, json_not_found, json_ok, json_server_error, require_json_keys
from app.utils.error_handling import handle_json_view_exception
from app.services.forms.processing_service import _create_dynamic_indicator_object
from app.routes.forms.helpers import existing_data_for_dynamic_assignment, render_dynamic_indicator_item_html
from app.services.organization.authorization_service import AuthorizationService
from app.utils.profile_utils import display_initials_for_user, get_user_profile_color
from app.services.notification.core import log_entity_activity
from markupsafe import escape
from app.utils.discussion_comments import (
    DISCUSSION_SOURCE_UPR_EXCEL,
    discussion_comment_author_label,
    discussion_comment_can_be_managed_by,
    discussion_comment_is_imported,
)

DISCUSSION_COMMENT_MAX_LENGTH = 2000

# Create the API blueprint
# Changed from /forms to /api/forms to avoid prefix conflict with forms.py
bp = Blueprint("forms_api", __name__, url_prefix="/api/forms")


def _presence_rate_limit_key():
    """
    Rate-limit presence endpoints per (user, assignment) when possible.
    Falls back to (ip, assignment) for safety.
    """
    aes_id = None
    try:
        aes_id = (request.view_args or {}).get("aes_id")
    except Exception as e:
        current_app.logger.debug("presence rate limit: aes_id extraction failed: %s", e)
        aes_id = None

    user_id = None
    try:
        user_id = current_user.get_id() if current_user and current_user.is_authenticated else None
    except Exception as e:
        current_app.logger.debug("presence rate limit: user_id extraction failed: %s", e)
        user_id = None

    if user_id:
        return f"presence_u{user_id}_aes{aes_id or 'x'}"
    return f"presence_ip{get_remote_address()}_aes{aes_id or 'x'}"


def _build_presence_users(presence_map, exclude_user_id=None):
    """Build ordered user payload from a presence map; optionally exclude one user."""
    if not presence_map:
        return []

    user_ids = [
        uid for uid in presence_map.keys()
        if exclude_user_id is None or uid != exclude_user_id
    ]
    if not user_ids:
        return []

    users_q = User.query.filter(User.id.in_(user_ids)).all()
    users_by_id = {u.id: u for u in users_q}

    ordered_user_ids = sorted(
        (uid for uid in user_ids if uid in users_by_id),
        key=lambda uid: presence_map[uid],
        reverse=True,
    )

    users = []
    for uid in ordered_user_ids:
        user_obj = users_by_id[uid]
        users.append({
            'id': user_obj.id,
            'name': (user_obj.name or ''),
            'email': (user_obj.email or ''),
            'profile_color': (user_obj.profile_color or '#3B82F6'),
            'last_seen': presence_map[uid].isoformat() if presence_map.get(uid) else None,
        })
    return users


from app.models.assignments import AssignmentEntityStatus
from app.services.forms.processing_service import slugify_age_group


@bp.route('/indicator-bank/search')
@login_required
def api_search_indicator_bank():
    """API endpoint to search the indicator bank for dynamic assignment."""
    try:
        # Get search parameters
        query = request.args.get('q', '').strip()
        sector_filter = request.args.get('sector', '')
        from app.utils.api_pagination import validate_pagination_params
        page, per_page = validate_pagination_params(request.args, default_per_page=20)

        # Base query - only active indicators
        indicators_query = IndicatorBank.query.filter(IndicatorBank.archived == False)

        # Apply search filter
        if query:
            safe_pattern = safe_ilike_pattern(query)
            indicators_query = indicators_query.filter(
                or_(
                    IndicatorBank.name.ilike(safe_pattern),
                    IndicatorBank.definition.ilike(safe_pattern)
                )
            )

        # Apply sector filter
        if sector_filter:
            indicators_query = indicators_query.filter(
                or_(
                    IndicatorBank.sector.like(f'%"{sector_filter}"%'),
                    IndicatorBank.sub_sector.like(f'%"{sector_filter}"%')
                )
            )

        # Paginate results
        pagination = indicators_query.paginate(
            page=page, per_page=per_page, error_out=False
        )

        # Format response
        indicators = []
        for indicator in pagination.items:
            indicators.append({
                'id': indicator.id,
                'name': get_localized_indicator_name(indicator),
                'type': indicator.type,
                'unit': indicator.unit,
                'definition': indicator.definition,
                'sector_display': get_localized_sector_name(indicator.get_sector_by_level('primary')),
                'sub_sector_display': get_localized_subsector_name(indicator.get_subsector_by_level('primary')),
                'emergency': indicator.emergency
            })

        return json_ok(
            indicators=indicators,
            pagination={
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev,
            },
        )

    except Exception as e:
        return handle_json_view_exception(e, 'Failed to search indicators', status_code=500)


@bp.route('/dynamic-indicators/add', methods=['POST'])
@login_required
def api_add_dynamic_indicator():
    """API endpoint to add a dynamic indicator to a section."""
    try:
        # Handle both JSON and form data
        data = get_json_or_form()

        aes_id_raw = data.get('assignment_entity_status_id')
        if not aes_id_raw or not data.get('section_id') or not data.get('indicator_bank_id'):
            return json_bad_request('Missing required fields: assignment_entity_status_id, section_id, indicator_bank_id')

        assignment_entity_status_id = int(aes_id_raw)
        section_id = int(data['section_id'])
        indicator_bank_id = int(data['indicator_bank_id'])
        custom_label = data.get('custom_label', '').strip()
        repeat_instance_number_raw = data.get('repeat_instance_number')
        repeat_instance_number = int(repeat_instance_number_raw) if repeat_instance_number_raw is not None else None

        # Verify the assignment exists and user has access
        access_result = ensure_aes_access(assignment_entity_status_id)
        if 'error' in access_result:
            return json_forbidden(access_result['error'])
        assignment_entity_status = access_result['aes']

        # Verify the section exists and is a dynamic section
        section = FormSection.query.get_or_404(section_id)
        if section.section_type != 'dynamic_indicators':
            return json_bad_request('Section is not a dynamic indicators section')

        # Verify the indicator exists
        indicator = IndicatorBank.query.get_or_404(indicator_bank_id)

        # Check if this indicator is already assigned to this section (and repeat instance)
        existing_assignment = DynamicIndicatorData.query.filter_by(
            assignment_entity_status_id=assignment_entity_status.id,
            section_id=section_id,
            indicator_bank_id=indicator_bank_id,
            repeat_instance_number=repeat_instance_number
        ).first()

        if existing_assignment:
            return json_bad_request('This indicator is already assigned to this section')

        # Get the next order number for this section (and repeat instance)
        max_order = db.session.query(db.func.max(DynamicIndicatorData.order)).filter_by(
            assignment_entity_status_id=assignment_entity_status.id,
            section_id=section_id,
            repeat_instance_number=repeat_instance_number
        ).scalar()

        next_order = 1 if max_order is None else max_order + 1

        # Create the dynamic assignment
        dynamic_assignment = DynamicIndicatorData(
            assignment_entity_status_id=assignment_entity_status.id,
            section_id=section_id,
            indicator_bank_id=indicator_bank_id,
            custom_label=custom_label if custom_label else None,
            order=next_order,
            added_by_user_id=current_user.id,
            repeat_instance_number=repeat_instance_number
        )

        db.session.add(dynamic_assignment)
        db.session.flush()

        # Return the created assignment data
        response_data = {
            'id': dynamic_assignment.id,
            'indicator_bank_id': indicator.id,
            'name': custom_label if custom_label else get_localized_indicator_name(indicator),
            'type': indicator.type,
            'unit': indicator.unit,
            'definition': indicator.definition,
            'custom_label': custom_label,
            'order': dynamic_assignment.order
        }

        return json_ok(assignment=response_data)

    except ValueError as e:
        return json_bad_request('Invalid input data')
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route('/dynamic-indicators/render-pending', methods=['POST'])
@login_required
def api_render_pending_dynamic_indicator():
    """API endpoint to render a pending dynamic indicator without creating DB record."""
    try:
        # Handle both JSON and form data
        data = get_json_or_form()

        aes_id_raw = data.get('assignment_entity_status_id')
        if not aes_id_raw or not data.get('section_id') or not data.get('indicator_bank_id') or not data.get('temp_assignment_id'):
            return json_bad_request('Missing required fields: assignment_entity_status_id, section_id, indicator_bank_id, temp_assignment_id')

        assignment_entity_status_id = int(aes_id_raw)
        section_id = int(data['section_id'])
        indicator_bank_id = int(data['indicator_bank_id'])
        temp_assignment_id = data['temp_assignment_id']
        repeat_instance_number_raw = data.get('repeat_instance_number')
        repeat_instance_number = int(repeat_instance_number_raw) if repeat_instance_number_raw is not None else None

        # Verify the assignment exists and user has access
        access_result = ensure_aes_access(assignment_entity_status_id)
        if 'error' in access_result:
            return json_forbidden(access_result['error'])
        assignment_entity_status = access_result['aes']

        # Optimize: Load section with template relationship to reduce queries
        section = FormSection.query.options(
            joinedload(FormSection.template)
        ).get_or_404(section_id)
        if section.section_type != 'dynamic_indicators':
            return json_bad_request('Section is not a dynamic indicators section')

        # Verify the indicator exists
        indicator = IndicatorBank.query.get_or_404(indicator_bank_id)

        # Quick duplicate check (scoped to repeat instance when applicable)
        existing_assignment = DynamicIndicatorData.query.filter_by(
            assignment_entity_status_id=assignment_entity_status.id,
            section_id=section_id,
            indicator_bank_id=indicator_bank_id,
            repeat_instance_number=repeat_instance_number
        ).first()

        if existing_assignment:
            return json_bad_request('This indicator is already assigned to this section')

        # Create a temporary assignment object (not saved to DB)
        # Use a mock object that mimics DynamicIndicatorData structure
        class TempDynamicAssignment:
            def __init__(self, temp_id, indicator_bank, section_id, assignment_id, repeat_instance_number=None):
                self.id = temp_id  # Temporary ID
                self.dynamic_assignment_id = temp_id  # For template compatibility
                self.indicator_bank_id = indicator_bank.id
                self.indicator_bank = indicator_bank
                self.section_id = section_id
                self.assignment_entity_status_id = assignment_id
                self.repeat_instance_number = repeat_instance_number
                self.custom_label = None
                self.order = 0
                self.value = None
                self.disagg_data = None
                self.data_not_available = False
                self.not_applicable = False

        temp_assignment = TempDynamicAssignment(temp_assignment_id, indicator, section_id, assignment_entity_status.id, repeat_instance_number)
        dynamic_field = _create_dynamic_indicator_object(temp_assignment, section)

        # Optimize template structure lookup - prefer section.template (already loaded)
        template_structure = getattr(section, 'template', None)
        if not template_structure and assignment_entity_status:
            template_structure = getattr(getattr(assignment_entity_status, 'assigned_form', None), 'template', None)
        if not template_structure:
            template_structure = type('TemplateStructure', (), {'display_order_visible': True})()

        html = render_template(
            'forms/entry_form/partials/dynamic_indicator_item.html',
            field=dynamic_field,
            section=section,
            existing_data={},
            template_structure=template_structure,
            config=Config,
            can_edit=True,
            translation_key=get_translation_key(),
            get_localized_indicator_definition=get_localized_indicator_definition,
            get_localized_indicator_type=get_localized_indicator_type,
            get_localized_indicator_unit=get_localized_indicator_unit,
            isinstance=isinstance,
            json=json,
            hasattr=hasattr,
            slugify_age_group=slugify_age_group
        )

        return json_ok(html=html)

    except Exception as e:
        return handle_json_view_exception(e, 'Failed to render indicator', status_code=500)


@bp.route('/dynamic-indicators/<int:assignment_id>/render', methods=['GET'])
@login_required
def api_render_dynamic_indicator(assignment_id):
    """API endpoint to render a dynamic indicator form item."""
    try:
        dynamic_assignment = DynamicIndicatorData.query.get_or_404(assignment_id)

        if not dynamic_assignment.assignment_entity_status_id:
            return json_bad_request('Dynamic indicator rendering requires a valid assignment.')

        access_result = ensure_aes_access(dynamic_assignment.assignment_entity_status_id)
        if 'error' in access_result:
            return json_forbidden(access_result['error'])

        assignment_entity_status = access_result['aes']
        section = FormSection.query.get_or_404(dynamic_assignment.section_id)

        html = render_dynamic_indicator_item_html(
            dynamic_assignment,
            section,
            assignment_entity_status,
        )

        return json_ok(html=html)

    except Exception as e:
        return handle_json_view_exception(e, 'Failed to render indicator', status_code=500)


@bp.route('/dynamic-indicators/<int:assignment_id>/remove', methods=['DELETE'])
@login_required
def api_remove_dynamic_indicator(assignment_id):
    """API endpoint to remove a dynamic indicator assignment."""
    try:
        # Find the assignment
        assignment = DynamicIndicatorData.query.get_or_404(assignment_id)

        # Check user access
        from app.utils.api_serialization import _country_for_aes
        aes_country = _country_for_aes(assignment.assignment_entity_status)
        if not check_country_access(aes_country.id if aes_country else None):
            return json_forbidden('Access denied')

        # Delete the assignment (data is now stored directly in the assignment)
        db.session.delete(assignment)
        db.session.flush()

        return json_ok()

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route('/dynamic-indicators/<int:assignment_id>/update', methods=['PUT'])
@login_required
def api_update_dynamic_indicator(assignment_id):
    """API endpoint to update a dynamic indicator assignment."""
    try:
        # Find the assignment
        assignment = DynamicIndicatorData.query.get_or_404(assignment_id)

        # Check user access
        from app.utils.api_serialization import _country_for_aes
        aes_country = _country_for_aes(assignment.assignment_entity_status)
        if not check_country_access(aes_country.id if aes_country else None):
            return json_forbidden('Access denied')

        # Get update data
        data = get_json_or_form()

        # Update fields
        if 'custom_label' in data:
            assignment.custom_label = data['custom_label'].strip() if data['custom_label'].strip() else None

        if 'order' in data:
            assignment.order = int(data['order'])

        db.session.flush()

        return json_ok()

    except ValueError as e:
        return json_bad_request('Invalid input data')
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route('/repeat-instances/<int:instance_id>/toggle-hide', methods=['PATCH'])
@login_required
def api_toggle_repeat_instance_hide(instance_id):
    """Toggle the is_hidden flag for a repeat group instance."""
    instance = RepeatGroupInstance.query.get_or_404(instance_id)

    # Permission check: ensure current user is part of assignment country status
    if not current_user.is_authenticated:
        return json_forbidden('Not authenticated')

    # Additional checks could be added here for role/access
    try:
        instance.is_hidden = not instance.is_hidden
        db.session.flush()
        if instance.assignment_entity_status_id:
            from app.services.assignments.completion_service import AssignmentCompletionService
            AssignmentCompletionService.refresh_and_persist(instance.assignment_entity_status_id)
        return json_ok(is_hidden=instance.is_hidden)
    except Exception as e:
        return handle_json_view_exception(e, 'Database error', status_code=500)


def _parse_lookup_list_config_from_request():
    """Parse plugin lookup-list config from query args (WAF-safe config_b64 preferred)."""
    config_b64 = request.args.get('config_b64')
    if config_b64:
        try:
            padded = config_b64 + '=' * (-len(config_b64) % 4)
            decoded = base64.b64decode(padded.encode('ascii')).decode('utf-8')
            return json.loads(decoded) if decoded else {}
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return {}

    existing_config_json = request.args.get('config', '{}')
    try:
        return json.loads(existing_config_json) if existing_config_json else {}
    except (json.JSONDecodeError, TypeError):
        return {}


@bp.route('/lookup-lists/<list_id>/config-ui', methods=['GET'])
@login_required
def get_lookup_list_config_ui(list_id):
    """
    Get configuration UI HTML for a plugin lookup list.
    Used by matrix item modal to show plugin-specific configuration options.

    Args:
        list_id: The lookup list ID

    Returns:
        JSON response with success flag and html string
    """
    try:
        # Check if form integration is available
        if not hasattr(current_app, 'form_integration'):
            return json_server_error('Form integration not available')

        # Get plugin lookup lists to find the right plugin
        plugin_lookup_lists = current_app.form_integration.get_plugin_lookup_lists()

        # Find the plugin that provides this lookup list
        for lookup_list_data in plugin_lookup_lists:
            if lookup_list_data['id'] == list_id:
                # Check if plugin provides a config UI handler
                config_ui_handler = lookup_list_data.get('get_config_ui_handler')
                if config_ui_handler and callable(config_ui_handler):
                    existing_config = _parse_lookup_list_config_from_request()

                    # Call the plugin's config UI handler
                    try:
                        html = config_ui_handler(config=existing_config)
                        return json_ok(html=html)
                    except Exception as handler_error:
                        return handle_json_view_exception(handler_error, 'Plugin config UI handler error', status_code=500)

                # No config UI handler for this list
                return json_ok(success=False, html='')

        # Lookup list not found
        return json_not_found('Lookup list not found')

    except Exception as e:
        return handle_json_view_exception(e, 'Failed to get config UI', status_code=500)


def get_plugin_lookup_list_options(list_id, country_iso=None, config=None, **kwargs):
    """
    Get options for plugin lookup lists.
    Routes to the appropriate plugin based on the list_id.

    Args:
        list_id: The lookup list ID
        country_iso: Optional ISO code to filter by country (for country-aware plugins)
        config: Optional configuration dictionary for plugin-specific filtering
        **kwargs: Additional parameters that may be passed to plugin handlers
    """
    try:
        # Check if form integration is available
        if not hasattr(current_app, 'form_integration'):
            current_app.logger.error("Form integration not available")
            return json_server_error('Form integration not available')

        # Get plugin lookup lists to find the right plugin
        plugin_lookup_lists = current_app.form_integration.get_plugin_lookup_lists()

        # Find the plugin that provides this lookup list
        for lookup_list_data in plugin_lookup_lists:
            if lookup_list_data['id'] == list_id:
                # Check if plugin provides a handler function
                handler = lookup_list_data.get('get_options_handler')
                if handler and callable(handler):
                    # Call the plugin's handler function with parameters
                    try:
                        return handler(country_iso=country_iso, config=config, **kwargs)
                    except Exception as handler_error:
                        return handle_json_view_exception(handler_error, 'Plugin handler error', status_code=500)

                # Fallback to legacy routing for plugins without handlers
                return route_to_plugin_lookup_api(list_id, lookup_list_data, country_iso=country_iso)

        current_app.logger.warning(f"Plugin lookup list {list_id} not found")
        return json_not_found('Lookup list not found')

    except Exception as e:
        return handle_json_view_exception(e, 'Failed to fetch plugin lookup list data', status_code=500)


def route_to_plugin_lookup_api(list_id, lookup_list_data, country_iso=None):
    """
    Legacy routing function for plugins that don't provide handler functions.
    This maintains backward compatibility.

    Args:
        list_id: The lookup list ID
        lookup_list_data: Lookup list metadata
        country_iso: Optional ISO code to filter by country (for country-aware plugins)
    """
    try:
        if list_id == 'reporting_currency':
            # Core system list provided by app (not a plugin)
            return get_reporting_currency_options()
        else:
            # For plugins without handlers, log warning
            current_app.logger.warning(f"No handler or routing defined for plugin lookup list: {list_id}")
            return json_error(f'No API available for lookup list {list_id}', 501)

    except Exception as e:
        return handle_json_view_exception(e, 'Failed to route to plugin API', status_code=500)


def _detect_country_context_from_request():
    """Attempt to detect current country context using ACS id, ISO codes or URL.

    Returns a tuple: (country_obj, iso2, iso3)
    """
    try:
        from app.models.core import Country
        from app.models.assignments import AssignmentEntityStatus
        from sqlalchemy import or_

        # 1) Try explicit query params
        aes_id = request.args.get('aes_id', type=int)
        iso = (request.args.get('iso') or request.args.get('country')).strip().upper() if (request.args.get('iso') or request.args.get('country')) else None

        if aes_id:
            aes = AssignmentEntityStatus.query.get(aes_id)
            if aes:
                from app.utils.api_serialization import _country_for_aes
                country = _country_for_aes(aes)
                if country:
                    return country, country.iso2, country.iso3

        if iso:
            country = Country.query.filter(or_(Country.iso3 == iso, Country.iso2 == iso)).first()
            if country:
                return country, country.iso2, country.iso3

        # 2) Try Referer URL for /forms/entry/<aes_id>
        referer = request.headers.get('Referer') or ''
        import re
        m = re.search(r"/forms/entry/(\d+)", referer)
        if m:
            with suppress(Exception):
                aes_id_ref = int(m.group(1))
                aes = AssignmentEntityStatus.query.get(aes_id_ref)
                if aes:
                    from app.utils.api_serialization import _country_for_aes
                    country = _country_for_aes(aes)
                    if country:
                        return country, country.iso2, country.iso3

        return None, None, None
    except Exception as e:
        current_app.logger.debug("country context detection failed: %s", e)
        return None, None, None


def get_reporting_currency_options():
    """Return dynamic reporting currency list: local currency + CHF/EUR/USD.

    Response rows use a single column 'code'.
    """
    try:
        from app.models.core import Country

        country, iso2, iso3 = _detect_country_context_from_request()

        # Determine local currency code from Country.currency_code
        local_currency = None
        if country and getattr(country, 'currency_code', None):
            local_currency = (country.currency_code or '').strip().upper() or None

        # Build rows: local currency (if available) first, then fixed set, deduplicated while preserving order
        ordered_codes = []
        if local_currency:
            ordered_codes.append(local_currency)
        ordered_codes.extend(['CHF', 'EUR', 'USD'])

        seen = set()
        dedup_codes = []
        for c in ordered_codes:
            if c and c not in seen:
                seen.add(c)
                dedup_codes.append(c)

        rows = [{ 'code': c } for c in dedup_codes]

        return json_ok(rows=rows)
    except Exception as e:
        return handle_json_view_exception(e, 'Failed to build reporting currency options', status_code=500)


@bp.route('/lookup-lists/<list_id>/options', methods=['GET'])
@login_required
def get_lookup_list_options(list_id):
    """
    API endpoint to get filtered options for a lookup list.
    Used by calculated lists in forms.

    Query Parameters:
        - filters: JSON string containing filters to apply
        - field_values: JSON string containing current field values for filter evaluation

    Returns:
        JSON response with success flag and rows array
    """
    try:
        current_app.logger.debug(f"Getting options for lookup list {list_id}")

        # Handle system lists (country_map, indicator_bank, national_society)
        if list_id == 'country_map':
            return get_country_map_options()
        elif list_id == 'indicator_bank':
            return get_indicator_bank_options()
        elif list_id == 'national_society':
            return get_national_society_options()

        # Handle plugin lookup lists (non-numeric IDs)
        if not list_id.isdigit():
            # Detect country ISO from request context for country-aware plugins
            # Plugins can use this if they need country filtering
            _, iso2, iso3 = _detect_country_context_from_request()
            country_iso = iso2 or iso3
            return get_plugin_lookup_list_options(list_id, country_iso=country_iso)

        # Convert to int for regular lookup lists
        try:
            list_id_int = int(list_id)
        except ValueError:
            current_app.logger.warning(f"Invalid lookup list ID: {list_id}")
            return json_bad_request('Invalid lookup list ID')

        # Get the lookup list
        lookup_list = LookupList.query.get(list_id_int)
        if not lookup_list:
            current_app.logger.warning(f"Lookup list {list_id_int} not found")
            return json_not_found('Lookup list not found')

        # Parse query parameters
        filters_param = request.args.get('filters', '[]')
        field_values_param = request.args.get('field_values', '{}')

        try:
            filters = json.loads(filters_param) if filters_param else []
            field_values = json.loads(field_values_param) if field_values_param else {}
        except json.JSONDecodeError as e:
            current_app.logger.error(f"Invalid JSON in parameters: {e}")
            return json_bad_request('Invalid JSON in parameters')

        current_app.logger.debug(f"Filters: {filters}")
        current_app.logger.debug(f"Field values: {field_values}")

        # Get all rows for this list
        all_rows = lookup_list.rows.order_by(LookupListRow.order).all()
        current_app.logger.debug(f"Found {len(all_rows)} total rows")

        # Apply filters if any
        filtered_rows = all_rows
        if filters:
            filtered_rows = apply_lookup_list_filters(all_rows, filters, field_values)
            current_app.logger.debug(f"After filtering: {len(filtered_rows)} rows")

        # Convert rows to the format expected by the frontend
        rows_data = []
        for row in filtered_rows:
            # row.data is a JSON object containing the row data
            row_dict = row.data if isinstance(row.data, dict) else {}
            rows_data.append(row_dict)

        current_app.logger.debug(f"Returning {len(rows_data)} rows")

        return json_ok(rows=rows_data)

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


from app.utils.sqlalchemy_grid import build_columns_config as _get_model_columns_config, model_to_dict as _model_to_dict

def get_country_map_options():
    """Get options from Country table for country_map system list"""
    try:
        from flask import session
        from flask_babel import get_locale
        from app.utils.form_localization import get_localized_country_name

        countries = Country.query.order_by(Country.name).all()
        columns_config = _get_model_columns_config(Country)
        rows_data = []

        # Get current locale for localization
        current_locale = get_translation_key()

        for country in countries:
            country_data = _model_to_dict(country, columns_config)
            # Ensure ID is included as both 'id' and '_id' for compatibility
            if 'id' in country_data:
                country_data['_id'] = country_data['id']
            elif hasattr(country, 'id'):
                country_data['id'] = country.id
                country_data['_id'] = country.id
            # Replace 'name' with localized name if available
            if 'name' in country_data:
                localized_name = get_localized_country_name(country)
                country_data['name'] = localized_name
            rows_data.append(country_data)

        return json_ok(rows=rows_data)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


def get_indicator_bank_options():
    """Get options from IndicatorBank table for indicator_bank system list"""
    try:
        indicators = IndicatorBank.query.order_by(IndicatorBank.name).all()
        columns_config = _get_model_columns_config(IndicatorBank)
        rows_data = []
        for indicator in indicators:
            indicator_data = _model_to_dict(indicator, columns_config)
            # Ensure ID is included as both 'id' and '_id' for compatibility
            if 'id' in indicator_data:
                indicator_data['_id'] = indicator_data['id']
            elif hasattr(indicator, 'id'):
                indicator_data['id'] = indicator.id
                indicator_data['_id'] = indicator.id
            rows_data.append(indicator_data)

        return json_ok(rows=rows_data)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


def get_national_society_options():
    """Get options from NationalSociety table for national_society system list"""
    try:
        from flask import session
        from flask_babel import get_locale

        # Eagerly load country relationship to access region field
        national_societies = NationalSociety.query.options(
            joinedload(NationalSociety.country)
        ).order_by(NationalSociety.name).all()
        columns_config = _get_model_columns_config(NationalSociety)
        # Add region field to columns config (will be handled manually)
        rows_data = []

        # Get current locale for localization
        current_locale = get_translation_key()

        for ns in national_societies:
            ns_data = _model_to_dict(ns, columns_config)
            # Ensure ID is included as both 'id' and '_id' for compatibility
            if 'id' in ns_data:
                ns_data['_id'] = ns_data['id']
            elif hasattr(ns, 'id'):
                ns_data['id'] = ns.id
                ns_data['_id'] = ns.id
            # Replace 'name' with localized name if available
            if 'name' in ns_data:
                localized_name = ns.get_name_translation(current_locale)
                if localized_name and localized_name.strip() and localized_name != ns.name:
                    ns_data['name'] = localized_name
                else:
                    ns_data['name'] = ns.name
            # Add region field from related Country
            if ns.country:
                ns_data['region'] = ns.country.region
            else:
                ns_data['region'] = ''
            rows_data.append(ns_data)

        return json_ok(rows=rows_data)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


def apply_lookup_list_filters(rows, filters, context_values=None):
    """
    Apply filters to lookup list rows.

    Args:
        rows: List of LookupListRow objects
        filters: List of filter dictionaries
        context_values: Dictionary of field values for filter evaluation

    Returns:
        List of filtered LookupListRow objects
    """
    if not filters:
        return rows

    filtered_rows = []
    for row in rows:
        if row_matches_filters(row, filters, context_values):
            filtered_rows.append(row)

    return filtered_rows


def row_matches_filters(row, filters, context_values=None):
    """
    Check if a row matches all the given filters.

    Args:
        row: LookupListRow object
        filters: List of filter dictionaries
        context_values: Dictionary of field values for filter evaluation

    Returns:
        bool: True if row matches all filters
    """
    if not filters:
        return True

    context_values = context_values or {}

    for filter_def in filters:
        if not filter_def:
            continue

        # Extract filter components
        field_name = filter_def.get('field')
        operator = filter_def.get('op', 'equals')
        filter_value = filter_def.get('value')
        value_field_id = filter_def.get('value_field_id')

        # If value_field_id is specified, get the value from context
        if value_field_id is not None:
            filter_value = context_values.get(str(value_field_id), '')

        # Get the row's value for this field
        row_data = row.data if isinstance(row.data, dict) else {}
        row_value = row_data.get(field_name, '')

        # Apply the filter operator
        if not evaluate_filter_condition(row_value, operator, filter_value):
            return False

    return True


def evaluate_filter_condition(field_value, operator, filter_value):
    """
    Evaluate a single filter condition.

    Args:
        field_value: Value from the row
        operator: Filter operator (equals, not_equals, contains, etc.)
        filter_value: Value to compare against

    Returns:
        bool: True if condition matches
    """
    # Convert to strings for comparison
    field_str = str(field_value) if field_value is not None else ''
    filter_str = str(filter_value) if filter_value is not None else ''

    # Handle empty values
    field_empty = not field_str.strip()
    filter_empty = not filter_str.strip()

    if operator in ['equals', 'EQUALS']:
        if field_empty and filter_empty:
            return True
        return field_str == filter_str

    elif operator in ['not_equals', 'NOT_EQUALS']:
        if field_empty and filter_empty:
            return False
        return field_str != filter_str

    elif operator in ['contains', 'CONTAINS']:
        if field_empty:
            return False
        return filter_str.lower() in field_str.lower()

    elif operator in ['not_contains', 'NOT_CONTAINS']:
        if field_empty:
            return True
        return filter_str.lower() not in field_str.lower()

    elif operator in ['greater_than', 'GREATER_THAN']:
        try:
            return float(field_str) > float(filter_str)
        except (ValueError, TypeError):
            return False

    elif operator in ['less_than', 'LESS_THAN']:
        try:
            return float(field_str) < float(filter_str)
        except (ValueError, TypeError):
            return False

    elif operator in ['greater_equal', 'GREATER_EQUAL']:
        try:
            return float(field_str) >= float(filter_str)
        except (ValueError, TypeError):
            return False

    elif operator in ['less_equal', 'LESS_EQUAL']:
        try:
            return float(field_str) <= float(filter_str)
        except (ValueError, TypeError):
            return False

    # Default to equals
    return field_str == filter_str


# ===================== Assignment Completion Rate API =====================

@bp.route('/assignment/<int:aes_id>/completion-rate', methods=['GET'])
@login_required
def api_assignment_completion_rate(aes_id):
    """Return the persisted completion rate for a given AssignmentEntityStatus."""
    try:
        if not check_aes_access_light(aes_id):
            return json_forbidden('Assignment not found or access denied')

        aes = db.session.get(AssignmentEntityStatus, aes_id)
        if not aes:
            return json_not_found('Assignment form not found')

        from app.services.assignments.completion_service import AssignmentCompletionService

        completion_rate = AssignmentCompletionService.stored_rate_for(aes)
        response = json_ok(completion_rate=completion_rate)
        response.headers['Cache-Control'] = 'private, max-age=30'
        return response
    except Exception as e:
        return handle_json_view_exception(e, 'Failed to compute completion rate', status_code=500)


@bp.route('/assignment/<int:aes_id>/completion-gaps', methods=['GET'])
@login_required
def api_assignment_completion_gaps(aes_id):
    """Return form items that count toward completion rate but are not yet filled."""
    try:
        if not check_aes_access_light(aes_id):
            return json_forbidden('Assignment not found or access denied')

        row = db.session.execute(
            select(FormTemplate.id, FormTemplate.published_version_id)
            .join(AssignedForm, AssignedForm.template_id == FormTemplate.id)
            .join(
                AssignmentEntityStatus,
                AssignmentEntityStatus.assigned_form_id == AssignedForm.id,
            )
            .where(AssignmentEntityStatus.id == aes_id)
        ).first()
        if not row:
            return json_not_found('Assignment form not found')

        template_id, published_version_id = row
        if not published_version_id:
            return json_ok(
                completion_rate=0.0,
                total_items=0,
                missing_count=0,
                missing_items=[],
                section_ids=[],
            )

        from flask import current_app

        from app.services.assignments.completion_service import AssignmentCompletionService

        hidden_field_ids = parse_csv_id_set(request.args.get('hidden_fields'))
        hidden_section_ids = parse_csv_id_set(request.args.get('hidden_sections'))
        include_debug = (
            request.args.get('debug') == '1'
            or current_app.config.get('DEBUG', False)
        )
        aes = db.session.get(AssignmentEntityStatus, aes_id)
        completion_rate = (
            AssignmentCompletionService.stored_rate_for(aes) if aes else 0.0
        )
        metrics = AssignmentCompletionService.compute_for_assignment(
            aes_id,
            template_id,
            published_version_id,
        )
        missing = AssignmentCompletionService.list_missing_items(
            aes_id,
            template_id,
            published_version_id,
            hidden_field_ids=hidden_field_ids,
            hidden_section_ids=hidden_section_ids,
            include_debug=include_debug,
        )
        missing_payload = [item.as_dict(include_debug=include_debug) for item in missing]
        section_ids = sorted({item.section_id for item in missing})
        if include_debug:
            for item in missing:
                if item.item_type == 'matrix':
                    current_app.logger.info(
                        'completion-gap matrix form_item_id=%s label=%r fill_hint=%s debug=%s',
                        item.form_item_id,
                        item.label,
                        item.fill_hint,
                        item.fill_debug,
                    )
        response = json_ok(
            completion_rate=completion_rate,
            total_items=metrics.total_items,
            missing_count=len(missing_payload),
            missing_items=missing_payload,
            section_ids=section_ids,
            matrix_rule='one_cell_enough',
        )
        response.headers['Cache-Control'] = 'private, max-age=15'
        return response
    except Exception as e:
        return handle_json_view_exception(e, 'Failed to compute completion gaps', status_code=500)


def _matrix_uses_auto_load(matrix_item):
    """Cheap config-only check (no DB/service calls) for whether a matrix FormItem
    is configured for auto-load. Lets callers skip the heavier per-matrix resolution
    work entirely when no matrix on the template actually needs it."""
    cfg = matrix_item.config if isinstance(matrix_item.config, dict) else {}
    mc = cfg.get('matrix_config') if isinstance(cfg.get('matrix_config'), dict) else cfg
    return bool(mc and mc.get('auto_load_entities') and mc.get('row_mode') == 'list_library')


def _entry_bootstrap_matrix_candidates(aes, matrix_item, variable_configs, assignment_level_resolved):
    """Collect auto-load entity candidates for one matrix FormItem (or None if unused).

    Forward-lookup ("same"/"any"/"specific") entities are already tick-filtered
    server-side by `_resolve_auto_load_entities_inner`. Reverse-lookup
    ("entities_containing") entities still need a tick-column check, but that check
    is deferred to the caller: this returns `tick_var_names` (non-empty only when a
    reverse tick filter is still needed) instead of resolving it here, so
    `api_assignment_entry_bootstrap` can run ONE batch `resolve_variables_batch` across
    every matrix's candidates plus already-saved rows instead of one batch call per matrix.

    `assignment_level_resolved` is the assignment-level `resolve_variables` result,
    computed once by the caller and shared across all matrices (previously each matrix
    with a reverse variable re-computed this independently).
    """
    from app.routes.api.assignments import _resolve_auto_load_entities_inner
    from app.services.forms.variable_resolution_service import VariableResolutionService

    cfg = matrix_item.config if isinstance(matrix_item.config, dict) else {}
    mc = cfg.get('matrix_config') if isinstance(cfg.get('matrix_config'), dict) else cfg
    if not mc or not mc.get('auto_load_entities'):
        return None
    if mc.get('row_mode') != 'list_library':
        return None

    columns = mc.get('columns') or []
    variable_columns = [c for c in columns if isinstance(c, dict) and c.get('is_variable')]
    if not variable_columns or not variable_configs:
        return None

    tick_column_names = []
    tick_var_names_all = []
    for col in variable_columns:
        if (col.get('type') or col.get('column_type') or '').lower() != 'tick':
            continue
        vname = col.get('variable') or col.get('variable_name')
        vcfg = variable_configs.get(vname) if vname else None
        if isinstance(vcfg, dict) and vcfg.get('matrix_column_name'):
            tick_column_names.append(vcfg['matrix_column_name'])
        else:
            tick_column_names.append(col.get('name') or '')
        if vname:
            tick_var_names_all.append(vname)

    entity_map = {}
    entity_type = None
    has_reverse = False

    for col in variable_columns:
        vname = col.get('variable') or col.get('variable_name')
        if not vname:
            continue
        vcfg = variable_configs.get(vname)
        if not isinstance(vcfg, dict):
            continue
        scope = (vcfg.get('entity_scope') or 'same').strip()
        if scope == 'entities_containing':
            has_reverse = True
            continue

        source_template_id = vcfg.get('source_template_id')
        source_period = vcfg.get('source_assignment_period')
        source_form_item_id = vcfg.get('source_form_item_id')
        if not source_template_id or not source_period or not source_form_item_id:
            continue

        effective_period = VariableResolutionService._resolve_effective_period(
            source_period, source_template_id, aes
        ) or source_period

        result = _resolve_auto_load_entities_inner(
            aes.entity_id,
            aes.entity_type,
            int(source_template_id),
            effective_period,
            int(source_form_item_id),
            require_tick_value_1=bool(tick_column_names),
            tick_column_names=tick_column_names,
            assignment_entity_status_id=aes.id,
        )
        if result.get('entity_type') and not entity_type:
            entity_type = result['entity_type']
        for ent in result.get('entities') or []:
            eid = ent.get('entity_id') if isinstance(ent, dict) else None
            etype = (ent.get('entity_type') if isinstance(ent, dict) else None) or entity_type
            if eid is not None and etype:
                entity_map[int(eid)] = {'entity_id': int(eid), 'entity_type': etype}

    tick_var_names = []
    if has_reverse and assignment_level_resolved is not None:
        # Reverse lookup: parse auto_load_format JSON blobs from the (already computed,
        # shared) assignment-level resolve instead of resolving again per matrix.
        for col in variable_columns:
            vname = col.get('variable') or col.get('variable_name')
            vcfg = variable_configs.get(vname) if vname else None
            if not isinstance(vcfg, dict):
                continue
            if (vcfg.get('entity_scope') or '').strip() != 'entities_containing':
                continue
            raw = assignment_level_resolved.get(vname)
            if not raw:
                continue
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(parsed, dict) or not isinstance(parsed.get('entities'), list):
                continue
            if parsed.get('entity_type') and not entity_type:
                entity_type = parsed['entity_type']
            for ent in parsed['entities']:
                if not isinstance(ent, dict):
                    continue
                eid = ent.get('entity_id', ent.get('id'))
                etype = ent.get('entity_type') or parsed.get('entity_type') or entity_type
                if eid is not None and etype:
                    entity_map[int(eid)] = {'entity_id': int(eid), 'entity_type': etype}

        if entity_map and tick_var_names_all:
            tick_var_names = tick_var_names_all

    return {
        'entity_map': entity_map,
        'entity_type': entity_type,
        'tick_var_names': tick_var_names,
    }


@bp.route('/assignment/<int:aes_id>/entry-bootstrap', methods=['GET'])
@login_required
def api_assignment_entry_bootstrap(aes_id):
    """One-shot bootstrap for the entry form: completion rate + initial matrix auto-load
    + variable resolve for known row entity ids.

    Replaces separate load-time calls to completion-rate, auto-load-entities/batch, and
    variables/resolve when the published template actually needs them. Interactive flows
    (adding rows later) continue to use the individual endpoints.
    """
    try:
        if not check_aes_access_light(aes_id):
            return json_forbidden('Assignment not found or access denied')

        row = db.session.execute(
            select(
                AssignmentEntityStatus,
                FormTemplate.id,
                FormTemplate.published_version_id,
            )
            .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
            .join(FormTemplate, AssignedForm.template_id == FormTemplate.id)
            .where(AssignmentEntityStatus.id == aes_id)
        ).first()
        if not row:
            return json_not_found('Assignment form not found')

        aes, template_id, published_version_id = row
        if not published_version_id:
            return json_ok(completion_rate=0.0, auto_load={}, resolved_variables={})

        from app.services.assignments.completion_service import AssignmentCompletionService
        from app.services.forms.variable_resolution_service import VariableResolutionService

        completion_rate = AssignmentCompletionService.stored_rate_for(aes)

        template_version = FormTemplateVersion.query.get(published_version_id)
        variable_configs = (template_version.variables if template_version else None) or {}

        matrices = FormItem.query.filter_by(
            template_id=template_id,
            version_id=published_version_id,
            item_type='matrix',
            archived=False,
        ).all()
        # Cheap config-only filter — skips all per-matrix resolution work below
        # (including the assignment-level resolve it would otherwise trigger for
        # reverse-lookup columns) when no matrix on this template uses auto-load.
        auto_load_matrices = [item for item in matrices if _matrix_uses_auto_load(item)]

        resolved_variables = {}
        assignment_level_resolved = None
        if template_version and variable_configs:
            try:
                # Computed once and shared: used for resolved_variables[''] below AND
                # passed into every matrix's candidate collection so reverse-lookup
                # ("entities_containing") columns don't each re-resolve it.
                assignment_level_resolved = VariableResolutionService.resolve_variables(
                    template_version, aes
                )
                resolved_variables[''] = assignment_level_resolved or {}
                resolved_variables['assignment'] = assignment_level_resolved or {}
            except Exception as e:
                current_app.logger.debug('entry-bootstrap assignment resolve failed: %s', e)

        auto_load = {}
        pending_tick_filters = []  # [(form_item_id_str, candidates), ...]
        row_entity_ids = set()

        for item in auto_load_matrices:
            try:
                candidates = _entry_bootstrap_matrix_candidates(
                    aes, item, variable_configs, assignment_level_resolved
                )
            except Exception as e:
                current_app.logger.debug(
                    'entry-bootstrap auto_load skipped for form_item %s: %s', item.id, e
                )
                candidates = None
            if not candidates:
                continue
            if candidates['tick_var_names']:
                # Needs a reverse+tick filter — deferred to the single batch resolve below.
                pending_tick_filters.append((str(item.id), candidates))
            else:
                auto_load[str(item.id)] = {
                    'entities': list(candidates['entity_map'].values()),
                    'entity_type': candidates['entity_type'],
                }
            row_entity_ids.update(candidates['entity_map'].keys())

        # Also include already-saved matrix row entity ids for variable resolve.
        matrix_ids = [item.id for item in matrices]
        if matrix_ids:
            fd_rows = FormData.query.filter(
                FormData.assignment_entity_status_id == aes_id,
                FormData.form_item_id.in_(matrix_ids),
            ).all()
            for entry in fd_rows:
                dd = entry.disagg_data or {}
                for key in dd:
                    if key == '_table' or '_' not in str(key):
                        continue
                    try:
                        row_entity_ids.add(int(str(key).split('_')[0]))
                    except (ValueError, TypeError):
                        pass

        # ONE batch resolve covers both the reverse+tick auto-load filter and
        # resolved_variables for already-saved rows (previously: one batch call per
        # reverse-lookup matrix, plus a second, separate assignment-wide batch call).
        batch = {}
        if template_version and row_entity_ids:
            try:
                batch = VariableResolutionService.resolve_variables_batch(
                    template_version, aes, list(row_entity_ids)
                ) or {}
            except Exception as e:
                current_app.logger.debug('entry-bootstrap batch resolve failed: %s', e)

        for rid, vals in batch.items():
            resolved_variables[str(rid)] = vals

        for item_id_str, candidates in pending_tick_filters:
            filtered = {}
            for eid, ent in candidates['entity_map'].items():
                vals = batch.get(eid) or batch.get(int(eid)) or {}
                if any(vals.get(vn) in (1, '1', True) for vn in candidates['tick_var_names']):
                    filtered[eid] = ent
            auto_load[item_id_str] = {
                'entities': list(filtered.values()),
                'entity_type': candidates['entity_type'],
            }

        response = json_ok(
            completion_rate=completion_rate,
            auto_load=auto_load,
            resolved_variables=resolved_variables,
        )
        response.headers['Cache-Control'] = 'private, max-age=30'
        return response
    except Exception as e:
        return handle_json_view_exception(e, 'Failed to build entry bootstrap', status_code=500)


# ===================== Presence (Live Users) APIs =====================

@bp.route('/presence/assignment/<int:aes_id>/sync', methods=['POST'])
@login_required
@limiter.limit("30 per minute", key_func=_presence_rate_limit_key, override_defaults=True)
def api_presence_sync(aes_id):
    """Record presence and return other active editors in one request."""
    try:
        if not check_aes_access_light(aes_id):
            return json_forbidden('Assignment not found or access denied')

        record_presence(aes_id=aes_id, user_id=current_user.id)
        presence_map = get_active_presence(aes_id=aes_id)
        users = _build_presence_users(presence_map, exclude_user_id=current_user.id)
        return json_ok(users=users)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route('/presence/assignment/<int:aes_id>/leave', methods=['POST'])
@login_required
@csrf.exempt  # sendBeacon cannot set X-CSRFToken; only removes caller's own presence
def api_presence_leave(aes_id):
    """Remove the current user's presence immediately (tab close / navigation)."""
    try:
        # Silently ignore requests for assignments the user can't access; the
        # presence record for this user+aes pair simply won't exist in that case.
        if check_aes_access_light(aes_id):
            remove_presence(aes_id=aes_id, user_id=current_user.id)
    except Exception as e:
        current_app.logger.debug("presence leave failed for aes=%s user=%s: %s", aes_id, current_user.id, e)
    return json_ok()


# DEPRECATED: use /sync — kept for one release cycle.
@bp.route('/presence/assignment/<int:aes_id>/heartbeat', methods=['POST'])
@login_required
@limiter.limit("30 per minute", key_func=_presence_rate_limit_key, override_defaults=True)
def api_presence_heartbeat(aes_id):
    """Record a presence heartbeat for the current user on this assignment."""
    try:
        # Verify access to assignment
        access_result = ensure_aes_access(aes_id)
        if 'error' in access_result:
            return json_forbidden(access_result['error'])

        record_presence(aes_id=aes_id, user_id=current_user.id)

        return json_ok()
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


# DEPRECATED: use /sync — kept for one release cycle.
@bp.route('/presence/assignment/<int:aes_id>/active-users', methods=['GET'])
@login_required
@limiter.limit("30 per minute", key_func=_presence_rate_limit_key, override_defaults=True)
def api_presence_active_users(aes_id):
    """Return users active in this assignment in the last PRESENCE_TTL_SECONDS."""
    try:
        # Verify access to assignment
        access_result = ensure_aes_access(aes_id)
        if 'error' in access_result:
            return json_forbidden(access_result['error'])

        presence_map = get_active_presence(aes_id=aes_id)
        users = _build_presence_users(presence_map)
        return json_ok(users=users)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


# ===================== Discussion Comments APIs =====================

def _discussion_comment_mutation_context(comment_id):
    """Load a comment and verify the current user may edit/delete it."""
    comment = SubmissionDiscussionComment.query.get(comment_id)
    if not comment:
        return None, json_not_found('Comment not found')

    aes_id = comment.assignment_entity_status_id
    if not aes_id:
        return None, json_forbidden('Cannot modify this comment')

    access_result = ensure_aes_access(aes_id)
    if 'error' in access_result:
        return None, json_forbidden(access_result['error'])

    aes = access_result['aes']
    if not AuthorizationService.can_edit_assignment(aes, current_user):
        return None, json_forbidden('Cannot modify comments on this assignment')

    if not discussion_comment_can_be_managed_by(comment, current_user):
        return None, json_forbidden('Can only modify your own comments')

    return {'comment': comment, 'aes': aes}, None


def _serialize_discussion_comment(comment):
    from flask_babel import gettext as _
    user = comment.created_by_user
    author_label = discussion_comment_author_label(comment, gettext_fn=_)
    author_payload = None
    if user:
        author_payload = {
            'id': user.id,
            'name': user.name or user.email,
            'email': user.email or '',
            'title': user.title or '',
            'profile_color': get_user_profile_color(user),
            'initials': display_initials_for_user(user),
        }
    return {
        'id': comment.id,
        'body': comment.body,
        'created_at': comment.created_at.isoformat() if comment.created_at else None,
        'source': comment.source,
        'is_imported': discussion_comment_is_imported(comment),
        'author_label': author_label,
        'author': author_payload,
        'created_by_user_id': comment.created_by_user_id,
    }


@bp.route('/discussion/comments', methods=['GET'])
@login_required
def api_get_discussion_comments():
    """List discussion comments for an assignment entity status."""
    try:
        aes_id = request.args.get('assignment_entity_status_id', type=int)
        if not aes_id:
            return json_bad_request('Missing assignment_entity_status_id')

        access_result = ensure_aes_access(aes_id)
        if 'error' in access_result:
            return json_forbidden(access_result['error'])

        comments = (
            SubmissionDiscussionComment.query
            .filter_by(assignment_entity_status_id=aes_id)
            .order_by(SubmissionDiscussionComment.created_at.asc())
            .all()
        )
        return json_ok(comments=[_serialize_discussion_comment(c) for c in comments])
    except Exception as e:
        return handle_json_view_exception(e, 'Failed to load discussion comments', status_code=500)


@bp.route('/discussion/comments', methods=['POST'])
@login_required
def api_add_discussion_comment():
    """Append a discussion comment to an assignment entity status."""
    try:
        data = get_json_or_form()
        aes_id_raw = data.get('assignment_entity_status_id')
        if not aes_id_raw:
            return json_bad_request('Missing assignment_entity_status_id')

        aes_id = int(aes_id_raw)
        access_result = ensure_aes_access(aes_id)
        if 'error' in access_result:
            return json_forbidden(access_result['error'])

        aes = access_result['aes']
        if not AuthorizationService.can_edit_assignment(aes, current_user):
            return json_forbidden('Cannot add comment to this assignment')

        body = (data.get('body') or '').strip()
        if not body:
            return json_bad_request('Comment body is required')
        if len(body) > DISCUSSION_COMMENT_MAX_LENGTH:
            return json_bad_request(f'Comment exceeds maximum length of {DISCUSSION_COMMENT_MAX_LENGTH} characters')

        comment = SubmissionDiscussionComment(
            assignment_entity_status_id=aes_id,
            body=escape(body),
            created_by_user_id=current_user.id,
            created_at=utcnow(),
        )
        db.session.add(comment)
        db.session.flush()

        author_name = current_user.name or current_user.email
        log_entity_activity(
            aes.entity_type,
            aes.entity_id,
            'discussion_comment_added',
            f'Comment added by {author_name}',
            summary_key='activity.discussion_comment_added',
            summary_params={'user': author_name},
            related_object_type='submission_discussion_comment',
            related_object_id=comment.id,
            assignment_id=aes.id,
            user_id=current_user.id,
        )
        db.session.commit()
        return json_ok(comment=_serialize_discussion_comment(comment))
    except Exception as e:
        db.session.rollback()
        return handle_json_view_exception(e, 'Failed to add discussion comment', status_code=500)


@bp.route('/discussion/comments/<int:comment_id>', methods=['PATCH'])
@login_required
def api_update_discussion_comment(comment_id):
    """Update the current user's own discussion comment."""
    try:
        ctx, error_response = _discussion_comment_mutation_context(comment_id)
        if error_response is not None:
            return error_response

        comment = ctx['comment']
        aes = ctx['aes']
        data = get_json_or_form()
        body = (data.get('body') or '').strip()
        if not body:
            return json_bad_request('Comment body is required')
        if len(body) > DISCUSSION_COMMENT_MAX_LENGTH:
            return json_bad_request(
                f'Comment exceeds maximum length of {DISCUSSION_COMMENT_MAX_LENGTH} characters'
            )

        comment.body = escape(body)
        db.session.flush()

        author_name = current_user.name or current_user.email
        log_entity_activity(
            aes.entity_type,
            aes.entity_id,
            'discussion_comment_edited',
            f'Comment edited by {author_name}',
            summary_key='activity.discussion_comment_edited',
            summary_params={'user': author_name},
            related_object_type='submission_discussion_comment',
            related_object_id=comment.id,
            assignment_id=aes.id,
            user_id=current_user.id,
        )
        db.session.commit()
        return json_ok(comment=_serialize_discussion_comment(comment))
    except Exception as e:
        db.session.rollback()
        return handle_json_view_exception(e, 'Failed to update discussion comment', status_code=500)


@bp.route('/discussion/comments/<int:comment_id>', methods=['DELETE'])
@login_required
def api_delete_discussion_comment(comment_id):
    """Delete the current user's own discussion comment."""
    try:
        ctx, error_response = _discussion_comment_mutation_context(comment_id)
        if error_response is not None:
            return error_response

        comment = ctx['comment']
        aes = ctx['aes']
        deleted_id = comment.id
        db.session.delete(comment)
        db.session.flush()

        author_name = current_user.name or current_user.email
        log_entity_activity(
            aes.entity_type,
            aes.entity_id,
            'discussion_comment_deleted',
            f'Comment deleted by {author_name}',
            summary_key='activity.discussion_comment_deleted',
            summary_params={'user': author_name},
            related_object_type='submission_discussion_comment',
            related_object_id=deleted_id,
            assignment_id=aes.id,
            user_id=current_user.id,
        )
        db.session.commit()
        return json_ok(deleted_id=deleted_id)
    except Exception as e:
        db.session.rollback()
        return handle_json_view_exception(e, 'Failed to delete discussion comment', status_code=500)
