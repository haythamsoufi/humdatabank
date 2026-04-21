"""
AUTO-GENERATED — blueprint 'admin_notifications'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "admin_notifications.api_send_notifications"): ActivityEndpointSpec(description="Sent Notifications", activity_type="admin_other"),
}

