"""Campaign email templates for Communication Center broadcasts."""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.app_settings_service import _is_lang_key, read_settings, write_settings

CAMPAIGN_EMAIL_TEMPLATE_KEYS = [
    "campaign_template_data_collection_launch",
    "campaign_template_submission_reminder",
    "campaign_template_deadline_reminder",
    "campaign_template_training_announcement",
    "campaign_template_general_announcement",
]

_CAMPAIGN_TEMPLATE_METADATA_KEYS = frozenset(
    ("label", "compose_title", "compose_message", "priority")
)

_SETTINGS_KEY = "campaign_email_templates"


def get_campaign_email_template(
    template_key: str,
    default: Optional[str] = None,
    language: str = "en",
) -> str:
    if template_key not in CAMPAIGN_EMAIL_TEMPLATE_KEYS:
        raise ValueError(f"Invalid campaign email template key: {template_key}")

    data = read_settings()
    templates = data.get(_SETTINGS_KEY, {})
    template = templates.get(template_key)

    if isinstance(template, dict):
        content = template.get(language) or template.get("en") or ""
        if content and isinstance(content, str) and content.strip():
            return content
        return default or ""

    if template and isinstance(template, str):
        return template

    return default or ""


def get_all_campaign_email_templates() -> Dict[str, Dict[str, str]]:
    data = read_settings()
    templates = data.get(_SETTINGS_KEY, {})
    result: Dict[str, Dict[str, str]] = {}
    for key in CAMPAIGN_EMAIL_TEMPLATE_KEYS:
        val = templates.get(key, "")
        if isinstance(val, dict):
            result[key] = {
                lang: content
                for lang, content in val.items()
                if _is_lang_key(lang) and isinstance(content, str) and content.strip()
            }
        elif isinstance(val, str) and val.strip():
            result[key] = {"en": val}
        else:
            result[key] = {}
    return result


def get_campaign_template_metadata() -> Dict[str, Dict[str, str]]:
    """Return compose pre-fill metadata per campaign template key."""
    data = read_settings()
    templates = data.get(_SETTINGS_KEY, {})
    if not isinstance(templates, dict):
        return {}
    result: Dict[str, Dict[str, str]] = {}
    for key in CAMPAIGN_EMAIL_TEMPLATE_KEYS:
        val = templates.get(key)
        if not isinstance(val, dict):
            result[key] = {
                "label": "",
                "title": "",
                "message": "",
                "priority": "normal",
            }
            continue
        result[key] = {
            "label": (val.get("label") or "").strip() or key.replace("_", " ").title(),
            "title": (val.get("compose_title") or "").strip(),
            "message": (val.get("compose_message") or "").strip(),
            "priority": (val.get("priority") or "normal").strip() or "normal",
        }
    return result


def get_campaign_compose_templates() -> Dict[str, Dict[str, str]]:
    """Alias used by Communication Center compose dropdown."""
    return get_campaign_template_metadata()


def normalize_campaign_email_template_key(raw: Optional[str]) -> Optional[str]:
    key = (raw or "").strip()
    if key in CAMPAIGN_EMAIL_TEMPLATE_KEYS:
        return key
    return None


def get_email_template_key_from_attachment_config(config: Optional[dict]) -> Optional[str]:
    if not isinstance(config, dict):
        return None
    return normalize_campaign_email_template_key(config.get("email_template_key"))


def merge_email_template_key_into_attachment_config(
    config: Optional[dict],
    email_template_key: Optional[str],
) -> Optional[dict]:
    return merge_campaign_email_attachment_config(
        config,
        email_template_key=email_template_key,
    )


def get_email_template_html_from_attachment_config(config: Optional[dict]) -> str:
    if not isinstance(config, dict):
        return ""
    html = config.get("email_template_html")
    return html.strip() if isinstance(html, str) else ""


def merge_campaign_email_attachment_config(
    config: Optional[dict],
    *,
    email_template_key: Optional[str] = None,
    email_template_html: Optional[str] = None,
    clear_email_template_html: bool = False,
) -> Optional[dict]:
    """Merge campaign email template key and optional per-campaign HTML override into attachment_config."""
    out: Optional[dict] = dict(config) if isinstance(config, dict) else None

    if email_template_key is not None:
        key = normalize_campaign_email_template_key(email_template_key)
        if key:
            out = dict(out or {})
            out["email_template_key"] = key
        elif out and "email_template_key" in out:
            out = dict(out)
            out.pop("email_template_key", None)
            if not out:
                out = None

    if clear_email_template_html or email_template_html is not None:
        if isinstance(email_template_html, str):
            html = email_template_html.strip()
        else:
            html = ""
        if html:
            out = dict(out or {})
            out["email_template_html"] = html
        elif out and "email_template_html" in out:
            out = dict(out)
            out.pop("email_template_html", None)
            if not out:
                out = None

    return out


def set_all_campaign_email_templates(
    templates: Dict[str, Any],
    metadata: Optional[Dict[str, Dict[str, str]]] = None,
    user_id: Optional[int] = None,
) -> bool:
    if not isinstance(templates, dict):
        raise ValueError("templates must be a dictionary")

    for key in templates.keys():
        if key not in CAMPAIGN_EMAIL_TEMPLATE_KEYS:
            raise ValueError(f"Invalid campaign email template key: {key}")

    data = read_settings()
    data[_SETTINGS_KEY] = {}

    for key in CAMPAIGN_EMAIL_TEMPLATE_KEYS:
        val = templates.get(key, {})
        if isinstance(val, str):
            trimmed = val.strip()
            content_part = {"en": trimmed} if trimmed else {}
        elif isinstance(val, dict):
            content_part = {
                lang: content.strip()
                for lang, content in val.items()
                if _is_lang_key(lang) and isinstance(content, str) and content.strip()
            }
        else:
            content_part = {}

        meta = (metadata or {}).get(key) or {}
        meta_part: Dict[str, str] = {}
        for field in _CAMPAIGN_TEMPLATE_METADATA_KEYS:
            v = meta.get(field)
            if isinstance(v, str) and v.strip():
                meta_part[field] = v.strip()

        data[_SETTINGS_KEY][key] = {**content_part, **meta_part}

    return write_settings(data, user_id=user_id)
