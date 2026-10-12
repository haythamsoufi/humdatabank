#!/usr/bin/env python3
"""Read-only check: T23 assigned_form 34, Jan-Jun 2026, form item 1433.

Confirms the 17 assignments restored on 12 Oct 2026 still have a partner-NS
funding matrix, and prints the form-wide matrix counts. Does not write.

  azure_webapp_tools.bat prod script ops/verify_t23_janjun2026_matrix.py
"""

from __future__ import annotations

import sys
from pathlib import Path

AES_IDS = (
    4089, 4091, 4094, 4096, 4097, 4099, 4100, 4103, 4104, 4105,
    4108, 4109, 4110, 4111, 4112, 4114, 4120,
)
ASSIGNED_FORM_ID = 34
MATRIX_ITEM_ID = 1433
# Austria AES 4096, partner Ukraine (country 185), from the 6 Oct dump.
AUSTRIA_AES_ID = 4096
AUSTRIA_FINGERPRINT_KEY = "185_Total Expenditure"
AUSTRIA_FINGERPRINT_VALUE = "6568756"


def _ensure_app_importable() -> None:
    app_root = Path("/app")
    if (app_root / "run.py").is_file() and (app_root / "app").is_dir():
        if str(app_root) not in sys.path:
            sys.path.insert(0, str(app_root))
        return
    scripts_dir = Path(__file__).resolve().parents[1]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from _bootstrap import setup_cli_paths

    setup_cli_paths(__file__)


_ensure_app_importable()


def main() -> int:
    from sqlalchemy import text

    from app import create_app, db

    app = create_app()
    with app.app_context():
        summary = db.session.execute(
            text(
                """
                SELECT a.status,
                       count(*) AS assignments,
                       count(*) FILTER (
                           WHERE EXISTS (
                               SELECT 1 FROM form_data f
                               WHERE f.assignment_entity_status_id = a.id
                                 AND f.form_item_id = :item_id
                           )
                       ) AS with_matrix
                FROM assignment_entity_status a
                WHERE a.assigned_form_id = :af_id
                GROUP BY a.status
                ORDER BY a.status
                """
            ),
            {"item_id": MATRIX_ITEM_ID, "af_id": ASSIGNED_FORM_ID},
        ).fetchall()

        print(f"assigned_form {ASSIGNED_FORM_ID} item {MATRIX_ITEM_ID} by status")
        print(f"{'status':<16} {'assignments':>12} {'with_matrix':>12}")
        for row in summary:
            print(f"{row.status:<16} {row.assignments:>12} {row.with_matrix:>12}")

        rows = db.session.execute(
            text(
                """
                SELECT a.id AS aes_id,
                       c.name AS entity,
                       c.id AS country_id,
                       a.status,
                       a.completion_rate,
                       f.id AS form_data_id,
                       CASE
                           WHEN f.disagg_data IS NULL THEN 0
                           ELSE (SELECT count(*) FROM json_object_keys(f.disagg_data))
                       END AS n_keys,
                       CASE
                           WHEN f.disagg_data IS NULL THEN 0
                           ELSE (
                               SELECT count(DISTINCT split_part(k, '_', 1))
                               FROM json_object_keys(f.disagg_data) AS k
                           )
                       END AS n_partners,
                       CASE
                           WHEN f.id IS NULL THEN NULL
                           ELSE (f.disagg_data::jsonb ->> :fp_key)
                       END AS fingerprint,
                       EXISTS (
                           SELECT 1 FROM form_data cmt
                           WHERE cmt.assignment_entity_status_id = a.id
                             AND cmt.form_item_id IN (1488, 1489)
                       ) AS has_comment,
                       EXISTS (
                           SELECT 1 FROM form_data st
                           WHERE st.assignment_entity_status_id = a.id
                             AND st.form_item_id = 1434
                       ) AS has_staff
                FROM assignment_entity_status a
                LEFT JOIN country c
                  ON c.id = a.entity_id AND a.entity_type = 'country'
                LEFT JOIN form_data f
                  ON f.assignment_entity_status_id = a.id
                 AND f.form_item_id = :item_id
                WHERE a.assigned_form_id = :af_id
                  AND a.id = ANY(:aes_ids)
                ORDER BY a.id
                """
            ),
            {
                "item_id": MATRIX_ITEM_ID,
                "af_id": ASSIGNED_FORM_ID,
                "aes_ids": list(AES_IDS),
                "fp_key": AUSTRIA_FINGERPRINT_KEY,
            },
        ).fetchall()

        print()
        print(
            f"{'aes':<6} {'entity':<22} {'status':<14} {'pct':>6} "
            f"{'keys':>6} {'partners':>9} {'comment':>8} {'staff':>6}"
        )
        found = {int(r.aes_id) for r in rows}
        missing_ids = [i for i in AES_IDS if i not in found]
        bad = []
        for r in rows:
            pct = "" if r.completion_rate is None else f"{r.completion_rate:g}"
            print(
                f"{r.aes_id:<6} {(r.entity or '?'):<22} {r.status:<14} {pct:>6} "
                f"{r.n_keys:>6} {r.n_partners:>9} "
                f"{('yes' if r.has_comment else 'no'):>8} "
                f"{('yes' if r.has_staff else 'no'):>6}"
            )
            # The 8 Oct wipe left no row. The 18 Sep collapse left exactly three
            # own-country total keys. One partner with a full 9-cell row is valid.
            if r.form_data_id is None or r.n_keys < 4:
                bad.append(int(r.aes_id))

        austria = next((r for r in rows if int(r.aes_id) == AUSTRIA_AES_ID), None)
        print()
        if austria is None:
            print(f"FAIL Austria AES {AUSTRIA_AES_ID} not on assigned_form {ASSIGNED_FORM_ID}")
            return 1
        fp_ok = str(austria.fingerprint) == AUSTRIA_FINGERPRINT_VALUE
        print(
            f"Austria AES {AUSTRIA_AES_ID}: form_data={austria.form_data_id} "
            f"keys={austria.n_keys} partners={austria.n_partners} "
            f"status={austria.status} completion={austria.completion_rate} "
            f"ukraine_expenditure_ok={fp_ok}"
        )
        if missing_ids:
            print(f"FAIL missing AES ids: {missing_ids}")
        if bad:
            print(f"FAIL matrix missing or collapsed (under 4 keys or under 2 partners): {bad}")
        if missing_ids or bad or not fp_ok:
            return 1
        print(f"OK {len(rows)}/{len(AES_IDS)} target assignments have a multi-partner matrix")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
