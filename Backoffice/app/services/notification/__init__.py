"""
Notification services package.

Consolidates all notification infrastructure: in-app notifications,
email digests, push notifications, scheduling, and analytics.
"""

from .core import create_notification, get_default_icon_for_notification_type
from .service import NotificationService
from .push import PushNotificationService
from .analytics import NotificationAnalytics

__all__ = [
    'create_notification',
    'get_default_icon_for_notification_type',
    'NotificationService',
    'PushNotificationService',
    'NotificationAnalytics',
]
