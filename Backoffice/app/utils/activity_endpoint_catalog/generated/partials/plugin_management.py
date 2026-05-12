"""
AUTO-GENERATED — blueprint 'plugin_management'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "plugin_management.activate_plugin"): ActivityEndpointSpec(description="Activated Plugin", activity_type="admin_plugin"),
    ("POST", "plugin_management.deactivate_plugin"): ActivityEndpointSpec(description="Deactivated Plugin", activity_type="admin_plugin"),
    ("POST", "plugin_management.install_plugin"): ActivityEndpointSpec(description="Installed Plugin", activity_type="admin_plugin"),
    ("POST", "plugin_management.plugin_settings"): ActivityEndpointSpec(description="Completed Plugin Settings", activity_type="admin_plugin"),
    ("POST", "plugin_management.render_plugin_field_builder"): ActivityEndpointSpec(description="Completed Render Plugin Field Builder", activity_type="admin_plugin"),
    ("POST", "plugin_management.uninstall_plugin"): ActivityEndpointSpec(description="Uninstalled Plugin", activity_type="admin_plugin"),
    ("POST", "plugin_management.upload_plugin"): ActivityEndpointSpec(description="Completed Upload Plugin", activity_type="admin_plugin"),
}

