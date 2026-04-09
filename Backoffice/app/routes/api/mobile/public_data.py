# Backoffice/app/routes/api/mobile/public_data.py
"""Public data routes: country map, sectors, indicator bank, FDRS overview, quiz.

Auth policy:
  - Truly public (no login required): countrymap, sectors-subsectors, indicator-bank,
    indicator-suggestions, quiz/leaderboard, data/periods, data/fdrs-overview.
    Rate-limited to prevent abuse.
  - Auth-required: quiz/submit-score (score is tied to the authenticated user).
"""

from contextlib import suppress

from flask import request, current_app
from flask_login import current_user

from app.utils.api_pagination import validate_pagination_params
from app.utils.mobile_auth import mobile_auth_required
from app.utils.rate_limiting import mobile_rate_limit
from app import db
from app.utils.mobile_responses import (
    mobile_ok, mobile_bad_request, mobile_server_error, mobile_paginated,
    mobile_not_found,
)
from app.utils.sql_utils import safe_ilike_pattern
from app.routes.api.mobile import mobile_bp


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
def public_indicator_detail(indicator_id):
    """Single indicator detail (public)."""
    from app.models import IndicatorBank

    indicator = IndicatorBank.query.get(indicator_id)
    if not indicator:
        return mobile_not_found('Indicator not found')

    return mobile_ok(data={
        'indicator': {
            'id': indicator.id,
            'name': indicator.name,
            'definition': getattr(indicator, 'definition', None),
            'type': getattr(indicator, 'type', None),
            'unit': getattr(indicator, 'unit', None),
            'sector': indicator.sector,
            'sub_sector': indicator.sub_sector,
            'fdrs_kpi_code': getattr(indicator, 'fdrs_kpi_code', None),
            'emergency': getattr(indicator, 'emergency', False),
        },
    })


@mobile_bp.route('/data/indicator-suggestions', methods=['POST'])
@mobile_rate_limit(requests_per_minute=10)
def submit_indicator_suggestion():
    """Submit an indicator suggestion (mirrors /api/v1/indicator-suggestions)."""
    from app.utils.api_helpers import get_json_safe
    from app.models import IndicatorSuggestion

    data = get_json_safe()
    name = (data.get('name') or '').strip()
    if not name:
        return mobile_bad_request('Indicator name is required')

    try:
        suggestion = IndicatorSuggestion(
            name=name,
            definition=data.get('definition', ''),
            submitted_by=data.get('submitted_by', ''),
            email=data.get('email', ''),
        )
        db.session.add(suggestion)
        db.session.flush()
        return mobile_ok(message='Indicator suggestion submitted', data={'id': suggestion.id})
    except Exception as e:
        current_app.logger.error("submit_indicator_suggestion: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()


@mobile_bp.route('/data/quiz/leaderboard', methods=['GET'])
@mobile_rate_limit(requests_per_minute=60)
def quiz_leaderboard():
    """Quiz leaderboard (mirrors /api/v1/quiz/leaderboard)."""
    from app.models import QuizScore

    limit = request.args.get('limit', 20, type=int)

    scores = QuizScore.query.order_by(
        QuizScore.score.desc(), QuizScore.created_at.asc()
    ).limit(min(limit, 100)).all()

    items = []
    for s in scores:
        items.append({
            'id': s.id,
            'user_name': s.user_name,
            'score': s.score,
            'total_questions': getattr(s, 'total_questions', None),
            'created_at': s.created_at.isoformat() if s.created_at else None,
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


@mobile_bp.route('/data/quiz/submit-score', methods=['POST'])
@mobile_auth_required
def submit_quiz_score():
    """Submit a quiz score (mirrors /api/v1/quiz/submit-score).

    user_name is derived from the authenticated user so the client never
    needs to send it — avoids the payload mismatch that caused all
    submissions to return 400 when the client sent only {score}.
    """
    from app.utils.api_helpers import get_json_safe
    from app.models import QuizScore

    data = get_json_safe()
    score = data.get('score')
    if score is None:
        return mobile_bad_request('score is required')

    # Derive display name from the authenticated user; never trust a
    # client-provided name for score attribution.
    user_name = (
        getattr(current_user, 'name', None)
        or getattr(current_user, 'email', None)
        or f'User {current_user.id}'
    ).strip()

    try:
        quiz_score = QuizScore(
            user_name=user_name,
            score=score,
            total_questions=data.get('total_questions'),
        )
        db.session.add(quiz_score)
        db.session.flush()
        return mobile_ok(message='Score submitted', data={'id': quiz_score.id})
    except Exception as e:
        current_app.logger.error("submit_quiz_score: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()
