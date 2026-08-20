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
from sqlalchemy import String, cast
from sqlalchemy.orm import joinedload

from app.models import EmailDeliveryLog, Notification, User
from app.services.email.delivery import (
    get_email_delivery_logs_needing_attention,
    get_skipped_email_delivery_logs,
)
from app.services.notification.core import get_default_icon_for_notification_type
from app.services.notification.service import NotificationService
from app.utils.datetime_helpers import ensure_utc

RECORD_TYPE_NOTIFICATION = 'notification'
RECORD_TYPE_EMAIL = 'email'
RECORD_TYPE_BOTH = 'both'

DEFAULT_CENTER_PAGE_SIZE = 50
MAX_CENTER_PAGE_SIZE = 200


def count_attention_needed_email_deliveries() -> int:
    """Delivery failures that should trigger the Communication Center banner."""
    return len(get_email_delivery_logs_needing_attention())


def _format_datetime(value: Optional[datetime]) -> str:
    if not value:
        return ''
    dt_utc = ensure_utc(value)
    return dt_utc.isoformat() if dt_utc else ''


def _record_type_display(record_type: str) -> str:
    if record_type == RECORD_TYPE_EMAIL:
        return _('Email')
    if record_type == RECORD_TYPE_BOTH:
        return _('Notification + email')
    return _('Notification')


def clamp_center_page_size(per_page: Optional[int]) -> int:
    """Keep Communication Center pages within a safe UI bound."""
    try:
        value = int(per_page) if per_page is not None else DEFAULT_CENTER_PAGE_SIZE
    except (TypeError, ValueError):
        return DEFAULT_CENTER_PAGE_SIZE
    if value < 1:
        return DEFAULT_CENTER_PAGE_SIZE
    return min(value, MAX_CENTER_PAGE_SIZE)


def build_notifications_query(
    *,
    unread_only: bool = False,
    notification_type: Optional[str] = None,
    user_id: Optional[int] = None,
    priority: Optional[str] = None,
    archived_only: bool = False,
    include_archived: bool = False,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
):
    """Filtered notification query for the Communication Center timeline."""
    query = Notification.query.join(User, Notification.user_id == User.id)

    if unread_only:
        query = query.filter(Notification.is_read == False)  # noqa: E712

    if notification_type:
        query = query.filter(cast(Notification.notification_type, String) == notification_type)

    if user_id:
        query = query.filter(Notification.user_id == user_id)

    if priority:
        query = query.filter(Notification.priority == priority)

    if archived_only:
        query = query.filter(Notification.is_archived == True)  # noqa: E712
    elif not include_archived:
        query = query.filter(Notification.is_archived == False)  # noqa: E712

    if date_from:
        query = query.filter(Notification.created_at >= date_from)
    if date_to:
        query = query.filter(Notification.created_at <= date_to)

    return query


def build_orphan_email_query(
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
):
    """Email delivery logs with no linked in-app notification."""
    query = EmailDeliveryLog.query.filter(EmailDeliveryLog.notification_id.is_(None))
    if date_from:
        query = query.filter(EmailDeliveryLog.created_at >= date_from)
    if date_to:
        query = query.filter(EmailDeliveryLog.created_at <= date_to)
    return query


def get_orphan_email_delivery_logs_for_grid(
    limit: Optional[int] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> List[EmailDeliveryLog]:
    """Email delivery logs with no linked in-app notification."""
    query = build_orphan_email_query(date_from=date_from, date_to=date_to).order_by(
        EmailDeliveryLog.created_at.desc(),
        EmailDeliveryLog.id.desc(),
    )
    if limit is not None:
        query = query.limit(limit)
    return query.all()


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
    logged_at = _format_datetime(log.created_at)

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

    created = _format_datetime(notification.created_at)
    read_at = _format_datetime(notification.read_at)
    has_email = bool(email_fields.get('has_email'))
    record_type = RECORD_TYPE_BOTH if has_email else RECORD_TYPE_NOTIFICATION
    title_key = notification.title_key or ''
    email_is_grouped = bool(has_email) and (
        notification_type_value == 'assignment_created'
        or (
            notification_type_value == 'assignment_submitted'
            and title_key != 'notification.assignment_submitted.admin.title'
        )
    )
    email_fields = dict(email_fields)
    email_fields['email_is_grouped'] = email_is_grouped

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


def _serialize_center_rows(
    notifications: List[Notification],
    orphan_email_logs: List[EmailDeliveryLog],
    *,
    original_notification_ids: Set[int],
    attention_notification_ids: Set[int],
) -> List[Dict[str, Any]]:
    assignment_status_cache, _ = NotificationService._build_assignment_caches_for_notifications(
        notifications
    )
    actor_fields_by_id = NotificationService.build_actor_display_fields_map(
        notifications, assignment_status_cache
    )
    email_fields_by_id = NotificationService.build_email_delivery_fields_map(
        [n.id for n in notifications],
        notifications=notifications,
        actor_fields_by_id=actor_fields_by_id,
    )
    return build_communications_center_grid(
        notifications,
        orphan_email_logs,
        actor_fields_by_id=actor_fields_by_id,
        email_fields_by_id=email_fields_by_id,
        original_notification_ids=original_notification_ids,
        attention_notification_ids=attention_notification_ids,
        iso_dates=True,
    )


def fetch_communications_center_page(
    *,
    page: int = 1,
    per_page: int = DEFAULT_CENTER_PAGE_SIZE,
    unread_only: bool = False,
    notification_type: Optional[str] = None,
    user_id: Optional[int] = None,
    priority: Optional[str] = None,
    archived_only: bool = False,
    include_archived: bool = False,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Newest-first page of Communication Center rows (notifications + orphan emails).

    Page 1 also pins email-attention rows (and filtered-out linked notifications)
    so failures stay visible without loading the full history.
    """
    try:
        page = max(1, int(page or 1))
    except (TypeError, ValueError):
        page = 1
    per_page = clamp_center_page_size(per_page)
    offset = (page - 1) * per_page
    window = offset + per_page

    filter_kwargs = {
        'unread_only': unread_only,
        'notification_type': notification_type,
        'user_id': user_id,
        'priority': priority,
        'archived_only': archived_only,
        'include_archived': include_archived,
        'date_from': date_from,
        'date_to': date_to,
    }
    notif_q = build_notifications_query(**filter_kwargs)
    orphan_q = build_orphan_email_query(date_from=date_from, date_to=date_to)

    notif_total = notif_q.count()
    orphan_total = orphan_q.count()

    notifications = (
        notif_q.options(joinedload(Notification.user))
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(window)
        .all()
    )
    orphan_logs = (
        orphan_q.order_by(EmailDeliveryLog.created_at.desc(), EmailDeliveryLog.id.desc())
        .limit(window)
        .all()
    )

    attention_logs = get_email_delivery_logs_needing_attention()
    skipped_logs = get_skipped_email_delivery_logs()
    linked_email_logs = attention_logs + skipped_logs
    attention_notification_ids = {
        log.notification_id for log in attention_logs if log.notification_id
    }
    linked_ids = {log.notification_id for log in linked_email_logs if log.notification_id}

    extra_ids: Set[int] = set()
    if linked_ids:
        in_filter = {
            nid
            for (nid,) in notif_q.with_entities(Notification.id)
            .filter(Notification.id.in_(linked_ids))
            .all()
        }
        extra_ids = linked_ids - in_filter

    original_ids = {n.id for n in notifications if n.id is not None}
    timeline_rows = _serialize_center_rows(
        notifications,
        orphan_logs,
        original_notification_ids=original_ids,
        attention_notification_ids=attention_notification_ids,
    )
    page_rows = timeline_rows[offset:offset + per_page]

    if page == 1:
        already_ids = {
            row.get('notification_id') for row in page_rows if row.get('notification_id')
        }
        pin_ids = (attention_notification_ids | extra_ids) - already_ids
        pin_ids.discard(None)
        if pin_ids:
            extra_notifs = Notification.query.filter(Notification.id.in_(pin_ids)).all()
            extra_rows = _serialize_center_rows(
                extra_notifs,
                [],
                original_notification_ids=set(),
                attention_notification_ids=attention_notification_ids,
            )
            seen = {row.get('grid_row_id') for row in page_rows}
            for row in extra_rows:
                rid = row.get('grid_row_id')
                if rid in seen:
                    continue
                page_rows.append(row)
                seen.add(rid)
            page_rows.sort(key=lambda row: row.get('sort_at') or '', reverse=True)

    timeline_total = notif_total + orphan_total
    total_count = timeline_total + len(extra_ids)
    has_more = (offset + per_page) < timeline_total

    return {
        'rows': page_rows,
        'total_count': total_count,
        'page': page,
        'per_page': per_page,
        'has_more': has_more,
        'failed_email_delivery_count': len(attention_logs),
    }
