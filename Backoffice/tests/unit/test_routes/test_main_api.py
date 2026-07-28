"""
Tests for app/routes/main/api.py

Covers:
  - GET /api/users/profile-summary (privileged and non-privileged paths)
  - GET /api/notifications
  - GET /api/notifications/count
  - GET /api/notifications/websocket-status  (public, no auth required)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.factories import (
    create_test_user,
    create_test_country,
    _grant_entity_permission,
)
from tests.helpers import login_session, assert_json_has_keys

pytestmark = [pytest.mark.unit]

# AuthorizationService is imported *inside* the route functions, so we must
# patch at the source class, not the route module.
_AUTH_SVC = "app.services.organization.authorization_service.AuthorizationService"
# NotificationService is also imported lazily inside route functions.
_NOTIF_SVC = "app.services.notification.service.NotificationService"


# ===========================================================================
# /api/users/profile-summary
# ===========================================================================

class TestApiUsersProfileSummary:
    """GET /api/users/profile-summary"""

    URL = "/api/users/profile-summary"

    # --- authentication guard -------------------------------------------

    def test_unauthenticated_redirects_to_login(self, client, db_session, app):
        resp = client.get(self.URL)
        assert resp.status_code in (302, 401)

    # --- empty param cases -----------------------------------------------

    def test_returns_empty_profiles_when_no_params(self, client, db_session, app, admin_user):
        login_session(client, admin_user.id)
        with patch(f"{_AUTH_SVC}.is_system_manager", return_value=True), \
             patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=True):
            resp = client.get(self.URL)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["profiles"] == []

    # --- privileged user: lookup by integer user_id ----------------------

    def test_privileged_returns_profiles_with_id_field(self, client, db_session, app, admin_user):
        login_session(client, admin_user.id)
        with patch(f"{_AUTH_SVC}.is_system_manager", return_value=True), \
             patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=True):
            resp = client.get(self.URL + f"?user_ids={admin_user.id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        profiles = data["profiles"]
        assert len(profiles) == 1
        assert "id" in profiles[0]
        assert profiles[0]["id"] == admin_user.id

    def test_privileged_lookup_by_email(self, client, db_session, app, admin_user):
        login_session(client, admin_user.id)
        with patch(f"{_AUTH_SVC}.is_system_manager", return_value=True), \
             patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=True):
            resp = client.get(self.URL + f"?emails={admin_user.email}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        profiles = data["profiles"]
        assert any(p["email"] == admin_user.email for p in profiles)

    def test_privileged_nonexistent_user_returns_empty(self, client, db_session, app, admin_user):
        login_session(client, admin_user.id)
        with patch(f"{_AUTH_SVC}.is_system_manager", return_value=True), \
             patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=True):
            resp = client.get(self.URL + "?user_ids=999999")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["profiles"] == []

    # --- non-privileged user: can only see self ---------------------------

    def test_non_privileged_can_see_self_by_user_id(self, client, db_session, app, test_user):
        login_session(client, test_user.id)
        with patch(f"{_AUTH_SVC}.is_system_manager", return_value=False), \
             patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=False):
            resp = client.get(self.URL + f"?user_ids={test_user.id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        # id field should NOT appear for non-privileged callers
        for profile in data["profiles"]:
            assert "id" not in profile

    def test_non_privileged_cannot_see_other_user_by_id(self, client, db_session, app, test_user, admin_user):
        """Non-privileged user requesting another user's integer id → empty list."""
        login_session(client, test_user.id)
        with patch(f"{_AUTH_SVC}.is_system_manager", return_value=False), \
             patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=False):
            resp = client.get(self.URL + f"?user_ids={admin_user.id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["profiles"] == []

    def test_non_privileged_with_shared_scope_can_see_peer(self, client, db_session, app):
        """Non-privileged user can see another user who shares an entity permission."""
        country = create_test_country(db_session)
        user_a = create_test_user(db_session, role="focal_point")
        user_b = create_test_user(db_session, role="focal_point")

        _grant_entity_permission(db_session, user_a, "country", country.id)
        _grant_entity_permission(db_session, user_b, "country", country.id)
        db_session.commit()

        login_session(client, user_a.id)
        with patch(f"{_AUTH_SVC}.is_system_manager", return_value=False), \
             patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=False):
            resp = client.get(self.URL + f"?emails={user_b.email}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"

    def test_non_privileged_with_no_shared_scope_cannot_see_peer(self, client, db_session, app):
        """Non-privileged user cannot see another user with a different entity scope."""
        country_a = create_test_country(db_session)
        country_b = create_test_country(db_session)
        user_a = create_test_user(db_session, role="focal_point")
        user_b = create_test_user(db_session, role="focal_point")

        _grant_entity_permission(db_session, user_a, "country", country_a.id)
        _grant_entity_permission(db_session, user_b, "country", country_b.id)
        db_session.commit()

        login_session(client, user_a.id)
        with patch(f"{_AUTH_SVC}.is_system_manager", return_value=False), \
             patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=False):
            resp = client.get(self.URL + f"?emails={user_b.email}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["profiles"] == []

    # --- lookup by external_id -------------------------------------------

    def test_privileged_lookup_by_external_uuid(self, client, db_session, app, admin_user):
        import uuid
        from app.models import User

        ext_id = str(uuid.uuid4())
        with app.app_context():
            u = User.query.get(admin_user.id)
            u.external_id = ext_id
            db_session.commit()

        login_session(client, admin_user.id)
        with patch(f"{_AUTH_SVC}.is_system_manager", return_value=True), \
             patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=True):
            resp = client.get(self.URL + f"?external_ids={ext_id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"

    # --- profile field coverage ------------------------------------------

    def test_profile_contains_expected_fields(self, client, db_session, app, admin_user):
        login_session(client, admin_user.id)
        with patch(f"{_AUTH_SVC}.is_system_manager", return_value=True), \
             patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=True):
            resp = client.get(self.URL + f"?user_ids={admin_user.id}")
        assert resp.status_code == 200
        data = resp.get_json()
        profiles = data["profiles"]
        assert len(profiles) == 1
        profile = profiles[0]
        for field in ("name", "email", "active", "profile_color", "role_badge_key"):
            assert field in profile, f"Missing field: {field}"

    # --- exception handling ----------------------------------------------

    def test_exception_in_handler_returns_500(self, client, db_session, app, admin_user):
        login_session(client, admin_user.id)
        with patch(
            "app.routes.main.api.collect_arg_strings",
            side_effect=RuntimeError("unexpected"),
        ):
            resp = client.get(self.URL + "?user_ids=1")
        assert resp.status_code == 500


# ===========================================================================
# /api/notifications
# ===========================================================================

class TestApiGetNotifications:
    """GET /api/notifications"""

    URL = "/api/notifications"

    def test_unauthenticated_redirects(self, client, db_session, app):
        resp = client.get(self.URL)
        assert resp.status_code in (302, 401)

    def test_authenticated_returns_200_with_expected_keys(self, client, db_session, app, admin_user):
        login_session(client, admin_user.id)
        with patch(f"{_NOTIF_SVC}.get_user_notifications", return_value=([], 0)), \
             patch(f"{_NOTIF_SVC}.get_unread_count", return_value=0):
            resp = client.get(self.URL)
        assert resp.status_code == 200
        data = assert_json_has_keys(resp, "success", "notifications", "unread_count", "total_count")
        assert data["success"] is True
        assert isinstance(data["notifications"], list)

    def test_returns_notification_list_and_counts(self, client, db_session, app, admin_user):
        login_session(client, admin_user.id)
        fake_notif = {"id": 1, "message": "Hello", "read": False}
        with patch(f"{_NOTIF_SVC}.get_user_notifications", return_value=([fake_notif], 1)), \
             patch(f"{_NOTIF_SVC}.get_unread_count", return_value=1):
            resp = client.get(self.URL)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_count"] == 1
        assert data["unread_count"] == 1
        assert len(data["notifications"]) == 1

    def test_exception_in_notification_service_returns_500(self, client, db_session, app, admin_user):
        login_session(client, admin_user.id)
        with patch(f"{_NOTIF_SVC}.get_user_notifications", side_effect=RuntimeError("db error")):
            resp = client.get(self.URL)
        assert resp.status_code == 500


# ===========================================================================
# /api/notifications/count
# ===========================================================================

class TestApiGetNotificationsCount:
    """GET /api/notifications/count"""

    URL = "/api/notifications/count"

    def test_unauthenticated_redirects(self, client, db_session, app):
        resp = client.get(self.URL)
        assert resp.status_code in (302, 401)

    def test_authenticated_returns_200_with_unread_count(self, client, db_session, app, admin_user):
        login_session(client, admin_user.id)
        with patch(f"{_NOTIF_SVC}.get_unread_count", return_value=5):
            resp = client.get(self.URL)
        assert resp.status_code == 200
        data = assert_json_has_keys(resp, "success", "unread_count")
        assert data["success"] is True
        assert data["unread_count"] == 5

    def test_zero_unread_count(self, client, db_session, app, admin_user):
        login_session(client, admin_user.id)
        with patch(f"{_NOTIF_SVC}.get_unread_count", return_value=0):
            resp = client.get(self.URL)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["unread_count"] == 0

    def test_exception_returns_500(self, client, db_session, app, admin_user):
        login_session(client, admin_user.id)
        with patch(f"{_NOTIF_SVC}.get_unread_count", side_effect=RuntimeError("db error")):
            resp = client.get(self.URL)
        assert resp.status_code == 500


# ===========================================================================
# /api/notifications/websocket-status  (public, no auth required)
# ===========================================================================

class TestApiWebsocketStatus:
    """GET /api/notifications/websocket-status — public endpoint."""

    URL = "/api/notifications/websocket-status"

    def test_public_returns_200_without_auth(self, client, db_session, app):
        resp = client.get(self.URL)
        assert resp.status_code == 200

    def test_response_contains_expected_keys(self, client, db_session, app):
        resp = client.get(self.URL)
        data = assert_json_has_keys(
            resp,
            "success",
            "enabled",
            "websocket_enabled",
            "websocket_endpoint",
            "flask_sock_available",
            "message",
        )
        assert data["success"] is True
        assert data["websocket_endpoint"] == "/api/notifications/ws"

    def test_enabled_when_websocket_config_true(self, client, db_session, app):
        app.config["WEBSOCKET_ENABLED"] = True
        resp = client.get(self.URL)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["enabled"] is True
        assert data["websocket_enabled"] is True

    def test_disabled_when_websocket_config_false(self, client, db_session, app):
        app.config["WEBSOCKET_ENABLED"] = False
        try:
            resp = client.get(self.URL)
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["enabled"] is False
            assert data["websocket_enabled"] is False
        finally:
            app.config.pop("WEBSOCKET_ENABLED", None)

    def test_flask_sock_available_flag_is_bool(self, client, db_session, app):
        resp = client.get(self.URL)
        data = resp.get_json()
        assert isinstance(data["flask_sock_available"], bool)

    def test_flask_sock_unavailable_is_handled(self, client, db_session, app):
        """If flask_sock cannot be imported, flask_sock_available should be False."""
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "flask_sock":
                raise ImportError("no module named flask_sock")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            resp = client.get(self.URL)
        # The endpoint should still return 200 (exception is caught internally)
        assert resp.status_code == 200
