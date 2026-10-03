"""Mobile FDRS overview: pre-aggregated indicator totals per country."""

from __future__ import annotations

from flask import current_app, request

from app.extensions import db
from app.utils.mobile_responses import mobile_bad_request, mobile_ok, mobile_server_error


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
