"""
Shared activity-type normalization helpers.

These helpers keep naming consistent across middleware logging, analytics views,
and any service that writes audit/activity rows.
"""

from typing import Optional


LEGACY_ACTIVITY_TYPE_MAP = {
    "form_submit": "form_submitted",
    "form_save": "form_saved",
    "data_update": "data_modified",
    "data_delete": "data_deleted",
    "file_upload": "file_uploaded",
}


CANONICAL_ACTIVITY_TYPES = {
    "page_view",
    "request",
    "login",
    "logout",
    "profile_update",
    "form_saved",
    "form_submitted",
    "form_approved",
    "form_reopened",
    "form_validated",
    "data_modified",
    "data_deleted",
    "file_uploaded",
    "data_export",
    "account_created",
}


def normalize_activity_type(activity_type: Optional[str]) -> Optional[str]:
    """Return canonical activity type when known, otherwise passthrough."""
    if activity_type is None:
        return None
    raw = str(activity_type).strip()
    if not raw:
        return raw
    if raw in CANONICAL_ACTIVITY_TYPES:
        return raw
    return LEGACY_ACTIVITY_TYPE_MAP.get(raw, raw)

