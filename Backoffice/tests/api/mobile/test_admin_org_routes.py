"""Integration tests for /api/mobile/v1/admin/org/* endpoints."""
import pytest
from tests.api.mobile.helpers import assert_mobile_ok

PREFIX = '/api/mobile/v1'


@pytest.mark.api
@pytest.mark.integration
class TestOrgRoutes:
    def test_branches_requires_auth(self, client, db_session):
        resp = client.get(f'{PREFIX}/admin/org/branches/1')
        assert resp.status_code == 401

    def test_branches_returns_list(self, client, jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/org/branches/1', headers=jwt_headers)
        assert_mobile_ok(resp, has_data=True)
        assert 'branches' in resp.get_json()['data']

    def test_subbranches_returns_list(self, client, jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/org/subbranches/1', headers=jwt_headers)
        assert_mobile_ok(resp, has_data=True)
        assert 'subbranches' in resp.get_json()['data']

    def test_structure_requires_permission(self, client, jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/org/structure', headers=jwt_headers)
        assert resp.status_code == 403

    def test_structure_returns_tree(self, client, admin_jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/org/structure', headers=admin_jwt_headers)
        assert_mobile_ok(resp, has_data=True)
        assert 'structure' in resp.get_json()['data']
