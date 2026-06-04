"""
Hand-curated catalog entries (override generated defaults).

Key: (HTTP_METHOD or "*", flask endpoint string).
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec

# Curated examples — activity_type matches blueprint category for badge consistency.
MANUAL_ACTIVITY_OVERRIDES: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "settings.manage_settings"): ActivityEndpointSpec(
        description="Updated system configuration",
        activity_type="admin_settings",
    ),
    ("*", "ai_management.traces_bulk_delete"): ActivityEndpointSpec(
        description="Deleted traces",
        activity_type="admin_ai",
    ),
    ("*", "content_management.edit_resource"): ActivityEndpointSpec(
        description="Edited resource",
        activity_type="admin_content",
    ),
    ("*", "embed_management.create_embed_content"): ActivityEndpointSpec(
        description="Created embed content",
        activity_type="admin_embed",
    ),
    ("POST", "utilities.preview_indicator_import"): ActivityEndpointSpec(
        description="Previewed Indicator Import",
        activity_type="admin_utilities",
    ),
    ("POST", "utilities.apply_indicator_import"): ActivityEndpointSpec(
        description="Applied Indicator Import",
        activity_type="admin_utilities",
    ),
    ("POST", "main.return_assignment_for_revision"): ActivityEndpointSpec(
        description="Returned Assignment For Revision",
        activity_type="admin_portal",
    ),
    ("POST", "indicator_bank_compat.indicator_suggestion"): ActivityEndpointSpec(
        description="Submitted Indicator Suggestion",
        activity_type="admin_portal",
    ),
    ("POST", "api_key_management.edit_api_key"): ActivityEndpointSpec(
        description="Edited API Key",
        activity_type="admin_security",
    ),
    ("POST", "api_key_management.rotate_api_key"): ActivityEndpointSpec(
        description="Rotated API Key",
        activity_type="admin_security",
    ),
}
