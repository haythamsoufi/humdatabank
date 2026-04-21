"""
AUTO-GENERATED — blueprint 'ai_management'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "ai_management.ai_review_auto_queue"): ActivityEndpointSpec(description="Completed Ai Review Auto Queue", activity_type="admin_ai"),
    ("POST", "ai_management.ai_review_detail"): ActivityEndpointSpec(description="Completed Ai Review Detail", activity_type="admin_ai"),
    ("POST", "ai_management.bulk_download_documents"): ActivityEndpointSpec(description="Bulk Download Documents", activity_type="admin_ai"),
    ("POST", "ai_management.bulk_reprocess_cancel"): ActivityEndpointSpec(description="Cancelled Bulk Reprocess", activity_type="admin_ai"),
    ("POST", "ai_management.bulk_reprocess_documents"): ActivityEndpointSpec(description="Bulk Reprocess Documents", activity_type="admin_ai"),
    ("POST", "ai_management.bulk_reprocess_metadata_cancel"): ActivityEndpointSpec(description="Cancelled Bulk Reprocess Metadata", activity_type="admin_ai"),
    ("POST", "ai_management.bulk_reprocess_metadata_documents"): ActivityEndpointSpec(description="Bulk Reprocess Metadata Documents", activity_type="admin_ai"),
    ("POST", "ai_management.delete_document"): ActivityEndpointSpec(description="Deleted Document", activity_type="admin_ai"),
    ("POST", "ai_management.process_submitted_document"): ActivityEndpointSpec(description="Processed Submitted Document", activity_type="admin_ai"),
    ("POST", "ai_management.redetect_country_document"): ActivityEndpointSpec(description="Redetected Country Document", activity_type="admin_ai"),
    ("POST", "ai_management.reprocess_document"): ActivityEndpointSpec(description="Reprocessed Document", activity_type="admin_ai"),
    ("POST", "ai_management.reprocess_document_metadata"): ActivityEndpointSpec(description="Reprocessed Document Metadata", activity_type="admin_ai"),
    ("POST", "ai_management.traces_bulk_delete"): ActivityEndpointSpec(description="Completed Traces Bulk Delete", activity_type="admin_ai"),
}

