"""Form data repeat group processing mixin."""

import json
from typing import Dict, List

from flask import request
from flask_login import current_user
from app.models import (
    db,
    DynamicIndicatorData,
    RepeatGroupData,
    RepeatGroupInstance,
)
from app.services.forms.processing_service import (
    FormItemProcessor,
    get_form_items_for_section,
    should_create_data_availability_entry as unified_should_create,
)
from app.services.forms.processors._common import get_english_field_name
from app.services.monitoring.debug import debug_manager, performance_monitor

logger = debug_manager.get_logger(__name__)


class RepeatGroupProcessorMixin:
    """Mixin providing repeat group processing for FormDataService."""

    @staticmethod
    def _format_repeat_entry_label_text(raw):
        if raw is None or raw == '':
            return None
        if isinstance(raw, list):
            text = ', '.join(str(v).strip() for v in raw if v not in (None, ''))
        else:
            text = str(raw).strip()
        if not text:
            return None
        return text[:255]

    @classmethod
    def _compute_repeat_instance_label(cls, section, instance_data, all_fields, instance_number):
        item_id = section.entry_label_item_id
        if not item_id:
            return None
        for field_index, field in enumerate(all_fields):
            if getattr(field, 'id', None) != item_id:
                continue
            raw = instance_data.get(f'field_{field_index}')
            if raw in (None, ''):
                for key, value in instance_data.items():
                    if key == f'field_{field_index}' or key.startswith(f'field_{field_index}_'):
                        raw = value
                        break
            return cls._format_repeat_entry_label_text(raw)
        return None

    @classmethod
    @performance_monitor("Repeat Groups Processing", quiet=True)
    def _process_repeat_groups(cls, section, assignment_entity_status, validation_errors: List) -> List[Dict]:
        """Process repeat groups with JavaScript compatibility"""
        field_changes = []

        # Get all form items for this section using the unified approach
        all_fields = get_form_items_for_section(section, assignment_entity_status)

        # Parse repeat data from form - use comprehensive approach from original
        repeat_data = {}
        processed_fields = set()

        for field_name in request.form.keys():
            if field_name.startswith(f'repeat_{section.id}_') and field_name not in processed_fields:
                parts = field_name.split('_')
                if len(parts) >= 4 and parts[3] == 'field':
                    section_id = int(parts[1])
                    instance_number = int(parts[2])

                    if len(parts) >= 5:
                        field_index = int(parts[4])

                        # Get all values for this field name (handles both single and multi-choice)
                        field_values = request.form.getlist(field_name)

                        if len(parts) >= 6:
                            input_index = '_'.join(parts[5:])
                            if input_index == 'emergency_metadata':
                                # Emergency-metadata hidden inputs are sidebar artifacts appended to
                                # the <form> element itself (not inside the repeat entry).  They
                                # survive when the entry is deleted from the DOM.  Skip them here
                                # and â€“ critically â€“ do NOT register the instance in repeat_data,
                                # so the orphan-removal step below can correctly delete entries
                                # that were removed from the UI.
                                processed_fields.add(field_name)
                                continue
                            field_key = f'field_{field_index}_{input_index}'
                        else:
                            field_key = f'field_{field_index}'

                        # Register the instance only after we have confirmed this is a real
                        # data field (not a metadata-only artifact like emergency_metadata).
                        if instance_number not in repeat_data:
                            repeat_data[instance_number] = {}

                        # Check if this is a multi-choice field
                        base_field = '_'.join(parts[:5])
                        is_multi_choice = len(field_values) > 1

                        if is_multi_choice:
                            repeat_data[instance_number][field_key] = field_values
                        else:
                            repeat_data[instance_number][field_key] = field_values[0] if field_values else ''

                        processed_fields.add(field_name)

        cls._log_verbose(f"Parsed repeat data: {repeat_data}")

        # Process each repeat instance
        for instance_number, instance_data in repeat_data.items():
            cls._log_verbose(f"Processing repeat instance {instance_number} with data: {instance_data}")

            # Create or get repeat group instance using helper methods
            if cls._is_public_submission(assignment_entity_status):
                repeat_instance = RepeatGroupInstance.query.filter_by(
                    public_submission_id=assignment_entity_status.id,
                    section_id=section.id,
                    instance_number=instance_number
                ).first()

                if not repeat_instance:
                    repeat_instance = RepeatGroupInstance(
                        public_submission_id=assignment_entity_status.id,
                        section_id=section.id,
                        instance_number=instance_number,
                        created_by_user_id=1,  # Public submissions use user_id=1
                        is_hidden=False
                    )
                    db.session.add(repeat_instance)
                    db.session.flush()  # Get the ID
                    logger.info(f"Created new repeat instance {repeat_instance.id}")
                else:
                    logger.info(f"Found existing repeat instance {repeat_instance.id}")
            else:
                repeat_instance = RepeatGroupInstance.query.filter_by(
                    assignment_entity_status_id=assignment_entity_status.id,
                    section_id=section.id,
                    instance_number=instance_number
                ).first()

                if not repeat_instance:
                    repeat_instance = RepeatGroupInstance(
                        assignment_entity_status_id=assignment_entity_status.id,
                        section_id=section.id,
                        instance_number=instance_number,
                        created_by_user_id=current_user.id,
                        is_hidden=False
                    )
                    db.session.add(repeat_instance)
                    db.session.flush()  # Get the ID
                    cls._log_verbose(f"Created new repeat instance {repeat_instance.id}")
                else:
                    cls._log_verbose(f"Found existing repeat instance {repeat_instance.id}")

            repeat_instance.instance_label = cls._compute_repeat_instance_label(
                section, instance_data, all_fields, instance_number
            )

            # Process each field in this instance using comprehensive field processing
            for field_index, field in enumerate(all_fields):
                cls._log_verbose(f"Checking field {field_index} ({field.label})")

                # Look for any field keys that start with this field index
                # Also handle variations like field_0_ and field_0 (without underscore)
                matching_keys = []

                # Pattern 1: field_{index}_ (with underscore)
                pattern_with_underscore = f'field_{field_index}_'
                matching_keys.extend([key for key in instance_data.keys() if key.startswith(pattern_with_underscore)])

                # Pattern 2: field_{index} (exact match, for base field key)
                base_field_key = f'field_{field_index}'
                if base_field_key in instance_data:
                    if base_field_key not in matching_keys:
                        matching_keys.append(base_field_key)

                # Pattern 3: Check if this is a field without underscore but with data (edge case)
                for key in instance_data.keys():
                    if key == f'field_{field_index}' or (key.startswith(f'field_{field_index}') and not key.startswith(f'field_{field_index}_')):
                        if key not in matching_keys:
                            matching_keys.append(key)

                cls._log_verbose(f"Found matching keys for field {field_index}: {matching_keys}")
                cls._log_verbose(f"Available keys in instance_data: {list(instance_data.keys())}")

                matching_keys = [key for key in matching_keys if not key.endswith('_emergency_metadata')]

                if matching_keys:
                    # Use comprehensive field processing like the original
                    field_values = {}
                    for key in matching_keys:
                        field_values[key] = instance_data[key]

                    # Also add the base field key if it exists
                    base_field_key = f'field_{field_index}'
                    if base_field_key in instance_data:
                        field_values[base_field_key] = instance_data[base_field_key]

                    cls._log_verbose(f"Processing field {field_index} ({field.label}) with field_values: {field_values}")

                    # Process the field data using comprehensive processing
                    processed_value, data_not_available, not_applicable, has_meaningful_data = cls._process_repeat_field_data_comprehensive(
                        field, field_values, field_index, instance_number
                    )

                    cls._log_verbose(f"Processed value: {processed_value}, has_meaningful_data: {has_meaningful_data}")

                    if has_meaningful_data:
                        emergency_metadata = None
                        if cls._is_emergency_operations_choice(field):
                            emergency_metadata = cls._get_emergency_metadata_from_request(
                                section_id=section.id,
                                instance_number=instance_number,
                                field_index=field_index,
                            )

                        # Create or update repeat group data entry
                        existing_entry = RepeatGroupData.query.filter_by(
                            repeat_instance_id=repeat_instance.id,
                            form_item_id=field.id
                        ).first()

                        # Track old value before updating
                        old_value = None
                        old_data_not_available = False
                        old_not_applicable = False
                        change_type = 'added'

                        if existing_entry:
                            # Track old values before updating - handle both simple values and disaggregated data
                            if cls._is_emergency_operations_choice(field):
                                old_value = cls._normalize_emergency_operation_from_entry(existing_entry)
                            elif existing_entry.disagg_type == 'emergency_operation' and existing_entry.value:
                                old_value = existing_entry.value
                            elif existing_entry.disagg_data:
                                old_value = existing_entry.disagg_data
                            else:
                                old_value = existing_entry.get_effective_value()
                            old_data_not_available = existing_entry.data_not_available or False
                            old_not_applicable = existing_entry.not_applicable or False
                            change_type = 'updated'

                            # Update existing entry
                            cls._store_repeat_data_entry(
                                existing_entry,
                                processed_value,
                                data_not_available,
                                not_applicable,
                                field,
                                emergency_metadata=emergency_metadata,
                            )
                            cls._log_verbose(f"Updated existing repeat data entry for field {field.id}: value={existing_entry.value}, disagg_data={existing_entry.disagg_data}")
                        else:
                            # Create new entry
                            new_entry = RepeatGroupData(
                                repeat_instance_id=repeat_instance.id,
                                form_item_id=field.id
                            )
                            cls._store_repeat_data_entry(
                                new_entry,
                                processed_value,
                                data_not_available,
                                not_applicable,
                                field,
                                emergency_metadata=emergency_metadata,
                            )
                            db.session.add(new_entry)
                            cls._log_verbose(f"Created new repeat data entry for field {field.id}: value={new_entry.value}, disagg_data={new_entry.disagg_data}")

                        # Record the change if value actually changed
                        # Compare values properly - handle dict comparison for disaggregated data
                        values_changed = False
                        if cls._is_emergency_operations_choice(field):
                            values_changed = not cls._emergency_operation_values_equal(
                                old_value,
                                processed_value,
                                old_entry=existing_entry,
                                new_metadata=emergency_metadata,
                            )
                            activity_old_value = old_value
                            activity_new_value = cls._normalize_emergency_operation_value(
                                processed_value, emergency_metadata
                            )
                        elif isinstance(old_value, dict) and isinstance(processed_value, dict):
                            # Compare dictionaries
                            values_changed = json.dumps(old_value, sort_keys=True) != json.dumps(processed_value, sort_keys=True)
                            activity_old_value = old_value
                            activity_new_value = processed_value
                        else:
                            values_changed = old_value != processed_value
                            activity_old_value = old_value
                            activity_new_value = processed_value

                        if (values_changed or
                            old_data_not_available != data_not_available or
                            old_not_applicable != not_applicable):
                            # Include instance number in field name for repeat groups
                            base_field_name = get_english_field_name(field)
                            field_name_with_instance = f"{base_field_name} (Entry {instance_number})"

                            field_changes.append({
                                'type': change_type,
                                'form_item_id': field.id,
                                'field_name': field_name_with_instance,
                                'old_value': activity_old_value,
                                'new_value': activity_new_value,
                                'old_data_not_available': old_data_not_available,
                                'new_data_not_available': data_not_available or False,
                                'old_not_applicable': old_not_applicable,
                                'new_not_applicable': not_applicable or False,
                                'repeat_instance_number': instance_number  # Store separately for potential future use
                            })
                    else:
                        existing_entry = RepeatGroupData.query.filter_by(
                            repeat_instance_id=repeat_instance.id,
                            form_item_id=field.id
                        ).first()
                        if existing_entry:
                            old_value = existing_entry.get_effective_value()
                            if existing_entry.disagg_type == 'emergency_operation' and existing_entry.value:
                                old_value = existing_entry.value
                            db.session.delete(existing_entry)
                            base_field_name = get_english_field_name(field)
                            field_name_with_instance = f"{base_field_name} (Entry {instance_number})"
                            field_changes.append({
                                'type': 'removed',
                                'form_item_id': field.id,
                                'field_name': field_name_with_instance,
                                'old_value': old_value,
                                'new_value': None,
                                'old_data_not_available': existing_entry.data_not_available or False,
                                'new_data_not_available': False,
                                'old_not_applicable': existing_entry.not_applicable or False,
                                'new_not_applicable': False,
                                'repeat_instance_number': instance_number,
                            })
                else:
                    cls._log_verbose(f"No matching keys found for field {field_index}")

        submitted_instance_numbers = set(repeat_data.keys())
        if cls._is_public_submission(assignment_entity_status):
            existing_instances = RepeatGroupInstance.query.filter_by(
                public_submission_id=assignment_entity_status.id,
                section_id=section.id,
            ).all()
        else:
            existing_instances = RepeatGroupInstance.query.filter_by(
                assignment_entity_status_id=assignment_entity_status.id,
                section_id=section.id,
            ).all()

        for existing_instance in existing_instances:
            if existing_instance.instance_number not in submitted_instance_numbers:
                cls._log_verbose(
                    f"Removing orphan repeat instance {existing_instance.id} "
                    f"(instance_number={existing_instance.instance_number})"
                )
                cls._delete_repeat_instance_dynamic_indicators(
                    section, assignment_entity_status, existing_instance.instance_number
                )
                db.session.delete(existing_instance)

        cls._log_verbose(f"Repeat group processing completed with {len(field_changes)} field changes")
        return field_changes

    @classmethod
    def _delete_repeat_instance_dynamic_indicators(cls, repeat_section, assignment_entity_status, instance_number) -> None:
        """Delete dynamic indicators scoped to a removed repeat entry."""
        try:
            subsection_ids = [
                sub.id for sub in repeat_section.sub_sections
                if getattr(sub, 'section_type', None) == 'dynamic_indicators'
            ]
        except Exception:
            subsection_ids = []

        if not subsection_ids:
            return

        if cls._is_public_submission(assignment_entity_status):
            dynamic_rows = DynamicIndicatorData.query.filter(
                DynamicIndicatorData.public_submission_id == assignment_entity_status.id,
                DynamicIndicatorData.section_id.in_(subsection_ids),
                DynamicIndicatorData.repeat_instance_number == instance_number,
            ).all()
        else:
            dynamic_rows = DynamicIndicatorData.query.filter(
                DynamicIndicatorData.assignment_entity_status_id == assignment_entity_status.id,
                DynamicIndicatorData.section_id.in_(subsection_ids),
                DynamicIndicatorData.repeat_instance_number == instance_number,
            ).all()

        for dynamic_row in dynamic_rows:
            db.session.delete(dynamic_row)
            logger.info(
                "Deleted dynamic indicator %s for orphan repeat instance %s in repeat section %s",
                dynamic_row.id,
                instance_number,
                repeat_section.id,
            )

    @classmethod
    def _is_numeric_field(cls, field):
        """Check if field is numeric-like"""
        try:
            field_type_for_js = getattr(field, 'field_type_for_js', '').lower()
        except (AttributeError, TypeError):
            field_type_for_js = ''

        return (field_type_for_js in ['number', 'percentage', 'currency'] or
                getattr(field, 'type', '') in ['Number', 'Percentage', 'Currency'])

    @classmethod
    def _find_field_value(cls, field_values, field_index, suffixes):
        """Find field value using multiple naming patterns"""
        # Build possible keys from suffixes
        possible_keys = [f'field_{field_index}_{suffix}' for suffix in suffixes]
        possible_keys.append(f'field_{field_index}')  # Add base pattern

        # Also check for any key that starts with field_{field_index} and might contain a value
        additional_keys = [key for key in field_values.keys()
                         if key.startswith(f'field_{field_index}')
                         and key not in possible_keys
                         and not key.endswith('_data_not_available')
                         and not key.endswith('_not_applicable')
                         and not key.endswith('_reporting_mode')
                         and not key.endswith('_emergency_metadata')
                         and not key.endswith('_other_text')]
        possible_keys.extend(additional_keys)

        for key in possible_keys:
            if key in field_values:
                val_str = field_values[key]
                if val_str and str(val_str).strip():
                    return val_str

        return None

    @classmethod
    def _process_numeric_value(cls, val_str, field):
        """Process numeric value based on field type"""
        try:
            field_type_for_js = getattr(field, 'field_type_for_js', '').lower()
            # Currency and number can have decimals; store as normalized string
            if field.type == 'Percentage' or field_type_for_js == 'percentage':
                return str(float(val_str))
            elif field_type_for_js in ['currency', 'number'] or getattr(field, 'type', '') in ['Currency', 'Number']:
                # Allow decimals for currency/number
                return str(float(val_str))
            else:
                return str(int(val_str))
        except ValueError:
            logger.warning(f"Invalid numeric value for {field.label}: {val_str}")
            return str(val_str) if val_str else None

    @classmethod
    def _process_repeat_field_data_comprehensive(cls, field, field_values, field_index, instance_number):
        """Process repeat field data with comprehensive handling like the original"""
        data_not_available = False
        not_applicable = False
        has_meaningful_data = False
        final_value_to_store = None

        # Check for data availability flags first
        data_not_available = field_values.get(f'field_{field_index}_data_not_available') == '1'
        not_applicable = field_values.get(f'field_{field_index}_not_applicable') == '1'

        # Handle different field types
        if field.is_indicator:
            final_value_to_store = cls._process_repeat_indicator_data_comprehensive(field, field_values, field_index)
        elif field.is_question:
            final_value_to_store = cls._process_repeat_question_data_comprehensive(field, field_values, field_index)
        elif field.is_document_field:
            final_value_to_store = cls._process_repeat_document_data_comprehensive(field, field_values, field_index)
        elif field.item_type == 'matrix':
            final_value_to_store = cls._process_repeat_matrix_data_comprehensive(field, field_values, field_index)
        else:
            # Unknown field type - try to find any value
            final_value_to_store = None

        # Determine if we have meaningful data
        has_meaningful_data = unified_should_create(final_value_to_store, data_not_available, not_applicable)

        cls._log_verbose(f"Comprehensive processing result - value: {final_value_to_store}, has_meaningful_data: {has_meaningful_data}")

        return final_value_to_store, data_not_available, not_applicable, has_meaningful_data

    @classmethod
    def _process_repeat_indicator_data_comprehensive(cls, field, field_values, field_index):
        """Process repeat indicator data with comprehensive handling"""
        logger.info(f"Processing repeat indicator {field.id} with field_values: {field_values}")

        # Check if this indicator truly supports disaggregation (beyond just 'total')
        supports_disaggregation = cls._field_supports_disaggregation(field)
        is_numeric_like = cls._is_numeric_field(field)

        if supports_disaggregation and is_numeric_like:
            return cls._process_repeat_disaggregation_indicator(field, field_values, field_index)

        # Handle numeric indicators WITHOUT disaggregation
        if is_numeric_like and not supports_disaggregation:
            val_str = cls._find_field_value(field_values, field_index, ['total_value', '0', 'standard_value'])
            if val_str:
                cls._log_verbose(f"Found numeric value '{val_str}' for non-disaggregated indicator {field.id}")
                return cls._process_numeric_value(val_str, field)

            cls._log_verbose(f"No numeric value found for non-disaggregated indicator {field.id}")
            return None

        # Handle text/other types - look for any non-empty value
        val_str = None

        # Special debugging for yes/no indicators
        if (hasattr(field, 'type') and
            field.type == 'yesno'):
            cls._log_verbose(f"PROCESSING YES/NO INDICATOR: field {field.id}, field_values keys: {list(field_values.keys())}")
            # Look specifically for standard_value key
            standard_value_key = f'field_{field_index}_standard_value'
            if standard_value_key in field_values:
                val_str = field_values[standard_value_key]
                cls._log_verbose(f"Found yes/no indicator value: '{val_str}' for field {field.id}")

        # Check for any key that might contain the actual value (prioritize standard_value for yes/no)
        if val_str is None:
            # First, check for standard_value (yes/no fields)
            standard_value_key = f'field_{field_index}_standard_value'
            if standard_value_key in field_values and field_values[standard_value_key]:
                val_str = field_values[standard_value_key]
                logger.info(f"Found standard value '{val_str}' for field {field.id}")
            else:
                # Then check other keys
                for key, value in field_values.items():
                    if key.startswith(f'field_{field_index}_') and value and str(value).strip():
                        # Skip reporting mode and other non-value fields
                        if not key.endswith('_reporting_mode') and not key.endswith('_data_not_available') and not key.endswith('_not_applicable'):
                            val_str = value
                            logger.info(f"Found text value '{val_str}' in key '{key}' for field {field.id}")
                            break

        if val_str and val_str.strip():
            return val_str

        return None

    @classmethod
    def _process_repeat_question_data_comprehensive(cls, field, field_values, field_index):
        """Process repeat question data with comprehensive handling"""
        cls._log_verbose(f"Processing repeat question {field.id} ({field.question_type}) with field_values: {field_values}")

        # Use optimized field value lookup
        question_type = field.question_type.value if field.question_type else None

        if question_type == 'yesno':
            # For yes/no questions, prioritize standard_value
            raw_value = cls._find_field_value(field_values, field_index, ['standard_value', '0'])
        else:
            # For other questions, try various patterns
            raw_value = cls._find_field_value(field_values, field_index, ['0', 'standard_value'])

        if raw_value is not None:
            return cls._process_question_value_by_type(raw_value, question_type, field, field_values, field_index)

        return None

    @classmethod
    def _process_question_value_by_type(cls, raw_value, question_type, field, field_values, field_index):
        """Process question value based on its type"""
        if isinstance(raw_value, str) and raw_value.strip() == '':
            return None

        if question_type == 'number':
            return cls._process_numeric_value(raw_value, field)
        elif question_type == 'percentage':
            return cls._process_numeric_value(raw_value, field)
        elif question_type == 'multiple_choice':
            return cls._process_multiple_choice_value(raw_value, field_values, field_index)
        elif question_type == 'single_choice':
            single_val = str(raw_value).strip() if raw_value else None
            if single_val == '__other__':
                other_text = field_values.get(f'field_{field_index}_other_text')
                if isinstance(other_text, list):
                    other_text = other_text[0] if other_text else ''
                return str(other_text).strip() if other_text else None
            return single_val
        elif question_type == 'yesno':
            return 'true' if raw_value else 'false'
        else:
            return str(raw_value).strip() if isinstance(raw_value, str) and str(raw_value).strip() else str(raw_value) if raw_value else None

    @classmethod
    def _process_multiple_choice_value(cls, raw_value, field_values, field_index):
        """Process multiple choice question values"""
        selected_options = []

        # Check if we already have an array of values from multi-choice field processing
        if f'field_{field_index}' in field_values:
            value = field_values[f'field_{field_index}']
            if isinstance(value, list):
                selected_options = value
                cls._log_verbose(f"Using pre-collected multi-choice values: {selected_options}")
            else:
                selected_options = [value] if value else []
                cls._log_verbose(f"Converting single value to multi-choice: {selected_options}")
        else:
            # Fallback: collect all values for this field
            for key, value in field_values.items():
                if (key.startswith(f'field_{field_index}')
                        and not key.endswith('_data_not_available')
                        and not key.endswith('_not_applicable')
                        and not key.endswith('_other_text')):
                    selected_options.append(value)
            cls._log_verbose(f"Fallback multi-choice collection: {selected_options}")

        other_text_key = f'field_{field_index}_other_text'
        if other_text_key in field_values:
            other_text = field_values[other_text_key]
            if isinstance(other_text, list):
                other_text = other_text[0] if other_text else ''
            other_text = str(other_text).strip() if other_text else ''
            selected_options = [v for v in selected_options if v != '__other__']
            if other_text and other_text not in selected_options:
                selected_options.append(other_text)

        return json.dumps(selected_options) if selected_options else None

    @classmethod
    def _store_repeat_data_entry(cls, entry, processed_value, data_not_available, not_applicable, field=None, emergency_metadata=None):
        """Store data in a repeat group data entry using appropriate method"""
        # Get field - use provided field or try to load from entry
        if not field:
            if entry.form_item:
                field = entry.form_item
            else:
                # Try to load it if not already loaded
                from app.models.forms import FormItem
                field = db.session.get(FormItem, entry.form_item_id)

        # Check if this is a matrix field - matrix data is stored in disagg_data
        is_matrix_field = field and str(field.item_type).lower() == 'matrix'

        cls._log_verbose(f"Storing repeat data entry for field {entry.form_item_id}: is_matrix={is_matrix_field}, item_type={field.item_type if field else 'None'}, processed_value_type={type(processed_value)}, is_dict={isinstance(processed_value, dict)}, has_mode={isinstance(processed_value, dict) and 'mode' in processed_value if isinstance(processed_value, dict) else False}, processed_value_keys={list(processed_value.keys()) if isinstance(processed_value, dict) else 'N/A'}")

        # Check for disaggregated data first (has 'mode' and 'values' keys)
        if isinstance(processed_value, dict) and 'mode' in processed_value and 'values' in processed_value:
            # This is disaggregated data
            mode = processed_value['mode']
            values = processed_value['values']
            entry.set_disaggregated_data(mode, values)
            cls._log_verbose(f"Stored disaggregated data: mode={mode}")
        elif is_matrix_field and isinstance(processed_value, dict):
            # Matrix data - store in disagg_data, leave value as None
            # IMPORTANT: Do NOT call set_simple_value for matrix data as it clears disagg_data
            entry.value = None
            entry.numeric_value = None
            entry.disagg_data = processed_value
            entry.disagg_type = 'matrix'
            # Explicitly ensure data_not_available and not_applicable are set AFTER setting disagg_data
            # (they will be set at the end, but being explicit here)
            cls._log_verbose(f"Stored matrix data in disagg_data for field {entry.form_item_id}: keys={list(processed_value.keys())}, sample_data={dict(list(processed_value.items())[:3])}")
        elif isinstance(processed_value, dict) and not is_matrix_field:
            # Non-matrix dict data - might be JSON string that was parsed
            # Convert to string for storage
            import json
            entry.value = json.dumps(processed_value) if processed_value else None
            entry.disagg_data = db.null()
            entry._sync_numeric_value_from_string()
            entry.disagg_type = 'simple' if entry.value is not None else None
            cls._log_verbose(f"Stored non-matrix dict as JSON string: {entry.value}")
        else:
            # Simple value - but check if it's a matrix field first to avoid overwriting
            if is_matrix_field:
                # Matrix field but value is not a dict - might be empty/None
                entry.value = None
                entry.disagg_data = db.null()
                entry.disagg_type = None
                cls._log_verbose(f"Matrix field with non-dict value (empty matrix): {processed_value}")
            else:
                # Simple value
                entry.set_simple_value(processed_value)
                if field and cls._is_emergency_operations_choice(field) and processed_value:
                    cls._apply_emergency_operation_disagg(
                        entry,
                        processed_value,
                        emergency_metadata,
                    )
                cls._log_verbose(f"Stored simple value: {processed_value}")

        # Set data availability flags for all field types
        if data_not_available or not_applicable:
            entry.set_data_availability(data_not_available, not_applicable)
        else:
            entry.data_not_available = False
            entry.not_applicable = False

    @classmethod
    def _process_repeat_document_data_comprehensive(cls, field, field_values, field_index):
        """Process repeat document data with comprehensive handling"""
        cls._log_verbose(f"Processing repeat document {field.id} with field_values: {field_values}")

        # For documents, we typically just need to check if a file was uploaded
        # This would be handled by the file upload processing, not the repeat group processing
        return None

    @classmethod
    def _process_repeat_matrix_data_comprehensive(cls, field, field_values, field_index):
        """Process repeat matrix data with comprehensive handling"""
        import json

        cls._log_verbose(f"Processing repeat matrix {field.id} with field_values: {field_values}")

        # Matrix data is stored in the hidden field: field_{field_index}_1
        # The first input (index 0) is the search input, the second (index 1) is the hidden field
        matrix_data_key = f'field_{field_index}_1'
        matrix_data_json = field_values.get(matrix_data_key, '')

        cls._log_verbose(f"Matrix data key: {matrix_data_key}, value: {matrix_data_json}")

        # Parse matrix data
        matrix_data = {}
        if matrix_data_json:
            try:
                matrix_data = json.loads(matrix_data_json)
                cls._log_verbose(f"Parsed matrix data for field {field.id}: {matrix_data}")
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Invalid matrix data for field {field.id}: {matrix_data_json} - {e}")
                matrix_data = {}

        # Return the matrix data dict (will be stored in disagg_data)
        # Return None if empty to indicate no data
        return matrix_data if matrix_data else None
