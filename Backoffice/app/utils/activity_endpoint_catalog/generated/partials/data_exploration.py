"""
AUTO-GENERATED — blueprint 'data_exploration'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "data_exploration.apply_imputed_value"): ActivityEndpointSpec(description="Completed Apply Imputed Value", activity_type="admin_analytics"),
    ("POST", "data_exploration.get_ai_opinions_for_rows"): ActivityEndpointSpec(description="Completed Ai Opinions For Rows", activity_type="admin_analytics"),
    ("POST", "data_exploration.run_ai_validation_for_rows"): ActivityEndpointSpec(description="Ran Ai Validation For Rows", activity_type="admin_analytics"),
}

