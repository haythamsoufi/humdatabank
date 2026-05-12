"""
AUTO-GENERATED — blueprint 'rbac_management'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "rbac_management.delete_grant"): ActivityEndpointSpec(description="Deleted Grant", activity_type="admin_settings"),
    ("POST", "rbac_management.delete_role"): ActivityEndpointSpec(description="Deleted Role", activity_type="admin_settings"),
    ("POST", "rbac_management.edit_role"): ActivityEndpointSpec(description="Edited Role", activity_type="admin_settings"),
    ("POST", "rbac_management.new_grant"): ActivityEndpointSpec(description="Created Grant", activity_type="admin_settings"),
    ("POST", "rbac_management.new_role"): ActivityEndpointSpec(description="Created Role", activity_type="admin_settings"),
}

