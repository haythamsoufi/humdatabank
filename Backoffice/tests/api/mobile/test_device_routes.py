"""Integration tests for /api/mobile/v1/devices/* endpoints."""
import pytest
from unittest.mock import patch
from tests.api.mobile.helpers import assert_mobile_ok

PREFIX = '/api/mobile/v1'


@pytest.mark.api
@pytest.mark.integration
class TestDeviceRoutes:
    def test_register_requires_auth(self, client, db_session):
        assert client.post(f'{PREFIX}/devices/register', json={}).status_code == 401

    @patch('app.services.notification.push.PushNotificationService.register_device')
    def test_register_device(self, mock_reg, client, jwt_headers, db_session):
        mock_reg.return_value = {'success': True, 'device_id': 'abc'}
        resp = client.post(f'{PREFIX}/devices/register', headers=jwt_headers, json={
            'device_token': 'tok123', 'platform': 'android',
        })
        assert_mobile_ok(resp, has_data=True)

    def test_register_missing_token(self, client, jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/devices/register', headers=jwt_headers,
                           json={'platform': 'ios'})
        assert resp.status_code == 400

    def test_register_invalid_platform(self, client, jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/devices/register', headers=jwt_headers,
                           json={'device_token': 'tok', 'platform': 'windows'})
        assert resp.status_code == 400

    @patch('app.services.notification.push.PushNotificationService.unregister_device')
    def test_unregister_device(self, mock_unreg, client, jwt_headers, db_session):
        mock_unreg.return_value = {'success': True}
        resp = client.post(f'{PREFIX}/devices/unregister', headers=jwt_headers,
                           json={'device_token': 'tok123'})
        assert_mobile_ok(resp, has_data=True)

    def test_unregister_missing_token(self, client, jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/devices/unregister', headers=jwt_headers, json={})
        assert resp.status_code == 400

    @patch('app.services.notification.push.PushNotificationService.update_device_activity')
    @patch('app.services.user_analytics_service._update_session_activity_explicit')
    def test_heartbeat(self, mock_session, mock_update, client, jwt_headers, db_session):
        mock_update.return_value = True
        resp = client.post(f'{PREFIX}/devices/heartbeat', headers=jwt_headers,
                           json={'device_token': 'tok123'})
        assert_mobile_ok(resp, has_data=True)
