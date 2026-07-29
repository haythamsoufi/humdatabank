#!/usr/bin/env python
"""Pre-flight checks before data submission integrity migrations (F2, F3, F9).

Run from Backoffice/:
    python scripts/check_data_submission_integrity.py

Exit code 0 when all checks pass; 1 when issues are found.
"""
from __future__ import annotations

import sys
from pathlib import Path

_scripts = Path(__file__).resolve().parents[1]
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))
from _bootstrap import setup_cli_paths

setup_cli_paths(__file__)

from sqlalchemy import text

from app import create_app
from app.extensions import db


CHECKS = [
    (
        "form_data duplicates (aes + form_item)",
        """
        SELECT assignment_entity_status_id, form_item_id, COUNT(*) AS cnt
        FROM form_data
        WHERE assignment_entity_status_id IS NOT NULL
        GROUP BY 1, 2
        HAVING COUNT(*) > 1
        LIMIT 20
        """,
    ),
    (
        "form_data duplicates (public_submission + form_item)",
        """
        SELECT public_submission_id, form_item_id, COUNT(*) AS cnt
        FROM form_data
        WHERE public_submission_id IS NOT NULL
        GROUP BY 1, 2
        HAVING COUNT(*) > 1
        LIMIT 20
        """,
    ),
    (
        "repeat_group_data duplicates (instance + form_item)",
        """
        SELECT repeat_instance_id, form_item_id, COUNT(*) AS cnt
        FROM repeat_group_data
        GROUP BY 1, 2
        HAVING COUNT(*) > 1
        LIMIT 20
        """,
    ),
    (
        "orphan form_data rows (both parent FKs NULL)",
        """
        SELECT COUNT(*) FROM form_data
        WHERE assignment_entity_status_id IS NULL AND public_submission_id IS NULL
        """,
    ),
    (
        "orphan dynamic_indicator_data rows",
        """
        SELECT COUNT(*) FROM dynamic_indicator_data
        WHERE assignment_entity_status_id IS NULL AND public_submission_id IS NULL
        """,
    ),
    (
        "orphan repeat_group_instance rows",
        """
        SELECT COUNT(*) FROM repeat_group_instance
        WHERE assignment_entity_status_id IS NULL AND public_submission_id IS NULL
        """,
    ),
    (
        "malformed form_data disagg_data",
        """
        SELECT COUNT(*) FROM form_data
        WHERE disagg_data IS NOT NULL
          AND (disagg_data::jsonb ? 'mode')
          AND NOT (disagg_data::jsonb ? 'values')
        """,
    ),
    (
        "malformed dynamic_indicator_data disagg_data",
        """
        SELECT COUNT(*) FROM dynamic_indicator_data
        WHERE disagg_data IS NOT NULL
          AND (disagg_data::jsonb ? 'mode')
          AND NOT (disagg_data::jsonb ? 'values')
        """,
    ),
    (
        "malformed repeat_group_data disagg_data",
        """
        SELECT COUNT(*) FROM repeat_group_data
        WHERE disagg_data IS NOT NULL
          AND (disagg_data::jsonb ? 'mode')
          AND NOT (disagg_data::jsonb ? 'values')
        """,
    ),
]


def main() -> int:
    app = create_app()
    failed = False
    with app.app_context():
        for label, sql in CHECKS:
            rows = db.session.execute(text(sql)).fetchall()
            if not rows:
                print(f"[OK] {label}: 0 issues")
                continue
            # COUNT(*) checks return a single row with count
            if len(rows) == 1 and len(rows[0]) == 1 and rows[0][0] == 0:
                print(f"[OK] {label}: 0 issues")
                continue
            failed = True
            print(f"[FAIL] {label}: {len(rows)} issue(s)")
            for row in rows[:10]:
                print(f"       {row}")
    if failed:
        print("\nResolve issues above before running integrity migrations.")
        return 1
    print("\nAll pre-flight checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
