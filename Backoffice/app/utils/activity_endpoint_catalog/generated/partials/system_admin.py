"""
AUTO-GENERATED — blueprint 'system_admin'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("DELETE", "system_admin.delete_lookup_list_row"): ActivityEndpointSpec(description="Deleted Lookup List Row", activity_type="admin_system"),
    ("PATCH", "system_admin.update_lookup_list_row"): ActivityEndpointSpec(description="Updated Lookup List Row", activity_type="admin_system"),
    ("POST", "system_admin.add_common_word_modal"): ActivityEndpointSpec(description="Added Common Word Modal", activity_type="admin_system"),
    ("POST", "system_admin.add_indicator_bank"): ActivityEndpointSpec(description="Added Indicator Bank", activity_type="admin_system"),
    ("POST", "system_admin.add_lookup_list_row"): ActivityEndpointSpec(description="Added Lookup List Row", activity_type="admin_system"),
    ("POST", "system_admin.archive_indicator_bank"): ActivityEndpointSpec(description="Archived Indicator Bank", activity_type="admin_system"),
    ("POST", "system_admin.cleanup_sessions"): ActivityEndpointSpec(description="Cleaned up Sessions", activity_type="admin_system"),
    ("POST", "system_admin.create_lookup_list"): ActivityEndpointSpec(description="Created Lookup List", activity_type="admin_system"),
    ("POST", "system_admin.delete_common_word"): ActivityEndpointSpec(description="Deleted Common Word", activity_type="admin_system"),
    ("POST", "system_admin.delete_country"): ActivityEndpointSpec(description="Deleted Country", activity_type="admin_system"),
    ("POST", "system_admin.delete_indicator_bank"): ActivityEndpointSpec(description="Deleted Indicator Bank", activity_type="admin_system"),
    ("POST", "system_admin.delete_lookup_list"): ActivityEndpointSpec(description="Deleted Lookup List", activity_type="admin_system"),
    ("POST", "system_admin.delete_ns_branch"): ActivityEndpointSpec(description="Deleted Ns Branch", activity_type="admin_system"),
    ("POST", "system_admin.delete_ns_localunit"): ActivityEndpointSpec(description="Deleted Ns Localunit", activity_type="admin_system"),
    ("POST", "system_admin.delete_ns_subbranch"): ActivityEndpointSpec(description="Deleted Ns Subbranch", activity_type="admin_system"),
    ("POST", "system_admin.delete_sector"): ActivityEndpointSpec(description="Deleted Sector", activity_type="admin_system"),
    ("POST", "system_admin.delete_subsector"): ActivityEndpointSpec(description="Deleted Subsector", activity_type="admin_system"),
    ("POST", "system_admin.edit_common_word_modal"): ActivityEndpointSpec(description="Edited Common Word Modal", activity_type="admin_system"),
    ("POST", "system_admin.edit_country"): ActivityEndpointSpec(description="Edited Country", activity_type="admin_system"),
    ("POST", "system_admin.edit_indicator_bank"): ActivityEndpointSpec(description="Edited Indicator Bank", activity_type="admin_system"),
    ("POST", "system_admin.edit_lookup_list"): ActivityEndpointSpec(description="Edited Lookup List", activity_type="admin_system"),
    ("POST", "system_admin.edit_ns_branch"): ActivityEndpointSpec(description="Edited Ns Branch", activity_type="admin_system"),
    ("POST", "system_admin.edit_ns_localunit"): ActivityEndpointSpec(description="Edited Ns Localunit", activity_type="admin_system"),
    ("POST", "system_admin.edit_ns_subbranch"): ActivityEndpointSpec(description="Edited Ns Subbranch", activity_type="admin_system"),
    ("POST", "system_admin.edit_sector"): ActivityEndpointSpec(description="Edited Sector", activity_type="admin_system"),
    ("POST", "system_admin.edit_subsector"): ActivityEndpointSpec(description="Edited Subsector", activity_type="admin_system"),
    ("POST", "system_admin.export_indicators"): ActivityEndpointSpec(description="Exported Indicators", activity_type="admin_system"),
    ("POST", "system_admin.import_common_words"): ActivityEndpointSpec(description="Imported Common Words", activity_type="admin_system"),
    ("POST", "system_admin.import_into_lookup_list"): ActivityEndpointSpec(description="Imported Into Lookup List", activity_type="admin_system"),
    ("POST", "system_admin.import_lookup_list"): ActivityEndpointSpec(description="Imported Lookup List", activity_type="admin_system"),
    ("POST", "system_admin.indicator_bank_neural_map_probe"): ActivityEndpointSpec(description="Completed Indicator Bank Neural Map Probe", activity_type="admin_system"),
    ("POST", "system_admin.move_lookup_list_row"): ActivityEndpointSpec(description="Completed Move Lookup List Row", activity_type="admin_system"),
    ("POST", "system_admin.new_country"): ActivityEndpointSpec(description="Created Country", activity_type="admin_system"),
    ("POST", "system_admin.new_ns_branch"): ActivityEndpointSpec(description="Created Ns Branch", activity_type="admin_system"),
    ("POST", "system_admin.new_ns_localunit"): ActivityEndpointSpec(description="Created Ns Localunit", activity_type="admin_system"),
    ("POST", "system_admin.new_ns_subbranch"): ActivityEndpointSpec(description="Created Ns Subbranch", activity_type="admin_system"),
    ("POST", "system_admin.new_sector"): ActivityEndpointSpec(description="Created Sector", activity_type="admin_system"),
    ("POST", "system_admin.new_subsector"): ActivityEndpointSpec(description="Created Subsector", activity_type="admin_system"),
    ("POST", "system_admin.sync_indicator_bank_remote"): ActivityEndpointSpec(description="Synced Indicator Bank Remote", activity_type="admin_system"),
    ("POST", "system_admin.update_indicator_translations"): ActivityEndpointSpec(description="Updated Indicator Translations", activity_type="admin_system"),
}

