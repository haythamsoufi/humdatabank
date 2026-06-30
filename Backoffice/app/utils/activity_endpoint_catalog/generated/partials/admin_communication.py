"""
AUTO-GENERATED — blueprint 'admin_communication'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "admin_communication.api_campaign_email_compose_preview"): ActivityEndpointSpec(description="Completed Campaign Email Compose Preview", activity_type="admin_notifications"),
    ("POST", "admin_communication.api_campaign_email_template_preview"): ActivityEndpointSpec(description="Completed Campaign Email Template Preview", activity_type="admin_notifications"),
    ("POST", "admin_communication.api_campaign_email_template_test_send"): ActivityEndpointSpec(description="Completed Campaign Email Template Test Send", activity_type="admin_notifications"),
    ("POST", "admin_communication.api_campaign_email_templates_save"): ActivityEndpointSpec(description="Completed Campaign Email Templates Save", activity_type="admin_notifications"),
    ("POST", "admin_communication.api_campaign_email_templates_seed"): ActivityEndpointSpec(description="Completed Campaign Email Templates Seed", activity_type="admin_notifications"),
    ("POST", "admin_communication.api_cancel_email_delivery"): ActivityEndpointSpec(description="Cancelled Email Delivery", activity_type="admin_notifications"),
    ("POST", "admin_communication.api_cancel_failed_email_deliveries"): ActivityEndpointSpec(description="Cancelled Failed Email Deliveries", activity_type="admin_notifications"),
    ("POST", "admin_communication.api_retry_email_delivery"): ActivityEndpointSpec(description="Completed Retry Email Delivery", activity_type="admin_notifications"),
    ("POST", "admin_communication.api_retry_failed_email_deliveries"): ActivityEndpointSpec(description="Completed Retry Failed Email Deliveries", activity_type="admin_notifications"),
    ("POST", "admin_communication.api_send_notifications"): ActivityEndpointSpec(description="Sent Notifications", activity_type="admin_notifications"),
}

