# Backoffice/app/routes/api/mobile/public_data.py
"""Public data routes: country map, sectors, indicator bank, FDRS overview, quiz.

Auth policy:
  - Truly public (no login required): countrymap, sectors-subsectors, indicator-bank,
    indicator-suggestions, data/periods, data/fdrs-overview, data/disaggregation-overview
    (global/regional for anonymous; country breakdown for authenticated org users), data/resources,
    data/unified-planning-config (appeals URL + unified planning type IDs for the mobile app),
    data/unified-planning-thumbnail (JPEG first page — server-rendered; IFRC URL allowlist;
    prefer POST JSON ``{"url_b64": "<base64url>"}`` so Azure WAF does not inspect raw IFRC URLs).
    Rate-limited to prevent abuse.
  - Auth-required: quiz/leaderboard, quiz/submit-score (scores are tied to authenticated users).
"""

from flask import request, current_app
from flask_login import current_user

from app.utils.api_pagination import validate_pagination_params
from app.utils.mobile_auth import mobile_auth_required
from app.utils.rate_limiting import mobile_rate_limit
from app import db
from app.utils.mobile_responses import (
    mobile_ok,
    mobile_bad_request,
    mobile_server_error,
    mobile_paginated,
    mobile_not_found,
    mobile_created,
    mobile_error,
)
from app.utils.transactions import request_transaction_rollback
from app.utils.sql_utils import safe_ilike_pattern
from app.utils.sector_logo_urls import sector_logo_url
from app.routes.api.mobile import mobile_bp
# In-process JPEG cache lives in plugins.upr.mobile.


@mobile_bp.route('/data/countrymap', methods=['GET'])
@mobile_rate_limit(requests_per_minute=60)
def countrymap():
    """Country map data for the mobile shell.

    Intentionally public and rate-limited. ``GET /api/v1/countrymap`` stays behind
    an API key or session because that prefix is the integration API.
    """
    from app.models import Country

    locale = request.args.get('locale', 'en')
    countries = Country.query.order_by(Country.name.asc()).all()

    items = []
    for c in countries:
        name = c.name
        if locale != 'en' and hasattr(c, f'name_{locale}'):
            name = getattr(c, f'name_{locale}', None) or c.name
        items.append({
            'id': c.id,
            'name': name,
            'iso2': getattr(c, 'iso2', None),
            'iso3': getattr(c, 'iso3', None),
            'region': getattr(c, 'region', None),
        })

    return mobile_ok(data={'countries': items}, meta={'total': len(items)})


@mobile_bp.route('/data/sectors-subsectors', methods=['GET'])
@mobile_rate_limit(requests_per_minute=60)
def sectors_subsectors():
    """List sectors and nested subsectors (same shape as /api/v1/sectors-subsectors)."""
    from app.models import Sector, SubSector

    sectors = Sector.query.filter_by(is_active=True).order_by(
        Sector.display_order, Sector.name
    ).all()

    sector_ids = [s.id for s in sectors]
    all_subsectors = (
        SubSector.query
        .filter(SubSector.sector_id.in_(sector_ids), SubSector.is_active == True)  # noqa: E712
        .order_by(SubSector.display_order, SubSector.name)
        .all()
    ) if sector_ids else []
    subsectors_by_sector: dict = {}
    for ss in all_subsectors:
        subsectors_by_sector.setdefault(ss.sector_id, []).append(ss)

    sectors_data = []
    for sector in sectors:
        subsectors = subsectors_by_sector.get(sector.id, [])

        subsectors_data = []
        for subsector in subsectors:
            multilingual_subsector_names = (
                subsector.name_translations
                if isinstance(getattr(subsector, 'name_translations', None), dict)
                else {}
            )
            subsectors_data.append({
                'id': subsector.id,
                'name': subsector.name,
                'description': subsector.description,
                'display_order': subsector.display_order,
                'multilingual_names': multilingual_subsector_names,
                'sector_id': subsector.sector_id,
            })

        multilingual_sector_names = (
            sector.name_translations
            if isinstance(getattr(sector, 'name_translations', None), dict)
            else {}
        )

        sectors_data.append({
            'id': sector.id,
            'name': sector.name,
            'description': sector.description,
            'display_order': sector.display_order,
            'logo_url': sector_logo_url(sector, external=True, via_api=True),
            'icon_class': sector.icon_class,
            'multilingual_names': multilingual_sector_names,
            'subsectors': subsectors_data,
        })

    return mobile_ok(data={'sectors': sectors_data})


@mobile_bp.route('/data/indicator-bank', methods=['GET'])
@mobile_rate_limit(requests_per_minute=60)
def public_indicator_bank():
    """Public indicator bank listing (mirrors /api/v1/indicator-bank)."""
    from app.services.indicators.bank_service import IndicatorBankFilters, get_indicator_list

    page, per_page = validate_pagination_params(
        request.args, default_per_page=500, max_per_page=2000
    )
    filters = IndicatorBankFilters(
        search=request.args.get('search', default='', type=str).strip(),
        indicator_type=request.args.get('type', default='', type=str).strip(),
        sector=request.args.get('sector', default='', type=str).strip(),
        sub_sector=request.args.get('sub_sector', default='', type=str).strip(),
        emergency=request.args.get('emergency', default='', type=str).strip(),
        archived=request.args.get('archived', default=None),
        sector_id=request.args.get('sector_id', type=int),
    )
    items, total, page_out, per_page_out = get_indicator_list(
        filters, page=page, per_page=per_page
    )
    return mobile_paginated(
        items=items,
        total=total,
        page=page_out or page,
        per_page=per_page_out or per_page,
    )


@mobile_bp.route('/data/indicator-bank/<int:indicator_id>', methods=['GET'])
@mobile_rate_limit(requests_per_minute=120)
def public_indicator_detail(indicator_id):
    """Single indicator detail (public) — fully localized."""
    from app.models import IndicatorBank
    from app.services.indicators.bank_service import serialize_indicator_list

    indicator = IndicatorBank.query.get(indicator_id)
    if not indicator:
        return mobile_not_found('Indicator not found')

    indicator_data = serialize_indicator_list([indicator])[0]
    return mobile_ok(data={'indicator': indicator_data})


@mobile_bp.route('/data/indicator-suggestions', methods=['POST'])
@mobile_rate_limit(requests_per_minute=5, shared=True)
def submit_indicator_suggestion():
    """Submit an indicator suggestion (same JSON body as POST /api/v1/indicator-suggestions).

    Anonymous by design (the app offers it before login), so abuse controls are layered:
    shared-store rate limit, strict payload validation and size caps, DB-backed per-email and
    global caps, and an optional reCAPTCHA token (``token``) when
    ``MOBILE_SUGGESTION_REQUIRE_CAPTCHA`` is enabled.
    """
    from app.models import IndicatorSuggestion
    from app.utils.api_helpers import get_json_safe
    from app.utils.suggestion_intake import (
        SuggestionValidationError,
        suggestion_throttle_error,
        validate_suggestion_payload,
    )

    try:
        data = get_json_safe()
        if not isinstance(data, dict):
            return mobile_bad_request('Request body must be a JSON object')

        if current_app.config.get('MOBILE_SUGGESTION_REQUIRE_CAPTCHA'):
            from app.routes.api.indicator_bank_compat import _verify_recaptcha

            token = data.get('token')
            if not isinstance(token, str) or not _verify_recaptcha(token):
                return mobile_bad_request('reCAPTCHA validation failed')

        try:
            values = validate_suggestion_payload(data)
        except SuggestionValidationError as validation_error:
            return mobile_bad_request(validation_error.public_message)

        throttle_message = suggestion_throttle_error(values['submitter_email'])
        if throttle_message:
            return mobile_error(throttle_message, 429, error_code='RATE_LIMIT_EXCEEDED', retry_after=3600)

        suggestion = IndicatorSuggestion(**values)

        db.session.add(suggestion)
        db.session.flush()

        try:
            from app.services.email.service import (
                send_suggestion_confirmation_email,
                send_admin_notification_email,
            )

            send_suggestion_confirmation_email(suggestion)
            send_admin_notification_email(suggestion)
        except Exception as email_error:
            current_app.logger.error(
                'Failed to send emails for suggestion %s: %s',
                suggestion.id,
                email_error,
            )

        return mobile_created(
            data={'suggestion_id': suggestion.id},
            message='Suggestion submitted successfully',
        )
    except Exception as e:
        current_app.logger.error('submit_indicator_suggestion: %s', e, exc_info=True)
        request_transaction_rollback()
        return mobile_server_error()


def _mobile_require_json_keys(data, keys):
    """Like require_json_keys for mobile: return mobile_bad_request or None."""
    if not isinstance(data, dict):
        return mobile_bad_request('Invalid request body.')
    missing = [k for k in keys if k not in data or data[k] is None]
    if missing:
        return mobile_bad_request(f"Missing required: {', '.join(missing)}")
    return None


@mobile_bp.route('/data/quiz/leaderboard', methods=['GET'])
@mobile_auth_required
@mobile_rate_limit(requests_per_minute=60)
def quiz_leaderboard():
    """Quiz leaderboard (mirrors /api/v1/quiz/leaderboard).

    Scores are stored on ``User.quiz_score`` (additive total per user), not a
    separate per-attempt table.
    """
    from sqlalchemy import desc
    from app.models import User

    limit = request.args.get('limit', default=20, type=int)
    if limit < 1 or limit > 100:
        limit = 20

    top_users = (
        User.query.filter(
            User.active == True,  # noqa: E712
            User.quiz_score > 0,
        )
        .order_by(desc(User.quiz_score), User.name.asc())
        .limit(limit)
        .all()
    )

    items = []
    for rank, user in enumerate(top_users, start=1):
        items.append({
            'rank': rank,
            'name': user.name or (
                user.email.split('@')[0] if user.email else 'User'
            ),
            'score': user.quiz_score or 0,
        })

    return mobile_ok(data={'leaderboard': items}, meta={'total': len(items)})


@mobile_bp.route('/data/periods', methods=['GET'])
@mobile_rate_limit(requests_per_minute=60)
def mobile_periods():
    """Distinct FDRS period names, newest first (mobile replacement for /api/v1/periods).

    Query params:
      - template_id (optional, default 21 — FDRS): scope to a specific form template
      - country_id (optional): scope to one country's assignments/submissions
    """
    import re
    from app.models import AssignedForm, PublicSubmission
    from app.utils.data_quality_constants import FDRS_TEMPLATE_ID

    template_id = request.args.get('template_id', FDRS_TEMPLATE_ID, type=int)
    country_id = request.args.get('country_id', type=int)

    try:
        periods_set = set()

        assigned_query = (
            db.session.query(AssignedForm.period_name)
            .distinct()
            .filter(AssignedForm.template_id == template_id)
        )
        if country_id:
            from app.models.assignments import AssignmentEntityStatus
            assigned_query = assigned_query.join(AssignmentEntityStatus).filter(
                AssignmentEntityStatus.entity_id == country_id,
                AssignmentEntityStatus.entity_type == 'country',
            )
        for (period_name,) in assigned_query.filter(AssignedForm.period_name.isnot(None)).all():
            if period_name:
                periods_set.add(period_name)

        public_query = (
            db.session.query(AssignedForm.period_name)
            .distinct()
            .join(PublicSubmission, AssignedForm.id == PublicSubmission.assigned_form_id)
            .filter(AssignedForm.template_id == template_id)
        )
        if country_id:
            public_query = public_query.filter(PublicSubmission.country_id == country_id)
        for (period_name,) in public_query.filter(AssignedForm.period_name.isnot(None)).all():
            if period_name:
                periods_set.add(period_name)

        from app.services.forms.reporting_period_service import sort_period_names

        sorted_periods = sort_period_names(list(periods_set))
        return mobile_ok(data={'periods': sorted_periods})
    except Exception as e:
        current_app.logger.error('mobile_periods: %s', e, exc_info=True)
        return mobile_ok(data={'periods': []})


@mobile_bp.route('/data/fdrs-overview', methods=['GET'])
@mobile_rate_limit(requests_per_minute=30)
def mobile_fdrs_overview():
    """Pre-aggregated FDRS indicator totals per country (mobile-optimised)."""
    from plugins.fdrs.mobile import fdrs_overview as _impl

    return _impl()


@mobile_bp.route('/data/disaggregation-overview', methods=['GET'])
@mobile_rate_limit(requests_per_minute=30)
def mobile_disaggregation_overview():
    """Pre-aggregated sex/age/regional/country disaggregation breakdown for mobile analytics.

    Figures come from the published snapshot (never the live editable value) and only
    from form items marked privacy=public. Anonymous callers receive global + regional
    aggregates only. Authenticated organization users (IFRC staff, focal points with
    country access, data-explore RBAC) may receive per-country breakdowns scoped to
    their permitted countries.

    Query params:
      - indicator_bank_id (optional, default 729 — people reached)
      - template_id (optional, default 21 — FDRS)
      - period_name (optional): filter to one reporting period
      - country_id (optional, org users only): filter to one country
      - locale (optional, default 'en'): localized country names
    """
    from app.models import FormData, Country, AssignedForm, PublicSubmission
    from app.models.assignments import AssignmentEntityStatus
    from app.services.organization.authorization_service import AuthorizationService
    from plugins.fdrs.published_facts import public_form_item_ids, published_snapshot_clause
    from app.utils.mobile_disaggregation import (
        aggregate_disaggregation_rows,
        can_view_disaggregation_country_details,
        get_disaggregation_country_scope,
        resolve_optional_mobile_user,
    )

    indicator_bank_id = request.args.get('indicator_bank_id', 729, type=int)
    template_id = request.args.get('template_id', 21, type=int)
    period_name = request.args.get('period_name', type=str) or None
    requested_country_id = request.args.get('country_id', type=int)
    locale = request.args.get('locale', 'en')

    user = resolve_optional_mobile_user()
    include_country_breakdown = can_view_disaggregation_country_details(user)
    country_scope = (
        get_disaggregation_country_scope(user) if include_country_breakdown else set()
    )

    country_id = requested_country_id if include_country_breakdown else None
    if (
        country_id
        and country_scope is not None
        and country_id not in country_scope
        and not AuthorizationService.has_country_access(user, country_id)
    ):
        country_id = None

    empty_payload = {
        'period_name': period_name,
        'indicator_bank_id': indicator_bank_id,
        'total': 0,
        'record_count': 0,
        'disaggregated_count': 0,
        'disaggregation_rate': 0,
        'by_sex': [],
        'by_age': [],
        'by_country': [],
        'by_region': [],
        'trends': [],
        'country_details_available': include_country_breakdown,
    }

    try:
        form_item_ids = public_form_item_ids(
            indicator_bank_id=indicator_bank_id,
            template_id=template_id,
        )
        if not form_item_ids:
            return mobile_ok(data=empty_payload)

        aes_q = (
            db.session.query(
                AssignmentEntityStatus.entity_id,
                AssignedForm.period_name,
                FormData.published_value,
                FormData.published_disagg_data,
            )
            .join(FormData, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
            .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
            .filter(
                FormData.form_item_id.in_(form_item_ids),
                AssignmentEntityStatus.entity_type == 'country',
                published_snapshot_clause(),
            )
        )
        if template_id:
            aes_q = aes_q.filter(AssignedForm.template_id == template_id)
        if period_name:
            aes_q = aes_q.filter(AssignedForm.period_name == period_name)
        if country_id:
            aes_q = aes_q.filter(AssignmentEntityStatus.entity_id == country_id)
        elif include_country_breakdown and country_scope is not None and len(country_scope) > 0:
            aes_q = aes_q.filter(AssignmentEntityStatus.entity_id.in_(list(country_scope)))

        pub_q = (
            db.session.query(
                PublicSubmission.country_id,
                AssignedForm.period_name,
                FormData.published_value,
                FormData.published_disagg_data,
            )
            .join(FormData, FormData.public_submission_id == PublicSubmission.id)
            .join(AssignedForm, AssignedForm.id == PublicSubmission.assigned_form_id)
            .filter(
                FormData.form_item_id.in_(form_item_ids),
                PublicSubmission.country_id.isnot(None),
                published_snapshot_clause(),
            )
        )
        if template_id:
            pub_q = pub_q.filter(AssignedForm.template_id == template_id)
        if period_name:
            pub_q = pub_q.filter(AssignedForm.period_name == period_name)
        if country_id:
            pub_q = pub_q.filter(PublicSubmission.country_id == country_id)
        elif include_country_breakdown and country_scope is not None and len(country_scope) > 0:
            pub_q = pub_q.filter(PublicSubmission.country_id.in_(list(country_scope)))

        rows = []
        country_ids = set()
        for cid, p_name, value, disagg in list(aes_q.all()) + list(pub_q.all()):
            if not cid:
                continue
            cid_int = int(cid)
            if (
                include_country_breakdown
                and country_scope is not None
                and len(country_scope) > 0
                and cid_int not in country_scope
            ):
                continue
            country_ids.add(cid_int)
            rows.append((cid_int, p_name or '', value, disagg, indicator_bank_id))

        countries = (
            Country.query.filter(Country.id.in_(list(country_ids))).all()
            if country_ids
            else []
        )
        country_names = {}
        country_regions = {}
        for c in countries:
            name = c.name
            if locale != 'en':
                localized = getattr(c, f'name_{locale}', None)
                if localized:
                    name = localized
            country_names[c.id] = name
            country_regions[c.id] = c.region or 'Other'

        payload = aggregate_disaggregation_rows(
            rows,
            country_names=country_names,
            country_regions=country_regions,
            include_country_breakdown=include_country_breakdown,
        )
        payload['period_name'] = period_name
        payload['indicator_bank_id'] = indicator_bank_id
        if country_id:
            payload['country_id'] = country_id
        payload['country_details_available'] = include_country_breakdown

        return mobile_ok(data=payload)
    except Exception as e:
        current_app.logger.error('mobile_disaggregation_overview: %s', e, exc_info=True)
        return mobile_server_error('Failed to load disaggregation overview data.')


def _serialize_public_resource(r, *, locale: str, base_url: str, storage) -> dict:
    """Build the public JSON object for one Resource row (mobile /data/resources)."""
    title = r.get_title(locale)
    description = r.get_description(locale)

    def _resolve_locale(get_path_attr):
        """Return language code for the first lang with a real file."""
        for lang in ([locale] if locale == 'en' else [locale, 'en']):
            tr = r.get_translation(lang)
            if not tr:
                continue
            rel = getattr(tr, get_path_attr, None)
            if rel and storage.exists(storage.RESOURCES, rel):
                return lang
        return None

    file_locale = _resolve_locale('file_relative_path')
    thumb_locale = _resolve_locale('thumbnail_relative_path')

    file_url = (
        f"{base_url}/resources/download/{r.id}/{file_locale}"
        if file_locale else None
    )
    thumbnail_url = (
        f"{base_url}/resources/thumbnail/{r.id}/{thumb_locale}"
        if thumb_locale else None
    )

    sub = r.resource_subcategory
    sub_payload = None
    if sub is not None:
        sub_payload = {
            'id': sub.id,
            'name': sub.name,
            'display_order': sub.display_order,
        }

    return {
        'id': r.id,
        'title': title,
        'description': description,
        'resource_type': r.resource_type,
        'publication_date': r.publication_date.isoformat() if r.publication_date else None,
        'created_at': r.created_at.isoformat() if r.created_at else None,
        'file_url': file_url,
        'thumbnail_url': thumbnail_url,
        'available_languages': r.get_available_languages(),
        'file_languages': [
            t.language_code
            for t in r.translations
            if t.has_uploaded_document
        ],
        'subcategory': sub_payload,
    }


@mobile_bp.route('/data/resources', methods=['GET'])
@mobile_rate_limit(requests_per_minute=60)
def public_resources():
    """Paginated public resources/publications listing (no JWT required; rate-limited).

    Query params:
      - page, per_page: pagination (default 20, max 100)
      - search: filter by title
      - type: filter by resource_type ('publication' | 'resource' | 'document' | 'other')
      - locale: language code for title/description (default 'en')
      - grouped: when ``true`` and ``search`` is empty, return ``data.sections`` instead
        of a flat list — each section is a subgroup with its resources (global sort preserved).
        Response is capped (see ``meta.max_resources``) so the payload stays bounded.
    """
    from sqlalchemy.orm import joinedload
    from app.models.documents import Resource, ResourceSubcategory

    page, per_page = validate_pagination_params(
        request.args, default_per_page=20, max_per_page=100
    )
    search = request.args.get('search', '').strip()
    resource_type = request.args.get('type', '').strip()
    locale = (request.args.get('locale', 'en') or 'en').strip().lower()
    grouped_raw = (request.args.get('grouped', '') or '').strip().lower()
    grouped = grouped_raw in ('1', 'true', 'yes')

    filtered = Resource.query.options(joinedload(Resource.resource_subcategory))
    if search:
        filtered = filtered.filter(Resource.default_title.ilike(safe_ilike_pattern(search)))
    if resource_type:
        filtered = filtered.filter(Resource.resource_type == resource_type)

    sorted_q = filtered.order_by(
        Resource.publication_date.desc(),
        Resource.created_at.desc(),
    )

    base_url = request.host_url.rstrip('/')
    from app.services.platform import storage_service as storage

    if grouped and not search:
        max_resources = 400
        total_in_db = filtered.count()
        rows = sorted_q.limit(max_resources).all()
        subcategories = (
            ResourceSubcategory.query.order_by(
                ResourceSubcategory.display_order.asc(),
                ResourceSubcategory.name.asc(),
            ).all()
        )
        known_ids = {s.id for s in subcategories}
        buckets = {sid: [] for sid in known_ids}
        uncategorized: list = []

        for r in rows:
            item = _serialize_public_resource(r, locale=locale, base_url=base_url, storage=storage)
            sid = r.resource_subcategory_id
            if sid and sid in known_ids:
                buckets[sid].append(item)
            else:
                uncategorized.append(item)

        sections = []
        for s in subcategories:
            items = buckets.get(s.id) or []
            if not items:
                continue
            sections.append({
                'subcategory': {
                    'id': s.id,
                    'name': s.name,
                    'display_order': s.display_order,
                },
                'resources': items,
            })
        if uncategorized:
            sections.append({
                'subcategory': None,
                'resources': uncategorized,
            })

        return mobile_ok(
            data={'sections': sections},
            meta={
                'mode': 'grouped',
                'total_resources': total_in_db,
                'returned_resources': len(rows),
                'max_resources': max_resources,
                'capped': len(rows) >= max_resources and total_in_db > len(rows),
            },
        )

    paginated = sorted_q.paginate(page=page, per_page=per_page, error_out=False)
    items = [
        _serialize_public_resource(r, locale=locale, base_url=base_url, storage=storage)
        for r in paginated.items
    ]

    return mobile_paginated(
        items=items,
        total=paginated.total,
        page=paginated.page,
        per_page=paginated.per_page,
    )


@mobile_bp.route('/data/unified-planning-config', methods=['GET'])
@mobile_rate_limit(requests_per_minute=60)
def unified_planning_config():
    """Public config for unified planning documents: appeals API URL and type IDs."""
    from plugins.upr.mobile import unified_planning_config as _impl

    return _impl()


@mobile_bp.route('/data/unified-planning-thumbnail', methods=['GET', 'POST'])
@mobile_rate_limit(requests_per_minute=120)
def unified_planning_thumbnail():
    """Return a small JPEG of the PDF first page for unified-planning grid tiles."""
    from plugins.upr.mobile import unified_planning_thumbnail as _impl

    return _impl()


@mobile_bp.route('/data/quiz/submit-score', methods=['POST'])
@mobile_rate_limit(requests_per_minute=10)
@mobile_auth_required
def submit_quiz_score():
    """Submit a quiz score (mirrors /api/v1/quiz/submit-score).

    Points are added to the authenticated user's ``User.quiz_score`` (same as
    the session-based v1 endpoint). The client should send only ``score``;
    identity comes from the JWT.
    """
    from app.utils.api_helpers import get_json_safe

    data = get_json_safe()
    score = data.get('score')
    if score is None:
        return mobile_bad_request('score is required')
    if not isinstance(score, int) or score < 0 or score > 100:
        return mobile_bad_request('Invalid score. Must be an integer from 0 to 100.')

    try:
        user = current_user
        user.quiz_score = (user.quiz_score or 0) + score
        db.session.flush()
        return mobile_ok(
            message='Score submitted',
            data={
                'user_id': user.id,
                'total_score': user.quiz_score,
                'points_added': score,
            },
        )
    except Exception as e:
        current_app.logger.error("submit_quiz_score: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()
