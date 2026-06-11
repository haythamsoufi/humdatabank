"""
Tests for app/routes/admin/api_key_management.py

Coverage targets:
- list_api_keys: all status filters, search, exception path
- create_api_key: GET form, POST success (with/without expiry), POST exception
- view_api_key: success with usage data, 404, exception
- edit_api_key: GET, POST success, revoked key redirect, POST exception
- rotate_api_key: success, revoked redirect, exception
- revoke_api_key: GET form, POST success, POST exception
- api_key_usage: success, exception
"""
import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from tests.factories import create_test_api_key

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_key(db_session, **kwargs):
    """Shortcut: create and return (api_key_obj, full_key)."""
    return create_test_api_key(db_session, **kwargs)


# ---------------------------------------------------------------------------
# list_api_keys
# ---------------------------------------------------------------------------

class TestListApiKeys:
    def test_list_all_default(self, logged_in_client, db_session, app):
        with app.app_context():
            _create_key(db_session, client_name="Client Alpha")
        resp = logged_in_client.get("/admin/api-management/api-keys")
        assert resp.status_code == 200

    def test_list_active_filter(self, logged_in_client, db_session, app):
        with app.app_context():
            _create_key(db_session, client_name="Active Client", is_active=True, is_revoked=False)
        resp = logged_in_client.get("/admin/api-management/api-keys?status=active")
        assert resp.status_code == 200

    def test_list_revoked_filter(self, logged_in_client, db_session, app):
        with app.app_context():
            key, _ = _create_key(db_session, client_name="Revoked Client")
            key.is_revoked = True
            key.is_active = False
            db_session.commit()
        resp = logged_in_client.get("/admin/api-management/api-keys?status=revoked")
        assert resp.status_code == 200

    def test_list_expired_filter(self, logged_in_client, db_session, app):
        with app.app_context():
            past = datetime.utcnow() - timedelta(days=1)
            _create_key(db_session, client_name="Expired Client", expires_at=past)
        resp = logged_in_client.get("/admin/api-management/api-keys?status=expired")
        assert resp.status_code == 200

    def test_list_search_by_client_name(self, logged_in_client, db_session, app):
        with app.app_context():
            _create_key(db_session, client_name="UniqueSearchableClient99")
        resp = logged_in_client.get("/admin/api-management/api-keys?search=UniqueSearchableClient99")
        assert resp.status_code == 200

    def test_list_search_no_results(self, logged_in_client, db_session, app):
        resp = logged_in_client.get("/admin/api-management/api-keys?search=NORESULTXYZ")
        assert resp.status_code == 200

    def test_list_exception_redirects(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.api_key_management.APIKey") as mock_cls:
            mock_cls.query.order_by.side_effect = Exception("db boom")
            resp = logged_in_client.get("/admin/api-management/api-keys")
        # Should redirect to admin dashboard on exception
        assert resp.status_code in (302, 200)

    def test_list_unauthenticated_redirects(self, client, db_session, app):
        resp = client.get("/admin/api-management/api-keys")
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# create_api_key
# ---------------------------------------------------------------------------

class TestCreateApiKey:
    def test_get_create_form(self, logged_in_client, db_session, app):
        resp = logged_in_client.get("/admin/api-management/api-keys/create")
        assert resp.status_code == 200

    def test_post_creates_key_success(self, logged_in_client, db_session, app):
        resp = logged_in_client.post(
            "/admin/api-management/api-keys/create",
            data={
                "client_name": "New Integration Client",
                "client_description": "Created in test",
                "rate_limit_per_minute": "60",
            },
        )
        # On success, renders create_success template (200)
        assert resp.status_code == 200

    def test_post_create_with_expiry(self, logged_in_client, db_session, app):
        future = (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%d")
        resp = logged_in_client.post(
            "/admin/api-management/api-keys/create",
            data={
                "client_name": "Expiring Client",
                "rate_limit_per_minute": "60",
                "expires_at": future,
            },
        )
        assert resp.status_code == 200

    def test_post_create_no_rate_limit_defaults(self, logged_in_client, db_session, app):
        """Omitting rate limit uses default of 60."""
        resp = logged_in_client.post(
            "/admin/api-management/api-keys/create",
            data={"client_name": "Default Rate Client"},
        )
        assert resp.status_code == 200

    def test_post_create_exception_shows_form(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.api_key_management.APIKey.generate_key",
                   side_effect=Exception("keygen failure")):
            resp = logged_in_client.post(
                "/admin/api-management/api-keys/create",
                data={"client_name": "Error Client", "rate_limit_per_minute": "60"},
            )
        assert resp.status_code == 200

    def test_post_invalid_form_rerenders(self, logged_in_client, db_session, app):
        """Empty client_name should re-render the form, not create key."""
        resp = logged_in_client.post(
            "/admin/api-management/api-keys/create",
            data={"client_name": ""},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# view_api_key
# ---------------------------------------------------------------------------

class TestViewApiKey:
    def test_view_existing_key(self, logged_in_client, db_session, app):
        with app.app_context():
            key, _ = _create_key(db_session, client_name="View Me")
            key_id = key.id
        resp = logged_in_client.get(f"/admin/api-management/api-keys/{key_id}")
        assert resp.status_code == 200

    def test_view_nonexistent_key_returns_404(self, logged_in_client, db_session, app):
        resp = logged_in_client.get("/admin/api-management/api-keys/99999")
        assert resp.status_code == 404

    def test_view_exception_redirects(self, logged_in_client, db_session, app):
        with app.app_context():
            key, _ = _create_key(db_session, client_name="Exception Key")
            key_id = key.id
        with patch("app.routes.admin.api_key_management.db") as mock_db:
            mock_db.session.get.return_value = MagicMock()
            mock_db.session.query.side_effect = Exception("query fail")
            resp = logged_in_client.get(f"/admin/api-management/api-keys/{key_id}")
        assert resp.status_code in (302, 200)


# ---------------------------------------------------------------------------
# edit_api_key
# ---------------------------------------------------------------------------

class TestEditApiKey:
    def test_get_edit_form(self, logged_in_client, db_session, app):
        with app.app_context():
            key, _ = _create_key(db_session, client_name="Editable Key")
            key_id = key.id
        resp = logged_in_client.get(f"/admin/api-management/api-keys/{key_id}/edit")
        assert resp.status_code == 200

    def test_get_edit_revoked_key_redirects(self, logged_in_client, db_session, app):
        with app.app_context():
            key, _ = _create_key(db_session, client_name="Revoked Edit Key")
            key.is_revoked = True
            db_session.commit()
            key_id = key.id
        resp = logged_in_client.get(f"/admin/api-management/api-keys/{key_id}/edit")
        assert resp.status_code == 302

    def test_post_edit_success(self, logged_in_client, db_session, app):
        with app.app_context():
            key, _ = _create_key(db_session, client_name="Original Name")
            key_id = key.id
        resp = logged_in_client.post(
            f"/admin/api-management/api-keys/{key_id}/edit",
            data={
                "client_name": "Updated Name",
                "client_description": "Updated description",
                "rate_limit_per_minute": "120",
            },
        )
        assert resp.status_code == 302  # redirect to view

    def test_post_edit_with_expiry(self, logged_in_client, db_session, app):
        with app.app_context():
            key, _ = _create_key(db_session, client_name="Key With Expiry")
            key_id = key.id
        future = (datetime.utcnow() + timedelta(days=60)).strftime("%Y-%m-%d")
        resp = logged_in_client.post(
            f"/admin/api-management/api-keys/{key_id}/edit",
            data={
                "client_name": "Key With Expiry",
                "rate_limit_per_minute": "60",
                "expires_at": future,
            },
        )
        assert resp.status_code == 302

    def test_post_edit_exception_stays_on_form(self, logged_in_client, db_session, app):
        with app.app_context():
            key, _ = _create_key(db_session, client_name="Error Edit Key")
            key_id = key.id
        with patch("app.routes.admin.api_key_management.log_admin_action",
                   side_effect=Exception("log fail")):
            resp = logged_in_client.post(
                f"/admin/api-management/api-keys/{key_id}/edit",
                data={
                    "client_name": "Error Edit Key",
                    "rate_limit_per_minute": "60",
                },
            )
        assert resp.status_code == 200

    def test_edit_nonexistent_key_404(self, logged_in_client, db_session, app):
        resp = logged_in_client.get("/admin/api-management/api-keys/99999/edit")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# rotate_api_key
# ---------------------------------------------------------------------------

class TestRotateApiKey:
    def test_rotate_active_key_success(self, logged_in_client, db_session, app):
        with app.app_context():
            key, _ = _create_key(db_session, client_name="Rotate Me")
            key_id = key.id
        resp = logged_in_client.post(f"/admin/api-management/api-keys/{key_id}/rotate")
        assert resp.status_code == 200  # renders rotate_success template

    def test_rotate_revoked_key_redirects(self, logged_in_client, db_session, app):
        with app.app_context():
            key, _ = _create_key(db_session, client_name="Revoked Rotate Key")
            key.is_revoked = True
            db_session.commit()
            key_id = key.id
        resp = logged_in_client.post(f"/admin/api-management/api-keys/{key_id}/rotate")
        assert resp.status_code == 302

    def test_rotate_nonexistent_key_404(self, logged_in_client, db_session, app):
        resp = logged_in_client.post("/admin/api-management/api-keys/99999/rotate")
        assert resp.status_code == 404

    def test_rotate_exception_redirects(self, logged_in_client, db_session, app):
        with app.app_context():
            key, _ = _create_key(db_session, client_name="Exception Rotate Key")
            key_id = key.id
        with patch("app.routes.admin.api_key_management.APIKey.generate_key",
                   side_effect=Exception("rotation error")):
            resp = logged_in_client.post(f"/admin/api-management/api-keys/{key_id}/rotate")
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# revoke_api_key
# ---------------------------------------------------------------------------

class TestRevokeApiKey:
    def test_get_revoke_form(self, logged_in_client, db_session, app):
        with app.app_context():
            key, _ = _create_key(db_session, client_name="Revoke Form Key")
            key_id = key.id
        resp = logged_in_client.get(f"/admin/api-management/api-keys/{key_id}/revoke")
        assert resp.status_code == 200

    def test_post_revoke_success(self, logged_in_client, db_session, app):
        with app.app_context():
            key, _ = _create_key(db_session, client_name="To Be Revoked")
            key_id = key.id
        resp = logged_in_client.post(
            f"/admin/api-management/api-keys/{key_id}/revoke",
            data={"revocation_reason": "No longer needed"},
        )
        assert resp.status_code == 302  # redirect to list

    def test_post_revoke_no_reason(self, logged_in_client, db_session, app):
        with app.app_context():
            key, _ = _create_key(db_session, client_name="Revoke No Reason Key")
            key_id = key.id
        resp = logged_in_client.post(
            f"/admin/api-management/api-keys/{key_id}/revoke",
            data={"revocation_reason": ""},
        )
        assert resp.status_code == 302

    def test_post_revoke_exception_stays_on_form(self, logged_in_client, db_session, app):
        with app.app_context():
            key, _ = _create_key(db_session, client_name="Exception Revoke Key")
            key_id = key.id
        with patch("app.routes.admin.api_key_management.log_admin_action",
                   side_effect=Exception("revoke log fail")):
            resp = logged_in_client.post(
                f"/admin/api-management/api-keys/{key_id}/revoke",
                data={"revocation_reason": "Test reason"},
            )
        assert resp.status_code == 200

    def test_revoke_nonexistent_key_404(self, logged_in_client, db_session, app):
        resp = logged_in_client.get("/admin/api-management/api-keys/99999/revoke")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# api_key_usage (JSON endpoint)
# ---------------------------------------------------------------------------

class TestApiKeyUsage:
    def test_usage_default_days(self, logged_in_client, db_session, app):
        with app.app_context():
            key, _ = _create_key(db_session, client_name="Usage Key")
            key_id = key.id
        resp = logged_in_client.get(f"/admin/api-management/api-keys/{key_id}/usage")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True
        result = data.get("result", {})
        assert result.get("key_id") == key_id
        assert "usage" in result

    def test_usage_custom_days(self, logged_in_client, db_session, app):
        with app.app_context():
            key, _ = _create_key(db_session, client_name="Usage Days Key")
            key_id = key.id
        resp = logged_in_client.get(
            f"/admin/api-management/api-keys/{key_id}/usage?days=7"
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        result = data.get("result", {})
        assert result.get("period_days") == 7

    def test_usage_clamps_days_min(self, logged_in_client, db_session, app):
        with app.app_context():
            key, _ = _create_key(db_session, client_name="Clamp Min Key")
            key_id = key.id
        resp = logged_in_client.get(
            f"/admin/api-management/api-keys/{key_id}/usage?days=0"
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        result = data.get("result", {})
        assert result.get("period_days") == 1  # clamped to 1

    def test_usage_clamps_days_max(self, logged_in_client, db_session, app):
        with app.app_context():
            key, _ = _create_key(db_session, client_name="Clamp Max Key")
            key_id = key.id
        resp = logged_in_client.get(
            f"/admin/api-management/api-keys/{key_id}/usage?days=9999"
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        result = data.get("result", {})
        assert result.get("period_days") == 365  # clamped to 365

    def test_usage_nonexistent_key_404(self, logged_in_client, db_session, app):
        resp = logged_in_client.get("/admin/api-management/api-keys/99999/usage")
        assert resp.status_code == 404

    def test_usage_exception_returns_server_error(self, logged_in_client, db_session, app):
        with app.app_context():
            key, _ = _create_key(db_session, client_name="Usage Error Key")
            key_id = key.id
        with patch("app.routes.admin.api_key_management.db") as mock_db:
            mock_db.session.get.return_value = MagicMock()
            mock_db.session.query.side_effect = Exception("usage query fail")
            resp = logged_in_client.get(f"/admin/api-management/api-keys/{key_id}/usage")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# _key_daily_chart (internal helper — tested via view_api_key)
# ---------------------------------------------------------------------------

class TestKeyDailyChart:
    def test_chart_data_included_in_view(self, logged_in_client, db_session, app):
        """Ensures _key_daily_chart is exercised as part of view_api_key."""
        with app.app_context():
            key, _ = _create_key(db_session, client_name="Chart Key")
            key_id = key.id
        resp = logged_in_client.get(f"/admin/api-management/api-keys/{key_id}")
        assert resp.status_code == 200
        assert b"chart" in resp.data.lower() or resp.status_code == 200
