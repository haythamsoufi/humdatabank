"""Unit tests for admin Communication Center routes."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestAdminCommunicationRoutes:
    def test_communication_center_requires_login(self, client):
        resp = client.get("/admin/communication/center", follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_old_notifications_center_url_removed(self, client):
        resp = client.get("/admin/notifications/center", follow_redirects=False)
        assert resp.status_code == 404

    def test_api_send_notifications_email_only_logs_per_recipient(self, logged_in_client):
        recipient_id = 99
        mock_notification = MagicMock()
        mock_notification.id = 501
        mock_notification.user_id = recipient_id
        mock_log = MagicMock(id=9001)

        with patch('app.routes.admin.communication.enforce_api_or_csrf_protection'), \
             patch('app.routes.admin.communication.create_notification', return_value=[{'user_id': recipient_id}]), \
             patch('app.routes.admin.communication._latest_admin_notifications_by_user', return_value={recipient_id: mock_notification}), \
             patch('app.routes.admin.communication.send_email_message', return_value=True), \
             patch('app.routes.admin.communication.log_email_attempt', return_value=mock_log) as mock_log_attempt, \
             patch('app.routes.admin.communication.mark_email_sent') as mock_mark_sent, \
             patch('app.routes.admin.communication.User') as mock_user_model:
            mock_user = MagicMock()
            mock_user.email = 'comm_user@test.com'
            mock_user_model.query.get.return_value = mock_user

            resp = logged_in_client.post(
                '/admin/api/notifications/send',
                json={
                    'user_ids': [recipient_id],
                    'title': 'Email only test',
                    'message': 'Hello from communication center',
                    'send_email': True,
                    'send_push': False,
                    'priority': 'normal',
                },
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        mock_log_attempt.assert_called_once_with(501, recipient_id, 'comm_user@test.com', 'Email only test')
        mock_mark_sent.assert_called_once_with(9001)
