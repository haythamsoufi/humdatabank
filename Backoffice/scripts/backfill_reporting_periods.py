#!/usr/bin/env python
"""Backfill reporting_period catalog links on assigned_form rows.

Run from Backoffice/:
    python scripts/backfill_reporting_periods.py --dry-run
    python scripts/backfill_reporting_periods.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BACKOFFICE_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKOFFICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKOFFICE_ROOT))

from app import create_app
from app.services.reporting_period_service import backfill_assigned_forms_missing_period


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill assigned_form reporting period fields")
    parser.add_argument("--dry-run", action="store_true", help="Count changes without writing")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        stats = backfill_assigned_forms_missing_period(dry_run=args.dry_run)
        mode = "DRY RUN" if args.dry_run else "APPLIED"
        print(f"[{mode}] examined={stats['examined']}")
        print(f"  synced={stats['synced']}")
        print(f"  cleared_unparseable={stats['cleared_unparseable']}")
        print(f"  skipped_already_linked={stats['skipped_already_linked']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
