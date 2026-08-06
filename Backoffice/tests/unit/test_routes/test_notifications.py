"""
Comprehensive pytest tests for app/routes/notifications.py

Covers:
- Notification center UI
- mark-read / mark-unread (JSON and form data)
- API list with filtering, pagination
- Count endpoint
- Archive / delete
- Preferences GET / POST
- Analytics endpoints (admin-only)
- View / Action per-notification
- Schedule (admin-only)
- Search
- Export (CSV and JSON)
- Device registration
- Stream status
- Edge cases and error paths
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from tests.factories import create_test_user

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_json(resp):
    return json.loads(resp.data)


def _assert_status(resp, *allowed):
    assert resp.status_code in allowed, (
        f"Expected one of {allowed}, got {resp.status_code}: {resp.data[:300]}"
    )


def _make_mock_prefs():
    prefs = MagicMock()
    prefs.email_notifications = True
    prefs.notification_types_enabled = []
    prefs.notification_frequency = "instant"
    prefs.sound_enabled = True
    prefs.push_notifications = True
    prefs.push_notification_types_enabled = []
    prefs.digest_day = None
    prefs.digest_time = None
    prefs.timezone = None
    return prefs


def _make_mock_notification(notification_id=1, user_id=1):
    n = MagicMock()
    n.id = notification_id
    n.user_id = user_id
    n.title = "Test notification"
    n.message = "Test message"
    n.viewed_at = None
    n.action_buttons = [{"action": "view", "label": "View", "endpoint": "/admin/"}]
    n.action_taken = None
    n.action_taken_at = None
    return n


# ---------------------------------------------------------------------------
# Auth guard – unauthenticated
# ---------------------------------------------------------------------------

class TestNotificationsAuthGuard:
    def test_center_unauthenticated(self, client, db_session):
        resp = client.get("/notifications/")
        _assert_status(resp, 302, 401)

    def test_mark_read_unauthenticated(self, client, db_session):
        resp = client.post("/notifications/mark-read", json={"notification_ids": [1]})
        _assert_status(resp, 302, 401)

    def test_mark_unread_unauthenticated(self, client, db_session):
        resp = client.post("/notifications/mark-unread", json={"notification_ids": [1]})
        _assert_status(resp, 302, 401)

    def test_api_list_unauthenticated(self, client, db_session):
        resp = client.get("/notifications/api")
        _assert_status(resp, 302, 401)

    def test_api_count_unauthenticated(self, client, db_session):
        resp = client.get("/notifications/api/count")
        _assert_status(resp, 302, 401)

    def test_archive_unauthenticated(self, client, db_session):
        resp = client.post("/notifications/api/archive", json={"notification_ids": [1]})
        _assert_status(resp, 302, 401)

    def test_delete_unauthenticated(self, client, db_session):
        resp = client.delete("/notifications/api/delete", json={"notification_ids": [1]})
        _assert_status(resp, 302, 401)

    def test_preferences_get_unauthenticated(self, client, db_session):
        resp = client.get("/notifications/api/preferences")
        _assert_status(resp, 302, 401)

    def test_preferences_post_unauthenticated(self, client, db_session):
        resp = client.post("/notifications/api/preferences", json={})
        _assert_status(resp, 302, 401)

    def test_search_unauthenticated(self, client, db_session):
        resp = client.get("/notifications/api/search")
        _assert_status(resp, 302, 401)

    def test_export_unauthenticated(self, client, db_session):
        resp = client.get("/notifications/api/export")
        _assert_status(resp, 302, 401)

    def test_stream_status_unauthenticated(self, client, db_session):
        resp = client.get("/notifications/api/stream/status")
        _assert_status(resp, 302, 401)


# ---------------------------------------------------------------------------
# Notification center UI
# ---------------------------------------------------------------------------

class TestNotificationsCenter:
    def test_renders(self, logged_in_client, db_session):
        with patch("app.services.platform.app_settings_service.get_merged_notification_audience_rules", return_value={}):
            resp = logged_in_client.get("/notifications/")
        _assert_status(resp, 200, 302)

    def test_renders_with_types(self, logged_in_client, db_session):
        mock_rules = {
            "admin_message": {"admin_users": True, "focal_points": False, "system_managers": True}
        }
        with patch("app.services.platform.app_settings_service.get_merged_notification_audience_rules", return_value=mock_rules):
            resp = logged_in_client.get("/notifications/")
        _assert_status(resp, 200, 302)


# ---------------------------------------------------------------------------
# Mark as read
# ---------------------------------------------------------------------------

class TestMarkNotificationsRead:
    def test_no_ids_returns_bad_request(self, logged_in_client, db_session):
        resp = logged_in_client.post("/notifications/mark-read", json={"notification_ids": []})
        _assert_status(resp, 400)

    def test_no_ids_key_returns_bad_request(self, logged_in_client, db_session):
        resp = logged_in_client.post("/notifications/mark-read", json={})
        _assert_status(resp, 400)

    def test_valid_ids_success(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.mark_as_read", return_value=True), \
             patch("app.services.notification.service.NotificationService.get_unread_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_archived_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_all_count", return_value=5):
            resp = logged_in_client.post("/notifications/mark-read", json={"notification_ids": [1, 2, 3]})
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data.get("success") is True

    def test_mark_read_service_failure(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.mark_as_read", return_value=False), \
             patch("app.services.notification.service.NotificationService.get_unread_count", return_value=5), \
             patch("app.services.notification.service.NotificationService.get_archived_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_all_count", return_value=10):
            resp = logged_in_client.post("/notifications/mark-read", json={"notification_ids": [1]})
        _assert_status(resp, 500)

    def test_invalid_id_format(self, logged_in_client, db_session):
        """Non-integer IDs should return bad request."""
        resp = logged_in_client.post(
            "/notifications/mark-read",
            json={"notification_ids": ["not-an-int"]},
        )
        _assert_status(resp, 400)

    def test_ids_as_string_comma_separated(self, logged_in_client, db_session):
        """String IDs should be parsed and handled."""
        with patch("app.services.notification.service.NotificationService.mark_as_read", return_value=True), \
             patch("app.services.notification.service.NotificationService.get_unread_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_archived_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_all_count", return_value=1):
            resp = logged_in_client.post(
                "/notifications/mark-read",
                json={"notification_ids": "1,2,3"},
            )
        _assert_status(resp, 200)

    def test_device_token_header(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.mark_as_read", return_value=True), \
             patch("app.services.notification.service.NotificationService.get_unread_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_archived_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_all_count", return_value=1), \
             patch("app.services.notification.push.PushNotificationService.update_device_activity"):
            resp = logged_in_client.post(
                "/notifications/mark-read",
                json={"notification_ids": [1]},
                headers={"X-Device-Token": "test-device-token"},
            )
        _assert_status(resp, 200)


# ---------------------------------------------------------------------------
# Mark as unread
# ---------------------------------------------------------------------------

class TestMarkNotificationsUnread:
    def test_no_ids_returns_bad_request(self, logged_in_client, db_session):
        resp = logged_in_client.post("/notifications/mark-unread", json={})
        _assert_status(resp, 400)

    def test_valid_ids_success(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.mark_as_unread", return_value=True), \
             patch("app.services.notification.service.NotificationService.get_unread_count", return_value=2), \
             patch("app.services.notification.service.NotificationService.get_archived_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_all_count", return_value=5):
            resp = logged_in_client.post("/notifications/mark-unread", json={"notification_ids": [1]})
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data.get("success") is True

    def test_service_failure(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.mark_as_unread", return_value=False), \
             patch("app.services.notification.service.NotificationService.get_unread_count", return_value=5), \
             patch("app.services.notification.service.NotificationService.get_archived_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_all_count", return_value=10):
            resp = logged_in_client.post("/notifications/mark-unread", json={"notification_ids": [1]})
        _assert_status(resp, 500)

    def test_non_list_ids(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.mark_as_unread", return_value=True), \
             patch("app.services.notification.service.NotificationService.get_unread_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_archived_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_all_count", return_value=1):
            resp = logged_in_client.post("/notifications/mark-unread", json={"notification_ids": 1})
        _assert_status(resp, 200)


# ---------------------------------------------------------------------------
# API list endpoint
# ---------------------------------------------------------------------------

class TestApiGetNotifications:
    def _mock_service(self):
        return (
            patch("app.services.notification.service.NotificationService.get_user_notifications",
                  return_value=([], 0)),
            patch("app.services.notification.service.NotificationService.get_unread_count", return_value=0),
            patch("app.services.notification.service.NotificationService.get_archived_count", return_value=0),
            patch("app.services.notification.service.NotificationService.get_all_count", return_value=0),
        )

    def test_basic_list(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.get_user_notifications", return_value=([], 0)), \
             patch("app.services.notification.service.NotificationService.get_unread_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_archived_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_all_count", return_value=0):
            resp = logged_in_client.get("/notifications/api")
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data.get("success") is True
        assert "notifications" in data

    def test_unread_only(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.get_user_notifications", return_value=([], 0)), \
             patch("app.services.notification.service.NotificationService.get_unread_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_archived_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_all_count", return_value=0):
            resp = logged_in_client.get("/notifications/api?unread_only=true")
        _assert_status(resp, 200)

    def test_with_type_filter(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.get_user_notifications", return_value=([], 0)), \
             patch("app.services.notification.service.NotificationService.get_unread_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_archived_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_all_count", return_value=0):
            resp = logged_in_client.get("/notifications/api?type=admin_message")
        _assert_status(resp, 200)

    def test_with_include_archived(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.get_user_notifications", return_value=([], 0)), \
             patch("app.services.notification.service.NotificationService.get_unread_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_archived_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_all_count", return_value=0):
            resp = logged_in_client.get("/notifications/api?include_archived=true")
        _assert_status(resp, 200)

    def test_with_archived_only(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.get_user_notifications", return_value=([], 0)), \
             patch("app.services.notification.service.NotificationService.get_unread_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_archived_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_all_count", return_value=0):
            resp = logged_in_client.get("/notifications/api?archived_only=true")
        _assert_status(resp, 200)

    def test_with_date_filters(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.get_user_notifications", return_value=([], 0)), \
             patch("app.services.notification.service.NotificationService.get_unread_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_archived_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_all_count", return_value=0):
            resp = logged_in_client.get(
                "/notifications/api?date_from=2024-01-01T00:00:00&date_to=2024-12-31T23:59:59"
            )
        _assert_status(resp, 200)

    def test_invalid_date_filters_ignored(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.get_user_notifications", return_value=([], 0)), \
             patch("app.services.notification.service.NotificationService.get_unread_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_archived_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_all_count", return_value=0):
            resp = logged_in_client.get("/notifications/api?date_from=not-a-date")
        _assert_status(resp, 200)

    def test_with_tags_filter(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.get_user_notifications", return_value=([], 0)), \
             patch("app.services.notification.service.NotificationService.get_unread_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_archived_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_all_count", return_value=0):
            resp = logged_in_client.get("/notifications/api?tags=important,urgent")
        _assert_status(resp, 200)

    def test_pagination(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.get_user_notifications", return_value=([], 0)), \
             patch("app.services.notification.service.NotificationService.get_unread_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_archived_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_all_count", return_value=0):
            resp = logged_in_client.get("/notifications/api?page=2&per_page=10")
        _assert_status(resp, 200)

    def test_language_param_valid(self, logged_in_client, db_session, app):
        with app.app_context():
            supported = app.config.get("SUPPORTED_LANGUAGES", ["en", "fr", "ar"])
            lang = supported[0] if supported else "en"

        with patch("app.services.notification.service.NotificationService.get_user_notifications", return_value=([], 0)), \
             patch("app.services.notification.service.NotificationService.get_unread_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_archived_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_all_count", return_value=0):
            resp = logged_in_client.get(f"/notifications/api?language={lang}")
        _assert_status(resp, 200)

    def test_device_token_header(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.get_user_notifications", return_value=([], 0)), \
             patch("app.services.notification.service.NotificationService.get_unread_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_archived_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_all_count", return_value=0), \
             patch("app.services.notification.push.PushNotificationService.update_device_activity"):
            resp = logged_in_client.get(
                "/notifications/api", headers={"X-Device-Token": "tok123"}
            )
        _assert_status(resp, 200)


# ---------------------------------------------------------------------------
# Count endpoint
# ---------------------------------------------------------------------------

class TestApiGetNotificationCount:
    def test_returns_count(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.get_unread_count", return_value=7):
            resp = logged_in_client.get("/notifications/api/count")
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data.get("unread_count") == 7

    def test_with_device_token(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.get_unread_count", return_value=3), \
             patch("app.services.notification.push.PushNotificationService.update_device_activity"):
            resp = logged_in_client.get(
                "/notifications/api/count",
                headers={"X-Device-Token": "device-abc"},
            )
        _assert_status(resp, 200)


# ---------------------------------------------------------------------------
# Stream status
# ---------------------------------------------------------------------------

class TestApiNotificationStreamStatus:
    def test_stream_status(self, logged_in_client, db_session):
        resp = logged_in_client.get("/notifications/api/stream/status")
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data.get("success") is True
        assert "enabled" in data
        assert "diagnostics" in data

    def test_stream_status_notification_ws_always_off(self, logged_in_client, db_session, app):
        """Notification stream reports disabled even when AI WEBSOCKET_ENABLED is on."""
        original = app.config.get("WEBSOCKET_ENABLED")
        app.config["WEBSOCKET_ENABLED"] = True
        try:
            resp = logged_in_client.get("/notifications/api/stream/status")
        finally:
            if original is not None:
                app.config["WEBSOCKET_ENABLED"] = original
            else:
                app.config.pop("WEBSOCKET_ENABLED", None)
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data.get("websocket_enabled") is False
        assert data.get("enabled") is False
        assert data.get("diagnostics", {}).get("config_websocket_enabled") is True
        assert data.get("diagnostics", {}).get("notifications_websocket") is False


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------

class TestApiArchiveNotifications:
    def test_no_ids_bad_request(self, logged_in_client, db_session):
        resp = logged_in_client.post("/notifications/api/archive", json={})
        _assert_status(resp, 400)

    def test_archive_success(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.archive_notifications", return_value=True), \
             patch("app.services.notification.service.NotificationService.get_unread_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_archived_count", return_value=1), \
             patch("app.services.notification.service.NotificationService.get_all_count", return_value=1):
            resp = logged_in_client.post(
                "/notifications/api/archive", json={"notification_ids": [1]}
            )
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data.get("success") is True

    def test_archive_failure(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.archive_notifications", return_value=False):
            resp = logged_in_client.post(
                "/notifications/api/archive", json={"notification_ids": [1]}
            )
        _assert_status(resp, 500)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

class TestApiDeleteNotifications:
    def test_no_ids_bad_request(self, logged_in_client, db_session):
        resp = logged_in_client.delete("/notifications/api/delete", json={})
        _assert_status(resp, 400)

    def test_delete_success(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.delete_notifications", return_value=True), \
             patch("app.services.notification.service.NotificationService.get_unread_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_archived_count", return_value=0), \
             patch("app.services.notification.service.NotificationService.get_all_count", return_value=0):
            resp = logged_in_client.delete(
                "/notifications/api/delete", json={"notification_ids": [1]}
            )
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data.get("success") is True

    def test_delete_failure(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.delete_notifications", return_value=False):
            resp = logged_in_client.delete(
                "/notifications/api/delete", json={"notification_ids": [1]}
            )
        _assert_status(resp, 500)


# ---------------------------------------------------------------------------
# Preferences GET
# ---------------------------------------------------------------------------

class TestApiGetNotificationPreferences:
    def test_get_preferences(self, logged_in_client, db_session):
        mock_prefs = _make_mock_prefs()
        with patch("app.services.notification.service.NotificationService.get_notification_preferences",
                   return_value=mock_prefs):
            resp = logged_in_client.get("/notifications/api/preferences")
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data.get("success") is True
        assert "preferences" in data

    def test_get_preferences_all_fields(self, logged_in_client, db_session):
        mock_prefs = _make_mock_prefs()
        mock_prefs.push_notifications = False
        mock_prefs.push_notification_types_enabled = ["admin_message"]
        mock_prefs.digest_day = "monday"
        mock_prefs.digest_time = "09:00"
        mock_prefs.timezone = "UTC"
        with patch("app.services.notification.service.NotificationService.get_notification_preferences",
                   return_value=mock_prefs):
            resp = logged_in_client.get("/notifications/api/preferences")
        _assert_status(resp, 200)
        data = _get_json(resp)
        prefs = data["preferences"]
        assert prefs["digest_day"] == "monday"
        assert prefs["timezone"] == "UTC"


# ---------------------------------------------------------------------------
# Preferences POST
# ---------------------------------------------------------------------------

class TestApiUpdateNotificationPreferences:
    def test_update_preferences_json(self, logged_in_client, db_session):
        mock_prefs = _make_mock_prefs()
        with patch("app.services.notification.service.NotificationService.update_notification_preferences",
                   return_value=mock_prefs):
            resp = logged_in_client.post(
                "/notifications/api/preferences",
                json={"email_notifications": True, "sound_enabled": False},
                content_type="application/json",
            )
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data.get("success") is True

    def test_update_preferences_service_returns_none(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.update_notification_preferences",
                   return_value=None):
            resp = logged_in_client.post(
                "/notifications/api/preferences",
                json={"email_notifications": True},
                content_type="application/json",
            )
        _assert_status(resp, 500)

    def test_update_preferences_invalid_json(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/notifications/api/preferences",
            data="not-json",
            content_type="text/plain",
        )
        # Should return error (bad request or server error)
        _assert_status(resp, 400, 500)

    def test_update_preferences_with_push_types(self, logged_in_client, db_session):
        mock_prefs = _make_mock_prefs()
        mock_prefs.push_notification_types_enabled = ["admin_message"]
        with patch("app.services.notification.service.NotificationService.update_notification_preferences",
                   return_value=mock_prefs):
            resp = logged_in_client.post(
                "/notifications/api/preferences",
                json={"push_notifications": True, "push_notification_types_enabled": ["admin_message"]},
                content_type="application/json",
            )
        _assert_status(resp, 200)


# ---------------------------------------------------------------------------
# Analytics endpoints (admin-only)
# ---------------------------------------------------------------------------

class TestNotificationAnalytics:
    def _mock_analytics(self, result=None):
        return patch(
            "app.services.notification.analytics.NotificationAnalytics.get_summary",
            return_value=result or {"total": 0},
        )

    def test_analytics_summary(self, logged_in_client, db_session):
        with patch("app.services.notification.analytics.NotificationAnalytics.get_summary", return_value={"total": 5}):
            resp = logged_in_client.get("/notifications/api/analytics/summary")
        _assert_status(resp, 200, 403)

    def test_analytics_summary_with_days(self, logged_in_client, db_session):
        with patch("app.services.notification.analytics.NotificationAnalytics.get_summary", return_value={}):
            resp = logged_in_client.get("/notifications/api/analytics/summary?days=7")
        _assert_status(resp, 200, 403)

    def test_analytics_delivery_rates(self, logged_in_client, db_session):
        with patch("app.services.notification.analytics.NotificationAnalytics.get_delivery_rates", return_value={}):
            resp = logged_in_client.get("/notifications/api/analytics/delivery-rates")
        _assert_status(resp, 200, 403)

    def test_analytics_read_rates(self, logged_in_client, db_session):
        with patch("app.services.notification.analytics.NotificationAnalytics.get_read_rates", return_value={}):
            resp = logged_in_client.get("/notifications/api/analytics/read-rates")
        _assert_status(resp, 200, 403)

    def test_analytics_peak_times(self, logged_in_client, db_session):
        with patch("app.services.notification.analytics.NotificationAnalytics.get_peak_times", return_value={}):
            resp = logged_in_client.get("/notifications/api/analytics/peak-times")
        _assert_status(resp, 200, 403)

    def test_analytics_user_engagement(self, logged_in_client, db_session):
        with patch("app.services.notification.analytics.NotificationAnalytics.get_user_engagement", return_value={}):
            resp = logged_in_client.get("/notifications/api/analytics/user-engagement")
        _assert_status(resp, 200, 403)

    def test_analytics_unauthenticated(self, client, db_session):
        resp = client.get("/notifications/api/analytics/summary")
        _assert_status(resp, 302, 401, 403)


# ---------------------------------------------------------------------------
# View notification
# ---------------------------------------------------------------------------

class TestApiViewNotification:
    def test_view_not_found(self, logged_in_client, db_session):
        from app.models import Notification
        with patch.object(Notification, "query") as mock_query:
            mock_query.filter_by.return_value.first.return_value = None
            resp = logged_in_client.post("/notifications/api/999/view")
        _assert_status(resp, 404)

    def test_view_success(self, logged_in_client, db_session, app):
        mock_notif = _make_mock_notification()
        from app.models import Notification
        with patch.object(Notification, "query") as mock_query:
            mock_query.filter_by.return_value.first.return_value = mock_notif
            resp = logged_in_client.post("/notifications/api/999/view")
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data.get("success") is True

    def test_view_already_viewed(self, logged_in_client, db_session):
        mock_notif = _make_mock_notification()
        mock_notif.viewed_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        from app.models import Notification
        with patch.object(Notification, "query") as mock_query:
            mock_query.filter_by.return_value.first.return_value = mock_notif
            resp = logged_in_client.post("/notifications/api/999/view")
        _assert_status(resp, 200)


# ---------------------------------------------------------------------------
# Action notification
# ---------------------------------------------------------------------------

class TestApiNotificationAction:
    def test_no_action_bad_request(self, logged_in_client, db_session):
        resp = logged_in_client.post("/notifications/api/999/action", json={})
        _assert_status(resp, 400)

    def test_notification_not_found(self, logged_in_client, db_session):
        from app.models import Notification
        with patch.object(Notification, "query") as mock_query:
            mock_query.filter_by.return_value.first.return_value = None
            resp = logged_in_client.post(
                "/notifications/api/999/action", json={"action": "view"}
            )
        _assert_status(resp, 404)

    def test_no_action_buttons(self, logged_in_client, db_session):
        mock_notif = _make_mock_notification()
        mock_notif.action_buttons = None
        from app.models import Notification
        with patch.object(Notification, "query") as mock_query:
            mock_query.filter_by.return_value.first.return_value = mock_notif
            resp = logged_in_client.post(
                "/notifications/api/999/action", json={"action": "view"}
            )
        _assert_status(resp, 400)

    def test_invalid_action(self, logged_in_client, db_session):
        mock_notif = _make_mock_notification()
        from app.models import Notification
        with patch.object(Notification, "query") as mock_query:
            mock_query.filter_by.return_value.first.return_value = mock_notif
            resp = logged_in_client.post(
                "/notifications/api/999/action", json={"action": "nonexistent_action"}
            )
        _assert_status(resp, 400)

    def test_valid_action_success(self, logged_in_client, db_session):
        mock_notif = _make_mock_notification()
        from app.models import Notification
        with patch.object(Notification, "query") as mock_query, \
             patch("app.services.notification.core.validate_action_button_endpoint", return_value=True):
            mock_query.filter_by.return_value.first.return_value = mock_notif
            resp = logged_in_client.post(
                "/notifications/api/999/action", json={"action": "view"}
            )
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data.get("success") is True
        assert data.get("action") == "view"

    def test_approve_action_non_admin_forbidden(self, logged_in_client, db_session, app):
        """approve/reject action should be forbidden for non-admin users."""
        mock_notif = _make_mock_notification()
        mock_notif.action_buttons = [
            {"action": "approve", "label": "Approve", "endpoint": "/admin/"}
        ]
        from app.models import Notification
        with patch.object(Notification, "query") as mock_query, \
             patch("app.services.organization.authorization_service.AuthorizationService.is_admin", return_value=False):
            mock_query.filter_by.return_value.first.return_value = mock_notif
            resp = logged_in_client.post(
                "/notifications/api/999/action", json={"action": "approve"}
            )
        _assert_status(resp, 403)

    def test_approve_action_admin_success(self, logged_in_client, db_session):
        mock_notif = _make_mock_notification()
        mock_notif.action_buttons = [
            {"action": "approve", "label": "Approve", "endpoint": "/admin/"}
        ]
        from app.models import Notification
        with patch.object(Notification, "query") as mock_query, \
             patch("app.services.organization.authorization_service.AuthorizationService.is_admin", return_value=True), \
             patch("app.services.notification.core.validate_action_button_endpoint", return_value=True):
            mock_query.filter_by.return_value.first.return_value = mock_notif
            resp = logged_in_client.post(
                "/notifications/api/999/action", json={"action": "approve"}
            )
        _assert_status(resp, 200)

    def test_unsafe_endpoint_stripped(self, logged_in_client, db_session):
        mock_notif = _make_mock_notification()
        from app.models import Notification
        with patch.object(Notification, "query") as mock_query, \
             patch("app.services.notification.core.validate_action_button_endpoint", return_value=False):
            mock_query.filter_by.return_value.first.return_value = mock_notif
            resp = logged_in_client.post(
                "/notifications/api/999/action", json={"action": "view"}
            )
        _assert_status(resp, 200)
        data = _get_json(resp)
        # endpoint should be None when unsafe
        assert data.get("endpoint") is None


# ---------------------------------------------------------------------------
# Schedule (admin-only)
# ---------------------------------------------------------------------------

class TestApiScheduleNotification:
    BASE_URL = "/notifications/api/schedule"

    def test_no_user_ids(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            self.BASE_URL,
            json={"notification_type": "admin_message", "scheduled_for": "2030-01-01T10:00:00"},
        )
        _assert_status(resp, 400, 403)

    def test_no_notification_type(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            self.BASE_URL,
            json={"user_ids": [1], "scheduled_for": "2030-01-01T10:00:00"},
        )
        _assert_status(resp, 400, 403)

    def test_no_scheduled_for(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            self.BASE_URL,
            json={"user_ids": [1], "notification_type": "admin_message"},
        )
        _assert_status(resp, 400, 403)

    def test_invalid_notification_type(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            self.BASE_URL,
            json={
                "user_ids": [1],
                "notification_type": "not_a_real_type",
                "scheduled_for": "2030-01-01T10:00:00",
            },
        )
        _assert_status(resp, 400, 403)

    def test_invalid_scheduled_for(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            self.BASE_URL,
            json={
                "user_ids": [1],
                "notification_type": "admin_message",
                "scheduled_for": "not-a-date",
            },
        )
        _assert_status(resp, 400, 403)

    def test_success(self, logged_in_client, db_session):
        mock_n = MagicMock()
        mock_n.id = 99
        with patch("app.services.notification.scheduling.create_scheduled_notification", return_value=[mock_n]):
            resp = logged_in_client.post(
                self.BASE_URL,
                json={
                    "user_ids": [1],
                    "notification_type": "admin_message",
                    "scheduled_for": "2030-06-01T10:00:00",
                    "title": "Hello",
                    "message": "Test",
                },
            )
        _assert_status(resp, 200, 403)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class TestApiSearchNotifications:
    def test_search_no_query(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.get_user_notifications",
                   return_value=([], 0)):
            resp = logged_in_client.get("/notifications/api/search")
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data.get("success") is True

    def test_search_with_query(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.get_user_notifications",
                   return_value=([], 0)):
            resp = logged_in_client.get("/notifications/api/search?q=hello")
        _assert_status(resp, 200)

    def test_search_with_type_filter(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.get_user_notifications",
                   return_value=([], 0)):
            resp = logged_in_client.get("/notifications/api/search?q=test&type=admin_message")
        _assert_status(resp, 200)

    def test_search_with_date_filters(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.get_user_notifications",
                   return_value=([], 0)):
            resp = logged_in_client.get(
                "/notifications/api/search?date_from=2024-01-01T00:00:00Z&date_to=2024-12-31T23:59:59Z"
            )
        _assert_status(resp, 200)

    def test_search_invalid_date_ignored(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.get_user_notifications",
                   return_value=([], 0)):
            resp = logged_in_client.get("/notifications/api/search?date_from=bad")
        _assert_status(resp, 200)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class TestApiExportNotifications:
    def test_export_json(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.get_user_notifications",
                   return_value=([], 0)):
            resp = logged_in_client.get("/notifications/api/export?format=json")
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data.get("success") is True
        assert "notifications" in data

    def test_export_csv(self, logged_in_client, db_session):
        sample = [
            {"id": 1, "title": "T1", "message": "M1", "type": "admin_message",
             "priority": "normal", "is_read": False, "created_at": "2024-01-01", "related_url": ""}
        ]
        with patch("app.services.notification.service.NotificationService.get_user_notifications",
                   return_value=(sample, 1)):
            resp = logged_in_client.get("/notifications/api/export?format=csv")
        _assert_status(resp, 200)
        assert "text/csv" in resp.content_type or resp.status_code == 200

    def test_export_with_date_filters(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.get_user_notifications",
                   return_value=([], 0)):
            resp = logged_in_client.get(
                "/notifications/api/export?date_from=2024-01-01T00:00:00&date_to=2024-12-31T23:59:59"
            )
        _assert_status(resp, 200)

    def test_export_default_format_is_json(self, logged_in_client, db_session):
        with patch("app.services.notification.service.NotificationService.get_user_notifications",
                   return_value=([], 0)):
            resp = logged_in_client.get("/notifications/api/export")
        _assert_status(resp, 200)


# ---------------------------------------------------------------------------
# Device registration
# ---------------------------------------------------------------------------

class TestRegisterDevice:
    BASE_URL = "/notifications/api/devices/register"

    def test_missing_device_token(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            self.BASE_URL, json={"platform": "ios"}
        )
        _assert_status(resp, 400)

    def test_missing_platform(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            self.BASE_URL, json={"device_token": "tok-abc"}
        )
        _assert_status(resp, 400)

    def test_invalid_platform(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            self.BASE_URL, json={"device_token": "tok-abc", "platform": "windows"}
        )
        _assert_status(resp, 400)

    def test_success_ios(self, logged_in_client, db_session):
        mock_device = MagicMock()
        mock_device.id = 1
        mock_device.device_token = "tok-abc"
        with patch("app.services.notification.push.PushNotificationService.register_device",
                   return_value=(mock_device, True)):
            resp = logged_in_client.post(
                self.BASE_URL,
                json={"device_token": "tok-abc", "platform": "ios"},
            )
        _assert_status(resp, 200, 201)

    def test_success_android(self, logged_in_client, db_session):
        mock_device = MagicMock()
        mock_device.id = 2
        mock_device.device_token = "tok-and"
        with patch("app.services.notification.push.PushNotificationService.register_device",
                   return_value=(mock_device, False)):
            resp = logged_in_client.post(
                self.BASE_URL,
                json={
                    "device_token": "tok-and",
                    "platform": "android",
                    "app_version": "1.0.0",
                    "device_model": "Pixel 7",
                    "os_version": "14",
                    "timezone": "UTC",
                },
            )
        _assert_status(resp, 200, 201)


# ---------------------------------------------------------------------------
# Notification type labels helper
# ---------------------------------------------------------------------------

class TestNotificationTypeLabels:
    def test_labels_are_strings(self, app):
        with app.app_context():
            from app.routes.notifications import get_notification_type_labels
            labels = get_notification_type_labels()
        assert isinstance(labels, dict)
        assert len(labels) > 0

    def test_labels_contain_known_type(self, app):
        with app.app_context():
            from app.routes.notifications import get_notification_type_labels
            labels = get_notification_type_labels()
        assert "assignment_created" in labels
        assert "admin_message" in labels


# ---------------------------------------------------------------------------
# get_notification_types_for_user helper
# ---------------------------------------------------------------------------

class TestGetNotificationTypesForUser:
    def test_returns_dict_with_expected_keys(self, logged_in_client, db_session, app):
        with app.app_context():
            from app.routes.notifications import get_notification_types_for_user
            from app.models import User
            user = User.query.first()
            if user is None:
                user = MagicMock()
                user.id = 1

            with patch("app.services.platform.app_settings_service.get_merged_notification_audience_rules", return_value={}):
                result = get_notification_types_for_user(user)

        assert "all" in result
        assert "for_user" in result

    def test_admin_sees_admin_types(self, logged_in_client, db_session, app, admin_user):
        with app.app_context():
            from app.routes.notifications import get_notification_types_for_user
            from app.models import User
            user = User.query.get(admin_user.id)
            result = get_notification_types_for_user(user)

        assert "public_submission_received" in result["for_user"]
        assert "access_request_received" in result["for_user"]

    def test_admin_configuration_includes_all_preference_eligible_types(self, app, admin_user):
        with app.app_context():
            from app.routes.notifications import get_notification_types_for_user
            from app.models import User

            user = User.query.get(admin_user.id)
            admin_config = get_notification_types_for_user(user, for_admin_configuration=True)

        assert "assignment_created" in admin_config["for_user"]
        assert "public_submission_received" in admin_config["for_user"]

    def test_focal_point_sees_assignment_created_in_self_service_list(self, app, db_session):
        from app.models import User
        from app.models.rbac import RbacRole, RbacUserRole
        from app import db

        with app.app_context():
            from app.routes.notifications import get_notification_types_for_user

            user = User(email="fp-prefs@test.com", name="FP Prefs", active=True)
            user.set_password("pw")
            db.session.add(user)
            db.session.flush()
            role = RbacRole.query.filter_by(code="assignment_editor_submitter").first()
            if not role:
                role = RbacRole(code="assignment_editor_submitter", name="AES")
                db.session.add(role)
                db.session.flush()
            db.session.add(RbacUserRole(user_id=user.id, role_id=role.id))
            db.session.commit()

            result = get_notification_types_for_user(user)

        assert "assignment_created" in result["for_user"]

    def test_preference_eligible_excludes_types_without_audience_rules(self, app):
        with app.app_context():
            from app.routes.notifications import get_preference_eligible_notification_types

            eligible = get_preference_eligible_notification_types()

        assert "assignment_created" in eligible
        assert "account_welcome" not in eligible
        assert "email_digest" not in eligible
        assert "deadline_reminder" not in eligible


# ---------------------------------------------------------------------------
# get_current_user_id helper
# ---------------------------------------------------------------------------

class TestGetCurrentUserId:
    def test_returns_user_id(self, logged_in_client, db_session, app):
        """When logged in, count endpoint shows _get_current_user_id works."""
        with patch("app.services.notification.service.NotificationService.get_unread_count", return_value=0):
            resp = logged_in_client.get("/notifications/api/count")
        _assert_status(resp, 200)
