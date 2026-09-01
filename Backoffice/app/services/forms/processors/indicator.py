"""Form data indicator processing mixin."""

import json
from contextlib import suppress
from typing import Dict, List

from flask import request
from app.models import db, FormData, FormItem
from app.services.forms.processing_service import FormItemProcessor
from app.services.forms.processors._common import (
    MatrixJsonDecodeError,
    decode_b64_matrix_json,
    get_english_field_name,
    get_possibly_chunked_form_value,
)
from app.services.monitoring.debug import debug_manager

logger = debug_manager.get_logger(__name__)


class IndicatorProcessorMixin:
    """Mixin providing indicator processing for FormDataService."""

    @classmethod
    def _should_preserve_existing_on_empty_save(
        cls,
        form_item_id: int,
        data_entry,
        *,
        is_presave: bool,
        field_cleared: bool,
        indicator: FormItem = None,
        field_prefix: str = None,
    ) -> bool:
        """
        Avoid wiping stored values on action=save when the POST contains empty inputs
        for fields the user did not change (e.g. hidden disaggregation total_value inputs).
        """
        if is_presave or field_cleared:
            return is_presave
        if request.form.get('action', 'save') != 'save':
            return False
        if not data_entry or not cls._has_meaningful_data(data_entry):
            return False
        if cls._check_for_field_clearing_signals(form_item_id):
            return False
        # Questions and simple (non-disaggregated) indicators submit their primary input
        # directly; an empty value means the user cleared the field.
        if indicator is None:
            return False
        if not field_prefix or not FormItemProcessor._field_supports_disaggregation(indicator):
            return False
        mode = FormItemProcessor._resolve_indicator_reporting_mode(
            indicator, request.form, field_prefix
        )
        if FormItemProcessor._indicator_mode_has_submitted_values(
            indicator, request.form, field_prefix, mode
        ):
            return False
        return True

    @classmethod
    def _indicator_field_was_submitted(cls, indicator: FormItem, field_prefix: str) -> bool:
        """Determine whether this indicator's active-mode inputs were present in the POST."""
        if not FormItemProcessor._field_supports_disaggregation(indicator):
            total_value_field = f'{field_prefix}_total_value'
            standard_value_field = f'{field_prefix}_standard_value'
            field_value_field = f'field_value[{indicator.id}]'
            return (
                (total_value_field in request.form)
                or (standard_value_field in request.form)
                or (field_value_field in request.form)
            )

        return FormItemProcessor._indicator_active_inputs_in_post(
            indicator, request.form, field_prefix
        )

    @classmethod
    def _process_indicator_data(cls, indicator: FormItem, assignment_entity_status, validation_errors: List) -> List[Dict]:
        """
        Process indicator data with JavaScript-compatible field patterns.

        Maintains exact naming patterns:
        - indicator_{item_id}_total_value
        - indicator_{item_id}_reporting_mode
        - indicator_{item_id}_data_not_available
        """
        field_changes = []
        field_prefix = f'indicator_{indicator.id}'

        # Check for explicit field clearing signals from JavaScript
        field_cleared = cls._check_for_field_clearing_signals(indicator.id)
        if field_cleared:
            # Handle field clearing
            return cls._handle_field_clearing(indicator, assignment_entity_status, field_changes)

        # Use FormItemProcessor for unified processing
        processed_value, has_value, data_not_available, not_applicable = \
            FormItemProcessor.process_form_item_data(
                indicator, request.form, assignment_entity_status.id, field_prefix
            )

        total_value_field = f'{field_prefix}_total_value'
        standard_value_field = f'{field_prefix}_standard_value'
        total_value_raw = request.form.get(total_value_field)
        standard_value_raw = request.form.get(standard_value_field)
        field_was_submitted = cls._indicator_field_was_submitted(indicator, field_prefix)

        # Get or create form data entry using helper methods
        form_item_id = indicator.id
        DataModel = cls._get_data_model(assignment_entity_status)
        query_filter = cls._get_data_query_filter(assignment_entity_status, form_item_id)

        data_entry = DataModel.query.filter_by(**query_filter).first()

        is_presave = request.form.get('ifrc_presave') == '1'

        # Handle the case where field was submitted but has no value (clearing existing value)
        # This happens when user clears a field - it's submitted as empty string but has_value is False
        if field_was_submitted and not has_value and not data_not_available and not not_applicable:
            if cls._should_preserve_existing_on_empty_save(
                form_item_id,
                data_entry,
                is_presave=is_presave,
                field_cleared=field_cleared,
                indicator=indicator,
                field_prefix=field_prefix,
            ):
                logger.info(
                    "Indicator %s: save submitted empty (total_value=%r, standard_value=%r) but existing "
                    "data preserved (presave=%s).",
                    form_item_id,
                    total_value_raw,
                    standard_value_raw,
                    is_presave,
                )
                return field_changes

            cls._log_verbose(f"Indicator {form_item_id}: Field was submitted empty (total_value='{total_value_raw}', standard_value='{standard_value_raw}'), "
                       f"has_value={has_value}, clearing existing value. data_entry exists={data_entry is not None}")
            if data_entry:
                # Track old value and data availability flags for change detection
                old_value = data_entry.get_effective_value()
                if data_entry.disagg_data:
                    old_value = data_entry.disagg_data
                old_data_not_available = data_entry.data_not_available
                old_not_applicable = data_entry.not_applicable

                # Clear the existing value
                cls._update_indicator_entry(data_entry, indicator, None, False, False)
                db.session.add(data_entry)

                # Record the change
                if old_value is not None or old_data_not_available or old_not_applicable:
                    cls._clear_ai_validation_for_form_data(data_entry, reason="indicator_value_cleared")
                    field_changes.append({
                        'type': 'updated',
                        'form_item_id': form_item_id,
                        'field_name': get_english_field_name(indicator),
                        'old_value': old_value,
                        'new_value': None,
                        'old_data_not_available': old_data_not_available,
                        'new_data_not_available': False,
                        'old_not_applicable': old_not_applicable,
                        'new_not_applicable': False
                    })
            # If no existing entry and field was submitted empty, nothing to do
            return field_changes

        if has_value or data_not_available or not_applicable:
            if data_entry:
                # Track old value and data availability flags for change detection
                old_value = data_entry.get_effective_value()
                if data_entry.disagg_data:
                    old_value = data_entry.disagg_data

                # Check if data availability flags have changed
                old_data_not_available = data_entry.data_not_available
                old_not_applicable = data_entry.not_applicable

                # Update with new data
                cls._update_indicator_entry(data_entry, indicator, processed_value, data_not_available, not_applicable)

                # Determine if there's a meaningful change
                value_changed = old_value != processed_value
                availability_changed = (old_data_not_available != data_not_available) or (old_not_applicable != not_applicable)

                if value_changed or availability_changed:
                    cls._clear_ai_validation_for_form_data(data_entry, reason="indicator_value_changed")
                    field_changes.append({
                        'type': 'updated',
                        'form_item_id': form_item_id,
                        'field_name': get_english_field_name(indicator),
                        'old_value': old_value,
                        'new_value': processed_value,
                        'old_data_not_available': old_data_not_available,
                        'new_data_not_available': data_not_available,
                        'old_not_applicable': old_not_applicable,
                        'new_not_applicable': not_applicable
                    })
            else:
                # Create new entry using helper method
                data_entry = cls._create_data_entry(assignment_entity_status, form_item_id)
                cls._update_indicator_entry(data_entry, indicator, processed_value, data_not_available, not_applicable)
                db.session.add(data_entry)

                field_changes.append({
                    'type': 'added',
                    'form_item_id': form_item_id,
                    'field_name': get_english_field_name(indicator),
                    'old_value': None,
                    'new_value': processed_value
                })

        return field_changes

    @classmethod
    def _update_indicator_entry(cls, data_entry: FormData, indicator: FormItem,
                               processed_value, data_not_available: bool, not_applicable: bool):
        """Update FormData entry with indicator data maintaining JS compatibility"""

        # Set data availability flags first
        data_entry.set_data_availability(data_not_available, not_applicable)

        # Only update the value if we don't have data availability flags set
        if not data_not_available and not not_applicable:
            if processed_value is not None:
                # Check if processed_value is a disaggregated data structure
                if isinstance(processed_value, dict) and 'mode' in processed_value and 'values' in processed_value:
                    # It's disaggregated data, extract mode and values
                    mode = processed_value['mode']
                    values = processed_value['values']
                    data_entry.set_disaggregated_data(mode, values)
                else:
                    # It's simple data
                    data_entry.set_simple_value(processed_value)
            else:
                data_entry.set_simple_value(None)

    @classmethod
    def _calculate_direct_total(cls, direct_values) -> float:
        """Calculate total from direct values structure"""
        if isinstance(direct_values, dict):
            return sum(value for value in direct_values.values() if isinstance(value, (int, float)))
        elif isinstance(direct_values, (int, float)):
            return direct_values
        return 0

    @classmethod
    def _calculate_total_from_values(cls, values: Dict) -> float:
        """Calculate total from disaggregated values"""
        total = 0
        for key, value in values.items():
            if key in ('indirect', 'disability'):
                continue
            if isinstance(value, (int, float)):
                total += value
        return total

    @classmethod
    def _is_emergency_operations_choice(cls, form_item) -> bool:
        if not form_item or not getattr(form_item, 'is_question', False):
            return False
        return str(getattr(form_item, 'lookup_list_id', '') or '') == 'emergency_operations'

    @classmethod
    def _parse_emergency_metadata_from_display(cls, display_value):
        import re

        text = str(display_value or '').strip()
        if not text:
            return None
        match = re.match(r'^(.*)\s+\(([^)]+)\)\s*$', text)
        if match:
            return {
                'name': match.group(1).strip(),
                'code': match.group(2).strip(),
            }
        return {'name': text, 'code': ''}

    @classmethod
    def _get_emergency_metadata_from_request(cls, form_item_id=None, section_id=None, instance_number=None, field_index=None):
        metadata_raw = None
        if section_id is not None and instance_number is not None and field_index is not None:
            metadata_raw = get_possibly_chunked_form_value(
                request.form,
                f'repeat_{section_id}_{instance_number}_field_{field_index}_emergency_metadata',
                default=None,
            )
        elif form_item_id is not None:
            metadata_raw = get_possibly_chunked_form_value(
                request.form,
                f'field_disagg_metadata[{form_item_id}]',
                default=None,
            )

        if not metadata_raw or not str(metadata_raw).strip():
            return None

        try:
            metadata_raw = decode_b64_matrix_json(str(metadata_raw).strip())
        except MatrixJsonDecodeError:
            logger.error(
                "Emergency metadata could not be base64-decoded; falling back to display value"
            )
            return None

        try:
            payload = json.loads(metadata_raw)
        except (json.JSONDecodeError, TypeError):
            return None

        if not isinstance(payload, dict):
            return None

        name = str(payload.get('name') or '').strip()
        code = str(payload.get('code') or '').strip()
        if not name and not code:
            return None
        return {'name': name, 'code': code}

    @classmethod
    def _apply_emergency_operation_disagg(cls, entry, display_value, metadata=None):
        """Persist emergency operation name/code alongside the selected display value."""
        text = str(display_value or '').strip()
        if not text:
            return

        meta = metadata or cls._parse_emergency_metadata_from_display(text)
        if not meta:
            return

        name = str(meta.get('name') or '').strip()
        code = str(meta.get('code') or '').strip()
        if not name and not code:
            return

        entry.disagg_data = {'name': name, 'code': code}
        entry.disagg_type = 'emergency_operation'

    @classmethod
    def _format_emergency_operation_metadata_dict(cls, meta):
        """Format emergency-operation {name, code} metadata as the canonical display string."""
        if not isinstance(meta, dict):
            return None
        keys = set(meta.keys())
        if not keys or not keys.issubset({'name', 'code'}):
            return None
        name = str(meta.get('name') or '').strip()
        code = str(meta.get('code') or '').strip()
        if name == '[object Object]':
            name = ''
        if code == '[object Object]':
            code = ''
        if name and code:
            return f"{name} ({code})"
        return name or code or None

    @classmethod
    def _normalize_emergency_operation_value(cls, value, metadata=None):
        """Normalize emergency-operation values to a canonical display string."""
        if isinstance(value, dict):
            formatted = cls._format_emergency_operation_metadata_dict(value)
            if formatted:
                return formatted
        text = str(value or '').strip()
        if text:
            return text
        if metadata:
            return cls._format_emergency_operation_metadata_dict(metadata)
        return None

    @classmethod
    def _normalize_emergency_operation_from_entry(cls, entry):
        """Read an emergency-operation value from a stored entry in display form."""
        if not entry:
            return None
        if getattr(entry, 'disagg_type', None) == 'emergency_operation':
            display = str(getattr(entry, 'value', '') or '').strip()
            if display:
                return display
        meta = getattr(entry, 'disagg_data', None)
        if isinstance(meta, dict):
            formatted = cls._format_emergency_operation_metadata_dict(meta)
            if formatted:
                return formatted
        effective = entry.get_effective_value() if hasattr(entry, 'get_effective_value') else getattr(entry, 'value', None)
        return str(effective or '').strip() or None

    @classmethod
    def _emergency_operation_values_equal(cls, old_value, new_value, old_entry=None, new_metadata=None):
        """Compare emergency-operation values regardless of dict vs display-string storage."""
        if old_entry is not None:
            old_normalized = cls._normalize_emergency_operation_from_entry(old_entry)
        else:
            old_normalized = cls._normalize_emergency_operation_value(old_value)
        new_normalized = cls._normalize_emergency_operation_value(new_value, new_metadata)
        return old_normalized == new_normalized

    @classmethod
    def _field_supports_disaggregation(cls, field):
        """Check if field truly supports disaggregation (beyond just 'total')"""
        options = getattr(field, 'allowed_disaggregation_options', None) or []
        has_true_disagg = any(opt in ('sex', 'age', 'sex_age') for opt in options)
        return has_true_disagg or bool(getattr(field, 'indirect_reach', False))

    @classmethod
    def _process_repeat_disaggregation_indicator(cls, field, field_values, field_index):
        """Process repeat disaggregation indicator data"""
        cls._log_verbose(f"Processing repeat disaggregation indicator {field.id}")
        base = f'field_{field_index}'
        reporting_mode = field_values.get(f'{base}_reporting_mode', 'total')

        collected_values = {}
        has_any_value = False

        def parse_int(val_str, is_percentage=False):
            try:
                return float(val_str) if is_percentage else int(val_str)
            except (ValueError, TypeError):
                return None

        is_percentage = (getattr(field, 'type', '') == 'Percentage' or getattr(field, 'field_type_for_js', '').lower() == 'percentage')

        # total mode
        if reporting_mode == 'total':
            total_str = field_values.get(f'{base}_total_value', '')
            if total_str and str(total_str).strip():
                parsed = parse_int(total_str, is_percentage)
                if parsed is not None:
                    key = 'direct' if getattr(field, 'indirect_reach', False) else 'total'
                    collected_values[key] = parsed
                    has_any_value = True

        # sex mode
        elif reporting_mode == 'sex':
            sex_values = {}
            for sex_cat in getattr(field, 'effective_sex_categories', []):
                sex_slug = sex_cat.lower().replace(' ', '_').replace('-', '_')
                key = f'{base}_sex_{sex_slug}'
                val_str = field_values.get(key, '')
                if val_str and str(val_str).strip():
                    parsed = parse_int(val_str, is_percentage)
                    if parsed is not None:
                        sex_values[sex_slug] = parsed
            if sex_values:
                if getattr(field, 'indirect_reach', False):
                    collected_values['direct'] = sex_values
                else:
                    collected_values = sex_values
                has_any_value = True

        # age mode
        elif reporting_mode == 'age':
            age_values = {}
            for age_group in getattr(field, 'effective_age_groups', []):
                age_slug = FormItemProcessor.slugify_age_group(age_group)
                key = f'{base}_age_{age_slug}'
                val_str = field_values.get(key, '')
                if val_str and str(val_str).strip():
                    parsed = parse_int(val_str, is_percentage)
                    if parsed is not None:
                        age_values[age_slug] = parsed
            if age_values:
                if getattr(field, 'indirect_reach', False):
                    collected_values['direct'] = age_values
                else:
                    collected_values = age_values
                has_any_value = True

        # sex_age mode
        elif reporting_mode == 'sex_age':
            sex_age_values = {}
            for sex_cat in getattr(field, 'effective_sex_categories', []):
                sex_slug = sex_cat.lower().replace(' ', '_').replace('-', '_')
                for age_group in getattr(field, 'effective_age_groups', []):
                    age_slug = FormItemProcessor.slugify_age_group(age_group)
                    key = f'{base}_sexage_{sex_slug}_{age_slug}'
                    val_str = field_values.get(key, '')
                    if val_str and str(val_str).strip():
                        parsed = parse_int(val_str, is_percentage)
                        if parsed is not None:
                            sex_age_values[f'{sex_slug}_{age_slug}'] = parsed
            if sex_age_values:
                if getattr(field, 'indirect_reach', False):
                    collected_values['direct'] = sex_age_values
                else:
                    collected_values = sex_age_values
                has_any_value = True

        # optional indirect reach in repeat context
        if getattr(field, 'indirect_reach', False):
            ir_str = field_values.get(f'{base}_indirect_reach', '')
            if ir_str and str(ir_str).strip():
                with suppress((ValueError, TypeError)):
                    ir_val = int(ir_str)
                    if ir_val >= 0:
                        collected_values['indirect'] = ir_val
                        has_any_value = True

        if has_any_value:
            return { 'mode': reporting_mode, 'values': collected_values }

        return None
