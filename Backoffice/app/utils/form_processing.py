# ========== Form Processing Utilities ==========
"""
Unified form processing utilities for handling form items, data processing, and validation.
Provides consistent processing across all form types (indicators, questions, documents).
"""

from flask import request, session, current_app
from app import get_locale
from app.models import FormData, FormItem, Config, FormSection, DynamicIndicatorData
from app.utils.form_localization import get_localized_indicator_name
import json
import re
from typing import Dict, List, Tuple, Any, Optional
import logging
from contextlib import suppress

# Set up logging
forms_logger = logging.getLogger('forms')


def slugify_age_group(age_group_str) -> str:
    """
    Convert age group string to a URL-safe slug for form field names.

    Canonical implementation used across forms, public routes, and services.
    Examples: "0-5 years" -> "0_5_years", "18+" -> "18_", "" -> "".

    :param age_group_str: Age group string (e.g. "0-5 years", "18+")
    :return: Slug (alphanumeric + underscore only, lowercased)
    """
    if age_group_str is None:
        return ''
    s = str(age_group_str).strip()
    if not s:
        return ''
    return re.sub(r'[^a-zA-Z0-9_]', '_', s.lower())


class FormItemProcessor:
    """
    Unified processor for all form item types (indicators, questions, documents).
    Handles disaggregation, indirect reach, and data availability consistently.
    """

    # JavaScript-compatible field naming patterns
    FIELD_PATTERNS = {
        'indicator': {
            'total_value': 'indicator_{item_id}_total_value',
            'standard_value': 'indicator_{item_id}_standard_value',
            'reporting_mode': 'indicator_{item_id}_reporting_mode',
            'data_not_available': 'indicator_{item_id}_data_not_available',
            'not_applicable': 'indicator_{item_id}_not_applicable',
            'indirect_reach': 'indicator_{item_id}_indirect_reach',
            'sex_pattern': 'indicator_{item_id}_sex_{sex_slug}',
            'age_pattern': 'indicator_{item_id}_age_{age_slug}',
            'sexage_pattern': 'indicator_{item_id}_sexage_{sex_slug}_{age_slug}'
        },
        'question': {
            'field_value': 'field_value[{item_id}]',
            'data_not_available': 'question_{item_id}_data_not_available',
            'not_applicable': 'question_{item_id}_not_applicable',
            'indirect_reach': 'question_{item_id}_indirect_reach'
        },
        'document': {
            'field_value': 'field_value[{item_id}]'
        }
    }

    @classmethod
    def setup_form_item_for_template(cls, form_item: FormItem, assignment_entity_status) -> FormItem:
        """
        Set up any form item (indicator, question, document) with all properties needed for template rendering.
        This replaces the separate setup logic for each item type.
        """
        # Add common JavaScript-compatible properties
        cls._add_common_properties(form_item)

        # Add type-specific properties
        if form_item.is_indicator:
            cls._setup_indicator_properties(form_item)
        elif form_item.is_question:
            cls._setup_question_properties(form_item)
        elif form_item.is_document_field:
            cls._setup_document_properties(form_item)
        elif form_item.is_matrix:
            cls._setup_matrix_properties(form_item)
        elif form_item.item_type and form_item.item_type.startswith('plugin_'):
            cls._setup_plugin_properties(form_item)

        # Add translation support
        cls._add_translation_support(form_item)

        # Add disaggregation support (for both indicators and questions)
        cls._add_disaggregation_support(form_item)

        return form_item

    @classmethod
    def _add_common_properties(cls, form_item: FormItem):
        """Add properties common to all form item types"""
        # Parse JSON conditions safely
        try:
            form_item.conditions = json.loads(form_item.relevance_condition) if form_item.relevance_condition and form_item.relevance_condition.strip() else []
        except json.JSONDecodeError:
            form_item.conditions = []
            current_app.logger.error(f"Invalid JSON in relevance_condition for FormItem ID {form_item.id}: {form_item.relevance_condition}")

        try:
            form_item.validations_from_db = json.loads(form_item.validation_condition) if form_item.validation_condition and form_item.validation_condition.strip() else []
        except json.JSONDecodeError:
            form_item.validations_from_db = []
            current_app.logger.error(f"Invalid JSON in validation_condition for FormItem ID {form_item.id}: {form_item.validation_condition}")

        # JavaScript-compatible properties
        form_item.is_required_for_js = form_item.is_required

        # Layout properties with defaults
        form_item.layout_column_width = getattr(form_item, 'layout_column_width', 12)
        form_item.layout_break_after = getattr(form_item, 'layout_break_after', False)

        # Legacy compatibility properties
        form_item.is_sub_indicator = form_item.is_sub_item if form_item.is_indicator else False
        form_item.is_sub_question = form_item.is_sub_item if form_item.is_question else False
        form_item.is_sub_document = form_item.is_sub_item if form_item.is_document_field else False

    @classmethod
    def _setup_indicator_properties(cls, form_item: FormItem):
        """Set up indicator-specific properties"""
        form_item.source_indicator_from_bank = form_item.indicator_bank

        # Priority: Custom label > Indicator bank name (localized).
        # Determine whether the saved label is truly a custom override or merely equal to the bank's name.
        def _norm(s: str) -> str:
            return ' '.join(str(s or '').strip().split()).lower()

        has_non_empty_label = bool(form_item.label and str(form_item.label).strip())
        has_custom_translations = bool(getattr(form_item, 'label_translations', None))

        is_custom_label = False
        if has_non_empty_label:
            if form_item.indicator_bank:
                # Build comparison set from bank's canonical name and known translations (if available)
                bank_candidates = set()
                with suppress(Exception):
                    if getattr(form_item.indicator_bank, 'name', None):
                        bank_candidates.add(form_item.indicator_bank.name)
                with suppress(Exception):
                    bank_name_translations = getattr(form_item.indicator_bank, 'name_translations', None)
                    # name_translations can be a dict or a JSON string; normalize to dict if possible
                    if isinstance(bank_name_translations, str):
                        try:
                            bank_name_translations = json.loads(bank_name_translations)
                        except Exception as e:
                            forms_logger.debug("json.loads bank_name_translations failed: %s", e)
                            bank_name_translations = None
                    if isinstance(bank_name_translations, dict):
                        for _val in bank_name_translations.values():
                            if isinstance(_val, str) and _val.strip():
                                bank_candidates.add(_val)

                # If label matches any bank candidate (case/whitespace-insensitive), treat as NOT custom
                label_matches_bank = any(_norm(form_item.label) == _norm(candidate) for candidate in bank_candidates if candidate)
                is_custom_label = not label_matches_bank
            else:
                # No bank to compare against; any non-empty label is considered custom
                is_custom_label = True

            # If custom translations exist, this is explicitly a custom label
            if has_custom_translations:
                is_custom_label = True

        # Expose a flag for templates/other code paths if needed
        form_item.has_custom_label = bool(is_custom_label)

        if is_custom_label:
            form_item.display_label = form_item.label
        elif form_item.indicator_bank:
            # Fall back to localized indicator bank name when not custom
            from app.utils.form_localization import get_localized_indicator_name
            form_item.display_label = get_localized_indicator_name(form_item.indicator_bank)
        else:
            form_item.display_label = form_item.label or ''

    @classmethod
    def _setup_question_properties(cls, form_item: FormItem):
        """Set up question-specific properties"""
        form_item.display_label = form_item.label

        # Ensure display_options is set
        if not hasattr(form_item, 'display_options') or form_item.display_options is None:
            form_item.display_options = form_item.options

    @classmethod
    def _setup_document_properties(cls, form_item: FormItem):
        """Set up document field-specific properties"""
        form_item.display_label = form_item.label
        # Note: options property is computed from options_json and automatically returns [] for document fields

    @classmethod
    def _setup_matrix_properties(cls, form_item: FormItem):
        """Set up matrix field-specific properties"""
        form_item.display_label = form_item.label

    @classmethod
    def _setup_plugin_properties(cls, form_item: FormItem):
        """Set up plugin-specific properties"""
        form_item.display_label = form_item.label

        # Add plugin-specific properties
        if form_item.item_type.startswith('plugin_'):
            plugin_type = form_item.item_type.replace('plugin_', '')
            form_item.plugin_type = plugin_type

            # Parse plugin config if available
            if hasattr(form_item, 'config') and form_item.config:
                try:
                    if isinstance(form_item.config, str):
                        form_item.plugin_config = json.loads(form_item.config)
                    else:
                        form_item.plugin_config = form_item.config
                except json.JSONDecodeError:
                    form_item.plugin_config = {}
                    current_app.logger.warning(f"Invalid plugin config JSON for {form_item.item_type}")
            else:
                form_item.plugin_config = {}

    @classmethod
    def _add_translation_support(cls, form_item: FormItem):
        """Add translation support for form items"""
        from app.utils.form_localization import get_translation_key
        from app import get_locale

        translation_key = get_translation_key()  # ISO (e.g., 'fr')
        locale_code = (get_locale() or 'en')
        if isinstance(locale_code, str) and '_' in locale_code:
            locale_code = locale_code.split('_', 1)[0]

        def _parse_translations_map(raw_map):
            if not raw_map:
                return {}
            if isinstance(raw_map, dict):
                return raw_map
            try:
                return json.loads(raw_map) if isinstance(raw_map, str) else {}
            except Exception as e:
                forms_logger.debug("_parse_translations_map json.loads failed: %s", e)
                return {}

        def _first_translation(translations_map, preferred_keys):
            if not translations_map:
                return None
            for k in preferred_keys:
                if not k:
                    continue
                # try exact, then lower, then upper
                for kk in (k, str(k).lower(), str(k).upper()):
                    val = translations_map.get(kk)
                    if isinstance(val, str) and val.strip():
                        return val
            return None

        # Order of keys to try for label/definition translations
        preferred_keys = [
            locale_code,       # e.g. 'fr'
            translation_key,   # e.g. 'fr' (same as above, harmless)
            'en', 'EN'
        ]

        # Add translation support for indicators
        if form_item.is_indicator:
            # Apply custom label translation if available
            if form_item.label_translations:
                translations_map = _parse_translations_map(form_item.label_translations)
                translated_label = _first_translation(translations_map, preferred_keys)
                if translated_label and translated_label.strip():
                    form_item.display_label = translated_label

            # Apply custom definition translation if available
            if form_item.definition_translations:
                definitions_map = _parse_translations_map(form_item.definition_translations)
                translated_definition = _first_translation(definitions_map, preferred_keys)
                if translated_definition and translated_definition.strip():
                    form_item.definition = translated_definition

        # Add translation support for questions, document fields, and matrix items
        if (form_item.is_question or form_item.is_document_field or getattr(form_item, 'item_type', None) == 'matrix') and form_item.label_translations:
            translations_map = _parse_translations_map(form_item.label_translations)
            translated_label = _first_translation(translations_map, preferred_keys)
            if translated_label and translated_label.strip():
                form_item.display_label = translated_label

            # Add definition translation for questions
            if form_item.is_question and form_item.definition_translations:
                definitions_map = _parse_translations_map(form_item.definition_translations)
                translated_definition = _first_translation(definitions_map, preferred_keys)
                if translated_definition and translated_definition.strip():
                    form_item.definition = translated_definition

            # Add description translation for document fields
            if form_item.is_document_field and form_item.description_translations:
                descriptions_map = _parse_translations_map(form_item.description_translations)
                translated_description = _first_translation(descriptions_map, preferred_keys)
                if translated_description and translated_description.strip():
                    form_item.description = translated_description

        # Add options translation support for questions
        if form_item.is_question and form_item.options_translations:
            form_item.display_options = form_item.get_display_options(translation_key)
        else:
            form_item.display_options = form_item.options

    @classmethod
    def _add_disaggregation_support(cls, form_item: FormItem):
        """Add disaggregation support for both indicators and questions"""
        # Both indicators and questions can have disaggregation
        if form_item.is_indicator or form_item.is_question:
            # Note: effective_age_groups and effective_sex_categories are computed properties
            # that automatically return appropriate values based on configuration

            # Use the actual database values for data availability flags
            # These are already set in the FormItem model, so we don't need to override them
            pass

    @classmethod
    def process_form_item_data(cls, form_item: FormItem, form_data: Dict, assignment_entity_status_id: int, field_prefix: str = None) -> Tuple[Any, bool, bool, bool]:
        """
        Process form data for any form item type.
        Returns: (processed_value, has_value, data_not_available, not_applicable)
        """
        if field_prefix is None:
            field_prefix = cls._get_field_prefix(form_item)

        if form_item.is_indicator:
            return cls._process_indicator_data(form_item, form_data, field_prefix)
        elif form_item.is_question:
            return cls._process_question_data(form_item, form_data, field_prefix)
        elif form_item.is_document_field:
            return cls._process_document_data(form_item, form_data, field_prefix)

        return None, False, False, False

    @classmethod
    def _get_field_prefix(cls, form_item: FormItem) -> str:
        """Get the appropriate field prefix for the form item type"""
        if form_item.is_indicator:
            return f"indicator_{form_item.id}"
        elif form_item.is_question:
            return f"question_{form_item.id}"
        else:
            return f"field_{form_item.id}"

    @classmethod
    def _process_indicator_data(cls, form_item: FormItem, form_data: Dict, field_prefix: str) -> Tuple[Any, bool, bool, bool]:
        """Process indicator data with unified disaggregation logic"""
        # Get data availability flags
        data_not_available = form_data.get(f'{field_prefix}_data_not_available') == '1'
        not_applicable = form_data.get(f'{field_prefix}_not_applicable') == '1'

        if data_not_available or not_applicable:
            # No value, but flags present
            return None, False, data_not_available, not_applicable

        # Process based on field type
        if form_item.field_type_for_js == 'yesno':
            # Yes/No indicators use standard_value
            val_str = form_data.get(f'{field_prefix}_standard_value', '').strip()
            if val_str:
                return val_str.lower(), True, False, False
            return None, False, False, False

        elif form_item.type in ['Number', 'Percentage', 'Currency']:
            # Check if this item truly supports disaggregation (beyond just 'total')
            supports_disaggregation = cls._field_supports_disaggregation(form_item)

            if supports_disaggregation:
                # Numeric indicators with real disaggregation support (sex/age/sex_age) or indirect reach
                return cls._process_numeric_indicator(form_item, form_data, field_prefix)
            else:
                # Numeric indicators without disaggregation - store simple numeric value
                val_str = form_data.get(f'{field_prefix}_total_value', '')
                if val_str and val_str.strip():
                    result = cls._process_numeric_value_simple(val_str, form_item.type)
                    if result is not None:
                        current_app.logger.info(f"Successfully processed numeric value: {result}")
                        return result, True, False, False
                    else:
                        current_app.logger.warning(f"Invalid number for {form_item.label}: {val_str}")
                        return str(val_str), True, False, False
                return None, False, False, False

        else:
            # Text and other types
            val_str = form_data.get(f'{field_prefix}_standard_value', '').strip()
            if val_str:
                return val_str, True, False, False
            return None, False, False, False

    @classmethod
    def _process_numeric_indicator(cls, form_item: FormItem, form_data: Dict, field_prefix: str) -> Tuple[Any, bool, bool, bool]:
        """Process numeric indicators with disaggregation support"""
        reporting_mode = form_data.get(f'{field_prefix}_reporting_mode', 'total')
        collected_values = {}
        has_any_value = False

        if reporting_mode == 'total':
            val_str = form_data.get(f'{field_prefix}_total_value', '')
            if val_str and str(val_str).strip():
                cleaned = cls._unformat_numeric_string(val_str)
                try:
                    if form_item.type == 'Percentage':
                        collected_values['direct' if form_item.indirect_reach else 'total'] = float(cleaned)
                    else:
                        collected_values['direct' if form_item.indirect_reach else 'total'] = int(cleaned)
                    has_any_value = True
                except (ValueError, TypeError):
                    current_app.logger.warning(f"Invalid number for {form_item.label}: {val_str}")

        elif reporting_mode == 'sex':
            collected_values = cls._process_sex_disaggregation(form_item, form_data, field_prefix)
            has_any_value = bool(collected_values)

        elif reporting_mode == 'age':
            collected_values = cls._process_age_disaggregation(form_item, form_data, field_prefix)
            has_any_value = bool(collected_values)

        elif reporting_mode == 'sex_age':
            collected_values = cls._process_sex_age_disaggregation(form_item, form_data, field_prefix)
            has_any_value = bool(collected_values)

        # Process indirect reach if enabled
        if form_item.indirect_reach:
            indirect_reach_str = form_data.get(f'{field_prefix}_indirect_reach', '')
            if indirect_reach_str and str(indirect_reach_str).strip():
                cleaned_indirect = cls._unformat_numeric_string(indirect_reach_str)
                with suppress((ValueError, TypeError)):
                    indirect_reach_value = int(cleaned_indirect)
                    if indirect_reach_value >= 0:
                        collected_values['indirect'] = indirect_reach_value
                        has_any_value = True

        if has_any_value:
            # Return structured data for disaggregated indicators
            data_payload = {"mode": reporting_mode, "values": collected_values}
            return data_payload, True, False, False

        return None, False, False, False

    @classmethod
    def _process_sex_disaggregation(cls, form_item: FormItem, form_data: Dict, field_prefix: str) -> Dict:
        """Process sex disaggregation values"""
        sex_values = {}
        for sex_cat in form_item.effective_sex_categories:
            sex_slug = sex_cat.lower().replace(' ', '_').replace('-', '_')
            val_str = form_data.get(f'{field_prefix}_sex_{sex_slug}', '')
            if val_str and val_str.strip():
                cleaned = cls._unformat_numeric_string(val_str)
                try:
                    if form_item.type == 'Percentage':
                        sex_values[sex_slug] = float(cleaned)
                    else:
                        sex_values[sex_slug] = int(cleaned)
                except (ValueError, TypeError):
                    current_app.logger.warning(f"Invalid sex value for {form_item.label} {sex_cat}: {val_str}")

        if form_item.indirect_reach:
            return {'direct': sex_values} if sex_values else {}
        return sex_values

    @classmethod
    def _process_age_disaggregation(cls, form_item: FormItem, form_data: Dict, field_prefix: str) -> Dict:
        """Process age disaggregation values"""
        age_values = {}
        for age_group in form_item.effective_age_groups:
            age_slug = cls.slugify_age_group(age_group)
            val_str = form_data.get(f'{field_prefix}_age_{age_slug}', '')
            if val_str and val_str.strip():
                cleaned = cls._unformat_numeric_string(val_str)
                try:
                    if form_item.type == 'Percentage':
                        age_values[age_slug] = float(cleaned)
                    else:
                        age_values[age_slug] = int(cleaned)
                except (ValueError, TypeError):
                    current_app.logger.warning(f"Invalid age value for {form_item.label} {age_group}: {val_str}")

        if form_item.indirect_reach:
            return {'direct': age_values} if age_values else {}
        return age_values

    @classmethod
    def _process_sex_age_disaggregation(cls, form_item: FormItem, form_data: Dict, field_prefix: str) -> Dict:
        """Process sex-age disaggregation values"""
        sex_age_values = {}
        for sex_cat in form_item.effective_sex_categories:
            sex_slug = sex_cat.lower().replace(' ', '_').replace('-', '_')
            for age_group in form_item.effective_age_groups:
                age_slug = cls.slugify_age_group(age_group)
                field_key = f'{sex_slug}_{age_slug}'
                val_str = form_data.get(f'{field_prefix}_sexage_{sex_slug}_{age_slug}', '')
                if val_str and val_str.strip():
                    cleaned = cls._unformat_numeric_string(val_str)
                    try:
                        if form_item.type == 'Percentage':
                            sex_age_values[field_key] = float(cleaned)
                        else:
                            sex_age_values[field_key] = int(cleaned)
                    except (ValueError, TypeError):
                        current_app.logger.warning(f"Invalid sex-age value for {form_item.label} {sex_cat}-{age_group}: {val_str}")

        if form_item.indirect_reach:
            return {'direct': sex_age_values} if sex_age_values else {}
        return sex_age_values

    @classmethod
    def _process_question_data(cls, form_item: FormItem, form_data: Dict, field_prefix: str) -> Tuple[Any, bool, bool, bool]:
        """Process question data - questions can now also have disaggregation like indicators"""
        # Get data availability flags
        data_not_available = form_data.get(f'{field_prefix}_data_not_available') == '1'
        not_applicable = form_data.get(f'{field_prefix}_not_applicable') == '1'

        if data_not_available or not_applicable:
            return None, False, data_not_available, not_applicable

        field_name = f'field_value[{form_item.id}]'
        raw_value = form_data.get(field_name)

        if raw_value is None:
            return None, False, False, False

        # Process based on question type
        if form_item.type == 'number':
            try:
                final_value = str(int(raw_value)) if raw_value and str(raw_value).strip() else None
            except ValueError:
                current_app.logger.warning(f"Invalid number for question {form_item.label}: {raw_value}")
                final_value = None

        elif form_item.type == 'percentage':
            try:
                final_value = str(float(raw_value)) if raw_value and str(raw_value).strip() else None
            except ValueError:
                current_app.logger.warning(f"Invalid percentage for question {form_item.label}: {raw_value}")
                final_value = None

        elif form_item.type == 'multiple_choice':
            selected_options = form_data.getlist(field_name)
            final_value = json.dumps(selected_options) if selected_options else None

        elif form_item.type == 'CHECKBOX':
            final_value = 'true' if raw_value else 'false'

        else:
            final_value = str(raw_value).strip() if raw_value and isinstance(raw_value, str) and str(raw_value).strip() else None

        # Process indirect reach for questions (similar to indicators)
        if hasattr(form_item, 'indirect_reach') and form_item.indirect_reach:
            indirect_reach_str = form_data.get(f'{field_prefix}_indirect_reach', '')
            if indirect_reach_str and indirect_reach_str.strip():
                try:
                    if form_item.type == 'number':
                        indirect_reach_value = int(indirect_reach_str)
                    elif form_item.type == 'percentage':
                        indirect_reach_value = float(indirect_reach_str)
                    else:
                        indirect_reach_value = int(indirect_reach_str)

                    # Create disaggregation data structure for questions with indirect reach
                    if final_value is not None:
                        disaggregation_data = {
                            'mode': 'total',
                            'values': {
                                'total': final_value,
                                'indirect_reach': indirect_reach_value
                            }
                        }
                        final_value = json.dumps(disaggregation_data)
                except ValueError:
                    current_app.logger.warning(f"Invalid indirect reach for question {form_item.label}: {indirect_reach_str}")

        has_value = final_value is not None
        return final_value, has_value, False, False

    @classmethod
    def _process_document_data(cls, form_item: FormItem, form_data: Dict, field_prefix: str) -> Tuple[Any, bool, bool, bool]:
        """Process document field data"""
        # Document processing is handled separately in the main form processing logic
        # This is just a placeholder for consistency
        return None, False, False, False

    @classmethod
    def _field_supports_disaggregation(cls, form_item):
        """Check if field truly supports disaggregation (beyond just 'total')"""
        options = getattr(form_item, 'allowed_disaggregation_options', None) or []
        has_true_disagg = any(opt in ('sex', 'age', 'sex_age') for opt in options)
        return has_true_disagg or bool(getattr(form_item, 'indirect_reach', False))

    @classmethod
    def _process_numeric_value_simple(cls, val_str, field_type):
        """Process numeric value based on field type"""
        cleaned = cls._unformat_numeric_string(val_str)
        try:
            if field_type == 'Percentage':
                return str(float(cleaned))
            else:
                return str(int(cleaned))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _unformat_numeric_string(value: Any) -> str:
        """Convert a numeric string to plain format: remove grouping, handle sentinels."""
        if value is None:
            return ''
        s = str(value).strip()
        if not s:
            return ''
        low = s.lower()
        if low in ('none', 'null', 'undefined'):
            return ''
        # Remove common grouping separators: commas, spaces, NBSPs
        s = s.replace('\u00A0', ' ').replace('\u202F', ' ')
        s = s.replace(' ', '').replace(',', '')
        return s

    @staticmethod
    def slugify_age_group(age_group_str: str) -> str:
        """Convert age group string to URL-safe slug. Delegates to module-level slugify_age_group."""
        return slugify_age_group(age_group_str)


class IndirectReachProcessor:
    """
    Centralized processor for indirect reach logic.
    Handles indirect reach calculations and data structures consistently.
    """

    @staticmethod
    def calculate_total_with_indirect(direct_value: float, indirect_value: float) -> float:
        """Calculate total including indirect reach"""
        direct = direct_value or 0
        indirect = indirect_value or 0
        return direct + indirect

    @staticmethod
    def calculate_disaggregation_total_with_indirect(collected_values: Dict) -> float:
        """Calculate total from disaggregated values including indirect reach"""
        if not collected_values:
            return 0

        total = 0
        direct_values = collected_values.get('direct', {})
        indirect_value = collected_values.get('indirect', 0) or 0

        # Calculate direct total
        if isinstance(direct_values, dict):
            for value in direct_values.values():
                if isinstance(value, (int, float)):
                    total += value
        elif isinstance(direct_values, (int, float)):
            total += direct_values

        # Add indirect value
        total += indirect_value

        return total

    @staticmethod
    def process_indirect_reach_value(form_data: Dict, field_prefix: str, item_type: str, item_label: str) -> Optional[float]:
        """
        Process indirect reach value from form data.
        Centralized function to replace duplicated logic.
        """
        indirect_reach_str = form_data.get(f'{field_prefix}_indirect_reach', '')
        if indirect_reach_str and indirect_reach_str.strip():
            try:
                return float(indirect_reach_str)
            except ValueError:
                current_app.logger.warning(f"Invalid indirect reach for {item_type} '{item_label}': {indirect_reach_str}")
                return None
        return None


def calculate_disaggregation_total(collected_values: Dict) -> float:
    """
    Calculate the total from disaggregation values.
    Centralized function to replace duplicated calculation logic.
    """
    if not collected_values:
        return 0

    total = 0
    for key, value in collected_values.items():
        # Skip indirect values in total calculation (handled separately)
        if key == 'indirect':
            continue

        if isinstance(value, (int, float)):
            total += value
        elif isinstance(value, str):
            try:
                total += float(value)
            except (ValueError, TypeError):
                continue
        elif isinstance(value, dict):
            # Handle nested dictionaries (for disaggregated modes)
            for nested_value in value.values():
                if isinstance(nested_value, (int, float)):
                    total += nested_value
                elif isinstance(nested_value, str):
                    try:
                        total += float(nested_value)
                    except (ValueError, TypeError):
                        continue

    return total


def should_create_data_availability_entry(field_value: Any, data_not_available: bool, not_applicable: bool) -> bool:
    """
    Check if we should create a database entry for this field.
    We create an entry if there's a value OR if data availability flags are set.
    """
    has_value = field_value is not None and str(field_value).strip()
    has_flags = data_not_available or not_applicable
    return has_value or has_flags

def get_form_items_for_section(section_obj: FormSection, assignment_entity_status) -> List:
    """
    Get all form items for a section using the unified FormItem model approach.
    This function is used by both template preparation and form data processing.

    Args:
        section_obj: The FormSection object
        assignment_entity_status: The AssignmentEntityStatus object for context

    Returns:
        List of processed FormItem objects ready for template rendering
    """
    current_section_fields = []

    # Get FormItems for this section using the unified approach (exclude archived items)
    form_items = FormItem.query.filter_by(section_id=section_obj.id, archived=False).order_by(FormItem.order).all()

    for form_item in form_items:
        # Set up the form item using our unified processor
        processed_item = FormItemProcessor.setup_form_item_for_template(form_item, assignment_entity_status)
        current_section_fields.append(processed_item)

    # Process dynamic indicators for Dynamic Indicators sections
    if section_obj.section_type == 'dynamic_indicators' and assignment_entity_status:
        dynamic_fields = _process_dynamic_indicators_for_section(section_obj, assignment_entity_status)
        current_section_fields.extend(dynamic_fields)

    # Sort fields by order
    current_section_fields.sort(key=lambda x: x.order)

    return current_section_fields

def _process_dynamic_indicators_for_section(section_obj: FormSection, assignment_entity_status) -> List:
    """Process dynamic indicators for dynamic sections"""
    dynamic_fields = []

    dynamic_assignments = DynamicIndicatorData.query.filter_by(
        assignment_entity_status_id=assignment_entity_status.id,
        section_id=section_obj.id
    ).order_by(DynamicIndicatorData.order).all()

    for dynamic_assignment in dynamic_assignments:
        # Create a pseudo-indicator object from the dynamic assignment
        dynamic_indicator = _create_dynamic_indicator_object(dynamic_assignment, section_obj)
        dynamic_fields.append(dynamic_indicator)

    return dynamic_fields

def _create_dynamic_indicator_object(dynamic_assignment, section_obj):
    """Create a dynamic indicator object with all necessary properties"""
    # Create pseudo-indicator object
    dynamic_indicator = type('DynamicIndicator', (), {})()
    dynamic_indicator.id = f"dynamic_{dynamic_assignment.id}"
    dynamic_indicator.item_type = 'indicator'

    # Set label (custom or localized)
    if dynamic_assignment.custom_label:
        dynamic_indicator.label = dynamic_assignment.custom_label
        dynamic_indicator.display_label = dynamic_assignment.custom_label
    else:
        localized_name = get_localized_indicator_name(dynamic_assignment.indicator_bank)
        dynamic_indicator.label = localized_name
        dynamic_indicator.display_label = localized_name

    # Copy indicator bank properties
    dynamic_indicator.type = dynamic_assignment.indicator_bank.type
    dynamic_indicator.unit = dynamic_assignment.indicator_bank.unit
    dynamic_indicator.order = dynamic_assignment.order
    dynamic_indicator.display_order = int(dynamic_assignment.order)
    dynamic_indicator.definition = dynamic_assignment.indicator_bank.definition
    dynamic_indicator.source_indicator_from_bank = dynamic_assignment.indicator_bank
    dynamic_indicator.indicator_bank_id = dynamic_assignment.indicator_bank_id
    dynamic_indicator.dynamic_assignment_id = dynamic_assignment.id

    # Set default properties for dynamic indicators
    dynamic_indicator.conditions = []
    dynamic_indicator.validations_from_db = []
    dynamic_indicator.is_required_for_js = False
    # Ensure attributes expected by processors exist with safe defaults
    # Original dynamic indicators do not support indirect reach; keep False unless later extended
    dynamic_indicator.indirect_reach = False
    # Use configured defaults for categories (matches original behavior)
    dynamic_indicator.effective_sex_categories = Config.DEFAULT_SEX_CATEGORIES
    dynamic_indicator.effective_age_groups = Config.DEFAULT_AGE_GROUPS

    # Set field type for JavaScript compatibility
    _set_dynamic_indicator_field_type(dynamic_indicator, dynamic_assignment.indicator_bank)

    # Set disaggregation options for dynamic indicators
    _set_dynamic_indicator_disaggregation(dynamic_indicator, dynamic_assignment, section_obj)

    # Set other required properties
    dynamic_indicator.is_sub_indicator = False
    dynamic_indicator.is_indicator = True
    dynamic_indicator.is_question = False
    dynamic_indicator.is_document_field = False

    # Set additional properties
    dynamic_indicator.description = getattr(dynamic_assignment.indicator_bank, 'definition', '')
    dynamic_indicator.relevance_condition = None
    dynamic_indicator.validation_condition = None
    dynamic_indicator.validation_message = None
    dynamic_indicator.layout_column_width = 12
    dynamic_indicator.layout_break_after = False

    return dynamic_indicator

def _set_dynamic_indicator_field_type(dynamic_indicator, indicator_bank):
    """Set field_type_for_js for dynamic indicators"""
    type_lower = indicator_bank.type.lower()

    if type_lower == 'number':
        dynamic_indicator.field_type_for_js = 'number'
    elif type_lower == 'percentage':
        dynamic_indicator.field_type_for_js = 'percentage'
    elif type_lower == 'text':
        dynamic_indicator.field_type_for_js = 'text'
    elif type_lower == 'yesno':
        dynamic_indicator.field_type_for_js = 'yesno'
    elif type_lower == 'date':
        dynamic_indicator.field_type_for_js = 'date'
    elif type_lower == 'datetime':
        dynamic_indicator.field_type_for_js = 'datetime'
    elif type_lower == 'currency':
        dynamic_indicator.field_type_for_js = 'currency'
    elif type_lower in ['single_choice', 'multiple_choice']:
        dynamic_indicator.field_type_for_js = type_lower
    else:
        dynamic_indicator.field_type_for_js = 'text'

def _set_dynamic_indicator_disaggregation(dynamic_indicator, dynamic_assignment, section_obj):
    """Set disaggregation options for dynamic indicators"""
    if (dynamic_assignment.indicator_bank.type == 'Number' and
        dynamic_assignment.indicator_bank.unit in ['People', 'Staff', 'Volunteers']):

        if hasattr(section_obj, 'allowed_disaggregation_options_list') and section_obj.allowed_disaggregation_options_list:
            dynamic_indicator.allowed_disaggregation_options = section_obj.allowed_disaggregation_options_list
        else:
            dynamic_indicator.allowed_disaggregation_options = ["total", "sex", "age", "sex_age"]
    else:
        # For numeric indicators without people-based units, only support total (no disaggregation)
        dynamic_indicator.allowed_disaggregation_options = ["total"]

    dynamic_indicator.age_groups_config = None
    dynamic_indicator.allow_data_not_available = getattr(section_obj, 'allow_data_not_available', False) if section_obj else False
    dynamic_indicator.allow_not_applicable = getattr(section_obj, 'allow_not_applicable', False) if section_obj else False
