# Backoffice/app/routes/api/data.py
"""
Data API endpoints.
Part of the /api/v1 blueprint.
"""

from datetime import datetime as _dt
import re
from flask import request, current_app, g, redirect
from sqlalchemy import and_, desc, event as sa_event, literal, or_
import uuid
from contextlib import suppress
from typing import Any, Dict, List, Optional, Sequence

# Import the API blueprint from parent
from app.routes.api import api_bp
from app.utils.ttl_cache import TTLCache

# Import models
from app.models import (
    AssignedForm,
    Country,
    FormData,
    IndicatorBank,
    NationalSociety,
    PublicSubmission,
    FormItem,
    FormTemplate,
    FormTemplateVersion,
)
from app.models.assignments import AssignmentEntityStatus
from app.utils.auth import require_api_key
from app.utils.rate_limiting import api_rate_limit
from app import db

# Import utility functions
from app.utils.api_helpers import json_response, json_data_response, api_error, extract_numeric_value
from app.utils.api_serialization import (
    format_country_info,
    format_form_item_info,
    format_national_society_info,
    format_dim_submission_assigned,
    build_star_schema_tables,
    build_matrix_cells_from_data_rows,
    enrich_matrix_cells,
    STAR_SCHEMA_VERSION,
    STAR_SCHEMA_GRAIN,
    serialize_dynamic_data_item,
    serialize_repeat_data_item,
)
from app.services.security.api_authentication import (
    authenticate_api_request,
    get_user_allowed_template_ids,
    _get_user_allowed_country_ids,
    apply_user_template_scoping,
    apply_api_key_data_scoping,
)
from app.services.security.public_data_access import (
    PUBLIC_DATA_MAX_PER_PAGE,
    public_include_dimensions,
    slim_public_data_rows,
    validate_public_data_request,
)
from app.utils.api_pagination import (
    parse_date_range, get_sort_params, validate_data_endpoint_params,
    validate_pagination_params,
    build_pagination_queries, get_paginated_data_ids, fetch_paginated_rows,
    build_paginated_response, query_filter_in_batches,
    MAX_USER_AUTH_ROWS,
)
from app.utils.api_formatting import format_answer_value, format_form_data_response, serialize_form_data_item
from app.utils.api_serialization import _wrap_disagg_dict as _normalize_disagg_payload_util
from app.utils.sql_utils import safe_ilike_pattern
from app.services import query_form_data
from app.services import get_form_data_queries
from app.services import TemplateService
from app.services import query_dynamic_indicator_data
from app.services import query_repeat_group_data
from app.utils.api_data_filters import (
    VERSION_SCOPE_PUBLISHED,
    apply_form_data_version_scoping,
    build_data_api_scope_meta,
    parse_data_item_filters,
    resolve_template_published_version_id,
)
from app.services.data_retrieval.shared import (
    get_effective_request_user,
    can_view_non_public_form_items,
    form_item_privacy_is_public_expr,
    escape_like_pattern,
)


_DATA_ARRAY_CATALOG = {
    'data': {
        'title': 'Static field values',
        'description': (
            'Submitted answers for static form items (FormData). One row per saved value. '
            'Join to form_items via form_item_id and to countries via country_id. '
            'Matrix cell values are normalized in matrix_cells[] (not duplicated here).'
        ),
        'grain': 'submission × static form_item',
        'key_fields': [
            'id', 'form_item_id', 'country_id', 'submission_id', 'submission_type',
            'template_id', 'period_name', 'value', 'num_value', 'data_status',
        ],
    },
    'dynamic_data': {
        'title': 'Dynamic indicator values',
        'description': (
            'Values for dynamic indicators (not tied to a fixed form_item_id). '
            'Keyed by indicator_bank_id and section_id; emergency appeals also use '
            'repeat_instance_number / repeat_instance_id. Join to indicator_bank via indicator_bank_id.'
        ),
        'grain': 'submission × section × indicator_bank (+ repeat slot when applicable)',
        'key_fields': [
            'id', 'indicator_bank_id', 'section_id', 'country_id', 'submission_id',
            'repeat_instance_number', 'repeat_instance_id', 'value', 'custom_label',
        ],
    },
    'repeat_data': {
        'title': 'Repeat-group field values',
        'description': (
            'Answers inside repeat groups (e.g. emergency appeal rows). '
            'Join to form_items via form_item_id and to dynamic_context via repeat_instance_id '
            'when resolving appeal metadata.'
        ),
        'grain': 'submission × repeat instance × form_item',
        'key_fields': [
            'id', 'form_item_id', 'repeat_instance_id', 'section_id', 'country_id',
            'submission_id', 'value', 'num_value',
        ],
    },
    'dynamic_context': {
        'title': 'Dynamic section bindings',
        'description': (
            'Metadata linking dynamic sections to repeat instances (e.g. appeal code and label '
            'for each emergency slot). Join to dynamic_data / repeat_data via repeat_instance_id.'
        ),
        'grain': 'submission × section × repeat instance',
        'key_fields': [
            'id', 'section_id', 'repeat_instance_id', 'label_snapshot', 'context_data',
            'submission_id', 'submission_type',
        ],
    },
    'form_items': {
        'title': 'Form item definitions',
        'description': (
            'Labels and config for form fields referenced by fact rows. Scope controlled by '
            'related=page (current page only) or related=all (full filtered dataset).'
        ),
        'grain': 'form_item',
        'key_fields': ['id', 'stable_key', 'label', 'type', 'section', 'bank_details', 'matrix_config'],
    },
    'countries': {
        'title': 'Country dimension',
        'description': 'Full country reference table (~192 rows). Always included. Join via country_id.',
        'grain': 'country',
        'key_fields': ['id', 'name', 'iso2', 'iso3', 'national_society_name', 'region'],
    },
    'indicator_bank': {
        'title': 'Indicator bank dimension',
        'description': (
            'Full indicator catalog (~466 rows). Always included. Provides name, definition, '
            'sector, and unit. Join via indicator_bank_id on dynamic_data or bank_details.id on form_items.'
        ),
        'grain': 'indicator',
        'key_fields': ['id', 'name', 'definition', 'type', 'unit', 'sector', 'sub_sector'],
    },
    'national_societies': {
        'title': 'National Society dimension',
        'description': (
            'Full National Society reference table. Always included. '
            'Join matrix_cells.row_entity_id when join_dimension=national_societies.'
        ),
        'grain': 'national_society',
        'key_fields': [
            'id', 'name', 'code', 'country_id', 'country_name', 'country_iso2', 'country_iso3',
            'part_of',
        ],
    },
    'matrix_cells': {
        'title': 'Matrix cell values',
        'description': (
            'Normalized matrix disaggregation rows parsed from data[]. One row per cell. '
            'Matrix-specific fields are grouped under matrix (row, column, entity).'
        ),
        'grain': 'form_data × matrix row entity × column × source',
        'key_fields': [
            'form_data_id', 'form_item_id', 'form_item_label', 'value',
            'matrix.parent_form_data_id', 'matrix.source',
            'matrix.row.entity_id', 'matrix.row.label',
            'matrix.column.key', 'matrix.column.label',
            'matrix.entity.id', 'matrix.entity.name',
        ],
    },
    'assignment_statuses': {
        'title': 'Assignment entity status dimension',
        'description': (
            'Workflow status rows for assigned submissions (AssignmentEntityStatus), '
            'including pending assignments that have no FormData yet. '
            'Join via submission_id on data[] / dynamic_data[] / repeat_data[] when '
            'submission_type is assigned. Equivalent to dim_submission (assigned) in layout=star.'
        ),
        'grain': 'assignment_entity_status',
        'key_fields': [
            'id', 'type', 'status', 'entity_type', 'entity_id',
            'submitted_at', 'due_date', 'assigned_form_id',
        ],
    },
}


def _build_data_array_catalog(*, include_dynamic: bool, include_repeat: bool) -> dict:
    """Return catalog entries for arrays present in this response."""
    catalog = {
        'data': {**_DATA_ARRAY_CATALOG['data'], 'included': True},
        'form_items': {**_DATA_ARRAY_CATALOG['form_items'], 'included': True},
        'countries': {**_DATA_ARRAY_CATALOG['countries'], 'included': True},
        'national_societies': {**_DATA_ARRAY_CATALOG['national_societies'], 'included': True},
        'indicator_bank': {**_DATA_ARRAY_CATALOG['indicator_bank'], 'included': True},
        'matrix_cells': {**_DATA_ARRAY_CATALOG['matrix_cells'], 'included': True},
        'assignment_statuses': {**_DATA_ARRAY_CATALOG['assignment_statuses'], 'included': True},
    }
    if include_dynamic:
        catalog['dynamic_data'] = {**_DATA_ARRAY_CATALOG['dynamic_data'], 'included': True}
        catalog['dynamic_context'] = {**_DATA_ARRAY_CATALOG['dynamic_context'], 'included': True}
    if include_repeat:
        catalog['repeat_data'] = {**_DATA_ARRAY_CATALOG['repeat_data'], 'included': True}
    return catalog


def _merge_scope_into_response(response_data, scope_meta):
    """Attach ``scope`` metadata when template-scoped filters were used."""
    if scope_meta:
        response_data['scope'] = scope_meta
    return response_data


def _collect_assigned_submission_ids(*row_lists) -> list:
    """Return sorted unique AssignmentEntityStatus ids from fact row dicts."""
    ids = set()
    for rows in row_lists:
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            if str(row.get('submission_type') or '').strip().lower() != 'assigned':
                continue
            sid = row.get('submission_id')
            if sid is None or str(sid).strip() == '':
                continue
            try:
                ids.add(int(sid))
            except (TypeError, ValueError):
                continue
    return sorted(ids)


def _collect_scoped_assignment_status_ids(
    *,
    template_id: Optional[int] = None,
    country_id: Optional[int] = None,
    period_name: Optional[str] = None,
    assignment_id: Optional[int] = None,
    submission_id: Optional[int] = None,
    allowed_template_ids: Optional[Sequence[int]] = None,
    allowed_country_ids: Optional[Sequence[int]] = None,
) -> list:
    """
    Return AES ids matching the request scope, including pending rows with no FormData.

    Requires at least one structural filter (template / country / period / assignment / submission)
    so unbounded /data calls do not dump the entire assignment_entity_status table.
    """
    period = (period_name or '').strip() or None
    has_scope = any(
        v is not None for v in (template_id, country_id, period, assignment_id, submission_id)
    )
    if not has_scope:
        return []

    if allowed_template_ids is not None and len(list(allowed_template_ids)) == 0:
        return []
    if allowed_country_ids is not None and len(list(allowed_country_ids)) == 0:
        return []

    if (
        template_id is not None
        and allowed_template_ids is not None
        and int(template_id) not in {int(x) for x in allowed_template_ids}
    ):
        return []
    if (
        country_id is not None
        and allowed_country_ids is not None
        and int(country_id) not in {int(x) for x in allowed_country_ids}
    ):
        return []

    q = AssignmentEntityStatus.query.join(
        AssignedForm,
        AssignmentEntityStatus.assigned_form_id == AssignedForm.id,
    )

    if assignment_id is not None:
        # Exact assignment scope — ignore coarser template/period filters that may
        # conflict (e.g. leftover period_name in a BI query).
        q = q.filter(AssignedForm.id == int(assignment_id))
    else:
        if template_id is not None:
            q = q.filter(AssignedForm.template_id == int(template_id))
        elif allowed_template_ids is not None:
            q = q.filter(AssignedForm.template_id.in_(list(allowed_template_ids)))

        if period:
            _pat = f"%{escape_like_pattern(period)}%"
            period_filter = AssignedForm.period_name.ilike(_pat, escape="\\")
            years = [int(y) for y in re.findall(r"\b(19\d{2}|20\d{2}|21\d{2})\b", str(period))]
            if years:
                start_year = min(years)
                end_year = max(years)
                period_start = _dt(start_year, 1, 1).date()
                period_end = _dt(end_year, 12, 31).date()
                period_filter = or_(
                    period_filter,
                    and_(
                        AssignedForm.period_start.isnot(None),
                        AssignedForm.period_end.isnot(None),
                        AssignedForm.period_start <= period_end,
                        AssignedForm.period_end >= period_start,
                    ),
                )
            q = q.filter(period_filter)

    # Still apply RBAC template allow-list when assignment_id is used.
    if assignment_id is not None and allowed_template_ids is not None:
        q = q.filter(AssignedForm.template_id.in_(list(allowed_template_ids)))

    if country_id is not None:
        q = q.filter(
            AssignmentEntityStatus.entity_type == 'country',
            AssignmentEntityStatus.entity_id == int(country_id),
        )
    elif allowed_country_ids is not None:
        q = q.filter(
            AssignmentEntityStatus.entity_type == 'country',
            AssignmentEntityStatus.entity_id.in_(list(allowed_country_ids)),
        )

    if submission_id is not None:
        q = q.filter(AssignmentEntityStatus.id == int(submission_id))

    ids = [
        int(aes_id)
        for (aes_id,) in q.with_entities(AssignmentEntityStatus.id).all()
        if aes_id is not None
    ]
    return sorted(set(ids))


def _load_assignment_statuses_table(aes_ids) -> list:
    """Serialize AssignmentEntityStatus rows for the flat /data dimension array."""
    if not aes_ids:
        return []
    aes_rows = query_filter_in_batches(
        AssignmentEntityStatus.query,
        AssignmentEntityStatus.id,
        list(aes_ids),
    )
    table = [
        format_dim_submission_assigned(aes)
        for aes in aes_rows
        if aes
    ]
    table.sort(key=lambda row: row.get('id') or 0)
    return table


def _build_assignment_statuses_table(
    *row_lists,
    template_id: Optional[int] = None,
    country_id: Optional[int] = None,
    period_name: Optional[str] = None,
    assignment_id: Optional[int] = None,
    submission_id: Optional[int] = None,
    submission_type: Optional[str] = None,
    allowed_template_ids: Optional[Sequence[int]] = None,
    allowed_country_ids: Optional[Sequence[int]] = None,
) -> list:
    """Fact-derived AES ids plus scoped AES (including pending with no FormData)."""
    if str(submission_type or '').strip().lower() == 'public':
        return []

    aes_ids = set(_collect_assigned_submission_ids(*row_lists))
    aes_ids.update(
        _collect_scoped_assignment_status_ids(
            template_id=template_id,
            country_id=country_id,
            period_name=period_name,
            assignment_id=assignment_id,
            submission_id=submission_id,
            allowed_template_ids=allowed_template_ids,
            allowed_country_ids=allowed_country_ids,
        )
    )
    return _load_assignment_statuses_table(sorted(aes_ids))


def _assemble_flat_data_payload(
    *,
    data_rows,
    form_items_table,
    countries_table,
    national_societies_table,
    indicator_bank_table,
    matrix_cells,
    total_items,
    total_pages,
    current_page,
    per_page,
    dynamic_data=None,
    repeat_data=None,
    dynamic_context=None,
    assignment_statuses=None,
    warning=None,
    partial=None,
    scope_meta=None,
    array_catalog=None,
):
    """
    Build a flat /data response dict with a stable, export-friendly key order.

    Grouping: scope → arrays (catalog) → pagination → facts → dimensions → status flags.
    """
    payload = {}
    if scope_meta:
        payload['scope'] = scope_meta
    if array_catalog is not None:
        payload['arrays'] = array_catalog
    payload['total_items'] = total_items
    payload['total_pages'] = total_pages
    payload['current_page'] = current_page
    payload['per_page'] = per_page
    payload['data'] = data_rows
    if dynamic_data is not None:
        payload['dynamic_data'] = dynamic_data
    if repeat_data is not None:
        payload['repeat_data'] = repeat_data
    if dynamic_context is not None:
        payload['dynamic_context'] = dynamic_context
    payload['matrix_cells'] = matrix_cells
    payload['form_items'] = form_items_table
    payload['countries'] = countries_table
    payload['national_societies'] = national_societies_table
    payload['indicator_bank'] = indicator_bank_table
    payload['assignment_statuses'] = (
        assignment_statuses if assignment_statuses is not None else []
    )
    if warning:
        payload['warning'] = warning
    if partial:
        payload['partial'] = partial
    return payload


# Dimension tables below (countries, national societies, indicator bank) change
# rarely and are always included in full on every /data response, so they are
# cached per-worker with a long TTL. Cache entries are also invalidated
# immediately on writes to the underlying models (see event listeners below),
# so admins editing this data see it reflected right away without waiting for
# the TTL to expire; the TTL is just a safety net for writes that happen
# outside the ORM event hooks (e.g. direct SQL, another process).
_REFERENCE_TABLE_CACHE_TTL_SECONDS = 24 * 60 * 60  # 1 day

_countries_table_cache: TTLCache = TTLCache(ttl_seconds=_REFERENCE_TABLE_CACHE_TTL_SECONDS)
_national_societies_table_cache: TTLCache = TTLCache(ttl_seconds=_REFERENCE_TABLE_CACHE_TTL_SECONDS)
_indicator_bank_table_cache: TTLCache = TTLCache(ttl_seconds=_REFERENCE_TABLE_CACHE_TTL_SECONDS)


def _load_full_indicator_bank_table_uncached():
    """Return the full indicator bank dimension (~466 rows, stable size)."""
    from app.services.indicators.bank_service import IndicatorBankFilters, get_indicator_list
    indicators, _total, _page, _per_page = get_indicator_list(IndicatorBankFilters())
    return indicators


def _load_full_countries_table_uncached():
    """Return the full country dimension (same coverage as /countrymap)."""
    from app.services import CountryService
    return [
        format_country_info(country)
        for country in CountryService.get_all_with_national_societies(ordered=True).all()
    ]


def _load_full_national_societies_table_uncached():
    """Return the full National Society dimension table."""
    from sqlalchemy.orm import joinedload
    societies = (
        NationalSociety.query
        .options(joinedload(NationalSociety.country))
        .filter(NationalSociety.is_active == True)  # noqa: E712
        .order_by(NationalSociety.display_order, NationalSociety.name)
        .all()
    )
    return [format_national_society_info(ns) for ns in societies]


def _load_full_indicator_bank_table():
    return _indicator_bank_table_cache.get_or_load(_load_full_indicator_bank_table_uncached)


def _load_full_countries_table():
    return _countries_table_cache.get_or_load(_load_full_countries_table_uncached)


def _load_full_national_societies_table():
    return _national_societies_table_cache.get_or_load(_load_full_national_societies_table_uncached)


def _invalidate_reference_table_caches_for_test():
    """Test-only helper to reset all three reference-table caches."""
    _countries_table_cache.invalidate()
    _national_societies_table_cache.invalidate()
    _indicator_bank_table_cache.invalidate()


def _register_reference_table_cache_invalidation():
    """Invalidate the relevant cache whenever Country / NationalSociety / IndicatorBank rows change.

    Registered once at module import time. Fires on flush (before commit), so a
    rollback after a write causes one harmless extra reload rather than a
    correctness issue.
    """
    for _model, _cache in (
        (Country, _countries_table_cache),
        (NationalSociety, _national_societies_table_cache),
        (IndicatorBank, _indicator_bank_table_cache),
    ):
        for _event_name in ('after_insert', 'after_update', 'after_delete'):
            sa_event.listens_for(_model, _event_name)(
                lambda mapper, connection, target, _cache=_cache: _cache.invalidate()
            )


_register_reference_table_cache_invalidation()


def _normalize_disagg_payload(disagg_data):
    """
    Normalize disagg_data for API response.
    Delegates to the shared _wrap_disagg_dict in api_serialization, which handles
    all three on-disk formats: standard disagg, flat matrix, and plugin/arbitrary JSON.
    Returns {'mode': None, 'values': {}} when disagg_data is None/empty rather than None,
    so callers that always expect a dict still work.
    """
    result = _normalize_disagg_payload_util(disagg_data)
    if result is None:
        return {'mode': None, 'values': {}}
    return result


def _parse_include_flags(args):
    """Return (include_dynamic, include_repeat) booleans from query-string args.

    Both default to True. Pass ``include_dynamic=false`` or ``include_repeat=false`` to exclude.
    """
    def _falsy(v):
        return str(v or '').strip().lower() in ('0', 'false', 'no', 'n')

    def _parse_flag(key):
        raw = args.get(key)
        if raw is None or str(raw).strip() == '':
            return True
        if _falsy(raw):
            return False
        return True

    return _parse_flag('include_dynamic'), _parse_flag('include_repeat')


def _fetch_extended_data(
    *,
    template_id, submission_id, item_id, country_id, period_name,
    assignment_id, indicator_bank_id, submission_type,
    include_dynamic, include_repeat,
    minimal_country_info,
    elevated_access, auth_user,
    date_from=None, date_to=None,
):
    """
    Fetch DynamicIndicatorData and/or RepeatGroupData rows for the current request filters.

    Returns a dict ``{'dynamic_data': [...], 'repeat_data': [...], 'dynamic_context': [...]}``.
    ``dynamic_context`` lists DynamicSectionContext bindings (e.g. emergency appeal codes).
    All keys are always present; lists are empty when the corresponding flag is False.

    RBAC:
    - API-key (elevated_access): no template restriction, fetch all matching rows.
    - User auth (not elevated_access): restrict to templates the user owns/shares, and to
      countries the user has permission for.  Uses the same ``get_user_allowed_template_ids``
      logic as the main /data query.
    """
    from app.services.security.api_authentication import (
        get_user_allowed_template_ids,
        _get_user_allowed_country_ids,
    )
    from app.services.organization.authorization_service import AuthorizationService
    from app.models import AssignedForm, PublicSubmission
    from app.models.assignments import AssignmentEntityStatus
    from sqlalchemy import literal

    dynamic_rows = []
    repeat_rows = []
    dynamic_context_rows = []
    dynamic_orm_rows = []
    # Collected inline (while rows are already being built) so the caller can
    # feed assignment_statuses[] without a second pass over dynamic_rows/repeat_rows.
    assigned_submission_ids = set()

    def _apply_user_scoping(q_dict, needs_af_join):
        """Apply user-level template + country RBAC to a dynamic/repeat query dict."""
        if elevated_access or auth_user is None:
            return q_dict

        is_sys_mgr = AuthorizationService.is_system_manager(auth_user)
        if is_sys_mgr:
            return q_dict

        allowed_tids = get_user_allowed_template_ids(auth_user.id)
        if not allowed_tids:
            return {'assigned': None, 'public': None}

        a_q = q_dict.get('assigned')
        p_q = q_dict.get('public')

        if a_q is not None:
            if needs_af_join:
                a_q = a_q.filter(AssignedForm.template_id.in_(allowed_tids))
            else:
                a_q = a_q.filter(AssignedForm.template_id.in_(allowed_tids))

        if p_q is not None:
            p_q = p_q.filter(AssignedForm.template_id.in_(allowed_tids))

        allowed_cids = _get_user_allowed_country_ids(auth_user)
        if allowed_cids is not None:
            if not allowed_cids:
                return {'assigned': None, 'public': None}
            if a_q is not None:
                a_q = a_q.filter(
                    AssignmentEntityStatus.entity_type == 'country',
                    AssignmentEntityStatus.entity_id.in_(allowed_cids),
                )
            if p_q is not None:
                p_q = p_q.filter(PublicSubmission.country_id.in_(allowed_cids))

        return {'assigned': a_q, 'public': p_q}

    if include_dynamic:
        try:
            dq = query_dynamic_indicator_data(
                template_id=template_id,
                submission_id=submission_id,
                country_id=country_id,
                period_name=period_name,
                assignment_id=assignment_id,
                indicator_bank_id=indicator_bank_id,
                submission_type=submission_type,
                preload=True,
            )
            needs_join = bool(
                template_id or country_id or period_name or submission_id or assignment_id
            )
            dq = _apply_user_scoping(dq, needs_join)

            for stype, q in [('assigned', dq.get('assigned')), ('public', dq.get('public'))]:
                if q is None:
                    continue
                if date_from:
                    from app.models.forms import DynamicIndicatorData
                    q = q.filter(DynamicIndicatorData.submitted_at >= date_from)
                if date_to:
                    from app.models.forms import DynamicIndicatorData
                    q = q.filter(DynamicIndicatorData.submitted_at <= date_to)
                dynamic_orm_rows.extend(q.all())

            if dynamic_orm_rows:
                from app.utils.api_serialization import (
                    batch_countries_for_aes_list,
                    build_dynamic_serialization_context,
                    fetch_dynamic_section_contexts,
                )
                assigned_aes = [
                    row.assignment_entity_status
                    for row in dynamic_orm_rows
                    if getattr(row, 'assignment_entity_status', None)
                ]
                aes_countries = batch_countries_for_aes_list(assigned_aes)
                dynamic_serialization_context = build_dynamic_serialization_context(dynamic_orm_rows)
                dynamic_context_rows = fetch_dynamic_section_contexts(dynamic_orm_rows)
                for row in dynamic_orm_rows:
                    item = serialize_dynamic_data_item(
                        row,
                        minimal_country_info=minimal_country_info,
                        aes_countries=aes_countries,
                        dynamic_context=dynamic_serialization_context,
                    )
                    if item.get('submission_type') == 'assigned' and item.get('submission_id') is not None:
                        assigned_submission_ids.add(int(item['submission_id']))
                    dynamic_rows.append(item)
        except Exception as e:
            current_app.logger.warning("_fetch_extended_data: dynamic query failed: %s", e, exc_info=True)

    if include_repeat:
        try:
            rq = query_repeat_group_data(
                template_id=template_id,
                submission_id=submission_id,
                item_id=item_id,
                country_id=country_id,
                period_name=period_name,
                assignment_id=assignment_id,
                submission_type=submission_type,
                preload=True,
            )
            needs_join = bool(
                template_id or country_id or period_name or submission_id or assignment_id
            )
            rq = _apply_user_scoping(rq, needs_join)

            for stype, q in [('assigned', rq.get('assigned')), ('public', rq.get('public'))]:
                if q is None:
                    continue
                if date_from:
                    from app.models.forms import RepeatGroupData
                    q = q.filter(RepeatGroupData.submitted_at >= date_from)
                if date_to:
                    from app.models.forms import RepeatGroupData
                    q = q.filter(RepeatGroupData.submitted_at <= date_to)
                rows = q.all()
                assigned_aes = []
                for row in rows:
                    instance = getattr(row, 'repeat_instance', None)
                    aes = getattr(instance, 'assignment_entity_status', None) if instance else None
                    if aes:
                        assigned_aes.append(aes)
                from app.utils.api_serialization import batch_countries_for_aes_list
                aes_countries = batch_countries_for_aes_list(assigned_aes)
                for row in rows:
                    item = serialize_repeat_data_item(
                        row,
                        minimal_country_info=minimal_country_info,
                        aes_countries=aes_countries,
                    )
                    if item.get('submission_type') == 'assigned' and item.get('submission_id') is not None:
                        assigned_submission_ids.add(int(item['submission_id']))
                    repeat_rows.append(item)
        except Exception as e:
            current_app.logger.warning("_fetch_extended_data: repeat query failed: %s", e, exc_info=True)

    return {
        'dynamic_data': dynamic_rows,
        'repeat_data': repeat_rows,
        'dynamic_context': dynamic_context_rows,
        'assigned_submission_ids': assigned_submission_ids,
    }


@api_bp.route('/templates/<int:template_id>/data', methods=['GET'])
@require_api_key
@api_rate_limit()
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
@api_rate_limit()
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


def _parse_tables_layout_param():
    """Return ``flat`` (default) or ``star`` for /data response shape."""
    layout = str(request.args.get('layout', 'flat') or 'flat').strip().lower()
    if layout not in ('flat', 'star'):
        layout = 'flat'
    return layout


def _build_flat_data_response(
    data_rows,
    form_items_table,
    countries_table,
    national_societies_table,
    indicator_bank_table,
    matrix_cells,
    *,
    should_paginate,
    total_items,
    page,
    per_page,
    expansion_failed=False,
    extra=None,
    assignment_statuses=None,
    scope_meta=None,
    array_catalog=None,
):
    """Multi-table submission data bundle (facts + dimensions)."""
    if should_paginate:
        total_pages = (total_items + per_page - 1) // per_page if per_page > 0 else 1
        resp_page = page
        resp_per_page = per_page
    else:
        total_pages = None
        resp_page = None
        resp_per_page = None

    warning = None
    partial = None
    if expansion_failed:
        warning = 'Related tables expansion failed, showing page-scoped results only'
        partial = True

    dynamic_data = repeat_data = dynamic_context = None
    if extra:
        dynamic_data = extra.get('dynamic_data')
        repeat_data = extra.get('repeat_data')
        dynamic_context = extra.get('dynamic_context')

    response_data = _assemble_flat_data_payload(
        data_rows=data_rows,
        form_items_table=form_items_table,
        countries_table=countries_table,
        national_societies_table=national_societies_table,
        indicator_bank_table=indicator_bank_table,
        matrix_cells=matrix_cells,
        total_items=total_items,
        total_pages=total_pages,
        current_page=resp_page,
        per_page=resp_per_page,
        dynamic_data=dynamic_data,
        repeat_data=repeat_data,
        dynamic_context=dynamic_context,
        assignment_statuses=assignment_statuses,
        warning=warning,
        partial=partial,
        scope_meta=scope_meta,
        array_catalog=array_catalog,
    )
    return json_response(response_data)


_build_flat_tables_response = _build_flat_data_response


def _build_star_data_response(
    data_rows,
    form_items_table,
    countries_table,
    national_societies_table,
    indicator_bank_table,
    matrix_cells,
    *,
    should_paginate,
    total_items,
    page,
    per_page,
    expansion_failed=False,
    extra=None,
    assignment_statuses=None,
    scope_meta=None,
    array_catalog=None,
):
    """Star-schema dimensional tables for BI / integrator consumers."""
    dynamic_data = repeat_data = dynamic_context = None
    if extra:
        dynamic_data = extra.get('dynamic_data')
        repeat_data = extra.get('repeat_data')
        dynamic_context = extra.get('dynamic_context')
    tables = build_star_schema_tables(
        data_rows,
        form_items_table,
        countries_table,
        dynamic_data=dynamic_data,
        repeat_data=repeat_data,
        matrix_cells=matrix_cells,
        national_societies_table=national_societies_table,
        indicator_bank_table=indicator_bank_table,
        dynamic_context=dynamic_context,
        assignment_statuses=assignment_statuses,
    )
    if should_paginate:
        total_pages = (total_items + per_page - 1) // per_page if per_page > 0 else 1
        meta = {
            'total_facts': total_items,
            'total_pages': total_pages,
            'current_page': page,
            'per_page': per_page,
        }
    else:
        meta = {
            'total_facts': total_items,
            'total_pages': None,
            'current_page': None,
            'per_page': None,
        }
    if expansion_failed:
        meta['warning'] = 'Related tables expansion failed, showing page-scoped results only'
        meta['partial'] = True
    if scope_meta:
        meta['scope'] = scope_meta
    if array_catalog is not None:
        meta['arrays'] = array_catalog
    body = {
        'schema_version': STAR_SCHEMA_VERSION,
        'grain': STAR_SCHEMA_GRAIN,
        'tables': tables,
    }
    return json_data_response(body, meta=meta)


_build_star_tables_response = _build_star_data_response


@api_bp.route('/data', methods=['GET'])
@api_rate_limit()
def get_all_data():
    """
    API endpoint to retrieve submission data with related dimension tables.

    Returns fact arrays (``data``, ``dynamic_data``, ``repeat_data``, ``dynamic_context``,
    ``matrix_cells``) plus dimension tables (``form_items``, ``countries``,
    ``national_societies``, ``indicator_bank``, ``assignment_statuses``).

    Authentication (one of):
      - Authorization: Bearer YOUR_API_KEY (full access, paginated response)
      - HTTP Basic auth or session (user-scoped access, no pagination)
      - No auth when scoped filters are present (public-privacy form items only;
        pagination required; see public_data_access module)
    Query Parameters:
        - template_id, assignment_id, submission_id, item_id, stable_key, version_scope, item_type,
          country_id, country_iso2, country_iso3, submission_type, period_name, indicator_bank_id: filters
        - date_from, date_to, sort, order, page, per_page
        - related: scope of related form_items ('page' or 'all'); default 'page'
        - layout: ``flat`` (default) or ``star`` (dimensional tables for BI)
        - include_dynamic / include_repeat: default true; pass ``false`` to omit extended arrays
        - include_non_reported, analysis, indicator_bank_ids: see data explorer / BI use cases
    """
    try:
        layout = _parse_tables_layout_param()

        # Authenticate request (or allow scoped public read — privacy='public' items only)
        public_data_access = False
        auth_result = authenticate_api_request()
        if hasattr(auth_result, 'status_code'):
            public_err = validate_public_data_request(request.args)
            if public_err is not None:
                return auth_result
            public_data_access = True
            elevated_access = False
            auth_user = None
            api_key_record = None
        else:
            elevated_access, auth_user, api_key_record = auth_result

        analysis_requested = str(request.args.get('analysis', '') or '').strip().lower() in ['1', 'true', 'yes', 'y']
        if analysis_requested and not elevated_access and auth_user is not None:
            from app.services.organization.authorization_service import AuthorizationService
            if not (
                AuthorizationService.is_system_manager(auth_user)
                or AuthorizationService.has_rbac_permission(auth_user, 'admin.data_explore.analysis')
            ):
                return api_error('Forbidden: analysis access is required', 403)

        template_id = request.args.get('template_id', type=int)
        assignment_id = request.args.get('assignment_id', type=int)
        if assignment_id is None:
            # Legacy alias
            assignment_id = request.args.get('assigned_form_id', type=int)
        # Prefer exact AssignedForm scope; derive template_id for version/item filters when omitted.
        if assignment_id is not None and template_id is None:
            af = AssignedForm.query.get(int(assignment_id))
            if af is None:
                return api_error('Assignment not found', 404)
            template_id = af.template_id
        submission_id = request.args.get('submission_id', type=int)
        item_id = request.args.get('item_id', type=int)
        item_id, stable_key_filter, version_scope, filter_error = parse_data_item_filters(
            request.args,
            template_id=template_id,
            item_id=item_id,
        )
        if filter_error:
            return api_error(filter_error['message'], filter_error['status'])

        published_version_id = resolve_template_published_version_id(template_id)

        item_type = request.args.get('item_type', type=str)
        country_id = request.args.get('country_id', type=int)
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
        if (country_iso2 or country_iso3) and not country_id:
            from app.utils.country_utils import resolve_country_from_iso
            resolved_id, error = resolve_country_from_iso(iso2=country_iso2, iso3=country_iso3)
            if error:
                status_code = 400 if 'Invalid' in error else 404
                return api_error(error, status_code)
            if resolved_id:
                country_id = resolved_id
        submission_type = request.args.get('submission_type')
        period_name = request.args.get('period_name', type=str)
        scope_meta = build_data_api_scope_meta(
            template_id=template_id,
            published_version_id=published_version_id,
            version_scope=version_scope,
            stable_key=stable_key_filter,
            assignment_id=assignment_id,
            period_name=period_name,
        )
        indicator_bank_id = request.args.get('indicator_bank_id', type=int)
        # Comma-separated indicator bank IDs for multi-indicator filtering.
        # Used by the disaggregation time-series call to fetch only the required
        # indicators (e.g. "722,724,727") instead of the full template dataset.
        _raw_ibids = (request.args.get('indicator_bank_ids') or '').strip()
        indicator_bank_ids: Optional[List[int]] = None
        if _raw_ibids:
            try:
                indicator_bank_ids = [int(x) for x in _raw_ibids.split(',') if x.strip().lstrip('-').isdigit()]
                indicator_bank_ids = [x for x in indicator_bank_ids if x > 0] or None
            except Exception:
                indicator_bank_ids = None
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

        # API key auth always paginates. Session auth paginates when per_page is requested
        # (e.g. data explorer sends per_page=10000); otherwise return all accessible rows.
        # Public anonymous access always paginates (capped page size).
        should_paginate = elevated_access or public_data_access

        # Validate and sanitize parameters
        if should_paginate:
            validated_params = validate_data_endpoint_params(request.args)
            page = validated_params['page']
            per_page = validated_params['per_page']
            if public_data_access:
                per_page = min(int(per_page), PUBLIC_DATA_MAX_PER_PAGE)
        else:
            page = 1
            per_page = None
            per_page_raw = request.args.get('per_page', default=None, type=int)
            if per_page_raw is not None and int(per_page_raw) > 0:
                page, per_page = validate_pagination_params(request.args)
                should_paginate = True

        related_scope = str(request.args.get('related', 'page')).strip().lower()
        if related_scope not in ('page', 'all'):
            related_scope = 'page'

        # Build queries via service layer for consistency.
        # form_item_info is never included in the star-schema response, so skip the
        # deep form_item joinedloads to avoid unnecessary joins on large datasets.
        queries = query_form_data(
            template_id=template_id,
            submission_id=submission_id,
            item_id=item_id,
            item_type=item_type,
            country_id=country_id,
            period_name=period_name,
            assignment_id=assignment_id,
            indicator_bank_id=indicator_bank_id,
            indicator_bank_ids=indicator_bank_ids,
            submission_type=submission_type,
            preload=True,
            full_preload=False,
        )
        assigned_form_data_query, public_form_data_query = get_form_data_queries(queries)

        # Apply date range filtering
        if date_from:
            # Ensure joins exist for assigned query
            # Note: queries are now guaranteed to be non-None by get_form_data_queries
            # Check if joins already exist
            if (
                template_id is None
                and country_id is None
                and period_name is None
                and assignment_id is None
            ):
                assigned_form_data_query = assigned_form_data_query.join(AssignmentEntityStatus)
            assigned_form_data_query = assigned_form_data_query.filter(FormData.submitted_at >= date_from)

            # Public query already has joins
            public_form_data_query = public_form_data_query.filter(FormData.submitted_at >= date_from)

        if date_to:
            # Ensure joins exist for assigned query
            # Check if joins already exist
            if (
                template_id is None
                and country_id is None
                and period_name is None
                and assignment_id is None
                and date_from is None
            ):
                assigned_form_data_query = assigned_form_data_query.join(AssignmentEntityStatus)
            assigned_form_data_query = assigned_form_data_query.filter(FormData.submitted_at <= date_to)

            # Public query already has joins
            public_form_data_query = public_form_data_query.filter(FormData.submitted_at <= date_to)

        # Optional allow-lists for assignment_statuses[] (None = unrestricted).
        aes_allowed_template_ids = None
        aes_allowed_country_ids = None

        def _assignment_statuses_for_scope(*row_lists):
            return _build_assignment_statuses_table(
                *row_lists,
                template_id=template_id,
                country_id=country_id,
                period_name=period_name,
                assignment_id=assignment_id,
                submission_id=submission_id,
                submission_type=submission_type,
                allowed_template_ids=aes_allowed_template_ids,
                allowed_country_ids=aes_allowed_country_ids,
            )

        # ---------- RBAC: if user-authenticated, restrict to templates the user owns or that are shared with them ----------
        if not elevated_access and auth_user is not None:
            # System managers have access to all templates
            from app.services.organization.authorization_service import AuthorizationService
            is_system_mgr = AuthorizationService.is_system_manager(auth_user)

            if not is_system_mgr:
                allowed_template_ids = get_user_allowed_template_ids(auth_user.id)
                if template_id is not None and template_id not in allowed_template_ids:
                    return api_error('Forbidden: no access to requested template', 403)
                aes_allowed_template_ids = allowed_template_ids
                aes_allowed_country_ids = _get_user_allowed_country_ids(auth_user)

            # Apply template scoping to queries
            scoped_queries = apply_user_template_scoping(
                queries,
                auth_user,
                template_id,
                country_id,
                period_name,
                assignment_id=assignment_id,
            )
            assigned_form_data_query, public_form_data_query = get_form_data_queries(scoped_queries)

            # If user has no access, return empty result.
            # IMPORTANT: Do NOT short-circuit when include_non_reported=1 for a bounded assigned scope,
            # because the caller may want virtual "missing" rows even when there are zero saved FormData rows.
            # Still return assignment_statuses for pending AES in scope (no FormData yet).
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
                            _inc_dyn, _inc_rep = _parse_include_flags(request.args)
                            _catalog = _build_data_array_catalog(
                                include_dynamic=_inc_dyn,
                                include_repeat=_inc_rep,
                            )
                            _countries = _load_full_countries_table()
                            _national_societies = _load_full_national_societies_table()
                            _indicator_bank = _load_full_indicator_bank_table()
                            _assignment_statuses = _assignment_statuses_for_scope()
                            if layout == 'star':
                                return _build_star_data_response(
                                    [], [], _countries, _national_societies, _indicator_bank, [],
                                    should_paginate=should_paginate,
                                    total_items=0,
                                    page=page,
                                    per_page=per_page,
                                    assignment_statuses=_assignment_statuses,
                                    scope_meta=scope_meta,
                                    array_catalog=_catalog,
                                )
                            return json_response(_assemble_flat_data_payload(
                                data_rows=[],
                                form_items_table=[],
                                countries_table=_countries,
                                national_societies_table=_national_societies,
                                indicator_bank_table=_indicator_bank,
                                matrix_cells=[],
                                assignment_statuses=_assignment_statuses,
                                total_items=0,
                                total_pages=None,
                                current_page=None,
                                per_page=None,
                                scope_meta=scope_meta,
                                array_catalog=_catalog,
                            ))

        # ---------- Scoped API key: restrict to template_ids / country_ids on the key ----------
        api_key_scope = getattr(g, 'api_key_data_scope', None)
        if not elevated_access and api_key_record is not None and api_key_scope:
            _key_templates = list(api_key_scope.get('template_ids') or [])
            _key_countries = list(api_key_scope.get('country_ids') or [])
            # Empty list on one dimension means unrestricted there; both empty = no access.
            if not _key_templates and not _key_countries:
                aes_allowed_template_ids = []
                aes_allowed_country_ids = []
            else:
                aes_allowed_template_ids = _key_templates or None
                aes_allowed_country_ids = _key_countries or None
            scoped_queries = apply_api_key_data_scoping(
                queries,
                api_key_scope,
                template_id,
                country_id,
                period_name,
                assignment_id=assignment_id,
            )
            assigned_form_data_query, public_form_data_query = get_form_data_queries(scoped_queries)
            if assigned_form_data_query is not None:
                with suppress(Exception):
                    test_count = assigned_form_data_query.limit(1).count()
                    if test_count == 0 and (
                        public_form_data_query is None
                        or public_form_data_query.limit(1).count() == 0
                    ):
                        bounded_missing_request = (
                            include_non_reported
                            and (not should_paginate)
                            and template_id is not None
                            and country_id is not None
                            and period_name
                            and str(submission_type or '').strip().lower() == 'assigned'
                        )
                        if not bounded_missing_request:
                            _inc_dyn, _inc_rep = _parse_include_flags(request.args)
                            _catalog = _build_data_array_catalog(
                                include_dynamic=_inc_dyn,
                                include_repeat=_inc_rep,
                            )
                            _countries = _load_full_countries_table()
                            _national_societies = _load_full_national_societies_table()
                            _indicator_bank = _load_full_indicator_bank_table()
                            _assignment_statuses = _assignment_statuses_for_scope()
                            if layout == 'star':
                                return _build_star_data_response(
                                    [], [], _countries, _national_societies, _indicator_bank, [],
                                    should_paginate=should_paginate,
                                    total_items=0,
                                    page=page,
                                    per_page=per_page,
                                    assignment_statuses=_assignment_statuses,
                                    scope_meta=scope_meta,
                                    array_catalog=_catalog,
                                )
                            return json_response(_assemble_flat_data_payload(
                                data_rows=[],
                                form_items_table=[],
                                countries_table=_countries,
                                national_societies_table=_national_societies,
                                indicator_bank_table=_indicator_bank,
                                matrix_cells=[],
                                assignment_statuses=_assignment_statuses,
                                total_items=0,
                                total_pages=None,
                                current_page=None,
                                per_page=None,
                                scope_meta=scope_meta,
                                array_catalog=_catalog,
                            ))

        assigned_form_data_query, public_form_data_query = apply_form_data_version_scoping(
            assigned_form_data_query,
            public_form_data_query,
            template_id=template_id,
            published_version_id=published_version_id,
            version_scope=version_scope,
            stable_key=stable_key_filter,
        )

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

        # Get data IDs (paginated for API key, capped for user auth) with sorting.
        # MAX_USER_AUTH_ROWS prevents runaway unbounded fetches on the session path.
        page_rows, total_items = get_paginated_data_ids(
            assigned_ids_q,
            public_ids_q,
            page if should_paginate else 1,
            per_page if should_paginate else None,
            paginate=should_paginate,
            sort_field=sort_field,
            sort_order=sort_order,
            max_rows=None if should_paginate else MAX_USER_AUTH_ROWS,
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
        # Collected inline while building data_rows below, so assignment_statuses[]
        # can be scoped without a second full pass over data_rows afterward.
        fact_assigned_submission_ids = set()

        # Collect form_item IDs from the current page for the related form_items table.
        # countries[] is always the full dimension (loaded later), so country_ids are not tracked here.
        for row in page_rows:
            if row.submission_type == 'assigned':
                data_item = assigned_map.get(row.id)
                if data_item and data_item.form_item_id:
                    form_item_ids.add(data_item.form_item_id)
            else:
                data_item = public_map.get(row.id)
                if data_item and data_item.form_item_id:
                    form_item_ids.add(data_item.form_item_id)

        # Now process rows (optimized: inline formatting to avoid function call overhead)
        # Note: form_items are loaded later when building related tables,
        # which allows for related_scope='all' expansion if needed
        for row in page_rows:
            if row.submission_type == 'assigned':
                data_item = assigned_map.get(row.id)
                if not data_item:
                    continue
                status_info = data_item.assignment_entity_status
                assigned_form = status_info.assigned_form if status_info else None
                # Use entity_id directly instead of country property to avoid queries.
                # Must not reuse request filter name ``country_id`` (would leak into
                # assignment_statuses / include_non_reported scoping below).
                row_country_id = (
                    status_info.entity_id
                    if (status_info and status_info.entity_type == 'country')
                    else None
                )

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

                # Exclude non-reported rows (no value, no disagg, no flags, no imputed) unless explicitly requested.
                if (not include_non_reported) and data_status == "available":
                    if (value is None) and (disagg_data_saved is None) and (not _has_any_aux_value(data_item)):
                        continue

                pdd = _normalize_disagg_raw(getattr(data_item, "prefilled_disagg_data", None))
                idd = _normalize_disagg_raw(getattr(data_item, "imputed_disagg_data", None))
                payload = {
                    'id': data_item.id,
                    'field_type': 'static',
                    'data_type': 'static',
                    'submission_type': 'assigned',
                    'submission_id': status_info.id if status_info else None,
                    'form_item_id': data_item.form_item_id,
                    'template_id': assigned_form.template_id if assigned_form else None,
                    'period_name': assigned_form.period_name if assigned_form else None,
                    'country_id': row_country_id,
                    'value': value,
                    'prefilled_value': getattr(data_item, "prefilled_value", None),
                    'imputed_value': getattr(data_item, "imputed_value", None),
                    'prefilled_disagg_data': getattr(data_item, "prefilled_disagg_data", None),
                    'imputed_disagg_data': getattr(data_item, "imputed_disagg_data", None),
                    'num_value': num_value,
                    'data_status': data_status,
                    'date_collected': submitted_at,
                    'submitted_at': submitted_at,
                    'disaggregation_data': (
                        _normalize_disagg_payload(disagg_data_saved) if disagg_data_saved else None
                    ),
                    'prefilled_disaggregation_data': (
                        _normalize_disagg_payload(pdd) if pdd else None
                    ),
                    'imputed_disaggregation_data': (
                        _normalize_disagg_payload(idd) if idd else None
                    ),
                }
                if status_info is not None:
                    fact_assigned_submission_ids.add(status_info.id)
                data_rows.append(payload)
            else:
                data_item = public_map.get(row.id)
                if not data_item:
                    continue
                submission = data_item.public_submission
                public_assignment = submission.assigned_form if submission else None
                # Use country_id directly instead of country relationship to avoid queries.
                # Must not reuse request filter name ``country_id`` (see assigned branch).
                row_country_id = submission.country_id if submission else None

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

                # Exclude non-reported rows (no value, no disagg, no flags, no imputed) unless explicitly requested.
                if (not include_non_reported) and data_status == "available":
                    if (value is None) and (disagg_data_saved is None) and (not _has_any_aux_value(data_item)):
                        continue

                pdd = _normalize_disagg_raw(getattr(data_item, "prefilled_disagg_data", None))
                idd = _normalize_disagg_raw(getattr(data_item, "imputed_disagg_data", None))
                payload = {
                    'id': data_item.id,
                    'field_type': 'static',
                    'data_type': 'static',
                    'submission_type': 'public',
                    'submission_id': submission.id if submission else None,
                    'assignment_id': public_assignment.id if public_assignment else None,
                    'form_item_id': data_item.form_item_id,
                    'template_id': public_assignment.template_id if public_assignment else None,
                    'period_name': public_assignment.period_name if public_assignment else None,
                    'country_id': row_country_id,
                    'value': value,
                    'prefilled_value': getattr(data_item, "prefilled_value", None),
                    'imputed_value': getattr(data_item, "imputed_value", None),
                    'prefilled_disagg_data': getattr(data_item, "prefilled_disagg_data", None),
                    'imputed_disagg_data': getattr(data_item, "imputed_disagg_data", None),
                    'num_value': num_value,
                    'data_status': data_status,
                    'date_collected': submitted_at,
                    'submitted_at': submitted_at,
                    'disaggregation_data': (
                        _normalize_disagg_payload(disagg_data_saved) if disagg_data_saved else None
                    ),
                    'prefilled_disaggregation_data': (
                        _normalize_disagg_payload(pdd) if pdd else None
                    ),
                    'imputed_disaggregation_data': (
                        _normalize_disagg_payload(idd) if idd else None
                    ),
                }
                data_rows.append(payload)

        # Optionally include non-reported (missing) form items as virtual rows (assigned submissions only).
        # This is intentionally only supported for user-auth (non-paginated) requests, and when
        # Template + Country + (assignment_id or period) are provided to keep the expansion bounded.
        if (
            include_non_reported
            and version_scope == VERSION_SCOPE_PUBLISHED
            and not should_paginate
            and template_id is not None
            and country_id is not None
            and (assignment_id is not None or period_name)
            and (not submission_type or str(submission_type).strip().lower() == 'assigned')
        ):
            try:
                # Resolve expected items for the template (respect item_id filter if provided)
                expected_items_q = FormItem.query.filter(
                    FormItem.template_id == int(template_id),
                    FormItem.archived == False,
                )

                # Scope expected items to the published template version (consistent with main query)
                if version_scope == VERSION_SCOPE_PUBLISHED and published_version_id:
                    expected_items_q = expected_items_q.filter(FormItem.version_id == int(published_version_id))

                # Apply privacy gating consistent with query_form_data
                viewer = get_effective_request_user()
                if not can_view_non_public_form_items(viewer):
                    expected_items_q = expected_items_q.filter(form_item_privacy_is_public_expr())

                if stable_key_filter:
                    expected_items_q = expected_items_q.filter(FormItem.stable_key == stable_key_filter)
                elif item_id is not None and int(item_id) > 0:
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
                        # 2) No assigned rows returned; fall back to a single matching assignment.
                        # Prefer exact assignment_id when provided (avoids period_name collisions).
                        af = None
                        if assignment_id is not None:
                            af = _AssignedForm.query.get(int(assignment_id))
                        if not af and period_name:
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
                            fact_assigned_submission_ids.add(aes_id)
                            for fid in expected_item_ids:
                                if (aes_id, int(fid)) in existing_set:
                                    continue
                                missing_count += 1
                                # Virtual id: stable, string; never persisted to the database.
                                virtual_id = f"m:{aes_id}:{int(fid)}"
                                data_rows.append({
                                    'id': virtual_id,
                                    'field_type': 'static',
                                    'data_type': 'static',
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
            except Exception as _e:
                # If any of the above expansions fail, log error and return partial result
                error_id = str(uuid.uuid4())
                current_app.logger.error(
                    f"related=all expansion failed in /data [ID: {error_id}]: {_e}",
                    exc_info=True,
                    extra={'endpoint': '/data', 'params': dict(request.args)}
                )
                expansion_failed = True

        # Optionally fetch dynamic indicator and repeat section data, folding their
        # form_item_ids into the related form_items table.
        include_dynamic, include_repeat = _parse_include_flags(request.args)
        if public_data_access:
            include_dynamic = False
            include_repeat = False
        array_catalog = _build_data_array_catalog(
            include_dynamic=include_dynamic,
            include_repeat=include_repeat,
        )
        extended = _fetch_extended_data(
            template_id=template_id,
            submission_id=submission_id,
            item_id=item_id,
            country_id=country_id,
            period_name=period_name,
            assignment_id=assignment_id,
            indicator_bank_id=indicator_bank_id,
            submission_type=submission_type,
            include_dynamic=include_dynamic,
            include_repeat=include_repeat,
            minimal_country_info=(per_page and per_page > 1000) or (not should_paginate),
            elevated_access=elevated_access,
            auth_user=auth_user,
            date_from=date_from,
            date_to=date_to,
        ) if (include_dynamic or include_repeat) else {
            'dynamic_data': [], 'repeat_data': [], 'dynamic_context': [], 'assigned_submission_ids': set(),
        }

        # Collect form_item_ids referenced by extended rows so they appear in form_items[].
        for rrow in extended.get('repeat_data', []):
            if rrow.get('form_item_id'):
                form_item_ids.add(rrow['form_item_id'])

        # Build related form_items from the collected id set (optimized with eager loading)
        form_items_table = []
        if form_item_ids:
            # Use eager loading to reduce N+1 queries
            from sqlalchemy.orm import joinedload
            form_items = query_filter_in_batches(
                FormItem.query.options(
                    joinedload(FormItem.form_section),
                    joinedload(FormItem.template),
                ),
                FormItem.id,
                list(form_item_ids),
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
        public_slim = public_data_access and not public_include_dimensions(request.args)
        extra_keys = {}
        if public_slim:
            data_rows = slim_public_data_rows(data_rows)
            form_items_table = []
            countries_table = []
            national_societies_table = []
            indicator_bank_table = []
            matrix_cells = []
            assignment_statuses_table = []
            array_catalog = None
        else:
            countries_table = _load_full_countries_table()
            national_societies_table = _load_full_national_societies_table()
            indicator_bank_table = _load_full_indicator_bank_table()
            # strip=True clears matrix values out of data_rows in the same pass that
            # extracts them into matrix_cells, avoiding a second full scan over data_rows.
            matrix_cells = build_matrix_cells_from_data_rows(data_rows, form_items_table, strip=True)
            matrix_cells = enrich_matrix_cells(
                matrix_cells,
                form_items_table,
                countries_table=countries_table,
                national_societies_table=national_societies_table,
                indicator_bank_table=indicator_bank_table,
            )

            if include_dynamic:
                extra_keys['dynamic_data'] = extended['dynamic_data']
                extra_keys['dynamic_context'] = extended.get('dynamic_context', [])
            if include_repeat:
                extra_keys['repeat_data'] = extended['repeat_data']

            # Union of assigned submission_ids already seen while building data_rows /
            # dynamic_data / repeat_data above — collected inline, so this is a cheap
            # set union rather than a second full scan over those (potentially large) lists.
            fact_assigned_submission_ids |= extended.get('assigned_submission_ids') or set()
            assignment_statuses_table = _assignment_statuses_for_scope(
                [
                    {'submission_type': 'assigned', 'submission_id': sid}
                    for sid in fact_assigned_submission_ids
                ]
            )
        if layout == 'star':
            response = _build_star_data_response(
                data_rows,
                form_items_table,
                countries_table,
                national_societies_table,
                indicator_bank_table,
                matrix_cells,
                should_paginate=should_paginate,
                total_items=total_items,
                page=page,
                per_page=per_page,
                expansion_failed=expansion_failed,
                extra=extra_keys or None,
                assignment_statuses=assignment_statuses_table,
                scope_meta=scope_meta,
                array_catalog=array_catalog,
            )
        else:
            response = _build_flat_data_response(
                data_rows,
                form_items_table,
                countries_table,
                national_societies_table,
                indicator_bank_table,
                matrix_cells,
                should_paginate=should_paginate,
                total_items=total_items,
                page=page,
                per_page=per_page,
                expansion_failed=expansion_failed,
                extra=extra_keys or None,
                assignment_statuses=assignment_statuses_table,
                scope_meta=scope_meta,
                array_catalog=array_catalog,
            )

        if public_data_access and hasattr(response, 'headers'):
            response.headers['Cache-Control'] = 'public, max-age=300, stale-while-revalidate=60'
            response.headers['X-Public-Data-Access'] = 'true'
        return response
    except Exception as e:
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            f"API Error [ID: {error_id}] fetching data: {e}",
            exc_info=True,
            extra={'endpoint': '/data', 'params': dict(request.args)}
        )
        return api_error("Could not fetch data", 500, error_id, None)


@api_bp.route('/data/tables', methods=['GET'])
def get_data_tables_legacy_redirect():
    """Legacy redirect — use GET /api/v1/data instead."""
    query_string = request.query_string.decode('utf-8')
    target = f'/api/v1/data?{query_string}' if query_string else '/api/v1/data'
    response = redirect(target, code=308)
    response.headers['Deprecation'] = 'true'
    response.headers['Link'] = '</api/v1/data>; rel="successor-version"'
    return response
