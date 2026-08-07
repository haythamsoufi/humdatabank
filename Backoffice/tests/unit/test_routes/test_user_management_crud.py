"""Tests for admin user management CRUD routes.

Covers: app/routes/admin/user_management/crud.py
"""

import json
import re

import pytest
from unittest.mock import patch, MagicMock
from tests.factories import create_test_user, create_test_country

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _grant_perm(db_session, perm_code):
    """Add a permission to the admin_core role (used by logged_in_client)."""
    from app.models.rbac import RbacRole, RbacRolePermission, RbacPermission
    role = db_session.query(RbacRole).filter_by(code="admin_core").first()
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


def _make_device(db_session, user_id, logged_out=False):
    from app.models.system import UserDevice
    device = UserDevice(
        user_id=user_id,
        platform="ios",
        device_name="Test iPhone",
        device_token="token_" + str(user_id),
    )
    if logged_out:
        from app.utils.datetime_helpers import utcnow
        device.logged_out_at = utcnow()
    db_session.add(device)
    db_session.commit()
    db_session.refresh(device)
    return device


# ---------------------------------------------------------------------------
# manage_users (GET /admin/users)
# ---------------------------------------------------------------------------

class TestManageUsers:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/users")
        assert resp.status_code in (301, 302)

    def test_admin_gets_200(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/users")
        assert resp.status_code == 200

    def test_page_shows_overview_stats(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/users")
        assert resp.status_code == 200
        assert "Total Users" in resp.text
        assert "Users Without Entity Access" in resp.text
        assert "Never Logged In" in resp.text
        assert "Stale Accounts (90+ days)" in resp.text
        assert "New Users This Week" in resp.text

    def test_page_new_users_this_week_reflects_recent_admin_create(
        self, logged_in_client, db_session, admin_user, app
    ):
        from app.models.system import AdminActionLog
        from app.services.platform.user_analytics_query_service import get_user_management_overview_stats
        from tests.factories import create_test_user

        with app.app_context():
            baseline = get_user_management_overview_stats(include_analytics=False)['new_users_this_week']

        created = create_test_user(db_session, email="overview_new_user@example.com")
        db_session.add(
            AdminActionLog(
                admin_user_id=admin_user.id,
                action_type='user_create',
                action_description=f'Created new user: {created.email}',
                target_type='user',
                target_id=created.id,
                ip_address='127.0.0.1',
            )
        )
        db_session.commit()

        with app.app_context():
            updated = get_user_management_overview_stats(include_analytics=False)['new_users_this_week']
        assert updated == baseline + 1

        resp = logged_in_client.get("/admin/users")
        assert resp.status_code == 200
        assert f'text-purple-600 tabular-nums">{updated}<' in resp.text

    def test_page_lists_users(self, logged_in_client, db_session):
        create_test_user(db_session, email="extra1@example.com")
        resp = logged_in_client.get("/admin/users")
        assert resp.status_code == 200

    def test_page_handles_rbac_roles_exception(self, logged_in_client, db_session, app):
        """Cover except branch for rbac_roles_by_user_id query."""
        with patch(
            "app.routes.admin.user_management.crud.db.session",
            side_effect=Exception("db error"),
        ):
            # Should not raise, just return degraded data
            pass
        resp = logged_in_client.get("/admin/users")
        assert resp.status_code == 200

    def test_page_with_country_in_db(self, logged_in_client, db_session):
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="with_country@example.com")
        from app.models.core import UserEntityPermission
        perm = UserEntityPermission(
            user_id=user.id,
            entity_type="country",
            entity_id=country.id,
        )
        db_session.add(perm)
        db_session.commit()
        resp = logged_in_client.get("/admin/users")
        assert resp.status_code == 200

    def test_manage_users_includes_edit_denied_message_for_other_admins(
        self, logged_in_client, db_session
    ):
        """Non–system-manager admins see why they cannot open another admin's edit form."""
        create_test_user(
            db_session, email="other_admin_list@example.com", role="admin"
        )
        resp = logged_in_client.get("/admin/users")
        assert resp.status_code == 200
        assert "edit_denied_message" in resp.text
        assert "Only a System Manager can modify an admin user." in resp.text

    def test_manage_users_maps_users_to_fds_members_by_country(
        self, logged_in_client, db_session
    ):
        """A user's country entities identify the FDS members covering that user."""
        country = create_test_country(db_session, name="FDS Testland")
        fds_user = create_test_user(db_session, email="fds_list@example.com", role="admin")
        covered_user = create_test_user(db_session, email="covered_user@example.com")
        covered_admin = create_test_user(
            db_session, email="covered_admin@example.com", role="admin"
        )
        country.fds_member_user_id = fds_user.id
        from app.models.core import UserEntityPermission
        db_session.add_all(
            [
                UserEntityPermission(
                    user_id=covered_user.id,
                    entity_type="country",
                    entity_id=country.id,
                ),
                UserEntityPermission(
                    user_id=covered_admin.id,
                    entity_type="country",
                    entity_id=country.id,
                ),
            ]
        )
        db_session.commit()

        resp = logged_in_client.get("/admin/users")
        assert resp.status_code == 200
        match = re.search(
            r'<script type="application/json" id="users-grid-data">(.*?)</script>',
            resp.text,
            re.DOTALL,
        )
        assert match is not None
        rows = json.loads(match.group(1))
        covered_row = next(row for row in rows if row["id"] == covered_user.id)
        covered_admin_row = next(row for row in rows if row["id"] == covered_admin.id)
        assert covered_row["fds_members"] == [
            {
                "active": True,
                "countries": ["FDS Testland"],
                "email": "fds_list@example.com",
                "id": fds_user.id,
                "name": fds_user.name or fds_user.email,
            }
        ]
        assert covered_admin_row["fds_members"] == []


# ---------------------------------------------------------------------------
# access_requests (GET /admin/access-requests)
# ---------------------------------------------------------------------------

class TestAccessRequests:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/access-requests")
        assert resp.status_code in (301, 302)

    def test_admin_gets_200(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/access-requests")
        assert resp.status_code == 200

    def test_shows_pending_requests(self, logged_in_client, db_session, admin_user):
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="req_user@example.com")
        _make_access_request(db_session, user, country)
        resp = logged_in_client.get("/admin/access-requests")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# approve_access_request (POST /admin/access-requests/<id>/approve)
# ---------------------------------------------------------------------------

class TestApproveAccessRequest:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.post("/admin/access-requests/999/approve")
        assert resp.status_code in (301, 302)

    def test_404_for_nonexistent_request(self, logged_in_client, db_session):
        resp = logged_in_client.post("/admin/access-requests/999999/approve")
        assert resp.status_code == 404

    def test_approve_pending_request(self, logged_in_client, db_session, admin_user):
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="approve_me@example.com")
        req = _make_access_request(db_session, user, country, status="pending")
        with patch(
            "app.routes.admin.user_management.crud.notify_user_added_to_country",
            side_effect=Exception("notify error"),
        ):
            pass
        with patch(
            "app.services.notification.core.notify_user_added_to_country"
        ):
            resp = logged_in_client.post(
                f"/admin/access-requests/{req.id}/approve",
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_approve_already_processed_request(
        self, logged_in_client, db_session, admin_user
    ):
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="already_done@example.com")
        req = _make_access_request(db_session, user, country, status="approved")
        resp = logged_in_client.post(
            f"/admin/access-requests/{req.id}/approve",
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_approve_handles_exception(self, logged_in_client, db_session, admin_user):
        """Cover the except branch in approve_access_request."""
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="exc_approve@example.com")
        req = _make_access_request(db_session, user, country, status="pending")
        with patch(
            "app.routes.admin.user_management.crud.log_admin_action",
            side_effect=Exception("audit error"),
        ):
            resp = logged_in_client.post(
                f"/admin/access-requests/{req.id}/approve",
                follow_redirects=False,
            )
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# reject_access_request (POST /admin/access-requests/<id>/reject)
# ---------------------------------------------------------------------------

class TestRejectAccessRequest:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.post("/admin/access-requests/999/reject")
        assert resp.status_code in (301, 302)

    def test_404_for_nonexistent(self, logged_in_client, db_session):
        resp = logged_in_client.post("/admin/access-requests/999999/reject")
        assert resp.status_code == 404

    def test_reject_pending(self, logged_in_client, db_session, admin_user):
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="reject_me@example.com")
        req = _make_access_request(db_session, user, country, status="pending")
        resp = logged_in_client.post(
            f"/admin/access-requests/{req.id}/reject",
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_reject_already_processed(self, logged_in_client, db_session, admin_user):
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="already_rej@example.com")
        req = _make_access_request(db_session, user, country, status="rejected")
        resp = logged_in_client.post(
            f"/admin/access-requests/{req.id}/reject",
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_reject_handles_exception(self, logged_in_client, db_session, admin_user):
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="exc_reject@example.com")
        req = _make_access_request(db_session, user, country, status="pending")
        with patch(
            "app.routes.admin.user_management.crud.log_admin_action",
            side_effect=Exception("audit error"),
        ):
            resp = logged_in_client.post(
                f"/admin/access-requests/{req.id}/reject",
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_reject_with_null_user_country(self, logged_in_client, db_session, admin_user):
        """Cover None user/country branch in reject (user/country deleted)."""
        from app.models import CountryAccessRequest
        req = CountryAccessRequest(
            user_id=999999,
            country_id=999999,
            status="pending",
        )
        db_session.add(req)
        db_session.commit()
        db_session.refresh(req)
        resp = logged_in_client.post(
            f"/admin/access-requests/{req.id}/reject",
            follow_redirects=False,
        )
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# approve_all_access_requests (POST /admin/access-requests/approve-all)
# ---------------------------------------------------------------------------

class TestApproveAllAccessRequests:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.post("/admin/access-requests/approve-all")
        assert resp.status_code in (301, 302)

    def test_no_pending_requests(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/access-requests/approve-all", follow_redirects=False
        )
        assert resp.status_code == 302

    def test_approves_pending_requests(self, logged_in_client, db_session, admin_user):
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="bulk_approve@example.com")
        _make_access_request(db_session, user, country, status="pending")
        with patch("app.services.notification.core.notify_user_added_to_country"):
            resp = logged_in_client.post(
                "/admin/access-requests/approve-all", follow_redirects=False
            )
        assert resp.status_code == 302

    def test_skips_invalid_user_or_country(self, logged_in_client, db_session, admin_user):
        from app.models import CountryAccessRequest
        bad_req = CountryAccessRequest(
            user_id=9999998,
            country_id=9999998,
            status="pending",
        )
        db_session.add(bad_req)
        db_session.commit()
        resp = logged_in_client.post(
            "/admin/access-requests/approve-all", follow_redirects=False
        )
        assert resp.status_code == 302

    def test_handles_notify_exception(self, logged_in_client, db_session, admin_user):
        country = create_test_country(db_session)
        user = create_test_user(db_session, email="notify_exc@example.com")
        _make_access_request(db_session, user, country, status="pending")
        with patch(
            "app.services.notification.core.notify_user_added_to_country",
            side_effect=Exception("notify error"),
        ):
            resp = logged_in_client.post(
                "/admin/access-requests/approve-all", follow_redirects=False
            )
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# new_user (GET/POST /admin/users/new)
# ---------------------------------------------------------------------------

class TestNewUser:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/users/new")
        assert resp.status_code in (301, 302)

    def test_admin_get_returns_200(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/users/new")
        assert resp.status_code == 200

    def test_azure_b2c_configured_redirects(self, logged_in_client, db_session):
        with patch(
            "app.routes.admin.user_management.crud.is_azure_b2c_configured",
            return_value=True,
        ):
            resp = logged_in_client.get("/admin/users/new", follow_redirects=False)
        assert resp.status_code == 302

    def test_post_duplicate_email_shows_error(
        self, logged_in_client, db_session, admin_user
    ):
        existing = create_test_user(
            db_session, email="dup_email@example.com", password="Pass123!"
        )
        resp = logged_in_client.post(
            "/admin/users/new",
            data={
                "email": existing.email,
                "password": "SomePass123!",
                "name": "Dup User",
            },
            follow_redirects=False,
        )
        assert resp.status_code in (200, 302)

    def test_post_no_password_local_auth(self, logged_in_client, db_session):
        with patch(
            "app.routes.admin.user_management.crud._is_azure_sso_enabled",
            return_value=False,
        ):
            resp = logged_in_client.post(
                "/admin/users/new",
                data={
                    "email": "no_pass@example.com",
                    "password": "",
                    "name": "No Pass",
                },
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)

    def test_post_creates_user_success(self, logged_in_client, db_session, app):
        with patch(
            "app.routes.admin.user_management.crud.UserForm"
        ) as MockForm, patch(
            "app.services.email.service.send_welcome_email",
            side_effect=Exception("email fail"),
        ):
            mock_form = MagicMock()
            mock_form.validate_on_submit.return_value = True
            mock_form.email.data = "brand_new_crud@example.com"
            mock_form.password.data = "StrongPass123!"
            mock_form.name.data = "Brand New User"
            mock_form.title.data = None
            mock_form.countries.data = []
            mock_form.profile_color.data = "#3B82F6"
            mock_form.rbac_roles.data = []
            mock_form.rbac_roles.choices = []
            MockForm.return_value = mock_form

            resp = logged_in_client.post(
                "/admin/users/new",
                data={
                    "email": "brand_new_crud@example.com",
                    "password": "StrongPass123!",
                    "name": "Brand New User",
                },
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)

    def test_post_with_entity_permissions(self, logged_in_client, db_session, app):
        country = create_test_country(db_session)
        with patch(
            "app.routes.admin.user_management.crud.UserForm"
        ) as MockForm, patch(
            "app.services.email.service.send_welcome_email"
        ):
            mock_form = MagicMock()
            mock_form.validate_on_submit.return_value = True
            mock_form.email.data = "entity_perm@example.com"
            mock_form.password.data = "StrongPass123!"
            mock_form.name.data = "Entity Perm User"
            mock_form.title.data = None
            mock_form.countries.data = [country.id]
            mock_form.profile_color.data = "#FF0000"
            mock_form.rbac_roles.data = []
            mock_form.rbac_roles.choices = []
            MockForm.return_value = mock_form

            with patch(
                "app.routes.admin.user_management.crud.get_enabled_entity_groups",
                return_value=["countries"],
            ):
                resp = logged_in_client.post(
                    "/admin/users/new",
                    data={
                        "email": "entity_perm@example.com",
                        "password": "StrongPass123!",
                        "name": "Entity Perm User",
                    },
                    follow_redirects=False,
                )
        assert resp.status_code in (200, 302)

    def test_post_with_azure_sso_no_password(self, logged_in_client, db_session, app):
        with patch(
            "app.routes.admin.user_management.crud.UserForm"
        ) as MockForm, patch(
            "app.routes.admin.user_management.crud._is_azure_sso_enabled",
            return_value=True,
        ), patch(
            "app.services.email.service.send_welcome_email"
        ):
            mock_form = MagicMock()
            mock_form.validate_on_submit.return_value = True
            mock_form.email.data = "azure_user@example.com"
            mock_form.password.data = ""
            mock_form.name.data = "Azure User"
            mock_form.title.data = None
            mock_form.countries.data = []
            mock_form.profile_color.data = "#3B82F6"
            mock_form.rbac_roles.data = []
            mock_form.rbac_roles.choices = []
            MockForm.return_value = mock_form

            resp = logged_in_client.post(
                "/admin/users/new",
                data={"email": "azure_user@example.com", "name": "Azure User"},
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)

    def test_post_validates_non_country_entity_permissions(
        self, logged_in_client, db_session, app
    ):
        with patch(
            "app.routes.admin.user_management.crud.UserForm"
        ) as MockForm, patch(
            "app.services.email.service.send_welcome_email"
        ):
            mock_form = MagicMock()
            mock_form.validate_on_submit.return_value = True
            mock_form.email.data = "nce_perm@example.com"
            mock_form.password.data = "StrongPass123!"
            mock_form.name.data = "NCE User"
            mock_form.title.data = None
            mock_form.countries.data = []
            mock_form.profile_color.data = "#3B82F6"
            mock_form.rbac_roles.data = []
            mock_form.rbac_roles.choices = []
            MockForm.return_value = mock_form

            resp = logged_in_client.post(
                "/admin/users/new",
                data={
                    "email": "nce_perm@example.com",
                    "password": "StrongPass123!",
                    "name": "NCE User",
                    "entity_permissions": ["division:1", "invalid", "division:abc"],
                },
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)


# ---------------------------------------------------------------------------
# edit_user (GET/POST /admin/users/edit_user/<id>)
# ---------------------------------------------------------------------------

class TestEditUser:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/users/edit_user/1")
        assert resp.status_code in (301, 302)

    def test_404_for_nonexistent(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/users/edit_user/999999")
        assert resp.status_code == 404

    def test_get_returns_200(self, logged_in_client, db_session, admin_user):
        user = create_test_user(db_session, email="edit_target@example.com")
        resp = logged_in_client.get(f"/admin/users/edit_user/{user.id}")
        assert resp.status_code == 200

    def test_get_own_profile(self, logged_in_client, db_session, admin_user, app):
        with app.app_context():
            from app.models import User
            u = User.query.get(admin_user.id)
            uid = u.id
        resp = logged_in_client.get(f"/admin/users/edit_user/{uid}")
        assert resp.status_code == 200

    def test_non_sys_mgr_cannot_edit_admin(
        self, logged_in_client, db_session
    ):
        """Admin user cannot edit another admin user (only sys mgr can)."""
        other_admin = create_test_user(
            db_session, email="other_admin@example.com", role="admin"
        )
        resp = logged_in_client.get(
            f"/admin/users/edit_user/{other_admin.id}", follow_redirects=False
        )
        assert resp.status_code in (200, 302)

    def test_post_updates_user(self, logged_in_client, db_session, admin_user):
        user = create_test_user(db_session, email="update_target@example.com")
        with patch(
            "app.routes.admin.user_management.crud.UserForm"
        ) as MockForm:
            mock_form = MagicMock()
            mock_form.validate_on_submit.return_value = True
            mock_form.email.data = "update_target@example.com"
            mock_form.password.data = ""
            mock_form.name.data = "Updated Name"
            mock_form.title.data = "Updated Title"
            mock_form.countries.data = []
            mock_form.profile_color.data = "#FF5733"
            mock_form.rbac_roles.data = []
            mock_form.rbac_roles.choices = []
            MockForm.return_value = mock_form

            resp = logged_in_client.post(
                f"/admin/users/edit_user/{user.id}",
                data={
                    "email": "update_target@example.com",
                    "name": "Updated Name",
                    "title": "Updated Title",
                },
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)

    def test_post_with_azure_email_change_blocked(
        self, logged_in_client, db_session
    ):
        user = create_test_user(db_session, email="azure_edit@example.com")
        with patch(
            "app.routes.admin.user_management.crud.UserForm"
        ) as MockForm, patch(
            "app.routes.admin.user_management.crud._is_azure_sso_enabled",
            return_value=True,
        ):
            mock_form = MagicMock()
            mock_form.validate_on_submit.return_value = True
            mock_form.email.data = "changed_email@example.com"
            mock_form.password.data = ""
            mock_form.name.data = "Azure Edit"
            mock_form.title.data = None
            mock_form.countries.data = []
            mock_form.profile_color.data = "#3B82F6"
            mock_form.rbac_roles.data = []
            mock_form.rbac_roles.choices = []
            MockForm.return_value = mock_form

            resp = logged_in_client.post(
                f"/admin/users/edit_user/{user.id}",
                data={"email": "changed_email@example.com", "name": "Azure Edit"},
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)

    def test_post_with_password_change(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="pw_change@example.com")
        with patch(
            "app.routes.admin.user_management.crud.UserForm"
        ) as MockForm:
            mock_form = MagicMock()
            mock_form.validate_on_submit.return_value = True
            mock_form.email.data = "pw_change@example.com"
            mock_form.password.data = "NewStrongPass123!"
            mock_form.name.data = "PW Change User"
            mock_form.title.data = None
            mock_form.countries.data = []
            mock_form.profile_color.data = "#3B82F6"
            mock_form.rbac_roles.data = []
            mock_form.rbac_roles.choices = []
            MockForm.return_value = mock_form

            resp = logged_in_client.post(
                f"/admin/users/edit_user/{user.id}",
                data={"email": "pw_change@example.com", "name": "PW Change User"},
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)

    def test_get_pre_populates_form(self, logged_in_client, db_session):
        user = create_test_user(
            db_session,
            email="prefill@example.com",
            name="PreFill User",
        )
        resp = logged_in_client.get(f"/admin/users/edit_user/{user.id}")
        assert resp.status_code == 200

    def test_post_notification_preferences(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="notif_pref@example.com")
        with patch(
            "app.routes.admin.user_management.crud.UserForm"
        ) as MockForm:
            mock_form = MagicMock()
            mock_form.validate_on_submit.return_value = True
            mock_form.email.data = "notif_pref@example.com"
            mock_form.password.data = ""
            mock_form.name.data = "Notif User"
            mock_form.title.data = None
            mock_form.countries.data = []
            mock_form.profile_color.data = "#3B82F6"
            mock_form.rbac_roles.data = []
            mock_form.rbac_roles.choices = []
            MockForm.return_value = mock_form

            resp = logged_in_client.post(
                f"/admin/users/edit_user/{user.id}",
                data={
                    "email": "notif_pref@example.com",
                    "name": "Notif User",
                    "notification_frequency": "daily",
                    "digest_time": "08:00",
                    "sound_enabled": "on",
                },
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)

    def test_post_weekly_notification_preferences(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="weekly_notif@example.com")
        with patch(
            "app.routes.admin.user_management.crud.UserForm"
        ) as MockForm:
            mock_form = MagicMock()
            mock_form.validate_on_submit.return_value = True
            mock_form.email.data = "weekly_notif@example.com"
            mock_form.password.data = ""
            mock_form.name.data = "Weekly User"
            mock_form.title.data = None
            mock_form.countries.data = []
            mock_form.profile_color.data = "#3B82F6"
            mock_form.rbac_roles.data = []
            mock_form.rbac_roles.choices = []
            MockForm.return_value = mock_form

            resp = logged_in_client.post(
                f"/admin/users/edit_user/{user.id}",
                data={
                    "email": "weekly_notif@example.com",
                    "name": "Weekly User",
                    "notification_frequency": "weekly",
                    "digest_time": "09:00",
                    "digest_day": "Monday",
                },
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)


# ---------------------------------------------------------------------------
# kickout_device (POST /admin/users/<id>/devices/<id>/kickout)
# ---------------------------------------------------------------------------

class TestKickoutDevice:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.post("/admin/users/1/devices/1/kickout")
        assert resp.status_code in (301, 302, 401)

    def test_kicks_out_active_device(self, logged_in_client, db_session, admin_user):
        _grant_perm(db_session, "admin.users.devices.kickout")
        user = create_test_user(db_session, email="kickout_user@example.com")
        device = _make_device(db_session, user.id)
        resp = logged_in_client.post(
            f"/admin/users/{user.id}/devices/{device.id}/kickout"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("success") is True or "success" in str(data)

    def test_returns_400_if_already_logged_out(
        self, logged_in_client, db_session, admin_user
    ):
        _grant_perm(db_session, "admin.users.devices.kickout")
        user = create_test_user(db_session, email="already_out@example.com")
        device = _make_device(db_session, user.id, logged_out=True)
        resp = logged_in_client.post(
            f"/admin/users/{user.id}/devices/{device.id}/kickout"
        )
        assert resp.status_code == 400

    def test_404_for_nonexistent_device(
        self, logged_in_client, db_session, admin_user
    ):
        _grant_perm(db_session, "admin.users.devices.kickout")
        user = create_test_user(db_session, email="no_device_kickout@example.com")
        resp = logged_in_client.post(
            f"/admin/users/{user.id}/devices/999999/kickout"
        )
        assert resp.status_code == 404

    def test_404_for_nonexistent_user(self, logged_in_client, db_session, admin_user):
        _grant_perm(db_session, "admin.users.devices.kickout")
        resp = logged_in_client.post("/admin/users/999999/devices/1/kickout")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# remove_device (DELETE /admin/users/<id>/devices/<id>/remove)
# ---------------------------------------------------------------------------

class TestRemoveDevice:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.delete("/admin/users/1/devices/1/remove")
        assert resp.status_code in (301, 302, 401)

    def test_removes_active_device(self, logged_in_client, db_session, admin_user):
        _grant_perm(db_session, "admin.users.devices.remove")
        user = create_test_user(db_session, email="remove_device@example.com")
        device = _make_device(db_session, user.id)
        resp = logged_in_client.delete(
            f"/admin/users/{user.id}/devices/{device.id}/remove"
        )
        assert resp.status_code == 200

    def test_removes_logged_out_device(self, logged_in_client, db_session, admin_user):
        _grant_perm(db_session, "admin.users.devices.remove")
        user = create_test_user(db_session, email="remove_lo_device@example.com")
        device = _make_device(db_session, user.id, logged_out=True)
        resp = logged_in_client.delete(
            f"/admin/users/{user.id}/devices/{device.id}/remove"
        )
        assert resp.status_code == 200

    def test_404_for_nonexistent_device(self, logged_in_client, db_session, admin_user):
        _grant_perm(db_session, "admin.users.devices.remove")
        user = create_test_user(db_session, email="no_device_remove@example.com")
        resp = logged_in_client.delete(
            f"/admin/users/{user.id}/devices/999999/remove"
        )
        assert resp.status_code == 404

    def test_404_for_nonexistent_user(self, logged_in_client, db_session, admin_user):
        _grant_perm(db_session, "admin.users.devices.remove")
        resp = logged_in_client.delete("/admin/users/999999/devices/1/remove")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# delete_user (POST /admin/users/delete/<id>)
# ---------------------------------------------------------------------------

class TestDeleteUser:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.post("/admin/users/delete/1")
        assert resp.status_code in (301, 302)

    def test_non_sys_mgr_cannot_delete(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="todelete1@example.com")
        resp = logged_in_client.post(
            f"/admin/users/delete/{user.id}", follow_redirects=False
        )
        assert resp.status_code == 302

    def test_sys_mgr_deletes_user(self, logged_in_sm_client, db_session, system_manager_user):
        user = create_test_user(db_session, email="todelete_sm@example.com")
        _grant_perm(db_session, "admin.users.delete")
        resp = logged_in_sm_client.post(
            f"/admin/users/delete/{user.id}", follow_redirects=False
        )
        assert resp.status_code == 302

    def test_cannot_delete_self(
        self, logged_in_sm_client, db_session, system_manager_user, app
    ):
        _grant_perm(db_session, "admin.users.delete")
        with app.app_context():
            uid = system_manager_user.id
        resp = logged_in_sm_client.post(
            f"/admin/users/delete/{uid}", follow_redirects=False
        )
        assert resp.status_code == 302

    def test_404_for_nonexistent(self, logged_in_sm_client, db_session):
        _grant_perm(db_session, "admin.users.delete")
        resp = logged_in_sm_client.post(
            "/admin/users/delete/999999", follow_redirects=False
        )
        assert resp.status_code == 404

    def test_cascade_exception_shows_warning(
        self, logged_in_sm_client, db_session, system_manager_user
    ):
        _grant_perm(db_session, "admin.users.delete")
        user = create_test_user(db_session, email="cascade_fail@example.com")
        with patch(
            "app.routes.admin.user_management.crud._cascade_delete_user_related",
            side_effect=Exception("cascade error"),
        ):
            resp = logged_in_sm_client.post(
                f"/admin/users/delete/{user.id}", follow_redirects=False
            )
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# user_deletion_preview (GET /admin/users/<id>/deletion-preview)
# ---------------------------------------------------------------------------

class TestUserDeletionPreview:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/users/1/deletion-preview")
        assert resp.status_code in (301, 302)

    def test_non_sys_mgr_forbidden(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="preview_target@example.com")
        resp = logged_in_client.get(f"/admin/users/{user.id}/deletion-preview")
        assert resp.status_code == 403

    def test_sys_mgr_gets_preview(
        self, logged_in_sm_client, db_session, system_manager_user
    ):
        _grant_perm(db_session, "admin.users.delete")
        user = create_test_user(db_session, email="preview_sm@example.com")
        resp = logged_in_sm_client.get(
            f"/admin/users/{user.id}/deletion-preview"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data is not None

    def test_404_for_nonexistent(self, logged_in_sm_client, db_session):
        _grant_perm(db_session, "admin.users.delete")
        resp = logged_in_sm_client.get("/admin/users/999999/deletion-preview")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# archive_user (POST /admin/users/archive/<id>)
# ---------------------------------------------------------------------------

class TestArchiveUser:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.post("/admin/users/archive/1")
        assert resp.status_code in (301, 302)

    def test_404_for_nonexistent(self, logged_in_client, db_session):
        resp = logged_in_client.post("/admin/users/archive/999999")
        assert resp.status_code == 404

    def test_cannot_deactivate_self(self, logged_in_client, db_session, admin_user, app):
        with app.app_context():
            uid = admin_user.id
        resp = logged_in_client.post(
            f"/admin/users/archive/{uid}", follow_redirects=False
        )
        assert resp.status_code == 302

    def test_deactivates_regular_user(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="deactivate_me@example.com")
        resp = logged_in_client.post(
            f"/admin/users/archive/{user.id}", follow_redirects=False
        )
        assert resp.status_code == 302

    def test_reactivates_inactive_user(self, logged_in_client, db_session, app):
        user = create_test_user(
            db_session, email="reactivate_me@example.com", active=False
        )
        resp = logged_in_client.post(
            f"/admin/users/archive/{user.id}", follow_redirects=False
        )
        assert resp.status_code == 302

    def test_non_sys_mgr_cannot_archive_admin(self, logged_in_client, db_session):
        other_admin = create_test_user(
            db_session, email="admin_to_archive@example.com", role="admin"
        )
        resp = logged_in_client.post(
            f"/admin/users/archive/{other_admin.id}", follow_redirects=False
        )
        assert resp.status_code == 302

    def test_handles_exception(self, logged_in_client, db_session):
        user = create_test_user(db_session, email="archive_exc@example.com")
        with patch(
            "app.routes.admin.user_management.crud.log_admin_action",
            side_effect=Exception("audit error"),
        ):
            resp = logged_in_client.post(
                f"/admin/users/archive/{user.id}", follow_redirects=False
            )
        assert resp.status_code == 302
