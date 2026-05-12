"""
AUTO-GENERATED — blueprint 'assignment_management'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("DELETE", "assignment_management.remove_entity_from_assignment"): ActivityEndpointSpec(description="Removed Entity From Assignment", activity_type="admin_assignments"),
    ("POST", "assignment_management.add_countries_to_assignment"): ActivityEndpointSpec(description="Added Countries To Assignment", activity_type="admin_assignments"),
    ("POST", "assignment_management.add_country_to_public"): ActivityEndpointSpec(description="Added Country To Public", activity_type="admin_assignments"),
    ("POST", "assignment_management.add_entity_to_assignment"): ActivityEndpointSpec(description="Added Entity To Assignment", activity_type="admin_assignments"),
    ("POST", "assignment_management.bulk_enable_public_reporting"): ActivityEndpointSpec(description="Bulk enabled Public Reporting", activity_type="admin_assignments"),
    ("POST", "assignment_management.bulk_remove_entities_from_assignment"): ActivityEndpointSpec(description="Bulk removed Entities From Assignment", activity_type="admin_assignments"),
    ("POST", "assignment_management.bulk_update_due_date_selected"): ActivityEndpointSpec(description="Bulk updated Due Date Selected", activity_type="admin_assignments"),
    ("POST", "assignment_management.bulk_update_entity_status"): ActivityEndpointSpec(description="Bulk updated Entity Status", activity_type="admin_assignments"),
    ("POST", "assignment_management.bulk_update_public_availability"): ActivityEndpointSpec(description="Bulk updated Public Availability", activity_type="admin_assignments"),
    ("POST", "assignment_management.close_assignment"): ActivityEndpointSpec(description="Closed Assignment", activity_type="admin_assignments"),
    ("POST", "assignment_management.delete_assignment"): ActivityEndpointSpec(description="Deleted Assignment", activity_type="admin_assignments"),
    ("POST", "assignment_management.delete_public_submission"): ActivityEndpointSpec(description="Deleted Public Submission", activity_type="admin_assignments"),
    ("POST", "assignment_management.edit_assignment"): ActivityEndpointSpec(description="Edited Assignment", activity_type="admin_assignments"),
    ("POST", "assignment_management.edit_assignment_entity_status"): ActivityEndpointSpec(description="Edited Assignment Entity Status", activity_type="admin_assignments"),
    ("POST", "assignment_management.generate_public_url"): ActivityEndpointSpec(description="Generated Public Url", activity_type="admin_assignments"),
    ("POST", "assignment_management.new_assignment"): ActivityEndpointSpec(description="Created Assignment", activity_type="admin_assignments"),
    ("POST", "assignment_management.remove_country_from_assignment"): ActivityEndpointSpec(description="Removed Country From Assignment", activity_type="admin_assignments"),
    ("POST", "assignment_management.remove_country_from_public"): ActivityEndpointSpec(description="Removed Country From Public", activity_type="admin_assignments"),
    ("POST", "assignment_management.reopen_closed_assignment"): ActivityEndpointSpec(description="Reopened Closed Assignment", activity_type="admin_assignments"),
    ("POST", "assignment_management.toggle_assignment_active"): ActivityEndpointSpec(description="Toggled Assignment Active", activity_type="admin_assignments"),
    ("POST", "assignment_management.toggle_public_access"): ActivityEndpointSpec(description="Toggled Public Access", activity_type="admin_assignments"),
    ("POST", "assignment_management.update_public_submission_status"): ActivityEndpointSpec(description="Updated Public Submission Status", activity_type="admin_assignments"),
    ("PUT", "assignment_management.update_entity_status"): ActivityEndpointSpec(description="Updated Entity Status", activity_type="admin_assignments"),
}

