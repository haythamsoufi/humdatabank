"""Mobile FDRS overview: pre-aggregated indicator totals per country."""

from __future__ import annotations

import re

from flask import current_app, request

from app.extensions import db
from app.utils.mobile_responses import (
    mobile_bad_request,
    mobile_not_found,
    mobile_ok,
    mobile_server_error,
)


def _country_totals(indicator_bank_id, template_id, period_name) -> dict[int, float]:
    """Published numeric totals per country for one indicator bank row (public items only)."""
    from app.models import FormData, AssignedForm, PublicSubmission
    from app.models.assignments import AssignmentEntityStatus
    from plugins.fdrs.published_facts import (
        public_form_item_ids,
        published_numeric,
        published_snapshot_clause,
    )

    form_item_ids = public_form_item_ids(
        indicator_bank_id=indicator_bank_id,
        template_id=template_id,
    )
    if not form_item_ids:
        return {}

    aes_q = (
        db.session.query(
            AssignmentEntityStatus.entity_id,
            FormData.published_numeric_value,
            FormData.published_value,
        )
        .join(FormData, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
        .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
        .filter(
            FormData.form_item_id.in_(form_item_ids),
            AssignmentEntityStatus.entity_type == 'country',
            published_snapshot_clause(),
        )
    )
    aes_q = aes_q.filter(AssignedForm.template_id == template_id)
    if period_name:
        aes_q = aes_q.filter(AssignedForm.period_name == period_name)

    pub_q = (
        db.session.query(
            PublicSubmission.country_id,
            FormData.published_numeric_value,
            FormData.published_value,
        )
        .join(FormData, FormData.public_submission_id == PublicSubmission.id)
        .join(AssignedForm, AssignedForm.id == PublicSubmission.assigned_form_id)
        .filter(
            FormData.form_item_id.in_(form_item_ids),
            PublicSubmission.country_id.isnot(None),
            AssignedForm.template_id == template_id,
            published_snapshot_clause(),
        )
    )
    if period_name:
        pub_q = pub_q.filter(AssignedForm.period_name == period_name)

    by_country: dict[int, float] = {}
    for country_id, numeric, value in list(aes_q.all()) + list(pub_q.all()):
        if not country_id:
            continue
        n = published_numeric(numeric, value)
        if n is None or n <= 0:
            continue
        by_country[country_id] = by_country.get(country_id, 0) + n
    return by_country


def _volunteer_rolling_mean(bank_ids, kpi_code, period_name) -> dict | None:
    """Website volunteer headline (3-year rolling mean) when the indicator is volunteers.

    Reuses the public adapter so the app and the website show the same figure. ``None``
    for any other indicator, an unparseable period, or when nothing could be computed.
    """
    from app.models import IndicatorBank
    from app.services.data_quality.helpers import parse_period_year
    from plugins.fdrs.services.fdrs_public_adapter import (
        VOLUNTEER_BANK_CODE,
        build_global_validation,
        last_published_year,
    )

    if kpi_code != VOLUNTEER_BANK_CODE:
        is_volunteers = (
            kpi_code is None
            and bool(bank_ids)
            and IndicatorBank.query.filter(
                IndicatorBank.id.in_(list(bank_ids)),
                IndicatorBank.fdrs_kpi_code == VOLUNTEER_BANK_CODE,
            ).first() is not None
        )
        if not is_volunteers:
            return None

    year = parse_period_year(period_name) if period_name else last_published_year()
    if year is None:
        return None
    world = next((r for r in build_global_validation(year) if r['ZoneCode'] == ''), None)
    if not world or not world['IntValue']:
        return None
    return {'value': world['IntValue'], 'year_from': year - 2, 'year_to': year}


def fdrs_overview():
    """Pre-aggregated FDRS indicator totals per country.

    Mobile-optimised replacement for the paginated /api/v1/data pattern:
    sums the published snapshot (never the live editable value) server-side and
    returns a compact envelope so the Flutter client never has to fetch and
    iterate tens of thousands of rows. Only privacy=public items are included.

    Query params:
      - indicator_bank_id: IndicatorBank PK to aggregate
      - kpi_code: FDRS KPI code (e.g. KPI_ReachH) to aggregate instead of one bank id;
        every bank row carrying the code contributes its larger value per country so
        duplicate rows are not double counted. Bank ids differ between environments,
        so the people-reached chips use this.
      Volunteers also return ``global_rolling_mean`` (the website's 3-year rolling mean
      headline, ``{value, year_from, year_to}``); it is null for every other indicator.
      - template_id (optional, default 21 — FDRS): scope to a specific form template
      - period_name (optional): scope to a specific reporting period
      - locale (optional, default 'en'): language code for country names

    One of indicator_bank_id or kpi_code is required.
    """
    from app.utils.data_quality_constants import FDRS_TEMPLATE_ID

    indicator_bank_id = request.args.get('indicator_bank_id', type=int)
    kpi_code = (request.args.get('kpi_code', type=str) or '').strip() or None
    template_id = request.args.get('template_id', FDRS_TEMPLATE_ID, type=int)
    period_name = request.args.get('period_name', type=str) or None
    locale = request.args.get('locale', 'en')

    if not indicator_bank_id and not kpi_code:
        return mobile_bad_request('indicator_bank_id or kpi_code is required')

    try:
        from app.models import Country, IndicatorBank

        if kpi_code:
            if kpi_code not in _KEY_KPI_CODES:
                return mobile_bad_request('Unknown kpi_code')
            bank_ids = [
                row.id
                for row in IndicatorBank.query.filter(IndicatorBank.fdrs_kpi_code == kpi_code)
                .with_entities(IndicatorBank.id)
                .all()
            ]
        else:
            bank_ids = [indicator_bank_id]

        by_country: dict[int, float] = {}
        for bank_id in bank_ids:
            for country_id, total in _country_totals(bank_id, template_id, period_name).items():
                by_country[country_id] = max(by_country.get(country_id, 0), total)

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

        rolling_mean = None
        try:
            rolling_mean = _volunteer_rolling_mean(bank_ids, kpi_code, period_name)
        except Exception as e:
            current_app.logger.warning('mobile_fdrs_overview rolling mean: %s', e, exc_info=True)

        return mobile_ok(data={
            'period_name': period_name,
            'by_country': {str(k): v for k, v in by_country.items()},
            'country_names': country_names,
            'country_iso2': country_iso2,
            'global_total': sum(by_country.values()),
            'global_rolling_mean': rolling_mean,
        })
    except Exception as e:
        current_app.logger.error('mobile_fdrs_overview: %s', e, exc_info=True)
        return mobile_server_error('Failed to load FDRS overview data.')


# Headline indicators on the public country/region profile, keyed by FDRS KPI code.
# Indicator bank ids differ between environments and some KPI codes have several rows.
_SINGLE_KEY_KPI = {
    'KPI_PeopleVol': 'volunteers',
    'KPI_PStaff': 'staff',
    'KPI_noBranches': 'branches',
    'KPI_noLocalUnits': 'local_units',
    'KPI_DonBlood': 'blood_donors',
    'KPI_TrainFA': 'first_aid',
    'KPI_IncomeLC_CHF': 'income',
    'KPI_expenditureLC_CHF': 'expenditure',
}
# "People reached" has no single indicator; clients group these by sector, in this order.
_PEOPLE_REACHED_KPIS = (
    'KPI_ReachH',
    'KPI_ReachHPM',
    'KPI_ReachHI',
    'KPI_ReachM',
    'KPI_ReachWASH',
    'KPI_ReachS',
    'KPI_ReachL',
    'KPI_ReachRCRCEd',
    'KPI_ReachSI',
    'KPI_ReachCTP',
    'KPI_Climate',
    'KPI_ClimateHeat',
    'KPI_ReachDRR',
    'KPI_ReachDRER',
    'KPI_ReachLTSPD',
)
_KEY_KPI_CODES = set(_SINGLE_KEY_KPI) | set(_PEOPLE_REACHED_KPIS)
_COUNTRY_PROFILE_MAX_PERIODS = 10
_COVER_IMAGE_TYPE = 'Cover Image'


def _localized_text(translations, fallback, locale):
    if locale != 'en' and isinstance(translations, dict):
        text = translations.get(locale)
        if isinstance(text, str) and text.strip():
            return text
    return fallback


def _key_indicator_data(template_id, country_ids):
    """Headline and people-reached indicators merged by FDRS KPI code.

    Returns ({kpi_code: {'bank': IndicatorBank, 'by_period': {period: {country_id: value}}}},
    ids of every bank row carrying one of those codes). Duplicate bank rows for a code
    contribute the larger value per (period, country) so nothing is counted twice.
    """
    from app.models import IndicatorBank

    banks = (
        IndicatorBank.query
        .filter(IndicatorBank.fdrs_kpi_code.in_(_KEY_KPI_CODES))
        .order_by(IndicatorBank.id)
        .all()
    )
    if not banks:
        return {}, set()
    code_by_id = {b.id: b.fdrs_kpi_code for b in banks}
    primary_bank: dict[str, object] = {}
    for bank in banks:
        primary_bank.setdefault(bank.fdrs_kpi_code, bank)

    totals = _published_totals(
        _public_item_indicators(template_id, code_by_id), template_id, country_ids
    )
    merged: dict[str, dict[str, dict[int, float]]] = {}
    for (indicator_id, period_name, country_id), value in totals.items():
        by_country = merged.setdefault(code_by_id[indicator_id], {}).setdefault(period_name, {})
        by_country[country_id] = max(by_country.get(country_id, 0), value)

    data = {
        code: {'bank': primary_bank[code], 'by_period': by_period}
        for code, by_period in merged.items()
    }
    return data, set(code_by_id)


def _key_indicator_meta(code):
    if code in _SINGLE_KEY_KPI:
        return {'key': _SINGLE_KEY_KPI[code], 'group': None, 'group_order': None}
    return {
        'key': code,
        'group': 'people_reached',
        'group_order': _PEOPLE_REACHED_KPIS.index(code),
    }


def _sector_names(banks, locale):
    from app.models import Sector

    sector_ids = {
        bank.sector.get('primary')
        for bank in banks
        if isinstance(bank.sector, dict) and bank.sector.get('primary')
    }
    if not sector_ids:
        return {}
    return {
        s.id: _localized_text(s.name_translations, s.name, locale)
        for s in Sector.query.filter(Sector.id.in_(list(sector_ids))).all()
    }


def _bank_sector(bank, sector_names):
    primary = bank.sector.get('primary') if isinstance(bank.sector, dict) else None
    return sector_names.get(primary)


def _public_item_indicators(template_id, indicator_ids=None) -> dict[int, int]:
    """Map public form item id -> indicator bank id for one template."""
    from app.models import FormItem
    from plugins.fdrs.published_facts import public_form_item_ids

    form_item_ids = public_form_item_ids(template_id=template_id)
    if not form_item_ids:
        return {}
    query = FormItem.query.filter(
        FormItem.id.in_(form_item_ids), FormItem.indicator_bank_id.isnot(None)
    )
    if indicator_ids:
        query = query.filter(FormItem.indicator_bank_id.in_(list(indicator_ids)))
    return {
        item_id: indicator_id
        for item_id, indicator_id in query.with_entities(
            FormItem.id, FormItem.indicator_bank_id
        ).all()
    }


def _published_totals(item_to_indicator, template_id, country_ids) -> dict[tuple[int, str, int], float]:
    """Published numeric totals keyed by (indicator_bank_id, period_name, country_id)."""
    from app.models import AssignedForm, FormData, PublicSubmission
    from app.models.assignments import AssignmentEntityStatus
    from plugins.fdrs.published_facts import published_numeric, published_snapshot_clause

    totals: dict[tuple[int, str, int], float] = {}
    if not item_to_indicator or not country_ids:
        return totals

    item_ids = list(item_to_indicator)
    aes_q = (
        db.session.query(
            AssignmentEntityStatus.entity_id,
            FormData.form_item_id,
            AssignedForm.period_name,
            FormData.published_numeric_value,
            FormData.published_value,
        )
        .select_from(AssignmentEntityStatus)
        .join(FormData, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
        .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
        .filter(
            FormData.form_item_id.in_(item_ids),
            AssignmentEntityStatus.entity_type == 'country',
            AssignmentEntityStatus.entity_id.in_(list(country_ids)),
            AssignedForm.template_id == template_id,
            AssignedForm.period_name.isnot(None),
            published_snapshot_clause(),
        )
    )
    pub_q = (
        db.session.query(
            PublicSubmission.country_id,
            FormData.form_item_id,
            AssignedForm.period_name,
            FormData.published_numeric_value,
            FormData.published_value,
        )
        .select_from(PublicSubmission)
        .join(FormData, FormData.public_submission_id == PublicSubmission.id)
        .join(AssignedForm, AssignedForm.id == PublicSubmission.assigned_form_id)
        .filter(
            FormData.form_item_id.in_(item_ids),
            PublicSubmission.country_id.in_(list(country_ids)),
            AssignedForm.template_id == template_id,
            AssignedForm.period_name.isnot(None),
            published_snapshot_clause(),
        )
    )
    for country_id, item_id, period_name, numeric, value in list(aes_q.all()) + list(pub_q.all()):
        n = published_numeric(numeric, value)
        if n is None or n <= 0:
            continue
        key = (item_to_indicator[item_id], period_name, country_id)
        totals[key] = totals.get(key, 0) + n
    return totals


def _newest_periods(period_names, period_order=None):
    """Up to [_COUNTRY_PROFILE_MAX_PERIODS] names, newest first.

    [period_order] is the full newest-first list, so a bulk build can sort once.
    """
    wanted = {(name or '').strip() for name in period_names if (name or '').strip()}
    if not wanted:
        return []
    if period_order is None:
        from app.services.forms.reporting_period_service import sort_period_names

        ordered = sort_period_names(list(wanted))
    else:
        ordered = [name for name in period_order if name in wanted]
    return ordered[:_COUNTRY_PROFILE_MAX_PERIODS]


def _assemble_country_profile(
    country,
    *,
    locale,
    key_data,
    other_totals,
    document_entries,
    banks_by_id,
    sector_names,
    period_order=None,
    pns_iso3s=None,
):
    """One country profile payload.

    [other_totals] is keyed by (indicator bank id, period, country id).
    [document_entries] uses the shape from ``country_documents``.
    """
    from app.utils.sector_logo_urls import country_ns_logo_url

    national_society = country.primary_national_society
    iso3 = (country.iso3 or '').strip().upper()
    if pns_iso3s is None:
        try:
            from plugins.upr.analysis.country_international import pns_country_iso3s

            pns_iso3s = pns_country_iso3s()
        except Exception:
            pns_iso3s = frozenset()
    country_payload = {
        'id': country.id,
        'name': country.get_name_translation(locale) if locale != 'en' else country.name,
        'iso2': country.iso2,
        'iso3': country.iso3,
        'region': country.region,
        'national_society_name': national_society.name if national_society else None,
        'logo_url': country_ns_logo_url(national_society, country.iso3),
        # True when this country is assigned UPR PNS plan/report templates (22/23).
        'is_pns': iso3 in pns_iso3s,
    }

    totals = {
        (indicator_id, period_name): value
        for (indicator_id, period_name, country_id), value in other_totals.items()
        if country_id == country.id
    }
    all_periods = {period for _, period in totals} | {
        period
        for data in key_data.values()
        for period, values in data['by_period'].items()
        if country.id in values
    }
    periods_newest_first = _newest_periods(all_periods, period_order)
    period_rank = {period: index for index, period in enumerate(reversed(periods_newest_first))}

    series_by_indicator: dict[int, list[dict]] = {}
    for (indicator_id, period_name), value in totals.items():
        if period_name not in period_rank:
            continue
        series_by_indicator.setdefault(indicator_id, []).append(
            {'period': period_name, 'value': value}
        )
    for series in series_by_indicator.values():
        series.sort(key=lambda point: period_rank[point['period']])

    indicator_items = []
    for indicator_id, series in series_by_indicator.items():
        bank = banks_by_id.get(indicator_id)
        if bank is None or not series:
            continue
        indicator_items.append({
            'id': bank.id,
            'key': None,
            'name': _localized_text(bank.name_translations, bank.name, locale),
            'unit': bank.unit,
            'sector': _bank_sector(bank, sector_names),
            'latest_period': series[-1]['period'],
            'latest_value': series[-1]['value'],
            'series': series,
        })
    for kpi_code, data in key_data.items():
        bank = data['bank']
        series = sorted(
            (
                {'period': period, 'value': values[country.id]}
                for period, values in data['by_period'].items()
                if period in period_rank and country.id in values
            ),
            key=lambda point: period_rank[point['period']],
        )
        if not series:
            continue
        indicator_items.append({
            'id': bank.id,
            'kpi_code': kpi_code,
            **_key_indicator_meta(kpi_code),
            'name': _localized_text(bank.name_translations, bank.name, locale),
            'unit': bank.unit,
            'sector': _bank_sector(bank, sector_names),
            'latest_period': series[-1]['period'],
            'latest_value': series[-1]['value'],
            'series': series,
        })
    indicator_items.sort(key=lambda item: item['latest_value'], reverse=True)

    cover_images: list[str] = []
    documents: list[dict] = []
    for entry in document_entries:
        if entry.get('document_type') == _COVER_IMAGE_TYPE:
            if entry.get('url'):
                cover_images.append(entry['url'])
            continue
        documents.append({
            'title': entry.get('title') or entry.get('name'),
            'filename': entry.get('name'),
            'url': entry.get('url'),
            'thumbnail': entry.get('thumbnail'),
            'year': entry.get('year'),
            'period': entry.get('YearText'),
            'document_type': entry.get('document_type'),
            'language': entry.get('language') or entry.get('LangCode'),
            'language_code': entry.get('LangCode'),
            'uploaded_at': entry.get('ModifiedAt'),
        })

    return {
        'country': country_payload,
        'periods': periods_newest_first,
        'indicators': indicator_items,
        'cover_images': cover_images,
        'documents': documents,
    }


def country_profile(iso3):
    """Public country profile: key figures, indicator series, cover images and documents.

    Mirrors the website country page using only the published snapshot of
    privacy=public form items, so the mobile client never needs an API key.

    Query params:
      - template_id (optional, default 21 — FDRS)
      - locale (optional, default 'en'): localized country, indicator and sector names
    """
    from app.utils.data_quality_constants import FDRS_TEMPLATE_ID

    template_id = request.args.get('template_id', FDRS_TEMPLATE_ID, type=int)
    locale = (request.args.get('locale', 'en') or 'en').strip().lower()
    code = (iso3 or '').strip().upper()
    if len(code) != 3 or not code.isalpha():
        return mobile_bad_request('iso3 must be a 3-letter country code')

    try:
        from app.models import Country, IndicatorBank
        from plugins.fdrs.services.fdrs_public_documents import country_documents

        country = Country.query.filter(db.func.upper(Country.iso3) == code).first()
        if country is None:
            return mobile_not_found('Country not found')

        key_data, key_bank_ids = _key_indicator_data(template_id, [country.id])
        item_to_indicator = {
            item_id: indicator_id
            for item_id, indicator_id in _public_item_indicators(template_id).items()
            if indicator_id not in key_bank_ids
        }
        other_totals = _published_totals(item_to_indicator, template_id, [country.id])
        indicator_ids = {
            indicator_id
            for (indicator_id, _period, country_id) in other_totals
            if country_id == country.id
        }
        banks = (
            IndicatorBank.query.filter(IndicatorBank.id.in_(list(indicator_ids))).all()
            if indicator_ids else []
        )
        banks_by_id = {bank.id: bank for bank in banks}
        sector_names = _sector_names(
            banks + [data['bank'] for data in key_data.values()], locale
        )
        return mobile_ok(data=_assemble_country_profile(
            country,
            locale=locale,
            key_data=key_data,
            other_totals=other_totals,
            document_entries=country_documents(country.id),
            banks_by_id=banks_by_id,
            sector_names=sector_names,
        ))
    except Exception as e:
        current_app.logger.error('mobile_country_profile: %s', e, exc_info=True)
        return mobile_server_error('Failed to load country profile.')


def country_international(iso3):
    """International bilateral support for one country (PNS outbound or host inbound).

    Powers the Institutional → International sub-tab on the mobile country
    profile. Uses the same public UPR flow figures as the Embed Content visuals.
    """
    code = (iso3 or '').strip().upper()
    if len(code) != 3 or not code.isalpha():
        return mobile_bad_request('iso3 must be a 3-letter country code')

    try:
        from app.models import Country
        from plugins.upr.analysis.country_international import build_country_international

        country = Country.query.filter(db.func.upper(Country.iso3) == code).first()
        if country is None:
            return mobile_not_found('Country not found')
        return mobile_ok(data=build_country_international(code))
    except Exception as e:
        current_app.logger.error('mobile_country_international: %s', e, exc_info=True)
        return mobile_server_error('Failed to load international support.')


def go_documents_all():
    """GO operation-document lists for every country, in one response.

    The mobile offline pack stores this single payload. Opening a country
    reads its rows from the list instead of requesting each country.
    """
    try:
        from app.models import Country
        from plugins.fdrs.services.go_operation_documents import fetch_go_documents_by_iso3

        iso2_to_iso3: dict[str, str] = {}
        iso3s: list[str] = []
        seen: set[str] = set()
        for iso2, iso3 in Country.query.with_entities(Country.iso2, Country.iso3).all():
            code3 = (iso3 or '').strip().upper()
            if len(code3) != 3 or not code3.isalpha() or code3 in seen:
                continue
            seen.add(code3)
            iso3s.append(code3)
            code2 = (iso2 or '').strip().upper()
            if len(code2) == 2 and code2.isalpha():
                iso2_to_iso3.setdefault(code2, code3)

        grouped, available = fetch_go_documents_by_iso3(iso2_to_iso3)
        by_country = {
            iso3: {
                'documents': grouped.get(iso3, []) if available else [],
                'available': available,
            }
            for iso3 in iso3s
        }
        return mobile_ok(data={'by_country': by_country})
    except Exception as e:
        current_app.logger.error('mobile_go_documents_all: %s', e, exc_info=True)
        return mobile_server_error('Failed to load operation documents.')


def country_go_documents(iso3):
    """Public GO operation documents for one country (appeals, updates, situation reports).

    Separate from the country profile so a slow GO response does not block key figures.
    ``available`` is false when GO could not be reached.
    """
    from plugins.fdrs.services.go_operation_documents import fetch_go_operation_documents

    code = (iso3 or '').strip().upper()
    if len(code) != 3 or not code.isalpha():
        return mobile_bad_request('iso3 must be a 3-letter country code')

    try:
        from app.models import Country

        country = Country.query.filter(db.func.upper(Country.iso3) == code).first()
        if country is None:
            return mobile_not_found('Country not found')

        iso2 = (country.iso2 or '').strip().upper()
        if len(iso2) != 2:
            return mobile_ok(data={'documents': [], 'available': True})

        documents, available = fetch_go_operation_documents(iso2=iso2, iso3=code)
        return mobile_ok(data={'documents': documents, 'available': available})
    except Exception as e:
        current_app.logger.error('mobile_country_go_documents: %s', e, exc_info=True)
        return mobile_server_error('Failed to load operation documents.')


def country_operations(iso3):
    """Active GO emergencies for one country: counts, people targeted, funding, and operations."""
    from plugins.fdrs.services.go_operations import fetch_operations

    code = (iso3 or '').strip().upper()
    if len(code) != 3 or not code.isalpha():
        return mobile_bad_request('iso3 must be a 3-letter country code')

    try:
        from app.models import Country

        country = Country.query.filter(db.func.upper(Country.iso3) == code).first()
        if country is None:
            return mobile_not_found('Country not found')

        payload, available = fetch_operations(iso3=code)
        return mobile_ok(data={**payload, 'available': available, 'supported': True})
    except Exception as e:
        current_app.logger.error('mobile_country_operations: %s', e, exc_info=True)
        return mobile_server_error('Failed to load operations.')


_REGION_TOP_COUNTRIES = 10


def _region_slug(region_name):
    return re.sub(r'[\s/]+', '-', (region_name or 'Other').strip().lower())


def region_profile(slug):
    """Regional analysis: summed key indicators per period and the top reporting countries.

    Uses the published snapshot of privacy=public form items only. Each series point
    carries the number of countries that reported, so clients can show coverage.

    Query params:
      - template_id (optional, default 21 — FDRS)
      - locale (optional, default 'en'): localized country and indicator names
    """
    from app.utils.data_quality_constants import FDRS_TEMPLATE_ID

    template_id = request.args.get('template_id', FDRS_TEMPLATE_ID, type=int)
    locale = (request.args.get('locale', 'en') or 'en').strip().lower()
    wanted = (slug or '').strip().lower()
    if not wanted:
        return mobile_bad_request('region slug is required')

    try:
        from app.models import Country
        from app.services.forms.reporting_period_service import sort_period_names

        countries = [c for c in Country.query.all() if _region_slug(c.region) == wanted]
        if not countries:
            return mobile_not_found('Region not found')
        countries_by_id = {c.id: c for c in countries}

        key_data, _ = _key_indicator_data(template_id, list(countries_by_id))

        periods_newest_first = sort_period_names(
            list({p for data in key_data.values() for p in data['by_period']})
        )[:_COUNTRY_PROFILE_MAX_PERIODS]
        period_rank = {p: i for i, p in enumerate(reversed(periods_newest_first))}
        sector_names = _sector_names([data['bank'] for data in key_data.values()], locale)

        indicator_items = []
        for kpi_code, data in key_data.items():
            by_period = {p: v for p, v in data['by_period'].items() if p in period_rank}
            if not by_period:
                continue
            bank = data['bank']
            ordered = sorted(by_period, key=lambda period: period_rank[period])
            series = [
                {
                    'period': period,
                    'value': sum(by_period[period].values()),
                    'countries': len(by_period[period]),
                }
                for period in ordered
            ]
            latest = ordered[-1]
            top = sorted(by_period[latest].items(), key=lambda kv: kv[1], reverse=True)
            indicator_items.append({
                'id': bank.id,
                'kpi_code': kpi_code,
                **_key_indicator_meta(kpi_code),
                'name': _localized_text(bank.name_translations, bank.name, locale),
                'unit': bank.unit,
                'sector': _bank_sector(bank, sector_names),
                'latest_period': latest,
                'latest_value': series[-1]['value'],
                'reporting_countries': series[-1]['countries'],
                'series': series,
                'top_countries': [
                    {
                        'iso3': countries_by_id[cid].iso3,
                        'name': (
                            countries_by_id[cid].get_name_translation(locale)
                            if locale != 'en' else countries_by_id[cid].name
                        ),
                        'value': value,
                    }
                    for cid, value in top[:_REGION_TOP_COUNTRIES]
                ],
            })
        indicator_items.sort(key=lambda item: item['id'])

        return mobile_ok(data={
            'region': {
                'name': countries[0].region,
                'slug': wanted,
                'country_count': len(countries),
            },
            'periods': periods_newest_first,
            'indicators': indicator_items,
        })
    except Exception as e:
        current_app.logger.error('mobile_region_profile: %s', e, exc_info=True)
        return mobile_server_error('Failed to load region profile.')


def region_operations(slug):
    """Active GO operations for one Databank region (the GO regional operations view)."""
    from plugins.fdrs.services.go_operations import fetch_operations, go_region_id

    wanted = (slug or '').strip().lower()
    if not wanted:
        return mobile_bad_request('region slug is required')

    try:
        from app.models import Country

        countries = [c for c in Country.query.all() if _region_slug(c.region) == wanted]
        if not countries:
            return mobile_not_found('Region not found')

        region_id = go_region_id(countries[0].region)
        if region_id is None:
            payload, available = fetch_operations()
            return mobile_ok(data={**payload, 'available': available, 'supported': False})

        payload, available = fetch_operations(region_id=region_id)
        return mobile_ok(data={**payload, 'available': available, 'supported': True})
    except Exception as e:
        current_app.logger.error('mobile_region_operations: %s', e, exc_info=True)
        return mobile_server_error('Failed to load operations.')


def build_reach_sectors(template_id, locale):
    """People-reached indicators grouped by sector.

    Only indicators with at least one privacy=public form item are listed.
    Sectors follow ``Sector.display_order`` (unsectored indicators last).
    """
    from app.models import IndicatorBank, Sector

    banks = (
        IndicatorBank.query
        .filter(IndicatorBank.fdrs_kpi_code.in_(_PEOPLE_REACHED_KPIS))
        .order_by(IndicatorBank.id)
        .all()
    )
    code_by_id = {bank.id: bank.fdrs_kpi_code for bank in banks}
    public_bank_ids = set(_public_item_indicators(template_id, code_by_id).values())

    primary_bank: dict[str, object] = {}
    for bank in banks:
        if bank.id in public_bank_ids:
            primary_bank.setdefault(bank.fdrs_kpi_code, bank)

    sector_names = _sector_names(list(primary_bank.values()), locale)
    sector_order = {
        sector.id: (sector.display_order or 0)
        for sector in Sector.query.filter(Sector.id.in_(list(sector_names))).all()
    } if sector_names else {}
    sectors: dict[object, dict] = {}
    for code in _PEOPLE_REACHED_KPIS:
        bank = primary_bank.get(code)
        if bank is None:
            continue
        primary = bank.sector.get('primary') if isinstance(bank.sector, dict) else None
        sector = sectors.setdefault(primary, {
            'id': str(primary) if primary is not None else None,
            'name': sector_names.get(primary),
            'indicators': [],
        })
        sector['indicators'].append({
            'kpi_code': code,
            'name': _localized_text(bank.name_translations, bank.name, locale),
        })

    ordered = sorted(
        sectors,
        key=lambda primary: (primary not in sector_order, sector_order.get(primary, 0)),
    )
    return [sectors[primary] for primary in ordered]


def reach_indicators():
    """People-reached indicators grouped by sector, for the home map chips.

    Only indicators with at least one privacy=public form item in the template are listed.
    Sectors follow ``Sector.display_order`` (unsectored indicators last), indicators keep the
    order of ``_PEOPLE_REACHED_KPIS`` and are identified by FDRS KPI code, which is stable across environments.

    Query params:
      - template_id (optional, default 21 — FDRS)
      - locale (optional, default 'en'): localized sector and indicator names
    """
    from app.utils.data_quality_constants import FDRS_TEMPLATE_ID

    template_id = request.args.get('template_id', FDRS_TEMPLATE_ID, type=int)
    locale = (request.args.get('locale', 'en') or 'en').strip().lower()

    try:
        return mobile_ok(data={'sectors': build_reach_sectors(template_id, locale)})
    except Exception as e:
        current_app.logger.error('mobile_reach_indicators: %s', e, exc_info=True)
        return mobile_server_error('Failed to load people reached indicators.')


def campaign_period_names(template_id, country_id=None):
    """Distinct campaign period names for a template, newest first."""
    from app.models import AssignedForm, PublicSubmission
    from app.models.enums import AssignmentScope
    from app.services.forms.reporting_period_service import sort_period_names

    periods_set = set()
    assigned_query = (
        db.session.query(AssignedForm.period_name)
        .distinct()
        .filter(
            AssignedForm.template_id == template_id,
            AssignedForm.scope == AssignmentScope.campaign.value,
        )
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
        .filter(
            AssignedForm.template_id == template_id,
            AssignedForm.scope == AssignmentScope.campaign.value,
        )
    )
    if country_id:
        public_query = public_query.filter(PublicSubmission.country_id == country_id)
    for (period_name,) in public_query.filter(AssignedForm.period_name.isnot(None)).all():
        if period_name:
            periods_set.add(period_name)
    return sort_period_names(list(periods_set))


def _parse_bank_ids(raw):
    bank_ids = []
    seen = set()
    for part in (raw or '').split(','):
        part = part.strip()
        if not part.isdigit():
            continue
        value = int(part)
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        bank_ids.append(value)
        if len(bank_ids) >= 20:
            break
    return bank_ids


def _overview_names(by_country, countries_by_id, locale):
    names = {}
    iso2 = {}
    for country_id in by_country:
        country = countries_by_id.get(country_id)
        if country is None:
            continue
        name = country.name
        if locale != 'en':
            localized = getattr(country, f'name_{locale}', None)
            if localized:
                name = localized
        names[str(country_id)] = name
        code = getattr(country, 'iso2', None)
        if code:
            iso2[str(country_id)] = code.upper()
    return names, iso2


def _empty_operations():
    return {
        'summary': {
            'active_drefs': 0,
            'active_appeals': 0,
            'people_targeted': 0,
            'amount_requested': 0,
            'amount_funded': 0,
        },
        'operations': [],
        'available': True,
        'supported': True,
    }


def offline_home():
    """Every home-map indicator for every reporting period, in one response.

    The app writes each slice into the same cache entries as
    ``/data/periods``, ``/data/fdrs-reach-indicators`` and ``/data/fdrs-overview``,
    so chips the user has never opened still work offline.

    Query params:
      - template_id (optional, default 21)
      - locale (optional, default 'en')
      - indicator_bank_ids: comma-separated bank ids the home chips request
    """
    from app.utils.data_quality_constants import FDRS_TEMPLATE_ID

    template_id = request.args.get('template_id', FDRS_TEMPLATE_ID, type=int)
    locale = (request.args.get('locale', 'en') or 'en').strip().lower()
    bank_ids = _parse_bank_ids(request.args.get('indicator_bank_ids', ''))

    try:
        from app.models import Country, IndicatorBank
        from plugins.fdrs.services.fdrs_public_adapter import VOLUNTEER_BANK_CODE

        periods = campaign_period_names(template_id)
        reach_sectors = build_reach_sectors(template_id, locale)
        countries = Country.query.all()
        countries_by_id = {country.id: country for country in countries}
        country_ids = list(countries_by_id)

        item_to_indicator = _public_item_indicators(template_id, set(bank_ids))
        bank_totals = _published_totals(item_to_indicator, template_id, country_ids)
        by_bank_period: dict[tuple[int, str], dict[int, float]] = {}
        for (indicator_id, period_name, country_id), value in bank_totals.items():
            by_bank_period.setdefault((indicator_id, period_name), {})[country_id] = value

        key_data, _key_bank_ids = _key_indicator_data(template_id, country_ids)
        volunteer_ids = {
            row.id
            for row in IndicatorBank.query.filter(
                IndicatorBank.id.in_(bank_ids),
                IndicatorBank.fdrs_kpi_code == VOLUNTEER_BANK_CODE,
            ).all()
        } if bank_ids else set()

        kpi_codes = []
        for sector in reach_sectors:
            for indicator in sector.get('indicators') or []:
                code = indicator.get('kpi_code')
                if code and code not in kpi_codes:
                    kpi_codes.append(code)

        overviews = []
        for bank_id in bank_ids:
            for period in periods:
                by_country = by_bank_period.get((bank_id, period), {})
                names, iso2 = _overview_names(by_country, countries_by_id, locale)
                rolling = None
                if bank_id in volunteer_ids:
                    try:
                        rolling = _volunteer_rolling_mean([bank_id], None, period)
                    except Exception as exc:
                        current_app.logger.warning(
                            'offline_home rolling mean: %s', exc, exc_info=True
                        )
                overviews.append({
                    'indicator_bank_id': bank_id,
                    'kpi_code': None,
                    'period_name': period,
                    'by_country': {str(key): value for key, value in by_country.items()},
                    'country_names': names,
                    'country_iso2': iso2,
                    'global_rolling_mean': rolling,
                })
        for kpi_code in kpi_codes:
            by_period = (key_data.get(kpi_code) or {}).get('by_period') or {}
            for period in periods:
                by_country = by_period.get(period) or {}
                names, iso2 = _overview_names(by_country, countries_by_id, locale)
                overviews.append({
                    'indicator_bank_id': None,
                    'kpi_code': kpi_code,
                    'period_name': period,
                    'by_country': {str(key): value for key, value in by_country.items()},
                    'country_names': names,
                    'country_iso2': iso2,
                    'global_rolling_mean': None,
                })

        return mobile_ok(data={
            'periods': periods,
            'reach_sectors': reach_sectors,
            'overviews': overviews,
        })
    except Exception as e:
        current_app.logger.error('mobile_offline_home: %s', e, exc_info=True)
        return mobile_server_error('Failed to prepare offline home data.')


def offline_countries():
    """Country list plus every country profile and its active operations.

    The app stores each piece under the cache key of ``/data/countrymap``,
    ``/data/country-profile/<iso3>`` and ``.../operations``.
    """
    from app.utils.data_quality_constants import FDRS_TEMPLATE_ID

    template_id = request.args.get('template_id', FDRS_TEMPLATE_ID, type=int)
    locale = (request.args.get('locale', 'en') or 'en').strip().lower()

    try:
        from app.models import IndicatorBank
        from app.services import CountryService
        from app.utils.sector_logo_urls import country_ns_logo_url
        from plugins.fdrs.services.fdrs_public_documents import public_documents_by_country
        from plugins.fdrs.services.go_operations import fetch_operations_by_iso3

        countries = CountryService.get_all_with_national_societies(ordered=True).all()
        country_ids = [country.id for country in countries]
        list_items = []
        for country in countries:
            name = country.name
            if locale != 'en' and hasattr(country, f'name_{locale}'):
                name = getattr(country, f'name_{locale}', None) or country.name
            society = country.primary_national_society
            list_items.append({
                'id': country.id,
                'name': name,
                'iso2': getattr(country, 'iso2', None),
                'iso3': getattr(country, 'iso3', None),
                'region': getattr(country, 'region', None),
                'national_society_name': society.name if society else None,
                'logo_url': country_ns_logo_url(society, getattr(country, 'iso3', None)),
            })

        key_data, key_bank_ids = _key_indicator_data(template_id, country_ids)
        item_to_indicator = {
            item_id: indicator_id
            for item_id, indicator_id in _public_item_indicators(template_id).items()
            if indicator_id not in key_bank_ids
        }
        other_totals = _published_totals(item_to_indicator, template_id, country_ids)
        indicator_ids = {indicator_id for (indicator_id, _period, _country_id) in other_totals}
        banks = (
            IndicatorBank.query.filter(IndicatorBank.id.in_(list(indicator_ids))).all()
            if indicator_ids else []
        )
        banks_by_id = {bank.id: bank for bank in banks}
        sector_names = _sector_names(
            banks + [data['bank'] for data in key_data.values()], locale
        )
        documents = public_documents_by_country()
        period_names = {
            period
            for (_indicator_id, period, _country_id) in other_totals
        }
        for data in key_data.values():
            period_names.update(data['by_period'])
        from app.services.forms.reporting_period_service import sort_period_names
        period_order = sort_period_names(list(period_names))
        try:
            from plugins.upr.analysis.country_international import pns_country_iso3s

            pns_iso3s = pns_country_iso3s()
        except Exception:
            pns_iso3s = frozenset()

        profiles = {}
        for country in countries:
            iso3 = (country.iso3 or '').strip().upper()
            if len(iso3) != 3 or not iso3.isalpha():
                continue
            profiles[iso3] = _assemble_country_profile(
                country,
                locale=locale,
                key_data=key_data,
                other_totals=other_totals,
                document_entries=documents.get(country.id) or [],
                banks_by_id=banks_by_id,
                sector_names=sector_names,
                period_order=period_order,
                pns_iso3s=pns_iso3s,
            )

        try:
            operations_by_iso, operations_available = fetch_operations_by_iso3()
        except Exception as exc:
            current_app.logger.warning('offline_countries operations: %s', exc, exc_info=True)
            operations_by_iso, operations_available = {}, False
        if not operations_available:
            operations = {
                iso3: {**_empty_operations(), 'available': False}
                for iso3 in profiles
            }
        else:
            operations = {
                iso3: operations_by_iso.get(iso3) or _empty_operations()
                for iso3 in profiles
            }

        return mobile_ok(data={
            'countries': list_items,
            'profiles': profiles,
            'operations': operations,
        })
    except Exception as e:
        current_app.logger.error('mobile_offline_countries: %s', e, exc_info=True)
        return mobile_server_error('Failed to prepare offline country data.')
