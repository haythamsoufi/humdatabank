"""
AUTO-GENERATED — blueprint 'fdrs'. Do not edit by hand.
Regenerate: python scripts/dev/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "fdrs.data_sync_cancel"): ActivityEndpointSpec(description="Cancelled Data Sync", activity_type="admin_system"),
    ("POST", "fdrs.run_data_sync"): ActivityEndpointSpec(description="Ran Data Sync", activity_type="admin_system"),
    ("POST", "fdrs.run_sync_verify"): ActivityEndpointSpec(description="Ran Sync Verify", activity_type="admin_system"),
    ("POST", "fdrs.sync_verify_cancel"): ActivityEndpointSpec(description="Cancelled Sync Verify", activity_type="admin_system"),
}
