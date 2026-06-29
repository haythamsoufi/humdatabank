"""Unit tests for mobile_auth decorator and JWT helper."""
from unittest.mock import MagicMock, patch

import pytest
from flask import g
from flask_login import login_user

from app.utils.mobile_auth import _try_jwt_auth, mobile_auth_required

pytestmark = [pytest.mark.unit, pytest.mark.auth_security]


@pytest.mark.unit
class TestTryJwtAuth:
    def test_no_bearer_header(self, app):
        with app.test_request_context():
            assert _try_jwt_auth() is False

    def test_empty_bearer_token(self, app):
        with app.test_request_context(headers={'Authorization': 'Bearer '}):
            assert _try_jwt_auth() is False

    def test_invalid_jwt(self, app):
        with app.test_request_context(headers={'Authorization': 'Bearer bad-token'}):
            assert _try_jwt_auth() is False

    def test_valid_jwt(self, app, db_session):
        from tests.factories import create_test_user
        from tests.api.mobile.conftest import _make_jwt_headers
        with app.app_context():
            user = create_test_user(db_session, email='jwt-unit@test.com', password='Pass123!')
        headers = _make_jwt_headers(app, user)
        token = headers['Authorization'].split(' ', 1)[1]
        with app.test_request_context(headers={'Authorization': f'Bearer {token}'}):
            assert _try_jwt_auth() is True
            assert g._mobile_jwt_auth is True

    def test_blacklisted_session_rejected(self, app, db_session):
        from tests.factories import create_test_user
        from tests.api.mobile.conftest import _make_jwt_headers
        with app.app_context():
            user = create_test_user(db_session, email='jwt-blacklist@test.com', password='Pass123!')
        sid = 'blacklisted-sid-test'
        headers = _make_jwt_headers(app, user, session_id=sid)
        token = headers['Authorization'].split(' ', 1)[1]
        with app.test_request_context(headers={'Authorization': f'Bearer {token}'}):
            with patch('app.services.user_analytics_service.should_block_mobile_jwt_session', return_value=True):
                assert _try_jwt_auth() is False

    def test_inactive_user_rejected(self, app, db_session):
        from tests.factories import create_test_user
        from tests.api.mobile.conftest import _make_jwt_headers
        with app.app_context():
            user = create_test_user(db_session, email='inactive-jwt@test.com', active=False)
        headers = _make_jwt_headers(app, user)
        token = headers['Authorization'].split(' ', 1)[1]
        with app.test_request_context(headers={'Authorization': f'Bearer {token}'}):
            assert _try_jwt_auth() is False


@pytest.mark.unit
class TestMobileAuthRequiredDecorator:
    def test_metadata_without_permission(self, app):
        @mobile_auth_required
        def view():
            return {'ok': True}

        assert view._ep_auth == 'user'
        assert not hasattr(view, '_ep_permission')

    def test_metadata_with_permission(self, app):
        @mobile_auth_required(permission='admin.users.view')
        def view():
            return {'ok': True}

        assert view._ep_auth == 'rbac'
        assert view._ep_permission == 'admin.users.view'

    def test_bearer_invalid_returns_refresh_message(self, app):
        @mobile_auth_required
        def view():
            return {'ok': True}

        with app.test_request_context(
            method='POST',
            headers={'Authorization': 'Bearer expired-token'},
        ):
            result = view()
        if isinstance(result, tuple):
            response, status = result
        else:
            response, status = result, result.status_code
        assert status == 401
        body = response.get_json()
        assert 'refresh' in body.get('error', '').lower()

    def test_jwt_session_activity_tracked(self, app, db_session):
        @mobile_auth_required
        def view():
            return {'ok': True}

        from tests.factories import create_test_user
        from tests.api.mobile.conftest import _make_jwt_headers
        with app.app_context():
            user = create_test_user(db_session, email='jwt-track@test.com', password='Pass123!')
        headers = _make_jwt_headers(app, user)
        with app.test_request_context(headers=headers):
            with patch('app.services.user_analytics_service._update_session_activity_explicit') as mock_track:
                result = view()
            mock_track.assert_called_once()
        assert result == {'ok': True}

    def test_tracking_error_does_not_break_auth(self, app, db_session):
        @mobile_auth_required
        def view():
            return {'ok': True}

        from tests.factories import create_test_user
        from tests.api.mobile.conftest import _make_jwt_headers
        with app.app_context():
            user = create_test_user(db_session, email='jwt-track-err@test.com', password='Pass123!')
        headers = _make_jwt_headers(app, user)
        with app.test_request_context(headers=headers):
            with patch(
                'app.services.user_analytics_service._update_session_activity_explicit',
                side_effect=RuntimeError('tracking down'),
            ):
                result = view()
        assert result == {'ok': True}

    def test_unauthenticated_returns_auth_error(self, app):
        @mobile_auth_required
        def view():
            return {'ok': True}

        with app.test_request_context(method='GET'):
            result = view()
        if isinstance(result, tuple):
            response, status = result
        else:
            response, status = result, result.status_code
        assert status == 401

    def test_session_post_enforces_csrf_protection(self, app, db_session):
        @mobile_auth_required
        def view():
            return {'ok': True}

        from tests.factories import create_test_user
        from flask_login import login_user
        with app.app_context():
            user = create_test_user(db_session, email='csrf-mobile@test.com', password='Pass123!')
        with app.test_request_context(method='POST'):
            login_user(user)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection') as mock_csrf:
                result = view()
            mock_csrf.assert_called_once()
        assert result == {'ok': True}

    def test_permission_denied_returns_forbidden(self, app, db_session):
        @mobile_auth_required(permission='admin.users.edit')
        def view():
            return {'ok': True}

        from tests.factories import create_test_user
        from tests.api.mobile.conftest import _make_jwt_headers
        with app.app_context():
            user = create_test_user(db_session, email='perm-deny@test.com', password='Pass123!')
        headers = _make_jwt_headers(app, user)
        with app.test_request_context(method='GET', headers=headers):
            with patch('app.routes.admin.shared.user_has_permission', return_value=False):
                result = view()
        if isinstance(result, tuple):
            response, status = result
        else:
            response, status = result, result.status_code
        assert status == 403

    def test_jwt_without_sid_skips_activity_tracking(self, app, db_session):
        @mobile_auth_required
        def view():
            return {'ok': True}

        import jwt as pyjwt
        from tests.factories import create_test_user
        from app.utils.mobile_jwt import (
            _jwt_secret, MOBILE_TOKEN_AUDIENCE, MOBILE_TOKEN_ISSUER, MOBILE_TOKEN_ALGORITHM,
        )
        with app.app_context():
            user = create_test_user(db_session, email='no-sid@test.com', password='Pass123!')
            payload = {
                'sub': str(user.id), 'type': 'access',
                'iat': 1, 'exp': 9999999999,
                'aud': MOBILE_TOKEN_AUDIENCE, 'iss': MOBILE_TOKEN_ISSUER, 'ver': 1,
            }
            token = pyjwt.encode(payload, _jwt_secret(), algorithm=MOBILE_TOKEN_ALGORITHM)
        with app.test_request_context(headers={'Authorization': f'Bearer {token}'}):
            with patch('app.services.user_analytics_service._update_session_activity_explicit') as mock_track:
                result = view()
            mock_track.assert_not_called()
        assert result == {'ok': True}

    def test_track_session_activity_false_skips_activity_update(self, app, db_session):
        @mobile_auth_required(track_session_activity=False)
        def view():
            return {'ok': True}

        from tests.factories import create_test_user
        from tests.api.mobile.conftest import _make_jwt_headers
        with app.app_context():
            user = create_test_user(db_session, email='no-track@test.com', password='Pass123!')
        headers = _make_jwt_headers(app, user)
        with app.test_request_context(method='GET', headers=headers):
            with patch('app.services.user_analytics_service._update_session_activity_explicit') as mock_track:
                result = view()
            mock_track.assert_not_called()
        assert result == {'ok': True}

    def test_decorator_factory_without_immediate_wrap(self, app):
        decorator = mobile_auth_required(permission='admin.users.view')
        assert callable(decorator)

    def test_try_jwt_auth_user_not_found(self, app, db_session):
        import jwt as pyjwt
        from app.utils.mobile_jwt import (
            _jwt_secret, MOBILE_TOKEN_AUDIENCE, MOBILE_TOKEN_ISSUER, MOBILE_TOKEN_ALGORITHM,
        )
        payload = {
            'sub': '999999', 'type': 'access', 'sid': 'orphan',
            'iat': 1, 'exp': 9999999999,
            'aud': MOBILE_TOKEN_AUDIENCE, 'iss': MOBILE_TOKEN_ISSUER, 'ver': 1,
        }
        with app.app_context():
            token = pyjwt.encode(payload, _jwt_secret(), algorithm=MOBILE_TOKEN_ALGORITHM)
        with app.test_request_context(headers={'Authorization': f'Bearer {token}'}):
            assert _try_jwt_auth() is False

    def test_session_auth_get_success(self, app, db_session):
        @mobile_auth_required
        def view():
            return {'ok': True}

        from tests.factories import create_test_user
        with app.app_context():
            user = create_test_user(db_session, email='session-get@test.com', password='Pass123!')
        with app.test_request_context(method='GET'):
            login_user(user)
            result = view()
        assert result == {'ok': True}

    def test_permission_granted_calls_view(self, app, db_session):
        @mobile_auth_required(permission='admin.users.view')
        def view():
            return {'ok': True}

        from tests.factories import create_test_admin
        from tests.api.mobile.conftest import _make_jwt_headers
        with app.app_context():
            admin = create_test_admin(db_session, email='perm-ok@test.com', password='Pass123!')
        headers = _make_jwt_headers(app, admin)
        with app.test_request_context(method='GET', headers=headers):
            with patch('app.routes.admin.shared.user_has_permission', return_value=True):
                result = view()
        assert result == {'ok': True}
