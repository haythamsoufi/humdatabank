from dataclasses import dataclass
from unittest.mock import patch

import pytest


@dataclass
class _Prefs:
    email_notifications: bool = True
    notification_types_enabled: list[str] = None
    notification_frequency: str = "immediate"
    sound_enabled: bool = True
    push_notifications: bool = True
    push_notification_types_enabled: list[str] = None
    digest_day: str | None = None
    digest_time: str | None = None
    timezone: str | None = "UTC"

    def __post_init__(self):
        if self.notification_types_enabled is None:
            self.notification_types_enabled = ["assignment_created"]
        if self.push_notification_types_enabled is None:
            self.push_notification_types_enabled = ["assignment_created"]


@pytest.mark.integration
class TestNotificationsRoutes:
    def test_notifications_center_requires_login(self, client):
        resp = client.get("/notifications/", follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)
        assert "/login" in (resp.headers.get("Location") or "")

    def test_notifications_api_list_contract(self, logged_in_client):
        with patch("app.routes.notifications.NotificationService.get_user_notifications", return_value=([{"id": 1}], 1)), patch(
            "app.routes.notifications.NotificationService.get_unread_count", return_value=1
        ), patch("app.routes.notifications.NotificationService.get_archived_count", return_value=0), patch(
            "app.routes.notifications.NotificationService.get_all_count", return_value=1
        ):
            resp = logged_in_client.get("/notifications/api?page=1&per_page=20")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert "notifications" in data and isinstance(data["notifications"], list)
            assert "unread_count" in data
            assert "archived_count" in data
            assert "all_count" in data
            assert "page" in data
            assert "per_page" in data
            assert "has_more" in data

    def test_notifications_api_count_contract(self, logged_in_client):
        with patch(
            "app.routes.notifications.NotificationService.get_unread_count",
            return_value=3,
        ):
            resp = logged_in_client.get("/notifications/api/count")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert data["unread_count"] == 3

    def test_mark_read_validation_400_when_missing_ids(self, logged_in_client):
        with patch(
            "app.utils.api_authentication.validate_plaintext_db_api_key_for_mobile_auth",
            return_value=True,
        ):
            resp = logged_in_client.post(
                "/notifications/mark-read",
                json={},
                headers={"X-Mobile-Auth": "db-api-key-plaintext"},
            )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False

    def test_mark_read_happy_path_updates_counts(self, logged_in_client):
        with patch(
            "app.utils.api_authentication.validate_plaintext_db_api_key_for_mobile_auth",
            return_value=True,
        ), patch("app.routes.notifications.NotificationService.mark_as_read", return_value=True), patch(
            "app.routes.notifications.NotificationService.get_unread_count", return_value=0
        ), patch("app.routes.notifications.NotificationService.get_archived_count", return_value=0), patch(
            "app.routes.notifications.NotificationService.get_all_count", return_value=2
        ):
            resp = logged_in_client.post(
                "/notifications/mark-read",
                json={"notification_ids": [1, 2]},
                headers={"X-Mobile-Auth": "db-api-key-plaintext"},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert data["unread_count"] == 0
            assert data["all_count"] == 2

    def test_archive_and_delete_contract(self, logged_in_client):
        with patch("app.routes.notifications.NotificationService.archive_notifications", return_value=True), patch(
            "app.routes.notifications.NotificationService.delete_notifications", return_value=True
        ), patch("app.routes.notifications.NotificationService.get_unread_count", return_value=0), patch(
            "app.routes.notifications.NotificationService.get_archived_count", return_value=0
        ), patch("app.routes.notifications.NotificationService.get_all_count", return_value=0):
            resp = logged_in_client.post("/notifications/api/archive", json={"notification_ids": [1]})
            assert resp.status_code == 200
            assert resp.get_json()["success"] is True

            resp2 = logged_in_client.open(
                "/notifications/api/delete",
                method="DELETE",
                json={"notification_ids": [1]},
            )
            assert resp2.status_code == 200
            assert resp2.get_json()["success"] is True

    def test_preferences_get_and_update_contract(self, logged_in_client):
        prefs = _Prefs()
        updated = _Prefs(email_notifications=False, sound_enabled=False)

        with patch("app.routes.notifications.NotificationService.get_notification_preferences", return_value=prefs), patch(
            "app.routes.notifications.NotificationService.update_notification_preferences", return_value=updated
        ), patch(
            "app.utils.api_authentication.validate_plaintext_db_api_key_for_mobile_auth",
            return_value=True,
        ):
            resp = logged_in_client.get("/notifications/api/preferences")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert "preferences" in data
            assert "email_notifications" in data["preferences"]
            assert "notification_types_enabled" in data["preferences"]

            resp2 = logged_in_client.post(
                "/notifications/api/preferences",
                json={"email_notifications": False, "sound_enabled": False},
                headers={"X-Mobile-Auth": "db-api-key-plaintext"},
            )
            assert resp2.status_code == 200
            data2 = resp2.get_json()
            assert data2["success"] is True
            assert data2["preferences"]["email_notifications"] is False
            assert data2["preferences"]["sound_enabled"] is False

