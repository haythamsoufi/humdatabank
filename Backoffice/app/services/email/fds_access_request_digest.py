"""Daily digest emails for FDS members with pending country access requests."""

from __future__ import annotations

from flask import current_app, url_for
from markupsafe import escape

from app.extensions import db
from app.models import EmailDeliveryLog, User
from app.services.app_settings_service import (
    get_auto_approve_access_requests,
    get_email_template,
    get_fds_access_request_digest_enabled,
)
from app.services.country_access_request_service import (
    FDS_ACCESS_REQUEST_DIGEST_SUBJECT_PREFIX,
    pending_country_access_requests_by_fds_member,
)
from app.services.country_service import fds_member_user_display_name
from app.services.email.client import send_email
from app.services.email.delivery import log_email_attempt, mark_email_failed, mark_email_sent
from app.services.email.rendering import render_admin_email_template
from app.services.email.service import get_fds_access_request_digest_default_template
from app.utils.datetime_helpers import format_in_org_timezone, org_day_start_utc
from app.utils.organization_helpers import get_org_copyright_year, get_org_name, get_org_team_email


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

    log = existing_log
    if log is None:
        log = log_email_attempt(None, user.id, user.email, subject)

    try:
        if send_email(
            subject=subject,
            recipients=[user.email],
            html=body,
            cc=_team_email_cc_for_recipient(user.email),
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


def send_fds_access_request_digests() -> int:
    """
    Send daily digest emails to FDS members who have pending access requests.

    Returns the number of digests successfully sent.
    """
    if not get_fds_access_request_digest_enabled():
        return 0
    if get_auto_approve_access_requests():
        return 0

    grouped = pending_country_access_requests_by_fds_member()
    if not grouped:
        return 0

    sent_count = 0
    for fds_user_id, requests in grouped.items():
        if _digest_already_sent_today(fds_user_id):
            continue
        user = User.query.filter_by(id=fds_user_id, active=True).first()
        if not user or not user.email:
            continue
        if send_fds_access_request_digest_email(user, requests):
            sent_count += 1

    if sent_count:
        db.session.commit()
    return sent_count
