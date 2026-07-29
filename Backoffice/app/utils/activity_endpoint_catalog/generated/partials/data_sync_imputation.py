"""
AUTO-GENERATED — blueprint 'data_sync_imputation'. Do not edit by hand.
Regenerate: python scripts/dev/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "data_sync_imputation.data_sync_cancel"): ActivityEndpointSpec(description="Cancelled Data Sync", activity_type="admin_system"),
    ("POST", "data_sync_imputation.export_preview_excel"): ActivityEndpointSpec(description="Exported Preview Excel", activity_type="admin_system"),
    ("POST", "data_sync_imputation.impute_template2"): ActivityEndpointSpec(description="Completed Impute Template2", activity_type="admin_system"),
    ("POST", "data_sync_imputation.preview_data_chunked"): ActivityEndpointSpec(description="Previewed Data Chunked", activity_type="admin_system"),
    ("POST", "data_sync_imputation.preview_imputation"): ActivityEndpointSpec(description="Previewed Imputation", activity_type="admin_system"),
    ("POST", "data_sync_imputation.preview_imputation_chunked"): ActivityEndpointSpec(description="Previewed Imputation Chunked", activity_type="admin_system"),
    ("POST", "data_sync_imputation.run_data_sync"): ActivityEndpointSpec(description="Ran Data Sync", activity_type="admin_system"),
    ("POST", "data_sync_imputation.run_imputation_filtered"): ActivityEndpointSpec(description="Ran Imputation Filtered", activity_type="admin_system"),
    ("POST", "data_sync_imputation.update_imputation_methods_batch"): ActivityEndpointSpec(description="Updated Imputation Methods Batch", activity_type="admin_system"),
}

