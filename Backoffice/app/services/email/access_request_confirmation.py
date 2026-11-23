"""Confirmation email to the user who submitted a country access request."""

from __future__ import annotations

from typing import Optional

from flask import current_app
from markupsafe import escape
from sqlalchemy.orm import joinedload

from app.models import Country, CountryAccessRequest, EmailDeliveryLog, User
from app.services.email.client import send_email
from app.services.email.delivery import (
    log_email_attempt,
    mark_email_failed_or_unknown,
    mark_email_sent,
)
from app.services.email.rendering import render_admin_email_template
from app.services.platform.app_settings_service import (
    get_access_request_confirmation_email_enabled,
    get_email_template,
)
from app.utils.database.transactions import register_post_commit
from app.utils.organization.organization_helpers import (
    get_org_copyright_year,
    get_org_name,
    get_org_team_email,
)

# Stable English prefix so delivery-log retry can recognize this email.
# Country names follow the em dash, separated by a middle dot.
ACCESS_REQUEST_CONFIRMATION_SUBJECT_PREFIX = "Country access request received — "
ACCESS_REQUEST_CONFIRMATION_TEMPLATE_KEY = "email_template_access_request_confirmation"
_MAX_SUBJECT_LENGTH = 240

DEFAULT_ACCESS_REQUEST_CONFIRMATION_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Country access request received</title>
    <style>
        body { margin: 0; padding: 0; background: #eef2f7; color: #1f2937;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
          line-height: 1.65; -webkit-font-smoothing: antialiased; }
        .email-outer { max-width: 960px; width: 100%; margin: 0 auto; padding: 28px 20px; box-sizing: border-box; }
        .email-card { background: #ffffff; border: 1px solid #e2e8f0; }
        .email-header { background: #0d9488; color: #ffffff; padding: 32px 40px; text-align: center; }
        .email-header h1 { margin: 0 0 8px; font-size: 26px; font-weight: 600; letter-spacing: -0.02em; }
        .email-header h2 { margin: 0; font-size: 18px; font-weight: 500; opacity: 0.95; }
        .email-body { padding: 36px 40px 32px; background: #ffffff; }
        .email-body p { margin: 0 0 16px; }
        .email-body ul { margin: 8px 0 16px; padding-left: 22px; }
        .email-body li { margin: 8px 0; }
        .email-footer { padding: 22px 40px; text-align: center; font-size: 12px; color: #64748b;
          background: #f8fafc; border-top: 1px solid #e2e8f0; }
        .email-footer p { margin: 6px 0; }
        .action-button { display: inline-block; background: #0d9488; color: #ffffff !important; padding: 12px 24px;
          text-decoration: none; font-weight: 600; font-size: 15px; margin: 8px 0 0; border: 1px solid #0f766e; }
        .muted { color: #64748b; font-size: 13px; }
    </style>
</head>
<body>
    <div class="email-outer">
        <div class="email-card">
            <div class="email-header">
                <h1>{{ org_name }}</h1>
                <h2>Country access request received</h2>
            </div>
            <div class="email-body">
                <p>Hello {{ user_name }},</p>
                <p>We received your request for access to the following
                {% if request_count == 1 %}country{% else %}countries{% endif %}:</p>
                <ul>
                    {{ country_list_html | safe }}
                </ul>
                <p>An administrator will review your request. You will receive another message when access is granted.</p>
                <p><a href="{{ dashboard_url }}" class="action-button">Open the dashboard</a></p>
                {% if team_email %}
                <p>If you have questions, contact us at <a href="mailto:{{ team_email }}">{{ team_email }}</a>.</p>
                {% endif %}
            </div>
            <div class="email-footer">
                <p>&copy; {{ copyright_year }} {{ org_name }}. All rights reserved.</p>
            </div>
        </div>
    </div>
</body>
</html>
"""


def confirmation_subject(country_names: list[str]) -> str:
    """Build the inbox subject. The prefix is stable so failed sends can be retried."""
    label = " · ".join(name for name in country_names if name) or "your selected country"
    subject = f"{ACCESS_REQUEST_CONFIRMATION_SUBJECT_PREFIX}{label}"
    if len(subject) > _MAX_SUBJECT_LENGTH:
        subject = subject[: _MAX_SUBJECT_LENGTH - 3].rstrip() + "..."
    return subject


def country_names_from_confirmation_subject(subject: Optional[str]) -> list[str]:
    """Parse country names from a confirmation subject. Empty when truncated or unrecognized."""
    text = (subject or "").strip()
    prefix = ACCESS_REQUEST_CONFIRMATION_SUBJECT_PREFIX
    if not text.startswith(prefix):
        return []
    rest = text[len(prefix):].strip()
    if not rest or rest.endswith("..."):
        return []
    return [part.strip() for part in rest.split(" · ") if part.strip()]


def queue_access_request_confirmation_email(user_id: int, request_ids: list[int]) -> bool:
    """
    Send the confirmation after the current request transaction commits.

    Delivery logging commits the session, so the send must not run while the
    access-request row is still uncommitted. Returns True when a send was queued.
    """
    ids = [int(request_id) for request_id in (request_ids or []) if request_id]
    if not user_id or not ids:
        return False
    if not get_access_request_confirmation_email_enabled():
        current_app.logger.info(
            "Country access request confirmation email disabled; not sending to user %s (%d request(s))",
            user_id,
            len(ids),
        )
        return False
    register_post_commit(
        send_access_request_confirmation_for_request_ids,
        int(user_id),
        ids,
    )
    current_app.logger.info(
        "Queued country access request confirmation email for user %s (%d request(s): %s)",
        user_id,
        len(ids),
        ids,
    )
    return True


def send_access_request_confirmation_for_request_ids(
    user_id: int,
    request_ids: list[int],
    existing_log: Optional[EmailDeliveryLog] = None,
    *,
    respect_enabled: bool = True,
) -> bool:
    """Send one confirmation covering the given access-request rows. Never raises."""
    try:
        return _send_access_request_confirmation(
            user_id,
            request_ids,
            existing_log=existing_log,
            respect_enabled=respect_enabled,
        )
    except Exception:
        current_app.logger.exception(
            "Country access request confirmation email failed for user %s",
            user_id,
        )
        return False


def retry_access_request_confirmation_email(user: User, log: EmailDeliveryLog) -> bool:
    """Resend a failed confirmation from its delivery-log subject."""
    if not user or not log:
        return False
    requests = _requests_matching_confirmation_subject(user, log.subject, anchor=log.created_at)
    if not requests:
        from app.services.email.delivery import mark_email_failed

        mark_email_failed(
            log.id,
            "Could not match this confirmation to a country access request",
            retry=False,
        )
        current_app.logger.warning(
            "Country access request confirmation retry skipped for %s: no matching request (log %s)",
            user.email,
            log.id,
        )
        return False
    return send_access_request_confirmation_for_request_ids(
        user.id,
        [req.id for req in requests],
        existing_log=log,
        respect_enabled=False,
    )


def _send_access_request_confirmation(
    user_id: int,
    request_ids: list[int],
    *,
    existing_log: Optional[EmailDeliveryLog],
    respect_enabled: bool,
) -> bool:
    ids = [int(request_id) for request_id in (request_ids or []) if request_id]
    if respect_enabled and not get_access_request_confirmation_email_enabled():
        current_app.logger.info(
            "Country access request confirmation email disabled; not sending to user %s",
            user_id,
        )
        return False

    user = User.query.get(user_id)
    if not user or not user.email:
        current_app.logger.warning(
            "Cannot send country access request confirmation: user %s is missing an email",
            user_id,
        )
        return False

    requests = _load_requests(ids)
    if not requests:
        current_app.logger.warning(
            "Cannot send country access request confirmation to %s: requests %s were not found",
            user.email,
            ids,
        )
        return False

    country_names = [_country_label(req) for req in requests]
    subject = confirmation_subject(country_names)
    from app.i18n import resolve_supported_language

    locale = resolve_supported_language(getattr(user, "preferred_language", None) or "en") or "en"
    org_name = get_org_name(locale=locale)
    user_name = user.name or user.email.split("@")[0]
    base_url = (current_app.config.get("BASE_URL") or "http://localhost:5000").rstrip("/")
    html_template = get_email_template(
        ACCESS_REQUEST_CONFIRMATION_TEMPLATE_KEY,
        DEFAULT_ACCESS_REQUEST_CONFIRMATION_TEMPLATE,
        language=locale,
    )
    body = render_admin_email_template(
        html_template,
        user_name=user_name,
        request_count=len(requests),
        country_names=" · ".join(country_names),
        country_list_html=_country_list_html(requests),
        dashboard_url=f"{base_url}/",
        team_email=get_org_team_email() or "",
        org_name=org_name,
        copyright_year=get_org_copyright_year(),
    )

    log = existing_log or log_email_attempt(None, user.id, user.email, subject)
    if not log:
        current_app.logger.error(
            "Cannot send country access request confirmation to %s: delivery log was not created",
            user.email,
        )
        return False

    failure_info: list = []
    try:
        sent = send_email(
            subject=subject,
            recipients=[user.email],
            html=body,
            sender=current_app.config.get("MAIL_DEFAULT_SENDER"),
            _failure_info=failure_info,
        )
    except Exception as exc:
        mark_email_failed_or_unknown(log.id, str(exc), failure_info[-1] if failure_info else None)
        current_app.logger.error(
            "Error sending country access request confirmation to %s: %s",
            user.email,
            exc,
            exc_info=True,
        )
        return False

    if sent:
        mark_email_sent(log.id)
        current_app.logger.info(
            "Country access request confirmation email sent to %s for %s (requests %s)",
            user.email,
            ", ".join(country_names),
            [req.id for req in requests],
        )
        return True

    mark_email_failed_or_unknown(
        log.id,
        "Email API returned failure",
        failure_info[-1] if failure_info else None,
    )
    current_app.logger.error(
        "Failed to send country access request confirmation to %s for requests %s",
        user.email,
        [req.id for req in requests],
    )
    return False


def _load_requests(request_ids: list[int]) -> list:
    if not request_ids:
        return []
    rows = (
        CountryAccessRequest.query.options(joinedload(CountryAccessRequest.country))
        .filter(CountryAccessRequest.id.in_(request_ids))
        .all()
    )
    by_id = {row.id: row for row in rows}
    return [by_id[request_id] for request_id in request_ids if request_id in by_id]


def _country_label(req) -> str:
    country = req.country
    if country and country.name:
        return country.name
    return f"Country {req.country_id}"


def _country_list_html(requests) -> str:
    items = []
    for req in requests:
        label = escape(_country_label(req))
        message = (req.request_message or "").strip()
        note = f'<br><span class="muted">{escape(message)}</span>' if message else ""
        items.append(f"<li>{label}{note}</li>")
    return "\n".join(items)


def _requests_matching_confirmation_subject(user: User, subject: Optional[str], *, anchor=None) -> list:
    names = country_names_from_confirmation_subject(subject)
    if not user or not names:
        return []
    rows = (
        CountryAccessRequest.query.options(joinedload(CountryAccessRequest.country))
        .join(Country, Country.id == CountryAccessRequest.country_id)
        .filter(
            CountryAccessRequest.user_id == user.id,
            Country.name.in_(names),
        )
        .all()
    )
    chosen = []
    for name in names:
        candidates = [row for row in rows if row.country and row.country.name == name]
        if not candidates:
            continue
        candidates.sort(key=lambda row: _distance_from_anchor(anchor, row.created_at))
        chosen.append(candidates[0])
    return chosen


def _distance_from_anchor(anchor, moment) -> float:
    if anchor is None or moment is None:
        return float("inf")
    try:
        return abs((moment - anchor).total_seconds())
    except TypeError:
        return float("inf")
