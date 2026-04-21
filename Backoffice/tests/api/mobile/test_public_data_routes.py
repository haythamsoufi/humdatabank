"""Integration tests for /api/mobile/v1/data/* endpoints."""
import pytest
from tests.api.mobile.helpers import assert_mobile_ok, assert_mobile_paginated

PREFIX = '/api/mobile/v1'


@pytest.mark.api
@pytest.mark.integration
class TestCountryMap:
    def test_requires_auth(self, client, db_session):
        resp = client.get(f'{PREFIX}/data/countrymap')
        assert resp.status_code == 401

    def test_returns_countries(self, client, jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/data/countrymap', headers=jwt_headers)
        assert_mobile_ok(resp, has_data=True)
        assert 'countries' in resp.get_json()['data']


@pytest.mark.api
@pytest.mark.integration
class TestSectorsSubsectors:
    def test_returns_data(self, client, jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/data/sectors-subsectors', headers=jwt_headers)
        assert_mobile_ok(resp, has_data=True)
        data = resp.get_json()['data']
        assert 'sectors' in data
        assert 'subsectors' in data


@pytest.mark.api
@pytest.mark.integration
class TestPublicIndicatorBank:
    def test_returns_paginated(self, client, jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/data/indicator-bank', headers=jwt_headers)
        assert_mobile_paginated(resp)


@pytest.mark.api
@pytest.mark.integration
class TestIndicatorSuggestions:
    def test_missing_required_fields(self, client, jwt_headers, db_session):
        resp = client.post(
            f'{PREFIX}/data/indicator-suggestions',
            headers=jwt_headers,
            json={'definition': 'x'},
        )
        assert resp.status_code == 400

    def test_submit_suggestion(self, client, jwt_headers, db_session):
        resp = client.post(
            f'{PREFIX}/data/indicator-suggestions',
            headers=jwt_headers,
            json={
                'submitter_name': 'Test User',
                'submitter_email': 'test@example.com',
                'suggestion_type': 'new_indicator',
                'indicator_name': 'New Indicator',
                'definition': 'A definition',
                'reason': 'Needed for reporting',
                'sector': {
                    'primary': 'Health',
                    'secondary': '',
                    'tertiary': '',
                },
                'sub_sector': {
                    'primary': 'WASH',
                    'secondary': '',
                    'tertiary': '',
                },
            },
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body['success'] is True
        assert 'suggestion_id' in body['data']


@pytest.mark.api
@pytest.mark.integration
class TestQuizLeaderboard:
    def test_returns_leaderboard(self, client, jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/data/quiz/leaderboard', headers=jwt_headers)
        assert_mobile_ok(resp, has_data=True)
        assert 'leaderboard' in resp.get_json()['data']


@pytest.mark.api
@pytest.mark.integration
class TestQuizSubmitScore:
    def test_missing_fields(self, client, jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/data/quiz/submit-score',
                           headers=jwt_headers, json={})
        assert resp.status_code == 400

    def test_submit_score(self, client, jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/data/quiz/submit-score',
                           headers=jwt_headers,
                           json={'user_name': 'Player1', 'score': 95})
        assert_mobile_ok(resp, has_data=True)
