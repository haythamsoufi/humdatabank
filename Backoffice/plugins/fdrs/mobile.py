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


def fdrs_overview():
    """Pre-aggregated FDRS indicator totals per country.

    Mobile-optimised replacement for the paginated /api/v1/data pattern:
    sums the published snapshot (never the live editable value) server-side and
    returns a compact envelope so the Flutter client never has to fetch and
    iterate tens of thousands of rows. Only privacy=public form items are included.

    Query params:
      - indicator_bank_id (required): IndicatorBank PK to aggregate
      - template_id (optional, default 21 — FDRS): scope to a specific form template
      - period_name (optional): scope to a specific reporting period
      - locale (optional, default 'en'): language code for country names
    """
    from app.utils.data_quality_constants import FDRS_TEMPLATE_ID

    indicator_bank_id = request.args.get('indicator_bank_id', type=int)
    template_id = request.args.get('template_id', FDRS_TEMPLATE_ID, type=int)
    period_name = request.args.get('period_name', type=str) or None
    locale = request.args.get('locale', 'en')

    if not indicator_bank_id:
        return mobile_bad_request('indicator_bank_id is required')

    try:
        from app.models import FormData, Country, AssignedForm, PublicSubmission
        from app.models.assignments import AssignmentEntityStatus
        from plugins.fdrs.published_facts import (
            public_form_item_ids,
            published_numeric,
            published_snapshot_clause,
        )
        # Public map: privacy=public items only, and only the published snapshot.
        form_item_ids = public_form_item_ids(
            indicator_bank_id=indicator_bank_id,
            template_id=template_id,
        )
        if not form_item_ids:
            return mobile_ok(data={
                'period_name': period_name,
                'by_country': {},
                'country_names': {},
                'country_iso2': {},
            })

        # ── Assigned-form rows ──────────────────────────────────────────────
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

        # ── Public-submission rows ──────────────────────────────────────────
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

        # ── Aggregate by country ────────────────────────────────────────────
        by_country: dict[int, float] = {}
        for country_id, numeric, value in list(aes_q.all()) + list(pub_q.all()):
            if not country_id:
                continue
            n = published_numeric(numeric, value)
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
        from app.models import (
            Country,
            IndicatorBank,
        )
        from app.services.forms.reporting_period_service import sort_period_names
        from plugins.fdrs.services.fdrs_public_documents import country_documents

        country = Country.query.filter(db.func.upper(Country.iso3) == code).first()
        if country is None:
            return mobile_not_found('Country not found')

        national_society = country.primary_national_society
        country_payload = {
            'id': country.id,
            'name': country.get_name_translation(locale) if locale != 'en' else country.name,
            'iso2': country.iso2,
            'iso3': country.iso3,
            'region': country.region,
            'national_society_name': national_society.name if national_society else None,
        }

        # ── Published values per (indicator, period) ───────────────────────
        key_data, key_bank_ids = _key_indicator_data(template_id, [country.id])
        item_to_indicator = {
            item_id: indicator_id
            for item_id, indicator_id in _public_item_indicators(template_id).items()
            if indicator_id not in key_bank_ids
        }
        totals: dict[tuple[int, str], float] = {
            (indicator_id, period_name): value
            for (indicator_id, period_name, _country_id), value in _published_totals(
                item_to_indicator, template_id, [country.id]
            ).items()
        }

        all_periods = {p for _, p in totals} | {
            p for data in key_data.values() for p in data['by_period']
        }
        periods_newest_first = sort_period_names(list(all_periods))[:_COUNTRY_PROFILE_MAX_PERIODS]
        period_rank = {p: i for i, p in enumerate(reversed(periods_newest_first))}

        series_by_indicator: dict[int, list[dict]] = {}
        for (indicator_id, period_name), value in totals.items():
            if period_name not in period_rank:
                continue
            series_by_indicator.setdefault(indicator_id, []).append(
                {'period': period_name, 'value': value}
            )
        for series in series_by_indicator.values():
            series.sort(key=lambda point: period_rank[point['period']])

        # ── Indicator + sector metadata ────────────────────────────────────
        indicators = (
            IndicatorBank.query.filter(IndicatorBank.id.in_(list(series_by_indicator))).all()
            if series_by_indicator else []
        )
        sector_names = _sector_names(
            indicators + [data['bank'] for data in key_data.values()], locale
        )

        indicator_items = []
        for ind in indicators:
            series = series_by_indicator[ind.id]
            indicator_items.append({
                'id': ind.id,
                'key': None,
                'name': _localized_text(ind.name_translations, ind.name, locale),
                'unit': ind.unit,
                'sector': _bank_sector(ind, sector_names),
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

        # ── Documents ──────────────────────────────────────────────────────
        cover_images: list[str] = []
        documents: list[dict] = []
        for entry in country_documents(country.id):
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

        return mobile_ok(data={
            'country': country_payload,
            'periods': periods_newest_first,
            'indicators': indicator_items,
            'cover_images': cover_images,
            'documents': documents,
        })
    except Exception as e:
        current_app.logger.error('mobile_country_profile: %s', e, exc_info=True)
        return mobile_server_error('Failed to load country profile.')


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
