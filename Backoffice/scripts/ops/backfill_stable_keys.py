#!/usr/bin/env python
"""Backfill stable_key on existing form_item and form_section rows.

Run from Backoffice/:
    python scripts/ops/backfill_stable_keys.py --dry-run
    python scripts/ops/backfill_stable_keys.py

Algorithm:
  1. Template 22 staff/funding matrices: share the canonical key where still null
  2. Indicator items: one key per (template_id, indicator_bank_id) when unambiguous
  3. Lineage pairs: match by section/item order rank via based_on_version_id
     and share one key (parents first). Do not overwrite keys that already differ.
  4. Remaining rows: assign fresh UUIDs
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Tuple

_BACKOFFICE_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKOFFICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKOFFICE_ROOT))

from app import create_app
from app.extensions import db
from app.models import FormItem, FormSection, FormTemplateVersion
from app.utils.stable_key import (
    T22_FUNDING_MATRIX_STABLE_KEY,
    T22_STAFF_MATRIX_COLUMN,
    T22_STAFF_MATRIX_STABLE_KEY,
    generate_stable_key,
)
from app.utils.stable_key_backfill import (
    align_stable_key,
    fill_null_stable_keys,
    index_by_position,
    lineage_order,
    shared_key_for_group,
)


@dataclass
class TemplateCoverage:
    template_id: int
    matched_indicator: int = 0
    matched_positional: int = 0
    unmatched: int = 0
    warnings: List[str] = field(default_factory=list)


def _section_order_rank(section_id: int, sections_by_id: Dict[int, FormSection]) -> Tuple:
    """Build a tuple of ancestor orders for positional matching."""
    orders = []
    current = sections_by_id.get(section_id)
    visited: Set[int] = set()
    while current and current.id not in visited:
        visited.add(current.id)
        orders.append(current.order)
        if not current.parent_section_id:
            break
        current = sections_by_id.get(current.parent_section_id)
    return tuple(reversed(orders))


def _item_position_key(item: FormItem, sections_by_id: Dict[int, FormSection]) -> Tuple:
    return (_section_order_rank(item.section_id, sections_by_id), item.order, item.item_type)


def _section_position_key(section: FormSection, sections_by_id: Dict[int, FormSection]) -> Tuple:
    return (_section_order_rank(section.id, sections_by_id), section.order, section.section_type)


def _matrix_column_names(item: FormItem) -> Set[str]:
    config = item.config if isinstance(item.config, dict) else {}
    matrix = config.get("matrix_config") if isinstance(config.get("matrix_config"), dict) else config
    names: Set[str] = set()
    if not isinstance(matrix, dict):
        return names
    for col in matrix.get("columns") or []:
        name = col.get("name") if isinstance(col, dict) else col
        if name:
            names.add(str(name).strip().lower())
    return names


def _assign_canonical_t22_keys(coverages: Dict[int, TemplateCoverage]) -> None:
    """Share the canonical template 22 staff/funding keys across versions.

    Rows that already have a key are left as they are. Null siblings copy that
    key when the group agrees. An all-null group receives the canonical key.
    """
    items = FormItem.query.filter(
        FormItem.template_id == 22,
        FormItem.item_type == "matrix",
        FormItem.archived == False,  # noqa: E712
    ).all()
    buckets: Dict[str, List[FormItem]] = {"staff": [], "funding": []}
    for item in items:
        names = _matrix_column_names(item)
        if T22_STAFF_MATRIX_COLUMN in names:
            buckets["staff"].append(item)
        elif {"sp1", "efs"} <= names:
            buckets["funding"].append(item)
    canonical = {
        "staff": T22_STAFF_MATRIX_STABLE_KEY,
        "funding": T22_FUNDING_MATRIX_STABLE_KEY,
    }
    for kind, rows in buckets.items():
        by_version: Dict[int, List[FormItem]] = defaultdict(list)
        for item in rows:
            by_version[item.version_id].append(item)
        updated = fill_null_stable_keys(by_version, canonical[kind], generate_stable_key)
        if updated:
            cov = coverages.setdefault(22, TemplateCoverage(template_id=22))
            cov.matched_positional += updated


def backfill(*, dry_run: bool = True) -> List[TemplateCoverage]:
    coverages: Dict[int, TemplateCoverage] = {}
    assigned_item_ids: Set[int] = set()
    assigned_section_ids: Set[int] = set()

    _assign_canonical_t22_keys(coverages)

    # Pass 1: indicator items grouped by (template_id, indicator_bank_id).
    # Share one key across versions only when each version has at most one row
    # for that bank id, reusing a key the group already has.
    indicator_groups: Dict[Tuple[int, int], List[FormItem]] = defaultdict(list)
    for item in FormItem.query.filter(FormItem.indicator_bank_id.isnot(None)).all():
        indicator_groups[(item.template_id, item.indicator_bank_id)].append(item)

    for (template_id, _bank_id), items in indicator_groups.items():
        by_version: Dict[int, List[FormItem]] = defaultdict(list)
        for item in items:
            by_version[item.version_id].append(item)
        if any(len(version_items) > 1 for version_items in by_version.values()):
            for item in items:
                if item.stable_key:
                    assigned_item_ids.add(item.id)
            continue
        key = shared_key_for_group((item.stable_key for item in items), generate_stable_key)
        if not key:
            continue
        cov = coverages.setdefault(template_id, TemplateCoverage(template_id=template_id))
        for item in items:
            if not item.stable_key:
                item.stable_key = key
                cov.matched_indicator += 1
            assigned_item_ids.add(item.id)

    # Pass 2: lineage-based positional matching for sections and non-indicator items.
    # Parents run first so a key minted on the root is copied onto later versions.
    versions = lineage_order(
        FormTemplateVersion.query.filter(
            FormTemplateVersion.based_on_version_id.isnot(None)
        ).all()
    )
    for version in versions:
        source = FormTemplateVersion.query.get(version.based_on_version_id)
        if not source:
            continue
        template_id = version.template_id
        cov = coverages.setdefault(template_id, TemplateCoverage(template_id=template_id))

        src_sections = FormSection.query.filter_by(
            template_id=template_id, version_id=source.id
        ).all()
        tgt_sections = FormSection.query.filter_by(
            template_id=template_id, version_id=version.id
        ).all()
        src_sections_by_id = {s.id: s for s in src_sections}
        tgt_sections_by_id = {s.id: s for s in tgt_sections}

        src_section_by_pos = index_by_position(
            src_sections,
            lambda section: _section_position_key(section, src_sections_by_id),
        )

        for section in tgt_sections:
            pos = _section_position_key(section, tgt_sections_by_id)
            src = src_section_by_pos.get(pos)
            if not src:
                if section.stable_key:
                    assigned_section_ids.add(section.id)
                continue
            if section.stable_key and src.stable_key:
                assigned_section_ids.add(section.id)
                assigned_section_ids.add(src.id)
                continue
            action = align_stable_key(src, section, generate_stable_key)
            assigned_section_ids.add(section.id)
            assigned_section_ids.add(src.id)
            if action != "unchanged":
                cov.matched_positional += 1

        src_items = FormItem.query.filter_by(
            template_id=template_id, version_id=source.id
        ).filter(FormItem.indicator_bank_id.is_(None)).all()
        tgt_items = FormItem.query.filter_by(
            template_id=template_id, version_id=version.id
        ).filter(FormItem.indicator_bank_id.is_(None)).all()
        src_items_by_pos = index_by_position(
            src_items,
            lambda item: _item_position_key(item, src_sections_by_id),
        )

        for item in tgt_items:
            pos = _item_position_key(item, tgt_sections_by_id)
            src_item = src_items_by_pos.get(pos)
            if not src_item:
                if item.stable_key:
                    assigned_item_ids.add(item.id)
                continue
            if item.stable_key and src_item.stable_key:
                assigned_item_ids.add(item.id)
                assigned_item_ids.add(src_item.id)
                continue
            action = align_stable_key(src_item, item, generate_stable_key)
            assigned_item_ids.add(item.id)
            assigned_item_ids.add(src_item.id)
            if action != "unchanged":
                cov.matched_positional += 1

    # Pass 3: assign fresh keys to anything still missing
    with db.session.no_autoflush:
        for item in FormItem.query.filter(FormItem.stable_key.is_(None)).all():
            item.stable_key = generate_stable_key()
            cov = coverages.setdefault(item.template_id, TemplateCoverage(template_id=item.template_id))
            cov.unmatched += 1

        for section in FormSection.query.filter(FormSection.stable_key.is_(None)).all():
            section.stable_key = generate_stable_key()
            cov = coverages.setdefault(section.template_id, TemplateCoverage(template_id=section.template_id))
            cov.unmatched += 1

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()

    return list(coverages.values())


def main() -> int:
    parser = argparse.ArgumentParser(description='Backfill stable_key on form structure rows')
    parser.add_argument('--dry-run', action='store_true', help='Report coverage without committing')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        coverages = backfill(dry_run=args.dry_run)
        mode = 'DRY RUN' if args.dry_run else 'COMMITTED'
        print(f"Backfill stable_key ({mode})")
        print("template_id\tmatched_indicator\tmatched_positional\tunmatched")
        for cov in sorted(coverages, key=lambda c: c.template_id):
            print(
                f"{cov.template_id}\t{cov.matched_indicator}\t"
                f"{cov.matched_positional}\t{cov.unmatched}"
            )
        if not coverages:
            print("(no rows needed backfill)")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
