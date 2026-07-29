"""
AUTO-GENERATED — blueprint 'main'. Do not edit by hand.
Regenerate: python scripts/dev/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "main.documents_submit"): ActivityEndpointSpec(description="Completed Documents Submit", activity_type="admin_portal"),
    ("POST", "main.return_assignment_for_revision"): ActivityEndpointSpec(description="Completed Return Assignment For Revision", activity_type="admin_portal"),
}

