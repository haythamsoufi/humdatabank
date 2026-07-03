"""
Admin Communication Center — unified grid for in-app notifications and email delivery.

Row kinds:
- notification (+ optional linked email on the same row)
- email (delivery log with no in-app notification)

Not every notification has email; not every email has a notification.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from flask_babel import gettext as _

from app.models import EmailDeliveryLog, Notification, User
from app.services.email.delivery import get_email_delivery_logs_needing_attention
from app.services.notification.core import get_default_icon_for_notification_type
from app.services.notification_service import NotificationService

RECORD_TYPE_NOTIFICATION = 'notification'
RECORD_TYPE_EMAIL = 'email'
RECORD_TYPE_BOTH = 'both'


def count_attention_needed_email_deliveries() -> int:
    """Delivery failures that should trigger the Communication Center banner."""
    return len(get_email_delivery_logs_needing_attention())


def _format_datetime(value: Optional[datetime], *, iso: bool) -> str:
    if not value:
        return ''
    return value.isoformat() if iso else value.strftime('%Y-%m-%d %H:%M:%S')


def _record_type_display(record_type: str) -> str:
    if record_type == RECORD_TYPE_EMAIL:
        return _('Email')
    if record_type == RECORD_TYPE_BOTH:
        return _('Notification + email')
    return _('Notification')


def get_orphan_email_delivery_logs_for_grid() -> List[EmailDeliveryLog]:
    """Email delivery logs with no linked in-app notification."""
    return (
        EmailDeliveryLog.query.filter(EmailDeliveryLog.notification_id.is_(None))
        .order_by(EmailDeliveryLog.created_at.desc())
        .all()
    )


def ensure_notifications_for_linked_email_logs(
    notifications: List[Notification],
    email_logs: List[EmailDeliveryLog],
) -> List[Notification]:
    """
    Include notifications referenced by email delivery logs even when filtered out
    (e.g. archived) so admins can see linked email status in the grid.
    """
    linked_notif_ids = {log.notification_id for log in email_logs if log.notification_id}
    if not linked_notif_ids:
        return notifications

    existing_ids = {n.id for n in notifications if n.id is not None}
    missing_ids = linked_notif_ids - existing_ids
    if not missing_ids:
        return notifications

    extra = Notification.query.filter(Notification.id.in_(missing_ids)).all()
    merged = list(notifications) + extra
    merged.sort(key=lambda row: row.created_at or datetime.min, reverse=True)
    return merged


def ensure_notifications_for_attention_failures(
    notifications: List[Notification],
    attention_logs: List[EmailDeliveryLog],
) -> List[Notification]:
    """Backward-compatible wrapper for failure-only inclusion."""
    return ensure_notifications_for_linked_email_logs(notifications, attention_logs)


def build_email_grid_row(
    log: EmailDeliveryLog,
    user: Optional[User],
    *,
    iso_dates: bool = False,
) -> Dict[str, Any]:
    """First-class email-only grid row (no synthetic notification fields)."""
    email_fields = NotificationService._serialize_email_delivery_log(log)
    recipient_name = (user.name or user.email) if user else (log.email_address or _('Unknown'))
    logged_at = _format_datetime(log.created_at, iso=iso_dates)

    return {
        'row_kind': RECORD_TYPE_EMAIL,
        'record_type': RECORD_TYPE_EMAIL,
        'record_type_display': _record_type_display(RECORD_TYPE_EMAIL),
        'has_notification': False,
        'has_email': True,
        'grid_row_id': f'email-{log.id}',
        'notification_id': None,
        'notification_type': None,
        'notification_type_display': '',
        'title': '',
        'message': '',
        'priority': None,
        'priority_display': '',
        'is_read': None,
        'is_archived': None,
        'status_display': '',
        'created_at': '',
        'read_at': '',
        'related_url': None,
        'actor': None,
        'actor_action_icon': None,
        'icon': 'fas fa-envelope',
        'primary_is_message': False,
        'included_for_email_failure': False,
        'user_id': log.user_id,
        'user_name': recipient_name,
        'user_email': user.email if user else log.email_address,
        'user_title': (user.title or '') if user else '',
        'user_active': bool(user.active) if user else True,
        'user_profile_color': (user.profile_color or '') if user else '',
        'rbac_role_codes': [],
        'sort_at': logged_at,
        **email_fields,
    }


def format_notification_grid_row(
    notification: Notification,
    *,
    actor_fields: Dict[str, Any],
    email_fields: Dict[str, Any],
    iso_dates: bool = False,
    included_for_email_failure: bool = False,
) -> Dict[str, Any]:
    """Serialize one in-app notification row (with optional linked email fields)."""
    user = notification.user
    message, title = NotificationService._translate_notification_content(notification)
    if message is None:
        message = notification.message
    if title is None:
        title = notification.title

    actor_obj = actor_fields.get('actor')
    actor_action_icon = actor_fields.get('actor_action_icon')
    primary_is_message = actor_fields.get('primary_is_message', False)
    if primary_is_message:
        display_title = message or title
        display_message = title if (title and title != display_title) else ''
    else:
        display_title = title
        display_message = message

    notification_type_value = (
        notification.notification_type.value
        if hasattr(notification.notification_type, 'value')
        else str(notification.notification_type)
    )
    notification_type_display = notification_type_value.replace('_', ' ').title()

    priority = notification.priority or 'normal'
    priority_display = priority.title()

    if notification.is_archived:
        status_display = 'archived'
    elif notification.is_read:
        status_display = 'read'
    else:
        status_display = 'unread'

    created = _format_datetime(notification.created_at, iso=iso_dates)
    read_at = _format_datetime(notification.read_at, iso=iso_dates)
    has_email = bool(email_fields.get('has_email'))
    record_type = RECORD_TYPE_BOTH if has_email else RECORD_TYPE_NOTIFICATION

    return {
        'row_kind': RECORD_TYPE_NOTIFICATION,
        'record_type': record_type,
        'record_type_display': _record_type_display(record_type),
        'has_notification': True,
        'id': notification.id,
        'notification_id': notification.id,
        'grid_row_id': f'notification-{notification.id}',
        'user_id': notification.user_id,
        'user_name': user.name or user.email,
        'user_email': user.email,
        'user_title': user.title or '',
        'user_active': bool(user.active),
        'user_profile_color': user.profile_color or '',
        'rbac_role_codes': [],
        'notification_type': notification_type_value,
        'notification_type_display': notification_type_display,
        'title': display_title,
        'message': display_message,
        'primary_is_message': primary_is_message,
        'actor': actor_obj,
        'actor_action_icon': actor_action_icon,
        'is_read': notification.is_read,
        'is_archived': notification.is_archived,
        'status_display': status_display,
        'priority': priority,
        'priority_display': priority_display,
        'created_at': created,
        'read_at': read_at,
        'related_url': notification.related_url,
        'icon': get_default_icon_for_notification_type(notification.notification_type),
        'included_for_email_failure': included_for_email_failure,
        'sort_at': created,
        **email_fields,
    }


def build_notification_grid_rows(
    notifications: List[Notification],
    *,
    actor_fields_by_id: Dict[int, Dict[str, Any]],
    email_fields_by_id: Dict[int, Dict[str, Any]],
    original_notification_ids: Optional[Set[int]] = None,
    attention_notification_ids: Optional[Set[int]] = None,
    iso_dates: bool = False,
) -> List[Dict[str, Any]]:
    """Build notification rows for the Communication Center grid."""
    original_ids = (
        {n.id for n in notifications if n.id is not None}
        if original_notification_ids is None
        else original_notification_ids
    )
    attention_ids = attention_notification_ids or set()

    rows: List[Dict[str, Any]] = []
    for notification in notifications:
        included = (
            notification.id in attention_ids
            and notification.id not in original_ids
        )
        rows.append(
            format_notification_grid_row(
                notification,
                actor_fields=actor_fields_by_id.get(notification.id, {}),
                email_fields=email_fields_by_id.get(
                    notification.id,
                    NotificationService._serialize_email_delivery_log(None),
                ),
                iso_dates=iso_dates,
                included_for_email_failure=included,
            )
        )
    return rows


def build_email_grid_rows(
    email_logs: List[EmailDeliveryLog],
    *,
    iso_dates: bool = False,
) -> List[Dict[str, Any]]:
    """Build email-only rows for the Communication Center grid."""
    if not email_logs:
        return []

    user_ids = list({log.user_id for log in email_logs if log.user_id})
    users_by_id = {}
    if user_ids:
        users_by_id = {u.id: u for u in User.query.filter(User.id.in_(user_ids)).all()}

    return [
        build_email_grid_row(log, users_by_id.get(log.user_id), iso_dates=iso_dates)
        for log in email_logs
    ]


def build_communications_center_grid(
    notifications: List[Notification],
    orphan_email_logs: List[EmailDeliveryLog],
    *,
    actor_fields_by_id: Dict[int, Dict[str, Any]],
    email_fields_by_id: Dict[int, Dict[str, Any]],
    original_notification_ids: Optional[Set[int]] = None,
    attention_notification_ids: Optional[Set[int]] = None,
    iso_dates: bool = False,
) -> List[Dict[str, Any]]:
    """Merge notification rows and email-only rows, sorted newest first."""
    rows = build_notification_grid_rows(
        notifications,
        actor_fields_by_id=actor_fields_by_id,
        email_fields_by_id=email_fields_by_id,
        original_notification_ids=original_notification_ids,
        attention_notification_ids=attention_notification_ids,
        iso_dates=iso_dates,
    )
    rows.extend(build_email_grid_rows(orphan_email_logs, iso_dates=iso_dates))
    rows.sort(key=lambda row: row.get('sort_at') or '', reverse=True)
    return rows
