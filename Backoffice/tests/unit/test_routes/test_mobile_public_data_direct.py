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
                'app.services.indicator_bank_service.get_indicator_list',
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
                'app.services.indicator_bank_service.get_indicator_list',
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

        ib = IndicatorBank(name='Test Indicator', code='TEST001', indicator_type='number')
        db_session.add(ib)
        db_session.commit()
        db_session.refresh(ib)

        with app.test_request_context(
            f'/api/mobile/v1/data/indicator-bank/{ib.id}', method='GET'
        ):
            with patch(
                'app.services.indicator_bank_service.serialize_indicator_list',
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
            'suggestion_type': 'new',
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
            'suggestion_type': 'new',
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
            'suggestion_type': 'new',
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
            'suggestion_type': 'new',
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
            'suggestion_type': 'new',
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
        assert 'config' in body.get_json()['data']


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
        from app.routes.api.mobile.public_data import unified_planning_thumbnail, \
            _UNIFIED_PLANNING_THUMB_JPEG, _UNIFIED_PLANNING_THUMB_LOCK
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
                with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                    resp = unified_planning_thumbnail()

            _, status = _parse(resp)
            assert status == 200
        finally:
            with _UNIFIED_PLANNING_THUMB_LOCK:
                _UNIFIED_PLANNING_THUMB_JPEG.pop(cache_key, None)
