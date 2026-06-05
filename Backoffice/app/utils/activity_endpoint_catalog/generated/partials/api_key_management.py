"""
AUTO-GENERATED — blueprint 'api_key_management'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "api_key_management.edit_api_key"): ActivityEndpointSpec(description="Edited Api Key", activity_type="admin_settings"),
    ("POST", "api_key_management.rotate_api_key"): ActivityEndpointSpec(description="Completed Rotate Api Key", activity_type="admin_settings"),
}

