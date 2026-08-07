#!/usr/bin/env python
"""Prune stale matrix cell keys left over from form-builder column renames.

Matrix ``disagg_data`` cells are stored as ``{row}_{column_name}``. When a
matrix column's internal ``name`` is renamed in the form builder (e.g. item
1403's funding column went from ``NS 2025 Total Funding`` to ``ns_fun``),
previously saved rows keep the *old* cell key forever: it no longer matches
any row/column pairing, so it's invisible in the UI and excluded from totals,
but it lingers in the JSON blob (see form_data.id=286867 for a concrete case
found in Jan-Jun 2026 country reporting data).

New saves are already protected — see ``app.utils.api_serialization.
prune_stale_matrix_cell_keys``, wired into ``FormDataService._process_matrix_data``
and ``RepeatGroupProcessorMixin._store_repeat_data_entry``. This script is the
one-off cleanup for rows written *before* that fix shipped.

Run from Backoffice/ against whichever environment DATABASE_URL points at:
    python scripts/ops/prune_stale_matrix_cell_keys.py --dry-run
    python scripts/ops/prune_stale_matrix_cell_keys.py --form-item-id 1403 --dry-run
    python scripts/ops/prune_stale_matrix_cell_keys.py --form-item-id 1403 --force

Options:
    --form-item-id ID   Only process this FormItem id (repeatable). Default: all matrix items.
    --table {form_data,repeat_group_data,all}   Which table(s) to scan. Default: all.
    --dry-run           Preview affected rows and the keys that would be dropped; no writes.
    --force             Skip the interactive confirmation prompt (for automated/CI use).

Exit code 0 on success (including "nothing to prune"), 1 on error or user abort.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_scripts = Path(__file__).resolve().parents[1]
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))
from _bootstrap import setup_cli_paths

setup_cli_paths(__file__)

logger = logging.getLogger(__name__)

DISAGG_FIELD_NAMES = ('disagg_data', 'prefilled_disagg_data', 'imputed_disagg_data')


def _iter_targets(model, form_item_ids):
    """Yield (row, disagg_field_name) for every dict-valued disagg JSON column on matching rows."""
    query = model.query.filter(model.form_item_id.in_(form_item_ids))
    for row in query.yield_per(200):
        for field_name in DISAGG_FIELD_NAMES:
            if isinstance(getattr(row, field_name, None), dict):
                yield row, field_name


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '--form-item-id', type=int, action='append', dest='form_item_ids',
        help='Only process this FormItem id (repeatable). Default: all matrix items.',
    )
    parser.add_argument(
        '--table', choices=['form_data', 'repeat_group_data', 'all'], default='all',
        help='Which table(s) to scan. Default: all.',
    )
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without writing.')
    parser.add_argument('--force', action='store_true', help='Skip confirmation prompt.')
    args = parser.parse_args()

    from app import create_app
    from app.extensions import db
    from app.models import FormData, FormItem, RepeatGroupData
    from app.utils.api_serialization import prune_stale_matrix_cell_keys

    app = create_app()
    with app.app_context():
        item_query = FormItem.query.filter(FormItem.item_type == 'matrix')
        if args.form_item_ids:
            item_query = item_query.filter(FormItem.id.in_(args.form_item_ids))
        matrix_configs = {
            item.id: ((item.config or {}).get('matrix_config') or {})
            for item in item_query.all()
        }

        if not matrix_configs:
            logger.info("No matching matrix FormItem rows found.")
            return 0

        logger.info("Scanning %d matrix FormItem(s): %s", len(matrix_configs), sorted(matrix_configs))

        models = []
        if args.table in ('form_data', 'all'):
            models.append(FormData)
        if args.table in ('repeat_group_data', 'all'):
            models.append(RepeatGroupData)

        planned_updates = []  # (table_name, row, field_name, pruned_value, dropped_keys)
        for model in models:
            for row, field_name in _iter_targets(model, list(matrix_configs.keys())):
                original = getattr(row, field_name)
                matrix_config = matrix_configs.get(row.form_item_id, {})
                pruned = prune_stale_matrix_cell_keys(original, matrix_config)
                if pruned.keys() != original.keys():
                    dropped_keys = sorted(set(original) - set(pruned))
                    planned_updates.append((model.__tablename__, row, field_name, pruned, dropped_keys))

        if not planned_updates:
            logger.info("No stale matrix cell keys found. Nothing to do.")
            return 0

        total_keys_dropped = sum(len(dropped) for *_rest, dropped in planned_updates)
        logger.info(
            "Found %d row/field pair(s) with %d stale key(s) total:",
            len(planned_updates), total_keys_dropped,
        )
        for table_name, row, field_name, _pruned, dropped_keys in planned_updates:
            logger.info(
                "  [%s] id=%s form_item_id=%s field=%s dropped=%s",
                table_name, row.id, row.form_item_id, field_name, dropped_keys,
            )

        if args.dry_run:
            logger.info("[DRY RUN] No changes written. Re-run without --dry-run to apply.")
            return 0

        if not args.force:
            logger.warning(
                "This will overwrite %d field(s) across %d row(s).",
                len(planned_updates), len({(t, r.id) for t, r, *_ in planned_updates}),
            )
            confirmation = input("Type 'PRUNE' to confirm: ")
            if confirmation != 'PRUNE':
                logger.info("Aborted.")
                return 1

        for _table_name, row, field_name, pruned, _dropped_keys in planned_updates:
            setattr(row, field_name, pruned)
            db.session.add(row)
        db.session.commit()

        logger.info(
            "Successfully pruned %d stale key(s) across %d row(s).",
            total_keys_dropped, len({(t, r.id) for t, r, *_ in planned_updates}),
        )
        return 0


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(main())
