"""Daily digest emails for FDS members with pending country access requests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Optional

from flask import current_app, url_for
from markupsafe import escape

from app.extensions import db
from app.models import EmailDeliveryLog, User
from app.services.app_settings_service import (
    get_auto_approve_access_requests,
    get_email_template,
    get_fds_access_request_digest_enabled,
    get_fds_access_request_digest_local_hour,
)
from app.services.country_access_request_service import (
    FDS_ACCESS_REQUEST_DIGEST_SUBJECT_PREFIX,
    pending_country_access_requests_by_fds_member,
    pending_country_access_requests_query,
)
from app.services.country_service import fds_member_user_display_name
from app.services.email.client import send_email
from app.services.email.delivery import (
    log_email_attempt,
    mark_email_failed,
    mark_email_sent,
    mark_email_skipped,
)
from app.services.email.rendering import render_admin_email_template
from app.services.email.service import get_fds_access_request_digest_default_template
from app.utils.datetime_helpers import (
    format_in_org_timezone,
    now_in_org_timezone,
    org_day_start_utc,
)
from app.utils.organization_helpers import get_org_copyright_year, get_org_name, get_org_team_email


@dataclass
class FdsDigestRunResult:
    """Outcome of one scheduled FDS digest job invocation at the configured Geneva hour."""

    ran: bool = False
    configured_hour: int = 0
    geneva_hour: int = 0
    skip_reason: Optional[str] = None
    pending_total: int = 0
    pending_without_fds_member: int = 0
    fds_member_count: int = 0
    sent_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    details: list[str] = field(default_factory=list)


def _parse_digest_request_count(subject: Optional[str]) -> Optional[int]:
    text = (subject or "").strip()
    marker = " pending request(s)"
    if marker not in text:
        return None
    prefix = FDS_ACCESS_REQUEST_DIGEST_SUBJECT_PREFIX
    if not text.startswith(prefix):
        return None
    count_part = text[len(prefix):].split(marker, 1)[0].strip()
    try:
        return int(count_part)
    except ValueError:
        return None


def get_fds_access_request_digest_last_sent_summary() -> dict[str, Any]:
    """
    Brief summary of the most recent Geneva-calendar-day batch of digest emails sent
    to FDS members (excludes run-summary audit rows).
    """
    latest = (
        EmailDeliveryLog.query.filter(
            EmailDeliveryLog.status == "sent",
            EmailDeliveryLog.subject.like(f"{FDS_ACCESS_REQUEST_DIGEST_SUBJECT_PREFIX}% pending request(s)"),
        )
        .order_by(EmailDeliveryLog.sent_at.desc().nullslast())
        .first()
    )
    if not latest or not latest.sent_at:
        return {
            "sent_at": None,
            "sent_at_display": "",
            "recipients": [],
            "recipient_count": 0,
        }

    day_start = org_day_start_utc(latest.sent_at)
    day_end = day_start + timedelta(days=1)

    logs = (
        EmailDeliveryLog.query.filter(
            EmailDeliveryLog.status == "sent",
            EmailDeliveryLog.subject.like(f"{FDS_ACCESS_REQUEST_DIGEST_SUBJECT_PREFIX}% pending request(s)"),
            EmailDeliveryLog.sent_at >= day_start,
            EmailDeliveryLog.sent_at < day_end,
        )
        .order_by(EmailDeliveryLog.sent_at.desc())
        .all()
    )

    user_ids = {log.user_id for log in logs if log.user_id}
    users_by_id = {}
    if user_ids:
        users_by_id = {u.id: u for u in User.query.filter(User.id.in_(user_ids)).all()}

    recipients = []
    seen_user_ids: set[int] = set()
    for log in logs:
        if not log.user_id or log.user_id in seen_user_ids:
            continue
        seen_user_ids.add(log.user_id)
        user = users_by_id.get(log.user_id)
        recipients.append(
            {
                "name": fds_member_user_display_name(user) if user else f"User {log.user_id}",
                "email": log.email_address or (user.email if user else ""),
                "request_count": _parse_digest_request_count(log.subject),
            }
        )

    return {
        "sent_at": latest.sent_at,
        "sent_at_display": format_in_org_timezone(latest.sent_at, "%Y-%m-%d %H:%M"),
        "recipients": recipients,
        "recipient_count": len(recipients),
    }


def _team_email_cc_for_recipient(recipient_email: str) -> list[str] | None:
    """CC the org team inbox when it differs from the primary recipient."""
    team_email = get_org_team_email()
    if not team_email:
        return None
    team_lower = team_email.strip().lower()
    recipient_lower = (recipient_email or "").strip().lower()
    if not team_lower or team_lower == recipient_lower:
        return None
    return [team_email]


def _digest_already_sent_today(user_id: int) -> bool:
    today_start = org_day_start_utc()
    return (
        EmailDeliveryLog.query.filter(
            EmailDeliveryLog.user_id == user_id,
            EmailDeliveryLog.subject.like(f"{FDS_ACCESS_REQUEST_DIGEST_SUBJECT_PREFIX}%"),
            EmailDeliveryLog.status == 'sent',
            EmailDeliveryLog.sent_at >= today_start,
        )
        .limit(1)
        .first()
        is not None
    )


def _build_request_rows_html(requests) -> str:
    rows = []
    for req in requests:
        user = req.user
        country = req.country
        user_label = escape(
            (user.name or user.email or f"User {req.user_id}") if user else f"User {req.user_id}"
        )
        country_label = escape(country.name if country else f"Country {req.country_id}")
        created = format_in_org_timezone(req.created_at) if req.created_at else ''
        message = (req.request_message or '').strip()
        message_html = (
            f'<br><span class="muted">Note: {escape(message)}</span>' if message else ''
        )
        rows.append(
            f'<tr>'
            f'<td>{user_label}</td>'
            f'<td>{country_label}</td>'
            f'<td>{escape(created)}{message_html}</td>'
            f'</tr>'
        )
    return '\n'.join(rows)


def _begin_fds_digest_delivery_log(
    user: User,
    subject: str,
    existing_log: Optional[EmailDeliveryLog] = None,
) -> Optional[EmailDeliveryLog]:
    """Create or reuse an email delivery log (no in-app notification)."""
    if not user or not user.email:
        return None
    if existing_log:
        return existing_log
    return log_email_attempt(None, user.id, user.email, subject)


def _record_fds_digest_skip(
    user: User,
    *,
    subject: str,
    reason: str,
) -> None:
    log = _begin_fds_digest_delivery_log(user, subject)
    if log:
        mark_email_skipped(log.id, reason)


def _log_fds_digest_run(result: FdsDigestRunResult, *, manual: bool = False) -> None:
    """Structured application log for Azure / prod troubleshooting."""
    logger = current_app.logger
    trigger = "manual" if manual else "scheduled"
    if not result.ran:
        if result.skip_reason:
            logger.info(
                'FDS access request digest not run (%s): %s (Geneva hour=%s, configured=%s)',
                trigger,
                result.skip_reason,
                result.geneva_hour,
                result.configured_hour,
            )
        return

    logger.info(
        'FDS access request digest run (%s) at %s (configured hour=%s): '
        'pending=%d, without_fds_member=%d, fds_members=%d, sent=%d, skipped=%d, failed=%d%s',
        trigger,
        format_in_org_timezone(now_in_org_timezone(), '%Y-%m-%d %H:%M'),
        result.configured_hour,
        result.pending_total,
        result.pending_without_fds_member,
        result.fds_member_count,
        result.sent_count,
        result.skipped_count,
        result.failed_count,
        f"; details: {' | '.join(result.details)}" if result.details else '',
    )


def _pending_digest_counts() -> tuple[int, int]:
    """Return (total pending, pending on countries without an FDS member)."""
    pending = pending_country_access_requests_query().all()
    without_fds = 0
    for req in pending:
        country = req.country
        if not country or not country.fds_member_user_id:
            without_fds += 1
    return len(pending), without_fds


def send_fds_access_request_digest_email(user: User, requests, existing_log=None) -> bool:
    """Send one FDS member digest listing pending access requests for their countries."""
    if not user or not user.email or not requests:
        return False

    count = len(requests)
    subject = f"{FDS_ACCESS_REQUEST_DIGEST_SUBJECT_PREFIX}{count} pending request(s)"
    base_url = current_app.config.get('BASE_URL', 'http://localhost:5000').rstrip('/')
    access_requests_url = f"{base_url}{url_for('user_management.access_requests')}"
    org_name = get_org_name()
    copyright_year = get_org_copyright_year()
    user_name = fds_member_user_display_name(user)

    default_template = get_fds_access_request_digest_default_template()
    html_template = get_email_template('email_template_fds_access_request_digest', default_template)
    body = render_admin_email_template(
        html_template,
        user_name=user_name,
        request_count=count,
        request_rows_html=_build_request_rows_html(requests),
        access_requests_url=access_requests_url,
        org_name=org_name,
        copyright_year=copyright_year,
    )

    log = _begin_fds_digest_delivery_log(user, subject, existing_log=existing_log)
    if not log:
        return False

    try:
        if send_email(
            subject=subject,
            recipients=[user.email],
            html=body,
            cc=_team_email_cc_for_recipient(user.email),
            expose_recipients_in_to=True,
        ):
            mark_email_sent(log.id)
            return True
        mark_email_failed(log.id, 'Email API returned failure')
        return False
    except Exception as exc:
        mark_email_failed(log.id, str(exc))
        current_app.logger.error(
            "Error sending FDS access request digest to %s: %s",
            user.email,
            exc,
            exc_info=True,
        )
        return False


def run_fds_access_request_digest_job(*, manual: bool = False) -> FdsDigestRunResult:
    """
    Scheduled entry point: run only at the configured Geneva hour, with application logging.
    Email delivery logs record send/skip/fail outcomes; no in-app notifications are created.

    When ``manual=True`` (admin-triggered), bypasses the hour gate, the enabled
    setting, and the once-per-day idempotency guard.
    """
    local_now = now_in_org_timezone()
    configured_hour = get_fds_access_request_digest_local_hour()
    result = FdsDigestRunResult(
        configured_hour=configured_hour,
        geneva_hour=local_now.hour,
    )

    if not manual and not get_fds_access_request_digest_enabled():
        result.skip_reason = 'Digest emails disabled in settings'
        _log_fds_digest_run(result, manual=manual)
        return result

    if get_auto_approve_access_requests():
        result.skip_reason = 'Auto-approve access requests is enabled (digest suppressed)'
        _log_fds_digest_run(result, manual=manual)
        return result

    if not manual and local_now.hour != configured_hour:
        current_app.logger.debug(
            'FDS access request digest: Geneva hour %s != configured %s — waiting',
            local_now.hour,
            configured_hour,
        )
        return result

    result.ran = True
    result.pending_total, result.pending_without_fds_member = _pending_digest_counts()
    grouped = pending_country_access_requests_by_fds_member()
    result.fds_member_count = len(grouped)

    if not grouped:
        if result.pending_total:
            result.skip_reason = (
                f'{result.pending_total} pending request(s), but none on countries with an '
                f'assigned FDS member ({result.pending_without_fds_member} without FDS member)'
            )
        else:
            result.skip_reason = 'No pending country access requests'
        _log_fds_digest_run(result, manual=manual)
        db.session.commit()
        return result

    for fds_user_id, requests in grouped.items():
        user_label = f'user {fds_user_id}'
        if not manual and _digest_already_sent_today(fds_user_id):
            result.skipped_count += 1
            detail = f'{user_label}: already sent today'
            result.details.append(detail)
            user = User.query.filter_by(id=fds_user_id, active=True).first()
            if user and user.email:
                _record_fds_digest_skip(
                    user,
                    subject=f'{FDS_ACCESS_REQUEST_DIGEST_SUBJECT_PREFIX}skipped',
                    reason='Already sent today',
                )
            continue

        user = User.query.filter_by(id=fds_user_id, active=True).first()
        if not user or not user.email:
            result.skipped_count += 1
            detail = f'{user_label}: inactive or missing email'
            result.details.append(detail)
            if user and user.email:
                _record_fds_digest_skip(
                    user,
                    subject=f'{FDS_ACCESS_REQUEST_DIGEST_SUBJECT_PREFIX}skipped',
                    reason='Inactive user or missing email address',
                )
            continue

        user_label = user.email
        if send_fds_access_request_digest_email(user, requests):
            result.sent_count += 1
            result.details.append(f'{user_label}: sent ({len(requests)} request(s))')
        else:
            result.failed_count += 1
            result.details.append(f'{user_label}: send failed')

    _log_fds_digest_run(result, manual=manual)
    db.session.commit()
    return result


def send_fds_access_request_digests() -> int:
    """
    Send daily digest emails to FDS members who have pending access requests.

    Returns the number of digests successfully sent.
    """
    result = run_fds_access_request_digest_job()
    return result.sent_count
