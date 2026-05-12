"""Integration tests for /api/mobile/v1/admin/users/* endpoints."""
import pytest
from tests.api.mobile.helpers import assert_mobile_ok, assert_mobile_paginated, assert_mobile_error

PREFIX = '/api/mobile/v1'


@pytest.mark.api
@pytest.mark.integration
class TestAdminUserRoutes:
    def test_list_requires_permission(self, client, jwt_headers, db_session):
        """Regular user cannot list users."""
        resp = client.get(f'{PREFIX}/admin/users', headers=jwt_headers)
        assert resp.status_code == 403

    def test_list_users(self, client, admin_jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/users', headers=admin_jwt_headers)
        assert_mobile_paginated(resp)

    def test_list_users_search(self, client, admin_jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/users?search=admin', headers=admin_jwt_headers)
        assert resp.status_code == 200

    def test_get_user_detail(self, client, admin_jwt_headers, admin_mobile_user, db_session):
        resp = client.get(f'{PREFIX}/admin/users/{admin_mobile_user.id}', headers=admin_jwt_headers)
        assert_mobile_ok(resp, has_data=True)
        assert 'user' in resp.get_json()['data']

    def test_get_user_not_found(self, client, admin_jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/users/999999', headers=admin_jwt_headers)
        assert resp.status_code == 404

    def test_update_user(self, client, sm_jwt_headers, mobile_user, db_session):
        resp = client.put(
            f'{PREFIX}/admin/users/{mobile_user.id}',
            headers=sm_jwt_headers,
            json={'name': 'New Name'},
        )
        assert_mobile_ok(resp, has_message=True)

    def test_activate_user(self, client, sm_jwt_headers, mobile_user, db_session, app):
        with app.app_context():
            from app import db as _db
            mobile_user.active = False
            _db.session.flush()

        resp = client.post(
            f'{PREFIX}/admin/users/{mobile_user.id}/activate',
            headers=sm_jwt_headers,
        )
        assert_mobile_ok(resp, has_message=True)

    def test_deactivate_self_rejected(self, client, sm_jwt_headers, sm_mobile_user, db_session):
        resp = client.post(
            f'{PREFIX}/admin/users/{sm_mobile_user.id}/deactivate',
            headers=sm_jwt_headers,
        )
        assert resp.status_code == 400

    def test_rbac_roles_list(self, client, admin_jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/users/rbac-roles', headers=admin_jwt_headers)
        assert_mobile_ok(resp, has_data=True)
        assert 'roles' in resp.get_json()['data']
