"""
AUTO-GENERATED — blueprint 'notifications'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("DELETE", "notifications.api_delete_campaign"): ActivityEndpointSpec(description="Deleted Campaign", activity_type="admin_notifications"),
    ("DELETE", "notifications.api_delete_notifications"): ActivityEndpointSpec(description="Deleted Notifications", activity_type="admin_notifications"),
    ("POST", "notifications.api_admin_check_user_devices"): ActivityEndpointSpec(description="Completed Admin Check User Devices", activity_type="admin_notifications"),
    ("POST", "notifications.api_admin_send_push"): ActivityEndpointSpec(description="Completed Admin Send Push", activity_type="admin_notifications"),
    ("POST", "notifications.api_archive_notifications"): ActivityEndpointSpec(description="Archived Notifications", activity_type="admin_notifications"),
    ("POST", "notifications.api_create_campaign"): ActivityEndpointSpec(description="Created Campaign", activity_type="admin_notifications"),
    ("POST", "notifications.api_notification_action"): ActivityEndpointSpec(description="Completed Notification Action", activity_type="admin_notifications"),
    ("POST", "notifications.api_schedule_notification"): ActivityEndpointSpec(description="Completed Schedule Notification", activity_type="admin_notifications"),
    ("POST", "notifications.api_send_campaign"): ActivityEndpointSpec(description="Sent Campaign", activity_type="admin_notifications"),
    ("POST", "notifications.api_update_notification_preferences"): ActivityEndpointSpec(description="Updated Notification Preferences", activity_type="admin_notifications"),
    ("POST", "notifications.api_view_notification"): ActivityEndpointSpec(description="Completed View Notification", activity_type="admin_notifications"),
    ("POST", "notifications.mark_notifications_unread"): ActivityEndpointSpec(description="Completed Mark Notifications Unread", activity_type="admin_notifications"),
    ("PUT", "notifications.api_update_campaign"): ActivityEndpointSpec(description="Updated Campaign", activity_type="admin_notifications"),
}

