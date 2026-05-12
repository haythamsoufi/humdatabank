"""
AUTO-GENERATED — blueprint 'forms_api'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("DELETE", "forms_api.api_remove_dynamic_indicator"): ActivityEndpointSpec(description="Removed Dynamic Indicator", activity_type="admin_forms"),
    ("PATCH", "forms_api.api_toggle_repeat_instance_hide"): ActivityEndpointSpec(description="Updated Toggle Repeat Instance Hide", activity_type="admin_forms"),
    ("POST", "forms_api.api_add_dynamic_indicator"): ActivityEndpointSpec(description="Added Dynamic Indicator", activity_type="admin_forms"),
    ("PUT", "forms_api.api_update_dynamic_indicator"): ActivityEndpointSpec(description="Updated Dynamic Indicator", activity_type="admin_forms"),
}

