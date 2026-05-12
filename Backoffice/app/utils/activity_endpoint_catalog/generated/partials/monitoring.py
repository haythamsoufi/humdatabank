"""
AUTO-GENERATED — blueprint 'monitoring'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "monitoring.clear_monitoring_logs"): ActivityEndpointSpec(description="Cleared Monitoring Logs", activity_type="admin_monitoring"),
    ("POST", "monitoring.test_error_notification"): ActivityEndpointSpec(description="Completed Test Error Notification", activity_type="admin_monitoring"),
}

