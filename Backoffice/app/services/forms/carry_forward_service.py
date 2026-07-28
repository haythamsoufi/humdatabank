"""Resolve carry-forward prefilled values from prior assignment submissions."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, TYPE_CHECKING, Tuple, Union

from app.models import AssignmentEntityStatus, AssignedForm, FormData

if TYPE_CHECKING:
    from app.models.form_items import FormItem

_CURRENT_SENTINEL = '__current__'
_STRATEGY_SOURCE = 'source'
_STRATEGY_ASSIGNMENT = 'assignment'
_VALID_STRATEGIES = {_STRATEGY_SOURCE, _STRATEGY_ASSIGNMENT}


class CarryForwardService:
    """Load prior-round form data for items marked with config.carry_forward."""

    @classmethod
    def resolve_for_aes(
        cls,
        aes: AssignmentEntityStatus,
        carry_forward_items: Iterable['FormItem'],
    ) -> Dict[int, Dict[str, Any]]:
        """Return carry-forward payloads keyed by current form_item_id."""
        items = [item for item in carry_forward_items if cls._item_has_carry_forward(item)]
        if not items or not aes:
            return {}

        item_ids = [item.id for item in items]
        current_entries = {
            fd.form_item_id: fd
            for fd in FormData.query.filter(
                FormData.assignment_entity_status_id == aes.id,
                FormData.form_item_id.in_(item_ids),
            ).all()
        }

        results: Dict[int, Dict[str, Any]] = {}
        for item in items:
            if cls._current_aes_has_user_data(current_entries.get(item.id)):
                continue

            payload = cls._resolve_item_payload(aes, item)
            if payload is not None:
                results[item.id] = payload

        return results

    @classmethod
    def resolve_references_for_aes(
        cls,
        aes: AssignmentEntityStatus,
        carry_forward_items: Iterable['FormItem'],
    ) -> Dict[int, Dict[str, Any]]:
        """Return carry-forward reference payloads for comparison, even when saved data exists."""
        items = [item for item in carry_forward_items if cls._item_has_carry_forward(item)]
        if not items or not aes:
            return {}

        results: Dict[int, Dict[str, Any]] = {}
        for item in items:
            payload = cls._resolve_item_payload(aes, item)
            if payload is not None:
                results[item.id] = payload

        return results

    @staticmethod
    def _item_has_carry_forward(item: 'FormItem') -> bool:
        config = item.config if isinstance(getattr(item, 'config', None), dict) else {}
        return bool(config.get('carry_forward'))

    @staticmethod
    def _current_aes_has_user_data(entry: Optional[FormData]) -> bool:
        if entry is None:
            return False
        if entry.data_not_available or entry.not_applicable:
            return True
        if entry.value is not None and str(entry.value).strip() != '':
            return True
        if entry.disagg_data is not None:
            return True
        if getattr(entry, 'prefilled_value', None) is not None:
            return True
        if getattr(entry, 'prefilled_disagg_data', None) is not None:
            return True
        if getattr(entry, 'imputed_value', None) is not None:
            return True
        if getattr(entry, 'imputed_disagg_data', None) is not None:
            return True
        return False

    @classmethod
    def _effective_sources(cls, config: dict) -> List[dict]:
        """Return configured sources in priority order.

        When no sources are configured, default to the current template and item.
        """
        sources = config.get('carry_forward_sources') or []
        if not sources:
            return [{'template_id': _CURRENT_SENTINEL, 'item_id': _CURRENT_SENTINEL}]
        return [source for source in sources if isinstance(source, dict)]

    @classmethod
    def _resolve_item_payload(cls, aes: AssignmentEntityStatus, item: 'FormItem') -> Optional[Dict[str, Any]]:
        config = item.config if isinstance(item.config, dict) else {}
        strategy = cls._normalize_priority(config.get('carry_forward_priority'))

        if strategy == _STRATEGY_ASSIGNMENT:
            return cls._resolve_item_payload_by_assignment(aes, item, config)
        return cls._resolve_item_payload_by_source(aes, item, config)

    @classmethod
    def _normalize_priority(cls, raw: Any) -> str:
        if isinstance(raw, str):
            normalized = raw.strip().lower()
            if normalized in _VALID_STRATEGIES:
                return normalized
        return _STRATEGY_SOURCE

    @classmethod
    def normalize_priority_for_storage(cls, raw: Any) -> str:
        return cls._normalize_priority(raw)

    @classmethod
    def _resolve_item_payload_by_source(
        cls,
        aes: AssignmentEntityStatus,
        item: 'FormItem',
        config: dict,
    ) -> Optional[Dict[str, Any]]:
        for source in cls._effective_sources(config):
            payload = cls._resolve_single_source(aes, item, source)
            if payload is not None:
                return payload
        return None

    @classmethod
    def _resolve_item_payload_by_assignment(
        cls,
        aes: AssignmentEntityStatus,
        item: 'FormItem',
        config: dict,
    ) -> Optional[Dict[str, Any]]:
        candidates: List[Tuple[Any, AssignmentEntityStatus, int, Optional['FormItem'], int]] = []

        for source in cls._effective_sources(config):
            resolved = cls._resolve_source_candidate(aes, item, source)
            if resolved is None:
                continue
            template_id, form_item_id, source_item, prev_aes = resolved
            sort_key = cls._aes_submission_sort_key(prev_aes)
            candidates.append((sort_key, prev_aes, form_item_id, source_item, template_id))

        if not candidates:
            return None

        candidates.sort(key=lambda entry: entry[0], reverse=True)
        _, prev_aes, form_item_id, source_item, template_id = candidates[0]
        return cls._payload_from_form_data(
            prev_aes,
            form_item_id,
            source_item,
            source_template_id=template_id,
        )

    @classmethod
    def _resolve_single_source(
        cls,
        aes: AssignmentEntityStatus,
        item: 'FormItem',
        source: dict,
    ) -> Optional[Dict[str, Any]]:
        resolved = cls._resolve_source_candidate(aes, item, source)
        if resolved is None:
            return None
        template_id, form_item_id, source_item, prev_aes = resolved
        return cls._payload_from_form_data(
            prev_aes,
            form_item_id,
            source_item,
            source_template_id=template_id,
        )

    @classmethod
    def _resolve_source_candidate(
        cls,
        aes: AssignmentEntityStatus,
        item: 'FormItem',
        source: dict,
    ) -> Optional[Tuple[int, int, Optional['FormItem'], AssignmentEntityStatus]]:
        try:
            template_id, form_item_id, source_item = cls._resolve_source_ids(aes, item, source)
        except (TypeError, ValueError):
            return None
        if not template_id or not form_item_id:
            return None

        prev_aes = cls._find_previous_aes_with_item_data(
            aes,
            template_id=template_id,
            form_item_id=form_item_id,
            item=source_item,
        )
        if not prev_aes:
            return None
        return template_id, form_item_id, source_item, prev_aes

    @staticmethod
    def _aes_submission_sort_key(aes: AssignmentEntityStatus) -> Tuple[Any, Any, int]:
        submitted_at = getattr(aes, 'submitted_at', None)
        status_timestamp = getattr(aes, 'status_timestamp', None)
        aes_id = getattr(aes, 'id', 0) or 0
        return (submitted_at, status_timestamp, aes_id)

    @classmethod
    def _resolve_source_ids(
        cls,
        aes: AssignmentEntityStatus,
        item: 'FormItem',
        source: dict,
    ) -> Tuple[int, int, Optional['FormItem']]:
        template_id = cls._resolve_template_id(aes, source.get('template_id'))
        form_item_id, source_item = cls._resolve_item_id(item, source.get('item_id'))
        return template_id, form_item_id, source_item

    @classmethod
    def _resolve_template_id(cls, aes: AssignmentEntityStatus, raw: Any) -> int:
        if cls._is_current_sentinel(raw):
            template_id = aes.assigned_form.template_id if aes.assigned_form else None
            if template_id is None:
                raise ValueError('current template unavailable')
            return int(template_id)
        return int(raw)

    @classmethod
    def _resolve_item_id(
        cls,
        item: 'FormItem',
        raw: Any,
    ) -> Tuple[int, Optional['FormItem']]:
        if cls._is_current_sentinel(raw):
            return int(item.id), item
        form_item_id = int(raw)
        return form_item_id, cls._get_item_stub_for_payload(form_item_id)

    @staticmethod
    def _is_current_sentinel(raw: Any) -> bool:
        if raw is None:
            return True
        if isinstance(raw, str):
            normalized = raw.strip().lower()
            return normalized in (_CURRENT_SENTINEL, 'current', '__current__', 'this', '')
        return False

    @classmethod
    def normalize_source_for_storage(cls, source: dict) -> Optional[dict]:
        """Normalize one carry-forward source dict for JSON storage."""
        if not isinstance(source, dict):
            return None

        template_raw = source.get('template_id')
        item_raw = source.get('item_id')

        if cls._is_current_sentinel(template_raw):
            template_value: Union[str, int] = _CURRENT_SENTINEL
        else:
            try:
                template_value = int(template_raw)
            except (TypeError, ValueError):
                return None
            if template_value <= 0:
                return None

        if cls._is_current_sentinel(item_raw):
            item_value: Union[str, int] = _CURRENT_SENTINEL
        else:
            try:
                item_value = int(item_raw)
            except (TypeError, ValueError):
                return None
            if item_value <= 0:
                return None

        return {'template_id': template_value, 'item_id': item_value}

    @classmethod
    def _find_previous_aes_with_item_data(
        cls,
        aes: AssignmentEntityStatus,
        *,
        template_id: int,
        form_item_id: int,
        item: Optional['FormItem'] = None,
    ) -> Optional[AssignmentEntityStatus]:
        candidates = (
            AssignmentEntityStatus.query
            .join(AssignedForm)
            .filter(
                AssignmentEntityStatus.entity_type == aes.entity_type,
                AssignmentEntityStatus.entity_id == aes.entity_id,
                AssignedForm.template_id == template_id,
                AssignmentEntityStatus.id != aes.id,
            )
            .order_by(
                AssignmentEntityStatus.submitted_at.desc().nullslast(),
                AssignmentEntityStatus.status_timestamp.desc(),
                AssignmentEntityStatus.id.desc(),
            )
            .limit(25)
            .all()
        )
        for candidate in candidates:
            if cls._form_data_has_carry_forward_payload(candidate.id, form_item_id, item=item):
                return candidate
        return None

    @classmethod
    def _form_data_has_carry_forward_payload(
        cls,
        aes_id: int,
        form_item_id: int,
        *,
        item: Optional['FormItem'] = None,
    ) -> bool:
        entry = (
            FormData.query.filter_by(
                assignment_entity_status_id=aes_id,
                form_item_id=form_item_id,
            )
            .order_by(FormData.submitted_at.desc())
            .first()
        )
        if entry is None:
            return False
        is_matrix = bool(item and (item.is_matrix or item.is_plugin))
        if is_matrix:
            return entry.disagg_data is not None
        if entry.value is not None and str(entry.value).strip() != '':
            return True
        return entry.disagg_data is not None

    @classmethod
    def _payload_from_form_data(
        cls,
        prev_aes: AssignmentEntityStatus,
        form_item_id: int,
        item: Optional['FormItem'],
        *,
        source_template_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        entry = (
            FormData.query.filter_by(
                assignment_entity_status_id=prev_aes.id,
                form_item_id=form_item_id,
            )
            .order_by(FormData.submitted_at.desc())
            .first()
        )
        if entry is None:
            return None

        is_matrix = bool(item and (item.is_matrix or item.is_plugin))
        if is_matrix:
            data = entry.disagg_data
            if data is None:
                return None
            return {
                'value': None,
                'disagg_data': data,
                'is_matrix': True,
                'source_label': cls._build_source_label(prev_aes, form_item_id, source_template_id),
            }

        value = entry.value
        if value is None and entry.disagg_data is not None:
            value = entry.disagg_data
        if value is None or str(value).strip() == '':
            return None

        return {
            'value': value,
            'disagg_data': None,
            'is_matrix': False,
            'source_label': cls._build_source_label(prev_aes, form_item_id, source_template_id),
        }

    @staticmethod
    def _get_item_stub_for_payload(item_id: int) -> Optional['FormItem']:
        from app.models.form_items import FormItem

        return FormItem.query.get(item_id)

    @staticmethod
    def _build_source_label(
        prev_aes: AssignmentEntityStatus,
        form_item_id: int,
        source_template_id: Optional[int] = None,
    ) -> str:
        assigned_form = prev_aes.assigned_form
        period = getattr(assigned_form, 'period_name', None) or 'unknown period'
        template_id = source_template_id or (assigned_form.template_id if assigned_form else None)
        return f'template {template_id}, item {form_item_id}, period {period}'

    @staticmethod
    def iter_carry_forward_items(sections: Iterable) -> List['FormItem']:
        items: List['FormItem'] = []
        seen_ids = set()
        for section in sections or []:
            for field in getattr(section, 'fields_ordered', []) or []:
                if not field or not hasattr(field, 'id'):
                    continue
                if field.id in seen_ids:
                    continue
                seen_ids.add(field.id)
                config = field.config if isinstance(getattr(field, 'config', None), dict) else {}
                if config.get('carry_forward'):
                    items.append(field)
        return items
