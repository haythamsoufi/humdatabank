"""Direct unit tests for app/routes/api/mobile/analytics.py."""
import time
import json
import pytest
from unittest.mock import patch, MagicMock
from flask_login import login_user

from tests.factories import create_test_user

pytestmark = [pytest.mark.unit]


def _jwt_headers(app, user_id, sid=None):
    from app.utils.mobile_jwt import issue_token_pair
    with app.app_context():
        tokens = issue_token_pair(user_id, session_id=sid or f'analytics-sid-{user_id}')
    return {'Authorization': f'Bearer {tokens["access_token"]}'}


def _unpack(resp):
    if isinstance(resp, tuple):
        return resp[0], resp[1]
    return resp, 200


class TestIsDuplicate:
    def test_no_entry_returns_false(self, app):
        from app.routes.api.mobile.analytics import _is_duplicate, _recent_screen_views
        _recent_screen_views.clear()
        assert _is_duplicate(9999, 'HomeScreen', '/home') is False

    def test_different_screen_returns_false(self, app):
        from app.routes.api.mobile.analytics import _is_duplicate, _recent_screen_views
        _recent_screen_views[8888] = ('HomeScreen', '/home', time.time())
        assert _is_duplicate(8888, 'SettingsScreen', '/settings') is False

    def test_different_route_returns_false(self, app):
        from app.routes.api.mobile.analytics import _is_duplicate, _recent_screen_views
        _recent_screen_views[7777] = ('HomeScreen', '/home', time.time())
        assert _is_duplicate(7777, 'HomeScreen', '/other') is False

    def test_within_window_returns_true(self, app):
        from app.routes.api.mobile.analytics import _is_duplicate, _recent_screen_views
        _recent_screen_views[6666] = ('HomeScreen', '/home', time.time())
        assert _is_duplicate(6666, 'HomeScreen', '/home') is True

    def test_outside_window_returns_false(self, app):
        from app.routes.api.mobile.analytics import _is_duplicate, _recent_screen_views, _DEDUP_WINDOW_SECONDS
        _recent_screen_views[5555] = ('HomeScreen', '/home', time.time() - _DEDUP_WINDOW_SECONDS - 1)
        assert _is_duplicate(5555, 'HomeScreen', '/home') is False


class TestScreenView:
    def test_missing_screen_name_returns_400(self, app, db_session):
        from app.routes.api.mobile.analytics import screen_view

        user = create_test_user(db_session, email='analytics-user1@example.com')
        headers = _jwt_headers(app, user.id)

        with app.test_request_context(
            '/api/mobile/v1/analytics/screen-view',
            method='POST',
            data=json.dumps({}),
            content_type='application/json',
            headers=headers,
        ):
            login_user(user)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.utils.rate_limiting.mobile_rate_limit', side_effect=lambda **kw: lambda f: f):
                resp = screen_view()

        _, status = _unpack(resp)
        assert status == 400

    def test_empty_screen_name_returns_400(self, app, db_session):
        from app.routes.api.mobile.analytics import screen_view

        user = create_test_user(db_session, email='analytics-user2@example.com')
        headers = _jwt_headers(app, user.id)

        with app.test_request_context(
            '/api/mobile/v1/analytics/screen-view',
            method='POST',
            data=json.dumps({'screen_name': '   '}),
            content_type='application/json',
            headers=headers,
        ):
            login_user(user)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.utils.rate_limiting.mobile_rate_limit', side_effect=lambda **kw: lambda f: f):
                resp = screen_view()

        _, status = _unpack(resp)
        assert status == 400

    def test_duplicate_screen_view_returns_200_early(self, app, db_session):
        from app.routes.api.mobile.analytics import screen_view, _recent_screen_views

        user = create_test_user(db_session, email='analytics-user3@example.com')
        # Pre-populate cache so it looks like a duplicate
        _recent_screen_views[user.id] = ('HomeScreen', '/home', time.time())
        headers = _jwt_headers(app, user.id)

        with app.test_request_context(
            '/api/mobile/v1/analytics/screen-view',
            method='POST',
            data=json.dumps({'screen_name': 'HomeScreen', 'route_path': '/home'}),
            content_type='application/json',
            headers=headers,
        ):
            login_user(user)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.utils.rate_limiting.mobile_rate_limit', side_effect=lambda **kw: lambda f: f):
                resp = screen_view()

        _, status = _unpack(resp)
        assert status == 200

    def test_screen_view_with_jwt_sid_in_g(self, app, db_session):
        from app.routes.api.mobile.analytics import screen_view, _recent_screen_views
        from flask import g

        user = create_test_user(db_session, email='analytics-user4@example.com')
        _recent_screen_views.pop(user.id, None)
        headers = _jwt_headers(app, user.id)

        with app.test_request_context(
            '/api/mobile/v1/analytics/screen-view',
            method='POST',
            data=json.dumps({'screen_name': 'DashScreen', 'route_path': '/dash'}),
            content_type='application/json',
            headers=headers,
        ):
            login_user(user)
            g._mobile_jwt_sid = 'analytics-explicit-sid'
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.utils.rate_limiting.mobile_rate_limit', side_effect=lambda **kw: lambda f: f), \
                 patch(
                     'app.services.user_analytics_service'
                     '.increment_session_page_views_without_activity_log_deferred'
                 ) as mock_incr:
                resp = screen_view()

        _, status = _unpack(resp)
        assert status == 200
        mock_incr.assert_called_once()

    def test_screen_view_fallback_to_active_session_row(self, app, db_session):
        """When g._mobile_jwt_sid is absent, the route should query UserSessionLog."""
        from app.models.core import UserSessionLog
        from app.routes.api.mobile.analytics import screen_view, _recent_screen_views

        user = create_test_user(db_session, email='analytics-user5@example.com')
        _recent_screen_views.pop(user.id, None)

        # Create an active session row
        sid = 'fallback-session-sid'
        row = UserSessionLog(
            user_id=user.id,
            session_id=sid,
            ip_address='127.0.0.1',
            is_active=True,
        )
        db_session.add(row)
        db_session.commit()

        headers = _jwt_headers(app, user.id)
        with app.test_request_context(
            '/api/mobile/v1/analytics/screen-view',
            method='POST',
            data=json.dumps({'screen_name': 'ProfileScreen'}),
            content_type='application/json',
            headers=headers,
        ):
            login_user(user)
            # Do NOT set g._mobile_jwt_sid so the fallback runs
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.utils.rate_limiting.mobile_rate_limit', side_effect=lambda **kw: lambda f: f), \
                 patch(
                     'app.services.user_analytics_service'
                     '.increment_session_page_views_without_activity_log_deferred'
                 ) as mock_incr:
                resp = screen_view()

        _, status = _unpack(resp)
        assert status == 200

    def test_screen_view_no_active_session_row(self, app, db_session):
        """When no active session row exists, the route should still return 200."""
        from app.routes.api.mobile.analytics import screen_view, _recent_screen_views

        user = create_test_user(db_session, email='analytics-user6@example.com')
        _recent_screen_views.pop(user.id, None)

        headers = _jwt_headers(app, user.id)
        with app.test_request_context(
            '/api/mobile/v1/analytics/screen-view',
            method='POST',
            data=json.dumps({'screen_name': 'MapScreen'}),
            content_type='application/json',
            headers=headers,
        ):
            login_user(user)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.utils.rate_limiting.mobile_rate_limit', side_effect=lambda **kw: lambda f: f), \
                 patch(
                     'app.services.user_analytics_service'
                     '.increment_session_page_views_without_activity_log_deferred'
                 ):
                resp = screen_view()

        _, status = _unpack(resp)
        assert status == 200

    def test_screen_view_logging_exception_does_not_break_response(self, app, db_session):
        """An exception during the analytics increment should not return 500."""
        from app.routes.api.mobile.analytics import screen_view, _recent_screen_views
        from flask import g

        user = create_test_user(db_session, email='analytics-user7@example.com')
        _recent_screen_views.pop(user.id, None)
        headers = _jwt_headers(app, user.id)

        with app.test_request_context(
            '/api/mobile/v1/analytics/screen-view',
            method='POST',
            data=json.dumps({'screen_name': 'ErrorScreen', 'route_path': '/err'}),
            content_type='application/json',
            headers=headers,
        ):
            login_user(user)
            g._mobile_jwt_sid = 'err-sid'
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.utils.rate_limiting.mobile_rate_limit', side_effect=lambda **kw: lambda f: f), \
                 patch(
                     'app.services.user_analytics_service'
                     '.increment_session_page_views_without_activity_log_deferred',
                     side_effect=RuntimeError('crash'),
                 ):
                resp = screen_view()

        _, status = _unpack(resp)
        assert status == 200

    def test_screen_view_no_auth_returns_401(self, app):
        client = app.test_client()
        resp = client.post(
            '/api/mobile/v1/analytics/screen-view',
            json={'screen_name': 'HomeScreen'},
        )
        assert resp.status_code == 401
