"""Sample previews for system notification copy and instant notification emails."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from flask_babel import gettext as _

from app.models.enums import NotificationType
from app.services.notification.core import (
    IN_APP_ONLY_NOTIFICATION_TYPES,
    translate_notification_message,
)
from app.utils.organization_helpers import get_org_name


_PREVIEW_VARIANT_SUFFIXES: Dict[str, List[tuple[str, str]]] = {
    "assignment_submitted": [
        ("", _("Other focal points")),
        ("submitter", _("Submitter")),
        ("team_email", _("Team email")),
        ("admin", _("Admin channel")),
    ],
    "assignment_sent_for_review": [("", _("Delegation focal point")), ("admin", _("Admin FYI"))],
    "document_uploaded": [("", _("Uploaded")), ("pending", _("Pending review"))],
}

_SAMPLE_PARAMS: Dict[str, Any] = {
    "template": "Unified Country Report",
    "assignment_title": "Unified Country Report \u2013 Jan-Jun 2026",
    "period": "Jan-Jun 2026",
    "country": "Example National Society",
    "country_name": "Example Country",
    "submitter_name": "Jamie Example",
    "actor_name": "Alex Admin",
    "submitter": "public@example.org",
    "due_date": "2026-06-30",
    "document": "Annual Report.pdf",
    "document_type": "Supporting document",
    "user_name": "Alex Admin",
    "entity": "Example National Society",
    "count": 3,
    "frequency": "Daily",
    "custom_title": "Sample admin message title",
    "message": "Sample admin message body for preview.",
}


def _translation_key_exists(key: str) -> bool:
    translated = translate_notification_message(key, locale="en")
    return bool(translated) and translated != key


def _variant_keys(type_key: str, suffix: str) -> tuple[str, str]:
    if suffix:
        return (
            f"notification.{type_key}.{suffix}.title",
            f"notification.{type_key}.{suffix}.message",
        )
    return (
        f"notification.{type_key}.title",
        f"notification.{type_key}.message",
    )


def list_notification_preview_variants(type_key: str) -> List[Dict[str, Any]]:
    """Return previewable title/message variants for a notification type key."""
    configured = _PREVIEW_VARIANT_SUFFIXES.get(type_key, [("", _("Default"))])
    variants: List[Dict[str, Any]] = []
    for suffix, label in configured:
        title_key, message_key = _variant_keys(type_key, suffix)
        if _translation_key_exists(title_key) and _translation_key_exists(message_key):
            variants.append(
                {
                    "id": suffix or "default",
                    "label": str(label),
                    "title_key": title_key,
                    "message_key": message_key,
                }
            )
    return variants


def _resolve_notification_type(type_key: str) -> Optional[NotificationType]:
    try:
        return NotificationType(type_key)
    except ValueError:
        return None


def _sample_params_for_locale(locale: Optional[str]) -> Dict[str, Any]:
    params = dict(_SAMPLE_PARAMS)
    params["org_name"] = get_org_name(locale=locale or "en")
    return params


def render_notification_preview(
    type_key: str,
    *,
    variant_id: str = "default",
    locale: Optional[str] = None,
    user_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build translated notification copy and optional instant-email HTML for admin preview.

    Returns dict with title, message, email_html (or None when in-app-only), and metadata.
    """
    variants = list_notification_preview_variants(type_key)
    variant = next((v for v in variants if v["id"] == variant_id), None)
    if not variant and variants:
        variant = variants[0]
    if not variant:
        raise ValueError(f"No preview variants for notification type '{type_key}'.")

    locale_to_use = (locale or "en").strip().lower() or "en"
    params = _sample_params_for_locale(locale_to_use)

    title = translate_notification_message(
        variant["title_key"], params, locale=locale_to_use
    )
    message = translate_notification_message(
        variant["message_key"], params, locale=locale_to_use
    )

    nt = _resolve_notification_type(type_key)
    priority = "normal"
    if nt is not None:
        from app.services.platform.app_settings_service import get_notification_priority

        priority = get_notification_priority(nt, default="normal")

    email_html = None
    sends_email = nt is None or nt not in IN_APP_ONLY_NOTIFICATION_TYPES
    if sends_email:
        from types import SimpleNamespace

        from app.services.notification.emails import render_instant_email

        preview_user = SimpleNamespace(
            name=user_name or "Preview User",
            email="preview@example.org",
            id=0,
        )
        preview_notification = SimpleNamespace(
            id=0,
            title=title,
            message=message,
            notification_type=nt or NotificationType.admin_message,
            priority=priority,
            related_url="/forms/assignment/1",
            title_key=variant["title_key"],
            message_key=variant["message_key"],
            title_params=params,
            message_params=params,
        )
        email_html = render_instant_email(
            preview_user, preview_notification, locale=locale_to_use
        )

    return {
        "type_key": type_key,
        "variant_id": variant["id"],
        "variant_label": variant["label"],
        "locale": locale_to_use,
        "title": title,
        "message": message,
        "priority": priority,
        "sends_instant_email": sends_email and priority in {"high", "urgent"},
        "sends_email": sends_email,
        "email_html": email_html,
        "title_key": variant["title_key"],
        "message_key": variant["message_key"],
        "preview_note": _preview_note(type_key, sends_email, priority),
    }


def _preview_note(type_key: str, sends_email: bool, priority: str) -> str:
    if not sends_email:
        return str(_("In-app only — this type is not sent by instant or digest email."))
    if priority in {"high", "urgent"}:
        return str(
            _(
                "Uses the hardcoded instant notification email layout with sample copy. "
                "High/urgent types send immediately; others may go in daily/weekly digests instead."
            )
        )
    return str(
        _(
            "Uses the hardcoded instant notification email layout with sample copy. "
            "Normal-priority types are usually batched into digests unless the user chose instant delivery."
        )
    )


def preview_variants_by_type_key() -> Dict[str, List[Dict[str, Any]]]:
    """Map of type_key -> preview variants for registry bootstrap."""
    from app.utils.notification_registry import NOTIFICATION_TYPE_REGISTRY_SPECS

    out: Dict[str, List[Dict[str, Any]]] = {}
    for spec in NOTIFICATION_TYPE_REGISTRY_SPECS:
        tk = spec["type_key"]
        variants = list_notification_preview_variants(tk)
        if variants:
            out[tk] = variants
    return out
