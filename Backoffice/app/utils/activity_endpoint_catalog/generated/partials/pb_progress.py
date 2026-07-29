"""
AUTO-GENERATED — blueprint 'pb_progress'. Do not edit by hand.
Regenerate: python scripts/dev/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "pb_progress.config_import_from_excel"): ActivityEndpointSpec(description="Completed Config Import From Excel", activity_type="admin_other"),
    ("POST", "pb_progress.data_source"): ActivityEndpointSpec(description="Completed Data Source", activity_type="admin_other"),
    ("POST", "pb_progress.generate"): ActivityEndpointSpec(description="Completed Generate", activity_type="admin_other"),
    ("POST", "pb_progress.generate_system_dataset"): ActivityEndpointSpec(description="Generated System Dataset", activity_type="admin_other"),
    ("POST", "pb_progress.mapping_sync"): ActivityEndpointSpec(description="Completed Mapping Sync", activity_type="admin_other"),
    ("POST", "pb_progress.upload_excel"): ActivityEndpointSpec(description="Completed Upload Excel", activity_type="admin_other"),
    ("PUT", "pb_progress.mapping"): ActivityEndpointSpec(description="Updated Mapping", activity_type="admin_other"),
    ("PUT", "pb_progress.report_years"): ActivityEndpointSpec(description="Updated Report Years", activity_type="admin_other"),
    ("PUT", "pb_progress.section_order"): ActivityEndpointSpec(description="Updated Section Order", activity_type="admin_other"),
    ("PUT", "pb_progress.translations"): ActivityEndpointSpec(description="Updated Translations", activity_type="admin_other"),
}

