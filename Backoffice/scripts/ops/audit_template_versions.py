#!/usr/bin/env python
"""Read-only audit of form template version integrity.

Run from Backoffice/:
    python scripts/ops/audit_template_versions.py
    python scripts/ops/audit_template_versions.py --template-id 22
    python scripts/ops/audit_template_versions.py --json

Exit code is 1 when a blocking issue is found (several drafts, inconsistent published
version, duplicate stable_key inside one version), otherwise 0. Rows without a stable_key are
reported as advisory; fix them with scripts/ops/backfill_stable_keys.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKOFFICE_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKOFFICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKOFFICE_ROOT))

from app import create_app
from app.services.platform.template_version_audit import audit_template_versions

TITLES = {
    'multiple_drafts': 'Templates with more than one draft (BLOCKING)',
    'published_inconsistencies': 'Published version / pointer mismatches (BLOCKING)',
    'duplicate_item_keys': 'Items sharing a stable_key inside one version (BLOCKING)',
    'duplicate_section_keys': 'Sections sharing a stable_key inside one version (BLOCKING)',
    'items_without_key': 'Items without stable_key in multi-version templates (advisory)',
    'sections_without_key': 'Sections without stable_key in multi-version templates (advisory)',
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--template-id', type=int, default=None)
    parser.add_argument('--json', action='store_true', help='Print findings as JSON')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        findings = audit_template_versions(args.template_id)

    if args.json:
        print(json.dumps(findings, indent=2, default=str))
    else:
        for name, title in TITLES.items():
            rows = findings[name]
            print(f"{title}: {len(rows)}")
            for row in rows:
                print(f"  - {row}")
        print('RESULT:', 'BLOCKING ISSUES FOUND' if findings['has_blocking_issues'] else 'OK')
    return 1 if findings['has_blocking_issues'] else 0


if __name__ == '__main__':
    sys.exit(main())
