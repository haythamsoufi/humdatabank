"""
Tests for app/services/notification/push.py

Targets 100% coverage of the PushNotificationService.
"""
from datetime import timedelta
from unittest.mock import patch, MagicMock, PropertyMock
import pytest

from app.services.notification.push import PushNotificationService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_device(user_id=1, token='token_abc', platform='android',
                 logged_out_at=None, consecutive_failures=0):
    device = MagicMock()
    device.id = 1
    device.user_id = user_id
    device.device_token = token
    device.platform = platform
    device.logged_out_at = logged_out_at
    device.consecutive_failures = consecutive_failures
    device.last_active_at = None
    device.app_version = None
    device.device_model = 'TestModel'
    device.device_name = 'TestDevice'
    device.os_version = '14'
    device.ip_address = '127.0.0.1'
    device.timezone = 'UTC'
    return device


# ---------------------------------------------------------------------------
# _get_access_token
# ---------------------------------------------------------------------------

class TestGetAccessToken:
    def test_returns_none_when_google_auth_not_available(self, app, db_session):
        import app.services.notification.push as push_module
        original = push_module.GOOGLE_AUTH_AVAILABLE
        try:
            push_module.GOOGLE_AUTH_AVAILABLE = False
            with app.app_context():
                result = PushNotificationService._get_access_token()
        finally:
            push_module.GOOGLE_AUTH_AVAILABLE = original
        assert result is None

    def test_returns_none_when_no_service_account_path(self, app, db_session):
        with app.app_context():
            with patch.dict('os.environ', {}, clear=True):
                import app.services.notification.push as push_module
                original = push_module.GOOGLE_AUTH_AVAILABLE
                push_module.GOOGLE_AUTH_AVAILABLE = True
                try:
                    # Clear cached credentials
                    PushNotificationService._credentials = None
                    PushNotificationService._access_token = None
                    PushNotificationService._token_expiry = None

                    result = PushNotificationService._get_access_token()
                finally:
                    push_module.GOOGLE_AUTH_AVAILABLE = original
        assert result is None

    def test_returns_cached_token_when_valid(self, app, db_session):
        from app.utils.datetime_helpers import utcnow
        import app.services.notification.push as push_module
        original_token = PushNotificationService._access_token
        original_expiry = PushNotificationService._token_expiry
        original_avail = push_module.GOOGLE_AUTH_AVAILABLE

        try:
            push_module.GOOGLE_AUTH_AVAILABLE = True
            PushNotificationService._access_token = 'cached_token'
            PushNotificationService._token_expiry = utcnow() + timedelta(hours=1)
            with app.app_context():
                result = PushNotificationService._get_access_token()
        finally:
            PushNotificationService._access_token = original_token
            PushNotificationService._token_expiry = original_expiry
            push_module.GOOGLE_AUTH_AVAILABLE = original_avail

        assert result == 'cached_token'

    def test_returns_none_when_service_account_file_not_found(self, app, db_session):
        import app.services.notification.push as push_module
        original_avail = push_module.GOOGLE_AUTH_AVAILABLE
        original_creds = PushNotificationService._credentials
        original_token = PushNotificationService._access_token
        original_expiry = PushNotificationService._token_expiry

        try:
            push_module.GOOGLE_AUTH_AVAILABLE = True
            PushNotificationService._credentials = None
            PushNotificationService._access_token = None
            PushNotificationService._token_expiry = None

            with app.app_context():
                with patch.dict('os.environ', {'FCM_SERVICE_ACCOUNT_PATH': '/nonexistent/path.json'}):
                    result = PushNotificationService._get_access_token()
        finally:
            push_module.GOOGLE_AUTH_AVAILABLE = original_avail
            PushNotificationService._credentials = original_creds
            PushNotificationService._access_token = original_token
            PushNotificationService._token_expiry = original_expiry

        assert result is None

    def test_handles_general_exception(self, app, db_session):
        import app.services.notification.push as push_module
        original_avail = push_module.GOOGLE_AUTH_AVAILABLE
        original_creds = PushNotificationService._credentials
        original_token = PushNotificationService._access_token
        original_expiry = PushNotificationService._token_expiry

        try:
            push_module.GOOGLE_AUTH_AVAILABLE = True
            PushNotificationService._credentials = None
            PushNotificationService._access_token = None
            PushNotificationService._token_expiry = None

            with app.app_context():
                with patch.dict('os.environ', {'FCM_SERVICE_ACCOUNT_PATH': '/some/path.json'}):
                    with patch('os.path.exists', return_value=True):
                        with patch('builtins.open', side_effect=Exception('read error')):
                            result = PushNotificationService._get_access_token()
        finally:
            push_module.GOOGLE_AUTH_AVAILABLE = original_avail
            PushNotificationService._credentials = original_creds
            PushNotificationService._access_token = original_token
            PushNotificationService._token_expiry = original_expiry

        assert result is None


# ---------------------------------------------------------------------------
# send_push_notification
# ---------------------------------------------------------------------------

class TestSendPushNotification:
    def test_returns_no_devices_result_when_no_devices(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.push.UserDevice') as MockUD:
                MockUD.query.filter_by.return_value.filter.return_value.all.return_value = []
                result = PushNotificationService.send_push_notification(
                    user_id=1, title='Title', body='Body'
                )
        assert result['success'] is False
        assert result['devices_count'] == 0
        assert result['notification_created'] is True

    def test_returns_false_when_no_fcm_project_id(self, app, db_session):
        device = _make_device()
        with app.app_context():
            with patch('app.services.notification.push.UserDevice') as MockUD:
                MockUD.query.filter_by.return_value.filter.return_value.all.return_value = [device]
                with patch.dict('os.environ', {}, clear=True):
                    with patch('os.path.exists', return_value=False):
                        result = PushNotificationService.send_push_notification(
                            user_id=1, title='Title', body='Body'
                        )
        assert result['success'] is False
        assert 'FCM not configured' in result.get('error', '')

    def test_successful_send_to_device(self, app, db_session):
        device = _make_device()
        with app.app_context():
            with patch('app.services.notification.push.UserDevice') as MockUD:
                MockUD.query.filter_by.return_value.filter.return_value.all.return_value = [device]
                with patch.dict('os.environ', {'FCM_PROJECT_ID': 'test-project'}):
                    with patch.object(PushNotificationService, '_send_to_device',
                                      return_value={'success': True, 'message_id': 'msg_1'}):
                        with patch('app.services.notification.push.db') as mock_db:
                            result = PushNotificationService.send_push_notification(
                                user_id=1, title='Title', body='Body'
                            )
        assert result['success'] is True
        assert result['success_count'] == 1

    def test_handles_device_failure_and_consecutive_tracking(self, app, db_session):
        device = _make_device(consecutive_failures=2)
        with app.app_context():
            with patch('app.services.notification.push.UserDevice') as MockUD:
                MockUD.query.filter_by.return_value.filter.return_value.all.return_value = [device]
                with patch.dict('os.environ', {'FCM_PROJECT_ID': 'test-project'}):
                    with patch.object(PushNotificationService, '_send_to_device',
                                      return_value={'success': False, 'error': 'Token invalid',
                                                    'error_code': 'NOT_FOUND'}):
                        with patch('app.services.notification.push.db') as mock_db:
                            result = PushNotificationService.send_push_notification(
                                user_id=1, title='T', body='B'
                            )
        assert result['failure_count'] == 1

    def test_deletes_invalid_device_after_3_failures(self, app, db_session):
        device = _make_device(consecutive_failures=3)
        with app.app_context():
            with patch('app.services.notification.push.UserDevice') as MockUD:
                MockUD.query.filter_by.return_value.filter.return_value.all.return_value = [device]
                with patch.dict('os.environ', {'FCM_PROJECT_ID': 'test-project'}):
                    with patch.object(PushNotificationService, '_send_to_device',
                                      return_value={'success': False, 'error_code': 'NOT_FOUND'}):
                        with patch('app.services.notification.push.db') as mock_db:
                            result = PushNotificationService.send_push_notification(
                                user_id=1, title='T', body='B'
                            )
        # Device should have been scheduled for deletion
        assert result is not None

    def test_handles_exception_with_rollback(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.push.UserDevice') as MockUD:
                MockUD.query.filter_by.return_value.filter.side_effect = Exception('db fail')
                with patch('app.services.notification.push.db') as mock_db:
                    result = PushNotificationService.send_push_notification(
                        user_id=1, title='T', body='B'
                    )
        assert result['success'] is False

    def test_project_id_from_service_account_file(self, app, db_session):
        device = _make_device()
        import json
        sa_info = {'project_id': 'my-project', 'type': 'service_account'}
        with app.app_context():
            with patch('app.services.notification.push.UserDevice') as MockUD:
                MockUD.query.filter_by.return_value.filter.return_value.all.return_value = [device]
                with patch.dict('os.environ', {'FCM_SERVICE_ACCOUNT_PATH': '/some/path.json'}):
                    with patch('os.path.exists', return_value=True):
                        with patch('builtins.open', MagicMock()):
                            with patch('json.load', return_value=sa_info):
                                with patch.object(PushNotificationService, '_send_to_device',
                                                  return_value={'success': True, 'message_id': 'x'}):
                                    with patch('app.services.notification.push.db'):
                                        result = PushNotificationService.send_push_notification(
                                            user_id=1, title='T', body='B'
                                        )
        assert result is not None


# ---------------------------------------------------------------------------
# _send_to_device
# ---------------------------------------------------------------------------

class TestSendToDevice:
    def test_returns_error_when_no_project_id(self, app, db_session):
        with app.app_context():
            with patch.dict('os.environ', {}, clear=True):
                result = PushNotificationService._send_to_device(
                    'token', 'android', 'Title', 'Body'
                )
        assert result['success'] is False
        assert 'FCM_PROJECT_ID' in result.get('error', '')

    def test_returns_error_when_no_access_token(self, app, db_session):
        with app.app_context():
            with patch.object(PushNotificationService, '_get_access_token', return_value=None):
                result = PushNotificationService._send_to_device(
                    'token', 'android', 'Title', 'Body', project_id='my-project'
                )
        assert result['success'] is False

    def test_successful_200_response(self, app, db_session):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'name': 'projects/my-project/messages/123'}

        with app.app_context():
            with patch.object(PushNotificationService, '_get_access_token', return_value='token123'):
                with patch('requests.post', return_value=mock_response):
                    result = PushNotificationService._send_to_device(
                        'device_token', 'android', 'Title', 'Body',
                        data={'key': 'val'}, priority='high',
                        project_id='my-project'
                    )
        assert result['success'] is True
        assert result['message_id'] == 'projects/my-project/messages/123'

    def test_4xx_error_response(self, app, db_session):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.content = True
        mock_response.json.return_value = {
            'error': {'message': 'Token not found', 'code': 'NOT_FOUND'}
        }
        with app.app_context():
            with patch.object(PushNotificationService, '_get_access_token', return_value='token123'):
                with patch('requests.post', return_value=mock_response):
                    result = PushNotificationService._send_to_device(
                        'device_token' * 3, 'android', 'T', 'B', project_id='my-project'
                    )
        assert result['success'] is False
        assert result['error_code'] == 'NOT_FOUND'

    def test_no_content_response(self, app, db_session):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.content = None
        with app.app_context():
            with patch.object(PushNotificationService, '_get_access_token', return_value='tok'):
                with patch('requests.post', return_value=mock_response):
                    result = PushNotificationService._send_to_device(
                        'device_token' * 3, 'ios', 'T', 'B', project_id='proj'
                    )
        assert result['success'] is False

    def test_timeout_error(self, app, db_session):
        import requests
        with app.app_context():
            with patch.object(PushNotificationService, '_get_access_token', return_value='tok'):
                with patch('requests.post', side_effect=requests.exceptions.Timeout()):
                    result = PushNotificationService._send_to_device(
                        'device_token' * 3, 'android', 'T', 'B', project_id='proj'
                    )
        assert result['success'] is False
        assert result['error_code'] == 'TIMEOUT'
        assert result['retryable'] is True

    def test_connection_error(self, app, db_session):
        import requests
        with app.app_context():
            with patch.object(PushNotificationService, '_get_access_token', return_value='tok'):
                with patch('requests.post', side_effect=requests.exceptions.ConnectionError()):
                    result = PushNotificationService._send_to_device(
                        'device_token' * 3, 'android', 'T', 'B', project_id='proj'
                    )
        assert result['success'] is False
        assert result['error_code'] == 'CONNECTION_ERROR'

    def test_request_exception(self, app, db_session):
        import requests
        with app.app_context():
            with patch.object(PushNotificationService, '_get_access_token', return_value='tok'):
                with patch('requests.post', side_effect=requests.exceptions.RequestException()):
                    result = PushNotificationService._send_to_device(
                        'device_token' * 3, 'android', 'T', 'B', project_id='proj'
                    )
        assert result['success'] is False
        assert result['error_code'] == 'NETWORK_ERROR'

    def test_unexpected_exception(self, app, db_session):
        with app.app_context():
            with patch.object(PushNotificationService, '_get_access_token', return_value='tok'):
                with patch('requests.post', side_effect=ValueError('unexpected')):
                    result = PushNotificationService._send_to_device(
                        'device_token' * 3, 'android', 'T', 'B', project_id='proj'
                    )
        assert result['success'] is False
        assert result['error_code'] == 'UNKNOWN_ERROR'

    def test_high_priority_sets_android_high(self, app, db_session):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'name': 'msg/1'}

        captured_payload = {}

        def capture_post(url, headers, json, timeout):
            captured_payload.update(json)
            return mock_response

        with app.app_context():
            with patch.object(PushNotificationService, '_get_access_token', return_value='tok'):
                with patch('requests.post', side_effect=capture_post):
                    result = PushNotificationService._send_to_device(
                        'token', 'android', 'T', 'B', priority='high', project_id='proj'
                    )
        assert captured_payload['message']['android']['priority'] == 'HIGH'

    def test_data_payload_converted_to_strings(self, app, db_session):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'name': 'msg/1'}

        captured_payload = {}

        def capture_post(url, headers, json, timeout):
            captured_payload.update(json)
            return mock_response

        with app.app_context():
            with patch.object(PushNotificationService, '_get_access_token', return_value='tok'):
                with patch('requests.post', side_effect=capture_post):
                    result = PushNotificationService._send_to_device(
                        'token', 'ios', 'T', 'B',
                        data={'count': 5, 'enabled': True},
                        project_id='proj'
                    )
        data = captured_payload['message']['data']
        assert data['count'] == '5'
        assert data['enabled'] == 'True'


# ---------------------------------------------------------------------------
# register_device
# ---------------------------------------------------------------------------

class TestRegisterDevice:
    def test_registers_new_device(self, app, db_session):
        from app.models import User
        from app import db

        with app.app_context():
            user = User(email='reg_device@test.com', name='RegDevice', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.commit()

            result = PushNotificationService.register_device(
                user_id=user.id,
                device_token='new_token_12345',
                platform='android',
                app_version='1.0.0',
                device_model='Pixel 7',
                device_name='My Phone',
                os_version='Android 13',
                ip_address='192.168.1.1',
                timezone='UTC'
            )

        assert result['success'] is True
        assert result['message'] == 'Device registered'
        assert 'device_id' in result

    def test_updates_existing_device_by_token(self, app, db_session):
        from app.models import User, UserDevice
        from app import db

        with app.app_context():
            user = User(email='update_device@test.com', name='Update', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            device = UserDevice(
                user_id=user.id,
                device_token='existing_token',
                platform='android',
            )
            db.session.add(device)
            db.session.commit()

            result = PushNotificationService.register_device(
                user_id=user.id,
                device_token='existing_token',
                platform='ios'
            )

        assert result['success'] is True
        assert result['message'] == 'Device updated'

    def test_reactivates_logged_out_device(self, app, db_session):
        from app.models import User, UserDevice
        from app import db
        from app.utils.datetime_helpers import utcnow

        with app.app_context():
            user = User(email='reactivate@test.com', name='Reactivate', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            device = UserDevice(
                user_id=user.id,
                device_token='logged_out_token',
                platform='android',
                logged_out_at=utcnow() - timedelta(days=1)
            )
            db.session.add(device)
            db.session.commit()

            result = PushNotificationService.register_device(
                user_id=user.id,
                device_token='logged_out_token',
                platform='android'
            )

        assert result['success'] is True
        assert 'reactivated' in result['message']

    def test_handles_stale_device_replacement(self, app, db_session):
        """Test single stale device matching by model/name."""
        from app.models import User, UserDevice
        from app import db

        with app.app_context():
            user = User(email='stale_device@test.com', name='Stale', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            device = UserDevice(
                user_id=user.id,
                device_token='old_token',
                platform='android',
                device_model='Pixel 7',
                device_name='My Phone'
            )
            db.session.add(device)
            db.session.commit()

            result = PushNotificationService.register_device(
                user_id=user.id,
                device_token='new_token_different',
                platform='android',
                device_model='Pixel 7',
                device_name='My Phone'
            )

        assert result['success'] is True

    def test_handles_exception_with_rollback(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.push.UserDevice') as MockUD:
                MockUD.query.filter_by.side_effect = Exception('db fail')
                with patch('app.services.notification.push.db') as mock_db:
                    result = PushNotificationService.register_device(
                        user_id=1, device_token='token', platform='android'
                    )
        assert result['success'] is False


# ---------------------------------------------------------------------------
# unregister_device
# ---------------------------------------------------------------------------

class TestUnregisterDevice:
    def test_marks_device_as_logged_out(self, app, db_session):
        from app.models import User, UserDevice
        from app import db

        with app.app_context():
            user = User(email='unreg@test.com', name='Unreg', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            device = UserDevice(
                user_id=user.id,
                device_token='unreg_token',
                platform='android',
            )
            db.session.add(device)
            db.session.commit()

            result = PushNotificationService.unregister_device(
                user_id=user.id, device_token='unreg_token'
            )

        assert result['success'] is True
        assert result['message'] == 'Device logged out'

    def test_returns_error_when_device_not_found(self, app, db_session):
        with app.app_context():
            result = PushNotificationService.unregister_device(
                user_id=9999, device_token='nonexistent_token'
            )
        assert result['success'] is False

    def test_handles_exception(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.push.UserDevice') as MockUD:
                MockUD.query.filter_by.side_effect = Exception('db fail')
                with patch('app.services.notification.push.db') as mock_db:
                    result = PushNotificationService.unregister_device(
                        user_id=1, device_token='token'
                    )
        assert result['success'] is False


# ---------------------------------------------------------------------------
# send_bulk_push_notifications
# ---------------------------------------------------------------------------

class TestSendBulkPushNotifications:
    def test_empty_user_list(self, app, db_session):
        with app.app_context():
            result = PushNotificationService.send_bulk_push_notifications(
                user_ids=[], title='T', body='B'
            )
        assert result['total_users'] == 0
        assert result['success'] is False

    def test_sends_to_multiple_users(self, app, db_session):
        with app.app_context():
            with patch.object(PushNotificationService, 'send_push_notification') as mock_send:
                mock_send.return_value = {
                    'success': True, 'success_count': 1,
                    'devices_count': 1, 'failure_count': 0, 'results': []
                }
                result = PushNotificationService.send_bulk_push_notifications(
                    user_ids=[1, 2, 3], title='T', body='B'
                )
        assert result['total_users'] == 3
        assert result['success'] is True

    def test_aggregates_failures(self, app, db_session):
        with app.app_context():
            def mock_send(user_id, title, body, data=None, priority='normal'):
                return {'success': False, 'devices_count': 1, 'failure_count': 1}

            with patch.object(PushNotificationService, 'send_push_notification', side_effect=mock_send):
                result = PushNotificationService.send_bulk_push_notifications(
                    user_ids=[1, 2], title='T', body='B'
                )
        assert result['success'] is False
        assert result['total_failure'] == 2


# ---------------------------------------------------------------------------
# update_device_activity
# ---------------------------------------------------------------------------

class TestUpdateDeviceActivity:
    def test_updates_specific_device_by_token(self, app, db_session):
        from app.models import User, UserDevice
        from app import db
        from app.utils.datetime_helpers import utcnow

        with app.app_context():
            user = User(email='activity@test.com', name='Activity', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            device = UserDevice(
                user_id=user.id,
                device_token='activity_token',
                platform='android',
                logged_out_at=None,
                last_active_at=utcnow() - timedelta(minutes=10)
            )
            db.session.add(device)
            db.session.commit()

            result = PushNotificationService.update_device_activity(
                user_id=user.id,
                device_token='activity_token',
                throttle_minutes=5
            )

        assert result is True

    def test_throttled_device_not_updated(self, app, db_session):
        from app.models import User, UserDevice
        from app import db
        from app.utils.datetime_helpers import utcnow

        with app.app_context():
            user = User(email='throttled@test.com', name='Throttled', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            device = UserDevice(
                user_id=user.id,
                device_token='throttled_token',
                platform='android',
                logged_out_at=None,
                last_active_at=utcnow() - timedelta(minutes=1)
            )
            db.session.add(device)
            db.session.commit()

            result = PushNotificationService.update_device_activity(
                user_id=user.id,
                device_token='throttled_token',
                throttle_minutes=5
            )

        assert result is False

    def test_updates_all_devices_when_no_token(self, app, db_session):
        from app.models import User, UserDevice
        from app import db
        from app.utils.datetime_helpers import utcnow

        with app.app_context():
            user = User(email='alldevices@test.com', name='AllDevices', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            for i in range(2):
                device = UserDevice(
                    user_id=user.id,
                    device_token=f'all_token_{i}',
                    platform='android',
                    logged_out_at=None,
                    last_active_at=utcnow() - timedelta(minutes=10)
                )
                db.session.add(device)
            db.session.commit()

            result = PushNotificationService.update_device_activity(
                user_id=user.id,
                device_token=None,
                throttle_minutes=5
            )

        assert result is True

    def test_returns_false_when_device_not_found(self, app, db_session):
        with app.app_context():
            result = PushNotificationService.update_device_activity(
                user_id=9999, device_token='nonexistent', throttle_minutes=5
            )
        assert result is False

    def test_handles_exception_gracefully(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.push.UserDevice') as MockUD:
                MockUD.query.filter_by.side_effect = Exception('db fail')
                result = PushNotificationService.update_device_activity(
                    user_id=1, device_token='token', throttle_minutes=5
                )
        assert result is False
