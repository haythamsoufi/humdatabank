"""
AUTO-GENERATED — blueprint 'analytics'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "analytics.cleanup_sessions"): ActivityEndpointSpec(description="Cleaned up Sessions", activity_type="admin_analytics"),
    ("POST", "analytics.end_session"): ActivityEndpointSpec(description="Completed End Session", activity_type="admin_analytics"),
    ("POST", "analytics.resolve_security_event"): ActivityEndpointSpec(description="Resolved Security Event", activity_type="admin_analytics"),
}

