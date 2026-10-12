#!/usr/bin/env python3
"""Compare live T23 item 1433 matrices to the 6 Oct dump extract. Read-only.

Expected payloads are the JSON embedded in
``restore_t23_myr26_funding_matrix_1433.sql`` (taken from the 6 Oct dump).
Prints match/mismatch per assignment. Does not print cell values.

  python scripts/ops/compare_t23_matrix_to_dump_extract.py path/to/expected.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


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


def _norm(value):
    if isinstance(value, bool):
        return ("b", value)
    if isinstance(value, (int, float)):
        return ("n", float(value))
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            return ("s", value)
        try:
            return ("n", float(text))
        except ValueError:
            return ("s", value)
    return ("j", json.dumps(value, sort_keys=True, default=str))


def _as_dict(raw):
    if raw is None:
        return None
    if isinstance(raw, str):
        return json.loads(raw)
    return dict(raw)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: compare_t23_matrix_to_dump_extract.py expected.json", file=sys.stderr)
        return 2
    expected = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    aes_ids = [int(k) for k in expected["matrices"]]

    from sqlalchemy import text

    from app import create_app, db

    app = create_app()
    mismatches = 0
    status_diffs = 0
    with app.app_context():
        rows = db.session.execute(
            text(
                """
                SELECT a.id AS aes_id,
                       c.name AS entity,
                       a.status,
                       f.disagg_data
                FROM assignment_entity_status a
                LEFT JOIN country c
                  ON c.id = a.entity_id AND a.entity_type = 'country'
                LEFT JOIN form_data f
                  ON f.assignment_entity_status_id = a.id
                 AND f.form_item_id = 1433
                WHERE a.id = ANY(:aes_ids)
                ORDER BY a.id
                """
            ),
            {"aes_ids": aes_ids},
        ).fetchall()
        by_id = {int(r.aes_id): r for r in rows}
        for aes_id in aes_ids:
            spec = expected["matrices"][str(aes_id)]
            row = by_id.get(aes_id)
            name = spec["name"]
            if row is None:
                print(f"MISSING assignment {aes_id} {name}")
                mismatches += 1
                continue
            live = _as_dict(row.disagg_data)
            want = spec["disagg"]
            if live is None:
                print(f"MISSING matrix {aes_id} {row.entity or name}")
                mismatches += 1
            else:
                live_n = {k: _norm(v) for k, v in live.items()}
                want_n = {k: _norm(v) for k, v in want.items()}
                missing = sorted(set(want_n) - set(live_n))
                extra = sorted(set(live_n) - set(want_n))
                changed = sorted(k for k in set(want_n) & set(live_n) if want_n[k] != live_n[k])
                if missing or extra or changed:
                    mismatches += 1
                    print(
                        f"DIFF {aes_id} {row.entity or name}: "
                        f"missing={len(missing)} extra={len(extra)} changed={len(changed)}"
                    )
                    if missing[:8]:
                        print("  missing keys: " + ", ".join(missing[:8]))
                    if extra[:8]:
                        print("  extra keys: " + ", ".join(extra[:8]))
                    if changed[:8]:
                        print("  changed keys: " + ", ".join(changed[:8]))
                else:
                    print(f"MATCH {aes_id} {row.entity or name}: {len(want_n)} cells")
            dump_status = spec["status"]
            if row.status != dump_status:
                status_diffs += 1
                print(f"  status dump={dump_status} live={row.status}")

    print()
    print(f"matrices_identical={len(aes_ids) - mismatches}/{len(aes_ids)}")
    print(f"status_differs_from_dump={status_diffs}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
