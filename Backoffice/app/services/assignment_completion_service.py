"""Assignment completion-rate calculations (dashboard, API, entry form)."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import case, func, or_, text

from app.models import (
    db,
    FormData,
    FormItem,
    FormSection,
    FormTemplate,
    SubmittedDocument,
)


def matrix_entry_is_filled(disagg, not_applicable) -> bool:
    """A matrix table counts as one filled item when N/A or any cell has data."""
    if not_applicable:
        return True
    if disagg and isinstance(disagg, dict):
        return any(
            v is not None and str(v).strip() != ''
            for k, v in disagg.items()
            if not k.startswith('_')
        )
    return False


def _form_data_has_value_filter():
    return or_(
        FormData.value.isnot(None),
        FormData.disagg_data.isnot(None),
        FormData.not_applicable == True,
    )


def _published_filters_single(template_id, version_id):
    return (
        FormSection.template_id == template_id,
        FormSection.version_id == version_id,
        FormItem.version_id == version_id,
        FormSection.archived == False,
        FormItem.archived == False,
    )


def _published_batch_join_filters(template_ids):
    return (
        FormSection.template_id.in_(template_ids),
        FormSection.version_id == FormTemplate.published_version_id,
        FormItem.version_id == FormTemplate.published_version_id,
        FormSection.archived == False,
        FormItem.archived == False,
    )


def _published_assignment_join_filters():
    """Restrict filled counts to published, non-archived form items."""
    return (
        FormSection.version_id == FormTemplate.published_version_id,
        FormItem.version_id == FormTemplate.published_version_id,
        FormSection.archived == False,
        FormItem.archived == False,
    )


def _uses_postgresql() -> bool:
    try:
        return db.engine.dialect.name == "postgresql"
    except Exception:
        return False


# Mirrors matrix_entry_is_filled() for top-level disagg_data keys (PostgreSQL jsonb).
_MATRIX_DISAGG_HAS_VALUE = text("""
    EXISTS (
        SELECT 1
        FROM jsonb_each(
            CASE
                WHEN form_data.disagg_data IS NULL THEN '{}'::jsonb
                WHEN jsonb_typeof(form_data.disagg_data::jsonb) = 'object'
                    THEN form_data.disagg_data::jsonb
                ELSE '{}'::jsonb
            END
        ) AS e(key, value)
        WHERE e.key NOT LIKE '\\_%'
          AND e.value IS NOT NULL
          AND btrim(e.value::text, '"') <> ''
    )
""")


def _matrix_row_is_filled_filter():
    """SQL filter: matrix FormData row counts as filled (N/A or non-empty disagg)."""
    return or_(
        FormData.not_applicable == True,
        _MATRIX_DISAGG_HAS_VALUE,
    )


def completion_rate_percent(filled_items: int, total_possible_items: int) -> float:
    if total_possible_items > 0:
        return (filled_items / total_possible_items) * 100
    return 0.0


@dataclass(frozen=True)
class CompletionMetrics:
    filled_items: int
    total_items: int
    completion_rate: float


@dataclass(frozen=True)
class CompletionPrefetch:
    total_items_by_template: dict[int, int]
    filled_data_by_aes: dict[int, int]
    filled_documents_by_aes: dict[int, int]

    def metrics_for(self, assignment_entity_status_id: int, template_id: int | None) -> CompletionMetrics:
        total_items = self.total_items_by_template.get(template_id, 0) if template_id else 0
        filled_items = (
            self.filled_data_by_aes.get(assignment_entity_status_id, 0)
            + self.filled_documents_by_aes.get(assignment_entity_status_id, 0)
        )
        return CompletionMetrics(
            filled_items=filled_items,
            total_items=total_items,
            completion_rate=completion_rate_percent(filled_items, total_items),
        )


class AssignmentCompletionService:
    """Centralized completion metrics for assignment entity statuses."""

    @staticmethod
    def _count_template_total_items(template_id: int, version_id: int) -> int:
        published_filters = _published_filters_single(template_id, version_id)
        non_document_count, document_count = (
            db.session.query(
                func.coalesce(
                    func.sum(case((FormItem.item_type != 'document_field', 1), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(case((FormItem.item_type == 'document_field', 1), else_=0)),
                    0,
                ),
            )
            .join(FormSection, FormItem.section_id == FormSection.id)
            .filter(*published_filters)
            .one()
        )
        return int(non_document_count) + int(document_count)

    @staticmethod
    def _count_filled_items(assignment_entity_status_id: int, template_id: int, version_id: int) -> int:
        published_filters = _published_filters_single(template_id, version_id)

        filled_non_matrix = (
            db.session.query(func.count(FormData.id))
            .join(FormItem, FormData.form_item_id == FormItem.id)
            .join(FormSection, FormItem.section_id == FormSection.id)
            .filter(
                FormData.assignment_entity_status_id == assignment_entity_status_id,
                *published_filters,
                FormItem.item_type != 'matrix',
                _form_data_has_value_filter(),
            )
            .scalar()
        ) or 0

        filled_matrices = AssignmentCompletionService._count_filled_matrix_rows(
            assignment_entity_status_id, published_filters
        )

        # One upload per document field is enough; max_documents is a cap, not a requirement.
        filled_documents = (
            db.session.query(func.count(func.distinct(SubmittedDocument.form_item_id)))
            .join(FormItem, SubmittedDocument.form_item_id == FormItem.id)
            .join(FormSection, FormItem.section_id == FormSection.id)
            .filter(
                SubmittedDocument.assignment_entity_status_id == assignment_entity_status_id,
                *published_filters,
                FormItem.item_type == 'document_field',
            )
            .scalar()
        ) or 0

        return int(filled_non_matrix) + filled_matrices + int(filled_documents)

    @staticmethod
    def _count_filled_matrix_rows(
        assignment_entity_status_id: int,
        published_filters,
    ) -> int:
        base = (
            db.session.query(func.count(FormData.id))
            .join(FormItem, FormData.form_item_id == FormItem.id)
            .join(FormSection, FormItem.section_id == FormSection.id)
            .filter(
                FormData.assignment_entity_status_id == assignment_entity_status_id,
                *published_filters,
                FormItem.item_type == 'matrix',
            )
        )
        if _uses_postgresql():
            return int(
                base.filter(_matrix_row_is_filled_filter()).scalar() or 0
            )

        matrix_entries = (
            db.session.query(FormData.disagg_data, FormData.not_applicable)
            .join(FormItem, FormData.form_item_id == FormItem.id)
            .join(FormSection, FormItem.section_id == FormSection.id)
            .filter(
                FormData.assignment_entity_status_id == assignment_entity_status_id,
                *published_filters,
                FormItem.item_type == 'matrix',
                or_(
                    FormData.disagg_data.isnot(None),
                    FormData.not_applicable == True,
                ),
            )
            .all()
        )
        return sum(
            1 for disagg, na in matrix_entries if matrix_entry_is_filled(disagg, na)
        )

    @staticmethod
    def _count_filled_matrix_rows_batch(
        assignment_entity_status_ids: list[int],
    ) -> dict[int, int]:
        if not assignment_entity_status_ids:
            return {}

        base = (
            db.session.query(
                FormData.assignment_entity_status_id,
                func.count(FormData.id),
            )
            .join(FormItem, FormData.form_item_id == FormItem.id)
            .join(FormSection, FormItem.section_id == FormSection.id)
            .join(FormTemplate, FormSection.template_id == FormTemplate.id)
            .filter(
                FormData.assignment_entity_status_id.in_(assignment_entity_status_ids),
                *_published_assignment_join_filters(),
                FormItem.item_type == 'matrix',
            )
        )
        if _uses_postgresql():
            return dict(
                base.filter(_matrix_row_is_filled_filter())
                .group_by(FormData.assignment_entity_status_id)
                .all()
            )

        matrix_entries = (
            db.session.query(
                FormData.assignment_entity_status_id,
                FormData.disagg_data,
                FormData.not_applicable,
            )
            .join(FormItem, FormData.form_item_id == FormItem.id)
            .join(FormSection, FormItem.section_id == FormSection.id)
            .join(FormTemplate, FormSection.template_id == FormTemplate.id)
            .filter(
                FormData.assignment_entity_status_id.in_(assignment_entity_status_ids),
                *_published_assignment_join_filters(),
                FormItem.item_type == 'matrix',
                or_(
                    FormData.disagg_data.isnot(None),
                    FormData.not_applicable == True,
                ),
            )
            .all()
        )
        matrix_filled_counts: dict[int, int] = {}
        for aes_id, disagg, na in matrix_entries:
            if matrix_entry_is_filled(disagg, na):
                matrix_filled_counts[aes_id] = matrix_filled_counts.get(aes_id, 0) + 1
        return matrix_filled_counts

    @staticmethod
    def template_total_items(template_id: int, version_id: int) -> int:
        return AssignmentCompletionService._count_template_total_items(template_id, version_id)

    @staticmethod
    def compute_for_assignment(
        assignment_entity_status_id: int,
        template_id: int,
        version_id: int,
    ) -> CompletionMetrics:
        total_items = AssignmentCompletionService._count_template_total_items(template_id, version_id)
        filled_items = AssignmentCompletionService._count_filled_items(
            assignment_entity_status_id, template_id, version_id
        )
        return CompletionMetrics(
            filled_items=filled_items,
            total_items=total_items,
            completion_rate=completion_rate_percent(filled_items, total_items),
        )

    @staticmethod
    def _prefetch_total_items_by_template(template_ids: set[int]) -> dict[int, int]:
        if not template_ids:
            return {}

        counts_rows = (
            db.session.query(
                FormSection.template_id,
                func.coalesce(
                    func.sum(case((FormItem.item_type != 'document_field', 1), else_=0)),
                    0,
                ).label('countable_count'),
                func.coalesce(
                    func.sum(case((FormItem.item_type == 'document_field', 1), else_=0)),
                    0,
                ).label('document_count'),
            )
            .join(FormItem, FormItem.section_id == FormSection.id)
            .join(FormTemplate, FormSection.template_id == FormTemplate.id)
            .filter(*_published_batch_join_filters(template_ids))
            .group_by(FormSection.template_id)
            .all()
        )
        return {
            tpl_id: int(countable or 0) + int(document_count or 0)
            for tpl_id, countable, document_count in counts_rows
        }

    @staticmethod
    def _prefetch_filled_data_by_aes(assignment_entity_status_ids: list[int]) -> dict[int, int]:
        if not assignment_entity_status_ids:
            return {}

        filled_non_matrix_counts = dict(
            db.session.query(FormData.assignment_entity_status_id, func.count(FormData.id))
            .join(FormItem, FormData.form_item_id == FormItem.id)
            .join(FormSection, FormItem.section_id == FormSection.id)
            .join(FormTemplate, FormSection.template_id == FormTemplate.id)
            .filter(
                FormData.assignment_entity_status_id.in_(assignment_entity_status_ids),
                *_published_assignment_join_filters(),
                FormItem.item_type != 'matrix',
                _form_data_has_value_filter(),
            )
            .group_by(FormData.assignment_entity_status_id)
            .all()
        )

        matrix_filled_counts = AssignmentCompletionService._count_filled_matrix_rows_batch(
            assignment_entity_status_ids
        )

        filled_data_counts = dict(filled_non_matrix_counts)
        for aes_id, count in matrix_filled_counts.items():
            filled_data_counts[aes_id] = filled_data_counts.get(aes_id, 0) + count
        return filled_data_counts

    @staticmethod
    def _prefetch_filled_documents_by_aes(assignment_entity_status_ids: list[int]) -> dict[int, int]:
        if not assignment_entity_status_ids:
            return {}

        return dict(
            db.session.query(
                SubmittedDocument.assignment_entity_status_id,
                func.count(func.distinct(SubmittedDocument.form_item_id)),
            )
            .join(FormItem, SubmittedDocument.form_item_id == FormItem.id)
            .join(FormSection, FormItem.section_id == FormSection.id)
            .join(FormTemplate, FormSection.template_id == FormTemplate.id)
            .filter(
                SubmittedDocument.assignment_entity_status_id.in_(assignment_entity_status_ids),
                *_published_assignment_join_filters(),
                FormItem.item_type == 'document_field',
            )
            .group_by(SubmittedDocument.assignment_entity_status_id)
            .all()
        )

    @staticmethod
    def prefetch(template_ids: set[int], assignment_entity_status_ids: list[int]) -> CompletionPrefetch:
        return CompletionPrefetch(
            total_items_by_template=AssignmentCompletionService._prefetch_total_items_by_template(template_ids),
            filled_data_by_aes=AssignmentCompletionService._prefetch_filled_data_by_aes(
                assignment_entity_status_ids
            ),
            filled_documents_by_aes=AssignmentCompletionService._prefetch_filled_documents_by_aes(
                assignment_entity_status_ids
            ),
        )
