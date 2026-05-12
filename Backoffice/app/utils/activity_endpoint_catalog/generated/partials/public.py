"""
AUTO-GENERATED — blueprint 'public'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "public.run_db_migrations"): ActivityEndpointSpec(description="Ran Db Migrations", activity_type="admin_portal"),
}

