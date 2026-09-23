"""
Admin Communication Center — insights and analysis.

Aggregates in-app notifications, email delivery logs, and campaigns for a
rolling window (7 / 30 / 90 / 365 days). “Communications” matches the
center grid: one row per notification plus orphan emails (no linked
notification).
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from flask_babel import gettext as _
from sqlalchemy import case, func

from app.extensions import db
from app.models import EmailDeliveryLog, Notification, NotificationCampaign
from app.services.email.delivery import SKIP_ERROR_PREFIX
from app.services.notification.service import NotificationService
from app.utils.datetime_helpers import utcnow

ALLOWED_INSIGHTS_DAYS: Tuple[int, ...] = (7, 30, 90, 365)
DEFAULT_INSIGHTS_DAYS = 30

CHANNEL_NOTIFICATION = 'notification'
CHANNEL_EMAIL = 'email'
CHANNEL_BOTH = 'both'


def clamp_insights_days(days: Optional[int]) -> int:
    """Restrict the insights window to the supported presets."""
    try:
        value = int(days) if days is not None else DEFAULT_INSIGHTS_DAYS
    except (TypeError, ValueError):
        return DEFAULT_INSIGHTS_DAYS
    if value in ALLOWED_INSIGHTS_DAYS:
        return value
    return DEFAULT_INSIGHTS_DAYS


def _enum_value(value: Any) -> str:
    if value is None:
        return ''
    return value.value if hasattr(value, 'value') else str(value)


def _as_iso_date(value: Any) -> str:
    if value is None:
        return ''
    if hasattr(value, 'strftime'):
        return value.strftime('%Y-%m-%d')
    return str(value)[:10]


def _period_bounds(days: int) -> Tuple[datetime, datetime, datetime]:
    now = utcnow()
    start_date = now.date() - timedelta(days=days - 1)
    cutoff = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    today_start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    return cutoff, today_start, now


def _counts_by_date(query) -> Dict[str, int]:
    rows = query.all()
    out: Dict[str, int] = {}
    for day, count in rows:
        key = _as_iso_date(day)
        if key:
            out[key] = int(count or 0)
    return out


def _date_series(start_date, end_date) -> List[str]:
    days: List[str] = []
    cursor = start_date
    while cursor <= end_date:
        days.append(cursor.strftime('%Y-%m-%d'))
        cursor += timedelta(days=1)
    return days


def _channel_label(channel: str) -> str:
    if channel == CHANNEL_EMAIL:
        return _('Email only')
    if channel == CHANNEL_BOTH:
        return _('Notification + email')
    return _('In-app only')


def _status_label(status: str) -> str:
    labels = {
        'pending': _('Pending'),
        'sent': _('Sent'),
        'failed': _('Failed'),
        'retrying': _('Retrying'),
        'cancelled': _('Cancelled'),
        'unknown': _('Unknown'),
        'skipped': _('Skipped'),
        'draft': _('Draft'),
        'scheduled': _('Scheduled'),
    }
    return labels.get(status, status.replace('_', ' ').title() if status else _('Unknown'))


def _priority_label(priority: str) -> str:
    labels = {
        'low': _('Low'),
        'normal': _('Normal'),
        'high': _('High'),
        'urgent': _('Urgent'),
    }
    return labels.get(priority or 'normal', (priority or _('Normal')).title())


def _type_label(type_key: str) -> str:
    if type_key == 'email':
        return _('Email')
    if not type_key:
        return _('Unknown')
    return NotificationService._get_translated_notification_type_label(type_key)


def build_communications_insights(days: int = DEFAULT_INSIGHTS_DAYS) -> Dict[str, Any]:
    """
    Build Communication Center insights for the last ``days`` calendar days
    (including today, UTC).
    """
    days = clamp_insights_days(days)
    cutoff, today_start, now = _period_bounds(days)
    start_date = cutoff.date()
    today = now.date()

    notif_in_period = Notification.created_at >= cutoff
    email_in_period = EmailDeliveryLog.created_at >= cutoff
    campaign_in_period = NotificationCampaign.created_at >= cutoff

    total_notifications = Notification.query.filter(notif_in_period).count()
    total_emails = EmailDeliveryLog.query.filter(email_in_period).count()
    orphan_emails = EmailDeliveryLog.query.filter(
        email_in_period,
        EmailDeliveryLog.notification_id.is_(None),
    ).count()
    total_communications = total_notifications + orphan_emails

    linked_notif_ids = (
        db.session.query(EmailDeliveryLog.notification_id)
        .filter(EmailDeliveryLog.notification_id.isnot(None))
        .distinct()
    )
    both_count = Notification.query.filter(
        notif_in_period,
        Notification.id.in_(linked_notif_ids),
    ).count()
    notification_only = total_notifications - both_count

    notif_today = Notification.query.filter(Notification.created_at >= today_start).count()
    orphan_today = EmailDeliveryLog.query.filter(
        EmailDeliveryLog.created_at >= today_start,
        EmailDeliveryLog.notification_id.is_(None),
    ).count()
    today_count = notif_today + orphan_today

    avg_per_day = round(total_communications / days, 2) if days else 0.0

    notif_user_ids = {
        uid
        for (uid,) in db.session.query(Notification.user_id)
        .filter(notif_in_period, Notification.user_id.isnot(None))
        .distinct()
        .all()
    }
    email_user_ids = {
        uid
        for (uid,) in db.session.query(EmailDeliveryLog.user_id)
        .filter(email_in_period, EmailDeliveryLog.user_id.isnot(None))
        .distinct()
        .all()
    }
    unique_recipients = len(notif_user_ids | email_user_ids)

    total_read = Notification.query.filter(notif_in_period, Notification.is_read.is_(True)).count()
    total_unread = Notification.query.filter(
        notif_in_period,
        Notification.is_read.is_(False),
        Notification.is_archived.is_(False),
    ).count()
    total_archived = Notification.query.filter(
        notif_in_period,
        Notification.is_archived.is_(True),
    ).count()
    read_rate = round((total_read / total_notifications) * 100, 2) if total_notifications else 0.0

    email_status_rows = (
        db.session.query(
            EmailDeliveryLog.status,
            func.count(EmailDeliveryLog.id),
        )
        .filter(email_in_period)
        .group_by(EmailDeliveryLog.status)
        .all()
    )
    skipped_count = EmailDeliveryLog.query.filter(
        email_in_period,
        EmailDeliveryLog.error_message.startswith(SKIP_ERROR_PREFIX),
    ).count()

    email_by_status_raw: Dict[str, int] = {}
    for status, count in email_status_rows:
        email_by_status_raw[_enum_value(status) or 'unknown'] = int(count or 0)

    cancelled_count = email_by_status_raw.get('cancelled', 0)
    cancelled_not_skipped = max(0, cancelled_count - skipped_count)
    email_by_status_counts = dict(email_by_status_raw)
    if skipped_count:
        email_by_status_counts['skipped'] = skipped_count
        if 'cancelled' in email_by_status_counts:
            if cancelled_not_skipped:
                email_by_status_counts['cancelled'] = cancelled_not_skipped
            else:
                email_by_status_counts.pop('cancelled', None)

    attention_needed = email_by_status_raw.get('failed', 0) + email_by_status_raw.get('unknown', 0)

    email_by_status = [
        {
            'status': status,
            'label': _status_label(status),
            'count': count,
        }
        for status, count in sorted(email_by_status_counts.items(), key=lambda item: item[1], reverse=True)
    ]

    notif_by_day = _counts_by_date(
        db.session.query(
            func.date(Notification.created_at).label('day'),
            func.count(Notification.id),
        )
        .filter(notif_in_period)
        .group_by(func.date(Notification.created_at))
    )
    email_by_day = _counts_by_date(
        db.session.query(
            func.date(EmailDeliveryLog.created_at).label('day'),
            func.count(EmailDeliveryLog.id),
        )
        .filter(email_in_period)
        .group_by(func.date(EmailDeliveryLog.created_at))
    )
    orphan_by_day = _counts_by_date(
        db.session.query(
            func.date(EmailDeliveryLog.created_at).label('day'),
            func.count(EmailDeliveryLog.id),
        )
        .filter(email_in_period, EmailDeliveryLog.notification_id.is_(None))
        .group_by(func.date(EmailDeliveryLog.created_at))
    )

    by_day: List[Dict[str, Any]] = []
    busiest_day: Optional[Dict[str, Any]] = None
    for day in _date_series(start_date, today):
        notifications = notif_by_day.get(day, 0)
        emails = email_by_day.get(day, 0)
        orphans = orphan_by_day.get(day, 0)
        communications = notifications + orphans
        point = {
            'date': day,
            'notifications': notifications,
            'emails': emails,
            'orphan_emails': orphans,
            'communications': communications,
        }
        by_day.append(point)
        if busiest_day is None or communications > busiest_day['count']:
            busiest_day = {'date': day, 'count': communications}

    if busiest_day and busiest_day['count'] == 0:
        busiest_day = None

    type_rows = (
        db.session.query(
            Notification.notification_type,
            func.count(Notification.id).label('total'),
            func.sum(case((Notification.is_read.is_(True), 1), else_=0)).label('read_count'),
        )
        .filter(notif_in_period)
        .group_by(Notification.notification_type)
        .all()
    )
    by_type: List[Dict[str, Any]] = []
    for notif_type, total, read_count in type_rows:
        total = int(total or 0)
        read_count = int(read_count or 0)
        type_key = _enum_value(notif_type)
        by_type.append({
            'type': type_key,
            'label': _type_label(type_key),
            'count': total,
            'read_count': read_count,
            'read_rate': round((read_count / total) * 100, 2) if total else 0.0,
        })
    if orphan_emails:
        by_type.append({
            'type': 'email',
            'label': _type_label('email'),
            'count': orphan_emails,
            'read_count': 0,
            'read_rate': 0.0,
        })
    by_type.sort(key=lambda row: row['count'], reverse=True)

    by_channel = [
        {
            'channel': CHANNEL_NOTIFICATION,
            'label': _channel_label(CHANNEL_NOTIFICATION),
            'count': notification_only,
        },
        {
            'channel': CHANNEL_BOTH,
            'label': _channel_label(CHANNEL_BOTH),
            'count': both_count,
        },
        {
            'channel': CHANNEL_EMAIL,
            'label': _channel_label(CHANNEL_EMAIL),
            'count': orphan_emails,
        },
    ]

    priority_rows = (
        db.session.query(
            Notification.priority,
            func.count(Notification.id).label('total'),
            func.sum(case((Notification.is_read.is_(True), 1), else_=0)).label('read_count'),
        )
        .filter(notif_in_period)
        .group_by(Notification.priority)
        .all()
    )
    by_priority: List[Dict[str, Any]] = []
    for priority, total, read_count in priority_rows:
        total = int(total or 0)
        read_count = int(read_count or 0)
        priority_key = (priority or 'normal')
        by_priority.append({
            'priority': priority_key,
            'label': _priority_label(priority_key),
            'count': total,
            'read_count': read_count,
            'read_rate': round((read_count / total) * 100, 2) if total else 0.0,
        })
    by_priority.sort(key=lambda row: row['count'], reverse=True)

    campaign_rows = (
        db.session.query(
            NotificationCampaign.status,
            func.count(NotificationCampaign.id),
        )
        .filter(campaign_in_period)
        .group_by(NotificationCampaign.status)
        .all()
    )
    campaigns_by_status = [
        {
            'status': _enum_value(status) or 'draft',
            'label': _status_label(_enum_value(status) or 'draft'),
            'count': int(count or 0),
        }
        for status, count in campaign_rows
    ]
    campaigns_by_status.sort(key=lambda row: row['count'], reverse=True)
    campaigns_total = sum(row['count'] for row in campaigns_by_status)
    campaigns_sent_recipients = (
        db.session.query(func.coalesce(func.sum(NotificationCampaign.sent_count), 0))
        .filter(campaign_in_period)
        .scalar()
    )

    return {
        'success': True,
        'period_days': days,
        'period_start': start_date.isoformat(),
        'period_end': today.isoformat(),
        'totals': {
            'communications': total_communications,
            'notifications': total_notifications,
            'emails': total_emails,
            'orphan_emails': orphan_emails,
            'unique_recipients': unique_recipients,
            'today': today_count,
            'avg_per_day': avg_per_day,
            'busiest_day': busiest_day,
        },
        'notifications': {
            'read': total_read,
            'unread': total_unread,
            'archived': total_archived,
            'read_rate': read_rate,
        },
        'email': {
            'total': total_emails,
            'sent': email_by_status_raw.get('sent', 0),
            'failed': email_by_status_raw.get('failed', 0),
            'pending': email_by_status_raw.get('pending', 0),
            'retrying': email_by_status_raw.get('retrying', 0),
            'cancelled': cancelled_not_skipped,
            'unknown': email_by_status_raw.get('unknown', 0),
            'skipped': skipped_count,
            'attention_needed': attention_needed,
            'by_status': email_by_status,
        },
        'by_day': by_day,
        'by_type': by_type,
        'by_channel': by_channel,
        'by_priority': by_priority,
        'campaigns': {
            'total': campaigns_total,
            'sent_recipients': int(campaigns_sent_recipients or 0),
            'by_status': campaigns_by_status,
        },
    }


def empty_communications_insights(days: int = DEFAULT_INSIGHTS_DAYS) -> Dict[str, Any]:
    """Fallback payload when insights cannot be computed."""
    days = clamp_insights_days(days)
    cutoff, _, now = _period_bounds(days)
    return {
        'success': True,
        'period_days': days,
        'period_start': cutoff.date().isoformat(),
        'period_end': now.date().isoformat(),
        'totals': {
            'communications': 0,
            'notifications': 0,
            'emails': 0,
            'orphan_emails': 0,
            'unique_recipients': 0,
            'today': 0,
            'avg_per_day': 0.0,
            'busiest_day': None,
        },
        'notifications': {
            'read': 0,
            'unread': 0,
            'archived': 0,
            'read_rate': 0.0,
        },
        'email': {
            'total': 0,
            'sent': 0,
            'failed': 0,
            'pending': 0,
            'retrying': 0,
            'cancelled': 0,
            'unknown': 0,
            'skipped': 0,
            'attention_needed': 0,
            'by_status': [],
        },
        'by_day': [
            {
                'date': day,
                'notifications': 0,
                'emails': 0,
                'orphan_emails': 0,
                'communications': 0,
            }
            for day in _date_series(cutoff.date(), now.date())
        ],
        'by_type': [],
        'by_channel': [
            {'channel': CHANNEL_NOTIFICATION, 'label': _channel_label(CHANNEL_NOTIFICATION), 'count': 0},
            {'channel': CHANNEL_BOTH, 'label': _channel_label(CHANNEL_BOTH), 'count': 0},
            {'channel': CHANNEL_EMAIL, 'label': _channel_label(CHANNEL_EMAIL), 'count': 0},
        ],
        'by_priority': [],
        'campaigns': {
            'total': 0,
            'sent_recipients': 0,
            'by_status': [],
        },
    }
