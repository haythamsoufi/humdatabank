# Backoffice/app/routes/api/data.py
"""
Data API endpoints.
Part of the /api/v1 blueprint.
"""

from flask import request, current_app
from sqlalchemy import desc, literal, or_
import uuid
from contextlib import suppress
from typing import Any, Dict, Optional

# Import the API blueprint from parent
from app.routes.api import api_bp

# Import models
from app.models import FormData, PublicSubmission, Country, FormItem, FormTemplate, FormTemplateVersion
from app.models.assignments import AssignmentEntityStatus
from app.utils.auth import require_api_key
from app.utils.rate_limiting import api_rate_limit
from app import db

# Import utility functions
from app.utils.api_helpers import json_response, api_error, extract_numeric_value
from app.utils.api_serialization import format_country_info, format_form_item_info
from app.utils.api_authentication import authenticate_api_request, get_user_allowed_template_ids, apply_user_template_scoping
from app.utils.api_pagination import (
    parse_date_range, get_sort_params, validate_data_endpoint_params,
    build_pagination_queries, get_paginated_data_ids, fetch_paginated_rows,
    build_paginated_response
)
from app.utils.form_localization import get_translation_key
from app.utils.api_formatting import format_answer_value, format_form_data_response, serialize_form_data_item
from app.utils.sql_utils import safe_ilike_pattern
from app.services import query_form_data, get_form_data_queries, TemplateService
from app.services.data_retrieval_shared import (
    get_effective_request_user,
    can_view_non_public_form_items,
    form_item_privacy_is_public_expr,
)


def _normalize_disagg_payload(disagg_data):
    """
    Normalize disagg_data for API response so the frontend always receives
    { mode, values }. Matrix data is stored as a flat dict (e.g. {"10_SP2": 4107000});
    age/sex disaggregation uses nested { "mode": "...", "values": { ... } }.
    """
    if not isinstance(disagg_data, dict):
        return {'mode': None, 'values': {}}
    if 'values' in disagg_data:
        return {
            'mode': disagg_data.get('mode'),
            'values': disagg_data.get('values') or {}
        }
    # Flat matrix format: use the whole dict as values, exclude reserved keys
    values = {k: v for k, v in disagg_data.items() if not k.startswith('_')}
    return {'mode': 'matrix', 'values': values}


def _resolve_matrix_entity_labels(form_item_id_to_prefix_ids, form_items_orm_list):
    """
    Resolve matrix row prefixes (entity IDs) to display names using each form item's
    matrix config (lookup_list_id / row_mode). Returns dict: form_item_id -> { prefix: display_name }.
    """
    result = {}
    if not form_item_id_to_prefix_ids or not form_items_orm_list:
        return result

    form_items_by_id = {fi.id: fi for fi in form_items_orm_list if fi}
    current_locale = get_translation_key()

    for form_item_id, prefix_ids in form_item_id_to_prefix_ids.items():
        form_item = form_items_by_id.get(form_item_id)
        if not form_item or getattr(form_item, 'item_type', None) != 'matrix':
            continue
        config = getattr(form_item, 'config', None) or {}
        matrix_config = config.get('matrix_config') if isinstance(config, dict) else config
        if not isinstance(matrix_config, dict):
            continue
        row_mode = (matrix_config.get('row_mode') or '').strip().lower()
        if row_mode != 'list_library':
            continue
        lookup_list_id = (matrix_config.get('lookup_list_id') or matrix_config.get('_table') or '').strip()
        display_column = (matrix_config.get('list_display_column') or matrix_config.get('display_column') or 'name').strip() or 'name'
        labels = _resolve_entity_ids_for_lookup(lookup_list_id, display_column, prefix_ids, current_locale)
        if labels:
            result[form_item_id] = labels
    return result


def _resolve_entity_ids_for_lookup(lookup_list_id, display_column, prefix_ids, current_locale='en'):
    """Resolve a set of prefix IDs (row entity IDs) to display names for a given lookup_list_id."""
    labels = {}
    prefix_ids = set(prefix_ids)
    if not prefix_ids or not lookup_list_id:
        return labels

    if lookup_list_id == 'national_society':
        from app.models.organization import NationalSociety
        for rid in prefix_ids:
            try:
                rid_int = int(rid)
            except (TypeError, ValueError):
                labels[str(rid)] = str(rid)
                continue
            obj = NationalSociety.query.get(rid_int)
            if obj:
                name = None
                get_tr = getattr(obj, 'get_name_translation', None)
                if get_tr and callable(get_tr):
                    try:
                        tr = get_tr(current_locale)
                        if isinstance(tr, str) and tr.strip():
                            name = tr.strip()
                    except Exception as e:
                        current_app.logger.debug("get_name_translation failed for national_society %s: %s", rid, e)
                labels[str(rid)] = name or getattr(obj, 'name', None) or str(rid)
            else:
                labels[str(rid)] = str(rid)
        return labels

    if lookup_list_id == 'country_map':
        from app.models.core import Country
        from app.utils.form_localization import get_localized_country_name
        for rid in prefix_ids:
            try:
                rid_int = int(rid)
            except (TypeError, ValueError):
                labels[str(rid)] = str(rid)
                continue
            obj = Country.query.get(rid_int)
            labels[str(rid)] = get_localized_country_name(obj) if obj else str(rid)
        return labels

    if lookup_list_id == 'indicator_bank':
        from app.models.indicator_bank import IndicatorBank
        for rid in prefix_ids:
            try:
                rid_int = int(rid)
            except (TypeError, ValueError):
                labels[str(rid)] = str(rid)
                continue
            obj = IndicatorBank.query.get(rid_int)
            labels[str(rid)] = obj.name if obj else str(rid)
        return labels

    if str(lookup_list_id).isdigit():
        from app.models import LookupListRow
        for rid in prefix_ids:
            try:
                rid_int = int(rid)
            except (TypeError, ValueError):
                labels[str(rid)] = str(rid)
                continue
            row_obj = LookupListRow.query.get(rid_int)
            if row_obj and isinstance(getattr(row_obj, 'data', None), dict):
                data = row_obj.data
                name = data.get(display_column) or data.get('name') or str(rid)
                labels[str(rid)] = str(name)
            else:
                labels[str(rid)] = str(rid)
        return labels

    return labels


@api_bp.route('/templates/<int:template_id>/data', methods=['GET'])
@require_api_key
def get_data_by_template(template_id):
    """
    API endpoint to retrieve form data submitted for a specific template.
    """
    template = TemplateService.get_by_id(template_id)
    if not template:
        return api_error('Template not found', 404)

    queries = query_form_data(template_id=template_id, preload=True)
    assigned_form_data_query, public_form_data_query = get_form_data_queries(queries)

    # Optional DB-level pagination using centralized helpers
    page = request.args.get('page', type=int)
    per_page = request.args.get('per_page', type=int)

    if page and per_page:
        # Build pagination queries using helper
        assigned_ids_q, public_ids_q = build_pagination_queries(
            assigned_form_data_query,
            public_form_data_query,
            submission_type=None  # Include both types
        )

        # Get paginated data IDs
        page_rows, total_items = get_paginated_data_ids(
            assigned_ids_q,
            public_ids_q,
            page,
            per_page,
            paginate=True,
            sort_field='submitted_at',
            sort_order='desc'
        )

        # Fetch full ORM rows
        assigned_map, public_map = fetch_paginated_rows(
            assigned_form_data_query,
            public_form_data_query,
            page_rows
        )

        # Serialize data using centralized helper
        paginated_data = []
        for r in page_rows:
            data_item = assigned_map.get(r.id) if r.submission_type == 'assigned' else public_map.get(r.id)
            if not data_item:
                continue
            paginated_data.append(serialize_form_data_item(data_item, r.submission_type))

        return json_response(build_paginated_response(paginated_data, total_items, page, per_page))

    return api_error("page and per_page query parameters are required", 400)


@api_bp.route('/countries/<int:country_id>/data', methods=['GET'])
@require_api_key
def get_data_by_country(country_id):
    """
    API endpoint to retrieve form data submitted for a specific country.
    """
    from app.services import CountryService
    country = CountryService.get_by_id(country_id)
    if not country:
        return api_error('Country not found', 404)

    queries = query_form_data(country_id=country_id, preload=True)
    assigned_form_data_query, public_form_data_query = get_form_data_queries(queries)

    # Optional DB-level pagination using centralized helpers
    page = request.args.get('page', type=int)
    per_page = request.args.get('per_page', type=int)

    if page and per_page:
        # Build pagination queries using helper
        assigned_ids_q, public_ids_q = build_pagination_queries(
            assigned_form_data_query,
            public_form_data_query,
            submission_type=None  # Include both types
        )

        # Get paginated data IDs
        page_rows, total_items = get_paginated_data_ids(
            assigned_ids_q,
            public_ids_q,
            page,
            per_page,
            paginate=True,
            sort_field='submitted_at',
            sort_order='desc'
        )

        # Fetch full ORM rows
        assigned_map, public_map = fetch_paginated_rows(
            assigned_form_data_query,
            public_form_data_query,
            page_rows
        )

        # Serialize data using centralized helper
        paginated_data = []
        for r in page_rows:
            data_item = assigned_map.get(r.id) if r.submission_type == 'assigned' else public_map.get(r.id)
            if not data_item:
                continue
            paginated_data.append(serialize_form_data_item(data_item, r.submission_type))

        return json_response(build_paginated_response(paginated_data, total_items, page, per_page))

    return api_error("page and per_page query parameters are required", 400)


@api_bp.route('/data', methods=['GET'])
@api_rate_limit()
def get_all_data():
    """
    API endpoint to retrieve form data with optional filtering.
    Authentication (one of):
      - Authorization: Bearer YOUR_API_KEY (full access, paginated response)
      - HTTP Basic auth or session (user-scoped access, no pagination)
    Query Parameters:
        - template_id: Filter by template ID
        - submission_id: Filter by submission ID
        - item_id: Filter by form item ID
        - item_type: Filter by item type ('indicator', 'question', 'document_field')
        - country_id: Filter by country ID
        - submission_type: Filter by submission type ('assigned' or 'public')
        - period_name: Filter by period name (e.g., FY2023, Q1 2024)
        - indicator_bank_id: Filter by indicator bank ID
        - disagg: Include disaggregation data (true/false)
        - include_full_info: Include detailed form item info (true/false, default: false for performance)
        - page: Page number (default: 1, only used with API key auth)
        - per_page: Items per page (default: 20, max 100000, only used with API key auth)

    Response format:
        - API key auth: Returns paginated response with total_pages, current_page, per_page
        - User auth: Returns all accessible data with total_pages=None, current_page=None, per_page=None
    """
    try:
        # Authenticate request
        auth_result = authenticate_api_request()
        # Check if it's an error response (has status_code attribute)
        if hasattr(auth_result, 'status_code'):
            return auth_result  # Return error response
        elevated_access, auth_user, api_key_record = auth_result

        # Get and validate query parameters
        # SECURITY: All parameters are validated to prevent injection and DoS attacks
        try:
            template_id = request.args.get('template_id', type=int)
            if template_id is not None and template_id < 1:
                template_id = None
        except (ValueError, TypeError):
            template_id = None

        try:
            submission_id = request.args.get('submission_id', type=int)
            if submission_id is not None and submission_id < 1:
                submission_id = None
        except (ValueError, TypeError):
            submission_id = None

        try:
            item_id = request.args.get('item_id', type=int)
            if item_id is not None and item_id < 1:
                item_id = None
        except (ValueError, TypeError):
            item_id = None

        # Validate item_type against whitelist
        item_type = request.args.get('item_type', type=str)
        if item_type:
            item_type = item_type.strip().lower()
            valid_item_types = ['indicator', 'question', 'document_field']
            if item_type not in valid_item_types:
                item_type = None

        try:
            country_id = request.args.get('country_id', type=int)
            if country_id is not None and country_id < 1:
                country_id = None
        except (ValueError, TypeError):
            country_id = None

        # Validate ISO codes (alphanumeric, max 3 chars)
        country_iso2 = request.args.get('country_iso2', type=str)
        if country_iso2:
            country_iso2 = country_iso2.strip().upper()[:2]
            if not country_iso2.isalpha():
                country_iso2 = None

        country_iso3 = request.args.get('country_iso3', type=str)
        if country_iso3:
            country_iso3 = country_iso3.strip().upper()[:3]
            if not country_iso3.isalpha():
                country_iso3 = None

        # Validate submission_type against whitelist
        submission_type = request.args.get('submission_type')
        if submission_type:
            submission_type = submission_type.strip().lower()
            if submission_type not in ['assigned', 'public']:
                submission_type = None

        # Validate period_name (sanitize length)
        period_name = request.args.get('period_name', type=str)
        if period_name:
            period_name = period_name.strip()[:100]  # Limit length
            if not period_name:
                period_name = None

        try:
            indicator_bank_id = request.args.get('indicator_bank_id', type=int)
            if indicator_bank_id is not None and indicator_bank_id < 1:
                indicator_bank_id = None
        except (ValueError, TypeError):
            indicator_bank_id = None

        # Parse date range filtering
        date_from, date_to = parse_date_range(request.args)

        # Parse sorting parameters
        sort_field, sort_order, _ = get_sort_params(request.args)

        # Resolve iso2/iso3 to country_id if provided (do this BEFORE building queries)
        if (country_iso2 or country_iso3) and not country_id:
            from app.utils.country_utils import resolve_country_from_iso
            resolved_id, error = resolve_country_from_iso(iso2=country_iso2, iso3=country_iso3)
            if error:
                # Determine status code based on error type
                status_code = 400 if 'Invalid' in error else 404
                return api_error(error, status_code)
            if resolved_id:
                country_id = resolved_id

        # Build queries via service layer for consistency
        queries = query_form_data(
            template_id=template_id,
            submission_id=submission_id,
            item_id=item_id,
            item_type=item_type,
            country_id=country_id,
            period_name=period_name,
            indicator_bank_id=indicator_bank_id,
            submission_type=submission_type,
            preload=True,
        )
        assigned_form_data_query, public_form_data_query = get_form_data_queries(queries)

        # Apply date range filtering
        if date_from:
            # Ensure joins exist for assigned query
            if assigned_form_data_query is not None:
                # Check if joins already exist
                if template_id is None and country_id is None and period_name is None:
                    assigned_form_data_query = assigned_form_data_query.join(AssignmentEntityStatus)
                assigned_form_data_query = assigned_form_data_query.filter(FormData.submitted_at >= date_from)

            # Public query already has joins
            if public_form_data_query is not None:
                public_form_data_query = public_form_data_query.filter(FormData.submitted_at >= date_from)

        if date_to:
            # Ensure joins exist for assigned query
            if assigned_form_data_query is not None:
                # Check if joins already exist
                if template_id is None and country_id is None and period_name is None and date_from is None:
                    assigned_form_data_query = assigned_form_data_query.join(AssignmentEntityStatus)
                assigned_form_data_query = assigned_form_data_query.filter(FormData.submitted_at <= date_to)

            # Public query already has joins
            if public_form_data_query is not None:
                public_form_data_query = public_form_data_query.filter(FormData.submitted_at <= date_to)

        # Determine if we should paginate based on authentication type
        # API key auth → paginated, User auth → no pagination (return all accessible data)
        should_paginate = elevated_access

        # Validate and sanitize parameters
        if should_paginate:
            # API key auth: use pagination parameters
            validated_params = validate_data_endpoint_params(request.args)
            page = validated_params['page']
            per_page = validated_params['per_page']
            include_disagg = validated_params['include_disagg']
            include_full_info = validated_params['include_full_info']
        else:
            # User auth: no pagination, but still validate disagg and full_info parameters
            disagg_param = request.args.get('disagg', default=None, type=str)
            include_disagg = False
            if disagg_param is not None:
                include_disagg = str(disagg_param).strip().lower() in ['1', 'true', 'yes', 'y']
            full_info_param = request.args.get('include_full_info', default=None, type=str)
            include_full_info = False
            if full_info_param is not None:
                include_full_info = str(full_info_param).strip().lower() in ['1', 'true', 'yes', 'y']
            # Set defaults for user auth (not used but needed for response structure)
            page = 1
            per_page = None

        # ---------- RBAC: if user-authenticated, restrict to templates the user owns or that are shared with them ----------
        if not elevated_access and auth_user is not None:
            # System managers have access to all templates
            from app.services.authorization_service import AuthorizationService
            is_system_mgr = AuthorizationService.is_system_manager(auth_user)

            # Check if specific template is requested and user has access
            if template_id is not None and not is_system_mgr:
                allowed_template_ids = get_user_allowed_template_ids(auth_user.id)
                if template_id not in allowed_template_ids:
                    return api_error('Forbidden: no access to requested template', 403)

            # Apply template scoping to queries
            scoped_queries = apply_user_template_scoping(queries, auth_user, template_id, country_id, period_name)
            assigned_form_data_query, public_form_data_query = get_form_data_queries(scoped_queries)

            # If user has no access, return empty result
            if assigned_form_data_query is not None:
                # Check if query is empty (1=0 filter)
                with suppress(Exception):
                    test_count = assigned_form_data_query.limit(1).count()
                    if test_count == 0 and (public_form_data_query is None or public_form_data_query.limit(1).count() == 0):
                        return json_response({
                            'data': [],
                            'total_items': 0,
                            'total_pages': 0 if should_paginate else None,
                            'current_page': page if should_paginate else None,
                            'per_page': per_page if should_paginate else None
                        })

        # (Filters already applied by the service and optional RBAC scoping)

        # Build pagination queries using helper
        assigned_ids_q, public_ids_q = build_pagination_queries(
            assigned_form_data_query,
            public_form_data_query,
            submission_type
        )

        # Get data IDs (paginated for API key, all for user auth) with sorting
        page_rows, total_items = get_paginated_data_ids(
            assigned_ids_q,
            public_ids_q,
            page if should_paginate else 1,
            per_page if should_paginate else None,
            paginate=should_paginate,
            sort_field=sort_field,
            sort_order=sort_order
        )

        # Fetch full ORM rows for the current page
        assigned_map, public_map = fetch_paginated_rows(
            assigned_form_data_query,
            public_form_data_query,
            page_rows
        )

        # Use minimal country info for large datasets to avoid N+1 queries
        # Threshold: use minimal info when per_page > 1000 or when returning all data (user auth)
        use_minimal_country_info = (per_page and per_page > 1000) or (not should_paginate)

        # Serialize in the exact DB order using helper functions
        from app.utils.api_serialization import serialize_assigned_data_item, serialize_public_data_item
        paginated_data = []
        for row in page_rows:
            if row.submission_type == 'assigned':
                data_item = assigned_map.get(row.id)
                if not data_item:
                    continue
                item_payload = serialize_assigned_data_item(
                    data_item,
                    include_disagg=include_disagg,
                    include_full_info=include_full_info,
                    minimal_country_info=use_minimal_country_info
                )
                paginated_data.append(item_payload)
            else:
                data_item = public_map.get(row.id)
                if not data_item:
                    continue
                item_payload = serialize_public_data_item(
                    data_item,
                    include_disagg=include_disagg,
                    include_full_info=include_full_info,
                    minimal_country_info=use_minimal_country_info
                )
                paginated_data.append(item_payload)

        # Build response based on authentication type
        if should_paginate:
            # API key auth: return paginated response
            total_pages = (total_items + per_page - 1) // per_page if per_page > 0 else 1
            return json_response({
                'data': paginated_data,
                'total_items': total_items,
                'total_pages': total_pages,
                'current_page': page,
                'per_page': per_page
            })
        else:
            # User auth: return all accessible data (no pagination)
            return json_response({
                'data': paginated_data,
                'total_items': total_items,
                'total_pages': None,
                'current_page': None,
                'per_page': None
            })

    except Exception as e:
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            f"API Error [ID: {error_id}] fetching all data: {e}",
            exc_info=True,
            extra={'endpoint': '/data', 'params': dict(request.args)}
        )
        return api_error("Could not fetch data", 500, error_id, None)


@api_bp.route('/data/tables', methods=['GET'])
def get_data_tables():
    """
    API endpoint to retrieve data rows along with related form item and country tables.
    Authentication (one of):
      - Authorization: Bearer YOUR_API_KEY (full access, paginated response)
      - HTTP Basic auth or session (user-scoped access, no pagination)
    Query Parameters:
        - template_id, submission_id, item_id, item_type, country_id, submission_type, period_name, indicator_bank_id: filters
        - disagg: include disaggregation data (true/false)
        - date_from: Filter by submission date from (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
        - date_to: Filter by submission date to (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
        - sort: Sort field (default: 'submitted_at', options: 'submitted_at', 'template_id', 'country_id', 'period_name')
        - order: Sort order (default: 'desc', options: 'asc', 'desc')
        - page, per_page: pagination for data rows (only used with API key auth)
        - related: scope of related tables ('page' or 'all'); default 'page'.
                   'page' returns form_items and countries referenced by the current page of data.
                   'all' returns form_items and countries for the full filtered dataset (not paginated).
    """
    try:
        # Authenticate request
        auth_result = authenticate_api_request()
        # Check if it's an error response (has status_code attribute)
        if hasattr(auth_result, 'status_code'):
            return auth_result  # Return error response
        elevated_access, auth_user, api_key_record = auth_result

        template_id = request.args.get('template_id', type=int)
        submission_id = request.args.get('submission_id', type=int)
        item_id = request.args.get('item_id', type=int)
        item_type = request.args.get('item_type', type=str)
        country_id = request.args.get('country_id', type=int)
        submission_type = request.args.get('submission_type')
        period_name = request.args.get('period_name', type=str)
        indicator_bank_id = request.args.get('indicator_bank_id', type=int)
        include_non_reported = str(request.args.get('include_non_reported', '') or '').strip().lower() in ['1', 'true', 'yes', 'y']

        def _is_blankish_scalar(v: Any) -> bool:
            """
            Treat None/empty/"null" (string) as blank for reporting purposes.
            This is important for legacy/imported rows where FormData.value was saved as the literal string "null".
            """
            if v is None:
                return True
            if isinstance(v, str):
                s = v.strip()
                return (s == "") or (s.lower() == "null")
            return False

        def _normalize_disagg_raw(d: Any) -> Optional[Dict[str, Any]]:
            """
            Normalize disagg_data into a dict when it contains meaningful values.
            Returns None for None/empty/"null"/invalid structures.
            """
            if d is None:
                return None
            if isinstance(d, str):
                s = d.strip()
                if (s == "") or (s.lower() == "null"):
                    return None
                # Unexpected string payload; treat as missing rather than erroring downstream.
                return None
            if not isinstance(d, dict):
                return None
            if len(d) == 0:
                return None
            values = d.get('values') if isinstance(d.get('values'), dict) else None
            if values is not None:
                has_any = False
                for vv in values.values():
                    if vv is None:
                        continue
                    if isinstance(vv, str) and vv.strip().lower() in ("", "null"):
                        continue
                    has_any = True
                    break
                if not has_any:
                    return None
            return d

        def _has_saved_imputed_value(v: Any) -> bool:
            if v is None:
                return False
            if isinstance(v, str):
                s = v.strip()
                return (s != "") and (s.lower() != "null")
            if isinstance(v, (list, dict)):
                return len(v) > 0
            return True

        def _has_any_aux_value(item: Any) -> bool:
            """
            Return True if an item has any non-reported (prefilled/imputed) value/disagg payload.
            Used to decide whether to include rows when include_non_reported=false.
            """
            try:
                if _has_saved_imputed_value(getattr(item, "prefilled_value", None)):
                    return True
                if _has_saved_imputed_value(getattr(item, "imputed_value", None)):
                    return True
                if _normalize_disagg_raw(getattr(item, "prefilled_disagg_data", None)) is not None:
                    return True
                if _normalize_disagg_raw(getattr(item, "imputed_disagg_data", None)) is not None:
                    return True
            except Exception as e:
                current_app.logger.debug("_has_saved_imputed_value check failed: %s", e)
                return False
            return False

        # Parse date range filtering
        date_from, date_to = parse_date_range(request.args)

        # Parse sorting parameters
        sort_field, sort_order, _ = get_sort_params(request.args)

        # Determine if we should paginate based on authentication type
        # API key auth → paginated, User auth → no pagination (return all accessible data)
        should_paginate = elevated_access

        # Validate and sanitize parameters
        if should_paginate:
            # API key auth: use pagination parameters
            validated_params = validate_data_endpoint_params(request.args)
            page = validated_params['page']
            per_page = validated_params['per_page']
            include_disagg = validated_params['include_disagg']
        else:
            # User auth: no pagination, but still validate disagg parameter
            disagg_param = request.args.get('disagg', default=None, type=str)
            include_disagg = False
            if disagg_param is not None:
                include_disagg = str(disagg_param).strip().lower() in ['1', 'true', 'yes', 'y']
            # Set defaults for user auth (not used but needed for response structure)
            page = 1
            per_page = None

        related_scope = str(request.args.get('related', 'page')).strip().lower()
        if related_scope not in ('page', 'all'):
            related_scope = 'page'

        # ---------- Scope to published template version (avoid multi-version duplicates) ----------
        # Templates can have multiple versions; FormItem.template_id is denormalized and can include items
        # from multiple versions. If we filter FormData by template_id only, we can inadvertently include
        # rows for items from draft/older versions, which appear as "duplicates" in the UI.
        published_version_id = None
        if template_id is not None:
            try:
                tmpl = db.session.get(FormTemplate, int(template_id))
                if tmpl and getattr(tmpl, "published_version_id", None):
                    published_version_id = int(tmpl.published_version_id)
                elif tmpl:
                    pass
            except Exception as e:
                current_app.logger.debug("published_version_id resolution failed: %s", e)
                published_version_id = None

        # Build queries via service layer for consistency
        queries = query_form_data(
            template_id=template_id,
            submission_id=submission_id,
            item_id=item_id,
            item_type=item_type,
            country_id=country_id,
            period_name=period_name,
            indicator_bank_id=indicator_bank_id,
            submission_type=submission_type,
            preload=True,
        )
        assigned_form_data_query, public_form_data_query = get_form_data_queries(queries)

        # Apply version scoping to both assigned/public queries.
        # Use .has() to avoid adding extra joins (keeps query shapes stable).
        if template_id is not None and published_version_id:
            try:
                assigned_form_data_query = assigned_form_data_query.filter(
                    FormData.form_item.has(FormItem.version_id == int(published_version_id))
                )
                public_form_data_query = public_form_data_query.filter(
                    FormData.form_item.has(FormItem.version_id == int(published_version_id))
                )
            except Exception as e:
                current_app.logger.warning("published_version scoping failed in /data/tables: %s", e, exc_info=True)

        # Apply date range filtering
        if date_from:
            # Ensure joins exist for assigned query
            # Note: queries are now guaranteed to be non-None by get_form_data_queries
            # Check if joins already exist
            if template_id is None and country_id is None and period_name is None:
                assigned_form_data_query = assigned_form_data_query.join(AssignmentEntityStatus)
            assigned_form_data_query = assigned_form_data_query.filter(FormData.submitted_at >= date_from)

            # Public query already has joins
            public_form_data_query = public_form_data_query.filter(FormData.submitted_at >= date_from)

        if date_to:
            # Ensure joins exist for assigned query
            # Check if joins already exist
            if template_id is None and country_id is None and period_name is None and date_from is None:
                assigned_form_data_query = assigned_form_data_query.join(AssignmentEntityStatus)
            assigned_form_data_query = assigned_form_data_query.filter(FormData.submitted_at <= date_to)

            # Public query already has joins
            public_form_data_query = public_form_data_query.filter(FormData.submitted_at <= date_to)

        # ---------- RBAC: if user-authenticated, restrict to templates the user owns or that are shared with them ----------
        if not elevated_access and auth_user is not None:
            # System managers have access to all templates
            from app.services.authorization_service import AuthorizationService
            is_system_mgr = AuthorizationService.is_system_manager(auth_user)

            # Check if specific template is requested and user has access
            if template_id is not None and not is_system_mgr:
                allowed_template_ids = get_user_allowed_template_ids(auth_user.id)
                if template_id not in allowed_template_ids:
                    return api_error('Forbidden: no access to requested template', 403)

            # Apply template scoping to queries
            scoped_queries = apply_user_template_scoping(queries, auth_user, template_id, country_id, period_name)
            assigned_form_data_query, public_form_data_query = get_form_data_queries(scoped_queries)

            # If user has no access, return empty result.
            # IMPORTANT: Do NOT short-circuit when include_non_reported=1 for a bounded assigned scope,
            # because the caller may want virtual "missing" rows even when there are zero saved FormData rows.
            if assigned_form_data_query is not None:
                with suppress(Exception):
                    test_count = assigned_form_data_query.limit(1).count()
                    if test_count == 0 and (public_form_data_query is None or public_form_data_query.limit(1).count() == 0):
                        bounded_missing_request = (
                            include_non_reported
                            and (not should_paginate)
                            and template_id is not None
                            and country_id is not None
                            and period_name
                            and str(submission_type or '').strip().lower() == 'assigned'
                        )
                        if not bounded_missing_request:
                            return json_response({
                                'data': [],
                                'form_items': [],
                                'countries': [],
                                'total_items': 0,
                                'total_pages': None,
                                'current_page': None,
                                'per_page': None
                            })

        if submission_type == 'assigned' and public_form_data_query is not None:
            public_form_data_query = public_form_data_query.filter(literal(False))
        elif submission_type == 'public' and assigned_form_data_query is not None:
            assigned_form_data_query = assigned_form_data_query.filter(literal(False))

        # Build pagination queries using helper
        assigned_ids_q, public_ids_q = build_pagination_queries(
            assigned_form_data_query,
            public_form_data_query,
            submission_type
        )

        # Get data IDs (paginated for API key, all for user auth) with sorting
        page_rows, total_items = get_paginated_data_ids(
            assigned_ids_q,
            public_ids_q,
            page if should_paginate else 1,
            per_page if should_paginate else None,
            paginate=should_paginate,
            sort_field=sort_field,
            sort_order=sort_order
        )

        # Fetch full ORM rows using helper
        # Note: query_form_data already applies eager loading when preload=True,
        # so we don't need to add more in fetch_paginated_rows
        assigned_map, public_map = fetch_paginated_rows(
            assigned_form_data_query,
            public_form_data_query,
            page_rows
        )

        # Initialize data_rows early to ensure it's always defined
        data_rows = []
        form_item_ids = set()
        country_ids = set()

        # Pre-fetch all form items and countries to avoid N+1 queries
        # Collect all IDs first - use entity_id directly for assigned to avoid property access
        for row in page_rows:
            if row.submission_type == 'assigned':
                data_item = assigned_map.get(row.id)
                if data_item:
                    if data_item.form_item_id:
                        form_item_ids.add(data_item.form_item_id)
                    status_info = data_item.assignment_entity_status
                    # Use entity_id directly instead of country property to avoid queries
                    if status_info and status_info.entity_type == 'country':
                        country_ids.add(status_info.entity_id)
            else:
                data_item = public_map.get(row.id)
                if data_item:
                    if data_item.form_item_id:
                        form_item_ids.add(data_item.form_item_id)
                    submission = data_item.public_submission
                    if submission and submission.country_id:
                        country_ids.add(submission.country_id)

        # Now process rows (optimized: inline formatting to avoid function call overhead)
        # Note: form_items and countries are loaded later when building related tables,
        # which allows for related_scope='all' expansion if needed
        for row in page_rows:
            if row.submission_type == 'assigned':
                data_item = assigned_map.get(row.id)
                if not data_item:
                    continue
                status_info = data_item.assignment_entity_status
                assigned_form = status_info.assigned_form if status_info else None
                # Use entity_id directly instead of country property to avoid queries
                country_id = status_info.entity_id if (status_info and status_info.entity_type == 'country') else None

                # Inline formatting to avoid function call overhead for 10k+ records
                value_raw = data_item.value
                data_not_avail = data_item.data_not_available
                not_applic = data_item.not_applicable

                if data_not_avail:
                    value = None
                    data_status = "data_not_available"
                elif not_applic:
                    value = None
                    data_status = "not_applicable"
                else:
                    value = format_answer_value(None if _is_blankish_scalar(value_raw) else value_raw)
                    data_status = "available"

                num_value = extract_numeric_value(value)
                submitted_at = data_item.submitted_at.isoformat() if data_item.submitted_at else None
                disagg_data_saved = _normalize_disagg_raw(getattr(data_item, "disagg_data", None))
                disagg_data = disagg_data_saved if include_disagg else None

                # Exclude non-reported rows (no value, no disagg, no flags, no imputed) unless explicitly requested.
                if (not include_non_reported) and data_status == "available":
                    if (value is None) and (disagg_data_saved is None) and (not _has_any_aux_value(data_item)):
                        continue

                payload = {
                    'id': data_item.id,
                    'submission_type': 'assigned',
                    'submission_id': status_info.id if status_info else None,
                    'form_item_id': data_item.form_item_id,
                    'template_id': assigned_form.template_id if assigned_form else None,
                    'period_name': assigned_form.period_name if assigned_form else None,
                    'country_id': country_id,
                    'value': value,
                    'prefilled_value': getattr(data_item, "prefilled_value", None),
                    'imputed_value': getattr(data_item, "imputed_value", None),
                    'prefilled_disagg_data': getattr(data_item, "prefilled_disagg_data", None),
                    'imputed_disagg_data': getattr(data_item, "imputed_disagg_data", None),
                    'num_value': num_value,
                    'data_status': data_status,
                    'date_collected': submitted_at,
                    'submitted_at': submitted_at,
                }
                if include_disagg and disagg_data:
                    payload['disaggregation_data'] = _normalize_disagg_payload(disagg_data)
                if include_disagg:
                    pdd = _normalize_disagg_raw(getattr(data_item, "prefilled_disagg_data", None))
                    idd = _normalize_disagg_raw(getattr(data_item, "imputed_disagg_data", None))
                    payload['prefilled_disaggregation_data'] = _normalize_disagg_payload(pdd) if pdd else None
                    payload['imputed_disaggregation_data'] = _normalize_disagg_payload(idd) if idd else None
                data_rows.append(payload)
            else:
                data_item = public_map.get(row.id)
                if not data_item:
                    continue
                submission = data_item.public_submission
                public_assignment = submission.assigned_form if submission else None
                # Use country_id directly instead of country relationship to avoid queries
                country_id = submission.country_id if submission else None

                # Inline formatting to avoid function call overhead
                value_raw = data_item.value
                data_not_avail = data_item.data_not_available
                not_applic = data_item.not_applicable

                if data_not_avail:
                    value = None
                    data_status = "data_not_available"
                elif not_applic:
                    value = None
                    data_status = "not_applicable"
                else:
                    value = format_answer_value(None if _is_blankish_scalar(value_raw) else value_raw)
                    data_status = "available"

                num_value = extract_numeric_value(value)
                submitted_at = submission.submitted_at.isoformat() if submission and submission.submitted_at else None
                disagg_data_saved = _normalize_disagg_raw(getattr(data_item, "disagg_data", None))
                disagg_data = disagg_data_saved if include_disagg else None

                # Exclude non-reported rows (no value, no disagg, no flags, no imputed) unless explicitly requested.
                if (not include_non_reported) and data_status == "available":
                    if (value is None) and (disagg_data_saved is None) and (not _has_any_aux_value(data_item)):
                        continue

                payload = {
                    'id': data_item.id,
                    'submission_type': 'public',
                    'submission_id': submission.id if submission else None,
                    'assignment_id': public_assignment.id if public_assignment else None,
                    'form_item_id': data_item.form_item_id,
                    'template_id': public_assignment.template_id if public_assignment else None,
                    'period_name': public_assignment.period_name if public_assignment else None,
                    'country_id': country_id,
                    'value': value,
                    'prefilled_value': getattr(data_item, "prefilled_value", None),
                    'imputed_value': getattr(data_item, "imputed_value", None),
                    'prefilled_disagg_data': getattr(data_item, "prefilled_disagg_data", None),
                    'imputed_disagg_data': getattr(data_item, "imputed_disagg_data", None),
                    'num_value': num_value,
                    'data_status': data_status,
                    'date_collected': submitted_at,
                    'submitted_at': submitted_at,
                }
                if include_disagg and disagg_data:
                    payload['disaggregation_data'] = _normalize_disagg_payload(disagg_data)
                if include_disagg:
                    pdd = _normalize_disagg_raw(getattr(data_item, "prefilled_disagg_data", None))
                    idd = _normalize_disagg_raw(getattr(data_item, "imputed_disagg_data", None))
                    payload['prefilled_disaggregation_data'] = _normalize_disagg_payload(pdd) if pdd else None
                    payload['imputed_disaggregation_data'] = _normalize_disagg_payload(idd) if idd else None
                data_rows.append(payload)

        # Optionally include non-reported (missing) form items as virtual rows (assigned submissions only).
        # This is intentionally only supported for user-auth (non-paginated) requests, and when
        # Template + Period + Country are provided to keep the expansion bounded.
        if (
            include_non_reported
            and not should_paginate
            and template_id is not None
            and country_id is not None
            and period_name
            and (not submission_type or str(submission_type).strip().lower() == 'assigned')
        ):
            try:
                # Resolve expected items for the template (respect item_id filter if provided)
                expected_items_q = FormItem.query.filter(
                    FormItem.template_id == int(template_id),
                    FormItem.archived == False,
                )

                # Scope expected items to the published template version (consistent with main query)
                if published_version_id:
                    expected_items_q = expected_items_q.filter(FormItem.version_id == int(published_version_id))

                # Apply privacy gating consistent with query_form_data
                viewer = get_effective_request_user()
                if not can_view_non_public_form_items(viewer):
                    expected_items_q = expected_items_q.filter(form_item_privacy_is_public_expr())

                if item_id is not None:
                    expected_items_q = expected_items_q.filter(FormItem.id == int(item_id))

                expected_item_ids = [int(fid) for (fid,) in expected_items_q.with_entities(FormItem.id).all() if fid is not None]
                if expected_item_ids:
                    # IMPORTANT: Avoid duplicates.
                    # If the DB has multiple AssignedForm rows that share the same period_name label,
                    # expanding "missing" rows across *all* of them can create "duplicate-looking" rows:
                    # one real row (from the assignment that has data) and another virtual missing row
                    # (from a different assignment with the same period label).
                    #
                    # Strategy:
                    # - Prefer expanding only for AES ids already present in the current filtered result set.
                    # - If there are *no* assigned rows yet (i.e., truly no reported data), fall back to
                    #   a single best-match AssignedForm for that (template_id, period_name, country_id).
                    from app.models import AssignedForm as _AssignedForm  # local import to avoid circular issues in some environments
                    from app.models.assignments import AssignmentEntityStatus as _AES

                    aes_list = []

                    # 1) Prefer AES ids already present in returned assigned rows.
                    existing_aes_ids = []
                    try:
                        existing_aes_ids = sorted({
                            int(r.get('submission_id'))
                            for r in (data_rows or [])
                            if isinstance(r, dict)
                            and r.get('submission_type') == 'assigned'
                            and r.get('submission_id') is not None
                            and str(r.get('submission_id')).strip() != ''
                        })
                    except Exception as e:
                        current_app.logger.debug("existing_aes_ids extraction failed: %s", e)
                        existing_aes_ids = []

                    if existing_aes_ids:
                        # Expand only within these AES ids; use the selected period_name for display.
                        for aes_id in existing_aes_ids:
                            try:
                                aes = _AES.query.get(int(aes_id))
                            except Exception as e:
                                current_app.logger.debug("AES lookup failed for id %s: %s", aes_id, e)
                                aes = None
                            if aes and int(aes.entity_id) == int(country_id) and str(aes.entity_type or '').lower() == 'country':
                                aes_list.append((aes, None))
                    else:
                        # 2) No assigned rows returned; fall back to a single matching assignment (best-effort).
                        # First try exact period match; if not found, try a conservative substring match.
                        af = (
                            _AssignedForm.query
                            .filter(_AssignedForm.template_id == int(template_id))
                            .filter(_AssignedForm.period_name == period_name)
                            .order_by(_AssignedForm.id.desc())
                            .first()
                        )
                        if not af:
                            _pat = safe_ilike_pattern(period_name or "")
                            af = (
                                _AssignedForm.query
                                .filter(_AssignedForm.template_id == int(template_id))
                                .filter(_AssignedForm.period_name.ilike(_pat))
                                .order_by(_AssignedForm.id.desc())
                                .first()
                            )
                        if af:
                            aes = (
                                _AES.query
                                .filter(
                                    _AES.assigned_form_id == af.id,
                                    _AES.entity_type == 'country',
                                    _AES.entity_id == int(country_id),
                                )
                                .first()
                            )
                            if aes:
                                aes_list.append((aes, af))

                    aes_ids = [int(aes.id) for (aes, _af) in aes_list if aes and aes.id]
                    if aes_ids:
                        # Ensure related country table includes the selected country even when all rows are virtual/missing.
                        country_ids.add(int(country_id))
                        existing_pairs = (
                            FormData.query
                            .filter(FormData.assignment_entity_status_id.in_(aes_ids))
                            .filter(FormData.form_item_id.in_(expected_item_ids))
                            .with_entities(FormData.assignment_entity_status_id, FormData.form_item_id)
                            .all()
                        )
                        existing_set = {(int(a), int(f)) for (a, f) in existing_pairs if a is not None and f is not None}

                        missing_count = 0
                        for (aes, af) in aes_list:
                            aes_id = int(aes.id)
                            for fid in expected_item_ids:
                                if (aes_id, int(fid)) in existing_set:
                                    continue
                                missing_count += 1
                                # Virtual id: stable, string; never persisted to the database.
                                virtual_id = f"m:{aes_id}:{int(fid)}"
                                data_rows.append({
                                    'id': virtual_id,
                                    'submission_type': 'assigned',
                                    'submission_id': aes_id,
                                    'form_item_id': int(fid),
                                    'template_id': int(template_id),
                                    'period_name': af.period_name if (af and getattr(af, 'period_name', None)) else period_name,
                                    'country_id': int(country_id),
                                    'value': None,
                                    'imputed_value': None,
                                    'num_value': None,
                                    'data_status': 'missing',
                                    'date_collected': None,
                                    'submitted_at': None,
                                    'is_missing': True,
                                })
                                form_item_ids.add(int(fid))
                        if missing_count:
                            total_items = int(total_items or 0) + int(missing_count)
            except Exception as e:
                current_app.logger.warning("include_non_reported expansion failed: %s", e, exc_info=True)

        # Collect matrix row prefixes (entity IDs) per form_item_id for entity name resolution
        matrix_row_prefixes = {}
        if include_disagg:
            for row in data_rows:
                disagg = row.get('disaggregation_data')
                if not disagg or disagg.get('mode') != 'matrix':
                    continue
                form_item_id = row.get('form_item_id')
                if not form_item_id:
                    continue
                values = disagg.get('values') or {}
                for key in values:
                    if not isinstance(key, str) or key.startswith('_'):
                        continue
                    idx = key.find('_')
                    prefix = key[:idx] if idx >= 0 else key
                    if prefix not in (None, ''):
                        matrix_row_prefixes.setdefault(form_item_id, set()).add(prefix)

        # Optionally expand related tables to cover the full filtered dataset (not only the current page)
        expansion_failed = False
        if related_scope == 'all':
            try:
                # Collect all unique form_item_ids across filtered assigned/public queries (optimized)
                if assigned_form_data_query is not None:
                    # Use scalar() for better performance
                    all_fi_ids_assigned = [
                        fid for (fid,) in assigned_form_data_query
                        .with_entities(FormData.form_item_id)
                        .distinct()
                        .all()
                        if fid is not None
                    ]
                    form_item_ids.update(all_fi_ids_assigned)
                if public_form_data_query is not None:
                    all_fi_ids_public = [
                        fid for (fid,) in public_form_data_query
                        .with_entities(FormData.form_item_id)
                        .distinct()
                        .all()
                        if fid is not None
                    ]
                    form_item_ids.update(all_fi_ids_public)

                # Collect all unique country_ids across filtered assigned/public queries (optimized)
                if assigned_form_data_query is not None:
                    # Check if join already exists to avoid duplicate joins
                    assigned_country_ids = [
                        cid for (cid,) in assigned_form_data_query
                        .join(AssignmentEntityStatus)
                        .with_entities(AssignmentEntityStatus.entity_id)
                        .filter(AssignmentEntityStatus.entity_type == 'country')
                        .distinct()
                        .all()
                        if cid is not None
                    ]
                    country_ids.update(assigned_country_ids)
                if public_form_data_query is not None:
                    # Public query already has PublicSubmission join
                    public_country_ids = [
                        cid for (cid,) in public_form_data_query
                        .with_entities(PublicSubmission.country_id)
                        .distinct()
                        .all()
                        if cid is not None
                    ]
                    country_ids.update(public_country_ids)
            except Exception as _e:
                # If any of the above expansions fail, log error and return partial result
                error_id = str(uuid.uuid4())
                current_app.logger.error(
                    f"related=all expansion failed in /data/tables [ID: {error_id}]: {_e}",
                    exc_info=True,
                    extra={'endpoint': '/data/tables', 'params': dict(request.args)}
                )
                expansion_failed = True

        # Build related tables from the collected id sets (optimized with eager loading)
        form_items_table = []
        if form_item_ids:
            # Use eager loading to reduce N+1 queries
            from sqlalchemy.orm import joinedload
            form_items = (
                FormItem.query
                .options(
                    joinedload(FormItem.form_section),
                    joinedload(FormItem.template)
                )
                .filter(FormItem.id.in_(form_item_ids))
                .all()
            )
            # Sort in Python after loading (more efficient than DB sort for small sets)
            form_items_sorted = sorted(form_items, key=lambda fi: (fi.template_id or 0, fi.id or 0))
            for item in form_items_sorted:
                form_items_table.append(
                    format_form_item_info(
                        item,
                        section=item.form_section,
                        template=item.template
                    )
                )
            # Resolve matrix row entity IDs to display names using form item matrix config
            matrix_entity_labels = _resolve_matrix_entity_labels(matrix_row_prefixes, form_items_sorted)
        else:
            matrix_entity_labels = {}

        countries_table = []
        if country_ids:
            # Note: primary_national_society is a property, not a relationship, so we can't eager load it
            countries = (
                Country.query
                .filter(Country.id.in_(country_ids))
                .all()
            )
            # Sort in Python after loading
            countries_sorted = sorted(countries, key=lambda c: c.name or '')
            for country in countries_sorted:
                countries_table.append(format_country_info(country))

        # Build response based on authentication type
        if should_paginate:
            # API key auth: return paginated response
            total_pages = (total_items + per_page - 1) // per_page if per_page > 0 else 1
            response_data = {
                'data': data_rows,
                'form_items': form_items_table,
                'countries': countries_table,
                'matrix_entity_labels': matrix_entity_labels,
                'total_items': total_items,
                'total_pages': total_pages,
                'current_page': page,
                'per_page': per_page
            }
        else:
            # User auth: return all accessible data (no pagination)
            response_data = {
                'data': data_rows,
                'form_items': form_items_table,
                'countries': countries_table,
                'matrix_entity_labels': matrix_entity_labels,
                'total_items': total_items,
                'total_pages': None,
                'current_page': None,
                'per_page': None
            }

        # Add warning if related=all expansion failed
        if expansion_failed:
            response_data['warning'] = 'Related tables expansion failed, showing page-scoped results only'
            response_data['partial'] = True

        return json_response(response_data)
    except Exception as e:
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            f"API Error [ID: {error_id}] fetching data tables: {e}",
            exc_info=True,
            extra={'endpoint': '/data/tables', 'params': dict(request.args)}
        )
        return api_error("Could not fetch data tables", 500, error_id, None)
