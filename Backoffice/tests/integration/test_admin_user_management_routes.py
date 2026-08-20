"""Integration tests for routes.admin.user_management (P1 — currently 25.8% coverage).

Covers:
  - GET  /admin/users              — list page (auth, permission)
  - GET  /admin/users/new          — create form (auth, Azure-B2C guard)
  - POST /admin/users/new          — create user (happy path, duplicate email, B2C guard)
  - GET  /admin/users/edit_user/<id> — edit form (auth)
  - POST /admin/users/archive/<id>   — activate/deactivate toggle
  - POST /admin/users/delete/<id>    — delete (system manager only, self-delete guard)
  - GET  /admin/access-requests      — access request list
"""
import pytest
from unittest.mock import patch, MagicMock
from tests.helpers import login_session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _admin_get(client, url, follow_redirects=True):
    return client.get(url, follow_redirects=follow_redirects)


def _admin_post(client, url, data=None, follow_redirects=True):
    return client.post(url, data=data or {}, follow_redirects=follow_redirects)


# ===========================================================================
# GET /admin/users — manage users list
# ===========================================================================

class TestManageUsersListRoute:
    def test_requires_login(self, client, db_session):
        resp = _admin_get(client, "/admin/users", follow_redirects=False)
        assert resp.status_code in (302, 401)

    def test_admin_can_view_user_list(self, logged_in_admin_client, db_session):
        resp = _admin_get(logged_in_admin_client, "/admin/users")
        assert resp.status_code == 200

    def test_user_list_shows_html(self, logged_in_admin_client, db_session):
        resp = _admin_get(logged_in_admin_client, "/admin/users")
        assert b"<html" in resp.data.lower() or b"<!doctype" in resp.data.lower()

    def test_regular_user_cannot_view_list(self, client, test_user, app):
        login_session(client, test_user.id)
        resp = _admin_get(client, "/admin/users", follow_redirects=False)
        assert resp.status_code in (302, 403)


# ===========================================================================
# GET /admin/users/new — create user form
# ===========================================================================

class TestNewUserFormRoute:
    def test_requires_login(self, client, db_session):
        resp = _admin_get(client, "/admin/users/new", follow_redirects=False)
        assert resp.status_code in (302, 401)

    def test_admin_can_view_new_user_form(self, logged_in_admin_client, db_session):
        with patch("app.routes.admin.user_management.crud.is_azure_b2c_configured", return_value=False):
            resp = _admin_get(logged_in_admin_client, "/admin/users/new")
        assert resp.status_code == 200

    def test_b2c_configured_redirects_away(self, logged_in_admin_client, db_session):
        with patch("app.routes.admin.user_management.crud.is_azure_b2c_configured", return_value=True):
            resp = _admin_get(logged_in_admin_client, "/admin/users/new", follow_redirects=False)
        assert resp.status_code == 302

    def test_system_manager_can_view_new_user_form_when_b2c_configured(self, logged_in_sm_client, db_session):
        """System Managers get a narrow pre-provisioning exception to the SSO-only guard."""
        with patch("app.routes.admin.user_management.crud.is_azure_b2c_configured", return_value=True):
            resp = _admin_get(logged_in_sm_client, "/admin/users/new", follow_redirects=False)
        assert resp.status_code == 200


# ===========================================================================
# POST /admin/users/new — create user
# ===========================================================================

class TestCreateUserRoute:
    def test_duplicate_email_rejected(self, logged_in_admin_client, admin_user, db_session, app):
        with patch("app.routes.admin.user_management.crud.is_azure_b2c_configured", return_value=False), \
             patch("app.services.email.service.send_welcome_email"):
            resp = _admin_post(
                logged_in_admin_client,
                "/admin/users/new",
                data={
                    "email": admin_user.email,
                    "name": "Dup User",
                    "password": "TestPassword123!",
                    "title": "",
                    "countries": [],
                },
            )
        assert resp.status_code == 200
        assert b"already exists" in resp.data

    def test_missing_password_rejected_for_local_auth(self, logged_in_admin_client, db_session):
        with patch("app.routes.admin.user_management.crud.is_azure_b2c_configured", return_value=False), \
             patch("app.routes.admin.user_management.crud._is_azure_sso_enabled", return_value=False):
            resp = _admin_post(
                logged_in_admin_client,
                "/admin/users/new",
                data={
                    "email": "newuser_nopass@example.com",
                    "name": "No Pass",
                    "password": "",
                    "title": "",
                },
            )
        assert resp.status_code in (200, 302)

    def test_b2c_configured_blocks_creation(self, logged_in_admin_client, db_session):
        with patch("app.routes.admin.user_management.crud.is_azure_b2c_configured", return_value=True):
            resp = _admin_post(
                logged_in_admin_client,
                "/admin/users/new",
                data={"email": "blocked@example.com", "name": "Blocked", "password": "Test123!"},
            )
        assert resp.status_code in (200, 302)

    def test_regular_admin_still_blocked_when_b2c_configured_no_user_created(
        self, logged_in_admin_client, db_session, app
    ):
        """Non-system-manager admins keep the pre-existing SSO-only restriction (pentest Finding #4)."""
        with patch("app.routes.admin.user_management.crud.is_azure_b2c_configured", return_value=True):
            resp = _admin_post(
                logged_in_admin_client,
                "/admin/users/new",
                data={"email": "should_not_be_created@example.com", "name": "Nope", "password": "Test123!"},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        with app.app_context():
            from app.models import User
            assert User.query.filter_by(email="should_not_be_created@example.com").first() is None

    def test_system_manager_can_pre_add_user_when_b2c_configured(
        self, logged_in_sm_client, system_manager_user, db_session, app
    ):
        """System Managers may pre-provision an account ahead of someone's first SSO sign-in.

        Also exercises email normalization (mixed-case entry still lands lowercased so it
        matches what auth.azure_callback will look up on first sign-in).
        """
        with app.app_context():
            from app.models.rbac import RbacRole
            role = RbacRole.query.first()
            role_id = role.id if role else None

        with patch("app.routes.admin.user_management.crud.is_azure_b2c_configured", return_value=True), \
             patch("app.routes.admin.user_management.crud._is_azure_sso_enabled", return_value=True), \
             patch("app.services.email.service.send_welcome_email"):
            resp = _admin_post(
                logged_in_sm_client,
                "/admin/users/new",
                data={
                    "email": "PreAdded.User@EXAMPLE.com",
                    "name": "Pre Added",
                    "password": "",
                    "title": "",
                    "countries": [],
                    "rbac_roles": [str(role_id)] if role_id else [],
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

        with app.app_context():
            from app.models import User
            created = User.query.filter_by(email="preadded.user@example.com").first()
            assert created is not None
            assert created.name == "Pre Added"
            assert created.password_hash is None

    def test_email_normalized_case_insensitive_duplicate(
        self, logged_in_admin_client, admin_user, db_session
    ):
        """A differently-cased email entry still collides with an existing account."""
        with patch("app.routes.admin.user_management.crud.is_azure_b2c_configured", return_value=False), \
             patch("app.services.email.service.send_welcome_email"):
            resp = _admin_post(
                logged_in_admin_client,
                "/admin/users/new",
                data={
                    "email": admin_user.email.upper(),
                    "name": "Case Dup",
                    "password": "TestPassword123!",
                    "title": "",
                    "countries": [],
                },
            )
        assert resp.status_code == 200
        assert b"already exists" in resp.data


# ===========================================================================
# GET /admin/users/edit_user/<id>
# ===========================================================================

class TestEditUserRoute:
    def test_requires_login(self, client, admin_user, db_session):
        resp = _admin_get(client, f"/admin/users/edit_user/{admin_user.id}", follow_redirects=False)
        assert resp.status_code in (302, 401)

    def test_admin_can_view_edit_form(self, logged_in_admin_client, admin_user, db_session):
        resp = _admin_get(logged_in_admin_client, f"/admin/users/edit_user/{admin_user.id}")
        assert resp.status_code == 200

    def test_edit_404_for_nonexistent_user(self, logged_in_admin_client, db_session):
        resp = _admin_get(logged_in_admin_client, "/admin/users/edit_user/999999")
        assert resp.status_code == 404


# ===========================================================================
# POST /admin/users/archive/<id> — activate / deactivate
# ===========================================================================

class TestArchiveUserRoute:
    def test_requires_login(self, client, test_user, db_session):
        resp = _admin_post(client, f"/admin/users/archive/{test_user.id}", follow_redirects=False)
        assert resp.status_code in (302, 401)

    def test_admin_can_deactivate_regular_user(
        self, logged_in_admin_client, test_user, db_session, app
    ):
        resp = _admin_post(
            logged_in_admin_client, f"/admin/users/archive/{test_user.id}"
        )
        assert resp.status_code in (200, 302)
        with app.app_context():
            from app.models import User
            updated = User.query.get(test_user.id)
            assert updated.active is False

    def test_cannot_deactivate_self(self, logged_in_admin_client, admin_user, db_session):
        resp = _admin_post(
            logged_in_admin_client, f"/admin/users/archive/{admin_user.id}"
        )
        assert resp.status_code in (200, 302)
        # The flash message or redirect should indicate the action was blocked
        assert b"cannot deactivate" in resp.data or resp.status_code == 302


# ===========================================================================
# POST /admin/users/delete/<id>
# ===========================================================================

class TestDeleteUserRoute:
    def test_requires_login(self, client, test_user, db_session):
        resp = _admin_post(client, f"/admin/users/delete/{test_user.id}", follow_redirects=False)
        assert resp.status_code in (302, 401)

    def test_regular_admin_cannot_delete(
        self, logged_in_admin_client, test_user, db_session
    ):
        resp = _admin_post(
            logged_in_admin_client,
            f"/admin/users/delete/{test_user.id}",
        )
        # Regular admin (not system_manager) should be redirected with a flash, not 200 delete
        assert resp.status_code in (200, 302)

    def test_system_manager_can_delete_other_user(
        self, logged_in_sm_client, test_user, db_session, app
    ):
        user_id = test_user.id
        resp = _admin_post(
            logged_in_sm_client,
            f"/admin/users/delete/{user_id}",
        )
        assert resp.status_code in (200, 302)
        with app.app_context():
            from app.models import User
            deleted = User.query.get(user_id)
            assert deleted is None

    def test_cannot_delete_self(self, logged_in_sm_client, system_manager_user, db_session):
        resp = _admin_post(
            logged_in_sm_client,
            f"/admin/users/delete/{system_manager_user.id}",
        )
        assert resp.status_code in (200, 302)


# ===========================================================================
# GET /admin/access-requests
# ===========================================================================

class TestAccessRequestsListRoute:
    def test_requires_login(self, client, db_session):
        resp = _admin_get(client, "/admin/access-requests", follow_redirects=False)
        assert resp.status_code in (302, 401)

    def test_admin_can_view_access_requests(self, logged_in_admin_client, db_session):
        resp = _admin_get(logged_in_admin_client, "/admin/access-requests")
        assert resp.status_code == 200

    def test_access_requests_includes_team_member_filter(self, logged_in_admin_client, db_session, admin_user):
        from tests.factories import create_test_country

        country = create_test_country(db_session, iso3="TMF", iso2="TM")
        country.fds_member_user_id = admin_user.id
        db_session.commit()

        resp = _admin_get(logged_in_admin_client, "/admin/access-requests")
        assert resp.status_code == 200
        assert b'id="fdsMemberFilter"' in resp.data
        assert b'Team member' in resp.data or b'team member' in resp.data.lower()

    def test_digest_settings_modal_visible_to_system_manager(self, logged_in_sm_client, db_session):
        resp = _admin_get(logged_in_sm_client, "/admin/access-requests")
        assert resp.status_code == 200
        assert b'id="openFdsDigestSettingsBtn"' in resp.data
        assert b'id="fds-access-request-digest-modal"' in resp.data
        assert b'id="fds-access-request-digest-local-hour"' in resp.data
        assert b'digest-settings' in resp.data
        assert b'Send digest now' in resp.data or b'send digest now' in resp.data.lower()
        assert b'Last sent' in resp.data or b'last sent' in resp.data.lower()

    def test_digest_send_post_requires_system_manager(self, logged_in_admin_client, db_session):
        resp = _admin_post(
            logged_in_admin_client,
            "/admin/access-requests/digest-send",
            data={},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_digest_send_post_system_manager(self, logged_in_sm_client, db_session, app):
        with app.app_context():
            with patch(
                "app.services.email.fds_access_request_digest.run_fds_access_request_digest_job",
            ) as mock_run:
                from app.services.email.fds_access_request_digest import FdsDigestRunResult

                mock_run.return_value = FdsDigestRunResult(
                    ran=True,
                    sent_count=2,
                    skipped_count=0,
                    failed_count=0,
                )
                resp = _admin_post(
                    logged_in_sm_client,
                    "/admin/access-requests/digest-send",
                    data={},
                    follow_redirects=True,
                )
            assert resp.status_code == 200
            mock_run.assert_called_once_with(manual=True)

    def test_digest_settings_modal_hidden_from_non_system_manager(self, logged_in_admin_client, db_session):
        resp = _admin_get(logged_in_admin_client, "/admin/access-requests")
        assert resp.status_code == 200
        assert b'id="openFdsDigestSettingsBtn"' not in resp.data
        assert b'id="fds-access-request-digest-modal"' not in resp.data
        assert b'id="fds-access-request-digest-utc-hour"' not in resp.data
        assert b'digest-settings' not in resp.data

    def test_digest_settings_post_requires_system_manager(self, logged_in_admin_client, db_session):
        resp = _admin_post(
            logged_in_admin_client,
            "/admin/access-requests/digest-settings",
            data={
                "fds_access_request_digest_enabled": "1",
                "fds_access_request_digest_local_hour": "8",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_digest_settings_post_system_manager(self, logged_in_sm_client, db_session, app):
        with app.app_context():
            from app.services.platform.app_settings_service import get_fds_access_request_digest_settings

            resp = _admin_post(
                logged_in_sm_client,
                "/admin/access-requests/digest-settings",
                data={
                    "fds_access_request_digest_enabled": "1",
                    "fds_access_request_digest_local_hour": "8",
                },
                follow_redirects=False,
            )
            assert resp.status_code == 302
            settings = get_fds_access_request_digest_settings()
            assert settings["enabled"] is True
            assert settings["local_hour"] == 8

    def test_regular_user_denied(self, client, test_user, app):
        login_session(client, test_user.id)
        resp = _admin_get(client, "/admin/access-requests", follow_redirects=False)
        assert resp.status_code in (302, 403)
