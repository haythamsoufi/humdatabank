#!/usr/bin/env python
"""Give template 22's three funding-year tables distinct light colours.

The year header uses the stronger shade. The Funding Requirements subgroup uses
the lighter shade, which wins for those columns. ``confirmedfn`` has no subgroup,
so it keeps the year shade. Labels and column codes are left as they are.
Saved form data is not touched.

    python scripts/ops/tint_t22_year_groups.py
    python scripts/ops/tint_t22_year_groups.py --apply
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

_scripts = Path(__file__).resolve().parents[1]
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))
from _bootstrap import setup_cli_paths  # noqa: E402

setup_cli_paths(__file__)

from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import FormItem, FormTemplate  # noqa: E402

# (year header, table body). Cells render at 22% of the body colour mixed with white,
# so the stored body colour is stronger than the tint people see. The year header is
# solid and darker than that tint.
YEAR_COLOURS = {
    0: ("#5f97c9", "#b5d4ef"),
    1: ("#6aaf58", "#c3e2b6"),
    2: ("#c48a28", "#f0d08a"),
}


def _year_offset(group_key: str) -> int | None:
    base = group_key.split("::", 1)[0]
    if "assignment_year" not in base:
        return None
    if "+2" in base:
        return 2
    if "+1" in base:
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        template = db.session.get(FormTemplate, 22)
        if template is None or not template.published_version_id:
            raise SystemExit("refusing: template 22 has no published version")
        items = (
            FormItem.query.filter(
                FormItem.version_id == template.published_version_id,
                FormItem.archived.is_(False),
                FormItem.item_type == "matrix",
            ).all()
        )
        labelled = [item for item in items if (item.label or "").strip().lower() == "funding requirements"]
        if len(labelled) != 1:
            raise SystemExit(f"refusing: expected one Funding Requirements matrix, found {len(labelled)}")
        item = labelled[0]
        config = item.config if isinstance(item.config, dict) else {}
        groups = (config.get("matrix_config") or {}).get("column_groups")
        if not isinstance(groups, dict) or not groups:
            raise SystemExit(f"refusing: item {item.id} has no column groups")

        updated = copy.deepcopy(groups)
        seen = {0: 0, 1: 0, 2: 0}
        for key, meta in updated.items():
            offset = _year_offset(key)
            if offset is None or not isinstance(meta, dict):
                print(f"leave {key}")
                continue
            header, body = YEAR_COLOURS[offset]
            meta["header_color"] = header if "::" not in key else body
            meta["apply_color_to_headers"] = True
            meta["apply_color_to_cells"] = True
            seen[offset] += 1
            print(f"{key}: {meta['header_color']}")
        missing = [offset for offset, count in seen.items() if count < 2]
        if missing:
            raise SystemExit(f"refusing: year groups missing for offsets {missing} (need the year and its subgroup)")
        if not args.apply:
            print("DRY RUN: nothing written. Re-run with --apply.")
            return 0
        new_config = copy.deepcopy(config)
        new_config["matrix_config"]["column_groups"] = updated
        item.config = new_config
        flag_modified(item, "config")
        db.session.commit()
        print(f"APPLIED on item {item.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
