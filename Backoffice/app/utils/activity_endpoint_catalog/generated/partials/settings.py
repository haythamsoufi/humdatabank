"""
AUTO-GENERATED — blueprint 'settings'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "settings.api_ai_settings_reset"): ActivityEndpointSpec(description="Completed Ai Settings Reset", activity_type="admin_settings"),
    ("POST", "settings.api_languages_settings"): ActivityEndpointSpec(description="Completed Languages Settings", activity_type="admin_settings"),
    ("POST", "settings.api_settings_email_template_preview"): ActivityEndpointSpec(description="Completed Settings Email Template Preview", activity_type="admin_settings"),
    ("POST", "settings.api_settings_email_template_test_send"): ActivityEndpointSpec(description="Completed Settings Email Template Test Send", activity_type="admin_settings"),
    ("POST", "settings.api_settings_email_templates_seed"): ActivityEndpointSpec(description="Completed Settings Email Templates Seed", activity_type="admin_settings"),
    ("POST", "settings.branding_assets_upload"): ActivityEndpointSpec(description="Completed Branding Assets Upload", activity_type="admin_settings"),
}

