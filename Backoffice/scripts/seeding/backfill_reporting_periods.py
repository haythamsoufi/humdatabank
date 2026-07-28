#!/usr/bin/env python
"""Backfill reporting_period catalog links on assigned_form rows.

Run from Backoffice/:
    python scripts/backfill_reporting_periods.py --dry-run
    python scripts/backfill_reporting_periods.py
    python scripts/backfill_reporting_periods.py --resync-all
    python scripts/backfill_reporting_periods.py --seed-catalog
    python scripts/backfill_reporting_periods.py --seed-catalog --resync-all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BACKOFFICE_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKOFFICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKOFFICE_ROOT))

from app import create_app
from app.services.forms.reporting_period_service import (
    backfill_assigned_forms_missing_period,
    resync_all_reporting_periods,
)
from scripts.seed_reporting_period_catalog import seed_reporting_period_catalog


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill assigned_form reporting period fields")
    parser.add_argument("--dry-run", action="store_true", help="Count changes without writing")
    parser.add_argument(
        "--resync-all",
        action="store_true",
        help="Re-link every assigned form to the catalog (not only missing period_id)",
    )
    parser.add_argument(
        "--seed-catalog",
        action="store_true",
        help="Seed/update reporting_period catalog rows from period_name labels (maintenance scripts only)",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        mode = "DRY RUN" if args.dry_run else "APPLIED"

        if args.seed_catalog:
            seed_stats = seed_reporting_period_catalog(dry_run=args.dry_run)
            print(f"[{mode}] seed labels_examined={seed_stats['labels_examined']}")
            print(f"  catalog_created={seed_stats['catalog_created']}")
            print(f"  catalog_updated={seed_stats['catalog_updated']}")
            print(f"  skipped_existing={seed_stats['skipped_existing']}")
            print(f"  unparseable={seed_stats['unparseable']}")

        if args.resync_all:
            stats = resync_all_reporting_periods(dry_run=args.dry_run)
            print(f"[{mode}] resync assigned_examined={stats['assigned_examined']}")
            print(f"  assigned_linked={stats['assigned_linked']}")
            print(f"  assigned_missing_catalog={stats['assigned_missing_catalog']}")
        elif not args.seed_catalog:
            stats = backfill_assigned_forms_missing_period(dry_run=args.dry_run)
            print(f"[{mode}] examined={stats['examined']}")
            print(f"  synced={stats['synced']}")
            print(f"  missing_catalog={stats['missing_catalog']}")
            print(f"  skipped_already_linked={stats['skipped_already_linked']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
