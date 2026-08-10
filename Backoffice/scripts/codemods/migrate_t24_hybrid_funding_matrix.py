#!/usr/bin/env python3
"""Migrate Template 24 funding matrices to the new 'hybrid' row mode.

Background
----------
Items 967, 968, 974  (row_mode="manual")  hold the HNS + IFRC Secretariat rows.
Items 970, 973, 975  (row_mode="list_library") hold the PNS (National Society) rows.

After this migration each *hns_ifrc* item becomes a single hybrid matrix that shows
HNS/IFRC Secretariat rows at the top and lets users search/add National Society rows
below.  The retired *pns* items are archived.

Data migration
--------------
For every (AES, pns_item) FormData row that has a disagg_data payload, the cell
keys are merged into the corresponding (AES, hns_ifrc_item) FormData record:
  - If a target record already exists its disagg_data is merged (target wins on conflicts).
  - If no target record exists the source record is re-pointed to the hns_ifrc item.
Any (AES, pns_item) records that were fully merged into an existing target are deleted.

Run from Backoffice/:
    python scripts/codemods/migrate_t24_hybrid_funding_matrix.py
    python scripts/codemods/migrate_t24_hybrid_funding_matrix.py --dry-run
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import os

# ---------------------------------------------------------------------------
# Bootstrap the Flask application context
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app import create_app
from app.models.form_items import FormItem
from app.models.forms import FormData
from app.extensions import db

# Pairs: (hns_ifrc_item_id, pns_item_id)
MERGE_PAIRS = [
    (967, 970),
    (968, 973),
    (974, 975),
]


def _get_item_or_abort(item_id: int) -> FormItem:
    item = FormItem.query.get(item_id)
    if item is None:
        print(f"  ERROR: FormItem {item_id} not found in the database — aborting.", file=sys.stderr)
        sys.exit(1)
    return item


def _matrix_config(item: FormItem) -> dict:
    return (item.config or {}).get('matrix_config') or {}


def migrate(dry_run: bool = False) -> None:
    label = "[DRY-RUN] " if dry_run else ""

    for hns_id, pns_id in MERGE_PAIRS:
        print(f"\n{'='*60}")
        print(f"{label}Merging item {pns_id} (PNS list_library) → item {hns_id} (HNS/IFRC hybrid)")
        print('='*60)

        hns_item = _get_item_or_abort(hns_id)
        pns_item = _get_item_or_abort(pns_id)

        hns_cfg = _matrix_config(hns_item)
        pns_cfg = _matrix_config(pns_item)

        # ── Validate source states ───────────────────────────────────────────
        if hns_cfg.get('row_mode') == 'hybrid':
            print(f"  SKIP: item {hns_id} is already in hybrid mode — skipping pair.")
            continue

        if hns_cfg.get('row_mode') != 'manual':
            print(f"  WARNING: item {hns_id} row_mode={hns_cfg.get('row_mode')!r} (expected 'manual'). Continuing anyway.")

        if pns_cfg.get('row_mode') != 'list_library':
            print(f"  WARNING: item {pns_id} row_mode={pns_cfg.get('row_mode')!r} (expected 'list_library'). Continuing anyway.")

        lookup_list_id = pns_cfg.get('lookup_list_id') or pns_item.lookup_list_id
        list_display_column = pns_cfg.get('list_display_column') or pns_item.list_display_column
        list_filters = pns_cfg.get('list_filters', [])
        allow_other = pns_cfg.get('allow_other', False)
        search_placeholder = pns_cfg.get('search_placeholder', '')

        if not lookup_list_id:
            print(f"  WARNING: item {pns_id} has no lookup_list_id — list library config will be empty.")

        print(f"  HNS static rows : {[r.get('text') if isinstance(r, dict) else r for r in hns_cfg.get('rows', [])]}")
        print(f"  PNS lookup list : {lookup_list_id!r}  display_col={list_display_column!r}")

        # ── Build the new hybrid config ──────────────────────────────────────
        new_cfg = copy.deepcopy(hns_cfg)
        new_cfg['row_mode'] = 'hybrid'
        new_cfg['lookup_list_id'] = lookup_list_id
        new_cfg['list_display_column'] = list_display_column
        if list_filters:
            new_cfg['list_filters'] = list_filters
        if allow_other:
            new_cfg['allow_other'] = allow_other
        if search_placeholder:
            new_cfg['search_placeholder'] = search_placeholder

        print(f"  New config row_mode=hybrid, lookup_list_id={lookup_list_id!r}")

        # ── Migrate FormData rows ────────────────────────────────────────────
        pns_data_rows = FormData.query.filter_by(form_item_id=pns_id).all()
        print(f"  Found {len(pns_data_rows)} FormData record(s) for item {pns_id}")

        merged_count = 0
        repointed_count = 0

        for pns_fd in pns_data_rows:
            aes_id = pns_fd.assignment_entity_status_id
            pub_id = pns_fd.public_submission_id

            # The pns disagg_data is the cell map we want to merge
            pns_payload = pns_fd.disagg_data or {}
            if not pns_payload:
                # Nothing to migrate — just re-point the record if we keep it
                if not dry_run:
                    pns_fd.form_item_id = hns_id
                repointed_count += 1
                continue

            # Find the matching hns record (same AES/public submission)
            if aes_id:
                target_fd = FormData.query.filter_by(
                    assignment_entity_status_id=aes_id,
                    form_item_id=hns_id,
                ).first()
            elif pub_id:
                target_fd = FormData.query.filter_by(
                    public_submission_id=pub_id,
                    form_item_id=hns_id,
                ).first()
            else:
                target_fd = None

            if target_fd is None:
                # No existing hns record — simply re-point this one
                print(f"    AES={aes_id}: no target record for item {hns_id} — re-pointing record {pns_fd.id}")
                if not dry_run:
                    pns_fd.form_item_id = hns_id
                repointed_count += 1
            else:
                # Merge pns_payload into target_fd.disagg_data
                target_payload = dict(target_fd.disagg_data or {})
                merged_payload = dict(pns_payload)
                merged_payload.update(target_payload)   # target wins on key conflicts
                cells_added = sum(1 for k in pns_payload if k not in target_payload)
                print(f"    AES={aes_id}: merging {len(pns_payload)} cell(s) into record {target_fd.id} "
                      f"({cells_added} new, {len(pns_payload)-cells_added} overlapping→kept target)")
                if not dry_run:
                    target_fd.disagg_data = merged_payload
                    db.session.delete(pns_fd)
                merged_count += 1

        print(f"  FormData: {merged_count} merged, {repointed_count} re-pointed")

        # ── Update item 967/968/974 config + ORM fields ──────────────────────
        if not dry_run:
            new_item_config = dict(hns_item.config or {})
            new_item_config['matrix_config'] = new_cfg
            hns_item.config = new_item_config

            hns_item.lookup_list_id = str(lookup_list_id) if lookup_list_id else None
            hns_item.list_display_column = list_display_column
            if list_filters:
                hns_item.list_filters_json = json.dumps(list_filters)

            # Archive the now-redundant PNS item
            pns_item.archived = True
            print(f"  Item {pns_id} archived.")

        else:
            print(f"  [DRY-RUN] Would update item {hns_id} config to hybrid + archive item {pns_id}.")

    # ── Commit ───────────────────────────────────────────────────────────────
    if not dry_run:
        print("\nCommitting changes…")
        db.session.commit()
        print("Done.")
    else:
        print("\n[DRY-RUN] No changes committed.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would change without writing to the database.')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        migrate(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
