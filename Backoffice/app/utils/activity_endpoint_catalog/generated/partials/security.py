"""
AUTO-GENERATED — blueprint 'security'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "security.resolve_security_event"): ActivityEndpointSpec(description="Resolved Security Event", activity_type="admin_other"),
    ("POST", "security.test_security_alert"): ActivityEndpointSpec(description="Completed Test Security Alert", activity_type="admin_other"),
}

