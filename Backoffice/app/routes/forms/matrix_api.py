"""Matrix table row search API for forms."""
from __future__ import annotations

from contextlib import suppress
import re

from flask import current_app, request, session
from flask_login import login_required
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from app import get_locale
from app.models import Country, LookupList, LookupListRow
from app.utils.api_helpers import get_json_safe
from app.utils.api_responses import json_bad_request, json_not_found, json_ok, json_server_error, require_json_keys
from app.utils.constants import DEFAULT_LOOKUP_ROW_LIMIT
from app.utils.form_localization import get_localized_country_name
from app.utils.request_validation import enforce_csrf_json
from app.utils.sql_utils import safe_ilike_pattern


def register_matrix_api_routes(bp):
    """Register matrix API routes onto the forms blueprint."""

    @bp.route('/matrix/search-rows', methods=['POST'])
    @login_required
    def search_matrix_rows():
        """
        API endpoint to search for rows in a list library for advanced matrix tables.
        This endpoint is for internal frontend use and requires user session authentication.

        Request Body:
            - lookup_list_id: ID of the lookup list to search
            - display_column: Column to use for row labels
            - filters: List of filters to apply (optional)
            - search_term: Search term to filter results (optional)
            - existing_rows: List of already selected row labels (optional)

        Returns:
            JSON object containing:
            - success: Boolean indicating success
            - options: List of available options with value and description
        """
        try:
            csrf_error = enforce_csrf_json()
            if csrf_error is not None:
                return csrf_error

            data = get_json_safe()
            err = require_json_keys(data, ['lookup_list_id', 'display_column'])
            if err:
                return err

            lookup_list_id = data.get('lookup_list_id')
            display_column = data.get('display_column')
            if not lookup_list_id or not display_column:
                return json_bad_request('lookup_list_id and display_column are required')
            filters = data.get('filters', [])
            search_term = data.get('search_term', '').strip()
            existing_rows = data.get('existing_rows', [])
            limit = data.get('limit', 500)
            plugin_config = data.get('plugin_config', {})

            def _row_matches_filters(row_data):
                """Check if a row dict matches all provided filters."""
                if not filters:
                    return True
                if not isinstance(row_data, dict):
                    return False
                for filter_item in filters:
                    column = filter_item.get('column')
                    operator = filter_item.get('operator', 'equals')
                    value = filter_item.get('value')

                    if column is None or value is None:
                        return False
                    if column not in row_data:
                        return False

                    row_value = str(row_data[column]).strip().lower()
                    filter_value = str(value).strip().lower()

                    if operator == 'equals' and row_value != filter_value:
                        return False
                    if operator == 'not_equals' and row_value == filter_value:
                        return False
                    if operator == 'contains' and filter_value not in row_value:
                        return False
                    if operator == 'not_contains' and filter_value in row_value:
                        return False
                return True

            def _build_options_from_rows(rows_data):
                """Convert normalized rows_data into matrix search options."""
                if not isinstance(rows_data, list):
                    return []

                filtered_rows = []
                for row_data in rows_data:
                    if _row_matches_filters(row_data):
                        filtered_rows.append(row_data)

                options_local = []
                for row_data in filtered_rows:
                    if not isinstance(row_data, dict):
                        continue

                    if display_column not in row_data:
                        continue

                    row_value = str(row_data[display_column]).strip()
                    if not row_value or row_value in existing_rows:
                        continue

                    if search_term and search_term.lower() not in row_value.lower():
                        continue

                    description = None
                    for desc_field in ['description', 'desc', 'details', 'notes']:
                        if desc_field in row_data and row_data[desc_field]:
                            description = str(row_data[desc_field])
                            break

                    row_id = row_data.get('_id') or row_data.get('id')

                    if not row_id:
                        current_app.logger.warning(
                            f"Matrix search option missing ID - row_value: {row_value}, row_data: {row_data}"
                        )

                    if row_id and (not row_data.get('_id') or not row_data.get('id')):
                        row_data['_id'] = row_id
                        row_data['id'] = row_id

                    options_local.append({
                        'value': row_value,
                        'description': description,
                        'data': row_data,
                        'id': row_id
                    })
                return options_local

            def _detect_country_iso_from_matrix_context():
                """Detect country ISO from matrix search request context."""
                try:
                    from app.models.assignments import AssignmentEntityStatus

                    assignment_entity_status_id = data.get('assignment_entity_status_id')
                    if assignment_entity_status_id:
                        with suppress((ValueError, TypeError)):
                            aes = AssignmentEntityStatus.query.get(int(assignment_entity_status_id))
                            if aes and aes.country:
                                return aes.country.iso2 or aes.country.iso3

                    referer = request.headers.get('Referer') or ''
                    m = re.search(r"/forms/(?:assignment|entry)/(\d+)", referer)
                    if m:
                        with suppress((ValueError, TypeError)):
                            aes_id = int(m.group(1))
                            aes = AssignmentEntityStatus.query.get(aes_id)
                            if aes and aes.country:
                                return aes.country.iso2 or aes.country.iso3

                    iso = request.args.get('iso') or request.args.get('country')
                    if iso:
                        iso = iso.strip().upper()
                        country = Country.query.filter(or_(Country.iso3 == iso, Country.iso2 == iso)).first()
                        if country:
                            return country.iso2 or country.iso3

                    return None
                except Exception as e:
                    current_app.logger.debug("_detect_country_iso_from_matrix_context failed: %s", e)
                    return None

            def _fetch_plugin_lookup_rows(list_id, config=None):
                """Reuse forms_api lookup endpoint logic for plugin/system lists."""
                try:
                    from app.routes.forms_api import get_plugin_lookup_list_options

                    country_iso = None
                    if list_id == 'emergency_operations':
                        country_iso = _detect_country_iso_from_matrix_context()

                    plugin_response = get_plugin_lookup_list_options(list_id, country_iso=country_iso, config=config)

                    if isinstance(plugin_response, tuple):
                        response_obj, status_code = plugin_response[0], plugin_response[1] if len(plugin_response) > 1 else 200
                    else:
                        response_obj = plugin_response
                        status_code = getattr(plugin_response, 'status_code', 200)

                    if status_code != 200:
                        return None, plugin_response
                    payload = response_obj.get_json(silent=True) or {}
                    rows = payload.get('rows') or payload.get('options') or []
                    if not isinstance(rows, list):
                        rows = []
                    return rows, None
                except Exception as plugin_exc:
                    current_app.logger.error(
                        f"Error loading lookup list {list_id} for matrix search: {plugin_exc}",
                        exc_info=True
                    )
                    err_resp, _ = json_server_error('Failed to load lookup list options', success=False)
                    return None, err_resp

            is_system_list = not str(lookup_list_id).isdigit()

            if is_system_list:
                rows_data = []
                plugin_response = None

                if lookup_list_id in ('country_map', 'national_society', 'indicator_bank'):
                    from app.models.organization import NationalSociety
                    from app.models.indicator_bank import IndicatorBank
                    from app.utils.sqlalchemy_grid import build_columns_config as _get_model_columns_config, model_to_dict as _model_to_dict

                    current_locale = session.get('language', 'en')
                    if not current_locale:
                        current_locale = str(get_locale()) if get_locale() else 'en'

                    if lookup_list_id == 'country_map':
                        model_class = Country
                        query_results = model_class.query.order_by(model_class.name).all()
                    elif lookup_list_id == 'national_society':
                        model_class = NationalSociety
                        query_results = model_class.query.options(
                            joinedload(NationalSociety.country)
                        ).order_by(model_class.name).all()
                    else:
                        model_class = IndicatorBank
                        query_results = model_class.query.order_by(model_class.name).all()

                    columns_config = _get_model_columns_config(model_class)

                    for instance in query_results:
                        row_data = _model_to_dict(instance, columns_config)

                        if hasattr(instance, 'id'):
                            row_data['id'] = instance.id
                            row_data['_id'] = instance.id
                        elif 'id' in row_data:
                            row_data['_id'] = row_data['id']

                        if lookup_list_id == 'national_society' and hasattr(instance, 'country') and instance.country:
                            row_data['region'] = instance.country.region

                        if display_column == 'name':
                            if lookup_list_id == 'country_map':
                                row_data['name'] = get_localized_country_name(instance)
                            elif lookup_list_id == 'national_society':
                                localized_name = instance.get_name_translation(current_locale)
                                row_data['name'] = localized_name if localized_name and localized_name.strip() else instance.name

                        rows_data.append(row_data)
                else:
                    rows_data, plugin_response = _fetch_plugin_lookup_rows(lookup_list_id, config=plugin_config)
                    if plugin_response:
                        return plugin_response

                options = _build_options_from_rows(rows_data)
            else:
                lookup_list = LookupList.query.get(int(lookup_list_id))
                if not lookup_list:
                    return json_not_found('Lookup list not found')

                query = lookup_list.rows.order_by(LookupListRow.order)

                if filters:
                    for filter_item in filters:
                        column = filter_item.get('column')
                        operator = filter_item.get('operator', 'equals')
                        value = filter_item.get('value')

                        if not column or not value:
                            continue

                        if operator == 'equals':
                            query = query.filter(LookupListRow.data[column].astext == value)
                        elif operator == 'not_equals':
                            query = query.filter(LookupListRow.data[column].astext != value)
                        elif operator == 'contains':
                            query = query.filter(LookupListRow.data[column].astext.ilike(safe_ilike_pattern(value)))
                        elif operator == 'not_contains':
                            query = query.filter(~LookupListRow.data[column].astext.ilike(safe_ilike_pattern(value)))

                rows = query.all()

                options = []
                for row in rows:
                    if row.data and display_column in row.data:
                        row_value = str(row.data[display_column]).strip()

                        if not row_value or row_value in existing_rows:
                            continue

                        if search_term and search_term.lower() not in row_value.lower():
                            continue

                        description = None
                        for desc_field in ['description', 'desc', 'details', 'notes']:
                            if desc_field in row.data and row.data[desc_field]:
                                description = str(row.data[desc_field])
                                break

                        row_id = row.id if hasattr(row, 'id') else None
                        row_data = row.data if isinstance(row.data, dict) else {}
                        if row_id is not None:
                            row_data['_id'] = row_id

                        options.append({
                            'value': row_value,
                            'description': description,
                            'data': row_data,
                            'id': row_id
                        })

            options.sort(key=lambda x: x['value'].lower())

            try:
                limit = int(limit)
                if limit < 1:
                    limit = DEFAULT_LOOKUP_ROW_LIMIT
            except (ValueError, TypeError):
                limit = DEFAULT_LOOKUP_ROW_LIMIT

            if len(options) > limit:
                options = options[:limit]

            return json_ok(success=True, options=options, total=len(options))

        except Exception as e:
            current_app.logger.error(f"Error searching matrix rows: {e}", exc_info=True)
            return json_server_error('Could not search rows')
