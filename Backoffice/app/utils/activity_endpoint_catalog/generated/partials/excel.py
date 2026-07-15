"""
AUTO-GENERATED — blueprint 'excel'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    # GET exports: logged explicitly in the route via log_user_activity (activity_type=data_export).
    # Middleware skips GETs for UserActivityLog, so the catalog entry is informational only.
    ("GET", "excel.export_assignment_excel"): ActivityEndpointSpec(description="Exported Assignment Excel", activity_type="data_export"),
    ("GET", "excel.export_upr_country_reporting_template"): ActivityEndpointSpec(description="Exported UPR Country Reporting Excel", activity_type="data_export"),
    # POST imports: logged by middleware (UserActivityLog) AND explicitly via log_entity_activity (EntityActivityLog).
    ("POST", "excel.import_assignment_excel"): ActivityEndpointSpec(description="Imported Assignment Excel", activity_type="admin_assignments"),
    ("POST", "excel.import_upr_country_reporting_template"): ActivityEndpointSpec(description="Imported Upr Country Reporting Template", activity_type="admin_assignments"),
    ("POST", "excel.validate_upr_country_reporting_import"): ActivityEndpointSpec(description="Completed Validate Upr Country Reporting Import", activity_type="admin_assignments"),
}

