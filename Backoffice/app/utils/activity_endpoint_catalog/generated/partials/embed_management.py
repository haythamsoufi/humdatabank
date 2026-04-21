"""
AUTO-GENERATED — blueprint 'embed_management'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("DELETE", "embed_management.delete_embed_content"): ActivityEndpointSpec(description="Deleted Embed Content", activity_type="admin_embed"),
    ("PATCH", "embed_management.update_embed_content"): ActivityEndpointSpec(description="Updated Embed Content", activity_type="admin_embed"),
    ("POST", "embed_management.create_embed_content"): ActivityEndpointSpec(description="Created Embed Content", activity_type="admin_embed"),
    ("POST", "embed_management.reorder_embed_content"): ActivityEndpointSpec(description="Reordered Embed Content", activity_type="admin_embed"),
    ("PUT", "embed_management.update_embed_content"): ActivityEndpointSpec(description="Updated Embed Content", activity_type="admin_embed"),
}

