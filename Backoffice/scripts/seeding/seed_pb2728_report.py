#!/usr/bin/env python
"""Seed an example PB27-28 progress report using the core Report Builder.

Run from Backoffice/:
    python scripts/seeding/seed_pb2728_report.py --dry-run
    python scripts/seeding/seed_pb2728_report.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BACKOFFICE_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKOFFICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKOFFICE_ROOT))

from app import create_app
from app.extensions import db
from app.models import ReportDefinition, User
from app.services.reports.definition_service import ReportDefinitionService
from app.services.reports.schema import validate_report_definition
from app.utils.data_quality_constants import FDRS_TEMPLATE_ID

EXAMPLE_SLUG = "pb27-28-progress-example"


def pb2728_report_definition(*, template_id: int) -> dict:
    return {
        "schema_version": 1,
        "filters": {
            "template_ids": [template_id],
            "period_names": [],
            "assignment_statuses": ["submitted", "approved"],
        },
        "sections": [
            {
                "id": "sec-pb2728",
                "title": "PB 2027-2028 Progress",
                "order": 0,
                "widgets": [],
                "dynamic_indicators": {
                    "enabled": True,
                    "rule": {"related_programs_any": ["PB27-28"]},
                    "widget_type": "indicator_dashboard",
                    "data_source_kind": "indicator_dashboard",
                    "group_by": "spef_section",
                    "metric": "sum",
                },
            }
        ],
    }


def seed_pb2728_report(*, dry_run: bool = False, template_id: int = FDRS_TEMPLATE_ID) -> dict[str, str | int]:
    definition = pb2728_report_definition(template_id=template_id)
    validate_report_definition(definition)

    owner = User.query.filter(User.email.ilike("test_sys@%")).order_by(User.id.asc()).first()
    if owner is None:
        owner = User.query.order_by(User.id.asc()).first()
    if owner is None:
        raise RuntimeError("No users found — run database seed/migrations first.")

    existing = ReportDefinition.query.filter_by(slug=EXAMPLE_SLUG).first()
    if dry_run:
        action = "update" if existing else "create"
        return {
            "action": action,
            "slug": EXAMPLE_SLUG,
            "owner_id": owner.id,
            "template_id": template_id,
        }

    if existing:
        existing.title = "PB 2027-2028 Progress (Report Builder example)"
        existing.description = (
            "Example report mirroring the pb_progress PB27-28 dashboard: "
            "SPEF sections with line charts (year on x-axis) and NS breakdown tables."
        )
        existing.definition_json = definition
        existing.schema_version = 1
        existing.updated_by_id = owner.id
        db.session.commit()
        return {"action": "updated", "report_id": existing.id, "slug": EXAMPLE_SLUG}

    report = ReportDefinitionService.create_report(
        owner,
        title="PB 2027-2028 Progress (Report Builder example)",
        description=(
            "Example report mirroring the pb_progress PB27-28 dashboard: "
            "SPEF sections with line charts (year on x-axis) and NS breakdown tables."
        ),
        definition=definition,
        scope_json={"template_ids": [template_id], "country_ids": []},
    )
    report.slug = EXAMPLE_SLUG
    db.session.commit()
    return {"action": "created", "report_id": report.id, "slug": EXAMPLE_SLUG}


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed PB27-28 example report definition")
    parser.add_argument("--dry-run", action="store_true", help="Validate only; do not write")
    parser.add_argument("--template-id", type=int, default=FDRS_TEMPLATE_ID, help="FDRS template id")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        result = seed_pb2728_report(dry_run=args.dry_run, template_id=args.template_id)
        print(result)


if __name__ == "__main__":
    main()
