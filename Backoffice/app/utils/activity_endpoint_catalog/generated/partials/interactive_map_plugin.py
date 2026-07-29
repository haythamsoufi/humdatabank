"""
AUTO-GENERATED — blueprint 'interactive_map_plugin'. Do not edit by hand.
Regenerate: python scripts/dev/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "interactive_map_plugin.clear_cache"): ActivityEndpointSpec(description="Cleared Cache", activity_type="admin_plugin"),
    ("POST", "interactive_map_plugin.geocode_address"): ActivityEndpointSpec(description="Completed Geocode Address", activity_type="admin_plugin"),
    ("POST", "interactive_map_plugin.save_settings"): ActivityEndpointSpec(description="Completed Save Settings", activity_type="admin_plugin"),
    ("POST", "interactive_map_plugin.update_config_section"): ActivityEndpointSpec(description="Updated Config Section", activity_type="admin_plugin"),
    ("POST", "interactive_map_plugin.update_full_config"): ActivityEndpointSpec(description="Updated Full Config", activity_type="admin_plugin"),
}

