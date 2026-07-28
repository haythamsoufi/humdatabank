#!/usr/bin/env python
"""Backfill stable_key on existing form_item and form_section rows.

Run from Backoffice/:
    python scripts/backfill_stable_keys.py --dry-run
    python scripts/backfill_stable_keys.py

Three-pass algorithm:
  1. Indicator items: group by (template_id, indicator_bank_id)
  2. Lineage pairs: match by section/item order rank via based_on_version_id
  3. Remaining rows: assign fresh UUIDs
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

_BACKOFFICE_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKOFFICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKOFFICE_ROOT))

from app import create_app
from app.extensions import db
from app.models import FormItem, FormSection, FormTemplateVersion
from app.utils.stable_key import generate_stable_key


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


def backfill(*, dry_run: bool = True) -> List[TemplateCoverage]:
    coverages: Dict[int, TemplateCoverage] = {}
    assigned_item_ids: Set[int] = set()
    assigned_section_ids: Set[int] = set()

    # Pass 1: indicator items grouped by (template_id, indicator_bank_id)
    # Share one key across versions only when each version has at most one row for that bank id.
    indicator_groups: Dict[Tuple[int, int], List[FormItem]] = defaultdict(list)
    for item in FormItem.query.filter(FormItem.indicator_bank_id.isnot(None)).all():
        if item.stable_key:
            assigned_item_ids.add(item.id)
            continue
        indicator_groups[(item.template_id, item.indicator_bank_id)].append(item)

    for (template_id, _bank_id), items in indicator_groups.items():
        by_version: Dict[int, List[FormItem]] = defaultdict(list)
        for item in items:
            by_version[item.version_id].append(item)
        if any(len(version_items) > 1 for version_items in by_version.values()):
            continue
        cov = coverages.setdefault(template_id, TemplateCoverage(template_id=template_id))
        key = generate_stable_key()
        for item in items:
            item.stable_key = key
            assigned_item_ids.add(item.id)
            cov.matched_indicator += 1

    # Pass 2: lineage-based positional matching for sections and non-indicator items
    versions = FormTemplateVersion.query.filter(
        FormTemplateVersion.based_on_version_id.isnot(None)
    ).all()
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

        src_section_by_pos = {}
        for section in src_sections:
            if section.stable_key:
                src_section_by_pos[_section_position_key(section, src_sections_by_id)] = section

        for section in tgt_sections:
            if section.id in assigned_section_ids or section.stable_key:
                if section.stable_key:
                    assigned_section_ids.add(section.id)
                continue
            pos = _section_position_key(section, tgt_sections_by_id)
            src = src_section_by_pos.get(pos)
            if src and src.stable_key:
                section.stable_key = src.stable_key
                assigned_section_ids.add(section.id)
                cov.matched_positional += 1
            elif src and not src.stable_key:
                new_key = generate_stable_key()
                src.stable_key = new_key
                section.stable_key = new_key
                assigned_section_ids.add(section.id)
                assigned_section_ids.add(src.id)
                cov.matched_positional += 1

        src_items = FormItem.query.filter_by(
            template_id=template_id, version_id=source.id
        ).filter(FormItem.indicator_bank_id.is_(None)).all()
        tgt_items = FormItem.query.filter_by(
            template_id=template_id, version_id=version.id
        ).filter(FormItem.indicator_bank_id.is_(None)).all()
        src_items_by_pos = {}
        for item in src_items:
            if item.stable_key:
                src_items_by_pos[_item_position_key(item, src_sections_by_id)] = item

        for item in tgt_items:
            if item.id in assigned_item_ids or item.stable_key:
                if item.stable_key:
                    assigned_item_ids.add(item.id)
                continue
            pos = _item_position_key(item, tgt_sections_by_id)
            src_item = src_items_by_pos.get(pos)
            if src_item and src_item.stable_key:
                if src_item.stable_key != item.stable_key:
                    item.stable_key = src_item.stable_key
                    assigned_item_ids.add(item.id)
                    cov.matched_positional += 1
            elif src_item and not src_item.stable_key:
                new_key = item.stable_key or generate_stable_key()
                src_item.stable_key = new_key
                item.stable_key = new_key
                assigned_item_ids.add(item.id)
                assigned_item_ids.add(src_item.id)
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
