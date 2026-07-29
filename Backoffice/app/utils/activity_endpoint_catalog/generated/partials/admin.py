"""
AUTO-GENERATED — blueprint 'admin'. Do not edit by hand.
Regenerate: python scripts/dev/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("DELETE", "admin.validation_rules_check_types_delete_api"): ActivityEndpointSpec(description="Deleted Validation Rules Check Types Delete Api", activity_type="admin_other"),
    ("DELETE", "admin.validation_rules_thresholds_delete_api"): ActivityEndpointSpec(description="Deleted Validation Rules Thresholds Delete Api", activity_type="admin_other"),
    ("POST", "admin.validation_dashboard_dispatch_preview"): ActivityEndpointSpec(description="Completed Validation Dashboard Dispatch Preview", activity_type="admin_other"),
    ("POST", "admin.validation_dashboard_dispatch_send"): ActivityEndpointSpec(description="Completed Validation Dashboard Dispatch Send", activity_type="admin_other"),
    ("POST", "admin.validation_dashboard_run_checks"): ActivityEndpointSpec(description="Completed Validation Dashboard Run Checks", activity_type="admin_other"),
    ("POST", "admin.validation_questions_create_follow_up"): ActivityEndpointSpec(description="Completed Validation Questions Create Follow Up", activity_type="admin_other"),
    ("POST", "admin.validation_questions_import"): ActivityEndpointSpec(description="Completed Validation Questions Import", activity_type="admin_other"),
    ("POST", "admin.validation_questions_update"): ActivityEndpointSpec(description="Completed Validation Questions Update", activity_type="admin_other"),
    ("POST", "admin.validation_questions_update_status"): ActivityEndpointSpec(description="Completed Validation Questions Update Status", activity_type="admin_other"),
    ("POST", "admin.validation_rules_check_types_upsert_api"): ActivityEndpointSpec(description="Completed Validation Rules Check Types Upsert Api", activity_type="admin_other"),
    ("POST", "admin.validation_rules_question_templates_update_api"): ActivityEndpointSpec(description="Completed Validation Rules Question Templates Update Api", activity_type="admin_other"),
    ("POST", "admin.validation_rules_thresholds_upsert_api"): ActivityEndpointSpec(description="Completed Validation Rules Thresholds Upsert Api", activity_type="admin_other"),
}

