"""Integration tests for /api/mobile/v1/notifications/* endpoints."""
import pytest
from unittest.mock import patch, MagicMock
from tests.api.mobile.helpers import assert_mobile_ok, assert_mobile_paginated, assert_mobile_error

PREFIX = '/api/mobile/v1'


@pytest.mark.api
@pytest.mark.integration
class TestNotificationRoutes:
    def test_list_requires_auth(self, client, db_session):
        assert client.get(f'{PREFIX}/notifications').status_code == 401

    @patch('app.services.notification.service.NotificationService.get_notifications')
    def test_list_notifications(self, mock_get, client, jwt_headers, db_session):
        mock_get.return_value = {'notifications': [{'id': 1, 'title': 'Hi'}], 'total': 1}
        resp = client.get(f'{PREFIX}/notifications', headers=jwt_headers)
        assert_mobile_paginated(resp)

    @patch('app.services.notification.service.NotificationService.get_unread_count')
    def test_count(self, mock_count, client, jwt_headers, db_session):
        mock_count.return_value = 5
        resp = client.get(f'{PREFIX}/notifications/count', headers=jwt_headers)
        assert_mobile_ok(resp, has_data=True)
        assert resp.get_json()['data']['unread_count'] == 5

    @patch('app.services.notification.service.NotificationService.mark_all_as_read')
    def test_mark_all_read(self, mock_mark, client, jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/notifications/mark-read', headers=jwt_headers,
                           json={'mark_all': True})
        assert_mobile_ok(resp)

    def test_mark_read_missing_ids(self, client, jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/notifications/mark-read', headers=jwt_headers, json={})
        assert resp.status_code == 400

    @patch('app.services.notification.service.NotificationService.mark_as_unread')
    def test_mark_unread(self, mock_mark, client, jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/notifications/mark-unread', headers=jwt_headers,
                           json={'notification_ids': [1, 2]})
        assert_mobile_ok(resp)

    def test_mark_unread_missing_ids(self, client, jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/notifications/mark-unread', headers=jwt_headers, json={})
        assert resp.status_code == 400

    @patch('app.services.notification.service.NotificationService.get_notification_preferences')
    def test_get_preferences(self, mock_prefs, client, jwt_headers, db_session):
        prefs = MagicMock()
        prefs.email_notifications = True
        prefs.notification_frequency = 'daily'
        prefs.sound_enabled = True
        prefs.push_notifications = True
        prefs.notification_types_enabled = ['info']
        prefs.push_notification_types_enabled = ['info']
        prefs.digest_day = 'monday'
        prefs.digest_time = '09:00'
        prefs.timezone = 'UTC'
        mock_prefs.return_value = prefs
        resp = client.get(f'{PREFIX}/notifications/preferences', headers=jwt_headers)
        assert_mobile_ok(resp, has_data=True)
        assert 'preferences' in resp.get_json()['data']

    @patch('app.services.notification.service.NotificationService.update_notification_preferences')
    def test_update_preferences(self, mock_update, client, jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/notifications/preferences', headers=jwt_headers,
                           json={'sound_enabled': False})
        assert_mobile_ok(resp)
