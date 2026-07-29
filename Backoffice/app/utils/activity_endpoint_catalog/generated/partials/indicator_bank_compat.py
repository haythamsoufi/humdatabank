"""
AUTO-GENERATED — blueprint 'indicator_bank_compat'. Do not edit by hand.
Regenerate: python scripts/dev/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "indicator_bank_compat.indicator_suggestion"): ActivityEndpointSpec(description="Completed Indicator Suggestion", activity_type="admin_other"),
}

