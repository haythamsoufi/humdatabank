"""
AUTO-GENERATED — blueprint 'emergency_operations_plugin'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "emergency_operations_plugin.clear_cache"): ActivityEndpointSpec(description="Cleared Cache", activity_type="admin_plugin"),
    ("POST", "emergency_operations_plugin.data_cache_refresh"): ActivityEndpointSpec(description="Completed Data Cache Refresh", activity_type="admin_plugin"),
    ("POST", "emergency_operations_plugin.data_cache_schedule"): ActivityEndpointSpec(description="Completed Data Cache Schedule", activity_type="admin_plugin"),
    ("POST", "emergency_operations_plugin.data_cache_source"): ActivityEndpointSpec(description="Completed Data Cache Source", activity_type="admin_plugin"),
    ("POST", "emergency_operations_plugin.update_config_section"): ActivityEndpointSpec(description="Updated Config Section", activity_type="admin_plugin"),
    ("POST", "emergency_operations_plugin.update_config_section_custom"): ActivityEndpointSpec(description="Updated Config Section Custom", activity_type="admin_plugin"),
    ("POST", "emergency_operations_plugin.update_full_config"): ActivityEndpointSpec(description="Updated Full Config", activity_type="admin_plugin"),
}

