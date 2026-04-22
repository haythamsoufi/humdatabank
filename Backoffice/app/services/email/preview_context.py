"""Sample Jinja context for admin email template preview (settings UI)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from flask import current_app

from app.services.app_settings_service import EMAIL_TEMPLATE_KEYS
from app.utils.organization_helpers import get_org_copyright_year, get_org_name


def normalize_template_language(lang: Optional[str]) -> str:
    if not lang or not isinstance(lang, str):
        return "en"
    s = lang.strip().lower()
    if not s:
        return "en"
    return s.split("_", 1)[0].split("-", 1)[0]


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
        return {
            "submitter_name": "Jamie Example",
            "suggestion_type_display": "New indicator",
            "indicator_name": "Sample indicator",
            "submitted_date": "April 22, 2026 at 10:30 AM",
            "suggestion_details": sample_details,
            "org_name": org_name,
            "copyright_year": copyright_year,
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
            "admin_url": f"{base_url}/admin/indicator-suggestions/0",
            "org_name": org_name,
            "copyright_year": copyright_year,
        }

    if template_key == "email_template_security_alert":
        return {
            "event_type": "preview_event",
            "severity": "medium",
            "description": "This is sample security alert text for preview.",
            "ip_address": "203.0.113.10",
            "user_email": "user@example.org",
            "user_id": 12345,
            "timestamp": ts,
            "admin_url": f"{base_url}/admin/security/dashboard",
            "org_name": org_name,
            "copyright_year": copyright_year,
        }

    if template_key == "email_template_welcome":
        return {
            "user_name": "Jamie",
            "dashboard_url": f"{base_url}/",
            "notifications_url": f"{base_url}/notifications",
            "documentation_url": f"{base_url}/admin/docs/",
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
