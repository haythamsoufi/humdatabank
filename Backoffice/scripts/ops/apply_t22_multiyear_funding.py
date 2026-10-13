#!/usr/bin/env python
"""Add the +1 / +2 year groups and their lookup variables to template 22's funding matrix.

Leaves the assignment-year columns, their group, and the assignment-year variables
(``fr_sp1`` ... ``fr_efs``) exactly as they are. Adds or replaces only:

* columns whose code contains ``[[assignment_year]+1]`` or ``[[assignment_year]+2]``
* the matching ``year_[[assignment_year]+1]`` / ``+2`` column groups (and ``::fun_req``)
* variables ``fr_*_2`` (T24 item 968) and ``fr_*_3`` (T24 item 974)

Definitions come from ``docs/t22-funding-matrix.snapshot.json``. Run from Backoffice/:

    python scripts/ops/apply_t22_multiyear_funding.py --snapshot docs/t22-funding-matrix.snapshot.json
    python scripts/ops/apply_t22_multiyear_funding.py --snapshot ... --apply

Without ``--apply`` nothing is written. Saved form data is not touched.
"""
from __future__ import annotations

import argparse
import copy
import json
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
from app.models import FormItem, FormTemplate, FormTemplateVersion  # noqa: E402

TEMPLATE_ID = 22
LATER_YEAR_TOKENS = ("[[assignment_year]+1]", "[[assignment_year]+2]")
YEAR0_REQUIRED = ("SP1_[assignment_year]", "EFs_[assignment_year]", "fr_tot_[assignment_year]")
LATER_YEAR_VARIABLE_SUFFIXES = ("_2", "_3")


def _is_later_year(name: str) -> bool:
    return any(token in str(name or "") for token in LATER_YEAR_TOKENS)


def _funding_item(version_id: int) -> FormItem:
    items = (
        FormItem.query.filter(FormItem.version_id == version_id, FormItem.archived.is_(False))
        .filter(FormItem.item_type == "matrix")
        .all()
    )
    labelled = [item for item in items if (item.label or "").strip().lower() == "funding requirements"]
    if len(labelled) != 1:
        raise SystemExit(f"refusing: expected one 'Funding Requirements' matrix, found {len(labelled)}")
    return labelled[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--snapshot", required=True, help="Path to t22-funding-matrix.snapshot.json")
    parser.add_argument("--apply", action="store_true", help="Write the changes (default is a dry run)")
    args = parser.parse_args()

    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    snap_mc = snapshot["matrix_config"]
    snap_columns = [col for col in snap_mc["columns"] if _is_later_year(col.get("name"))]
    snap_groups = {key: val for key, val in snap_mc["column_groups"].items() if _is_later_year(key)}
    snap_variables = {
        key: val
        for key, val in snapshot["variables"].items()
        if key.startswith("fr_") and key.endswith(LATER_YEAR_VARIABLE_SUFFIXES)
    }
    if len(snap_columns) != 16 or len(snap_groups) != 4 or len(snap_variables) != 12:
        raise SystemExit(
            f"refusing: snapshot has {len(snap_columns)} later-year columns, "
            f"{len(snap_groups)} groups, {len(snap_variables)} variables (expected 16, 4, 12)"
        )

    app = create_app()
    with app.app_context():
        template = db.session.get(FormTemplate, TEMPLATE_ID)
        if template is None or not template.published_version_id:
            raise SystemExit("refusing: template 22 has no published version")
        version = db.session.get(FormTemplateVersion, template.published_version_id)
        item = _funding_item(version.id)
        config = item.config if isinstance(item.config, dict) else {}
        mc = config.get("matrix_config")
        if not isinstance(mc, dict):
            raise SystemExit(f"refusing: item {item.id} has no matrix_config")

        live_columns = list(mc.get("columns") or [])
        live_names = [col.get("name") for col in live_columns if isinstance(col, dict)]
        missing_year0 = [name for name in YEAR0_REQUIRED if name not in live_names]
        if missing_year0:
            raise SystemExit(f"refusing: assignment-year columns not in place yet: {missing_year0}")

        print(f"template {template.id} '{template.name}' published version {version.id}")
        print(f"funding matrix item {item.id} ({len(live_columns)} columns now)")
        print("BACKUP_BEGIN")
        print(json.dumps({"item_id": item.id, "matrix_config": mc, "variables": version.variables}, ensure_ascii=False, default=str))
        print("BACKUP_END")

        kept_columns = [col for col in live_columns if not _is_later_year(col.get("name"))]
        replaced_columns = [col.get("name") for col in live_columns if _is_later_year(col.get("name"))]
        new_columns = kept_columns + copy.deepcopy(snap_columns)

        live_groups = dict(mc.get("column_groups") or {})
        replaced_groups = sorted(key for key in live_groups if _is_later_year(key))
        new_groups = {key: val for key, val in live_groups.items() if not _is_later_year(key)}
        new_groups.update(copy.deepcopy(snap_groups))

        live_variables = dict(version.variables or {})
        replaced_variables = sorted(key for key in snap_variables if key in live_variables)
        new_variables = copy.deepcopy(live_variables)
        new_variables.update(copy.deepcopy(snap_variables))

        print(f"keep {len(kept_columns)} assignment-year columns: {[c.get('name') for c in kept_columns]}")
        print(f"later-year columns: replace {replaced_columns or 'none'}, write {len(snap_columns)}")
        print(f"later-year groups: replace {replaced_groups or 'none'}, write {sorted(snap_groups)}")
        print(f"variables: replace {replaced_variables or 'none'}, write {sorted(snap_variables)}")
        for key in sorted(snap_variables):
            var = snap_variables[key]
            print(f"  {key}: T{var.get('source_template_id')} item {var.get('source_form_item_id')} column {var.get('matrix_column_name')}")
        print(f"result: {len(new_columns)} columns, {len(new_groups)} groups, {len(new_variables)} variables")

        if not args.apply:
            print("DRY RUN: nothing written. Re-run with --apply.")
            return 0

        new_config = copy.deepcopy(config)
        new_config["matrix_config"]["columns"] = new_columns
        new_config["matrix_config"]["column_groups"] = new_groups
        item.config = new_config
        flag_modified(item, "config")
        version.variables = new_variables
        flag_modified(version, "variables")
        db.session.commit()

        item = db.session.get(FormItem, item.id)
        version = db.session.get(FormTemplateVersion, version.id)
        names = [col["name"] for col in item.config["matrix_config"]["columns"]]
        print(f"APPLIED: {len(names)} columns, {len(version.variables)} variables")
        print(f"  year0 untouched: {[n for n in names if not _is_later_year(n)]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
