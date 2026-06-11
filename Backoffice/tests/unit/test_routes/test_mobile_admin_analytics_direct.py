"""Direct unit tests for app.routes.api.mobile.admin_analytics view functions.

Pattern: uses `route_admin` fixture (defined in local conftest.py) which
calls create_test_admin(db_session) DIRECTLY from a fixture — same pattern
as the working admin_mobile_user fixture in tests/api/mobile/conftest.py.
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
# dashboard_stats
# ---------------------------------------------------------------------------

class TestDashboardStats:
    def test_success(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_analytics import dashboard_stats

        with app.test_request_context(
            '/api/mobile/v1/admin/analytics/dashboard-stats',
            method='GET',
        ):
            login_user(route_admin)
            with patch('app.routes.api.mobile.admin_analytics._has_table', return_value=False), \
                 patch('app.services.get_platform_stats', return_value={
                     'total_users': 5,
                     'total_countries': 3,
                     'total_templates': 2,
                     'total_indicators': 10,
                 }):
                resp = dashboard_stats()

        body, status = _parse(resp)
        assert status == 200
        data = body.get_json()['data']
        assert 'user_count' in data
        assert data['user_count'] == 5

    def test_with_table_present(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_analytics import dashboard_stats

        with app.test_request_context(
            '/api/mobile/v1/admin/analytics/dashboard-stats',
            method='GET',
        ):
            login_user(route_admin)
            with patch('app.routes.api.mobile.admin_analytics._has_table', return_value=True), \
                 patch('app.services.get_platform_stats', return_value={
                     'total_users': 10,
                 }):
                resp = dashboard_stats()

        _, status = _parse(resp)
        assert status == 200

    def test_server_error(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_analytics import dashboard_stats

        with app.test_request_context(
            '/api/mobile/v1/admin/analytics/dashboard-stats',
            method='GET',
        ):
            login_user(route_admin)
            with patch('app.services.get_platform_stats', side_effect=RuntimeError('fail')):
                resp = dashboard_stats()

        _, status = _parse(resp)
        assert status == 500


# ---------------------------------------------------------------------------
# dashboard_activity
# ---------------------------------------------------------------------------

class TestDashboardActivity:
    def test_success(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_analytics import dashboard_activity

        with app.test_request_context(
            '/api/mobile/v1/admin/analytics/dashboard-activity',
            method='GET',
        ):
            login_user(route_admin)
            with patch('app.routes.api.mobile.admin_analytics._has_table', return_value=False):
                resp = dashboard_activity()

        body, status = _parse(resp)
        assert status == 200
        data = body.get_json()['data']
        assert 'activity' in data

    def test_with_days_param(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_analytics import dashboard_activity

        with app.test_request_context(
            '/api/mobile/v1/admin/analytics/dashboard-activity?days=14',
            method='GET',
        ):
            login_user(route_admin)
            with patch('app.routes.api.mobile.admin_analytics._has_table', return_value=False):
                resp = dashboard_activity()

        _, status = _parse(resp)
        assert status == 200

    def test_error(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_analytics import dashboard_activity

        with app.test_request_context(
            '/api/mobile/v1/admin/analytics/dashboard-activity',
            method='GET',
        ):
            login_user(route_admin)
            with patch('app.routes.api.mobile.admin_analytics._has_table', side_effect=RuntimeError('fail')):
                resp = dashboard_activity()

        _, status = _parse(resp)
        assert status == 500


# ---------------------------------------------------------------------------
# login_logs
# ---------------------------------------------------------------------------

class TestLoginLogs:
    def test_success_no_table(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_analytics import login_logs

        with app.test_request_context(
            '/api/mobile/v1/admin/analytics/login-logs',
            method='GET',
        ):
            login_user(route_admin)
            with patch('app.routes.api.mobile.admin_analytics._has_table', return_value=False):
                resp = login_logs()

        body, status = _parse(resp)
        assert status == 200

    def test_with_filters(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_analytics import login_logs

        with app.test_request_context(
            '/api/mobile/v1/admin/analytics/login-logs?event_type=login_success&search=test&page=1&per_page=10',
            method='GET',
        ):
            login_user(route_admin)
            with patch('app.routes.api.mobile.admin_analytics._has_table', return_value=False):
                resp = login_logs()

        _, status = _parse(resp)
        assert status == 200

    def test_error(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_analytics import login_logs

        with app.test_request_context('/api/mobile/v1/admin/analytics/login-logs', method='GET'):
            login_user(route_admin)
            with patch('app.routes.api.mobile.admin_analytics._has_table', side_effect=RuntimeError('fail')):
                resp = login_logs()

        _, status = _parse(resp)
        assert status == 500


# ---------------------------------------------------------------------------
# session_logs
# ---------------------------------------------------------------------------

class TestSessionLogs:
    def test_success_no_table(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_analytics import session_logs

        with app.test_request_context(
            '/api/mobile/v1/admin/analytics/session-logs',
            method='GET',
        ):
            login_user(route_admin)
            with patch('app.routes.api.mobile.admin_analytics._has_table', return_value=False):
                resp = session_logs()

        body, status = _parse(resp)
        assert status == 200

    def test_with_filter_and_pagination(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_analytics import session_logs

        with app.test_request_context(
            '/api/mobile/v1/admin/analytics/session-logs?search=test&page=2&per_page=5',
            method='GET',
        ):
            login_user(route_admin)
            with patch('app.routes.api.mobile.admin_analytics._has_table', return_value=False):
                resp = session_logs()

        _, status = _parse(resp)
        assert status == 200

    def test_error(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_analytics import session_logs

        with app.test_request_context('/api/mobile/v1/admin/analytics/session-logs', method='GET'):
            login_user(route_admin)
            with patch('app.routes.api.mobile.admin_analytics._has_table', side_effect=RuntimeError('fail')):
                resp = session_logs()

        _, status = _parse(resp)
        assert status == 500


# ---------------------------------------------------------------------------
# end_session
# ---------------------------------------------------------------------------

class TestEndSession:
    def test_session_not_found(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_analytics import end_session

        with app.test_request_context(
            '/api/mobile/v1/admin/analytics/sessions/99999/end',
            method='POST',
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.routes.api.mobile.admin_analytics._has_table', return_value=False):
                resp = end_session(99999)

        _, status = _parse(resp)
        assert status == 404

    def test_error(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_analytics import end_session

        with app.test_request_context(
            '/api/mobile/v1/admin/analytics/sessions/1/end',
            method='POST',
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.routes.api.mobile.admin_analytics._has_table', side_effect=RuntimeError('fail')):
                resp = end_session(1)

        _, status = _parse(resp)
        assert status == 500


# ---------------------------------------------------------------------------
# audit_trail
# ---------------------------------------------------------------------------

class TestAuditTrail:
    def test_success_no_table(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_analytics import audit_trail

        with app.test_request_context(
            '/api/mobile/v1/admin/analytics/audit-trail',
            method='GET',
        ):
            login_user(route_admin)
            with patch('app.routes.api.mobile.admin_analytics._has_table', return_value=False):
                resp = audit_trail()

        body, status = _parse(resp)
        assert status == 200

    def test_with_all_filters(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_analytics import audit_trail

        with app.test_request_context(
            '/api/mobile/v1/admin/analytics/audit-trail'
            '?search=update&action_type=user_update&risk_level=low'
            '&date_from=2024-01-01&date_to=2024-12-31&page=1&per_page=10',
            method='GET',
        ):
            login_user(route_admin)
            with patch('app.routes.api.mobile.admin_analytics._has_table', return_value=False):
                resp = audit_trail()

        _, status = _parse(resp)
        assert status == 200

    def test_error(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_analytics import audit_trail

        with app.test_request_context('/api/mobile/v1/admin/analytics/audit-trail', method='GET'):
            login_user(route_admin)
            with patch('app.routes.api.mobile.admin_analytics._has_table', side_effect=RuntimeError('fail')):
                resp = audit_trail()

        _, status = _parse(resp)
        assert status == 500


# ---------------------------------------------------------------------------
# admin_send_notification
# ---------------------------------------------------------------------------

class TestAdminSendNotification:
    def test_missing_fields_returns_400(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_analytics import admin_send_notification

        with app.test_request_context(
            '/api/mobile/v1/admin/analytics/send-notification',
            method='POST',
            data=json.dumps({}),
            content_type='application/json',
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = admin_send_notification()

        _, status = _parse(resp)
        assert status == 400

    def test_empty_title_returns_400(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_analytics import admin_send_notification

        with app.test_request_context(
            '/api/mobile/v1/admin/analytics/send-notification',
            method='POST',
            data=json.dumps({'title': '', 'body': 'Test message'}),
            content_type='application/json',
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = admin_send_notification()

        _, status = _parse(resp)
        assert status == 400

    def test_empty_body_returns_400(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_analytics import admin_send_notification

        with app.test_request_context(
            '/api/mobile/v1/admin/analytics/send-notification',
            method='POST',
            data=json.dumps({'title': 'Test', 'body': ''}),
            content_type='application/json',
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = admin_send_notification()

        _, status = _parse(resp)
        assert status == 400

    def test_success_broadcast(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_analytics import admin_send_notification

        mock_push = MagicMock()
        mock_push.send_broadcast.return_value = {'sent': 5, 'failed': 0}

        with app.test_request_context(
            '/api/mobile/v1/admin/analytics/send-notification',
            method='POST',
            data=json.dumps({'title': 'Test Title', 'body': 'Test Body'}),
            content_type='application/json',
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.routes.api.mobile.admin_analytics.PushNotificationService',
                       return_value=mock_push):
                resp = admin_send_notification()

        _, status = _parse(resp)
        assert status == 200

    def test_target_user_not_found_returns_404(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_analytics import admin_send_notification

        with app.test_request_context(
            '/api/mobile/v1/admin/analytics/send-notification',
            method='POST',
            data=json.dumps({'title': 'Test Title', 'body': 'Test Body', 'user_id': 99999}),
            content_type='application/json',
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = admin_send_notification()

        _, status = _parse(resp)
        assert status == 404

    def test_target_user_success(self, app, db_session, route_admin, route_user):
        from app.routes.api.mobile.admin_analytics import admin_send_notification

        mock_push = MagicMock()
        mock_push.send_to_user.return_value = {'sent': 1, 'failed': 0}

        with app.test_request_context(
            '/api/mobile/v1/admin/analytics/send-notification',
            method='POST',
            data=json.dumps({'title': 'Test Title', 'body': 'Test Body', 'user_id': route_user.id}),
            content_type='application/json',
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.routes.api.mobile.admin_analytics.PushNotificationService',
                       return_value=mock_push):
                resp = admin_send_notification()

        _, status = _parse(resp)
        assert status == 200

    def test_push_service_error_returns_500(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_analytics import admin_send_notification

        mock_push = MagicMock()
        mock_push.send_broadcast.side_effect = RuntimeError('push failed')

        with app.test_request_context(
            '/api/mobile/v1/admin/analytics/send-notification',
            method='POST',
            data=json.dumps({'title': 'Test Title', 'body': 'Test Body'}),
            content_type='application/json',
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.routes.api.mobile.admin_analytics.PushNotificationService',
                       return_value=mock_push):
                resp = admin_send_notification()

        _, status = _parse(resp)
        assert status == 500
