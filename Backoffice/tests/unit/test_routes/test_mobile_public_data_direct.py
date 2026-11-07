"""Direct unit tests for app.routes.api.mobile.public_data view functions.

Public routes don't require auth. Auth-required routes (quiz) use route_user.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from flask_login import login_user

pytestmark = [pytest.mark.unit]


def _parse(resp):
    if isinstance(resp, tuple):
        body, status = resp
        return body, status
    return resp, resp.status_code


# ---------------------------------------------------------------------------
# countrymap
# ---------------------------------------------------------------------------

class TestCountrymap:
    def test_success_empty(self, app, db_session):
        from app.routes.api.mobile.public_data import countrymap

        with app.test_request_context('/api/mobile/v1/data/countrymap', method='GET'):
            resp = countrymap()

        body, status = _parse(resp)
        assert status == 200
        assert 'countries' in body.get_json()['data']

    def test_with_locale(self, app, db_session):
        from app.routes.api.mobile.public_data import countrymap

        with app.test_request_context('/api/mobile/v1/data/countrymap?locale=fr', method='GET'):
            resp = countrymap()

        _, status = _parse(resp)
        assert status == 200

    def test_with_country(self, app, db_session):
        from app.routes.api.mobile.public_data import countrymap
        from tests.factories import create_test_country

        create_test_country(db_session, name='CountryA', iso2='CA', iso3='CAA')

        with app.test_request_context('/api/mobile/v1/data/countrymap', method='GET'):
            resp = countrymap()

        body, status = _parse(resp)
        assert status == 200
        countries = body.get_json()['data']['countries']
        assert isinstance(countries, list)


# ---------------------------------------------------------------------------
# sectors_subsectors
# ---------------------------------------------------------------------------

class TestSectorsSubsectors:
    def test_success_empty(self, app, db_session):
        from app.routes.api.mobile.public_data import sectors_subsectors

        with app.test_request_context('/api/mobile/v1/data/sectors-subsectors', method='GET'):
            resp = sectors_subsectors()

        body, status = _parse(resp)
        assert status == 200
        assert 'sectors' in body.get_json()['data']


# ---------------------------------------------------------------------------
# public_indicator_bank
# ---------------------------------------------------------------------------

class TestPublicIndicatorBank:
    def test_success(self, app, db_session):
        from app.routes.api.mobile.public_data import public_indicator_bank

        with app.test_request_context('/api/mobile/v1/data/indicator-bank', method='GET'):
            with patch(
                'app.services.indicators.bank_service.get_indicator_list',
                return_value=([], 0, 1, 20),
            ):
                resp = public_indicator_bank()

        body, status = _parse(resp)
        assert status == 200
        assert body.get_json()['data'] == []

    def test_with_search_params(self, app, db_session):
        from app.routes.api.mobile.public_data import public_indicator_bank

        with app.test_request_context(
            '/api/mobile/v1/data/indicator-bank?search=population&type=number&sector=health',
            method='GET',
        ):
            with patch(
                'app.services.indicators.bank_service.get_indicator_list',
                return_value=([], 0, 1, 20),
            ):
                resp = public_indicator_bank()

        _, status = _parse(resp)
        assert status == 200


# ---------------------------------------------------------------------------
# public_indicator_detail
# ---------------------------------------------------------------------------

class TestPublicIndicatorDetail:
    def test_not_found(self, app, db_session):
        from app.routes.api.mobile.public_data import public_indicator_detail

        with app.test_request_context('/api/mobile/v1/data/indicator-bank/99999', method='GET'):
            resp = public_indicator_detail(99999)

        _, status = _parse(resp)
        assert status == 404

    def test_success(self, app, db_session):
        from app.routes.api.mobile.public_data import public_indicator_detail
        from app.models import IndicatorBank

        ib = IndicatorBank(name='Test Indicator', type='number')
        db_session.add(ib)
        db_session.commit()
        db_session.refresh(ib)

        with app.test_request_context(
            f'/api/mobile/v1/data/indicator-bank/{ib.id}', method='GET'
        ):
            with patch(
                'app.services.indicators.bank_service.serialize_indicator_list',
                return_value=[{'id': ib.id, 'name': ib.name}],
            ):
                resp = public_indicator_detail(ib.id)

        body, status = _parse(resp)
        assert status == 200
        assert body.get_json()['data']['indicator']['id'] == ib.id


# ---------------------------------------------------------------------------
# submit_indicator_suggestion
# ---------------------------------------------------------------------------

class TestSubmitIndicatorSuggestion:
    def test_missing_fields_returns_400(self, app, db_session):
        from app.routes.api.mobile.public_data import submit_indicator_suggestion

        with app.test_request_context(
            '/api/mobile/v1/data/indicator-suggestions',
            method='POST',
            data=json.dumps({}),
            content_type='application/json',
        ):
            resp = submit_indicator_suggestion()

        _, status = _parse(resp)
        assert status == 400

    def test_success(self, app, db_session):
        from app.routes.api.mobile.public_data import submit_indicator_suggestion

        payload = {
            'submitter_name': 'Test User',
            'submitter_email': 'test@example.com',
            'suggestion_type': 'new_indicator',
            'indicator_name': 'New Indicator',
            'reason': 'This is needed for tracking',
        }

        with app.test_request_context(
            '/api/mobile/v1/data/indicator-suggestions',
            method='POST',
            data=json.dumps(payload),
            content_type='application/json',
        ):
            with patch('app.services.email.service.send_suggestion_confirmation_email'), \
                 patch('app.services.email.service.send_admin_notification_email'):
                resp = submit_indicator_suggestion()

        _, status = _parse(resp)
        assert status == 201

    def test_with_sector_subsector(self, app, db_session):
        from app.routes.api.mobile.public_data import submit_indicator_suggestion

        payload = {
            'submitter_name': 'Test User',
            'submitter_email': 'test@example.com',
            'suggestion_type': 'new_indicator',
            'indicator_name': 'Sector Indicator',
            'reason': 'Needed',
            'sector': {'primary': 'Health', 'secondary': None, 'tertiary': None},
            'sub_sector': {'primary': 'Primary Care', 'secondary': None, 'tertiary': None},
        }

        with app.test_request_context(
            '/api/mobile/v1/data/indicator-suggestions',
            method='POST',
            data=json.dumps(payload),
            content_type='application/json',
        ):
            with patch('app.services.email.service.send_suggestion_confirmation_email'), \
                 patch('app.services.email.service.send_admin_notification_email'):
                resp = submit_indicator_suggestion()

        _, status = _parse(resp)
        assert status == 201

    def test_empty_required_field_returns_400(self, app, db_session):
        from app.routes.api.mobile.public_data import submit_indicator_suggestion

        payload = {
            'submitter_name': '',
            'submitter_email': 'test@example.com',
            'suggestion_type': 'new_indicator',
            'indicator_name': 'Indicator',
            'reason': 'Reason',
        }

        with app.test_request_context(
            '/api/mobile/v1/data/indicator-suggestions',
            method='POST',
            data=json.dumps(payload),
            content_type='application/json',
        ):
            resp = submit_indicator_suggestion()

        _, status = _parse(resp)
        assert status == 400

    def test_invalid_sector_primary_returns_400(self, app, db_session):
        from app.routes.api.mobile.public_data import submit_indicator_suggestion

        payload = {
            'submitter_name': 'Test',
            'submitter_email': 'test@example.com',
            'suggestion_type': 'new_indicator',
            'indicator_name': 'Test',
            'reason': 'Reason',
            'sector': {'primary': ''},
        }

        with app.test_request_context(
            '/api/mobile/v1/data/indicator-suggestions',
            method='POST',
            data=json.dumps(payload),
            content_type='application/json',
        ):
            resp = submit_indicator_suggestion()

        _, status = _parse(resp)
        assert status == 400

    def test_error_returns_500(self, app, db_session):
        from app.routes.api.mobile.public_data import submit_indicator_suggestion

        payload = {
            'submitter_name': 'Test',
            'submitter_email': 'test@example.com',
            'suggestion_type': 'new_indicator',
            'indicator_name': 'Indicator',
            'reason': 'Reason',
        }

        with app.test_request_context(
            '/api/mobile/v1/data/indicator-suggestions',
            method='POST',
            data=json.dumps(payload),
            content_type='application/json',
        ):
            from app import db as _db
            with patch.object(_db.session, 'add', side_effect=RuntimeError('db fail')), \
                 patch('app.utils.transactions.request_transaction_rollback'):
                resp = submit_indicator_suggestion()

        _, status = _parse(resp)
        assert status == 500


# ---------------------------------------------------------------------------
# quiz_leaderboard (auth required)
# ---------------------------------------------------------------------------

class TestQuizLeaderboard:
    def test_success_empty(self, app, db_session, route_user):
        from app.routes.api.mobile.public_data import quiz_leaderboard

        with app.test_request_context('/api/mobile/v1/data/quiz/leaderboard', method='GET'):
            login_user(route_user)
            resp = quiz_leaderboard()

        body, status = _parse(resp)
        assert status == 200
        assert 'leaderboard' in body.get_json()['data']

    def test_with_limit(self, app, db_session, route_user):
        from app.routes.api.mobile.public_data import quiz_leaderboard

        with app.test_request_context(
            '/api/mobile/v1/data/quiz/leaderboard?limit=5', method='GET'
        ):
            login_user(route_user)
            resp = quiz_leaderboard()

        _, status = _parse(resp)
        assert status == 200

    def test_invalid_limit_uses_default(self, app, db_session, route_user):
        from app.routes.api.mobile.public_data import quiz_leaderboard

        with app.test_request_context(
            '/api/mobile/v1/data/quiz/leaderboard?limit=999', method='GET'
        ):
            login_user(route_user)
            resp = quiz_leaderboard()

        _, status = _parse(resp)
        assert status == 200


# ---------------------------------------------------------------------------
# mobile_periods
# ---------------------------------------------------------------------------

class TestMobilePeriods:
    def test_success_empty(self, app, db_session):
        from app.routes.api.mobile.public_data import mobile_periods

        with app.test_request_context('/api/mobile/v1/data/periods', method='GET'):
            resp = mobile_periods()

        body, status = _parse(resp)
        assert status == 200
        assert 'periods' in body.get_json()['data']

    def test_defaults_to_fdrs_template_id(self, app, db_session):
        """Without template_id, periods are scoped to FDRS (template 21 by default)."""
        from unittest.mock import patch

        from app.models import AssignedForm
        from app.routes.api.mobile.public_data import mobile_periods
        from tests.factories import create_test_template

        with app.app_context():
            fdrs_tmpl = create_test_template(db_session)
            other_tmpl = create_test_template(db_session)
            db_session.add(AssignedForm(template_id=fdrs_tmpl.id, period_name='FDRS-Only'))
            db_session.add(AssignedForm(template_id=other_tmpl.id, period_name='Other-Only'))
            db_session.commit()
            fdrs_id = fdrs_tmpl.id

        with patch('app.utils.data_quality_constants.FDRS_TEMPLATE_ID', fdrs_id):
            with app.test_request_context('/api/mobile/v1/data/periods', method='GET'):
                resp = mobile_periods()

        body, status = _parse(resp)
        assert status == 200
        periods = body.get_json()['data']['periods']
        assert 'FDRS-Only' in periods
        assert 'Other-Only' not in periods

    def test_with_template_filter(self, app, db_session):
        from app.routes.api.mobile.public_data import mobile_periods

        with app.test_request_context(
            '/api/mobile/v1/data/periods?template_id=1', method='GET'
        ):
            resp = mobile_periods()

        _, status = _parse(resp)
        assert status == 200

    def test_with_country_filter(self, app, db_session):
        from app.routes.api.mobile.public_data import mobile_periods

        with app.test_request_context(
            '/api/mobile/v1/data/periods?country_id=1', method='GET'
        ):
            resp = mobile_periods()

        _, status = _parse(resp)
        assert status == 200


# ---------------------------------------------------------------------------
# mobile_fdrs_overview
# ---------------------------------------------------------------------------

class TestMobileFdrsOverview:
    def test_missing_indicator_bank_id_returns_400(self, app, db_session):
        from app.routes.api.mobile.public_data import mobile_fdrs_overview

        with app.test_request_context('/api/mobile/v1/data/fdrs-overview', method='GET'):
            resp = mobile_fdrs_overview()

        _, status = _parse(resp)
        assert status == 400

    def test_success_no_form_items(self, app, db_session):
        from app.routes.api.mobile.public_data import mobile_fdrs_overview

        with app.test_request_context(
            '/api/mobile/v1/data/fdrs-overview?indicator_bank_id=999', method='GET'
        ):
            resp = mobile_fdrs_overview()

        body, status = _parse(resp)
        assert status == 200
        assert 'by_country' in body.get_json()['data']

    def test_with_period_and_template(self, app, db_session):
        from app.routes.api.mobile.public_data import mobile_fdrs_overview

        with app.test_request_context(
            '/api/mobile/v1/data/fdrs-overview?indicator_bank_id=999&period_name=2024&template_id=1',
            method='GET',
        ):
            resp = mobile_fdrs_overview()

        _, status = _parse(resp)
        assert status == 200

    def test_uses_published_snapshot_not_live_value(self, app, db_session):
        from sqlalchemy.orm.attributes import flag_modified

        from app.models import FormData, IndicatorBank
        from app.routes.api.mobile.public_data import mobile_disaggregation_overview, mobile_fdrs_overview
        from tests.factories import (
            create_test_assignment_entity_status,
            create_test_country,
            create_test_item,
            create_test_section,
            create_test_template,
        )

        template = create_test_template(db_session, name="Mobile published overview")
        section = create_test_section(db_session, template)
        indicator = IndicatorBank(name="People reached published", type="number", unit="people", archived=False)
        db_session.add(indicator)
        db_session.commit()
        item = create_test_item(
            db_session,
            section,
            template,
            label="Public people reached",
            indicator_bank_id=indicator.id,
        )
        item.set_privacy("public")
        flag_modified(item, "config")
        db_session.commit()

        country = create_test_country(db_session, name="Snapshotland", iso3="SNP")
        aes = create_test_assignment_entity_status(
            db_session, country=country, template=template, period_name="2024",
        )
        db_session.add(FormData(
            assignment_entity_status_id=aes.id,
            form_item_id=item.id,
            value="999",
            numeric_value=999,
            published_value="40",
            published_numeric_value=40,
            published_disagg_data={"mode": "sex", "values": {"female": 30, "male": 10}},
        ))
        db_session.commit()

        with app.test_request_context(
            f"/api/mobile/v1/data/fdrs-overview?indicator_bank_id={indicator.id}&template_id={template.id}&period_name=2024",
            method="GET",
        ):
            resp = mobile_fdrs_overview()

        body, status = _parse(resp)
        assert status == 200
        by_country = body.get_json()["data"]["by_country"]
        assert by_country.get(str(country.id)) == 40

        with app.test_request_context(
            f"/api/mobile/v1/data/disaggregation-overview?indicator_bank_id={indicator.id}&template_id={template.id}&period_name=2024",
            method="GET",
        ):
            disagg_resp = mobile_disaggregation_overview()

        disagg_body, disagg_status = _parse(disagg_resp)
        assert disagg_status == 200
        payload = disagg_body.get_json()["data"]
        assert payload["record_count"] == 1
        assert payload["total"] != 999
        sexes = {row["category"]: row["value"] for row in payload["by_sex"]}
        assert sexes.get("Female") == 30
        assert sexes.get("Male") == 10


# ---------------------------------------------------------------------------
# mobile_country_profile
# ---------------------------------------------------------------------------

class TestMobileCountryProfile:
    def test_invalid_iso3_returns_400(self, app, db_session):
        from app.routes.api.mobile.public_data import mobile_country_profile

        with app.test_request_context('/api/mobile/v1/data/country-profile/12', method='GET'):
            resp = mobile_country_profile('12')

        _, status = _parse(resp)
        assert status == 400

    def test_unknown_country_returns_404(self, app, db_session):
        from app.routes.api.mobile.public_data import mobile_country_profile

        with app.test_request_context('/api/mobile/v1/data/country-profile/ZZZ', method='GET'):
            resp = mobile_country_profile('ZZZ')

        _, status = _parse(resp)
        assert status == 404

    def test_returns_published_series_only_for_public_items(self, app, db_session):
        from sqlalchemy.orm.attributes import flag_modified

        from app.models import FormData, IndicatorBank
        from app.routes.api.mobile.public_data import mobile_country_profile
        from tests.factories import (
            create_test_assignment_entity_status,
            create_test_country,
            create_test_item,
            create_test_section,
            create_test_template,
        )

        template = create_test_template(db_session, name="Country profile template")
        section = create_test_section(db_session, template)
        indicator = IndicatorBank(name="Volunteers profile", type="number", unit="people", archived=False)
        db_session.add(indicator)
        db_session.commit()
        item = create_test_item(
            db_session, section, template, label="Public volunteers", indicator_bank_id=indicator.id,
        )
        item.set_privacy("public")
        flag_modified(item, "config")
        db_session.commit()

        country = create_test_country(db_session, name="Profileland", iso3="PRF")
        aes = create_test_assignment_entity_status(
            db_session, country=country, template=template, period_name="2024",
        )
        db_session.add(FormData(
            assignment_entity_status_id=aes.id,
            form_item_id=item.id,
            value="999",
            numeric_value=999,
            published_value="40",
            published_numeric_value=40,
        ))
        db_session.commit()

        with app.test_request_context(
            f'/api/mobile/v1/data/country-profile/prf?template_id={template.id}', method='GET',
        ):
            resp = mobile_country_profile('prf')

        body, status = _parse(resp)
        assert status == 200
        data = body.get_json()['data']
        assert data['country']['iso3'] == 'PRF'
        assert data['periods'] == ['2024']
        assert len(data['indicators']) == 1
        entry = data['indicators'][0]
        assert entry['id'] == indicator.id
        assert entry['latest_value'] == 40
        assert entry['series'] == [{'period': '2024', 'value': 40}]
        assert data['documents'] == []
        assert data['cover_images'] == []


class TestMobileRegionProfile:
    def test_unknown_region_returns_404(self, app, db_session):
        from app.routes.api.mobile.public_data import mobile_region_profile

        with app.test_request_context('/api/mobile/v1/data/region-profile/nowhere', method='GET'):
            resp = mobile_region_profile('nowhere')

        _, status = _parse(resp)
        assert status == 404

    def test_sums_key_indicator_across_region_countries(self, app, db_session):
        from sqlalchemy.orm.attributes import flag_modified

        from app.models import FormData, IndicatorBank
        from app.routes.api.mobile.public_data import mobile_region_profile
        from tests.factories import (
            create_test_assignment_entity_status,
            create_test_country,
            create_test_item,
            create_test_section,
            create_test_template,
        )

        template = create_test_template(db_session, name="Region profile template")
        section = create_test_section(db_session, template)
        indicator = IndicatorBank(
            name="Reached with health", type="number", unit="people", archived=False,
            fdrs_kpi_code="KPI_ReachH",
        )
        db_session.add(indicator)
        db_session.commit()
        item = create_test_item(
            db_session, section, template, label="Public volunteers", indicator_bank_id=indicator.id,
        )
        item.set_privacy("public")
        flag_modified(item, "config")
        db_session.commit()

        first_aes = None
        for name, iso3, value in (("Regionone", "RG1", 40), ("Regiontwo", "RG2", 10)):
            country = create_test_country(db_session, name=name, iso3=iso3, region="Test Region")
            if first_aes is None:
                aes = first_aes = create_test_assignment_entity_status(
                    db_session, country=country, template=template, period_name="2024",
                )
            else:
                from app.models.assignments import AssignmentEntityStatus

                aes = AssignmentEntityStatus(
                    assigned_form_id=first_aes.assigned_form_id,
                    entity_type="country",
                    entity_id=country.id,
                    status="in_progress",
                )
                db_session.add(aes)
                db_session.flush()
            db_session.add(FormData(
                assignment_entity_status_id=aes.id,
                form_item_id=item.id,
                published_value=str(value),
                published_numeric_value=value,
            ))
        db_session.commit()

        with app.test_request_context(
            f'/api/mobile/v1/data/region-profile/test-region?template_id={template.id}',
            method='GET',
        ):
            resp = mobile_region_profile('test-region')

        body, status = _parse(resp)
        assert status == 200
        data = body.get_json()['data']
        assert data['region']['country_count'] == 2
        entry = data['indicators'][0]
        assert entry['key'] == 'KPI_ReachH'
        assert entry['group'] == 'people_reached'
        assert entry['latest_value'] == 50
        assert entry['reporting_countries'] == 2
        assert [c['iso3'] for c in entry['top_countries']] == ['RG1', 'RG2']


def _seed_public_reach_indicator(db_session, template, section, *, kpi_code, name, sector_id=None):
    from sqlalchemy.orm.attributes import flag_modified

    from app.models import IndicatorBank
    from tests.factories import create_test_item

    indicator = IndicatorBank(
        name=name, type="number", unit="people", archived=False, fdrs_kpi_code=kpi_code,
        sector={"primary": sector_id} if sector_id else None,
    )
    db_session.add(indicator)
    db_session.commit()
    item = create_test_item(db_session, section, template, label=name, indicator_bank_id=indicator.id)
    item.set_privacy("public")
    flag_modified(item, "config")
    db_session.commit()
    return indicator, item


class TestMobileFdrsKpiOverview:
    def test_requires_bank_id_or_kpi_code(self, app, db_session):
        from app.routes.api.mobile.public_data import mobile_fdrs_overview

        with app.test_request_context('/api/mobile/v1/data/fdrs-overview', method='GET'):
            resp = mobile_fdrs_overview()

        _, status = _parse(resp)
        assert status == 400

    def test_unknown_kpi_code_returns_400(self, app, db_session):
        from app.routes.api.mobile.public_data import mobile_fdrs_overview

        with app.test_request_context(
            '/api/mobile/v1/data/fdrs-overview?kpi_code=KPI_Nope', method='GET'
        ):
            resp = mobile_fdrs_overview()

        _, status = _parse(resp)
        assert status == 400

    def test_kpi_code_uses_larger_value_of_duplicate_banks(self, app, db_session):
        from app.models import FormData
        from app.routes.api.mobile.public_data import mobile_fdrs_overview
        from tests.factories import (
            create_test_assignment_entity_status,
            create_test_country,
            create_test_section,
            create_test_template,
        )

        template = create_test_template(db_session, name="Kpi overview template")
        section = create_test_section(db_session, template)
        country = create_test_country(db_session, name="Kpiland", iso3="KPL")
        _, item_a = _seed_public_reach_indicator(
            db_session, template, section, kpi_code="KPI_ReachH", name="Health A"
        )
        _, item_b = _seed_public_reach_indicator(
            db_session, template, section, kpi_code="KPI_ReachH", name="Health B"
        )
        aes = create_test_assignment_entity_status(
            db_session, country=country, template=template, period_name="2024",
        )
        for item, value in ((item_a, 40), (item_b, 25)):
            db_session.add(FormData(
                assignment_entity_status_id=aes.id,
                form_item_id=item.id,
                published_value=str(value),
                published_numeric_value=value,
            ))
        db_session.commit()

        with app.test_request_context(
            f'/api/mobile/v1/data/fdrs-overview?kpi_code=KPI_ReachH&template_id={template.id}&period_name=2024',
            method='GET',
        ):
            resp = mobile_fdrs_overview()

        body, status = _parse(resp)
        assert status == 200
        data = body.get_json()['data']
        assert data['by_country'] == {str(country.id): 40}
        assert data['global_total'] == 40


class TestMobileFdrsReachIndicators:
    def test_groups_public_indicators_by_sector(self, app, db_session):
        from app.models import Sector
        from app.routes.api.mobile.public_data import mobile_fdrs_reach_indicators
        from tests.factories import create_test_section, create_test_template

        template = create_test_template(db_session, name="Reach sectors template")
        section = create_test_section(db_session, template)
        health = Sector(name="Reach Health", display_order=1)
        shelter = Sector(name="Reach Shelter", display_order=2)
        db_session.add_all([health, shelter])
        db_session.commit()
        _seed_public_reach_indicator(
            db_session, template, section, kpi_code="KPI_ReachS", name="Shelter reach", sector_id=shelter.id
        )
        _seed_public_reach_indicator(
            db_session, template, section, kpi_code="KPI_ReachHPM", name="Mental health reach", sector_id=health.id
        )
        _seed_public_reach_indicator(
            db_session, template, section, kpi_code="KPI_ReachH", name="Health reach", sector_id=health.id
        )

        with app.test_request_context(
            f'/api/mobile/v1/data/fdrs-reach-indicators?template_id={template.id}', method='GET'
        ):
            resp = mobile_fdrs_reach_indicators()

        body, status = _parse(resp)
        assert status == 200
        sectors = body.get_json()['data']['sectors']
        assert [s['name'] for s in sectors] == ["Reach Health", "Reach Shelter"]
        assert [i['kpi_code'] for i in sectors[0]['indicators']] == ["KPI_ReachH", "KPI_ReachHPM"]
        assert [i['kpi_code'] for i in sectors[1]['indicators']] == ["KPI_ReachS"]

    def test_skips_indicators_without_public_items(self, app, db_session):
        from app.models import IndicatorBank
        from app.routes.api.mobile.public_data import mobile_fdrs_reach_indicators
        from tests.factories import create_test_template

        template = create_test_template(db_session, name="Reach private template")
        db_session.add(IndicatorBank(
            name="Hidden reach", type="number", unit="people", archived=False, fdrs_kpi_code="KPI_ReachL",
        ))
        db_session.commit()

        with app.test_request_context(
            f'/api/mobile/v1/data/fdrs-reach-indicators?template_id={template.id}', method='GET'
        ):
            resp = mobile_fdrs_reach_indicators()

        body, status = _parse(resp)
        assert status == 200
        assert body.get_json()['data']['sectors'] == []


# ---------------------------------------------------------------------------
# public_resources
# ---------------------------------------------------------------------------

class TestPublicResources:
    def test_success_empty(self, app, db_session):
        from app.routes.api.mobile.public_data import public_resources

        with app.test_request_context('/api/mobile/v1/data/resources', method='GET'):
            resp = public_resources()

        _, status = _parse(resp)
        assert status == 200

    def test_with_filters(self, app, db_session):
        from app.routes.api.mobile.public_data import public_resources

        with app.test_request_context(
            '/api/mobile/v1/data/resources?search=guide&resource_type=guide',
            method='GET',
        ):
            resp = public_resources()

        _, status = _parse(resp)
        assert status == 200


# ---------------------------------------------------------------------------
# unified_planning_config
# ---------------------------------------------------------------------------

class TestUnifiedPlanningConfig:
    def test_success(self, app, db_session):
        from app.routes.api.mobile.public_data import unified_planning_config

        with app.test_request_context(
            '/api/mobile/v1/data/unified-planning-config', method='GET'
        ):
            resp = unified_planning_config()

        body, status = _parse(resp)
        assert status == 200
        data = body.get_json()['data']
        # Flat config keys (not nested under "config")
        assert 'ifrc_public_site_appeals_url' in data
        assert 'document_types' in data


# ---------------------------------------------------------------------------
# unified_planning_thumbnail (POST)
# ---------------------------------------------------------------------------

class TestUnifiedPlanningThumbnail:
    def test_missing_url_returns_400(self, app, db_session):
        from app.routes.api.mobile.public_data import unified_planning_thumbnail

        with app.test_request_context(
            '/api/mobile/v1/data/unified-planning-thumbnail',
            method='POST',
            data=json.dumps({}),
            content_type='application/json',
        ):
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = unified_planning_thumbnail()

        _, status = _parse(resp)
        assert status == 400

    def test_invalid_host_returns_400(self, app, db_session):
        from app.routes.api.mobile.public_data import unified_planning_thumbnail
        import base64

        bad_url = 'https://evil.example.com/page.pdf'
        url_b64 = base64.urlsafe_b64encode(bad_url.encode()).decode()

        with app.test_request_context(
            '/api/mobile/v1/data/unified-planning-thumbnail',
            method='POST',
            data=json.dumps({'url_b64': url_b64}),
            content_type='application/json',
        ):
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = unified_planning_thumbnail()

        _, status = _parse(resp)
        assert status == 400

    def test_cached_response(self, app, db_session):
        """Returns cached JPEG if already in cache."""
        from plugins.upr.mobile import (
            unified_planning_thumbnail,
            _UNIFIED_PLANNING_THUMB_JPEG,
            _UNIFIED_PLANNING_THUMB_LOCK,
        )
        import base64
        from hashlib import sha256

        valid_url = 'https://prddsgofilestorage.blob.core.windows.net/api/planning.pdf'
        url_b64 = base64.urlsafe_b64encode(valid_url.encode()).decode()
        cache_key = sha256(valid_url.encode()).hexdigest()

        with _UNIFIED_PLANNING_THUMB_LOCK:
            _UNIFIED_PLANNING_THUMB_JPEG[cache_key] = b'\xff\xd8\xff\xe0cached'

        try:
            with app.test_request_context(
                '/api/mobile/v1/data/unified-planning-thumbnail',
                method='POST',
                data=json.dumps({'url_b64': url_b64}),
                content_type='application/json',
            ):
                with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                     patch(
                         'app.routes.ai_documents.helpers._validate_ifrc_fetch_url',
                         return_value=(True, ''),
                     ):
                    resp = unified_planning_thumbnail()

            _, status = _parse(resp)
            assert status == 200
        finally:
            with _UNIFIED_PLANNING_THUMB_LOCK:
                _UNIFIED_PLANNING_THUMB_JPEG.pop(cache_key, None)
