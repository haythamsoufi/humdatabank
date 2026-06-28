#!/usr/bin/env python
"""Seed reporting_period catalog rows from assignment period_name labels.

Run from Backoffice/ when catalog rows are missing for existing labels:
    python scripts/seed_reporting_period_catalog.py --dry-run
    python scripts/seed_reporting_period_catalog.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BACKOFFICE_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKOFFICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKOFFICE_ROOT))

from app import create_app
from app.extensions import db
from app.models.assignments import AssignedForm, ReportingPeriod
from app.services.reporting_period_service import upsert_reporting_period
from app.utils.reporting_period_label_parser import parse_period_label


def seed_reporting_period_catalog(*, dry_run: bool = False) -> dict[str, int]:
    stats = {
        "labels_examined": 0,
        "catalog_created": 0,
        "catalog_updated": 0,
        "unparseable": 0,
        "skipped_existing": 0,
    }

    rows = (
        db.session.query(AssignedForm.period_name)
        .filter(AssignedForm.period_name.isnot(None))
        .distinct()
        .all()
    )
    catalog_names = {
        name
        for (name,) in db.session.query(ReportingPeriod.name).all()
    }

    for (period_name,) in rows:
        label = (period_name or "").strip()
        if not label:
            continue
        stats["labels_examined"] += 1
        parsed = parse_period_label(label)
        if parsed is None:
            stats["unparseable"] += 1
            continue

        period_type, period_start, period_end = parsed
        existing = label in catalog_names
        if existing:
            row = ReportingPeriod.query.filter_by(name=label).first()
            if (
                row
                and (
                    row.period_type != period_type
                    or row.period_start != period_start
                    or row.period_end != period_end
                )
            ):
                stats["catalog_updated"] += 1
                if not dry_run:
                    upsert_reporting_period(
                        label,
                        period_type=period_type,
                        period_start=period_start,
                        period_end=period_end,
                    )
            else:
                stats["skipped_existing"] += 1
            continue

        stats["catalog_created"] += 1
        if not dry_run:
            upsert_reporting_period(
                label,
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
            )
            catalog_names.add(label)

    if not dry_run:
        db.session.commit()

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed reporting_period catalog from period_name labels")
    parser.add_argument("--dry-run", action="store_true", help="Count changes without writing")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        stats = seed_reporting_period_catalog(dry_run=args.dry_run)
        mode = "DRY RUN" if args.dry_run else "APPLIED"
        print(f"[{mode}] labels_examined={stats['labels_examined']}")
        print(f"  catalog_created={stats['catalog_created']}")
        print(f"  catalog_updated={stats['catalog_updated']}")
        print(f"  skipped_existing={stats['skipped_existing']}")
        print(f"  unparseable={stats['unparseable']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
