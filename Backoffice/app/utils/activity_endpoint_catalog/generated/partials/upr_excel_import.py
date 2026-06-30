"""
AUTO-GENERATED — blueprint 'upr_excel_import'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "upr_excel_import.analyze"): ActivityEndpointSpec(description="Completed Analyze", activity_type="admin_other"),
    ("POST", "upr_excel_import.cancel_job"): ActivityEndpointSpec(description="Cancelled Job", activity_type="admin_other"),
    ("POST", "upr_excel_import.preview"): ActivityEndpointSpec(description="Completed Preview", activity_type="admin_other"),
    ("POST", "upr_excel_import.run_import"): ActivityEndpointSpec(description="Ran Import", activity_type="admin_other"),
    ("POST", "upr_excel_import.upload"): ActivityEndpointSpec(description="Completed Upload", activity_type="admin_other"),
}

