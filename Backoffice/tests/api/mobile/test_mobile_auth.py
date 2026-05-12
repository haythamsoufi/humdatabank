"""Integration tests for the mobile_auth_required decorator."""
import pytest
from tests.api.mobile.helpers import assert_mobile_error

PREFIX = '/api/mobile/v1'


@pytest.mark.api
@pytest.mark.integration
class TestMobileAuthDecorator:
    """Tests hit a real protected endpoint (/auth/session) to exercise the decorator."""

    def test_valid_jwt_returns_200(self, client, jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/auth/session', headers=jwt_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True

    def test_no_auth_returns_401(self, client, db_session):
        resp = client.get(f'{PREFIX}/auth/session')
        assert_mobile_error(resp, 401, error_code='AUTH_REQUIRED')

    def test_expired_jwt_returns_401(self, client, expired_jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/auth/session', headers=expired_jwt_headers)
        assert_mobile_error(resp, 401, error_code='AUTH_REQUIRED')

    def test_invalid_bearer_returns_401(self, client, db_session):
        headers = {'Authorization': 'Bearer totally-invalid-token', 'Content-Type': 'application/json'}
        resp = client.get(f'{PREFIX}/auth/session', headers=headers)
        assert_mobile_error(resp, 401, error_code='AUTH_REQUIRED')

    def test_permission_denied_returns_403(self, client, jwt_headers, db_session):
        """Regular user hitting an admin-only endpoint gets 403."""
        resp = client.get(f'{PREFIX}/admin/users', headers=jwt_headers)
        assert_mobile_error(resp, 403, error_code='FORBIDDEN')

    def test_admin_permission_passes(self, client, admin_jwt_headers, db_session):
        """Admin user can access admin.users.view endpoints."""
        resp = client.get(f'{PREFIX}/admin/users', headers=admin_jwt_headers)
        assert resp.status_code == 200

    def test_session_cookie_fallback(self, client, mobile_user, db_session):
        """When no Bearer header, session cookie auth still works."""
        with client.session_transaction() as sess:
            sess['_user_id'] = str(mobile_user.id)
            sess['_fresh'] = True
        resp = client.get(f'{PREFIX}/auth/session')
        assert resp.status_code == 200
