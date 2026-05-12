"""
AUTO-GENERATED — blueprint 'excel'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "excel.import_assignment_excel"): ActivityEndpointSpec(description="Imported Assignment Excel", activity_type="admin_assignments"),
}

