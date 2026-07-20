"""Shared constants for data quality and validation (template-agnostic)."""

import os

# FDRS template — used only by fdrs_v1 catalog / rule pack, not generic routes.
FDRS_TEMPLATE_ID = 21

# Unified Planning and Reporting (UPR) country templates shown on the
# Validation Dashboard as one product tab (Reporting + Planning).
UPR_REPORTING_TEMPLATE_ID = 33
UPR_PLANNING_TEMPLATE_ID = 24
UPR_VALIDATION_TEMPLATE_IDS = (UPR_REPORTING_TEMPLATE_ID, UPR_PLANNING_TEMPLATE_ID)
# Legacy published copy of country reporting; folded into the UPR tab when 33 exists.
UPR_LEGACY_REPORTING_TEMPLATE_ID = 25

METHODOLOGY_FDRS_V1 = "fdrs_v1"
RULE_PACK_FDRS_MATRIX_V1 = "fdrs_matrix_v1"

METHODOLOGY_TO_DEFAULT_RULE_PACK = {
    METHODOLOGY_FDRS_V1: RULE_PACK_FDRS_MATRIX_V1,
}

REGISTERED_METHODOLOGIES = (METHODOLOGY_FDRS_V1,)
REGISTERED_RULE_PACKS = (RULE_PACK_FDRS_MATRIX_V1,)


def is_data_quality_dashboard_enabled() -> bool:
    """Master switch for QoD dashboard tabs and API (env: DATA_QUALITY_DASHBOARD_ENABLED)."""
    raw = os.environ.get("DATA_QUALITY_DASHBOARD_ENABLED", "").strip().lower()
    return raw in ("1", "true", "yes", "on")
