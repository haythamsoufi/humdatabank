"""
AUTO-GENERATED — blueprint 'form_builder'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "form_builder.configure_dynamic_section"): ActivityEndpointSpec(description="Configured Dynamic Section", activity_type="admin_forms"),
    ("POST", "form_builder.configure_repeat_section"): ActivityEndpointSpec(description="Configured Repeat Section", activity_type="admin_forms"),
    ("POST", "form_builder.create_draft_version"): ActivityEndpointSpec(description="Created Draft Version", activity_type="admin_forms"),
    ("POST", "form_builder.delete_template"): ActivityEndpointSpec(description="Deleted Template", activity_type="admin_forms"),
    ("POST", "form_builder.delete_template_section"): ActivityEndpointSpec(description="Deleted Template Section", activity_type="admin_forms"),
    ("POST", "form_builder.delete_template_version"): ActivityEndpointSpec(description="Deleted Template Version", activity_type="admin_forms"),
    ("POST", "form_builder.deploy_template_version"): ActivityEndpointSpec(description="Deployed Template Version", activity_type="admin_forms"),
    ("POST", "form_builder.discard_template_draft"): ActivityEndpointSpec(description="Discarded Template Draft", activity_type="admin_forms"),
    ("POST", "form_builder.duplicate_item"): ActivityEndpointSpec(description="Duplicated Item", activity_type="admin_forms"),
    ("POST", "form_builder.duplicate_template"): ActivityEndpointSpec(description="Duplicated Template", activity_type="admin_forms"),
    ("POST", "form_builder.duplicate_template_section"): ActivityEndpointSpec(description="Duplicated Template Section", activity_type="admin_forms"),
    ("POST", "form_builder.edit_template"): ActivityEndpointSpec(description="Edited Template", activity_type="admin_forms"),
    ("POST", "form_builder.edit_template_section"): ActivityEndpointSpec(description="Edited Template Section", activity_type="admin_forms"),
    ("POST", "form_builder.import_kobo_xls"): ActivityEndpointSpec(description="Imported Kobo Xls", activity_type="admin_forms"),
    ("POST", "form_builder.import_template_excel"): ActivityEndpointSpec(description="Imported Template Excel", activity_type="admin_forms"),
    ("POST", "form_builder.kobo_data_import_analyze"): ActivityEndpointSpec(description="Completed Kobo Data Import Analyze", activity_type="admin_forms"),
    ("POST", "form_builder.kobo_data_import_execute"): ActivityEndpointSpec(description="Completed Kobo Data Import Execute", activity_type="admin_forms"),
    ("POST", "form_builder.kobo_data_import_map_columns"): ActivityEndpointSpec(description="Completed Kobo Data Import Map Columns", activity_type="admin_forms"),
    ("POST", "form_builder.kobo_data_import_match"): ActivityEndpointSpec(description="Completed Kobo Data Import Match", activity_type="admin_forms"),
    ("POST", "form_builder.kobo_data_import_preview"): ActivityEndpointSpec(description="Completed Kobo Data Import Preview", activity_type="admin_forms"),
    ("POST", "form_builder.kobo_data_import_template_structure"): ActivityEndpointSpec(description="Completed Kobo Data Import Template Structure", activity_type="admin_forms"),
    ("POST", "form_builder.manage_template_variables"): ActivityEndpointSpec(description="Managed Template Variables", activity_type="admin_forms"),
    ("POST", "form_builder.new_template"): ActivityEndpointSpec(description="Created Template", activity_type="admin_forms"),
    ("POST", "form_builder.new_template_section"): ActivityEndpointSpec(description="Created Template Section", activity_type="admin_forms"),
    ("POST", "form_builder.unarchive_item"): ActivityEndpointSpec(description="Completed Unarchive Item", activity_type="admin_forms"),
    ("POST", "form_builder.unarchive_section"): ActivityEndpointSpec(description="Completed Unarchive Section", activity_type="admin_forms"),
    ("POST", "form_builder.update_draft_comment"): ActivityEndpointSpec(description="Updated Draft Comment", activity_type="admin_forms"),
    ("POST", "form_builder.update_version_comment"): ActivityEndpointSpec(description="Updated Version Comment", activity_type="admin_forms"),
}

