"""
AUTO-GENERATED — blueprint 'auth'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("DELETE", "auth.remove_own_device"): ActivityEndpointSpec(description="Removed Own Device", activity_type="admin_portal"),
    ("POST", "auth.account_settings"): ActivityEndpointSpec(description="Completed Account Settings", activity_type="admin_portal"),
    ("POST", "auth.azure_callback"): ActivityEndpointSpec(description="Completed Azure Callback", activity_type="admin_portal"),
    ("POST", "auth.forgot_password"): ActivityEndpointSpec(description="Completed Forgot Password", activity_type="admin_portal"),
    ("POST", "auth.kickout_own_device"): ActivityEndpointSpec(description="Kicked out Own Device", activity_type="admin_portal"),
    ("POST", "auth.register"): ActivityEndpointSpec(description="Completed Register", activity_type="admin_portal"),
    ("POST", "auth.reset_password"): ActivityEndpointSpec(description="Completed Reset Password", activity_type="admin_portal"),
}

