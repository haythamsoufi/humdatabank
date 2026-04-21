# Backoffice/app/routes/api/mobile/notifications.py
"""Notification routes: list, count, mark-read/unread, preferences."""

from flask import request, current_app
from flask_login import current_user

from app.utils.api_helpers import get_json_safe
from app.utils.api_pagination import validate_pagination_params
from app.utils.mobile_auth import mobile_auth_required
from app.utils.mobile_responses import (
    mobile_ok, mobile_bad_request, mobile_server_error, mobile_paginated,
)
from app.routes.api.mobile import mobile_bp


@mobile_bp.route('/notifications', methods=['GET'])
@mobile_auth_required
def list_notifications():
    """Paginated notifications for the current user."""
    from app.services.notification.service import NotificationService

    page, per_page = validate_pagination_params(request.args, default_per_page=20)
    unread_only = request.args.get('unread_only', 'false').lower() in ('1', 'true', 'yes')
    notification_type = request.args.get('type')

    result = NotificationService.get_notifications(
        user_id=current_user.id,
        page=page,
        per_page=per_page,
        unread_only=unread_only,
        notification_type=notification_type,
    )
    return mobile_paginated(
        items=result.get('notifications', []),
        total=result.get('total', 0),
        page=page,
        per_page=per_page,
    )


@mobile_bp.route('/notifications/count', methods=['GET'])
@mobile_auth_required
def notification_count():
    """Return unread notification count."""
    from app.services.notification.service import NotificationService
    count = NotificationService.get_unread_count(current_user.id)
    return mobile_ok(data={'unread_count': count})


@mobile_bp.route('/notifications/mark-read', methods=['POST'])
@mobile_auth_required
def mark_notifications_read():
    """Mark notifications as read."""
    from app.services.notification.service import NotificationService
    data = get_json_safe()
    notification_ids = data.get('notification_ids')
    mark_all = data.get('mark_all', False)

    try:
        if mark_all:
            NotificationService.mark_all_as_read(current_user.id)
        elif notification_ids:
            NotificationService.mark_as_read(notification_ids, current_user.id)
        else:
            return mobile_bad_request('notification_ids or mark_all required')
        return mobile_ok(message='Notifications marked as read')
    except Exception as e:
        current_app.logger.error("mark_notifications_read: %s", e, exc_info=True)
        return mobile_server_error()


@mobile_bp.route('/notifications/mark-unread', methods=['POST'])
@mobile_auth_required
def mark_notifications_unread():
    """Mark notifications as unread."""
    from app.services.notification.service import NotificationService
    data = get_json_safe()
    notification_ids = data.get('notification_ids', [])
    if not notification_ids:
        return mobile_bad_request('notification_ids required')

    try:
        NotificationService.mark_as_unread(notification_ids, current_user.id)
        return mobile_ok(message='Notifications marked as unread')
    except Exception as e:
        current_app.logger.error("mark_notifications_unread: %s", e, exc_info=True)
        return mobile_server_error()


@mobile_bp.route('/notifications/preferences', methods=['GET'])
@mobile_auth_required
def get_notification_preferences():
    """Return current user's notification preferences."""
    from app.services.notification.service import NotificationService
    prefs = NotificationService.get_notification_preferences(current_user.id)
    return mobile_ok(data={
        'preferences': {
            'email_notifications': prefs.email_notifications,
            'notification_frequency': prefs.notification_frequency,
            'sound_enabled': prefs.sound_enabled,
            'push_notifications': prefs.push_notifications,
            'notification_types_enabled': prefs.notification_types_enabled or [],
            'push_notification_types_enabled': prefs.push_notification_types_enabled or [],
            'digest_day': prefs.digest_day,
            'digest_time': prefs.digest_time,
            'timezone': getattr(prefs, 'timezone', None),
        },
    })


@mobile_bp.route('/notifications/preferences', methods=['POST'])
@mobile_auth_required
def update_notification_preferences():
    """Update notification preferences."""
    from app.services.notification.service import NotificationService
    data = get_json_safe()
    try:
        NotificationService.update_notification_preferences(
            user_id=current_user.id,
            email_notifications=data.get('email_notifications'),
            notification_types_enabled=data.get('notification_types_enabled'),
            notification_frequency=data.get('notification_frequency'),
            sound_enabled=data.get('sound_enabled'),
            push_notifications=data.get('push_notifications'),
            push_notification_types_enabled=data.get('push_notification_types_enabled'),
            digest_day=data.get('digest_day'),
            digest_time=data.get('digest_time'),
            timezone=data.get('timezone'),
        )
        return mobile_ok(message='Preferences updated')
    except Exception as e:
        current_app.logger.error("update_notification_preferences: %s", e, exc_info=True)
        return mobile_server_error()
