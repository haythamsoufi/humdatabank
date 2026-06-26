"""Sample Jinja context for admin email template preview (settings UI)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

from flask import current_app, url_for

from app.services.app_settings_service import EMAIL_TEMPLATE_KEYS
from app.services.email.rendering import _datetimeformat_filter
from app.utils.datetime_helpers import utcnow
from app.utils.organization_helpers import get_org_copyright_year, get_org_name, get_org_team_email

_SECURITY_ALERT_PALETTE = {
    "low": ("#d97706", "#fffbeb", "#f59e0b"),
    "medium": ("#ea580c", "#fff7ed", "#f97316"),
    "high": ("#dc2626", "#fef2f2", "#dc2626"),
    "critical": ("#7f1d1d", "#fef2f2", "#7f1d1d"),
}


def normalize_template_language(lang: Optional[str]) -> str:
    if not lang or not isinstance(lang, str):
        return "en"
    s = lang.strip().lower()
    if not s:
        return "en"
    return s.split("_", 1)[0].split("-", 1)[0]


def _coerce_security_alert_timestamp(
    timestamp: Union[datetime, str, None],
) -> datetime:
    if timestamp is None:
        return utcnow()
    if isinstance(timestamp, str):
        try:
            return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return utcnow()
    return timestamp


def build_security_alert_email_context(
    *,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    description: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_id: Optional[int] = None,
    user_email: Optional[str] = None,
    timestamp: Union[datetime, str, None] = None,
    admin_url: Optional[str] = None,
    org_name: Optional[str] = None,
    copyright_year: Optional[str] = None,
) -> Dict[str, Any]:
    """Build template variables for security alert emails (production + preview)."""
    severity_norm = (severity or "medium").strip().lower()
    header_bg, alert_bg, alert_border = _SECURITY_ALERT_PALETTE.get(
        severity_norm, _SECURITY_ALERT_PALETTE["medium"]
    )
    event_raw = event_type or "Unknown Event"
    timestamp_dt = _coerce_security_alert_timestamp(timestamp)
    formatted_timestamp = _datetimeformat_filter(timestamp_dt) or "N/A"

    return {
        "event_type": event_raw,
        "event_type_display": event_raw.replace("_", " ").title(),
        "severity": severity or "medium",
        "severity_display": (severity or "medium").upper(),
        "header_bg_color": header_bg,
        "alert_bg_color": alert_bg,
        "alert_border_color": alert_border,
        "description": description or "No description provided",
        "ip_address": ip_address,
        "user_id": user_id,
        "user_email": user_email,
        "timestamp": timestamp_dt,
        "formatted_timestamp": formatted_timestamp,
        "admin_url": admin_url or "",
        "org_name": org_name or "",
        "copyright_year": copyright_year or "",
    }


def get_email_template_preview_context(
    template_key: str, template_language: Optional[str] = None
) -> Dict[str, Any]:
    """Build placeholder variables for the given template key (same names as production sends).

    *template_language* is the email body language tab the admin is editing (e.g. ``ar``) so
    :func:`get_org_name` can return the matching localized organization name from branding.
    """
    if template_key not in EMAIL_TEMPLATE_KEYS:
        return {}

    base_url = (current_app.config.get("BASE_URL") or "http://localhost:5000").rstrip("/")
    tlang = normalize_template_language(template_language)
    org_name = get_org_name(locale=tlang)
    copyright_year = get_org_copyright_year()
    sample_details = (
        "<table style=\"width:100%;border-collapse:collapse;margin:8px 0;\">"
        "<tr><th style=\"border:1px solid #ddd;padding:6px;\">Field</th>"
        "<th style=\"border:1px solid #ddd;padding:6px;\">Value</th></tr>"
        "<tr><td style=\"border:1px solid #ddd;padding:6px;\">Example</td>"
        "<td style=\"border:1px solid #ddd;padding:6px;\">Preview sample</td></tr></table>"
    )
    ts = datetime.now(timezone.utc)

    if template_key == "email_template_suggestion_confirmation":
        team_email = get_org_team_email()
        return {
            "submitter_name": "Jamie Example",
            "suggestion_type_display": "New indicator",
            "indicator_name": "Sample indicator",
            "submitted_date": "April 22, 2026 at 10:30 AM",
            "suggestion_details": sample_details,
            "org_name": org_name,
            "copyright_year": copyright_year,
            "team_email": team_email,
        }

    if template_key == "email_template_admin_notification":
        return {
            "submitter_name": "Jamie Example",
            "submitter_email": "submitter@example.org",
            "suggestion_type_display": "New indicator",
            "indicator_name": "Sample indicator",
            "submitted_date": "April 22, 2026 at 10:30 AM",
            "suggestion_details": sample_details,
            "reason": "Sample reason text for preview.",
            "additional_notes": "Optional notes for preview.",
            "admin_url": f"{base_url}{url_for('utilities.view_indicator_suggestion', suggestion_id=0)}",
            "org_name": org_name,
            "copyright_year": copyright_year,
        }

    if template_key == "email_template_security_alert":
        return build_security_alert_email_context(
            event_type="preview_event",
            severity="medium",
            description="This is sample security alert text for preview.",
            ip_address="203.0.113.10",
            user_email="user@example.org",
            user_id=12345,
            timestamp=ts,
            admin_url=f"{base_url}/admin/security/dashboard",
            org_name=org_name,
            copyright_year=copyright_year,
        )

    if template_key == "email_template_welcome":
        return {
            "user_name": "Jamie",
            "dashboard_url": f"{base_url}/",
            "notifications_url": f"{base_url}/notifications",
            "documentation_url": f"{base_url}/help/docs/",
            "org_name": org_name,
            "copyright_year": copyright_year,
        }

    if template_key == "email_template_notification":
        return {
            "title": "Preview notification title",
            "message": (
                "This is sample notification body text for preview. "
                "It can span multiple sentences."
            ),
            "org_name": org_name,
        }

    return {}
