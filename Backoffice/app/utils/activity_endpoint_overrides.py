"""
Shared mappings from Flask endpoints / legacy log text to canonical activity types.

Used by activity middleware (when logging) and analytics (when displaying old rows
that still have generic type ``request`` and ``Performed …`` descriptions).
"""

from __future__ import annotations

import re
from typing import Dict, Optional

# POST requests: last segment of ``request.endpoint`` (after the dot) → activity_type
POST_ENDPOINT_SEGMENT_TO_ACTIVITY_TYPE: Dict[str, str] = {
    # Push / mobile
    "register_device": "device_registered",
    "unregister_device": "device_unregistered",
    # System settings (admin)
    "manage_settings": "settings_updated",
    # JSON save for email templates (manage_settings.html) — same blueprint segment after stripping api_
    "api_settings_email_templates": "email_templates_updated",
    "settings_email_templates": "email_templates_updated",
    # Access (main blueprint)
    "request_country_access": "country_access_requested",
    # Dashboard / country selection (common POSTs that are not form submit)
    "select_country": "country_selected",
    "reopen_assignment": "form_reopened",
    "approve_assignment": "form_approved",
    # API keys (admin) — aligns with AdminActionLog action_type / audit badge keys
    "create_api_key": "api_key_create",
    "revoke_api_key": "api_key_revoke",
}

# Optional: full ``endpoint`` string when the segment alone is ambiguous (rare)
POST_FULL_ENDPOINT_TO_ACTIVITY_TYPE: Dict[str, str] = {
    # Same keys as segments are resolved via segment map; add overrides here if needed.
}

# DELETE requests: view function name (last segment) → activity_type (not generic data_deleted)
DELETE_ENDPOINT_SEGMENT_TO_ACTIVITY_TYPE: Dict[str, str] = {
    "get_or_delete_conversation": "ai_conversation_deleted",
    "delete_all_conversations": "ai_conversations_deleted_all",
}

# Legacy rows stored description ``Performed Title Case`` — map title fragment → activity_type
LEGACY_PERFORMED_TITLE_TO_ACTIVITY_TYPE: Dict[str, str] = {
    "Manage Settings": "settings_updated",
    "Register Device": "device_registered",
    "Unregister Device": "device_unregistered",
    "Request Country Access": "country_access_requested",
    "Select Country": "country_selected",
    "Reopen Assignment": "form_reopened",
    "Approve Assignment": "form_approved",
}

# Legacy ``Submitted {Title}`` lines (generic request type) → activity_type
LEGACY_SUBMITTED_TITLE_TO_ACTIVITY_TYPE: Dict[str, str] = {
    "Settings Email Templates": "email_templates_updated",
    "Create Api Key": "api_key_create",
    "Revoke Api Key": "api_key_revoke",
}

# Short, natural sentences for audit descriptions (middleware + analytics fallback)
ACTIVITY_TYPE_DESCRIPTIONS: Dict[str, str] = {
    "device_registered": "Registered a mobile device for push notifications",
    "device_unregistered": "Unregistered a mobile device from push notifications",
    "settings_updated": "Updated system settings",
    "email_templates_updated": "Updated email notification templates",
    "country_access_requested": "Requested access to a country workspace",
    "country_selected": "Selected a country workspace",
    "ai_conversation_deleted": "Deleted an AI chat conversation",
    "ai_conversations_deleted_all": "Deleted all AI chat conversations",
    "api_key_create": "Created an API key",
    "api_key_revoke": "Revoked an API key",
}


def endpoint_last_segment(endpoint: Optional[str]) -> str:
    if not endpoint:
        return ""
    return endpoint.rsplit(".", 1)[-1] if "." in endpoint else endpoint


def strip_endpoint_verb_prefix(segment: str) -> str:
    if not segment:
        return ""
    return re.sub(r"^(api_|get_|post_|put_|delete_|fetch_)", "", segment, flags=re.I)


def resolve_delete_activity_type(endpoint: Optional[str]) -> Optional[str]:
    """Return a specific activity type for a DELETE request, or None for generic data_deleted."""
    if not endpoint:
        return None
    seg = endpoint_last_segment(endpoint)
    cleaned = strip_endpoint_verb_prefix(seg)
    return (
        DELETE_ENDPOINT_SEGMENT_TO_ACTIVITY_TYPE.get(cleaned)
        or DELETE_ENDPOINT_SEGMENT_TO_ACTIVITY_TYPE.get(seg)
    )


def resolve_post_activity_type(endpoint: Optional[str]) -> Optional[str]:
    """Return a specific activity type for a POST request, or None to use generic rules."""
    if not endpoint:
        return None
    full = POST_FULL_ENDPOINT_TO_ACTIVITY_TYPE.get(endpoint)
    if full:
        return full
    seg = endpoint_last_segment(endpoint)
    cleaned = strip_endpoint_verb_prefix(seg)
    return (
        POST_ENDPOINT_SEGMENT_TO_ACTIVITY_TYPE.get(cleaned)
        or POST_ENDPOINT_SEGMENT_TO_ACTIVITY_TYPE.get(seg)
    )


def infer_activity_type_from_legacy_description(description: Optional[str]) -> Optional[str]:
    """Map old ``Performed X`` text to a canonical activity type."""
    if not description or not description.startswith("Performed "):
        return None
    tail = description[len("Performed ") :].strip()
    return LEGACY_PERFORMED_TITLE_TO_ACTIVITY_TYPE.get(tail)


def infer_activity_type_from_submitted_line(description: Optional[str]) -> Optional[str]:
    """Map ``Submitted X`` text (generic request rows) to a canonical activity type."""
    if not description or not description.startswith("Submitted "):
        return None
    tail = description[len("Submitted ") :].strip()
    return LEGACY_SUBMITTED_TITLE_TO_ACTIVITY_TYPE.get(tail)


def description_for_activity_type(activity_type: str) -> Optional[str]:
    """Return a natural-language description for a canonical activity type, if known."""
    return ACTIVITY_TYPE_DESCRIPTIONS.get(activity_type)
