#!/usr/bin/env python3
"""Merge a duplicate sector into the sector Backoffice already keeps.

The legacy Indicator Bank names the sector "WASH". Backoffice spells that
same sector "Water, Sanitation, and Hygiene" and stores the logo and the
WASH subsectors there. A second active sector named "WASH" makes the public
home page show both tiles.

Indicators that point at the duplicate are repointed at the kept sector.
The duplicate is deleted only when it has no subsectors.

Dry run (default):

    python scripts/ops/merge_duplicate_sector.py

Write:

    python scripts/ops/merge_duplicate_sector.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

for candidate in (Path("/app"), Path(__file__).resolve().parent.parent.parent):
    if (candidate / "app").is_dir() and (candidate / "run.py").is_file():
        root = str(candidate)
        if root not in sys.path:
            sys.path.insert(0, root)
        scripts = str(candidate / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        break
else:
    from _bootstrap import setup_cli_paths

    setup_cli_paths(__file__)

from app import create_app  # noqa: E402


def _rows_for(model, column, source_id: int):
    from sqlalchemy import or_

    return model.query.filter(
        or_(
            column["primary"].astext == str(source_id),
            column["secondary"].astext == str(source_id),
            column["tertiary"].astext == str(source_id),
        )
    ).all()


def _rewrite_sector_levels(payload, source_id: int, target_id: int):
    """Replace source_id with target_id in a primary/secondary/tertiary map.

    Defined here so this script can run on a container that has not been
    deployed with the matching service helper yet.
    """
    if not isinstance(payload, dict):
        return None, False

    def _as_id(value):
        if value is None or value == "":
            return None
        if value == source_id or str(value) == str(source_id):
            return target_id
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    updated = {}
    seen = set()
    for level in ("primary", "secondary", "tertiary"):
        sector_id = _as_id(payload.get(level))
        if sector_id is None or sector_id in seen:
            continue
        seen.add(sector_id)
        updated[level] = sector_id

    original = {}
    for level in ("primary", "secondary", "tertiary"):
        raw = payload.get(level)
        if raw in (None, ""):
            continue
        try:
            original[level] = int(raw)
        except (TypeError, ValueError):
            return (updated or None), True
    return (updated or None), updated != original


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source-name", default="WASH")
    parser.add_argument("--target-name", default="Water, Sanitation, and Hygiene")
    parser.add_argument("--apply", action="store_true", help="Write the merge. Default is a dry run.")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        from sqlalchemy.orm.attributes import flag_modified

        from app.extensions import db
        from app.models import IndicatorBank, IndicatorBankHistory, IndicatorSuggestion, Sector, SubSector

        source = Sector.query.filter_by(name=args.source_name).first()
        target = Sector.query.filter_by(name=args.target_name).first()
        if source is None:
            print(json.dumps({"ok": True, "action": "already_absent", "source_name": args.source_name}))
            return 0
        if target is None:
            print(json.dumps({"ok": False, "error": "target sector not found", "target_name": args.target_name}))
            return 1
        if source.id == target.id:
            print(json.dumps({"ok": False, "error": "source and target are the same sector", "id": source.id}))
            return 1

        subsectors = SubSector.query.filter_by(sector_id=source.id).all()
        if subsectors:
            print(json.dumps({
                "ok": False,
                "error": "source sector still has subsectors; move those before deleting it",
                "source_id": source.id,
                "subsector_ids": [row.id for row in subsectors],
            }))
            return 1

        tables = (
            ("indicator_bank", IndicatorBank, IndicatorBank.sector),
            ("indicator_bank_history", IndicatorBankHistory, IndicatorBankHistory.sector),
            ("indicator_suggestion", IndicatorSuggestion, IndicatorSuggestion.sector),
        )
        summary = {
            "ok": True,
            "apply": bool(args.apply),
            "source": {"id": source.id, "name": source.name, "logo_filename": source.logo_filename},
            "target": {"id": target.id, "name": target.name, "logo_filename": target.logo_filename},
            "rows": {},
            "backup": [],
        }
        pending = []
        for label, model, column in tables:
            rows = _rows_for(model, column, source.id)
            changed = 0
            for row in rows:
                rewritten, did_change = _rewrite_sector_levels(row.sector, source.id, target.id)
                if not did_change:
                    continue
                changed += 1
                pending.append((row, rewritten))
                summary["backup"].append({
                    "table": label,
                    "id": row.id,
                    "sector": row.sector,
                })
            summary["rows"][label] = {"matched": len(rows), "rewritten": changed}

        print(json.dumps(summary, indent=2))
        if not args.apply:
            return 0

        for row, rewritten in pending:
            row.sector = rewritten
            flag_modified(row, "sector")
        db.session.delete(source)
        db.session.commit()
        print(json.dumps({"deleted_sector_id": source.id, "deleted_sector_name": args.source_name}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
