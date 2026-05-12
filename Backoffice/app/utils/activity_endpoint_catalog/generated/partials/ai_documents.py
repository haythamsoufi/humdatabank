"""
AUTO-GENERATED — blueprint 'ai_documents'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("DELETE", "ai_documents.delete_document"): ActivityEndpointSpec(description="Deleted Document", activity_type="admin_ai"),
    ("PATCH", "ai_documents.update_document"): ActivityEndpointSpec(description="Updated Document", activity_type="admin_ai"),
    ("POST", "ai_documents.answer_documents"): ActivityEndpointSpec(description="Answered Documents", activity_type="admin_ai"),
    ("POST", "ai_documents.import_ifrc_api_document"): ActivityEndpointSpec(description="Imported Ifrc Api Document", activity_type="admin_ai"),
    ("POST", "ai_documents.import_ifrc_api_documents_bulk"): ActivityEndpointSpec(description="Imported Ifrc Api Documents Bulk", activity_type="admin_ai"),
    ("POST", "ai_documents.import_ifrc_bulk_cancel"): ActivityEndpointSpec(description="Cancelled Import Ifrc Bulk", activity_type="admin_ai"),
    ("POST", "ai_documents.reprocess_document"): ActivityEndpointSpec(description="Reprocessed Document", activity_type="admin_ai"),
    ("POST", "ai_documents.search_documents"): ActivityEndpointSpec(description="Completed Search Documents", activity_type="admin_ai"),
    ("POST", "ai_documents.sync_workflow_docs"): ActivityEndpointSpec(description="Synced Workflow Docs", activity_type="admin_ai"),
    ("POST", "ai_documents.upload_document"): ActivityEndpointSpec(description="Completed Upload Document", activity_type="admin_ai"),
}

