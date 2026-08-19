"""Deployment feature flag for mobile push notifications (FCM)."""
from __future__ import annotations

from typing import Any, Dict, Optional

PUSH_NOT_ENABLED_MESSAGE = 'Push notifications are not enabled on this deployment.'
PUSH_NOT_ENABLED_CODE = 'PUSH_NOT_ENABLED'


def is_notifications_push_enabled(app=None) -> bool:
    """True when ``FEATURES['notifications_push_enabled']`` is on (env-driven)."""
    from flask import current_app

    app = app or current_app
    features = app.config.get('FEATURES') or {}
    return bool(features.get('notifications_push_enabled', False))


def push_disabled_service_result(*, devices_count: int = 0) -> Dict[str, Any]:
    return {
        'success': False,
        'error': PUSH_NOT_ENABLED_MESSAGE,
        'error_code': PUSH_NOT_ENABLED_CODE,
        'devices_count': devices_count,
        'push_disabled': True,
    }


def preferences_for_client(preferences) -> Dict[str, Any]:
    """Serialize notification preferences for API/template consumers."""
    payload = {
        'email_notifications': preferences.email_notifications,
        'notification_types_enabled': preferences.notification_types_enabled,
        'in_app_notification_types_enabled': getattr(
            preferences, 'in_app_notification_types_enabled', []
        ),
        'notification_frequency': preferences.notification_frequency,
        'push_notifications': getattr(preferences, 'push_notifications', True),
        'push_notification_types_enabled': getattr(
            preferences, 'push_notification_types_enabled', []
        ),
        'digest_day': getattr(preferences, 'digest_day', None),
        'digest_time': getattr(preferences, 'digest_time', None),
        'timezone': getattr(preferences, 'timezone', None),
    }
    if not is_notifications_push_enabled():
        payload['push_notifications'] = False
        payload['push_notification_types_enabled'] = []
    return payload


def strip_push_preference_kwargs(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Remove push preference fields when the deployment flag is off."""
    if is_notifications_push_enabled():
        return kwargs
    filtered = dict(kwargs)
    filtered.pop('push_notifications', None)
    filtered.pop('push_notification_types_enabled', None)
    return filtered
