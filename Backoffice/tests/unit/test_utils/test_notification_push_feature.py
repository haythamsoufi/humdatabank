"""Tests for app/utils/notification_push.py and push feature gating."""
from unittest.mock import patch

from app.utils.notification_push import (
    PUSH_NOT_ENABLED_CODE,
    is_notifications_push_enabled,
    preferences_for_client,
    push_disabled_service_result,
    strip_push_preference_kwargs,
)


class TestNotificationPushFeatureFlag:
    def test_disabled_by_default(self, app):
        with app.app_context():
            app.config['FEATURES'] = {}
            assert is_notifications_push_enabled() is False

    def test_enabled_when_feature_flag_on(self, app):
        with app.app_context():
            with patch.dict(app.config, {'FEATURES': {'notifications_push_enabled': True}}):
                assert is_notifications_push_enabled() is True

    def test_disabled_via_features_config(self, app):
        with app.app_context():
            with patch.dict(app.config, {'FEATURES': {'notifications_push_enabled': False}}):
                assert is_notifications_push_enabled() is False

    def test_push_disabled_service_result(self):
        result = push_disabled_service_result()
        assert result['success'] is False
        assert result['error_code'] == PUSH_NOT_ENABLED_CODE
        assert result['push_disabled'] is True

    def test_preferences_for_client_strips_push_when_disabled(self, app):
        with app.app_context():
            prefs = type('Prefs', (), {
                'email_notifications': True,
                'notification_types_enabled': ['admin_message'],
                'notification_frequency': 'instant',
                'push_notifications': True,
                'push_notification_types_enabled': ['admin_message'],
                'digest_day': None,
                'digest_time': None,
                'timezone': None,
            })()

            with patch(
                'app.utils.notification_push.is_notifications_push_enabled',
                return_value=False,
            ):
                payload = preferences_for_client(prefs)
            assert payload['push_notifications'] is False
            assert payload['push_notification_types_enabled'] == []

    def test_strip_push_preference_kwargs_when_disabled(self, app):
        with app.app_context():
            with patch(
                'app.utils.notification_push.is_notifications_push_enabled',
                return_value=False,
            ):
                filtered = strip_push_preference_kwargs({
                    'push_notifications': True,
                    'push_notification_types_enabled': ['admin_message'],
                    'email_notifications': True,
                })
            assert 'push_notifications' not in filtered
            assert 'push_notification_types_enabled' not in filtered
            assert filtered['email_notifications'] is True


class TestPushServiceWhenFeatureDisabled:
    def test_send_push_notification_returns_disabled_result(self, app):
        from app.services.notification.push import PushNotificationService

        with app.app_context():
            with patch(
                'app.utils.notification_push.is_notifications_push_enabled',
                return_value=False,
            ):
                result = PushNotificationService.send_push_notification(
                    user_id=1, title='T', body='B'
                )
        assert result['push_disabled'] is True
        assert result['success'] is False

    def test_register_device_returns_disabled_result(self, app):
        from app.services.notification.push import PushNotificationService

        with app.app_context():
            with patch(
                'app.utils.notification_push.is_notifications_push_enabled',
                return_value=False,
            ):
                result = PushNotificationService.register_device(
                    user_id=1, device_token='tok', platform='android'
                )
        assert result['push_disabled'] is True
        assert result['success'] is False

    def test_update_device_activity_noops_when_disabled(self, app):
        from app.services.notification.push import PushNotificationService

        with app.app_context():
            with patch(
                'app.utils.notification_push.is_notifications_push_enabled',
                return_value=False,
            ):
                assert PushNotificationService.update_device_activity(user_id=1) is False
