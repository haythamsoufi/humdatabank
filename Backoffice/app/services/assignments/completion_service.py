"""Assignment completion-rate calculations (dashboard, API, entry form)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import and_, case, func, or_, text

from app.models import (
    AssignedForm,
    AssignmentEntityStatus,
    db,
    FormData,
    FormItem,
    FormSection,
    FormTemplate,
    RepeatGroupData,
    RepeatGroupInstance,
    SubmittedDocument,
)
from app.utils.matrix_activity import matrix_cell_display_value


def _matrix_cell_has_value(raw: Any) -> bool:
    """True when a matrix cell has a user-visible value (handles {original, modified} payloads)."""
    display = matrix_cell_display_value(raw)
    if display is None:
        return False
    if isinstance(display, bool):
        return display
    return str(display).strip() != ''


def matrix_entry_is_filled(disagg, not_applicable) -> bool:
    """A matrix table counts as one filled item when N/A or any cell has data.

    Only one non-empty cell is required — the whole matrix does not need to be complete.
    """
    if not_applicable:
        return True
    if not disagg or not isinstance(disagg, dict):
        return False
    return any(
        _matrix_cell_has_value(v)
        for k, v in disagg.items()
        if not str(k).startswith('_')
    )


def _coalesce_disagg(disagg, prefilled_disagg, imputed_disagg):
    if disagg is not None:
        return disagg
    if prefilled_disagg is not None:
        return prefilled_disagg
    if imputed_disagg is not None:
        return imputed_disagg
    return None


def explain_matrix_entry_fill(
    disagg,
    prefilled_disagg,
    imputed_disagg,
    not_applicable,
    *,
    source: str,
) -> dict[str, Any]:
    """Human-readable reason why a matrix row does or does not count as filled."""
    if not_applicable:
        return {
            'filled': True,
            'reason': 'not_applicable',
            'source': source,
            'detail': 'Marked not applicable.',
        }

    effective = _coalesce_disagg(disagg, prefilled_disagg, imputed_disagg)
    if effective is None:
        return {
            'filled': False,
            'reason': 'no_disagg_data',
            'source': source,
            'detail': 'No saved matrix payload (disagg_data / prefilled / imputed).',
        }
    if not isinstance(effective, dict):
        return {
            'filled': False,
            'reason': 'invalid_disagg_shape',
            'source': source,
            'detail': f'Expected object, got {type(effective).__name__}.',
        }

    cell_keys = [k for k in effective if not str(k).startswith('_')]
    filled_cells = [k for k in cell_keys if _matrix_cell_has_value(effective.get(k))]
    if filled_cells:
        return {
            'filled': True,
            'reason': 'has_cell_data',
            'source': source,
            'detail': 'At least one matrix cell has a value (one cell is enough).',
            'filled_cell_count': len(filled_cells),
            'sample_cells': filled_cells[:5],
            'data_source': (
                'disagg_data' if disagg is not None
                else 'prefilled_disagg_data' if prefilled_disagg is not None
                else 'imputed_disagg_data'
            ),
        }

    return {
        'filled': False,
        'reason': 'all_cells_empty',
        'source': source,
        'detail': 'Matrix payload exists but every cell is empty.',
        'cell_count': len(cell_keys),
    }


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


def _exclude_from_completion_rate_filter():
    """Exclude optional items (e.g. comment fields) flagged in form builder."""
    cfg = FormItem.config
    flag = cfg['exclude_from_completion_rate']
    return or_(
        cfg.is_(None),
        flag.is_(None),
        func.coalesce(flag.as_boolean(), False).is_(False),
    )


def _countable_form_item_filter():
    """Exclude labels (blank), images, and items flagged optional for completion."""
    type_lower = func.lower(func.coalesce(FormItem.type, ''))
    return and_(
        FormItem.item_type.notin_(['image', 'blank']),
        or_(
            FormItem.item_type != 'question',
            type_lower != 'blank',
        ),
        _exclude_from_completion_rate_filter(),
    )


def _visibility_filters(
    hidden_field_ids: set[int] | None,
    hidden_section_ids: set[int] | None,
):
    """Exclude relevance-hidden fields/sections from completion counts."""
    filters = []
    if hidden_field_ids:
        filters.append(~FormItem.id.in_(list(hidden_field_ids)))
    if hidden_section_ids:
        filters.append(~FormItem.section_id.in_(list(hidden_section_ids)))
    return tuple(filters)


def _repeat_group_row_is_filled(row) -> bool:
    """True when a RepeatGroupData row counts as filled for completion."""
    if not row:
        return False
    if row.not_applicable or row.data_not_available:
        return True
    effective_disagg = _coalesce_disagg(
        row.disagg_data,
        row.prefilled_disagg_data,
        row.imputed_disagg_data,
    )
    if effective_disagg is not None:
        if isinstance(effective_disagg, dict):
            values = effective_disagg.get('values')
            if isinstance(values, dict) and any(
                v is not None and str(v).strip() != ''
                for v in values.values()
            ):
                return True
            if any(
                _matrix_cell_has_value(v)
                for k, v in effective_disagg.items()
                if not str(k).startswith('_')
            ):
                return True
        elif str(effective_disagg).strip():
            return True
    effective_value = row.value
    if effective_value is None and row.prefilled_value is not None:
        effective_value = row.prefilled_value
    elif effective_value is None and row.imputed_value is not None:
        effective_value = row.imputed_value
    return effective_value is not None and str(effective_value).strip() != ''


def _repeat_section_id_by_section_id(template_id: int, version_id: int) -> dict[int, int]:
    """Map section id -> owning repeat section id (includes repeat sections themselves)."""
    rows = (
        db.session.query(
            FormSection.id,
            FormSection.section_type,
            FormSection.parent_section_id,
        )
        .filter(
            FormSection.template_id == template_id,
            FormSection.version_id == version_id,
            FormSection.archived == False,
        )
        .all()
    )
    meta = {sid: (stype, pid) for sid, stype, pid in rows}
    out: dict[int, int] = {}
    for sid, (stype, pid) in meta.items():
        if stype == 'repeat':
            out[sid] = sid
        elif pid and meta.get(pid, (None, None))[0] == 'repeat':
            out[sid] = pid
    return out


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
class MissingCompletionItem:
    form_item_id: int
    section_id: int
    item_type: str
    label: str
    question_type: str | None = None
    fill_hint: str | None = None
    fill_debug: dict | None = field(default=None, compare=False)

    def as_dict(self, *, include_debug: bool = False) -> dict:
        payload = {
            'form_item_id': self.form_item_id,
            'section_id': self.section_id,
            'item_type': self.item_type,
            'label': self.label,
            'question_type': self.question_type,
        }
        if self.fill_hint:
            payload['fill_hint'] = self.fill_hint
        if include_debug and self.fill_debug:
            payload['fill_debug'] = self.fill_debug
        return payload


@dataclass(frozen=True)
class CompletionMetrics:
    filled_items: int
    total_items: int
    completion_rate: float


@dataclass(frozen=True)
class CompletionPrefetch:
    """Batch completion metrics keyed by AssignmentEntityStatus id."""

    metrics_by_aes: dict[int, CompletionMetrics]

    def metrics_for(self, assignment_entity_status_id: int, template_id: int | None) -> CompletionMetrics:
        del template_id  # kept for call-site compatibility
        return self.metrics_by_aes.get(
            assignment_entity_status_id,
            CompletionMetrics(filled_items=0, total_items=0, completion_rate=0.0),
        )


class AssignmentCompletionService:
    """Centralized completion metrics for assignment entity statuses."""

    @staticmethod
    def _count_template_total_items(
        template_id: int,
        version_id: int,
        hidden_field_ids: set[int] | None = None,
        hidden_section_ids: set[int] | None = None,
    ) -> int:
        published_filters = _published_filters_single(template_id, version_id)
        visibility_filters = _visibility_filters(hidden_field_ids, hidden_section_ids)
        non_document_count, document_count = (
            db.session.query(
                func.coalesce(
                    func.sum(case((
                        and_(
                            FormItem.item_type.notin_(['document_field', 'image']),
                            _countable_form_item_filter(),
                        ),
                        1,
                    ), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(case((FormItem.item_type == 'document_field', 1), else_=0)),
                    0,
                ),
            )
            .join(FormSection, FormItem.section_id == FormSection.id)
            .filter(*published_filters, *visibility_filters)
            .one()
        )
        return int(non_document_count) + int(document_count)

    @staticmethod
    def _filled_repeat_non_matrix_item_ids(
        assignment_entity_status_id: int,
        template_id: int,
        version_id: int,
        published_filters,
        visibility_filters=(),
    ) -> set[int]:
        """Form items inside repeat sections filled in every visible repeat instance."""
        repeat_by_section = _repeat_section_id_by_section_id(template_id, version_id)
        if not repeat_by_section:
            return set()

        item_rows = (
            db.session.query(FormItem.id, FormItem.section_id)
            .join(FormSection, FormItem.section_id == FormSection.id)
            .filter(
                *published_filters,
                *visibility_filters,
                FormItem.section_id.in_(list(repeat_by_section.keys())),
                FormItem.item_type.notin_(['matrix', 'image']),
                _countable_form_item_filter(),
            )
            .all()
        )
        if not item_rows:
            return set()

        repeat_section_ids = set(repeat_by_section.values())
        instances = RepeatGroupInstance.query.filter(
            RepeatGroupInstance.assignment_entity_status_id == assignment_entity_status_id,
            RepeatGroupInstance.section_id.in_(list(repeat_section_ids)),
            RepeatGroupInstance.is_hidden == False,  # noqa: E712
        ).all()
        instances_by_repeat_section: dict[int, list] = {}
        for inst in instances:
            instances_by_repeat_section.setdefault(inst.section_id, []).append(inst)

        instance_ids = [inst.id for inst in instances]
        data_by_instance_item: dict[tuple[int, int], object] = {}
        if instance_ids:
            for row in RepeatGroupData.query.filter(
                RepeatGroupData.repeat_instance_id.in_(instance_ids)
            ).all():
                data_by_instance_item[(row.repeat_instance_id, row.form_item_id)] = row

        filled: set[int] = set()
        for form_item_id, section_id in item_rows:
            repeat_section_id = repeat_by_section.get(section_id)
            if not repeat_section_id:
                continue
            insts = instances_by_repeat_section.get(repeat_section_id) or []
            if not insts:
                continue
            if all(
                _repeat_group_row_is_filled(
                    data_by_instance_item.get((inst.id, form_item_id))
                )
                for inst in insts
            ):
                filled.add(form_item_id)
        return filled

    @staticmethod
    def _filled_non_matrix_form_item_ids(
        assignment_entity_status_id: int,
        template_id: int,
        version_id: int,
        published_filters,
        visibility_filters=(),
    ) -> set[int]:
        repeat_by_section = _repeat_section_id_by_section_id(template_id, version_id)
        repeat_section_ids = set(repeat_by_section.keys())

        query = (
            db.session.query(FormItem.id)
            .join(FormData, FormData.form_item_id == FormItem.id)
            .join(FormSection, FormItem.section_id == FormSection.id)
            .filter(
                FormData.assignment_entity_status_id == assignment_entity_status_id,
                *published_filters,
                *visibility_filters,
                FormItem.item_type != 'matrix',
                _form_data_has_value_filter(),
            )
        )
        if repeat_section_ids:
            query = query.filter(~FormItem.section_id.in_(list(repeat_section_ids)))

        filled = {item_id for (item_id,) in query.all()}
        filled |= AssignmentCompletionService._filled_repeat_non_matrix_item_ids(
            assignment_entity_status_id,
            template_id,
            version_id,
            published_filters,
            visibility_filters,
        )
        return filled

    @staticmethod
    def _count_filled_items(
        assignment_entity_status_id: int,
        template_id: int,
        version_id: int,
        hidden_field_ids: set[int] | None = None,
        hidden_section_ids: set[int] | None = None,
    ) -> int:
        published_filters = _published_filters_single(template_id, version_id)
        visibility_filters = _visibility_filters(hidden_field_ids, hidden_section_ids)

        filled_non_matrix = len(
            AssignmentCompletionService._filled_non_matrix_form_item_ids(
                assignment_entity_status_id,
                template_id,
                version_id,
                published_filters,
                visibility_filters,
            )
        )

        filled_matrices = AssignmentCompletionService._count_filled_matrix_rows(
            assignment_entity_status_id,
            published_filters,
            visibility_filters,
        )

        # One upload per document field is enough; max_documents is a cap, not a requirement.
        filled_documents = (
            db.session.query(func.count(func.distinct(SubmittedDocument.form_item_id)))
            .join(FormItem, SubmittedDocument.form_item_id == FormItem.id)
            .join(FormSection, FormItem.section_id == FormSection.id)
            .filter(
                SubmittedDocument.assignment_entity_status_id == assignment_entity_status_id,
                *published_filters,
                *visibility_filters,
                FormItem.item_type == 'document_field',
            )
            .scalar()
        ) or 0

        return int(filled_non_matrix) + filled_matrices + int(filled_documents)

    @staticmethod
    def _count_filled_matrix_rows(
        assignment_entity_status_id: int,
        published_filters,
        visibility_filters=(),
    ) -> int:
        return len(AssignmentCompletionService._filled_matrix_item_ids(
            assignment_entity_status_id, published_filters, visibility_filters
        ))

    @staticmethod
    def _matrix_fill_state_by_item_id(
        assignment_entity_status_id: int,
        published_filters,
        visibility_filters=(),
    ) -> dict[int, dict]:
        """Per matrix form_item_id, best-known fill explanation (any filled source wins)."""
        by_item: dict[int, dict] = {}

        def _merge(item_id: int, explanation: dict) -> None:
            existing = by_item.get(item_id)
            if existing and existing.get('filled'):
                return
            if explanation.get('filled') or existing is None:
                by_item[item_id] = explanation

        form_rows = (
            db.session.query(
                FormItem.id,
                FormData.disagg_data,
                FormData.prefilled_disagg_data,
                FormData.imputed_disagg_data,
                FormData.not_applicable,
            )
            .join(FormData, FormData.form_item_id == FormItem.id)
            .join(FormSection, FormItem.section_id == FormSection.id)
            .filter(
                FormData.assignment_entity_status_id == assignment_entity_status_id,
                *published_filters,
                *visibility_filters,
                FormItem.item_type == 'matrix',
            )
            .all()
        )
        for item_id, disagg, prefilled, imputed, na in form_rows:
            _merge(
                item_id,
                explain_matrix_entry_fill(
                    disagg, prefilled, imputed, na, source='form_data',
                ),
            )

        repeat_rows = (
            db.session.query(
                FormItem.id,
                RepeatGroupData.disagg_data,
                RepeatGroupData.prefilled_disagg_data,
                RepeatGroupData.imputed_disagg_data,
                RepeatGroupData.not_applicable,
            )
            .join(RepeatGroupInstance, RepeatGroupData.repeat_instance_id == RepeatGroupInstance.id)
            .join(FormItem, RepeatGroupData.form_item_id == FormItem.id)
            .join(FormSection, FormItem.section_id == FormSection.id)
            .filter(
                RepeatGroupInstance.assignment_entity_status_id == assignment_entity_status_id,
                *published_filters,
                *visibility_filters,
                FormItem.item_type == 'matrix',
            )
            .all()
        )
        for item_id, disagg, prefilled, imputed, na in repeat_rows:
            _merge(
                item_id,
                explain_matrix_entry_fill(
                    disagg, prefilled, imputed, na, source='repeat_group_data',
                ),
            )

        return by_item

    @staticmethod
    def _filled_matrix_item_ids(
        assignment_entity_status_id: int,
        published_filters,
        visibility_filters=(),
    ) -> set[int]:
        return {
            item_id
            for item_id, state in AssignmentCompletionService._matrix_fill_state_by_item_id(
                assignment_entity_status_id, published_filters, visibility_filters
            ).items()
            if state.get('filled')
        }

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
                FormData.prefilled_disagg_data,
                FormData.imputed_disagg_data,
                FormData.not_applicable,
            )
            .join(FormItem, FormData.form_item_id == FormItem.id)
            .join(FormSection, FormItem.section_id == FormSection.id)
            .join(FormTemplate, FormSection.template_id == FormTemplate.id)
            .filter(
                FormData.assignment_entity_status_id.in_(assignment_entity_status_ids),
                *_published_assignment_join_filters(),
                FormItem.item_type == 'matrix',
            )
            .all()
        )
        matrix_filled_counts: dict[int, int] = {}
        for aes_id, disagg, prefilled, imputed, na in matrix_entries:
            effective = _coalesce_disagg(disagg, prefilled, imputed)
            if not matrix_entry_is_filled(effective, na):
                continue
            matrix_filled_counts[aes_id] = matrix_filled_counts.get(aes_id, 0) + 1
        return matrix_filled_counts

    @staticmethod
    def template_total_items(template_id: int, version_id: int) -> int:
        return AssignmentCompletionService._count_template_total_items(template_id, version_id)

    @staticmethod
    def list_missing_items(
        assignment_entity_status_id: int,
        template_id: int,
        version_id: int,
        *,
        hidden_field_ids: set[int] | None = None,
        hidden_section_ids: set[int] | None = None,
        include_debug: bool = False,
    ) -> list[MissingCompletionItem]:
        """Return published form items that count toward completion but are not filled."""
        published_filters = _published_filters_single(template_id, version_id)
        visibility_filters = _visibility_filters(hidden_field_ids, hidden_section_ids)
        rows = (
            db.session.query(
                FormItem.id,
                FormItem.section_id,
                FormItem.item_type,
                FormItem.label,
                FormItem.type,
            )
            .join(FormSection, FormItem.section_id == FormSection.id)
            .filter(*published_filters, *visibility_filters, _countable_form_item_filter())
            .order_by(FormSection.order, FormItem.order)
            .all()
        )
        if not rows:
            return []

        filled_non_matrix = AssignmentCompletionService._filled_non_matrix_form_item_ids(
            assignment_entity_status_id,
            template_id,
            version_id,
            published_filters,
            visibility_filters,
        )
        matrix_fill_state = AssignmentCompletionService._matrix_fill_state_by_item_id(
            assignment_entity_status_id, published_filters, visibility_filters
        )
        filled_matrix = {
            item_id for item_id, state in matrix_fill_state.items() if state.get('filled')
        }
        filled_documents = {
            item_id for (item_id,) in (
                db.session.query(SubmittedDocument.form_item_id)
                .join(FormItem, SubmittedDocument.form_item_id == FormItem.id)
                .join(FormSection, FormItem.section_id == FormSection.id)
                .filter(
                    SubmittedDocument.assignment_entity_status_id == assignment_entity_status_id,
                    *published_filters,
                    *visibility_filters,
                    FormItem.item_type == 'document_field',
                )
                .distinct()
                .all()
            )
        }

        missing: list[MissingCompletionItem] = []
        for form_item_id, section_id, item_type, label, question_type in rows:
            fill_hint = None
            fill_debug = None
            if item_type == 'matrix':
                is_filled = form_item_id in filled_matrix
                if not is_filled:
                    state = matrix_fill_state.get(form_item_id)
                    if state:
                        fill_hint = state.get('reason')
                        if include_debug:
                            fill_debug = {**state, 'form_item_id': form_item_id}
                    else:
                        fill_hint = 'no_saved_row'
                        if include_debug:
                            fill_debug = {
                                'form_item_id': form_item_id,
                                'filled': False,
                                'reason': 'no_saved_row',
                                'detail': (
                                    'No FormData or repeat-group row exists for this matrix. '
                                    'Save the form after entering matrix data.'
                                ),
                            }
            elif item_type == 'document_field':
                is_filled = form_item_id in filled_documents
                if not is_filled:
                    fill_hint = 'no_document_upload'
            else:
                is_filled = form_item_id in filled_non_matrix
                if not is_filled:
                    fill_hint = 'no_form_data_value'
            if is_filled:
                continue
            missing.append(
                MissingCompletionItem(
                    form_item_id=form_item_id,
                    section_id=section_id,
                    item_type=item_type,
                    label=(label or '').strip(),
                    question_type=question_type,
                    fill_hint=fill_hint,
                    fill_debug=fill_debug,
                )
            )
        return missing

    @staticmethod
    def compute_for_assignment(
        assignment_entity_status_id: int,
        template_id: int,
        version_id: int,
        *,
        hidden_field_ids: set[int] | None = None,
        hidden_section_ids: set[int] | None = None,
    ) -> CompletionMetrics:
        total_items = AssignmentCompletionService._count_template_total_items(
            template_id,
            version_id,
            hidden_field_ids,
            hidden_section_ids,
        )
        filled_items = AssignmentCompletionService._count_filled_items(
            assignment_entity_status_id,
            template_id,
            version_id,
            hidden_field_ids,
            hidden_section_ids,
        )
        return CompletionMetrics(
            filled_items=filled_items,
            total_items=total_items,
            completion_rate=completion_rate_percent(filled_items, total_items),
        )

    @staticmethod
    def _template_context_for_aes(assignment_entity_status_id: int) -> tuple[int, int] | None:
        """Return (template_id, published_version_id) for an assignment entity status."""
        row = (
            db.session.query(FormTemplate.id, FormTemplate.published_version_id)
            .join(AssignedForm, AssignedForm.template_id == FormTemplate.id)
            .join(
                AssignmentEntityStatus,
                AssignmentEntityStatus.assigned_form_id == AssignedForm.id,
            )
            .filter(AssignmentEntityStatus.id == assignment_entity_status_id)
            .first()
        )
        if not row:
            return None
        template_id, published_version_id = row
        if not published_version_id:
            return None
        return template_id, published_version_id

    @staticmethod
    def backfill_persisted_rates(
        batch_size: int = 500,
        *,
        progress_callback=None,
    ) -> int:
        """Bulk-persist completion_rate for all assignment entity statuses.

        Optimized for migration/CLI: caches template item totals, commits in batches,
        and uses bulk UPDATE instead of per-row flush/get.

        Uses keyset pagination (id > last_id) rather than server-side cursors so
        batch commits remain safe on PostgreSQL.
        """
        if batch_size < 1:
            batch_size = 500

        total_items_cache: dict[tuple[int, int], int] = {}
        updated = 0
        last_id = 0

        while True:
            rows = (
                db.session.query(
                    AssignmentEntityStatus.id,
                    FormTemplate.id,
                    FormTemplate.published_version_id,
                )
                .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
                .join(FormTemplate, AssignedForm.template_id == FormTemplate.id)
                .filter(AssignmentEntityStatus.id > last_id)
                .order_by(AssignmentEntityStatus.id)
                .limit(batch_size)
                .all()
            )
            if not rows:
                break

            pending_updates: list[dict[str, object]] = []
            for aes_id, template_id, published_version_id in rows:
                if not published_version_id:
                    rate = 0.0
                else:
                    cache_key = (template_id, published_version_id)
                    if cache_key not in total_items_cache:
                        total_items_cache[cache_key] = (
                            AssignmentCompletionService._count_template_total_items(
                                template_id, published_version_id
                            )
                        )
                    total_items = total_items_cache[cache_key]
                    filled_items = AssignmentCompletionService._count_filled_items(
                        aes_id, template_id, published_version_id
                    )
                    rate = round(completion_rate_percent(filled_items, total_items), 1)

                pending_updates.append({'id': aes_id, 'completion_rate': rate})

            db.session.bulk_update_mappings(AssignmentEntityStatus, pending_updates)
            db.session.commit()
            updated += len(pending_updates)
            last_id = rows[-1][0]
            if progress_callback:
                progress_callback(updated)

        return updated

    @staticmethod
    def refresh_and_persist(assignment_entity_status_id: int) -> float:
        """Recompute completion rate and persist on assignment_entity_status."""
        aes = db.session.get(AssignmentEntityStatus, assignment_entity_status_id)
        if not aes:
            return 0.0

        context = AssignmentCompletionService._template_context_for_aes(assignment_entity_status_id)
        if not context:
            rate = 0.0
        else:
            template_id, published_version_id = context
            metrics = AssignmentCompletionService.compute_for_assignment(
                assignment_entity_status_id,
                template_id,
                published_version_id,
            )
            rate = round(metrics.completion_rate, 1)

        aes.completion_rate = rate
        db.session.flush()
        return rate

    @staticmethod
    def stored_rate_for(assignment_entity_status: AssignmentEntityStatus) -> float:
        """Return persisted completion rate, computing and storing when missing."""
        if assignment_entity_status.completion_rate is not None:
            return float(assignment_entity_status.completion_rate)
        return AssignmentCompletionService.refresh_and_persist(assignment_entity_status.id)

    @staticmethod
    def refresh_for_template(template_id: int) -> int:
        """Recompute and persist completion_rate for all entities on this template."""
        aes_ids = [
            aes_id
            for (aes_id,) in (
                db.session.query(AssignmentEntityStatus.id)
                .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
                .filter(AssignedForm.template_id == template_id)
                .all()
            )
        ]
        for aes_id in aes_ids:
            AssignmentCompletionService.refresh_and_persist(aes_id)
        return len(aes_ids)

    @staticmethod
    def refresh_for_template_with_existing_rates(template_id: int) -> int:
        """Recompute completion_rate for assignments that already have a stored rate > 0."""
        aes_ids = [
            aes_id
            for (aes_id,) in (
                db.session.query(AssignmentEntityStatus.id)
                .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
                .filter(
                    AssignedForm.template_id == template_id,
                    AssignmentEntityStatus.completion_rate.isnot(None),
                    AssignmentEntityStatus.completion_rate != 0,
                )
                .all()
            )
        ]
        for aes_id in aes_ids:
            AssignmentCompletionService.refresh_and_persist(aes_id)
        return len(aes_ids)

    @staticmethod
    def _item_exclude_from_completion_rate(form_item) -> bool:
        cfg = form_item.config if isinstance(form_item.config, dict) else {}
        return bool(cfg.get('exclude_from_completion_rate', False))

    @staticmethod
    def maybe_refresh_after_exclude_from_completion_change(
        form_item,
        previous_exclude: bool,
    ) -> int:
        """When exclude_from_completion_rate changes on the published version, refresh in-progress rates."""
        template = getattr(form_item, 'template', None)
        if not template or template.published_version_id != form_item.version_id:
            return 0
        new_exclude = AssignmentCompletionService._item_exclude_from_completion_rate(form_item)
        if new_exclude == previous_exclude:
            return 0
        return AssignmentCompletionService.refresh_for_template_with_existing_rates(template.id)

    @staticmethod
    def prefetch(template_ids: set[int], assignment_entity_status_ids: list[int]) -> CompletionPrefetch:
        """Batch-read persisted completion rates for dashboard/API list views."""
        del template_ids  # kept for call-site compatibility
        metrics_by_aes: dict[int, CompletionMetrics] = {}
        if not assignment_entity_status_ids:
            return CompletionPrefetch(metrics_by_aes=metrics_by_aes)

        for aes in AssignmentEntityStatus.query.filter(
            AssignmentEntityStatus.id.in_(assignment_entity_status_ids)
        ):
            rate = AssignmentCompletionService.stored_rate_for(aes)
            metrics_by_aes[aes.id] = CompletionMetrics(
                filled_items=0,
                total_items=0,
                completion_rate=rate,
            )
        return CompletionPrefetch(metrics_by_aes=metrics_by_aes)
