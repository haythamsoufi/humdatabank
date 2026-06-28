"""
Simple email delivery tracking for notifications.
"""
from datetime import datetime, timedelta
from typing import Optional, List
from flask import current_app
from app import db
from app.models import EmailDeliveryLog
from app.utils.datetime_helpers import utcnow


def log_email_attempt(notification_id: Optional[int], user_id: int, email_address: str, subject: str) -> EmailDeliveryLog:
    """Create a log entry for an email attempt."""
    log = EmailDeliveryLog(
        notification_id=notification_id,
        user_id=user_id,
        email_address=email_address,
        subject=subject,
        status='pending'
    )
    db.session.add(log)
    db.session.commit()
    return log


def mark_email_sent(log_id: int) -> Optional[EmailDeliveryLog]:
    """Mark an email as successfully sent."""
    log = EmailDeliveryLog.query.get(log_id)
    if log:
        log.status = 'sent'
        log.sent_at = utcnow()
        db.session.commit()
    return log


def mark_email_failed(
    log_id: int,
    error_message: str,
    retry: bool = False,
    max_retries: int = 3,
) -> Optional[EmailDeliveryLog]:
    """
    Mark an email delivery attempt as failed.

    Automatic retries are disabled; admins retry manually from Communication Center.
    The ``retry`` parameter is kept for call-site compatibility but is ignored.
    """
    _ = retry, max_retries  # legacy parameters — no automatic re-queue

    log = EmailDeliveryLog.query.get(log_id)
    if not log:
        return None

    log.status = 'failed'
    log.error_message = error_message
    log.failed_at = utcnow()
    log.next_retry_at = None
    log.retry_count = int(log.retry_count or 0) + 1
    db.session.commit()
    return log


def get_pending_retries(max_retries: int = 3) -> List[EmailDeliveryLog]:
    """Legacy hook — automatic email retries are disabled."""
    _ = max_retries
    return []


def classify_orphan_email_log(subject: Optional[str]) -> str:
    """
    Classify delivery logs with no notification_id for retry routing.

    Orphan logs are typically digests (by design) or legacy welcome emails.
    """
    text = (subject or '').strip().lower()
    if 'weekly notification digest' in text:
        return 'weekly_digest'
    if 'daily notification digest' in text:
        return 'daily_digest'
    if text.startswith('welcome to'):
        return 'welcome'
    return 'unsupported'


def email_delivery_log_can_retry(log: Optional[EmailDeliveryLog]) -> bool:
    """Whether an admin/manual retry can resend this delivery log."""
    if log is None:
        return False

    status = log.status.value if hasattr(log.status, 'value') else str(log.status or '')
    if status not in ('failed', 'retrying'):
        return False

    if log.notification_id:
        return True

    return classify_orphan_email_log(log.subject) != 'unsupported'


def email_delivery_log_can_cancel(log: Optional[EmailDeliveryLog]) -> bool:
    """Whether an admin can dismiss a failed delivery log without retrying."""
    if log is None:
        return False

    status = log.status.value if hasattr(log.status, 'value') else str(log.status or '')
    return status in ('failed', 'retrying')


def cancel_email_delivery_log(log_id: int) -> tuple[bool, str]:
    """Dismiss a failed email delivery log (no resend)."""
    log = EmailDeliveryLog.query.get(log_id)
    if not log:
        return False, 'Email delivery log not found'

    status = log.status.value if hasattr(log.status, 'value') else str(log.status or '')
    if status == 'cancelled':
        return True, 'Email failure already dismissed'

    if status not in ('failed', 'retrying'):
        return False, f'Cannot dismiss email in status: {status}'

    log.status = 'cancelled'
    log.next_retry_at = None
    db.session.commit()
    return True, 'Email failure dismissed'


def admin_cancel_email_delivery_logs(log_ids: Optional[List[int]] = None) -> dict:
    """Dismiss multiple failed delivery logs without retrying."""
    query = EmailDeliveryLog.query.filter(
        EmailDeliveryLog.status.in_(('failed', 'retrying'))
    )
    if log_ids:
        query = query.filter(EmailDeliveryLog.id.in_(log_ids))

    logs = query.order_by(EmailDeliveryLog.created_at.asc()).all()
    success_count = 0
    failure_count = 0
    skipped_count = 0
    errors: List[str] = []

    for log in logs:
        if not email_delivery_log_can_cancel(log):
            skipped_count += 1
            continue
        ok, message = cancel_email_delivery_log(log.id)
        if ok:
            success_count += 1
        else:
            failure_count += 1
            if message and len(errors) < 5:
                errors.append(message)

    return {
        'attempted': len(logs) - skipped_count,
        'skipped_count': skipped_count,
        'success_count': success_count,
        'failure_count': failure_count,
        'errors': errors,
    }


def admin_retry_email_delivery_log(log_id: int) -> tuple[bool, str]:
    """
    Manually retry a failed email delivery log (admin Communication Center).

    Returns:
        (success, message)
    """
    from app.services.notification.emails import retry_email_delivery_log

    log = EmailDeliveryLog.query.get(log_id)
    if not log:
        return False, 'Email delivery log not found'

    status = log.status.value if hasattr(log.status, 'value') else str(log.status or '')
    if status == 'sent':
        return True, 'Email already sent'

    if status not in ('failed', 'retrying'):
        return False, f'Cannot retry email in status: {status}'

    if not email_delivery_log_can_retry(log):
        return False, f'Retry is not supported for this email type (subject: {log.subject or "(empty)"})'

    log.next_retry_at = None
    db.session.commit()

    if retry_email_delivery_log(log):
        return True, 'Email sent successfully'

    db.session.refresh(log)
    refreshed = log.status.value if hasattr(log.status, 'value') else str(log.status or '')
    if refreshed == 'sent':
        return True, 'Email sent successfully'

    error = log.error_message or 'Email send failed'
    return False, error


def admin_retry_failed_email_delivery_logs(log_ids: Optional[List[int]] = None) -> dict:
    """Retry multiple failed delivery logs. Returns counts for admin UI."""
    query = EmailDeliveryLog.query.filter(
        EmailDeliveryLog.status.in_(('failed', 'retrying'))
    )
    if log_ids:
        query = query.filter(EmailDeliveryLog.id.in_(log_ids))

    logs = query.order_by(EmailDeliveryLog.created_at.asc()).all()
    success_count = 0
    failure_count = 0
    skipped_count = 0
    errors: List[str] = []

    for log in logs:
        if not email_delivery_log_can_retry(log):
            skipped_count += 1
            continue
        ok, message = admin_retry_email_delivery_log(log.id)
        if ok:
            success_count += 1
        else:
            failure_count += 1
            if message and len(errors) < 5:
                errors.append(message)

    return {
        'attempted': len(logs) - skipped_count,
        'skipped_count': skipped_count,
        'success_count': success_count,
        'failure_count': failure_count,
        'errors': errors,
    }
