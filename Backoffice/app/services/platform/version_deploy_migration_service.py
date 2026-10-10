"""Deploy-time FK remapping for template version submission data continuity."""

from __future__ import annotations

import copy
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from flask import current_app
from sqlalchemy import func

from app import db
from app.models import (
    DynamicIndicatorData,
    DynamicSectionContext,
    FormData,
    FormItem,
    FormSection,
    FormTemplateVersion,
    RepeatGroupData,
    RepeatGroupInstance,
)
from app.models.assignments import AssignmentPageStatus
from app.models.documents import SubmittedDocument
from app.utils.stable_key import generate_stable_key


class VersionDeployMigrationError(Exception):
    """Raised when deploy-time FK migration cannot proceed safely."""


class VersionDeployMigrationService:
    """Bulk-remap submission FKs from an archived published version to a new one."""

    @classmethod
    def estimate_migration_counts(
        cls,
        old_version_id: int,
        new_version_id: int,
        template_id: int,
    ) -> Dict[str, Any]:
        """Return read-only counts of rows that would be remapped on deploy."""
        item_map, section_map = cls._build_key_maps(old_version_id, new_version_id, template_id)
        old_item_ids = list(item_map.keys())
        old_section_ids = list(section_map.keys())
        page_map = cls._build_page_map(section_map)

        counts = {
            'form_data': cls._count_form_data(old_item_ids),
            'repeat_group_data': cls._count_repeat_group_data(old_item_ids),
            'submitted_document': cls._count_submitted_documents(old_item_ids),
            'repeat_group_instance': cls._count_repeat_instances(old_section_ids),
            'dynamic_indicator_data': cls._count_dynamic_indicators(old_section_ids),
            'dynamic_section_context': cls._count_dynamic_contexts(old_section_ids),
            'assignment_page_status': cls._count_page_statuses(list(page_map.keys())),
        }
        total = sum(count for label, count in counts.items() if label != 'assignment_page_status')
        return {
            'remappable_rows': total,
            'per_table': counts,
            'matched_items': len(item_map),
            'matched_sections': len(section_map),
            'orphaned_items': cls._count_orphan_items(old_version_id, new_version_id, template_id),
            'orphaned_sections': cls._count_orphan_sections(old_version_id, new_version_id, template_id),
        }

    @classmethod
    def build_field_comparison(
        cls,
        old_version_id: int,
        new_version_id: int,
        template_id: int,
    ) -> List[Dict[str, Any]]:
        """Read-only draft vs published field mapping for the review UI."""
        if old_version_id == new_version_id:
            return []

        old_sections = FormSection.query.filter_by(
            template_id=template_id, version_id=old_version_id
        ).all()
        new_sections = FormSection.query.filter_by(
            template_id=template_id, version_id=new_version_id
        ).all()
        old_sections_by_id = {section.id: section for section in old_sections}
        new_sections_by_id = {section.id: section for section in new_sections}

        old_items = FormItem.query.filter_by(
            template_id=template_id, version_id=old_version_id
        ).order_by(FormItem.order, FormItem.id).all()
        new_items = FormItem.query.filter_by(
            template_id=template_id, version_id=new_version_id
        ).order_by(FormItem.order, FormItem.id).all()

        section_matches, item_matches = cls._compute_positional_matches(
            old_version_id, new_version_id, template_id
        )

        pub_items_by_key = {
            item.stable_key: item for item in old_items if item.stable_key
        }
        exact_pub_item_ids: Set[int] = {
            pub_items_by_key[item.stable_key].id
            for item in new_items
            if item.stable_key and item.stable_key in pub_items_by_key
        }
        matched_pub_item_ids: Set[int] = set()
        rows: List[Dict[str, Any]] = []

        for draft_item in new_items:
            published_item: Optional[FormItem] = None
            confidence = 'new'
            if draft_item.stable_key and draft_item.stable_key in pub_items_by_key:
                published_item = pub_items_by_key[draft_item.stable_key]
                confidence = 'exact'
            elif (
                draft_item.id in item_matches
                and item_matches[draft_item.id].id not in exact_pub_item_ids
            ):
                published_item = item_matches[draft_item.id]
                if (
                    draft_item.stable_key
                    and published_item.stable_key
                    and draft_item.stable_key == published_item.stable_key
                ):
                    confidence = 'exact'
                else:
                    confidence = 'suggested'
            if published_item:
                matched_pub_item_ids.add(published_item.id)
            data_rows = cls._count_form_data([published_item.id]) if published_item else 0
            rows.append({
                'entity_type': 'item',
                'draft_item': cls._serialize_item_for_mapping(draft_item, new_sections_by_id),
                'published_item': (
                    cls._serialize_item_for_mapping(published_item, old_sections_by_id)
                    if published_item else None
                ),
                'confidence': confidence,
                'data_rows': data_rows,
            })

        for pub_item in old_items:
            if pub_item.id in matched_pub_item_ids:
                continue
            rows.append({
                'entity_type': 'item',
                'draft_item': None,
                'published_item': cls._serialize_item_for_mapping(pub_item, old_sections_by_id),
                'confidence': 'orphaned',
                'data_rows': cls._count_form_data([pub_item.id]),
            })

        pub_sections_by_key = {
            section.stable_key: section for section in old_sections if section.stable_key
        }
        exact_pub_section_ids: Set[int] = {
            pub_sections_by_key[section.stable_key].id
            for section in new_sections
            if section.stable_key and section.stable_key in pub_sections_by_key
        }
        matched_pub_section_ids: Set[int] = set()
        for draft_section in new_sections:
            published_section: Optional[FormSection] = None
            confidence = 'new'
            if draft_section.stable_key and draft_section.stable_key in pub_sections_by_key:
                published_section = pub_sections_by_key[draft_section.stable_key]
                confidence = 'exact'
            elif (
                draft_section.id in section_matches
                and section_matches[draft_section.id].id not in exact_pub_section_ids
            ):
                published_section = section_matches[draft_section.id]
                if (
                    draft_section.stable_key
                    and published_section.stable_key
                    and draft_section.stable_key == published_section.stable_key
                ):
                    confidence = 'exact'
                else:
                    confidence = 'suggested'
            if published_section:
                matched_pub_section_ids.add(published_section.id)
            rows.append({
                'entity_type': 'section',
                'draft_item': cls._serialize_section_for_mapping(draft_section),
                'published_item': (
                    cls._serialize_section_for_mapping(published_section)
                    if published_section else None
                ),
                'confidence': confidence,
                'data_rows': 0,
            })

        for pub_section in old_sections:
            if pub_section.id in matched_pub_section_ids:
                continue
            rows.append({
                'entity_type': 'section',
                'draft_item': None,
                'published_item': cls._serialize_section_for_mapping(pub_section),
                'confidence': 'orphaned',
                'data_rows': 0,
            })

        return rows

    @classmethod
    def count_field_mapping_summary(
        cls,
        old_version_id: int,
        new_version_id: int,
        template_id: int,
    ) -> Dict[str, int]:
        """Counts for deploy preflight / mapping review banners."""
        rows = cls.build_field_comparison(old_version_id, new_version_id, template_id)
        item_rows = [row for row in rows if row.get('entity_type') == 'item']
        return {
            'suggested_items': sum(1 for row in item_rows if row.get('confidence') == 'suggested'),
            'unlinked_items': sum(1 for row in item_rows if row.get('confidence') == 'new'),
            'orphaned_items_with_data': sum(
                1 for row in item_rows
                if row.get('confidence') == 'orphaned' and (row.get('data_rows') or 0) > 0
            ),
        }

    @classmethod
    def migrate_submission_fks(
        cls,
        old_version_id: int,
        new_version_id: int,
        template_id: int,
        *,
        restore_archived: bool = False,
    ) -> Dict[str, Any]:
        """Remap submission rows from old_version structure to new_version via stable_key.

        ``restore_archived`` is set when ``new_version_id`` was published before (rollback):
        rows that an earlier deploy archived as orphans are made visible again.
        """
        if old_version_id == new_version_id:
            return cls._empty_summary()

        cls._assert_unique_stable_keys(new_version_id, template_id)

        aligned = cls._align_stable_keys_for_deploy(old_version_id, new_version_id, template_id)
        current_app.logger.info(
            "VERSION_MIGRATION: aligned stable_key rows sections=%s items=%s indicators=%s",
            aligned.get('sections', 0),
            aligned.get('items', 0),
            aligned.get('indicators', 0),
        )

        item_map, section_map = cls._build_key_maps(old_version_id, new_version_id, template_id)
        page_map = cls._build_page_map(section_map)

        if section_map or item_map:
            cls._assert_no_submission_rows_on_new_sections(list(section_map.values()))

        summary: Dict[str, Any] = {
            'matched_items': len(item_map),
            'matched_sections': len(section_map),
            'per_table': {},
        }

        if section_map:
            section_updates = [
                (RepeatGroupInstance, 'section_id', 'repeat_group_instance'),
                (DynamicIndicatorData, 'section_id', 'dynamic_indicator_data'),
                (DynamicSectionContext, 'section_id', 'dynamic_section_context'),
            ]
            for model, column_name, label in section_updates:
                updated = cls._bulk_remap_fk(model, column_name, section_map)
                summary['per_table'][label] = updated
                current_app.logger.info(
                    "VERSION_MIGRATION: %s section_id rows updated=%s", label, updated
                )

        if item_map:
            item_updates = [
                (FormData, 'form_item_id', 'form_data'),
                (RepeatGroupData, 'form_item_id', 'repeat_group_data'),
                (SubmittedDocument, 'form_item_id', 'submitted_document'),
            ]
            for model, column_name, label in item_updates:
                updated = cls._bulk_remap_fk(model, column_name, item_map)
                summary['per_table'][label] = updated
                current_app.logger.info(
                    "VERSION_MIGRATION: %s form_item_id rows updated=%s", label, updated
                )

        if page_map:
            page_status_rows, page_conflicts = cls._remap_page_statuses(page_map)
            summary['per_table']['assignment_page_status'] = page_status_rows
            summary['page_status_conflicts'] = page_conflicts

        summary['variable_references_remapped'] = cls._remap_variable_item_references(item_map)

        restored_items = restored_sections = 0
        if restore_archived:
            restored_items, restored_sections = cls._restore_archived_rows(
                old_version_id, new_version_id, template_id
            )
        summary['restored_items'] = restored_items
        summary['restored_sections'] = restored_sections

        orphaned_items = cls._archive_orphaned_items(old_version_id, new_version_id, template_id)
        orphaned_sections = cls._archive_orphaned_sections(old_version_id, new_version_id, template_id)
        summary['orphaned_items'] = orphaned_items
        summary['orphaned_sections'] = orphaned_sections
        summary['remapped_rows'] = sum(
            count for label, count in summary['per_table'].items()
            if label != 'assignment_page_status'
        )
        summary['stable_key_alignment'] = aligned

        if summary['remapped_rows'] == 0:
            pending = cls._count_submission_rows_on_old_structure(old_version_id, template_id)
            if pending > 0 and not item_map and not section_map:
                raise VersionDeployMigrationError(
                    f"Cannot deploy: {pending} submission row(s) exist on the previous version "
                    f"but no fields could be matched to the new version by stable_key. "
                    f"Run: python scripts/ops/backfill_stable_keys.py --dry-run then commit, "
                    f"or python scripts/archive/repair_version_deploy_migration.py --template-id {template_id} "
                    f"--from-version {old_version_id} --to-version {new_version_id}"
                )

        current_app.logger.info(
            "VERSION_MIGRATION: complete matched_items=%s matched_sections=%s remapped_rows=%s orphaned_items=%s",
            summary['matched_items'],
            summary['matched_sections'],
            summary['remapped_rows'],
            summary['orphaned_items'],
        )
        return summary

    @classmethod
    def _empty_summary(cls) -> Dict[str, Any]:
        return {
            'matched_items': 0,
            'matched_sections': 0,
            'orphaned_items': 0,
            'orphaned_sections': 0,
            'remapped_rows': 0,
            'per_table': {},
        }

    @classmethod
    def _build_key_maps(
        cls,
        old_version_id: int,
        new_version_id: int,
        template_id: int,
    ) -> Tuple[Dict[int, int], Dict[int, int]]:
        old_items = FormItem.query.filter_by(
            template_id=template_id, version_id=old_version_id
        ).filter(FormItem.stable_key.isnot(None)).all()
        new_items_by_key = {
            item.stable_key: item.id
            for item in FormItem.query.filter_by(
                template_id=template_id, version_id=new_version_id
            ).filter(FormItem.stable_key.isnot(None)).all()
            if item.stable_key
        }
        item_map = {
            old.id: new_items_by_key[old.stable_key]
            for old in old_items
            if old.stable_key in new_items_by_key
        }

        old_sections = FormSection.query.filter_by(
            template_id=template_id, version_id=old_version_id
        ).filter(FormSection.stable_key.isnot(None)).all()
        new_sections_by_key = {
            section.stable_key: section.id
            for section in FormSection.query.filter_by(
                template_id=template_id, version_id=new_version_id
            ).filter(FormSection.stable_key.isnot(None)).all()
            if section.stable_key
        }
        section_map = {
            old.id: new_sections_by_key[old.stable_key]
            for old in old_sections
            if old.stable_key in new_sections_by_key
        }
        return item_map, section_map

    @classmethod
    def _serialize_item_for_mapping(
        cls,
        item: FormItem,
        sections_by_id: Dict[int, FormSection],
    ) -> Dict[str, Any]:
        section = sections_by_id.get(item.section_id)
        return {
            'id': item.id,
            'label': item.label,
            'item_type': item.item_type,
            'stable_key': item.stable_key,
            'section_name': section.name if section else '',
            'order': item.order,
            'indicator_bank_id': item.indicator_bank_id,
        }

    @classmethod
    def _serialize_section_for_mapping(cls, section: FormSection) -> Dict[str, Any]:
        return {
            'id': section.id,
            'name': section.name,
            'section_type': section.section_type,
            'stable_key': section.stable_key,
            'order': section.order,
        }

    @classmethod
    def _compute_positional_matches(
        cls,
        old_version_id: int,
        new_version_id: int,
        template_id: int,
    ) -> Tuple[Dict[int, FormSection], Dict[int, FormItem]]:
        """Return draft row id -> published row for positional alignment (read-only).

        Positions shared by more than one row on either side are ambiguous and never
        matched: guessing would cross-wire submission data between unrelated fields.
        """
        old_sections = FormSection.query.filter_by(
            template_id=template_id, version_id=old_version_id
        ).all()
        new_sections = FormSection.query.filter_by(
            template_id=template_id, version_id=new_version_id
        ).all()
        old_sections_by_id = {section.id: section for section in old_sections}
        new_sections_by_id = {section.id: section for section in new_sections}

        section_matches: Dict[int, FormSection] = {}
        for new_id, old_row in cls._unique_position_pairs(
            old_sections,
            new_sections,
            lambda row: cls._section_position_key(row, old_sections_by_id),
            lambda row: cls._section_position_key(row, new_sections_by_id),
        ).items():
            section_matches[new_id] = old_row

        old_items = FormItem.query.filter_by(
            template_id=template_id, version_id=old_version_id
        ).all()
        new_items = FormItem.query.filter_by(
            template_id=template_id, version_id=new_version_id
        ).all()

        old_indicators_by_bank: Dict[int, List[FormItem]] = {}
        new_indicators_by_bank: Dict[int, List[FormItem]] = {}
        for item in old_items:
            if item.indicator_bank_id:
                old_indicators_by_bank.setdefault(item.indicator_bank_id, []).append(item)
        for item in new_items:
            if item.indicator_bank_id:
                new_indicators_by_bank.setdefault(item.indicator_bank_id, []).append(item)

        item_matches: Dict[int, FormItem] = {}
        for bank_id, old_group in old_indicators_by_bank.items():
            new_group = new_indicators_by_bank.get(bank_id) or []
            if not new_group:
                continue
            old_group = sorted(old_group, key=lambda row: (row.order, row.id))
            new_group = sorted(new_group, key=lambda row: (row.order, row.id))
            for old_item, new_item in zip(old_group, new_group):
                item_matches[new_item.id] = old_item

        item_matches.update(
            cls._unique_position_pairs(
                [item for item in old_items if not item.indicator_bank_id],
                [item for item in new_items if not item.indicator_bank_id],
                lambda row: cls._item_position_key(row, old_sections_by_id),
                lambda row: cls._item_position_key(row, new_sections_by_id),
            )
        )

        return section_matches, item_matches

    @staticmethod
    def _unique_position_pairs(old_rows, new_rows, old_key_fn, new_key_fn) -> Dict[int, Any]:
        """Pair rows whose position key is held by exactly one row on each side."""
        old_by_pos: Dict[Tuple, List[Any]] = defaultdict(list)
        new_by_pos: Dict[Tuple, List[Any]] = defaultdict(list)
        for row in old_rows:
            old_by_pos[old_key_fn(row)].append(row)
        for row in new_rows:
            new_by_pos[new_key_fn(row)].append(row)
        pairs: Dict[int, Any] = {}
        for pos, new_group in new_by_pos.items():
            old_group = old_by_pos.get(pos)
            if old_group and len(old_group) == 1 and len(new_group) == 1:
                pairs[new_group[0].id] = old_group[0]
        return pairs

    @classmethod
    def _section_order_rank(cls, section_id: int, sections_by_id: Dict[int, FormSection]) -> Tuple:
        orders: List = []
        current = sections_by_id.get(section_id)
        visited: Set[int] = set()
        while current and current.id not in visited:
            visited.add(current.id)
            orders.append(current.order)
            if not current.parent_section_id:
                break
            current = sections_by_id.get(current.parent_section_id)
        return tuple(reversed(orders))

    @classmethod
    def _section_position_key(cls, section: FormSection, sections_by_id: Dict[int, FormSection]) -> Tuple:
        return (cls._section_order_rank(section.id, sections_by_id), section.order, section.section_type)

    @classmethod
    def _item_position_key(cls, item: FormItem, sections_by_id: Dict[int, FormSection]) -> Tuple:
        return (cls._section_order_rank(item.section_id, sections_by_id), item.order, item.item_type)

    @classmethod
    def _choose_shared_stable_key(cls, old_row, new_row) -> str:
        if getattr(old_row, 'stable_key', None):
            return old_row.stable_key
        if getattr(new_row, 'stable_key', None):
            return new_row.stable_key
        return generate_stable_key()

    @classmethod
    def _assign_shared_stable_key(cls, old_row, new_row, shared_key: str) -> bool:
        changed = False
        if old_row.stable_key != shared_key:
            old_row.stable_key = shared_key
            changed = True
        if new_row.stable_key != shared_key:
            new_row.stable_key = shared_key
            changed = True
        return changed

    @classmethod
    def _align_pair_if_eligible(
        cls,
        old_row,
        new_row,
        old_keys: Set[str],
        new_keys: Set[str],
    ) -> bool:
        """Give a positionally matched pair one shared stable_key, only to fill a missing identity.

        A row that already carries a stable_key has an identity (cloned from the previous
        version, linked in the mapping review, or deliberately unlinked as a new field).
        Overwriting it from position would silently move data onto an unrelated field after
        a reorder or a replace-in-place edit.
        """
        if old_row.stable_key and new_row.stable_key:
            return False
        if old_row.stable_key and old_row.stable_key in new_keys:
            return False
        if new_row.stable_key and new_row.stable_key in old_keys:
            return False
        shared = cls._choose_shared_stable_key(old_row, new_row)
        changed = cls._assign_shared_stable_key(old_row, new_row, shared)
        if changed:
            old_keys.add(shared)
            new_keys.add(shared)
        return changed

    @classmethod
    def _align_stable_keys_for_deploy(
        cls,
        old_version_id: int,
        new_version_id: int,
        template_id: int,
    ) -> Dict[str, int]:
        """Align stable_key between archived and newly published structure rows before FK remap.

        Only fills identities that are missing (legacy rows never backfilled), then makes sure
        every row of both versions ends up with a key so later deploys match by key alone.
        """
        counts = {'sections': 0, 'items': 0, 'indicators': 0}

        section_matches, item_matches = cls._compute_positional_matches(
            old_version_id, new_version_id, template_id
        )
        new_sections = FormSection.query.filter_by(
            template_id=template_id, version_id=new_version_id
        ).all()
        old_sections = FormSection.query.filter_by(
            template_id=template_id, version_id=old_version_id
        ).all()
        old_items = FormItem.query.filter_by(
            template_id=template_id, version_id=old_version_id
        ).all()
        new_items = FormItem.query.filter_by(
            template_id=template_id, version_id=new_version_id
        ).all()

        old_section_keys = {row.stable_key for row in old_sections if row.stable_key}
        new_section_keys = {row.stable_key for row in new_sections if row.stable_key}
        new_sections_by_id = {row.id: row for row in new_sections}
        for new_id, old_section in section_matches.items():
            new_section = new_sections_by_id.get(new_id)
            if new_section is None:
                continue
            if cls._align_pair_if_eligible(
                old_section, new_section, old_section_keys, new_section_keys
            ):
                counts['sections'] += 1

        old_item_keys = {row.stable_key for row in old_items if row.stable_key}
        new_item_keys = {row.stable_key for row in new_items if row.stable_key}
        new_items_by_id = {row.id: row for row in new_items}
        for new_id, old_item in item_matches.items():
            new_item = new_items_by_id.get(new_id)
            if new_item is None:
                continue
            if cls._align_pair_if_eligible(old_item, new_item, old_item_keys, new_item_keys):
                counts['indicators' if new_item.indicator_bank_id else 'items'] += 1

        for row in (*old_sections, *new_sections, *old_items, *new_items):
            if not row.stable_key:
                row.stable_key = generate_stable_key()

        db.session.flush()
        return counts

    @classmethod
    def _assert_unique_stable_keys(cls, version_id: int, template_id: int) -> None:
        """Refuse to deploy a version where two rows claim the same logical field."""
        for model, label in ((FormItem, 'field'), (FormSection, 'section')):
            duplicates = (
                db.session.query(model.stable_key, func.count(model.id))
                .filter(
                    model.template_id == template_id,
                    model.version_id == version_id,
                    model.stable_key.isnot(None),
                )
                .group_by(model.stable_key)
                .having(func.count(model.id) > 1)
                .all()
            )
            if duplicates:
                raise VersionDeployMigrationError(
                    f"Cannot deploy: {len(duplicates)} {label} identity key(s) are shared by more "
                    f"than one {label} in this version. Open the field mapping review and mark the "
                    f"extra {label}(s) as new before deploying."
                )

    @classmethod
    def _count_submission_rows_on_old_structure(cls, old_version_id: int, template_id: int) -> int:
        old_item_ids = [
            row[0]
            for row in db.session.query(FormItem.id).filter_by(
                template_id=template_id, version_id=old_version_id
            ).all()
        ]
        old_section_ids = [
            row[0]
            for row in db.session.query(FormSection.id).filter_by(
                template_id=template_id, version_id=old_version_id
            ).all()
        ]
        total = 0
        total += cls._count_form_data(old_item_ids)
        total += cls._count_repeat_group_data(old_item_ids)
        total += cls._count_submitted_documents(old_item_ids)
        total += cls._count_repeat_instances(old_section_ids)
        total += cls._count_dynamic_indicators(old_section_ids)
        total += cls._count_dynamic_contexts(old_section_ids)
        return total

    @classmethod
    def _build_page_map(cls, section_map: Dict[int, int]) -> Dict[int, int]:
        """Map old FormPage ids to new ones using the sections that moved between them.

        Pages have no stable_key, so identity is inferred from the sections they hold:
        an old page maps to the new page that received most of its matched sections, and
        only when that relationship is one-to-one.
        """
        if not section_map:
            return {}
        old_sections = {
            row.id: row
            for row in FormSection.query.filter(FormSection.id.in_(list(section_map.keys()))).all()
        }
        new_sections = {
            row.id: row
            for row in FormSection.query.filter(FormSection.id.in_(list(section_map.values()))).all()
        }
        votes: Dict[Tuple[int, int], int] = defaultdict(int)
        for old_id, new_id in section_map.items():
            old_section = old_sections.get(old_id)
            new_section = new_sections.get(new_id)
            if not old_section or not new_section:
                continue
            if old_section.page_id and new_section.page_id:
                votes[(old_section.page_id, new_section.page_id)] += 1

        best_for_old: Dict[int, Tuple[int, int]] = {}
        for (old_page, new_page), count in votes.items():
            current = best_for_old.get(old_page)
            if current is None or count > current[1] or (
                count == current[1] and new_page < current[0]
            ):
                best_for_old[old_page] = (new_page, count)

        claimed: Dict[int, Tuple[int, int]] = {}
        for old_page, (new_page, count) in sorted(best_for_old.items()):
            holder = claimed.get(new_page)
            if holder is None or count > holder[1]:
                claimed[new_page] = (old_page, count)
        return {old_page: new_page for new_page, (old_page, _count) in claimed.items()}

    @classmethod
    def _count_page_statuses(cls, old_page_ids: List[int]) -> int:
        if not old_page_ids:
            return 0
        return db.session.query(func.count(AssignmentPageStatus.id)).filter(
            AssignmentPageStatus.form_page_id.in_(old_page_ids)
        ).scalar() or 0

    @classmethod
    def _remap_page_statuses(cls, page_map: Dict[int, int]) -> Tuple[int, int]:
        """Carry per-page workflow status (submitted/approved/locked) onto the new pages.

        Returns (rows_moved, pages_skipped). A page is skipped when the new page already has
        status rows, so an existing workflow state is never overwritten.
        """
        moved = 0
        skipped = 0
        for old_page_id, new_page_id in page_map.items():
            if old_page_id == new_page_id:
                continue
            already_tracked = db.session.query(AssignmentPageStatus.id).filter(
                AssignmentPageStatus.form_page_id == new_page_id
            ).first()
            if already_tracked:
                skipped += 1
                continue
            moved += (
                AssignmentPageStatus.query.filter(AssignmentPageStatus.form_page_id == old_page_id)
                .update({'form_page_id': new_page_id}, synchronize_session=False)
                or 0
            )
        return moved, skipped

    @classmethod
    def _remap_variable_item_references(cls, item_map: Dict[int, int]) -> int:
        """Repoint template variables that read a field by id to the field's new row.

        Variables store ``source_form_item_id`` as a raw form_item.id. Once the submission rows
        move to the new version's items, a reference to the old id resolves to nothing.
        """
        effective = {old: new for old, new in item_map.items() if old != new}
        if not effective:
            return 0
        remapped = 0
        versions = FormTemplateVersion.query.filter(FormTemplateVersion.variables.isnot(None)).all()
        for version in versions:
            variables = version.variables
            if not isinstance(variables, dict):
                continue
            updated = None
            for name, config in variables.items():
                if not isinstance(config, dict):
                    continue
                raw = config.get('source_form_item_id')
                try:
                    old_id = int(raw)
                except (TypeError, ValueError):
                    continue
                new_id = effective.get(old_id)
                if new_id is None:
                    continue
                if updated is None:
                    updated = copy.deepcopy(variables)
                updated[name]['source_form_item_id'] = new_id
                remapped += 1
            if updated is not None:
                version.variables = updated
        return remapped

    @classmethod
    def _restore_archived_rows(
        cls, current_version_id: int, target_version_id: int, template_id: int
    ) -> Tuple[int, int]:
        """Un-archive rows of a re-deployed version that an earlier deploy archived as orphans.

        Those rows are exactly the archived ones whose key is absent from the version being
        replaced; rows archived by editors (and still present in both versions) stay archived.
        """
        current_item_keys = {
            row[0]
            for row in db.session.query(FormItem.stable_key).filter_by(
                template_id=template_id, version_id=current_version_id
            ).filter(FormItem.stable_key.isnot(None)).all()
        }
        current_section_keys = {
            row[0]
            for row in db.session.query(FormSection.stable_key).filter_by(
                template_id=template_id, version_id=current_version_id
            ).filter(FormSection.stable_key.isnot(None)).all()
        }
        restored_items = 0
        for item in FormItem.query.filter_by(
            template_id=template_id, version_id=target_version_id, archived=True
        ).all():
            if item.stable_key and item.stable_key not in current_item_keys:
                item.archived = False
                restored_items += 1
        restored_sections = 0
        for section in FormSection.query.filter_by(
            template_id=template_id, version_id=target_version_id, archived=True
        ).all():
            if section.stable_key and section.stable_key not in current_section_keys:
                section.archived = False
                restored_sections += 1
        return restored_items, restored_sections

    @classmethod
    def _bulk_remap_fk(cls, model, column_name: str, id_map: Dict[int, int]) -> int:
        if not id_map:
            return 0
        column = getattr(model, column_name)
        total = 0
        for old_id, new_id in id_map.items():
            if old_id == new_id:
                continue
            updated = (
                model.query.filter(column == old_id)
                .update({column_name: new_id}, synchronize_session=False)
            )
            total += updated or 0
        return total

    @classmethod
    def _assert_no_submission_rows_on_new_sections(cls, new_section_ids: List[int]) -> None:
        if not new_section_ids:
            return
        checks = [
            ('repeat_group_instance', RepeatGroupInstance.query.filter(
                RepeatGroupInstance.section_id.in_(new_section_ids)
            ).count()),
            ('dynamic_indicator_data', DynamicIndicatorData.query.filter(
                DynamicIndicatorData.section_id.in_(new_section_ids)
            ).count()),
            ('dynamic_section_context', DynamicSectionContext.query.filter(
                DynamicSectionContext.section_id.in_(new_section_ids)
            ).count()),
        ]
        for label, count in checks:
            if count and count > 0:
                raise VersionDeployMigrationError(
                    f"Cannot deploy: draft version already has {count} "
                    f"{label} row(s). Data entry on a draft version is not supported."
                )

    @classmethod
    def _archive_orphaned_items(
        cls, old_version_id: int, new_version_id: int, template_id: int
    ) -> int:
        new_keys = {
            row[0]
            for row in db.session.query(FormItem.stable_key).filter_by(
                template_id=template_id, version_id=new_version_id
            ).filter(FormItem.stable_key.isnot(None)).all()
            if row[0]
        }
        orphaned = FormItem.query.filter_by(
            template_id=template_id, version_id=old_version_id, archived=False
        ).filter(
            FormItem.stable_key.isnot(None),
            ~FormItem.stable_key.in_(new_keys) if new_keys else FormItem.stable_key.isnot(None),
        ).all()
        count = 0
        for item in orphaned:
            if item.stable_key and item.stable_key not in new_keys:
                item.archived = True
                count += 1
        return count

    @classmethod
    def _archive_orphaned_sections(
        cls, old_version_id: int, new_version_id: int, template_id: int
    ) -> int:
        new_keys = {
            row[0]
            for row in db.session.query(FormSection.stable_key).filter_by(
                template_id=template_id, version_id=new_version_id
            ).filter(FormSection.stable_key.isnot(None)).all()
            if row[0]
        }
        orphaned = FormSection.query.filter_by(
            template_id=template_id, version_id=old_version_id, archived=False
        ).filter(
            FormSection.stable_key.isnot(None),
            ~FormSection.stable_key.in_(new_keys) if new_keys else FormSection.stable_key.isnot(None),
        ).all()
        count = 0
        for section in orphaned:
            if section.stable_key and section.stable_key not in new_keys:
                section.archived = True
                count += 1
        return count

    @classmethod
    def _count_orphan_items(cls, old_version_id, new_version_id, template_id) -> int:
        new_keys = {
            row[0]
            for row in db.session.query(FormItem.stable_key).filter_by(
                template_id=template_id, version_id=new_version_id
            ).filter(FormItem.stable_key.isnot(None)).all()
            if row[0]
        }
        q = FormItem.query.filter_by(
            template_id=template_id, version_id=old_version_id
        ).filter(FormItem.stable_key.isnot(None))
        if new_keys:
            q = q.filter(~FormItem.stable_key.in_(new_keys))
        return q.count()

    @classmethod
    def _count_orphan_sections(cls, old_version_id, new_version_id, template_id) -> int:
        new_keys = {
            row[0]
            for row in db.session.query(FormSection.stable_key).filter_by(
                template_id=template_id, version_id=new_version_id
            ).filter(FormSection.stable_key.isnot(None)).all()
            if row[0]
        }
        q = FormSection.query.filter_by(
            template_id=template_id, version_id=old_version_id
        ).filter(FormSection.stable_key.isnot(None))
        if new_keys:
            q = q.filter(~FormSection.stable_key.in_(new_keys))
        return q.count()

    @classmethod
    def _count_form_data(cls, old_item_ids: List[int]) -> int:
        if not old_item_ids:
            return 0
        return db.session.query(func.count(FormData.id)).filter(
            FormData.form_item_id.in_(old_item_ids)
        ).scalar() or 0

    @classmethod
    def _count_repeat_group_data(cls, old_item_ids: List[int]) -> int:
        if not old_item_ids:
            return 0
        return db.session.query(func.count(RepeatGroupData.id)).filter(
            RepeatGroupData.form_item_id.in_(old_item_ids)
        ).scalar() or 0

    @classmethod
    def _count_submitted_documents(cls, old_item_ids: List[int]) -> int:
        if not old_item_ids:
            return 0
        return db.session.query(func.count(SubmittedDocument.id)).filter(
            SubmittedDocument.form_item_id.in_(old_item_ids)
        ).scalar() or 0

    @classmethod
    def _count_repeat_instances(cls, old_section_ids: List[int]) -> int:
        if not old_section_ids:
            return 0
        return db.session.query(func.count(RepeatGroupInstance.id)).filter(
            RepeatGroupInstance.section_id.in_(old_section_ids)
        ).scalar() or 0

    @classmethod
    def _count_dynamic_indicators(cls, old_section_ids: List[int]) -> int:
        if not old_section_ids:
            return 0
        return db.session.query(func.count(DynamicIndicatorData.id)).filter(
            DynamicIndicatorData.section_id.in_(old_section_ids)
        ).scalar() or 0

    @classmethod
    def _count_dynamic_contexts(cls, old_section_ids: List[int]) -> int:
        if not old_section_ids:
            return 0
        return db.session.query(func.count(DynamicSectionContext.id)).filter(
            DynamicSectionContext.section_id.in_(old_section_ids)
        ).scalar() or 0
