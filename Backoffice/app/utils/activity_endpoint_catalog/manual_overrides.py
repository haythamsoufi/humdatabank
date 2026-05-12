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
}
