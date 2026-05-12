"""Integration tests for /api/mobile/v1/admin/access-requests/* endpoints."""
import pytest
from tests.api.mobile.helpers import assert_mobile_ok

PREFIX = '/api/mobile/v1'


@pytest.mark.api
@pytest.mark.integration
class TestAccessRequestRoutes:
    def test_list_requires_permission(self, client, jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/access-requests', headers=jwt_headers)
        assert resp.status_code == 403

    def test_list_access_requests(self, client, admin_jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/access-requests', headers=admin_jwt_headers)
        assert_mobile_ok(resp, has_data=True)

    def test_approve_not_found(self, client, admin_jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/admin/access-requests/999999/approve',
                           headers=admin_jwt_headers)
        assert resp.status_code == 404

    def test_reject_not_found(self, client, admin_jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/admin/access-requests/999999/reject',
                           headers=admin_jwt_headers)
        assert resp.status_code == 404

    def test_approve_all_empty(self, client, admin_jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/admin/access-requests/approve-all',
                           headers=admin_jwt_headers)
        assert_mobile_ok(resp)
        assert resp.get_json().get('data', {}).get('approved_count', 0) == 0
