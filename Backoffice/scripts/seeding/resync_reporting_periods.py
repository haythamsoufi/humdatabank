#!/usr/bin/env python
"""Re-sync assigned_form rows with reporting_period catalog links.

Run from Backoffice/ after seeding/updating catalog rows:
    python scripts/resync_reporting_periods.py --dry-run
    python scripts/resync_reporting_periods.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BACKOFFICE_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKOFFICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKOFFICE_ROOT))

from app import create_app
from app.services.forms.reporting_period_service import resync_all_reporting_periods


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-link assigned_form rows to reporting_period catalog rows",
    )
    parser.add_argument("--dry-run", action="store_true", help="Count changes without writing")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        stats = resync_all_reporting_periods(dry_run=args.dry_run)
        mode = "DRY RUN" if args.dry_run else "APPLIED"
        print(f"[{mode}] assigned_examined={stats['assigned_examined']}")
        print(f"  assigned_linked={stats['assigned_linked']}")
        print(f"  assigned_missing_catalog={stats['assigned_missing_catalog']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
