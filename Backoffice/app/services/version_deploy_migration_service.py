"""Deploy-time FK remapping for template version submission data continuity."""

from __future__ import annotations

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
    RepeatGroupData,
    RepeatGroupInstance,
)
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

        counts = {
            'form_data': cls._count_form_data(old_item_ids),
            'repeat_group_data': cls._count_repeat_group_data(old_item_ids),
            'submitted_document': cls._count_submitted_documents(old_item_ids),
            'repeat_group_instance': cls._count_repeat_instances(old_section_ids),
            'dynamic_indicator_data': cls._count_dynamic_indicators(old_section_ids),
            'dynamic_section_context': cls._count_dynamic_contexts(old_section_ids),
        }
        total = sum(counts.values())
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
        matched_pub_item_ids: Set[int] = set()
        rows: List[Dict[str, Any]] = []

        for draft_item in new_items:
            published_item: Optional[FormItem] = None
            confidence = 'new'
            if draft_item.stable_key and draft_item.stable_key in pub_items_by_key:
                published_item = pub_items_by_key[draft_item.stable_key]
                confidence = 'exact'
            elif draft_item.id in item_matches:
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
        matched_pub_section_ids: Set[int] = set()
        for draft_section in new_sections:
            published_section: Optional[FormSection] = None
            confidence = 'new'
            if draft_section.stable_key and draft_section.stable_key in pub_sections_by_key:
                published_section = pub_sections_by_key[draft_section.stable_key]
                confidence = 'exact'
            elif draft_section.id in section_matches:
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
    ) -> Dict[str, Any]:
        """Remap submission rows from old_version structure to new_version via stable_key."""
        if old_version_id == new_version_id:
            return cls._empty_summary()

        aligned = cls._align_stable_keys_for_deploy(old_version_id, new_version_id, template_id)
        current_app.logger.info(
            "VERSION_MIGRATION: aligned stable_key rows sections=%s items=%s indicators=%s",
            aligned.get('sections', 0),
            aligned.get('items', 0),
            aligned.get('indicators', 0),
        )

        item_map, section_map = cls._build_key_maps(old_version_id, new_version_id, template_id)

        new_section_ids = [
            row[0]
            for row in db.session.query(FormSection.id).filter_by(
                template_id=template_id, version_id=new_version_id
            ).all()
        ]
        if section_map or item_map:
            cls._assert_no_submission_rows_on_new_sections(new_section_ids)

        summary: Dict[str, Any] = {
            'matched_items': len(item_map),
            'matched_sections': len(section_map),
            'per_table': {},
        }

        old_section_ids = list(section_map.keys())
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

        old_item_ids = list(item_map.keys())
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

        orphaned_items = cls._archive_orphaned_items(old_version_id, new_version_id, template_id)
        orphaned_sections = cls._archive_orphaned_sections(old_version_id, new_version_id, template_id)
        summary['orphaned_items'] = orphaned_items
        summary['orphaned_sections'] = orphaned_sections
        summary['remapped_rows'] = sum(summary['per_table'].values())
        summary['stable_key_alignment'] = aligned

        if summary['remapped_rows'] == 0:
            pending = cls._count_submission_rows_on_old_structure(old_version_id, template_id)
            if pending > 0 and not item_map and not section_map:
                raise VersionDeployMigrationError(
                    f"Cannot deploy: {pending} submission row(s) exist on the previous version "
                    f"but no fields could be matched to the new version by stable_key. "
                    f"Run: python scripts/backfill_stable_keys.py --dry-run then commit, "
                    f"or python scripts/repair_version_deploy_migration.py --template-id {template_id} "
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
        """Return draft row id -> published row for positional alignment (read-only)."""
        old_sections = FormSection.query.filter_by(
            template_id=template_id, version_id=old_version_id
        ).all()
        new_sections = FormSection.query.filter_by(
            template_id=template_id, version_id=new_version_id
        ).all()
        old_sections_by_id = {section.id: section for section in old_sections}
        new_sections_by_id = {section.id: section for section in new_sections}

        old_sections_by_pos = {
            cls._section_position_key(section, old_sections_by_id): section
            for section in old_sections
        }
        section_matches: Dict[int, FormSection] = {}
        for new_section in new_sections:
            pos = cls._section_position_key(new_section, new_sections_by_id)
            old_section = old_sections_by_pos.get(pos)
            if old_section:
                section_matches[new_section.id] = old_section

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

        old_items_by_pos = {}
        for item in old_items:
            if item.indicator_bank_id:
                continue
            old_items_by_pos[cls._item_position_key(item, old_sections_by_id)] = item

        for new_item in new_items:
            if new_item.indicator_bank_id:
                continue
            pos = cls._item_position_key(new_item, new_sections_by_id)
            old_item = old_items_by_pos.get(pos)
            if old_item:
                item_matches[new_item.id] = old_item

        return section_matches, item_matches

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
    def _align_stable_keys_for_deploy(
        cls,
        old_version_id: int,
        new_version_id: int,
        template_id: int,
    ) -> Dict[str, int]:
        """Align stable_key between archived and newly published structure rows before FK remap."""
        counts = {'sections': 0, 'items': 0, 'indicators': 0}

        old_sections = FormSection.query.filter_by(
            template_id=template_id, version_id=old_version_id
        ).all()
        new_sections = FormSection.query.filter_by(
            template_id=template_id, version_id=new_version_id
        ).all()
        old_sections_by_id = {s.id: s for s in old_sections}
        new_sections_by_id = {s.id: s for s in new_sections}

        old_sections_by_pos = {
            cls._section_position_key(section, old_sections_by_id): section
            for section in old_sections
        }
        for new_section in new_sections:
            pos = cls._section_position_key(new_section, new_sections_by_id)
            old_section = old_sections_by_pos.get(pos)
            if not old_section:
                continue
            shared = cls._choose_shared_stable_key(old_section, new_section)
            if cls._assign_shared_stable_key(old_section, new_section, shared):
                counts['sections'] += 1

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

        for bank_id, old_group in old_indicators_by_bank.items():
            new_group = new_indicators_by_bank.get(bank_id) or []
            if not new_group:
                continue
            old_group = sorted(old_group, key=lambda row: (row.order, row.id))
            new_group = sorted(new_group, key=lambda row: (row.order, row.id))
            for old_item, new_item in zip(old_group, new_group):
                shared = cls._choose_shared_stable_key(old_item, new_item)
                if cls._assign_shared_stable_key(old_item, new_item, shared):
                    counts['indicators'] += 1

        old_items_by_pos = {}
        for item in old_items:
            if item.indicator_bank_id:
                continue
            old_items_by_pos[cls._item_position_key(item, old_sections_by_id)] = item

        for new_item in new_items:
            if new_item.indicator_bank_id:
                continue
            pos = cls._item_position_key(new_item, new_sections_by_id)
            old_item = old_items_by_pos.get(pos)
            if not old_item:
                continue
            shared = cls._choose_shared_stable_key(old_item, new_item)
            if cls._assign_shared_stable_key(old_item, new_item, shared):
                counts['items'] += 1

        db.session.flush()
        return counts

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
