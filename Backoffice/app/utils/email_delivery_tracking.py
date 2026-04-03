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


def mark_email_failed(log_id: int, error_message: str, retry: bool = True, max_retries: int = 3) -> Optional[EmailDeliveryLog]:
    """
    Mark an email as failed and schedule retry if needed.

    Uses exponential backoff: 15 min, 1 hour, 4 hours (default max 3 retries)

    Args:
        log_id: Email delivery log ID
        error_message: Error message describing the failure
        retry: Whether to schedule a retry
        max_retries: Maximum number of retry attempts (default: 3)

    Returns:
        EmailDeliveryLog instance or None
    """
    log = EmailDeliveryLog.query.get(log_id)
    if not log:
        return None

    log.status = 'failed'
    log.error_message = error_message
    log.failed_at = utcnow()

    # Schedule retry with exponential backoff if enabled
    if retry and log.retry_count < max_retries:
        log.retry_count += 1
        # Exponential backoff: 15^1=15min, 15^2=225min (3.75h), 15^3=3375min (56.25h)
        # Using more reasonable delays: 15 min, 1 hour, 4 hours
        retry_delays_minutes = [15, 60, 240]  # Exponential backoff: 15min, 1h, 4h
        delay_index = min(log.retry_count - 1, len(retry_delays_minutes) - 1)
        delay_minutes = retry_delays_minutes[delay_index]
        log.next_retry_at = utcnow() + timedelta(minutes=delay_minutes)
        log.status = 'retrying'
        current_app.logger.info(
            f"Scheduled retry #{log.retry_count} for email log {log_id} "
            f"in {delay_minutes} minutes"
        )
    else:
        # Max retries exceeded or retry disabled
        log.retry_count += 1
        log.status = 'failed'
        if log.retry_count >= max_retries:
            current_app.logger.warning(
                f"Email log {log_id} exceeded max retries ({max_retries}), marking as permanently failed"
            )

    db.session.commit()
    return log


def get_pending_retries(max_retries: int = 3) -> List[EmailDeliveryLog]:
    """
    Get emails that are ready to retry.

    Args:
        max_retries: Maximum number of retries allowed (default: 3)

    Returns:
        List of EmailDeliveryLog instances ready for retry
    """
    now = utcnow()
    return EmailDeliveryLog.query.filter(
        EmailDeliveryLog.status == 'retrying',
        EmailDeliveryLog.next_retry_at <= now,
        EmailDeliveryLog.retry_count <= max_retries
    ).all()
