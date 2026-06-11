"""Integration tests for /api/mobile/v1/auth/* endpoints."""
import json
import pytest
from unittest.mock import patch
from tests.api.mobile.helpers import assert_mobile_ok, assert_mobile_error

pytestmark = [pytest.mark.api, pytest.mark.integration, pytest.mark.auth_security]
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
            'new_password': 'XwQ9#mP2vL8!zR',  # no sequential characters
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


@pytest.mark.api
@pytest.mark.integration
class TestExchangeSession:
    def test_exchange_session_with_cookie(self, client, mobile_user, db_session, app):
        user_id = int(mobile_user.id)
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user_id)
            sess['_fresh'] = True
            sess['session_id'] = 'existing-web-session'
        with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
            resp = client.post(
                f'{PREFIX}/auth/exchange-session',
                headers={'Content-Type': 'application/json', 'X-App-Version': '99.0.0'},
            )
        assert resp.status_code == 200
        body = resp.get_json()
        assert 'access_token' in body.get('data', {})

    def test_exchange_session_requires_login(self, client, db_session):
        resp = client.post(f'{PREFIX}/auth/exchange-session')
        assert resp.status_code == 401


@pytest.mark.api
@pytest.mark.integration
class TestIssueTokensLockout:
    def test_account_locked_returns_429(self, client, mobile_user, db_session, app):
        from app.models.core import UserLoginLog
        from app.utils.datetime_helpers import utcnow
        with app.app_context():
            for _ in range(10):
                db_session.add(UserLoginLog(
                    email_attempted='mobile@test.com',
                    event_type='login_failed',
                    timestamp=utcnow(),
                    ip_address='127.0.0.1',
                ))
            db_session.commit()
        resp = client.post(f'{PREFIX}/auth/token', json={
            'email': 'mobile@test.com', 'password': 'MobilePass123!',
        })
        assert resp.status_code == 429
        body = resp.get_json()
        assert body.get('error_code') == 'ACCOUNT_LOCKED'


@pytest.mark.api
@pytest.mark.integration
class TestChangePasswordValidation:
    def test_weak_new_password_rejected(self, client, jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/auth/change-password', headers=jwt_headers, json={
            'current_password': 'MobilePass123!',
            'new_password': '12345678',
        })
        assert resp.status_code == 400


@pytest.mark.api
@pytest.mark.integration
class TestRefreshTokenExtended:
    def test_refresh_token_reuse_blacklists_session(self, client, mobile_user, db_session, app):
        login_resp = client.post(f'{PREFIX}/auth/token', json={
            'email': 'mobile@test.com', 'password': 'MobilePass123!',
        })
        refresh_token = login_resp.get_json()['data']['refresh_token']
        first = client.post(f'{PREFIX}/auth/refresh', json={'refresh_token': refresh_token})
        assert first.status_code == 200
        second = client.post(f'{PREFIX}/auth/refresh', json={'refresh_token': refresh_token})
        assert second.status_code == 401

    def test_refresh_missing_user_returns_401(self, client, db_session, app):
        import jwt as pyjwt
        from app.utils.mobile_jwt import (
            _jwt_secret, MOBILE_TOKEN_AUDIENCE, MOBILE_TOKEN_ISSUER, MOBILE_TOKEN_ALGORITHM,
        )
        payload = {
            'sub': '999999', 'type': 'refresh', 'sid': 'orphan-sid', 'jti': 'jti-orphan',
            'iat': 1, 'exp': 9999999999,
            'aud': MOBILE_TOKEN_AUDIENCE, 'iss': MOBILE_TOKEN_ISSUER, 'ver': 1,
        }
        with app.app_context():
            token = pyjwt.encode(payload, _jwt_secret(), algorithm=MOBILE_TOKEN_ALGORITHM)
        resp = client.post(f'{PREFIX}/auth/refresh', json={'refresh_token': token})
        assert resp.status_code == 401


@pytest.mark.api
@pytest.mark.integration
class TestMobileLogoutExtended:
    def test_logout_with_expired_access_token(self, client, mobile_user, db_session, app):
        from tests.api.mobile.conftest import _make_jwt_headers
        headers = _make_jwt_headers(app, mobile_user)
        expired_headers = dict(headers)
        import jwt as pyjwt
        from app.utils.mobile_jwt import (
            _jwt_secret, MOBILE_TOKEN_AUDIENCE, MOBILE_TOKEN_ISSUER, MOBILE_TOKEN_ALGORITHM,
        )
        payload = {
            'sub': str(mobile_user.id), 'type': 'access', 'sid': 'logout-expired-sid',
            'iat': 0, 'exp': 1,
            'aud': MOBILE_TOKEN_AUDIENCE, 'iss': MOBILE_TOKEN_ISSUER, 'ver': 1,
        }
        with app.app_context():
            expired_headers['Authorization'] = f'Bearer {pyjwt.encode(payload, _jwt_secret(), algorithm=MOBILE_TOKEN_ALGORITHM)}'
        resp = client.post(f'{PREFIX}/auth/logout', headers=expired_headers)
        assert resp.status_code == 200


@pytest.mark.api
@pytest.mark.integration
class TestMobileProfileExtended:
    def test_update_profile_all_fields(self, client, jwt_headers, db_session):
        resp = client.put(f'{PREFIX}/auth/profile', headers=jwt_headers, json={
            'name': 'Full Name',
            'title': 'Lead',
            'chatbot_enabled': True,
            'profile_color': '#EF4444',
        })
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True

    def test_update_profile_server_error(self, client, jwt_headers, db_session, app):
        with patch('app.routes.api.mobile.auth.db.session.flush', side_effect=RuntimeError('db')):
            resp = client.put(f'{PREFIX}/auth/profile', headers=jwt_headers, json={'name': 'X'})
        assert resp.status_code == 500


@pytest.mark.api
@pytest.mark.integration
class TestMobileAuthRoutesExtended:
    def test_issue_tokens_user_not_found(self, client, db_session):
        resp = client.post(f'{PREFIX}/auth/token', json={
            'email': 'nobody@example.com', 'password': 'SomePass123!',
        })
        assert resp.status_code == 401

    def test_issue_tokens_empty_credentials(self, client, db_session):
        resp = client.post(f'{PREFIX}/auth/token', json={'email': '', 'password': ''})
        assert resp.status_code == 400

    def test_refresh_blacklisted_session(self, client, mobile_user, db_session, app):
        login_resp = client.post(f'{PREFIX}/auth/token', json={
            'email': 'mobile@test.com', 'password': 'MobilePass123!',
        })
        refresh_token = login_resp.get_json()['data']['refresh_token']
        with patch('app.services.user_analytics_service.is_session_blacklisted', return_value=True):
            resp = client.post(f'{PREFIX}/auth/refresh', json={'refresh_token': refresh_token})
        assert resp.status_code == 401

    def test_refresh_inactive_session_resumes(self, client, mobile_user, db_session, app):
        login_resp = client.post(f'{PREFIX}/auth/token', json={
            'email': 'mobile@test.com', 'password': 'MobilePass123!',
        })
        refresh_token = login_resp.get_json()['data']['refresh_token']
        from app.utils.mobile_jwt import decode_mobile_token
        with app.app_context():
            claims = decode_mobile_token(refresh_token, expected_type='refresh')
            from app.models.core import UserSessionLog
            sess = UserSessionLog.query.filter_by(session_id=claims.sid).first()
            if sess:
                sess.is_active = False
                db_session.commit()
        resp = client.post(f'{PREFIX}/auth/refresh', json={'refresh_token': refresh_token})
        assert resp.status_code == 200

    def test_change_password_server_error(self, client, jwt_headers, db_session, app):
        with patch('app.routes.api.mobile.auth.db.session.flush', side_effect=RuntimeError('db')):
            resp = client.post(f'{PREFIX}/auth/change-password', headers=jwt_headers, json={
                'current_password': 'MobilePass123!',
                'new_password': 'XwQ9#mP2vL8!zR',
            })
        assert resp.status_code == 500

    def test_logout_without_bearer_still_succeeds(self, client, db_session):
        resp = client.post(f'{PREFIX}/auth/logout')
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_logout_blacklist_failure_still_succeeds(self, client, jwt_headers, db_session, app):
        with patch('app.services.user_analytics_service.add_session_to_blacklist', side_effect=RuntimeError('redis down')):
            resp = client.post(f'{PREFIX}/auth/logout', headers=jwt_headers)
        assert resp.status_code == 200

    def test_profile_includes_rbac_roles(self, client, jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/auth/profile', headers=jwt_headers)
        body = resp.get_json()
        user = body['data']['user']
        assert 'rbac_roles' in user
        assert 'role' in user
