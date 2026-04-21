"""
AUTO-GENERATED — blueprint 'settings'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "settings.api_ai_settings_reset"): ActivityEndpointSpec(description="Completed Ai Settings Reset", activity_type="admin_settings"),
    ("POST", "settings.api_languages_settings"): ActivityEndpointSpec(description="Completed Languages Settings", activity_type="admin_settings"),
}

