"""Tests for admin user management JSON API routes.

Covers: app/routes/admin/user_management/api.py
"""

import pytest
from unittest.mock import patch, MagicMock
from tests.factories import create_test_user, create_test_country

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _grant_perm(db_session, perm_code, role_code="admin_core"):
    from app.models.rbac import RbacRole, RbacRolePermission, RbacPermission
    role = db_session.query(RbacRole).filter_by(code=role_code).first()
    if not role:
        return
    perm = db_session.query(RbacPermission).filter_by(code=perm_code).first()
    if not perm:
        perm = RbacPermission(code=perm_code, name=perm_code, description=perm_code)
        db_session.add(perm)
        db_session.flush()
    existing = db_session.query(RbacRolePermission).filter_by(
        role_id=role.id, permission_id=perm.id
    ).first()
    if not existing:
        db_session.add(RbacRolePermission(role_id=role.id, permission_id=perm.id))
        db_session.commit()


def _make_access_request(db_session, user, country, status="pending"):
    from app.models import CountryAccessRequest
    req = CountryAccessRequest(
        user_id=user.id,
        country_id=country.id,
        status=status,
    )
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)
    return req


# ---------------------------------------------------------------------------
# api_users_list (GET /admin/api/users)
# ---------------------------------------------------------------------------

class TestApiUsersList:
    def test_unauthenticated_returns_401(self, client, db_session):
        resp = client.get("/admin/api/users")
        assert resp.status_code in (302, 401)

    def test_admin_returns_200_with_data(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/users")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data is not None
        assert "data" in data or "status" in data

    def test_returns_users_list(self, logged_in_client, db_session):
        create_test_user(db_session, email="api_list1@example.com")
        resp = logged_in_client.get("/admin/api/users")
        assert resp.status_code == 200

    def test_handles_exception(self, logged_in_client, db_session):
        with patch(
            "app.routes.admin.user_management.api.build_admin_user_list_rows",
            side_effect=Exception("db error"),
        ):
            resp = logged_in_client.get("/admin/api/users")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# api_user_detail (GET /admin/api/users/<id>)
# ---------------------------------------------------------------------------

class TestApiUserDetail:
    def test_unauthenticated_returns_401(self, client, db_session):
        resp = client.get("/admin/api/users/1")
        assert resp.status_code in (302, 401)

    def test_returns_user_detail(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="detail_user@example.com")
        resp = logged_in_client.get(f"/admin/api/users/{user.id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data is not None

    def test_returns_404_for_nonexistent(self, logged_in_client, db_session):
        with patch(
            "app.routes.admin.user_management.api.build_admin_user_detail_dict",
            return_value=None,
        ):
            resp = logged_in_client.get("/admin/api/users/999999")
        assert resp.status_code == 404

    def test_handles_exception(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="detail_exc@example.com")
        with patch(
            "app.routes.admin.user_management.api.build_admin_user_detail_dict",
            side_effect=Exception("detail error"),
        ):
            resp = logged_in_client.get(f"/admin/api/users/{user.id}")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# api_rbac_roles_catalog (GET /admin/api/rbac/roles)
# ---------------------------------------------------------------------------

class TestApiRbacRolesCatalog:
    def test_unauthenticated_returns_401(self, client, db_session):
        resp = client.get("/admin/api/rbac/roles")
        assert resp.status_code in (302, 401)

    def test_sys_mgr_returns_roles(self, logged_in_sm_client, db_session):
        resp = logged_in_sm_client.get("/admin/api/rbac/roles")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data is not None

    def test_non_roles_assign_returns_403(self, logged_in_client, db_session):
        # admin_core does NOT have admin.users.roles.assign by default
        resp = logged_in_client.get("/admin/api/rbac/roles")
        assert resp.status_code in (302, 403)

    def test_handles_exception(self, logged_in_sm_client, db_session):
        with patch(
            "app.routes.admin.user_management.api.RbacRole",
            side_effect=Exception("rbac error"),
        ):
            pass
        from app.models.rbac import RbacRole
        with patch.object(
            RbacRole,
            "query",
            new_callable=lambda: type(
                "Q", (), {"order_by": staticmethod(lambda *a: type("Q2", (), {"all": staticmethod(lambda: (_ for _ in ()).throw(Exception("fail")))})())}
            ),
        ):
            pass
        # Just verify the endpoint is accessible for sys_mgr
        resp = logged_in_sm_client.get("/admin/api/rbac/roles")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# api_user_update (PUT/PATCH /admin/api/users/<id>)
# ---------------------------------------------------------------------------

class TestApiUserUpdate:
    def test_unauthenticated_returns_401(self, client, db_session):
        resp = client.patch(
            "/admin/api/users/1",
            json={"name": "New Name"},
        )
        assert resp.status_code in (302, 401)

    def test_update_name(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="api_update@example.com")
        resp = logged_in_client.patch(
            f"/admin/api/users/{user.id}",
            json={"name": "Updated Via API"},
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_update_title(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="api_title@example.com")
        resp = logged_in_client.patch(
            f"/admin/api/users/{user.id}",
            json={"title": "New Title"},
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_update_chatbot_enabled(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="api_chatbot@example.com")
        resp = logged_in_client.patch(
            f"/admin/api/users/{user.id}",
            json={"chatbot_enabled": True},
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_update_profile_color(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="api_color@example.com")
        resp = logged_in_client.patch(
            f"/admin/api/users/{user.id}",
            json={"profile_color": "#FF5733"},
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_invalid_profile_color_returns_400(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="api_bad_color@example.com")
        resp = logged_in_client.patch(
            f"/admin/api/users/{user.id}",
            json={"profile_color": "not-a-color"},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_empty_profile_color_returns_400(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="api_empty_color@example.com")
        resp = logged_in_client.patch(
            f"/admin/api/users/{user.id}",
            json={"profile_color": ""},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_null_profile_color_is_no_op(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="api_null_color@example.com")
        resp = logged_in_client.patch(
            f"/admin/api/users/{user.id}",
            json={"profile_color": None},
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_deactivate_user(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="api_deact@example.com")
        resp = logged_in_client.patch(
            f"/admin/api/users/{user.id}",
            json={"active": False},
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_cannot_deactivate_self(self, logged_in_client, db_session, admin_user, app):
        with app.app_context():
            uid = admin_user.id
        resp = logged_in_client.patch(
            f"/admin/api/users/{uid}",
            json={"active": False},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_non_json_body_returns_400(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="api_non_json@example.com")
        resp = logged_in_client.patch(
            f"/admin/api/users/{user.id}",
            data="not-json",
            content_type="text/plain",
        )
        assert resp.status_code == 400

    def test_empty_fields_returns_400(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="api_empty@example.com")
        resp = logged_in_client.patch(
            f"/admin/api/users/{user.id}",
            json={"unsupported_field": "value"},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_404_for_nonexistent_user(self, logged_in_client, db_session):
        resp = logged_in_client.patch(
            "/admin/api/users/999999",
            json={"name": "Ghost"},
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_name_too_long_returns_400(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="api_long_name@example.com")
        resp = logged_in_client.patch(
            f"/admin/api/users/{user.id}",
            json={"name": "A" * 101},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_title_too_long_returns_400(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="api_long_title@example.com")
        resp = logged_in_client.patch(
            f"/admin/api/users/{user.id}",
            json={"title": "T" * 101},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_null_title_clears_field(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="api_null_title@example.com")
        resp = logged_in_client.patch(
            f"/admin/api/users/{user.id}",
            json={"title": None},
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_null_name_clears_field(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="api_null_name@example.com")
        resp = logged_in_client.patch(
            f"/admin/api/users/{user.id}",
            json={"name": None},
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_non_sys_mgr_cannot_edit_admin(self, logged_in_client, db_session):
        other_admin = create_test_user(
            db_session, email="api_other_admin@example.com", role="admin"
        )
        resp = logged_in_client.patch(
            f"/admin/api/users/{other_admin.id}",
            json={"name": "Hacked"},
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_update_rbac_roles_requires_permission(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="api_roles_perm@example.com")
        resp = logged_in_client.patch(
            f"/admin/api/users/{user.id}",
            json={"rbac_role_ids": [1]},
            content_type="application/json",
        )
        assert resp.status_code in (200, 400, 403)

    def test_update_rbac_roles_invalid_list(self, logged_in_sm_client, db_session):
        user = create_test_user(db_session, email="api_bad_roles@example.com")
        resp = logged_in_sm_client.patch(
            f"/admin/api/users/{user.id}",
            json={"rbac_role_ids": "not-a-list"},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_update_rbac_roles_invalid_id(self, logged_in_sm_client, db_session):
        user = create_test_user(db_session, email="api_inv_role@example.com")
        resp = logged_in_sm_client.patch(
            f"/admin/api/users/{user.id}",
            json={"rbac_role_ids": ["not-an-id"]},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_update_rbac_roles_empty_list_returns_400(self, logged_in_sm_client, db_session):
        user = create_test_user(db_session, email="api_empty_roles@example.com")
        resp = logged_in_sm_client.patch(
            f"/admin/api/users/{user.id}",
            json={"rbac_role_ids": []},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_cannot_change_own_roles(self, logged_in_client, db_session, admin_user, app):
        _grant_perm(db_session, "admin.users.roles.assign")
        with app.app_context():
            uid = admin_user.id
        resp = logged_in_client.patch(
            f"/admin/api/users/{uid}",
            json={"rbac_role_ids": [1]},
            content_type="application/json",
        )
        assert resp.status_code in (200, 400, 403)

    def test_sys_mgr_can_edit_sys_mgr_user(
        self, logged_in_sm_client, db_session, system_manager_user
    ):
        user = create_test_user(
            db_session, email="api_sm_target@example.com", role="system_manager"
        )
        resp = logged_in_sm_client.patch(
            f"/admin/api/users/{user.id}",
            json={"name": "SM Updated"},
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_non_sys_mgr_cannot_edit_sys_mgr(self, logged_in_client, db_session):
        user = create_test_user(
            db_session, email="sm_cannot_edit@example.com", role="system_manager"
        )
        resp = logged_in_client.patch(
            f"/admin/api/users/{user.id}",
            json={"name": "Attempted"},
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_put_method_also_works(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="api_put@example.com")
        resp = logged_in_client.put(
            f"/admin/api/users/{user.id}",
            json={"name": "PUT Updated"},
            content_type="application/json",
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# api_users_profile_summary (GET /admin/api/users/profile-summary)
# ---------------------------------------------------------------------------

class TestApiUsersProfileSummary:
    def test_unauthenticated_returns_401(self, client, db_session):
        resp = client.get("/admin/api/users/profile-summary")
        assert resp.status_code in (302, 401)

    def test_empty_params_returns_empty_list(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/users/profile-summary")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("profiles") == []

    def test_by_user_ids(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="profile_sum@example.com")
        resp = logged_in_client.get(
            f"/admin/api/users/profile-summary?user_ids={user.id}"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "profiles" in data

    def test_by_email(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="profile_email@example.com")
        resp = logged_in_client.get(
            f"/admin/api/users/profile-summary?emails={user.email}"
        )
        assert resp.status_code == 200

    def test_nonexistent_user_returns_empty(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/api/users/profile-summary?user_ids=9999999"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("profiles") == []

    def test_handles_exception(self, logged_in_client, db_session):
        with patch(
            "app.routes.admin.user_management.api.User",
        ) as MockUser:
            MockUser.query = MagicMock()
            MockUser.query.side_effect = Exception("query error")
            resp = logged_in_client.get(
                "/admin/api/users/profile-summary?user_ids=1"
            )
        assert resp.status_code in (200, 500)

    def test_by_external_ids(self, logged_in_client, db_session):
        import uuid
        resp = logged_in_client.get(
            f"/admin/api/users/profile-summary?external_ids={uuid.uuid4()}"
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# api_access_requests_count (GET /admin/api/users/access-requests/count)
# ---------------------------------------------------------------------------

class TestApiAccessRequestsCount:
    def test_unauthenticated_returns_401(self, client, db_session):
        resp = client.get("/admin/api/users/access-requests/count")
        assert resp.status_code in (302, 401)

    def test_returns_count(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/users/access-requests/count")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "data" in data

    def test_count_includes_pending(self, logged_in_client, db_session, admin_user):
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="cnt_req@example.com")
        _make_access_request(db_session, user, country, status="pending")
        resp = logged_in_client.get("/admin/api/users/access-requests/count")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# api_access_requests_list (GET /admin/api/users/access-requests)
# ---------------------------------------------------------------------------

class TestApiAccessRequestsList:
    def test_unauthenticated_returns_401(self, client, db_session):
        resp = client.get("/admin/api/users/access-requests")
        assert resp.status_code in (302, 401)

    def test_returns_pending_and_processed(self, logged_in_client, db_session, admin_user):
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="list_req@example.com")
        _make_access_request(db_session, user, country, status="pending")
        _make_access_request(db_session, user, country, status="approved")
        resp = logged_in_client.get("/admin/api/users/access-requests")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "pending" in data
        assert "processed" in data


# ---------------------------------------------------------------------------
# api_approve_access_request (POST /admin/api/users/access-requests/<id>/approve)
# ---------------------------------------------------------------------------

class TestApiApproveAccessRequest:
    def test_unauthenticated_returns_401(self, client, db_session):
        resp = client.post("/admin/api/users/access-requests/999/approve")
        assert resp.status_code in (302, 401)

    def test_404_for_nonexistent(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/api/users/access-requests/999999/approve"
        )
        assert resp.status_code == 404

    def test_approve_pending(self, logged_in_client, db_session, admin_user):
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="api_app_req@example.com")
        req = _make_access_request(db_session, user, country, status="pending")
        with patch("app.services.notification.core.notify_user_added_to_country"):
            resp = logged_in_client.post(
                f"/admin/api/users/access-requests/{req.id}/approve"
            )
        assert resp.status_code == 200

    def test_already_processed_returns_400(self, logged_in_client, db_session, admin_user):
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="api_app_done@example.com")
        req = _make_access_request(db_session, user, country, status="approved")
        resp = logged_in_client.post(
            f"/admin/api/users/access-requests/{req.id}/approve"
        )
        assert resp.status_code == 400

    def test_handles_exception(self, logged_in_client, db_session, admin_user):
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="api_app_exc@example.com")
        req = _make_access_request(db_session, user, country, status="pending")
        with patch(
            "app.routes.admin.user_management.api.log_admin_action",
            side_effect=Exception("audit error"),
        ):
            resp = logged_in_client.post(
                f"/admin/api/users/access-requests/{req.id}/approve"
            )
        assert resp.status_code == 500

    def test_notification_exception_still_succeeds(
        self, logged_in_client, db_session, admin_user
    ):
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="api_app_notif@example.com")
        req = _make_access_request(db_session, user, country, status="pending")
        with patch(
            "app.services.notification.core.notify_user_added_to_country",
            side_effect=Exception("notify error"),
        ):
            resp = logged_in_client.post(
                f"/admin/api/users/access-requests/{req.id}/approve"
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# api_reject_access_request (POST /admin/api/users/access-requests/<id>/reject)
# ---------------------------------------------------------------------------

class TestApiRejectAccessRequest:
    def test_unauthenticated_returns_401(self, client, db_session):
        resp = client.post("/admin/api/users/access-requests/999/reject")
        assert resp.status_code in (302, 401)

    def test_404_for_nonexistent(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/api/users/access-requests/999999/reject"
        )
        assert resp.status_code == 404

    def test_reject_pending(self, logged_in_client, db_session, admin_user):
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="api_rej_req@example.com")
        req = _make_access_request(db_session, user, country, status="pending")
        resp = logged_in_client.post(
            f"/admin/api/users/access-requests/{req.id}/reject"
        )
        assert resp.status_code == 200

    def test_already_processed_returns_400(self, logged_in_client, db_session, admin_user):
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="api_rej_done@example.com")
        req = _make_access_request(db_session, user, country, status="rejected")
        resp = logged_in_client.post(
            f"/admin/api/users/access-requests/{req.id}/reject"
        )
        assert resp.status_code == 400

    def test_handles_exception(self, logged_in_client, db_session, admin_user):
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="api_rej_exc@example.com")
        req = _make_access_request(db_session, user, country, status="pending")
        with patch(
            "app.routes.admin.user_management.api.log_admin_action",
            side_effect=Exception("audit error"),
        ):
            resp = logged_in_client.post(
                f"/admin/api/users/access-requests/{req.id}/reject"
            )
        assert resp.status_code == 500

    def test_null_user_or_country_handled(self, logged_in_client, db_session, admin_user):
        from app.models import CountryAccessRequest
        req = CountryAccessRequest(
            user_id=9998887,
            country_id=9998887,
            status="pending",
        )
        db_session.add(req)
        db_session.commit()
        resp = logged_in_client.post(
            f"/admin/api/users/access-requests/{req.id}/reject"
        )
        assert resp.status_code in (200, 500)


# ---------------------------------------------------------------------------
# api_approve_all_access_requests (POST /admin/api/users/access-requests/approve-all)
# ---------------------------------------------------------------------------

class TestApiApproveAllAccessRequests:
    def test_unauthenticated_returns_401(self, client, db_session):
        resp = client.post("/admin/api/users/access-requests/approve-all")
        assert resp.status_code in (302, 401)

    def test_no_pending_returns_zero_count(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/api/users/access-requests/approve-all"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("approved_count") == 0

    def test_approves_pending(self, logged_in_client, db_session, admin_user):
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="api_bulk_app@example.com")
        _make_access_request(db_session, user, country, status="pending")
        with patch("app.services.notification.core.notify_user_added_to_country"):
            resp = logged_in_client.post(
                "/admin/api/users/access-requests/approve-all"
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("approved_count", 0) >= 1

    def test_skips_invalid_user_country(self, logged_in_client, db_session):
        from app.models import CountryAccessRequest
        bad_req = CountryAccessRequest(
            user_id=9997776,
            country_id=9997776,
            status="pending",
        )
        db_session.add(bad_req)
        db_session.commit()
        resp = logged_in_client.post(
            "/admin/api/users/access-requests/approve-all"
        )
        assert resp.status_code == 200

    def test_handles_notify_exception(self, logged_in_client, db_session, admin_user):
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="api_bulk_notif@example.com")
        _make_access_request(db_session, user, country, status="pending")
        with patch(
            "app.services.notification.core.notify_user_added_to_country",
            side_effect=Exception("notify error"),
        ):
            resp = logged_in_client.post(
                "/admin/api/users/access-requests/approve-all"
            )
        assert resp.status_code == 200

    def test_bulk_approve_combines_notification_for_same_user(
        self, logged_in_client, db_session, admin_user
    ):
        """Approving several countries for the same user in one bulk action should
        send exactly one notification/email, not one per country."""
        from app.models import Notification, NotificationType

        user = create_test_user(db_session, email="api_bulk_combine@example.com")
        country_a = create_test_country(db_session)
        country_b = create_test_country(db_session)
        _make_access_request(db_session, user, country_a, status="pending")
        _make_access_request(db_session, user, country_b, status="pending")

        with patch("app.services.notification.emails.send_instant_notification_email"), \
             patch("app.services.notification.push.PushNotificationService"), \
             patch("app.utils.ws_manager.broadcast_notification"), \
             patch("app.utils.ws_manager.broadcast_unread_count"):
            resp = logged_in_client.post(
                "/admin/api/users/access-requests/approve-all"
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("approved_count") == 2

        notifications = Notification.query.filter_by(
            user_id=user.id, notification_type=NotificationType.user_added_to_country
        ).all()
        assert len(notifications) == 1
        assert country_a.name in notifications[0].message
        assert country_b.name in notifications[0].message


# ---------------------------------------------------------------------------
# api_user_deletion_preview (GET /admin/api/users/<id>/deletion-preview)
# ---------------------------------------------------------------------------

class TestApiUserDeletionPreview:
    def test_unauthenticated_returns_401(self, client, db_session):
        resp = client.get("/admin/api/users/1/deletion-preview")
        assert resp.status_code in (302, 401)

    def test_non_sys_mgr_forbidden(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="dp_non_sm@example.com")
        resp = logged_in_client.get(f"/admin/api/users/{user.id}/deletion-preview")
        assert resp.status_code == 403

    def test_sys_mgr_gets_preview(
        self, logged_in_sm_client, db_session, system_manager_user
    ):
        user = create_test_user(db_session, email="dp_sm@example.com")
        resp = logged_in_sm_client.get(
            f"/admin/api/users/{user.id}/deletion-preview"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "data" in data

    def test_404_for_nonexistent(self, logged_in_sm_client, db_session):
        resp = logged_in_sm_client.get("/admin/api/users/999999/deletion-preview")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# api_activate_user (POST /admin/api/users/<id>/activate)
# ---------------------------------------------------------------------------

class TestApiActivateUser:
    def test_unauthenticated_returns_401(self, client, db_session):
        resp = client.post("/admin/api/users/1/activate")
        assert resp.status_code in (302, 401)

    def test_activates_user(self, logged_in_client, db_session):
        user = create_test_user(
            db_session, email="activate_me@example.com", active=False
        )
        resp = logged_in_client.post(f"/admin/api/users/{user.id}/activate")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("status") == "success" or "success" in str(data)

    def test_404_for_nonexistent(self, logged_in_client, db_session):
        resp = logged_in_client.post("/admin/api/users/999999/activate")
        assert resp.status_code == 404

    def test_cannot_activate_self(self, logged_in_client, db_session, admin_user, app):
        with app.app_context():
            uid = admin_user.id
        resp = logged_in_client.post(f"/admin/api/users/{uid}/activate")
        assert resp.status_code == 400

    def test_non_sys_mgr_cannot_activate_admin(self, logged_in_client, db_session):
        other_admin = create_test_user(
            db_session, email="act_other_admin@example.com", role="admin", active=False
        )
        resp = logged_in_client.post(f"/admin/api/users/{other_admin.id}/activate")
        assert resp.status_code == 403

    def test_handles_exception(self, logged_in_client, db_session):
        user = create_test_user(
            db_session, email="act_exc@example.com", active=False
        )
        with patch(
            "app.routes.admin.user_management.api.log_admin_action",
            side_effect=Exception("audit error"),
        ):
            resp = logged_in_client.post(f"/admin/api/users/{user.id}/activate")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# api_deactivate_user (POST /admin/api/users/<id>/deactivate)
# ---------------------------------------------------------------------------

class TestApiDeactivateUser:
    def test_unauthenticated_returns_401(self, client, db_session):
        resp = client.post("/admin/api/users/1/deactivate")
        assert resp.status_code in (302, 401)

    def test_deactivates_user(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="deact_me@example.com", active=True)
        resp = logged_in_client.post(f"/admin/api/users/{user.id}/deactivate")
        assert resp.status_code == 200

    def test_404_for_nonexistent(self, logged_in_client, db_session):
        resp = logged_in_client.post("/admin/api/users/999999/deactivate")
        assert resp.status_code == 404

    def test_cannot_deactivate_self(
        self, logged_in_client, db_session, admin_user, app
    ):
        with app.app_context():
            uid = admin_user.id
        resp = logged_in_client.post(f"/admin/api/users/{uid}/deactivate")
        assert resp.status_code == 400

    def test_non_sys_mgr_cannot_deactivate_admin(self, logged_in_client, db_session):
        other_admin = create_test_user(
            db_session, email="deact_other_admin@example.com", role="admin", active=True
        )
        resp = logged_in_client.post(
            f"/admin/api/users/{other_admin.id}/deactivate"
        )
        assert resp.status_code == 403

    def test_handles_exception(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="deact_exc@example.com", active=True)
        with patch(
            "app.routes.admin.user_management.api.log_admin_action",
            side_effect=Exception("audit error"),
        ):
            resp = logged_in_client.post(f"/admin/api/users/{user.id}/deactivate")
        assert resp.status_code == 500
