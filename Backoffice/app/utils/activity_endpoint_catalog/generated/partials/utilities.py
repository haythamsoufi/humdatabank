"""
AUTO-GENERATED — blueprint 'utilities'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "utilities.add_translation"): ActivityEndpointSpec(description="Added Translation", activity_type="admin_utilities"),
    ("POST", "utilities.api_bulk_update_translations"): ActivityEndpointSpec(description="Bulk updated Translations", activity_type="admin_utilities"),
    ("POST", "utilities.cleanup_sessions"): ActivityEndpointSpec(description="Cleaned up Sessions", activity_type="admin_utilities"),
    ("POST", "utilities.compile_translations"): ActivityEndpointSpec(description="Compiled Translations", activity_type="admin_utilities"),
    ("POST", "utilities.delete_indicator_suggestion"): ActivityEndpointSpec(description="Deleted Indicator Suggestion", activity_type="admin_utilities"),
    ("POST", "utilities.delete_removed_translation"): ActivityEndpointSpec(description="Deleted Translation", activity_type="admin_utilities"),
    ("POST", "utilities.edit_translation"): ActivityEndpointSpec(description="Edited Translation", activity_type="admin_utilities"),
    ("POST", "utilities.extract_update_translations"): ActivityEndpointSpec(description="Extracted Translations", activity_type="admin_utilities"),
    ("POST", "utilities.import_indicators"): ActivityEndpointSpec(description="Imported Indicators", activity_type="admin_utilities"),
    ("POST", "utilities.import_translations"): ActivityEndpointSpec(description="Imported Translations", activity_type="admin_utilities"),
    ("POST", "utilities.reload_translations"): ActivityEndpointSpec(description="Reloaded Translations", activity_type="admin_utilities"),
    ("POST", "utilities.update_indicator_suggestion_status"): ActivityEndpointSpec(description="Updated Indicator Suggestion Status", activity_type="admin_utilities"),
}

