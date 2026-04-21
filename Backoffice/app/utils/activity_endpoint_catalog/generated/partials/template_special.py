"""
AUTO-GENERATED — blueprint 'template_special'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "template_special.export_preview_excel"): ActivityEndpointSpec(description="Exported Preview Excel", activity_type="admin_system"),
    ("POST", "template_special.impute_template2"): ActivityEndpointSpec(description="Completed Impute Template2", activity_type="admin_system"),
    ("POST", "template_special.preview_data_chunked"): ActivityEndpointSpec(description="Previewed Data Chunked", activity_type="admin_system"),
    ("POST", "template_special.preview_imputation"): ActivityEndpointSpec(description="Previewed Imputation", activity_type="admin_system"),
    ("POST", "template_special.preview_imputation_chunked"): ActivityEndpointSpec(description="Previewed Imputation Chunked", activity_type="admin_system"),
    ("POST", "template_special.run_fdrs_sync"): ActivityEndpointSpec(description="Ran Fdrs Sync", activity_type="admin_system"),
    ("POST", "template_special.run_imputation_filtered"): ActivityEndpointSpec(description="Ran Imputation Filtered", activity_type="admin_system"),
    ("POST", "template_special.update_imputation_methods_batch"): ActivityEndpointSpec(description="Updated Imputation Methods Batch", activity_type="admin_system"),
}

