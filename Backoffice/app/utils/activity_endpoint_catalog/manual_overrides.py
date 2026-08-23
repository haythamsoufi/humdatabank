"""
Hand-curated catalog entries (override generated defaults).

Key: (HTTP_METHOD or "*", flask endpoint string).
Write the sentence a reviewer would say — no Flask view names, no Title Case leftovers.
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec

MANUAL_ACTIVITY_OVERRIDES: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "settings.manage_settings"): ActivityEndpointSpec(
        description="Updated system configuration",
        activity_type="admin_settings",
    ),
    ("*", "ai_management.traces_bulk_delete"): ActivityEndpointSpec(
        description="Deleted AI traces",
        activity_type="admin_ai",
    ),
    ("*", "content_management.edit_resource"): ActivityEndpointSpec(
        description="Edited a resource",
        activity_type="admin_content",
    ),
    ("*", "embed_management.create_embed_content"): ActivityEndpointSpec(
        description="Created embed content",
        activity_type="admin_embed",
    ),
    ("POST", "utilities.apply_indicator_import"): ActivityEndpointSpec(
        description="Applied an indicator import",
        activity_type="admin_utilities",
    ),
    ("POST", "main.return_assignment_for_revision"): ActivityEndpointSpec(
        description="Returned an assignment for revision",
        activity_type="admin_assignments",
    ),
    ("POST", "indicator_bank_compat.indicator_suggestion"): ActivityEndpointSpec(
        description="Submitted an indicator suggestion",
        activity_type="admin_system",
    ),
    ("POST", "api_key_management.edit_api_key"): ActivityEndpointSpec(
        description="Edited an API key",
        activity_type="admin_settings",
    ),
    ("POST", "api_key_management.rotate_api_key"): ActivityEndpointSpec(
        description="Rotated an API key",
        activity_type="admin_settings",
    ),
    ("POST", "upr_excel_import.run_import"): ActivityEndpointSpec(
        description="Imported UPR country reporting data",
        activity_type="admin_assignments",
    ),
    ("POST", "excel.import_upr_country_reporting_template"): ActivityEndpointSpec(
        description="Imported a UPR country reporting file",
        activity_type="admin_assignments",
    ),
    ("POST", "excel.validate_upr_country_reporting_import"): ActivityEndpointSpec(
        description="Checked a UPR country reporting file",
        activity_type="admin_assignments",
    ),
    ("POST", "excel.import_unified_country_plan_template"): ActivityEndpointSpec(
        description="Imported a Unified Country Plan file",
        activity_type="admin_assignments",
    ),
    ("POST", "pb_progress.generate"): ActivityEndpointSpec(
        description="Generated a Planning and Budgeting dataset",
        activity_type="admin_plugin",
    ),
    ("POST", "pb_progress.upload_excel"): ActivityEndpointSpec(
        description="Uploaded a Planning and Budgeting spreadsheet",
        activity_type="admin_plugin",
    ),
    ("POST", "pb_progress.generate_system_dataset"): ActivityEndpointSpec(
        description="Generated a Planning and Budgeting system dataset",
        activity_type="admin_plugin",
    ),
    ("POST", "upr_visuals.generate"): ActivityEndpointSpec(
        description="Generated UPR visuals",
        activity_type="admin_plugin",
    ),
    ("POST", "system_admin.edit_indicator_bank"): ActivityEndpointSpec(
        description="Updated an indicator in the indicator bank",
        activity_type="admin_system",
    ),
    ("POST", "system_admin.edit_spef_lookup"): ActivityEndpointSpec(
        description="Updated a SPEF lookup list",
        activity_type="admin_system",
    ),
    ("POST", "ai_management.delete_document"): ActivityEndpointSpec(
        description="Deleted a document",
        activity_type="admin_ai",
    ),
    ("POST", "ai_management.process_submitted_document"): ActivityEndpointSpec(
        description="Processed a submitted document",
        activity_type="admin_ai",
    ),
    ("POST", "ai_management.bulk_reprocess_documents"): ActivityEndpointSpec(
        description="Reprocessed documents",
        activity_type="admin_ai",
    ),
    ("POST", "ai_management.import_system_bulk"): ActivityEndpointSpec(
        description="Imported system documents",
        activity_type="admin_ai",
    ),
    ("POST", "assignment_management.bulk_update_entity_status"): ActivityEndpointSpec(
        description="Updated assignment status for multiple countries",
        activity_type="admin_assignments",
    ),
    ("POST", "assignment_management.new_assignment"): ActivityEndpointSpec(
        description="Created an assignment",
        activity_type="admin_assignments",
    ),
    ("POST", "assignment_management.edit_assignment"): ActivityEndpointSpec(
        description="Updated an assignment",
        activity_type="admin_assignments",
    ),
    ("POST", "assignment_management.close_assignment"): ActivityEndpointSpec(
        description="Closed an assignment",
        activity_type="admin_assignments",
    ),
    ("POST", "assignment_management.delete_assignment"): ActivityEndpointSpec(
        description="Deleted an assignment",
        activity_type="admin_assignments",
    ),
    ("POST", "assignment_management.add_entity_to_assignment"): ActivityEndpointSpec(
        description="Added a country or entity to an assignment",
        activity_type="admin_assignments",
    ),
    ("POST", "assignment_management.update_entity_status"): ActivityEndpointSpec(
        description="Updated assignment status",
        activity_type="admin_assignments",
    ),
    ("POST", "assignment_management.toggle_assignment_active"): ActivityEndpointSpec(
        description="Changed whether an assignment is active",
        activity_type="admin_assignments",
    ),
    ("POST", "utilities.delete_all_removed_translations"): ActivityEndpointSpec(
        description="Deleted unused translations",
        activity_type="admin_utilities",
    ),
    ("POST", "utilities.extract_update_translations"): ActivityEndpointSpec(
        description="Updated the translation catalog from source",
        activity_type="admin_utilities",
    ),
    ("POST", "admin_communication.api_retry_email_delivery"): ActivityEndpointSpec(
        description="Retried an email delivery",
        activity_type="admin_notifications",
    ),
    ("POST", "admin_communication.api_retry_failed_email_deliveries"): ActivityEndpointSpec(
        description="Retried failed email deliveries",
        activity_type="admin_notifications",
    ),
    ("POST", "forms.view_edit_form"): ActivityEndpointSpec(
        description="Updated form data",
        activity_type="admin_forms",
    ),
    ("POST", "analytics.end_session"): ActivityEndpointSpec(
        description="Ended a user session",
        activity_type="admin_analytics",
    ),
    ("POST", "analytics.cleanup_sessions"): ActivityEndpointSpec(
        description="Cleaned up idle sessions",
        activity_type="admin_analytics",
    ),
    ("POST", "security.resolve_security_event"): ActivityEndpointSpec(
        description="Resolved a security event",
        activity_type="admin_monitoring",
    ),
}
