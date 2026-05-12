from contextlib import suppress
# ========== Forms API Blueprint ==========
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
from app.extensions import limiter
from app.models import (
    db, IndicatorBank, DynamicIndicatorData,
    FormSection, RepeatGroupInstance, LookupList, LookupListRow,
    User, Country, NationalSociety, Config
)
from app.utils.form_localization import (
    get_localized_indicator_name, get_localized_sector_name, get_localized_subsector_name,
    get_localized_indicator_definition, get_localized_indicator_type, get_localized_indicator_unit,
    get_translation_key
)
from sqlalchemy import or_, inspect
from sqlalchemy.orm import joinedload
from datetime import datetime
import re
import json
from app.services.presence_store import get_active_presence, record_presence
from app.services import check_country_access, ensure_aes_access
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.request_utils import get_json_or_form, is_json_request
from app.utils.api_responses import json_bad_request, json_error, json_forbidden, json_not_found, json_ok, json_server_error, require_json_keys
from app.utils.error_handling import handle_json_view_exception
from app.services.form_processing_service import _create_dynamic_indicator_object

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


from app.services.form_processing_service import slugify_age_group


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

        # Check if this indicator is already assigned to this section
        existing_assignment = DynamicIndicatorData.query.filter_by(
            assignment_entity_status_id=assignment_entity_status.id,
            section_id=section_id,
            indicator_bank_id=indicator_bank_id
        ).first()

        if existing_assignment:
            return json_bad_request('This indicator is already assigned to this section')

        # Get the next order number for this section
        max_order = db.session.query(db.func.max(DynamicIndicatorData.order)).filter_by(
            assignment_entity_status_id=assignment_entity_status.id,
            section_id=section_id
        ).scalar()

        next_order = 1 if max_order is None else max_order + 1

        # Create the dynamic assignment
        dynamic_assignment = DynamicIndicatorData(
            assignment_entity_status_id=assignment_entity_status.id,
            section_id=section_id,
            indicator_bank_id=indicator_bank_id,
            custom_label=custom_label if custom_label else None,
            order=next_order,  # Use the next sequential order number
            added_by_user_id=current_user.id  # Add the current user ID
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

        # Quick duplicate check (frontend also checks, but verify server-side for security)
        existing_assignment = DynamicIndicatorData.query.filter_by(
            assignment_entity_status_id=assignment_entity_status.id,
            section_id=section_id,
            indicator_bank_id=indicator_bank_id
        ).first()

        if existing_assignment:
            return json_bad_request('This indicator is already assigned to this section')

        # Create a temporary assignment object (not saved to DB)
        # Use a mock object that mimics DynamicIndicatorData structure
        class TempDynamicAssignment:
            def __init__(self, temp_id, indicator_bank, section_id, assignment_id):
                self.id = temp_id  # Temporary ID
                self.dynamic_assignment_id = temp_id  # For template compatibility
                self.indicator_bank_id = indicator_bank.id
                self.indicator_bank = indicator_bank
                self.section_id = section_id
                self.assignment_entity_status_id = assignment_id
                self.custom_label = None
                self.order = 0
                self.value = None
                self.disagg_data = None
                self.data_not_available = False
                self.not_applicable = False

        temp_assignment = TempDynamicAssignment(temp_assignment_id, indicator, section_id, assignment_entity_status.id)
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
            hasattr=hasattr
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
        dynamic_field = _create_dynamic_indicator_object(dynamic_assignment, section)

        template_structure = None
        if assignment_entity_status and getattr(assignment_entity_status, 'assigned_form', None):
            template_structure = assignment_entity_status.assigned_form.template
        if not template_structure and getattr(section, 'template', None):
            template_structure = section.template
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
            hasattr=hasattr
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
        if not check_country_access(assignment.assignment_entity_status.country.id):
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
        if not check_country_access(assignment.assignment_entity_status.country.id):
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
        return json_ok(is_hidden=instance.is_hidden)
    except Exception as e:
        return handle_json_view_exception(e, 'Database error', status_code=500)


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
                    # Get existing config from query parameter if provided
                    existing_config_json = request.args.get('config', '{}')
                    try:
                        existing_config = json.loads(existing_config_json) if existing_config_json else {}
                    except (json.JSONDecodeError, TypeError):
                        existing_config = {}

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
            if aes and aes.country:
                return aes.country, aes.country.iso2, aes.country.iso3

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
                if aes and aes.country:
                    return aes.country, aes.country.iso2, aes.country.iso3

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


# ===================== Presence (Live Users) APIs =====================

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
        aes = access_result['aes']

        # Keep live presence out of user_activity_log; store in cache/memory.
        record_presence(aes_id=aes_id, user_id=current_user.id, ttl_seconds=75)

        return json_ok()
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route('/presence/assignment/<int:aes_id>/active-users', methods=['GET'])
@login_required
@limiter.limit("30 per minute", key_func=_presence_rate_limit_key, override_defaults=True)
def api_presence_active_users(aes_id):
    """Return users active in this assignment in the last 75 seconds."""
    try:
        # Verify access to assignment
        access_result = ensure_aes_access(aes_id)
        if 'error' in access_result:
            return json_forbidden(access_result['error'])
        aes = access_result['aes']

        presence_map = get_active_presence(aes_id=aes_id, ttl_seconds=75)
        if not presence_map:
            return json_ok(users=[])

        user_ids = list(presence_map.keys())
        users_q = User.query.filter(User.id.in_(user_ids)).all()
        users_by_id = {u.id: u for u in users_q}

        # Order by most recent heartbeat first.
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
                'profile_color': (user_obj.profile_color or '#3B82F6'),
                'last_seen': presence_map[uid].isoformat() if presence_map.get(uid) else None,
            })

        return json_ok(users=users)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)
