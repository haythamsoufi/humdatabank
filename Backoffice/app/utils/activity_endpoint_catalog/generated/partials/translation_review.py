"""
AUTO-GENERATED — blueprint 'translation_review'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "translation_review.save_review_string"): ActivityEndpointSpec(description="Completed Save Review String", activity_type="admin_other"),
    ("POST", "translation_review.toggle_review_mode"): ActivityEndpointSpec(description="Toggled Review Mode", activity_type="admin_other"),
}

