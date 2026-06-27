#!/usr/bin/env python
"""Repair submission FK remapping after a deploy that ran without stable_key alignment.

Use when a template was deployed but submission data still points at the archived
version's form_item / form_section ids.

Run from Backoffice/:
    python scripts/repair_version_deploy_migration.py --template-id 34 --from-version 40 --to-version 41
    python scripts/repair_version_deploy_migration.py --template-id 34 --from-version 40 --to-version 41 --dry-run
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
from app.models import FormTemplate
from app.services.version_deploy_migration_service import (
    VersionDeployMigrationError,
    VersionDeployMigrationService,
)


def main() -> int:
    parser = argparse.ArgumentParser(description='Repair deploy-time submission FK remapping')
    parser.add_argument('--template-id', type=int, required=True)
    parser.add_argument('--from-version', type=int, required=True, help='Archived/previous version id')
    parser.add_argument('--to-version', type=int, required=True, help='Currently published version id')
    parser.add_argument('--dry-run', action='store_true', help='Align and report without committing')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        template = FormTemplate.query.get(args.template_id)
        if not template:
            print(f'Template {args.template_id} not found.')
            return 1

        try:
            summary = VersionDeployMigrationService.migrate_submission_fks(
                args.from_version,
                args.to_version,
                args.template_id,
            )
        except VersionDeployMigrationError as exc:
            print(f'Repair failed: {exc}')
            db.session.rollback()
            return 1

        print('Repair summary:')
        print(f"  matched_items={summary.get('matched_items')}")
        print(f"  matched_sections={summary.get('matched_sections')}")
        print(f"  remapped_rows={summary.get('remapped_rows')}")
        print(f"  orphaned_items={summary.get('orphaned_items')}")
        print(f"  per_table={summary.get('per_table')}")
        print(f"  stable_key_alignment={summary.get('stable_key_alignment')}")

        if args.dry_run:
            db.session.rollback()
            print('DRY RUN — no changes committed.')
        else:
            db.session.commit()
            print('Committed.')
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
