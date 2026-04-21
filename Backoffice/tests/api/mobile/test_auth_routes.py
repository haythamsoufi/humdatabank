"""Integration tests for /api/mobile/v1/auth/* endpoints."""
import json
import pytest
from tests.api.mobile.helpers import assert_mobile_ok, assert_mobile_error

PREFIX = '/api/mobile/v1'


@pytest.mark.api
@pytest.mark.integration
class TestIssueTokens:
    def test_valid_credentials(self, client, mobile_user, db_session):
        resp = client.post(f'{PREFIX}/auth/token', json={
            'email': 'mobile@test.com', 'password': 'MobilePass123!',
        })
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        assert 'access_token' in body.get('data', {})
        assert 'refresh_token' in body.get('data', {})
        assert body['data']['user']['email'] == 'mobile@test.com'

    def test_wrong_password(self, client, mobile_user, db_session):
        resp = client.post(f'{PREFIX}/auth/token', json={
            'email': 'mobile@test.com', 'password': 'WrongPassword!',
        })
        assert resp.status_code == 401

    def test_missing_fields(self, client, db_session):
        resp = client.post(f'{PREFIX}/auth/token', json={'email': 'x@x.com'})
        assert resp.status_code == 400

    def test_inactive_user(self, client, db_session, app):
        from tests.factories import create_test_user
        with app.app_context():
            create_test_user(db_session, email='inactive@test.com', password='Pass123!', active=False)
        resp = client.post(f'{PREFIX}/auth/token', json={
            'email': 'inactive@test.com', 'password': 'Pass123!',
        })
        assert resp.status_code == 403


@pytest.mark.api
@pytest.mark.integration
class TestRefreshToken:
    def test_valid_refresh(self, client, mobile_user, db_session):
        login_resp = client.post(f'{PREFIX}/auth/token', json={
            'email': 'mobile@test.com', 'password': 'MobilePass123!',
        })
        refresh_token = login_resp.get_json()['data']['refresh_token']

        resp = client.post(f'{PREFIX}/auth/refresh', json={'refresh_token': refresh_token})
        assert resp.status_code == 200
        body = resp.get_json()
        assert 'access_token' in body.get('data', {})

    def test_missing_refresh_token(self, client, db_session):
        resp = client.post(f'{PREFIX}/auth/refresh', json={})
        assert resp.status_code == 400

    def test_invalid_refresh_token(self, client, db_session):
        resp = client.post(f'{PREFIX}/auth/refresh', json={'refresh_token': 'bogus'})
        assert resp.status_code == 401


@pytest.mark.api
@pytest.mark.integration
class TestSessionCheck:
    def test_returns_user(self, client, jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/auth/session', headers=jwt_headers)
        assert_mobile_ok(resp, has_data=True)
        assert 'user' in resp.get_json()['data']


@pytest.mark.api
@pytest.mark.integration
class TestLogout:
    def test_logout_success(self, client, jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/auth/logout', headers=jwt_headers)
        assert_mobile_ok(resp, has_message=True)


@pytest.mark.api
@pytest.mark.integration
class TestChangePassword:
    def test_valid_change(self, client, mobile_user, db_session, app):
        from tests.api.mobile.conftest import _make_jwt_headers
        headers = _make_jwt_headers(app, mobile_user)
        resp = client.post(f'{PREFIX}/auth/change-password', headers=headers, json={
            'current_password': 'MobilePass123!',
            'new_password': 'NewSecurePass456!',
        })
        assert resp.status_code == 200

    def test_wrong_current_password(self, client, jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/auth/change-password', headers=jwt_headers, json={
            'current_password': 'WrongCurrent!',
            'new_password': 'NewSecurePass456!',
        })
        assert resp.status_code == 401

    def test_missing_fields(self, client, jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/auth/change-password', headers=jwt_headers, json={})
        assert resp.status_code == 400


@pytest.mark.api
@pytest.mark.integration
class TestProfile:
    def test_get_profile(self, client, jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/auth/profile', headers=jwt_headers)
        assert_mobile_ok(resp, has_data=True)
        data = resp.get_json()['data']
        assert 'user' in data
        assert 'role' in data['user']

    def test_update_profile(self, client, jwt_headers, db_session):
        resp = client.put(f'{PREFIX}/auth/profile', headers=jwt_headers, json={
            'name': 'Updated Name',
        })
        assert_mobile_ok(resp, has_message=True)
