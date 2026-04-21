"""Integration tests for /api/mobile/v1/admin/analytics/* endpoints."""
import pytest
from unittest.mock import patch
from tests.api.mobile.helpers import assert_mobile_ok, assert_mobile_paginated

PREFIX = '/api/mobile/v1'


@pytest.mark.api
@pytest.mark.integration
class TestDashboardStats:
    def test_requires_permission(self, client, jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/analytics/dashboard-stats', headers=jwt_headers)
        assert resp.status_code == 403

    @patch('app.services.get_platform_stats')
    def test_returns_stats(self, mock_stats, client, admin_jwt_headers, db_session):
        mock_stats.return_value = {
            'total_users': 10, 'total_countries': 5,
            'total_templates': 3, 'total_indicators': 20,
        }
        resp = client.get(f'{PREFIX}/admin/analytics/dashboard-stats',
                          headers=admin_jwt_headers)
        assert_mobile_ok(resp, has_data=True)
        data = resp.get_json()['data']
        assert 'user_count' in data


@pytest.mark.api
@pytest.mark.integration
class TestDashboardActivity:
    def test_requires_permission(self, client, jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/analytics/dashboard-activity', headers=jwt_headers)
        assert resp.status_code == 403

    def test_returns_activity(self, client, admin_jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/analytics/dashboard-activity',
                          headers=admin_jwt_headers)
        assert_mobile_ok(resp, has_data=True)


@pytest.mark.api
@pytest.mark.integration
class TestLoginLogs:
    def test_requires_permission(self, client, jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/analytics/login-logs', headers=jwt_headers)
        assert resp.status_code == 403

    def test_returns_paginated(self, client, admin_jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/analytics/login-logs',
                          headers=admin_jwt_headers)
        assert_mobile_paginated(resp)


@pytest.mark.api
@pytest.mark.integration
class TestSessionLogs:
    def test_requires_permission(self, client, jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/analytics/session-logs', headers=jwt_headers)
        assert resp.status_code == 403

    def test_returns_paginated(self, client, admin_jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/analytics/session-logs',
                          headers=admin_jwt_headers)
        assert_mobile_paginated(resp)


@pytest.mark.api
@pytest.mark.integration
class TestEndSession:
    def test_not_found(self, client, admin_jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/admin/analytics/sessions/nonexistent/end',
                           headers=admin_jwt_headers)
        assert resp.status_code == 404


@pytest.mark.api
@pytest.mark.integration
class TestAuditTrail:
    def test_requires_permission(self, client, jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/analytics/audit-trail', headers=jwt_headers)
        assert resp.status_code == 403

    def test_returns_paginated(self, client, admin_jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/analytics/audit-trail',
                          headers=admin_jwt_headers)
        assert_mobile_paginated(resp)


@pytest.mark.api
@pytest.mark.integration
class TestSendNotification:
    def test_requires_permission(self, client, jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/admin/notifications/send', headers=jwt_headers, json={})
        assert resp.status_code == 403

    def test_missing_fields(self, client, admin_jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/admin/notifications/send',
                           headers=admin_jwt_headers, json={'title': 'Hi'})
        assert resp.status_code == 400
