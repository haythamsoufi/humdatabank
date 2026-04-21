"""
AUTO-GENERATED — blueprint 'user_management'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("DELETE", "user_management.remove_device"): ActivityEndpointSpec(description="Removed Device", activity_type="admin_users"),
    ("DELETE", "user_management.remove_user_entity"): ActivityEndpointSpec(description="Removed User Entity", activity_type="admin_users"),
    ("PATCH", "user_management.api_user_update"): ActivityEndpointSpec(description="Updated User Update", activity_type="admin_users"),
    ("POST", "user_management.add_user_entity"): ActivityEndpointSpec(description="Added User Entity", activity_type="admin_users"),
    ("POST", "user_management.api_activate_user"): ActivityEndpointSpec(description="Activated User", activity_type="admin_users"),
    ("POST", "user_management.api_approve_access_request"): ActivityEndpointSpec(description="Approved Access Request", activity_type="admin_users"),
    ("POST", "user_management.api_approve_all_access_requests"): ActivityEndpointSpec(description="Approved All Access Requests", activity_type="admin_users"),
    ("POST", "user_management.api_deactivate_user"): ActivityEndpointSpec(description="Deactivated User", activity_type="admin_users"),
    ("POST", "user_management.api_reject_access_request"): ActivityEndpointSpec(description="Rejected Access Request", activity_type="admin_users"),
    ("POST", "user_management.approve_access_request"): ActivityEndpointSpec(description="Approved Access Request", activity_type="admin_users"),
    ("POST", "user_management.approve_all_access_requests"): ActivityEndpointSpec(description="Approved All Access Requests", activity_type="admin_users"),
    ("POST", "user_management.archive_user"): ActivityEndpointSpec(description="Archived User", activity_type="admin_users"),
    ("POST", "user_management.delete_user"): ActivityEndpointSpec(description="Deleted User", activity_type="admin_users"),
    ("POST", "user_management.edit_user"): ActivityEndpointSpec(description="Edited User", activity_type="admin_users"),
    ("POST", "user_management.kickout_device"): ActivityEndpointSpec(description="Kicked out Device", activity_type="admin_users"),
    ("POST", "user_management.new_user"): ActivityEndpointSpec(description="Created User", activity_type="admin_users"),
    ("POST", "user_management.reject_access_request"): ActivityEndpointSpec(description="Rejected Access Request", activity_type="admin_users"),
    ("PUT", "user_management.api_user_update"): ActivityEndpointSpec(description="Updated User Update", activity_type="admin_users"),
}

