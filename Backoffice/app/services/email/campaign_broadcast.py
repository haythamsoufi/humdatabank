"""Render and send Communication Center campaign broadcast emails."""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional

from flask import current_app
from sqlalchemy import and_

from app.models import Notification, NotificationPreferences, User
from app.services.campaign_email_templates_service import (
    get_campaign_email_template,
    normalize_campaign_email_template_key,
)
from app.services.email.client import send_email
from app.services.email.delivery import log_email_attempt, mark_email_failed, mark_email_sent
from app.services.email.rendering import render_admin_email_template
from app.services.notification.core import IN_APP_ONLY_NOTIFICATION_TYPES
from app.utils.datetime_helpers import utcnow
from app.utils.organization_helpers import get_org_copyright_year, get_org_name


def build_campaign_email_context(
    *,
    user,
    title: str,
    message: str,
    language: str = "en",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base_url = (current_app.config.get("BASE_URL") or "http://localhost:5000").rstrip("/")
    org_name = get_org_name(locale=language)
    ctx: Dict[str, Any] = {
        "title": title,
        "message": message,
        "user_name": (getattr(user, "name", None) or getattr(user, "email", None) or "User"),
        "user_email": getattr(user, "email", None) or "",
        "org_name": org_name,
        "org_short_name": org_name,
        "copyright_year": get_org_copyright_year(),
        "dashboard_url": f"{base_url}/",
        "documentation_url": f"{base_url}/help/docs/",
        "reporting_url": f"{base_url}/",
        "action_url": f"{base_url}/",
        "period_name": "",
        "deadline_date": "",
    }
    if extra:
        ctx.update(extra)
    return ctx


def render_campaign_broadcast_email(
    template_key: str,
    *,
    user,
    title: str,
    message: str,
    language: str = "en",
    template_html_override: Optional[str] = None,
) -> str:
    default_html = """
    <!DOCTYPE html><html><body><h1>{{ title }}</h1><p>Hello {{ user_name }},</p><p>{{ message }}</p></body></html>
    """
    override = (template_html_override or "").strip()
    if override:
        template_html = override
    else:
        template_html = get_campaign_email_template(
            template_key,
            default=default_html,
            language=language,
        )
    context = build_campaign_email_context(user=user, title=title, message=message, language=language)
    return render_admin_email_template(template_html, **context)


def _should_send_campaign_email(
    user,
    notification,
    *,
    override_preferences: bool,
    preferences_map: Optional[Dict[int, NotificationPreferences]] = None,
) -> bool:
    if notification.notification_type in IN_APP_ONLY_NOTIFICATION_TYPES:
        return False
    if override_preferences:
        return True

    preferences = (preferences_map or {}).get(user.id)
    if not preferences:
        preferences = NotificationPreferences.query.filter_by(user_id=user.id).first()
    if not preferences or not preferences.email_notifications:
        return False

    if preferences.notification_frequency != "instant":
        urgent_priorities = {"high", "urgent"}
        if (notification.priority or "normal").lower() not in urgent_priorities:
            return False

    if preferences.notification_types_enabled:
        ntype = notification.notification_type.value
        if ntype not in preferences.notification_types_enabled:
            return False
    return True


def send_campaign_broadcast_notification_email(
    user,
    notification,
    *,
    template_key: str,
    title: str,
    message: str,
    override_preferences: bool = False,
    preferences_map: Optional[Dict[int, NotificationPreferences]] = None,
    template_html_override: Optional[str] = None,
) -> bool:
    """Send one campaign-template email for an existing notification."""
    if not user or not getattr(user, "email", None):
        return False
    if not normalize_campaign_email_template_key(template_key):
        return False
    if not _should_send_campaign_email(
        user,
        notification,
        override_preferences=override_preferences,
        preferences_map=preferences_map,
    ):
        return False

    language = getattr(user, "preferred_language", None) or "en"
    body = render_campaign_broadcast_email(
        template_key,
        user=user,
        title=title,
        message=message,
        language=language,
        template_html_override=template_html_override,
    )
    if notification.priority in ("high", "urgent"):
        subject = title
    else:
        subject = f"New Notification: {title}"
    importance = (
        (notification.priority or "normal").lower()
        if notification.priority in ("high", "urgent")
        else None
    )

    log = log_email_attempt(notification.id, user.id, user.email, subject)
    try:
        filtered_out: List[str] = []
        success = send_email(
            subject=subject,
            recipients=[user.email],
            html=body,
            sender=current_app.config.get(
                "MAIL_NOREPLY_SENDER", current_app.config["MAIL_DEFAULT_SENDER"]
            ),
            importance=importance,
            _filtered_out=filtered_out,
        )
        if success:
            mark_email_sent(log.id)
            return True
        if filtered_out:
            return False
        mark_email_failed(log.id, "Email send returned False", retry=False)
    except Exception as exc:
        mark_email_failed(log.id, str(exc), retry=False)
        current_app.logger.warning(
            "Campaign broadcast email failed for user %s notification %s: %s",
            user.id,
            notification.id,
            exc,
        )
    return False


def send_campaign_broadcast_emails_for_users(
    *,
    user_ids: List[int],
    template_key: str,
    title: str,
    message: str,
    notification_type,
    override_preferences: bool = False,
    template_html_override: Optional[str] = None,
) -> int:
    """
    Send campaign-template emails for notifications created in the last few seconds.
    Returns the number of emails successfully sent.
    """
    if not user_ids or not normalize_campaign_email_template_key(template_key):
        return 0

    recent_cutoff = utcnow() - timedelta(seconds=5)
    notifications = Notification.query.filter(
        and_(
            Notification.user_id.in_(user_ids),
            Notification.notification_type == notification_type,
            Notification.created_at >= recent_cutoff,
        )
    ).all()
    if not notifications:
        return 0

    users = User.query.filter(User.id.in_(user_ids)).all()
    user_map = {u.id: u for u in users}
    preferences_list = NotificationPreferences.query.filter(
        NotificationPreferences.user_id.in_(user_ids)
    ).all()
    preferences_map = {p.user_id: p for p in preferences_list}

    sent = 0
    for notification in notifications:
        user = user_map.get(notification.user_id)
        if not user:
            continue
        if send_campaign_broadcast_notification_email(
            user,
            notification,
            template_key=template_key,
            title=title,
            message=message,
            override_preferences=override_preferences,
            preferences_map=preferences_map,
            template_html_override=template_html_override,
        ):
            sent += 1
    return sent
