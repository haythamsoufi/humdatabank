"""
AUTO-GENERATED — blueprint 'forms'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "forms.approve_public_submission"): ActivityEndpointSpec(description="Approved Public Submission", activity_type="admin_forms"),
    ("POST", "forms.debug_public_form_test"): ActivityEndpointSpec(description="Completed Debug Public Form Test", activity_type="admin_forms"),
    ("POST", "forms.delete_document"): ActivityEndpointSpec(description="Deleted Document", activity_type="admin_forms"),
    ("POST", "forms.delete_public_submission"): ActivityEndpointSpec(description="Deleted Public Submission", activity_type="admin_forms"),
    ("POST", "forms.delete_self_report_assignment"): ActivityEndpointSpec(description="Deleted Self Report Assignment", activity_type="admin_forms"),
    ("POST", "forms.edit_public_submission"): ActivityEndpointSpec(description="Edited Public Submission", activity_type="admin_forms"),
    ("POST", "forms.fill_public_form"): ActivityEndpointSpec(description="Completed Fill Public Form", activity_type="admin_forms"),
    ("POST", "forms.handle_excel_import"): ActivityEndpointSpec(description="Completed Handle Excel Import", activity_type="admin_forms"),
    ("POST", "forms.reject_public_submission"): ActivityEndpointSpec(description="Rejected Public Submission", activity_type="admin_forms"),
    ("POST", "forms.update_public_submission_status"): ActivityEndpointSpec(description="Updated Public Submission Status", activity_type="admin_forms"),
    ("POST", "forms.validation_summary_cancel"): ActivityEndpointSpec(description="Cancelled Validation Summary", activity_type="admin_forms"),
    ("POST", "forms.validation_summary_run_and_load_opinions"): ActivityEndpointSpec(description="Completed Validation Summary Run And Load Opinions", activity_type="admin_forms"),
    ("POST", "forms.view_edit_form"): ActivityEndpointSpec(description="Completed View Edit Form", activity_type="admin_forms"),
}

