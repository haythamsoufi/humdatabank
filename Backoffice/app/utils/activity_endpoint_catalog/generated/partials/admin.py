"""
AUTO-GENERATED — blueprint 'admin'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "admin.validation_dashboard_dispatch_preview"): ActivityEndpointSpec(description="Completed Validation Dashboard Dispatch Preview", activity_type="admin_other"),
    ("POST", "admin.validation_dashboard_dispatch_send"): ActivityEndpointSpec(description="Completed Validation Dashboard Dispatch Send", activity_type="admin_other"),
    ("POST", "admin.validation_dashboard_run_checks"): ActivityEndpointSpec(description="Completed Validation Dashboard Run Checks", activity_type="admin_other"),
    ("POST", "admin.validation_questions_create_follow_up"): ActivityEndpointSpec(description="Completed Validation Questions Create Follow Up", activity_type="admin_other"),
    ("POST", "admin.validation_questions_import"): ActivityEndpointSpec(description="Completed Validation Questions Import", activity_type="admin_other"),
    ("POST", "admin.validation_questions_update"): ActivityEndpointSpec(description="Completed Validation Questions Update", activity_type="admin_other"),
    ("POST", "admin.validation_questions_update_status"): ActivityEndpointSpec(description="Completed Validation Questions Update Status", activity_type="admin_other"),
}

