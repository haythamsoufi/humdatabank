"""Public API for the FDRS published-data feed.

``GET /api/v1/fdrs/published-data`` is the one external-facing endpoint this
plugin exposes so a public website can pull FDRS figures. It only ever reads the
published snapshot (``FormData.published_value`` / ``published_disagg_data`` /
``published_numeric_value`` / ``published_source``), written when an admin runs the "Manage Publication"
tool (``plugins/fdrs/publication_routes.py``) — never the live/editable ``value``.
See ``plugins/fdrs/services/fdrs_publication_service.py`` for how that snapshot is
filled.

Auth: Bearer API key *or* an authenticated Backoffice session (same as
``/api/v1/data``). External consumers provision a key via Admin > API Keys;
logged-in admins can open the URL in the browser. Register the route in
Admin → API Management via ``API_ENDPOINTS`` / ``FdrsPlugin.get_api_endpoints()``.
"""

from __future__ import annotations

from flask import request

from app.extensions import db
from app.models import AssignedForm, Country, FormData, FormItem
from app.models.assignments import AssignmentEntityStatus
from app.services.data_retrieval.shared import form_item_privacy_is_public_expr
from app.utils.api_helpers import (
    DEFAULT_PAGE,
    DEFAULT_PER_PAGE,
    GENERIC_ERROR_MESSAGE,
    MAX_PER_PAGE,
    api_error,
    json_data_response,
)
from app.utils.auth import require_api_key_or_session
from app.utils.data_quality_constants import FDRS_TEMPLATE_ID
from app.utils.error_handling import handle_json_view_exception
from plugins.fdrs import bp

# Owned by this plugin — PluginManager merges these into API Management.
API_ENDPOINTS = [
    {
        "group": "FDRS",
        "path": "/api/v1/fdrs/published-data",
        "methods": ["GET"],
        "auth": "api_key_or_session",
        "rate_limited": True,
        "featured": True,
        "description": (
            "Published FDRS figures for the public website (published_* snapshot only). "
            "Bearer API key or an authenticated Backoffice session. "
            "Each row includes value_source (reported | imputed | null). "
            "Filters: period_name, assignment_id, country_id / country_iso2 / country_iso3, "
            "form_item_id, page, per_page."
        ),
        "consumers": "Public website, Backoffice session",
    },
]


@bp.route("/api/v1/fdrs/published-data", methods=["GET"])
@require_api_key_or_session
def get_fdrs_published_data():
    """
    Published FDRS figures for the public website integration.

    Only returns rows that have actually been published (``published_value`` or
    ``published_disagg_data`` set) for form items marked ``privacy='public'``, on
    FDRS (template 21) country-level assignments. Never exposes an unpublished /
    draft value, even if one exists.

    Query parameters:
      - ``period_name``: exact FDRS reporting period (e.g. ``"2024"``)
      - ``assignment_id``: ``AssignedForm.id`` (one FDRS reporting round)
      - ``country_id`` / ``country_iso2`` / ``country_iso3``
      - ``form_item_id``
      - ``page``, ``per_page`` (default 20, max 100000)
    """
    try:
        # NOTE: no `or DEFAULT_*` fallback here — `request.args.get(..., type=int)` already
        # returns the default for a missing/unparseable param; an `or` fallback would also
        # silently coerce an explicit page=0/per_page=0 to the default, making the checks
        # below unreachable for zero (only negative values would ever trip them).
        page = request.args.get('page', DEFAULT_PAGE, type=int)
        per_page = request.args.get('per_page', DEFAULT_PER_PAGE, type=int)
        if page < 1:
            return api_error('page must be >= 1', 400)
        if per_page < 1 or per_page > MAX_PER_PAGE:
            return api_error(f'per_page must be between 1 and {MAX_PER_PAGE}', 400)

        public_item_ids = [
            row.id for row in (
                FormItem.query
                .filter(FormItem.template_id == FDRS_TEMPLATE_ID)
                .filter(form_item_privacy_is_public_expr())
                .with_entities(FormItem.id)
                .all()
            )
        ]
        if not public_item_ids:
            return json_data_response([], meta={'total': 0, 'page': page, 'per_page': per_page, 'total_pages': 0})

        query = (
            db.session.query(
                FormData.id,
                FormData.form_item_id,
                FormData.published_value,
                FormData.published_numeric_value,
                FormData.published_disagg_data,
                FormData.published_source,
                FormData.published_at,
                AssignmentEntityStatus.id.label('submission_id'),
                AssignedForm.id.label('assignment_id'),
                AssignedForm.period_name,
                Country.id.label('country_id'),
                Country.name.label('country_name'),
                Country.iso2,
                Country.iso3,
                FormItem.label.label('item_label'),
                FormItem.stable_key,
                FormItem.indicator_bank_id,
            )
            .select_from(FormData)
            .join(AssignmentEntityStatus, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
            .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
            .join(FormItem, FormData.form_item_id == FormItem.id)
            .join(Country, Country.id == AssignmentEntityStatus.entity_id)
            .filter(AssignedForm.template_id == FDRS_TEMPLATE_ID)
            .filter(AssignmentEntityStatus.entity_type == 'country')
            .filter(FormData.form_item_id.in_(public_item_ids))
            .filter(
                db.or_(
                    FormData.published_value.isnot(None),
                    FormData.published_disagg_data.isnot(None),
                )
            )
        )

        period_name = (request.args.get('period_name') or '').strip()
        if period_name:
            query = query.filter(AssignedForm.period_name == period_name)

        assignment_id = request.args.get('assignment_id', type=int)
        if assignment_id is not None:
            query = query.filter(AssignedForm.id == assignment_id)

        country_id = request.args.get('country_id', type=int)
        if country_id is not None:
            query = query.filter(Country.id == country_id)

        country_iso2 = (request.args.get('country_iso2') or '').strip().upper()[:2]
        if country_iso2 and country_iso2.isalpha():
            query = query.filter(Country.iso2 == country_iso2)

        country_iso3 = (request.args.get('country_iso3') or '').strip().upper()[:3]
        if country_iso3 and country_iso3.isalpha():
            query = query.filter(Country.iso3 == country_iso3)

        form_item_id = request.args.get('form_item_id', type=int)
        if form_item_id is not None:
            query = query.filter(FormData.form_item_id == form_item_id)

        total = query.count()
        total_pages = (total + per_page - 1) // per_page if per_page > 0 else 1

        rows = (
            query
            .order_by(
                AssignedForm.period_name.desc(),
                Country.name.asc(),
                FormData.form_item_id.asc(),
            )
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        data = [
            {
                'submission_id': r.submission_id,
                'assignment_id': r.assignment_id,
                'period_name': r.period_name,
                'country_id': r.country_id,
                'country_name': r.country_name,
                'iso2': r.iso2,
                'iso3': r.iso3,
                'form_item_id': r.form_item_id,
                'stable_key': r.stable_key,
                'indicator_bank_id': r.indicator_bank_id,
                'item_label': r.item_label,
                'value': r.published_value,
                'num_value': r.published_numeric_value,
                'disaggregation_data': r.published_disagg_data,
                'value_source': r.published_source,
                'data_status': (
                    'no_data' if FormData._is_blank_value(r.published_value, r.published_disagg_data)
                    else 'available'
                ),
                'published_at': r.published_at.isoformat() if r.published_at else None,
            }
            for r in rows
        ]

        return json_data_response(
            data,
            meta={'total': total, 'page': page, 'per_page': per_page, 'total_pages': total_pages},
        )
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)
