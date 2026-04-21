# Backoffice/app/routes/api/mobile/public_data.py
"""Public data routes: country map, sectors, indicator bank, FDRS overview, quiz.

Auth policy:
  - Truly public (no login required): countrymap, sectors-subsectors, indicator-bank,
    indicator-suggestions, data/periods, data/fdrs-overview, data/resources,
    data/unified-planning-config (IFRC GO URL + unified planning type IDs for the mobile app),
    data/unified-planning-thumbnail (JPEG first page — server-rendered; IFRC URL allowlist;
    prefer POST JSON ``{"url_b64": "<base64url>"}`` so Azure WAF does not inspect raw IFRC URLs).
    Rate-limited to prevent abuse.
  - Auth-required: quiz/leaderboard, quiz/submit-score (scores are tied to authenticated users).
"""

from collections import OrderedDict
from contextlib import suppress
from hashlib import sha256
from threading import Lock

from flask import request, current_app, make_response
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
)
from app.utils.transactions import request_transaction_rollback
from app.utils.sql_utils import safe_ilike_pattern
from app.routes.api.mobile import mobile_bp
from app.utils.constants import APPEALS_TYPE_DEFAULT_IDS_STR, APPEALS_TYPE_DISPLAY_NAMES

# In-process JPEG cache for unified-planning thumbnails (key = sha256 of URL).
_UNIFIED_PLANNING_THUMB_JPEG: "OrderedDict[str, bytes]" = OrderedDict()
_UNIFIED_PLANNING_THUMB_LOCK = Lock()
_UNIFIED_PLANNING_THUMB_MAX_ENTRIES = 128


@mobile_bp.route('/data/countrymap', methods=['GET'])
@mobile_rate_limit(requests_per_minute=60)
def countrymap():
    """Country map data (mirrors /api/v1/countrymap)."""
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

    sectors_data = []
    for sector in sectors:
        subsectors = SubSector.query.filter_by(
            sector_id=sector.id, is_active=True
        ).order_by(SubSector.display_order, SubSector.name).all()

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
                'logo_url': (
                    f"{request.host_url.rstrip('/')}/api/v1/uploads/subsectors/{subsector.logo_filename}"
                    if subsector.logo_filename
                    else None
                ),
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
            'logo_url': (
                f"{request.host_url.rstrip('/')}/api/v1/uploads/sectors/{sector.logo_filename}"
                if sector.logo_filename
                else None
            ),
            'icon_class': sector.icon_class,
            'multilingual_names': multilingual_sector_names,
            'subsectors': subsectors_data,
        })

    return mobile_ok(data={'sectors': sectors_data})


@mobile_bp.route('/data/indicator-bank', methods=['GET'])
@mobile_rate_limit(requests_per_minute=60)
def public_indicator_bank():
    """Public indicator bank listing (mirrors /api/v1/indicator-bank)."""
    from flask_babel import force_locale

    from app.models import IndicatorBank, Sector, SubSector
    from app.routes.api.indicators import (
        _build_sector_subsector_names,
        _get_localized_type_unit,
    )

    # Allow full-catalog loads (hundreds of indicators); cap protects against abuse.
    page, per_page = validate_pagination_params(
        request.args, default_per_page=500, max_per_page=2000
    )

    search_query = request.args.get('search', default='', type=str).strip()
    indicator_type = request.args.get('type', default='', type=str).strip()
    sector_name = request.args.get('sector', default='', type=str).strip()
    sub_sector_name = request.args.get('sub_sector', default='', type=str).strip()
    emergency = request.args.get('emergency', default='', type=str).strip()
    archived_param = request.args.get('archived', default=None)
    sector_id_param = request.args.get('sector_id', type=int)

    requested_locale = request.args.get('locale', default='', type=str).strip().lower()
    if requested_locale:
        with suppress(Exception):
            with force_locale(requested_locale):
                pass

    query = IndicatorBank.query

    if archived_param is not None:
        if archived_param.lower() == 'true':
            query = query.filter(IndicatorBank.archived == True)  # noqa: E712
        elif archived_param.lower() == 'false':
            query = query.filter(IndicatorBank.archived == False)  # noqa: E712

    if search_query:
        safe_pattern = safe_ilike_pattern(search_query)
        query = query.filter(
            db.or_(
                IndicatorBank.name.ilike(safe_pattern),
                IndicatorBank.definition.ilike(safe_pattern),
            )
        )

    if indicator_type:
        query = query.filter(
            IndicatorBank.type.ilike(safe_ilike_pattern(indicator_type))
        )

    if sector_name:
        sector_obj = Sector.query.filter_by(name=sector_name, is_active=True).first()
        if sector_obj:
            sid = str(sector_obj.id)
            query = query.filter(
                db.or_(
                    IndicatorBank.sector['primary'].astext == sid,
                    IndicatorBank.sector['secondary'].astext == sid,
                    IndicatorBank.sector['tertiary'].astext == sid,
                )
            )

    if sub_sector_name:
        subsector_obj = SubSector.query.filter_by(
            name=sub_sector_name, is_active=True
        ).first()
        if subsector_obj:
            ssid = str(subsector_obj.id)
            query = query.filter(
                db.or_(
                    IndicatorBank.sub_sector['primary'].astext == ssid,
                    IndicatorBank.sub_sector['secondary'].astext == ssid,
                    IndicatorBank.sub_sector['tertiary'].astext == ssid,
                )
            )

    if sector_id_param is not None:
        sid = str(sector_id_param)
        query = query.filter(
            db.or_(
                IndicatorBank.sector['primary'].astext == sid,
                IndicatorBank.sector['secondary'].astext == sid,
                IndicatorBank.sector['tertiary'].astext == sid,
            )
        )

    if emergency:
        query = query.filter(
            IndicatorBank.emergency.ilike(safe_ilike_pattern(emergency))
        )

    paginated = query.order_by(IndicatorBank.name.asc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    indicators = paginated.items

    sector_ids = set()
    subsector_ids = set()
    for indicator in indicators:
        if indicator.sector:
            for level in ('primary', 'secondary', 'tertiary'):
                sector_id_val = indicator.sector.get(level)
                if sector_id_val:
                    sector_ids.add(sector_id_val)
        if indicator.sub_sector:
            for level in ('primary', 'secondary', 'tertiary'):
                subsector_id_val = indicator.sub_sector.get(level)
                if subsector_id_val:
                    subsector_ids.add(subsector_id_val)

    sectors_dict = {}
    if sector_ids:
        sectors = Sector.query.filter(Sector.id.in_(sector_ids)).all()
        sectors_dict = {s.id: s.name for s in sectors}

    subsectors_dict = {}
    if subsector_ids:
        subsectors = SubSector.query.filter(SubSector.id.in_(subsector_ids)).all()
        subsectors_dict = {s.id: s.name for s in subsectors}

    items = []
    for indicator in indicators:
        localized_type, localized_unit = _get_localized_type_unit(
            indicator, requested_locale
        )
        sector_sub = _build_sector_subsector_names(
            indicator, sectors_dict, subsectors_dict
        )
        items.append({
            'id': indicator.id,
            'name': indicator.name,
            'type': indicator.type,
            'localized_type': localized_type,
            'unit': indicator.unit,
            'localized_unit': localized_unit,
            'fdrs_kpi_code': getattr(indicator, 'fdrs_kpi_code', None),
            'definition': indicator.definition,
            'name_translations': (
                indicator.name_translations
                if hasattr(indicator, 'name_translations')
                else None
            ),
            'definition_translations': (
                indicator.definition_translations
                if hasattr(indicator, 'definition_translations')
                else None
            ),
            'sector': sector_sub['sector'],
            'sub_sector': sector_sub['sub_sector'],
            'emergency': indicator.emergency,
            'related_programs': indicator.related_programs_list,
            'archived': indicator.archived,
            'created_at': (
                indicator.created_at.isoformat()
                if hasattr(indicator, 'created_at') and indicator.created_at
                else None
            ),
            'updated_at': (
                indicator.updated_at.isoformat()
                if hasattr(indicator, 'updated_at') and indicator.updated_at
                else None
            ),
        })

    return mobile_paginated(
        items=items,
        total=paginated.total,
        page=paginated.page,
        per_page=paginated.per_page,
    )


@mobile_bp.route('/data/indicator-bank/<int:indicator_id>', methods=['GET'])
@mobile_rate_limit(requests_per_minute=120)
def public_indicator_detail(indicator_id):
    """Single indicator detail (public) — fully localized."""
    from app.models import IndicatorBank, Sector, SubSector
    from app.routes.api.indicators import (
        _build_sector_subsector_names,
        _get_localized_type_unit,
    )

    requested_locale = request.args.get('locale', default='', type=str).strip().lower()

    indicator = IndicatorBank.query.get(indicator_id)
    if not indicator:
        return mobile_not_found('Indicator not found')

    # Collect sector/subsector IDs referenced by this indicator
    sector_ids = set()
    subsector_ids = set()
    if indicator.sector:
        for level in ('primary', 'secondary', 'tertiary'):
            val = indicator.sector.get(level)
            if val:
                sector_ids.add(val)
    if indicator.sub_sector:
        for level in ('primary', 'secondary', 'tertiary'):
            val = indicator.sub_sector.get(level)
            if val:
                subsector_ids.add(val)

    sectors_dict = {}
    if sector_ids:
        sectors = Sector.query.filter(Sector.id.in_(sector_ids)).all()
        sectors_dict = {s.id: s.name for s in sectors}

    subsectors_dict = {}
    if subsector_ids:
        subsectors = SubSector.query.filter(SubSector.id.in_(subsector_ids)).all()
        subsectors_dict = {s.id: s.name for s in subsectors}

    localized_type, localized_unit = _get_localized_type_unit(indicator, requested_locale)
    sector_sub = _build_sector_subsector_names(indicator, sectors_dict, subsectors_dict)

    return mobile_ok(data={
        'indicator': {
            'id': indicator.id,
            'name': indicator.name,
            'definition': getattr(indicator, 'definition', None),
            'type': indicator.type,
            'localized_type': localized_type,
            'unit': indicator.unit,
            'localized_unit': localized_unit,
            'fdrs_kpi_code': getattr(indicator, 'fdrs_kpi_code', None),
            'name_translations': (
                indicator.name_translations
                if hasattr(indicator, 'name_translations')
                else None
            ),
            'definition_translations': (
                indicator.definition_translations
                if hasattr(indicator, 'definition_translations')
                else None
            ),
            'sector': sector_sub['sector'],
            'sub_sector': sector_sub['sub_sector'],
            'emergency': getattr(indicator, 'emergency', False),
            'related_programs': indicator.related_programs_list,
            'archived': indicator.archived,
        },
    })


@mobile_bp.route('/data/indicator-suggestions', methods=['POST'])
@mobile_rate_limit(requests_per_minute=10)
def submit_indicator_suggestion():
    """Submit an indicator suggestion (same JSON body as POST /api/v1/indicator-suggestions)."""
    from app.utils.api_helpers import get_json_safe
    from app.models import IndicatorSuggestion

    try:
        data = get_json_safe()
        required_fields = [
            'submitter_name',
            'submitter_email',
            'suggestion_type',
            'indicator_name',
            'reason',
        ]
        err = _mobile_require_json_keys(data, required_fields)
        if err:
            return err
        for field in required_fields:
            if not data.get(field):
                return mobile_bad_request(f'Missing required field: {field}')

        # Validate sector and subsector data (parity with api/v1/indicator-suggestions)
        if data.get('sector'):
            sector_data = data['sector']
            if isinstance(sector_data, dict):
                if not sector_data.get('primary', '').strip():
                    return mobile_bad_request('Primary sector must be filled')

        if data.get('sub_sector'):
            subsector_data = data['sub_sector']
            if isinstance(subsector_data, dict):
                if not subsector_data.get('primary', '').strip():
                    return mobile_bad_request('Primary subsector must be filled')

        sector_data = None
        if data.get('sector'):
            if isinstance(data['sector'], dict):
                sector_data = {}
                for level in ('primary', 'secondary', 'tertiary'):
                    if data['sector'].get(level):
                        sector_data[level] = data['sector'][level].strip()
                    else:
                        sector_data[level] = None
            else:
                sector_data = {
                    'primary': data['sector'],
                    'secondary': None,
                    'tertiary': None,
                }

        subsector_data = None
        if data.get('sub_sector'):
            if isinstance(data['sub_sector'], dict):
                subsector_data = {}
                for level in ('primary', 'secondary', 'tertiary'):
                    if data['sub_sector'].get(level):
                        subsector_data[level] = data['sub_sector'][level].strip()
                    else:
                        subsector_data[level] = None
            else:
                subsector_data = {
                    'primary': data['sub_sector'],
                    'secondary': None,
                    'tertiary': None,
                }

        suggestion = IndicatorSuggestion(
            submitter_name=data['submitter_name'],
            submitter_email=data['submitter_email'],
            suggestion_type=data['suggestion_type'],
            indicator_id=data.get('indicator_id'),
            indicator_name=data['indicator_name'],
            definition=data.get('definition'),
            type=data.get('type'),
            unit=data.get('unit'),
            sector=sector_data,
            sub_sector=subsector_data,
            emergency=data.get('emergency', False),
            related_programs=data.get('related_programs'),
            reason=data['reason'],
            additional_notes=data.get('additional_notes'),
        )

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
            'user_id': user.id,
            'name': user.name or (
                user.email.split('@')[0] if user.email else 'User'
            ),
            'email': user.email or '',
            'score': user.quiz_score or 0,
        })

    return mobile_ok(data={'leaderboard': items}, meta={'total': len(items)})


@mobile_bp.route('/data/periods', methods=['GET'])
@mobile_rate_limit(requests_per_minute=60)
def mobile_periods():
    """Distinct FDRS period names, newest first (mobile replacement for /api/v1/periods)."""
    import re
    from app.models import AssignedForm, PublicSubmission

    template_id = request.args.get('template_id', type=int)
    country_id = request.args.get('country_id', type=int)

    try:
        periods_set = set()

        assigned_query = db.session.query(AssignedForm.period_name).distinct()
        if template_id:
            assigned_query = assigned_query.filter(AssignedForm.template_id == template_id)
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
        )
        if template_id:
            public_query = public_query.filter(AssignedForm.template_id == template_id)
        if country_id:
            public_query = public_query.filter(PublicSubmission.country_id == country_id)
        for (period_name,) in public_query.filter(AssignedForm.period_name.isnot(None)).all():
            if period_name:
                periods_set.add(period_name)

        def _extract_year(p):
            m = re.search(r'\b(20\d{2})\b', p or '')
            return int(m.group(1)) if m else 0

        sorted_periods = sorted(periods_set, key=lambda p: (_extract_year(p), str(p)), reverse=True)
        return mobile_ok(data={'periods': sorted_periods})
    except Exception as e:
        current_app.logger.error('mobile_periods: %s', e, exc_info=True)
        return mobile_ok(data={'periods': []})


@mobile_bp.route('/data/fdrs-overview', methods=['GET'])
@mobile_rate_limit(requests_per_minute=30)
def mobile_fdrs_overview():
    """Pre-aggregated FDRS indicator totals per country.

    Mobile-optimised replacement for the paginated /api/v1/data/tables pattern:
    performs the country-level SUM server-side and returns a compact envelope so
    the Flutter client never has to fetch and iterate tens of thousands of rows.

    Query params:
      - indicator_bank_id (required): IndicatorBank PK to aggregate
      - template_id (optional): scope to a specific form template
      - period_name (optional): scope to a specific reporting period
      - locale (optional, default 'en'): language code for country names
    """
    indicator_bank_id = request.args.get('indicator_bank_id', type=int)
    template_id = request.args.get('template_id', type=int)
    period_name = request.args.get('period_name', type=str) or None
    locale = request.args.get('locale', 'en')

    if not indicator_bank_id:
        return mobile_bad_request('indicator_bank_id is required')

    try:
        from app.models import FormData, FormItem, Country, AssignedForm, PublicSubmission
        from app.models.assignments import AssignmentEntityStatus
        from app.utils.api_helpers import extract_numeric_value
        # Resolve all FormItem IDs for this indicator bank entry
        form_item_ids = [
            fi.id for fi in
            FormItem.query.filter(FormItem.indicator_bank_id == indicator_bank_id).all()
        ]
        if not form_item_ids:
            return mobile_ok(data={
                'period_name': period_name,
                'by_country': {},
                'country_names': {},
                'country_iso2': {},
            })

        # ── Assigned-form rows ──────────────────────────────────────────────
        aes_q = (
            db.session.query(AssignmentEntityStatus.entity_id, FormData.value)
            .join(FormData, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
            .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
            .filter(
                FormData.form_item_id.in_(form_item_ids),
                AssignmentEntityStatus.entity_type == 'country',
                db.or_(FormData.data_not_available.is_(None), FormData.data_not_available == False),  # noqa: E712
                db.or_(FormData.not_applicable.is_(None), FormData.not_applicable == False),  # noqa: E712
            )
        )
        if template_id:
            aes_q = aes_q.filter(AssignedForm.template_id == template_id)
        if period_name:
            aes_q = aes_q.filter(AssignedForm.period_name == period_name)

        # ── Public-submission rows ──────────────────────────────────────────
        pub_q = (
            db.session.query(PublicSubmission.country_id, FormData.value)
            .join(FormData, FormData.public_submission_id == PublicSubmission.id)
            .join(AssignedForm, AssignedForm.id == PublicSubmission.assigned_form_id)
            .filter(
                FormData.form_item_id.in_(form_item_ids),
                PublicSubmission.country_id.isnot(None),
                db.or_(FormData.data_not_available.is_(None), FormData.data_not_available == False),  # noqa: E712
                db.or_(FormData.not_applicable.is_(None), FormData.not_applicable == False),  # noqa: E712
            )
        )
        if template_id:
            pub_q = pub_q.filter(AssignedForm.template_id == template_id)
        if period_name:
            pub_q = pub_q.filter(AssignedForm.period_name == period_name)

        # ── Aggregate by country ────────────────────────────────────────────
        by_country: dict[int, float] = {}
        for country_id, value in list(aes_q.all()) + list(pub_q.all()):
            if not country_id:
                continue
            n = extract_numeric_value(value)
            if n is None or n <= 0:
                continue
            by_country[country_id] = by_country.get(country_id, 0) + n

        # ── Country metadata ────────────────────────────────────────────────
        country_ids = list(by_country.keys())
        countries = Country.query.filter(Country.id.in_(country_ids)).all() if country_ids else []

        country_names: dict[str, str] = {}
        country_iso2: dict[str, str] = {}
        for c in countries:
            name = c.name
            if locale != 'en':
                localized = getattr(c, f'name_{locale}', None)
                if localized:
                    name = localized
            country_names[str(c.id)] = name
            iso = getattr(c, 'iso2', None)
            if iso:
                country_iso2[str(c.id)] = iso.upper()

        return mobile_ok(data={
            'period_name': period_name,
            'by_country': {str(k): v for k, v in by_country.items()},
            'country_names': country_names,
            'country_iso2': country_iso2,
        })
    except Exception as e:
        current_app.logger.error('mobile_fdrs_overview: %s', e, exc_info=True)
        return mobile_server_error('Failed to load FDRS overview data.')


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
    from app.services import storage_service as storage

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
    """Public config for unified planning documents: IFRC GO API URL and type IDs.

    The mobile app calls the IFRC API directly using credentials supplied in the app
    build (not returned here). This endpoint only exposes the canonical base URL and
    the three AppealsTypeId values (Plan, Mid-Year Report, Annual Report).

    ``pdf_thumbnail_enabled`` is true only when the server has IFRC basic auth
    configured so ``/data/unified-planning-thumbnail`` can fetch PDFs. The list
    still works with app-side IFRC credentials alone; thumbnails require
    ``IFRC_API_USER`` / ``IFRC_API_PASSWORD`` on the Backoffice host.
    """
    from app.routes.ai_documents.helpers import _get_ifrc_basic_auth

    base = 'https://go-api.ifrc.org/Api/PublicSiteAppeals'
    ids = APPEALS_TYPE_DEFAULT_IDS_STR
    document_types = [
        {'id': tid, 'label': APPEALS_TYPE_DISPLAY_NAMES[tid]}
        for tid in sorted(APPEALS_TYPE_DISPLAY_NAMES.keys())
    ]
    return mobile_ok(
        data={
            'ifrc_public_site_appeals_base_url': base,
            'appeals_type_ids': ids,
            'ifrc_public_site_appeals_url': f'{base}?AppealsTypeId={ids}',
            'document_types': document_types,
            'pdf_thumbnail_enabled': _get_ifrc_basic_auth() is not None,
        },
    )


@mobile_bp.route('/data/unified-planning-thumbnail', methods=['GET', 'POST'])
@mobile_rate_limit(requests_per_minute=120)
def unified_planning_thumbnail():
    """Return a small JPEG of the PDF first page for unified-planning grid tiles.

    The mobile app should prefer this over downloading full PDFs on-device. The server
    fetches the IFRC PDF (same allowlist / Basic auth as document import), renders with
    PyMuPDF, and returns ``image/jpeg`` (not the usual mobile JSON envelope).

    **URL input (use POST in production):**

    - **POST** ``application/json``: ``{"url_b64": "<base64url UTF-8 of url>"}`` — preferred;
      avoids Azure WAF blocking raw IFRC URLs (tokens / ``&`` / ``=`` in JSON or query strings).
    - **POST** ``{"url": "<https...>"}`` — legacy plaintext (may be blocked by WAF).
    - **GET** ``?url=`` — legacy query string (often blocked by WAF for long SAS URLs).
    """
    import base64
    from urllib.parse import unquote

    import requests
    import fitz  # PyMuPDF

    from app.utils.api_helpers import get_json_safe

    from app.routes.ai_documents.helpers import (
        _get_ifrc_basic_auth,
        _validate_ifrc_fetch_url,
    )

    _max_url_len = int(current_app.config.get('UNIFIED_PLANNING_THUMB_MAX_URL_CHARS') or 16384)
    _max_b64_len = int(current_app.config.get('UNIFIED_PLANNING_THUMB_MAX_URL_B64_CHARS') or 32768)

    if request.method == 'POST':
        data = get_json_safe()
        raw = ''
        if isinstance(data, dict):
            url_b64 = (data.get('url_b64') or '').strip()
            if url_b64:
                if len(url_b64) > _max_b64_len:
                    return mobile_bad_request('url_b64 is too long')
                try:
                    pad = (-len(url_b64)) % 4
                    if pad:
                        url_b64 += '=' * pad
                    raw = base64.urlsafe_b64decode(url_b64.encode('ascii')).decode('utf-8')
                except Exception:
                    return mobile_bad_request('Invalid url_b64')
            else:
                raw = (data.get('url') or '').strip()
    else:
        raw = (request.args.get('url') or '').strip()
    if len(raw) > _max_url_len:
        return mobile_bad_request('url is too long')
    url = unquote(raw).strip()
    ok, err = _validate_ifrc_fetch_url(url)
    if not ok:
        return mobile_bad_request(err)

    cache_key = sha256(url.encode('utf-8')).hexdigest()
    with _UNIFIED_PLANNING_THUMB_LOCK:
        cached = _UNIFIED_PLANNING_THUMB_JPEG.get(cache_key)
        if cached is not None:
            _UNIFIED_PLANNING_THUMB_JPEG.move_to_end(cache_key)
            resp = make_response(cached)
            resp.headers['Content-Type'] = 'image/jpeg'
            resp.headers['Cache-Control'] = 'public, max-age=86400'
            return resp

    max_bytes = int(current_app.config.get('UNIFIED_PLANNING_THUMB_MAX_BYTES') or (12 * 1024 * 1024))
    auth = _get_ifrc_basic_auth()
    if auth is None:
        current_app.logger.warning('unified_planning_thumbnail: IFRC basic auth not configured')
        return mobile_bad_request('IFRC credentials are not configured on the server')

    r = None
    try:
        r = requests.get(
            url,
            auth=auth,
            timeout=(15, 90),
            stream=True,
            headers={'User-Agent': 'hum-databank-backoffice/1.0'},
            allow_redirects=True,
        )
        if r.status_code != 200:
            return mobile_bad_request(f'Upstream HTTP {r.status_code}')
        cl = r.headers.get('Content-Length')
        if cl is not None:
            with suppress(ValueError):
                if int(cl) > max_bytes:
                    return mobile_bad_request('PDF too large for thumbnail')
        chunks = []
        total = 0
        for chunk in r.iter_content(chunk_size=65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                return mobile_bad_request('PDF too large for thumbnail')
            chunks.append(chunk)
        pdf_bytes = b''.join(chunks)
    except requests.RequestException as e:
        current_app.logger.warning('unified_planning_thumbnail fetch: %s', e)
        return mobile_server_error()
    finally:
        if r is not None:
            with suppress(Exception):
                r.close()

    doc = None
    jpeg_bytes = b''
    try:
        doc = fitz.open(stream=pdf_bytes, filetype='pdf')
        if doc.page_count < 1:
            return mobile_bad_request('PDF has no pages')
        page = doc.load_page(0)
        rect = page.rect
        if rect.width <= 0:
            return mobile_bad_request('Invalid PDF page size')
        zoom = min(280.0 / float(rect.width), 2.5)
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        jpeg_bytes = pix.tobytes('jpeg', jpg_quality=82)
    except Exception as e:
        current_app.logger.warning('unified_planning_thumbnail render: %s', e, exc_info=True)
        return mobile_bad_request('Could not render PDF thumbnail')
    finally:
        if doc is not None:
            with suppress(Exception):
                doc.close()

    if not jpeg_bytes:
        return mobile_server_error()

    with _UNIFIED_PLANNING_THUMB_LOCK:
        _UNIFIED_PLANNING_THUMB_JPEG[cache_key] = jpeg_bytes
        _UNIFIED_PLANNING_THUMB_JPEG.move_to_end(cache_key)
        while len(_UNIFIED_PLANNING_THUMB_JPEG) > _UNIFIED_PLANNING_THUMB_MAX_ENTRIES:
            _UNIFIED_PLANNING_THUMB_JPEG.popitem(last=False)

    resp = make_response(jpeg_bytes)
    resp.headers['Content-Type'] = 'image/jpeg'
    resp.headers['Cache-Control'] = 'public, max-age=86400'
    return resp


@mobile_bp.route('/data/quiz/submit-score', methods=['POST'])
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
    if not isinstance(score, int) or score < 0:
        return mobile_bad_request('Invalid score. Must be a non-negative integer.')

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
