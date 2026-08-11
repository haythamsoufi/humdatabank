"""
Simple email delivery tracking for notifications.
"""
import concurrent.futures
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from flask import current_app
from app import db
from app.models import EmailDeliveryLog
from app.utils.datetime_helpers import utcnow


SKIP_ERROR_PREFIX = '[Skipped] '

# Statuses that represent an outstanding, actionable send attempt — surfaced in the
# Communication Center banner/grid and eligible for manual retry/dismiss. 'unknown'
# (no HTTP response from the Email API — see mark_email_failed_or_unknown) is included
# alongside 'failed' because it needs the same admin attention, even though it isn't
# a confirmed failure.
ACTIONABLE_EMAIL_STATUSES = ('failed', 'retrying', 'unknown')

# A single retry-all click can face a large backlog after an outage. Each retry is a
# blocking HTTP call to the Email API (up to the ~15s client timeout), so processing
# is parallelized (see admin_retry_failed_email_delivery_logs) and capped per call to
# keep the admin's request from running for minutes; the UI re-calls for the rest.
EMAIL_RETRY_BATCH_MAX_PER_CALL = int(os.environ.get('EMAIL_RETRY_BATCH_MAX_PER_CALL', '20'))
EMAIL_RETRY_BATCH_MAX_WORKERS = int(os.environ.get('EMAIL_RETRY_BATCH_MAX_WORKERS', '5'))


def email_delivery_log_is_skipped(log: Optional[EmailDeliveryLog]) -> bool:
    """True when the log was recorded as an intentional skip (not a send failure)."""
    if log is None:
        return False
    return (log.error_message or '').startswith(SKIP_ERROR_PREFIX)


def mark_email_skipped(log_id: int, reason: str) -> Optional[EmailDeliveryLog]:
    """Record a deliberate skip (audit trail only — not a delivery failure)."""
    log = EmailDeliveryLog.query.get(log_id)
    if not log:
        return None
    log.status = 'cancelled'
    log.error_message = f'{SKIP_ERROR_PREFIX}{reason}'
    log.next_retry_at = None
    db.session.commit()
    return log


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
    status: str = 'failed',
) -> Optional[EmailDeliveryLog]:
    """
    Mark an email delivery attempt as failed (or ``status='unknown'``, see
    :func:`mark_email_failed_or_unknown`).

    Automatic retries are disabled; admins retry manually from Communication Center.
    The ``retry`` parameter is kept for call-site compatibility but is ignored.
    """
    _ = retry, max_retries  # legacy parameters — no automatic re-queue

    log = EmailDeliveryLog.query.get(log_id)
    if not log:
        return None

    log.status = status
    log.error_message = error_message
    log.failed_at = utcnow()
    log.next_retry_at = None
    log.retry_count = int(log.retry_count or 0) + 1
    db.session.commit()
    return log


def mark_email_failed_or_unknown(
    log_id: int,
    error_message: str,
    failure_info: Optional[dict] = None,
) -> Optional[EmailDeliveryLog]:
    """
    Record a send failure, choosing ``status='unknown'`` over ``'failed'`` when the
    Email API never returned an HTTP response at all (``failure_info['code'] ==
    'email_api_request_error'`` — read timeout / connection error raised in
    ``app.services.email.client._send_via_ifrc``).

    A no-response outcome is genuinely ambiguous: the request may have reached the
    API and actually been sent, and manually retrying it risks a duplicate email if
    so. 'failed' is reserved for outcomes we're confident did NOT go through (client-
    side validation errors, or an explicit HTTP error status from the API). See
    docs/runbooks/email-api-no-response.md for the full triage/escalation notes.
    """
    code = (failure_info or {}).get('code')
    if code == 'email_api_request_error':
        client_request_id = (failure_info or {}).get('client_request_id')
        id_note = f" client_request_id={client_request_id}" if client_request_id else ""
        note = (
            "No response received from the Email API before our timeout — delivery "
            f"could not be confirmed and may have already succeeded upstream.{id_note} "
            f"Details: {error_message}"
        )
        return mark_email_failed(log_id, note, status='unknown')
    return mark_email_failed(log_id, error_message, status='failed')


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
    if text.startswith('country access requests -'):
        return 'fds_access_request_digest'
    if text.startswith('welcome to'):
        return 'welcome'
    return 'unsupported'


def email_delivery_log_can_retry(log: Optional[EmailDeliveryLog]) -> bool:
    """Whether an admin/manual retry can resend this delivery log."""
    if log is None:
        return False

    status = log.status.value if hasattr(log.status, 'value') else str(log.status or '')
    if status not in ACTIONABLE_EMAIL_STATUSES:
        return False

    if log.notification_id:
        return True

    if email_delivery_log_is_skipped(log):
        return False

    return classify_orphan_email_log(log.subject) != 'unsupported'


def email_delivery_log_can_cancel(log: Optional[EmailDeliveryLog]) -> bool:
    """Whether an admin can dismiss a failed delivery log without retrying."""
    if log is None:
        return False

    if email_delivery_log_is_skipped(log):
        return False

    status = log.status.value if hasattr(log.status, 'value') else str(log.status or '')
    return status in ACTIONABLE_EMAIL_STATUSES


def _latest_email_logs_by_notification_id(notification_ids: List[int]) -> Dict[int, EmailDeliveryLog]:
    """Map notification_id -> most recent EmailDeliveryLog row."""
    if not notification_ids:
        return {}

    logs = (
        EmailDeliveryLog.query.filter(EmailDeliveryLog.notification_id.in_(notification_ids))
        .order_by(EmailDeliveryLog.notification_id, EmailDeliveryLog.created_at.desc())
        .all()
    )
    latest: Dict[int, EmailDeliveryLog] = {}
    for log in logs:
        nid = log.notification_id
        if nid is not None and nid not in latest:
            latest[nid] = log
    return latest


def email_delivery_log_needs_attention(
    log: Optional[EmailDeliveryLog],
    *,
    latest_by_notification: Optional[Dict[int, EmailDeliveryLog]] = None,
) -> bool:
    """
    True when a failed/retrying log should appear in the Communication Center alert.

    Excludes intentional skips, superseded retry attempts, and non-actionable states.
    """
    if log is None:
        return False

    if email_delivery_log_is_skipped(log):
        return False

    status = log.status.value if hasattr(log.status, 'value') else str(log.status or '')
    if status not in ACTIONABLE_EMAIL_STATUSES:
        return False

    if log.notification_id:
        latest_map = latest_by_notification
        if latest_map is None:
            latest_map = _latest_email_logs_by_notification_id([log.notification_id])
        latest = latest_map.get(log.notification_id)
        if not latest or latest.id != log.id:
            return False

    return email_delivery_log_can_retry(log) or email_delivery_log_can_cancel(log)


def get_email_delivery_logs_needing_attention() -> List[EmailDeliveryLog]:
    """Failed/retrying/unknown delivery logs that admins should see in Communication Center."""
    candidates = (
        EmailDeliveryLog.query.filter(EmailDeliveryLog.status.in_(ACTIONABLE_EMAIL_STATUSES))
        .order_by(EmailDeliveryLog.created_at.desc())
        .all()
    )
    if not candidates:
        return []

    notification_ids = list({log.notification_id for log in candidates if log.notification_id})
    latest_by_notification = _latest_email_logs_by_notification_id(notification_ids)

    return [
        log
        for log in candidates
        if email_delivery_log_needs_attention(log, latest_by_notification=latest_by_notification)
    ]


def count_email_delivery_logs_needing_attention() -> int:
    """Count of delivery failures that should trigger the Communication Center banner."""
    return len(get_email_delivery_logs_needing_attention())


def get_skipped_email_delivery_logs() -> List[EmailDeliveryLog]:
    """
    Skipped delivery logs for the Communication Center grid (audit trail).

    Includes orphan digests and notification-linked skips when the skip is the
    latest attempt for that notification.
    """
    candidates = (
        EmailDeliveryLog.query.filter(
            EmailDeliveryLog.status.in_(ACTIONABLE_EMAIL_STATUSES + ('cancelled',))
        )
        .order_by(EmailDeliveryLog.created_at.desc())
        .all()
    )
    skipped = [log for log in candidates if email_delivery_log_is_skipped(log)]
    if not skipped:
        return []

    notification_ids = list({log.notification_id for log in skipped if log.notification_id})
    latest_by_notification = _latest_email_logs_by_notification_id(notification_ids)

    return [
        log
        for log in skipped
        if not log.notification_id
        or latest_by_notification.get(log.notification_id) is log
    ]


def cancel_email_delivery_log(log_id: int) -> tuple[bool, str]:
    """Dismiss a failed email delivery log (no resend)."""
    log = EmailDeliveryLog.query.get(log_id)
    if not log:
        return False, 'Email delivery log not found'

    status = log.status.value if hasattr(log.status, 'value') else str(log.status or '')
    if status == 'cancelled':
        return True, 'Email failure already dismissed'

    if status not in ACTIONABLE_EMAIL_STATUSES:
        return False, f'Cannot dismiss email in status: {status}'

    log.status = 'cancelled'
    log.next_retry_at = None
    db.session.commit()
    return True, 'Email failure dismissed'


def admin_cancel_email_delivery_logs(log_ids: Optional[List[int]] = None) -> dict:
    """Dismiss multiple failed delivery logs without retrying."""
    if log_ids:
        logs = EmailDeliveryLog.query.filter(EmailDeliveryLog.id.in_(log_ids)).order_by(
            EmailDeliveryLog.created_at.asc()
        ).all()
    else:
        logs = sorted(get_email_delivery_logs_needing_attention(), key=lambda row: row.created_at or utcnow())
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

    if status not in ACTIONABLE_EMAIL_STATUSES:
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


def _retry_one_log_in_background_thread(app, log_id: int) -> tuple:
    """
    Run a single retry on a worker thread of the bounded pool below.

    Flask's ``current_app``/``db.session`` are context-local, so each thread needs
    its own app context (same pattern as the UPR Excel import background worker in
    ``app/routes/admin/upr_excel_import.py``) — reusing the request thread's context
    across threads would not work, and could cross-contaminate sessions.
    """
    with app.app_context():
        try:
            return admin_retry_email_delivery_log(log_id)
        finally:
            db.session.remove()


def admin_retry_failed_email_delivery_logs(log_ids: Optional[List[int]] = None) -> dict:
    """
    Retry multiple failed/unknown delivery logs. Returns counts for admin UI.

    Each retry is a blocking HTTP call to the Email API that can take up to its ~15s
    client-side timeout (see app.services.email.client). Retrying serially inside a
    single admin request previously meant one slow/unresponsive API call blocked every
    other retry behind it — a backlog of a few dozen failures could hold the request
    (and a DB connection) open for minutes. Here, retries run concurrently on a small
    bounded pool, and the batch itself is capped per call; ``remaining_count`` in the
    result tells the caller whether to invoke this again for the rest. See
    docs/runbooks/email-api-no-response.md.
    """
    if log_ids:
        logs = EmailDeliveryLog.query.filter(EmailDeliveryLog.id.in_(log_ids)).order_by(
            EmailDeliveryLog.created_at.asc()
        ).all()
    else:
        logs = sorted(get_email_delivery_logs_needing_attention(), key=lambda row: row.created_at or utcnow())

    # Filter to retryable logs *before* capping (not after) so repeated calls with the
    # same log_ids/"retry all" (e.g. the UI auto-looping while remaining_count > 0)
    # advance through the backlog: items that succeeded on a previous round drop out
    # of this list on their own, letting the next round's capped batch reach further
    # instead of re-examining the same head-of-list items every time.
    retryable_logs = [log for log in logs if email_delivery_log_can_retry(log)]
    skipped_count = len(logs) - len(retryable_logs)

    batch_ids = [log.id for log in retryable_logs[:EMAIL_RETRY_BATCH_MAX_PER_CALL]]
    remaining_count = max(0, len(retryable_logs) - len(batch_ids))
    retryable_ids = batch_ids
    success_count = 0
    failure_count = 0
    errors: List[str] = []

    if retryable_ids:
        app = current_app._get_current_object()
        max_workers = max(1, min(EMAIL_RETRY_BATCH_MAX_WORKERS, len(retryable_ids)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [
                pool.submit(_retry_one_log_in_background_thread, app, log_id)
                for log_id in retryable_ids
            ]
            for future in concurrent.futures.as_completed(futures):
                try:
                    ok, message = future.result()
                except Exception as exc:
                    ok, message = False, str(exc)
                if ok:
                    success_count += 1
                else:
                    failure_count += 1
                    if message and len(errors) < 5:
                        errors.append(message)

    return {
        'attempted': len(retryable_ids),
        'skipped_count': skipped_count,
        'success_count': success_count,
        'failure_count': failure_count,
        'errors': errors,
        'remaining_count': remaining_count,
    }
