"""
FormItem model - the unified model for indicators, questions, and document fields.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, ForeignKey, String, Text, DateTime, Boolean, JSON, Float
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, backref
from ..extensions import db
from .enums import FormItemType
from .lookups import LookupList, LookupListRow
from config import Config
import json
from contextlib import suppress


class FormItem(db.Model):
    __tablename__ = 'form_item'
    id = Column(Integer, primary_key=True)
    section_id = Column(Integer, ForeignKey('form_section.id', ondelete='CASCADE'), nullable=False)
    # Version that this item belongs to (primary reference)
    version_id = db.Column(db.Integer, db.ForeignKey('form_template_version.id', ondelete='CASCADE'), nullable=False)
    # Template reference (denormalized for performance, can be derived from version)
    template_id = db.Column(db.Integer, db.ForeignKey('form_template.id', ondelete='CASCADE'), nullable=True)
    item_type = Column(String(100), nullable=False)  # Changed from Enum to String to support dynamic plugin field types

    # Common fields for all item types
    label = Column(Text, nullable=False)
    order = Column(Float, nullable=False, default=0)
    relevance_condition = db.Column(db.Text, nullable=True)
    archived = Column(Boolean, nullable=False, default=False)  # For soft deletion when keeping data

    # Consolidated configuration field
    config = Column(JSON, nullable=True, default=lambda: {
        'is_required': False,
        'layout_column_width': 12,
        'layout_break_after': False,
        'allowed_disaggregation_options': ["total"],
        'age_groups_config': None,
        'default_value': None,
        'allow_data_not_available': False,
        'allow_not_applicable': False,
        'indirect_reach': False,
        'privacy': 'ifrc_network'
    })

    # Indicator-specific fields (nullable for non-indicator types)
    indicator_bank_id = Column(Integer, ForeignKey('indicator_bank.id'), nullable=True)
    type = Column(String(50), nullable=True)
    unit = Column(String(50), nullable=True)
    indicator_type_id = Column(Integer, ForeignKey('indicator_bank_type.id'), nullable=True)
    indicator_unit_id = Column(Integer, ForeignKey('indicator_bank_unit.id'), nullable=True)
    validation_condition = db.Column(db.Text, nullable=True)
    validation_message = db.Column(db.Text, nullable=True)

    # Question-specific fields (nullable for non-question types)
    definition = db.Column(db.Text, nullable=True)
    options_json = Column(JSON, nullable=True)

    # Calculated list choice fields (for choice questions)
    # Can be either an integer (database lookup list ID) or string (special identifiers like 'emergency_operations')
    lookup_list_id = Column(String(50), nullable=True)
    list_display_column = Column(String(100), nullable=True)
    list_filters_json = Column(JSON, nullable=True)

    label_translations = Column(JSON, nullable=True)
    definition_translations = Column(JSON, nullable=True)
    options_translations = Column(JSON, nullable=True)
    description_translations = Column(JSON, nullable=True)

    # Document field-specific fields (nullable for non-document types)
    description = db.Column(db.Text, nullable=True)

    # Relationships
    form_section = relationship(
        'FormSection',
        backref=backref(
            'form_items',
            lazy='dynamic',
            order_by='FormItem.order',
            cascade='all, delete-orphan'
        ),
        lazy='select'
    )
    template = relationship(
        'FormTemplate',
        backref=backref(
            'form_items',
            lazy='dynamic',
            cascade='all, delete-orphan'
        ),
        lazy='select'
    )
    indicator_bank = relationship('IndicatorBank', backref='form_item_usages', lazy='select')
    measurement_type = relationship('IndicatorBankType', foreign_keys=[indicator_type_id], lazy='select')
    measurement_unit = relationship('IndicatorBankUnit', foreign_keys=[indicator_unit_id], lazy='select')

    __table_args__ = (
        db.Index('ix_form_item_version_order', 'version_id', 'order'),
        db.Index('ix_form_item_section_order', 'section_id', 'order'),
        db.Index('ix_form_item_item_type', 'item_type'),
        db.Index('ix_form_item_indicator_bank', 'indicator_bank_id'),
        db.Index('ix_form_item_lookup_list', 'lookup_list_id'),
        db.Index('ix_form_item_template', 'template_id'),
        db.Index('ix_form_item_indicator_type', 'indicator_type_id'),
        db.Index('ix_form_item_indicator_unit', 'indicator_unit_id'),
    )
    # Lookup list relationship - only works for database IDs, not special strings like 'emergency_operations'
    @property
    def lookup_list(self):
        """Get the lookup list if lookup_list_id is a database ID."""
        if self.lookup_list_id and str(self.lookup_list_id).isdigit():
            return LookupList.query.get(int(self.lookup_list_id))
        return None

    # Data entries relationships
    data_entries = relationship('FormData', foreign_keys='FormData.form_item_id', lazy='dynamic', cascade="all, delete-orphan", overlaps="indicator,question")
    repeat_data_entries = relationship('RepeatGroupData', foreign_keys='RepeatGroupData.form_item_id', lazy='dynamic', cascade="all, delete-orphan", overlaps="indicator,question")

    # Document-related relationships
    submitted_documents = relationship('SubmittedDocument', foreign_keys='SubmittedDocument.form_item_id', lazy='dynamic', cascade="all, delete-orphan", overlaps="document_field")

    @property
    def is_indicator(self):
        return self.item_type == 'indicator'

    @property
    def is_question(self):
        return self.item_type == 'question'

    @property
    def is_document_field(self):
        return self.item_type == 'document_field'

    @property
    def is_matrix(self):
        return self.item_type == 'matrix'

    @property
    def is_plugin(self):
        """Returns True if this is a plugin field type."""
        return self.item_type.startswith('plugin_')

    @property
    def is_sub_item(self):
        """Returns True if this is a sub-item (has decimal order like 1.1, 1.2, etc.)."""
        return self.order != int(self.order)

    @property
    def parent_order(self):
        """Returns the parent item order (e.g., 1.0 for sub-item 1.1)."""
        return int(self.order) if self.is_sub_item else None

    @property
    def depth_level(self):
        """Returns the depth level (0 for main items, 1 for sub-items)."""
        return 1 if self.is_sub_item else 0

    @property
    def display_order(self):
        """Returns a formatted order for display (e.g., '1', '1.1', '1.2')."""
        if self.order == int(self.order):
            return str(int(self.order))
        else:
            return f"{self.order:.1f}"

    # Properties to access consolidated config fields
    @property
    def is_required(self):
        """Get is_required from config."""
        return self.config.get('is_required', False) if self.config else False

    @is_required.setter
    def is_required(self, value):
        """Set is_required in config."""
        self.set_is_required(value)

    @property
    def layout_column_width(self):
        """Get layout_column_width from config."""
        return self.config.get('layout_column_width', 12) if self.config else 12

    @layout_column_width.setter
    def layout_column_width(self, value):
        """Set layout_column_width in config."""
        self.set_layout_column_width(value)

    @property
    def layout_break_after(self):
        """Get layout_break_after from config."""
        return self.config.get('layout_break_after', False) if self.config else False

    @layout_break_after.setter
    def layout_break_after(self, value):
        """Set layout_break_after in config."""
        self.set_layout_break_after(value)

    @property
    def allowed_disaggregation_options(self):
        """Get allowed_disaggregation_options from config."""
        return self.config.get('allowed_disaggregation_options', ["total"]) if self.config else ["total"]

    @allowed_disaggregation_options.setter
    def allowed_disaggregation_options(self, value):
        """Set allowed_disaggregation_options in config."""
        self.set_allowed_disaggregation_options(value)

    @property
    def age_groups_config(self):
        """Get age_groups_config from config."""
        return self.config.get('age_groups_config') if self.config else None

    @age_groups_config.setter
    def age_groups_config(self, value):
        """Set age_groups_config in config."""
        self.set_age_groups_config(value)

    @property
    def allow_data_not_available(self):
        """Get allow_data_not_available from config."""
        return self.config.get('allow_data_not_available', False) if self.config else False

    @allow_data_not_available.setter
    def allow_data_not_available(self, value):
        """Set allow_data_not_available in config."""
        self.set_allow_data_not_available(value)

    @property
    def allow_not_applicable(self):
        """Get allow_not_applicable from config."""
        return self.config.get('allow_not_applicable', False) if self.config else False

    @allow_not_applicable.setter
    def allow_not_applicable(self, value):
        """Set allow_not_applicable in config."""
        self.set_allow_not_applicable(value)

    @property
    def indirect_reach(self):
        """Get indirect_reach from config."""
        return self.config.get('indirect_reach', False) if self.config else False

    @indirect_reach.setter
    def indirect_reach(self, value):
        """Set indirect_reach in config."""
        self.set_indirect_reach(value)

    @property
    def privacy(self):
        """Get privacy from config. Values: 'public' | 'ifrc_network'."""
        return self.config.get('privacy', 'ifrc_network') if self.config else 'ifrc_network'

    @privacy.setter
    def privacy(self, value):
        """Set privacy in config."""
        self.set_privacy(value)

    # --- Safe display helpers to avoid Jinja callable shadowing ---
    @property
    def type_display(self):
        """Return a localized, human-friendly type label for indicators; fallback to raw type."""
        with suppress(Exception):
            if self.is_indicator and self.type:
                from app.utils.form_localization import get_localized_indicator_type  # local import to avoid circulars
                # If helper returns falsy, fallback to raw value
                localized = get_localized_indicator_type(self.type)
                return localized if localized is not None else (self.type or '')
        return self.type or ''

    @property
    def unit_display(self):
        """Return a localized, human-friendly unit label for indicators; fallback to raw unit."""
        with suppress(Exception):
            if self.is_indicator and self.unit:
                from app.utils.form_localization import get_localized_indicator_unit  # local import to avoid circulars
                localized = get_localized_indicator_unit(self.unit)
                return localized if localized is not None else (self.unit or '')
        return self.unit or ''

    @property
    def is_required_for_js(self):
        """Compatibility property for JavaScript - same as is_required."""
        return self.is_required

    @is_required_for_js.setter
    def is_required_for_js(self, value):
        """Setter for is_required_for_js - sets is_required in config."""
        self.set_is_required(value)

    # Setter methods for config fields
    def set_is_required(self, value):
        """Set is_required in config."""
        if self.config is None:
            self.config = {}
        self.config['is_required'] = bool(value)

    def set_layout_column_width(self, value):
        """Set layout_column_width in config."""
        if self.config is None:
            self.config = {}
        self.config['layout_column_width'] = int(value)

    def set_layout_break_after(self, value):
        """Set layout_break_after in config."""
        if self.config is None:
            self.config = {}
        self.config['layout_break_after'] = bool(value)

    def set_allowed_disaggregation_options(self, value):
        """Set allowed_disaggregation_options in config."""
        if self.config is None:
            self.config = {}
        self.config['allowed_disaggregation_options'] = value if value is not None else ["total"]

    def set_age_groups_config(self, value):
        """Set age_groups_config in config."""
        if self.config is None:
            self.config = {}
        self.config['age_groups_config'] = value

    def set_allow_data_not_available(self, value):
        """Set allow_data_not_available in config."""
        if self.config is None:
            self.config = {}
        self.config['allow_data_not_available'] = bool(value)

    def set_allow_not_applicable(self, value):
        """Set allow_not_applicable in config."""
        if self.config is None:
            self.config = {}
        self.config['allow_not_applicable'] = bool(value)

    def set_indirect_reach(self, value):
        """Set indirect_reach in config."""
        if self.config is None:
            self.config = {}
        self.config['indirect_reach'] = bool(value)

    def set_privacy(self, value):
        """Set privacy in config."""
        if self.config is None:
            self.config = {}
        allowed = {'public', 'ifrc_network'}
        self.config['privacy'] = value if value in allowed else 'ifrc_network'

    @property
    def effective_age_groups(self):
        """Returns custom age groups if configured, otherwise default (for indicators only)."""
        if not self.is_indicator:
            return []
        if self.age_groups_config and self.age_groups_config.strip():
            return [group.strip() for group in self.age_groups_config.split(',') if group.strip()]
        return Config.DEFAULT_AGE_GROUPS

    @property
    def effective_sex_categories(self):
        """Returns default sex categories (for indicators only)."""
        if not self.is_indicator:
            return []
        return Config.DEFAULT_SEX_CATEGORIES

    @property
    def supports_disaggregation(self):
        """Returns True if this indicator supports disaggregation based on type and unit."""
        if not self.is_indicator:
            return False
        t_ok = self.type and str(self.type).lower() == 'number'
        if not t_ok:
            return False
        if self.indicator_unit_id and self.measurement_unit is not None:
            return bool(self.measurement_unit.allows_disaggregation)
        from config import Config
        u = (self.unit or '').strip()
        if not u:
            return False
        allowed = {x.lower() for x in (getattr(Config, "DISAGGREGATION_ALLOWED_UNITS", None) or [])}
        return u.lower() in allowed

    @property
    def disaggregation_options_display(self):
        """Returns display names for allowed disaggregation options (for indicators only)."""
        if not self.is_indicator or not self.allowed_disaggregation_options:
            return ["Total Only"]

        # Check if all disaggregation options are available
        all_options = set(['total', 'sex', 'age', 'sex_age'])
        current_options = set(self.allowed_disaggregation_options)

        # If all options are present, show "All"
        if current_options == all_options:
            return ["All"]

        return [Config.DISAGGREGATION_MODES.get(opt, opt.title()) for opt in self.allowed_disaggregation_options]

    @property
    def options(self):
        """Returns parsed options from options_json, or calculated options from lookup list (for questions only)."""
        if not self.is_question:
            return []

        # For calculated lists, resolve options dynamically
        if self.lookup_list_id and self.list_display_column:
            return self.get_calculated_options()

        # For manual options, parse from options_json
        if self.options_json is None:
            return []
        try:
            parsed_options = json.loads(self.options_json) if isinstance(self.options_json, str) else self.options_json
            return parsed_options if isinstance(parsed_options, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    def get_display_options(self, language=None):
        """Returns options with translations applied for display purposes."""
        base_options = self.options

        # Debug logging
        from flask import current_app
        current_app.logger.debug(f"get_display_options called with language: {language}")
        current_app.logger.debug(f"Base options: {base_options}")
        current_app.logger.debug(f"Options translations: {self.options_translations}")

        # If no language specified or no translations, return base options
        if not language or not self.options_translations:
            current_app.logger.debug(f"Returning base options (no language or no translations)")
            return base_options

        # Apply translations
        translated_options = []
        for option in base_options:
            # Find the translation entry for this option
            translation_entry = None
            for entry in self.options_translations:
                if entry.get('option_text') == option:
                    translation_entry = entry
                    break

            # Get the translated text for this language, or use original if no translation
            if translation_entry and translation_entry.get('translations', {}).get(language):
                translated_text = translation_entry['translations'][language]
                current_app.logger.debug(f"Found translation for '{option}' -> '{translated_text}'")
                translated_options.append(translated_text)
            else:
                current_app.logger.debug(f"No translation found for '{option}', using original")
                translated_options.append(option)

        current_app.logger.debug(f"Final translated options: {translated_options}")
        return translated_options

    def get_option_value_for_display(self, saved_value, language=None):
        """Returns the display value for a saved option value, considering translations."""
        if not saved_value or not self.options_translations:
            return saved_value

        # Find the translation entry for this saved value
        translation_entry = None
        for entry in self.options_translations:
            if entry.get('option_text') == saved_value:
                translation_entry = entry
                break

        # Get the translated text for this language, or use original if no translation
        if translation_entry and translation_entry.get('translations', {}).get(language):
            return translation_entry['translations'][language]

        return saved_value

    def get_calculated_options(self, context_values=None):
        """
        Get options from lookup list with filter evaluation.

        This method evaluates the filters stored in list_filters_json against
        the rows in the associated lookup list and returns the values from
        the specified display column.

        Args:
            context_values (dict): Optional dictionary of field_id -> value
                                 for resolving filter references

        Returns:
            list: A list of unique option values from the display column,
                  filtered according to the configured filters.
        """
        if not self.lookup_list_id or not self.list_display_column:
            return []

        # Simple caching based on filters JSON to avoid recalculation
        cache_key = f"{self.lookup_list_id}_{self.list_display_column}_{self.list_filters_json or ''}_{context_values or ''}"
        if hasattr(self, '_calculated_options_cache') and self._calculated_options_cache.get('key') == cache_key:
            return self._calculated_options_cache.get('options', [])

        try:
            # Handle special case: emergency_operations
            if self.lookup_list_id == 'emergency_operations':
                # For emergency operations, we can't get data here as it requires API calls
                # This method is used for database lookup lists only
                return []

            # Handle system lists (country_map, indicator_bank)
            if self.lookup_list_id == 'country_map':
                from app.models.core import Country
                from flask import session
                from flask_babel import get_locale
                from app.utils.form_localization import get_localized_country_name
                countries = Country.query.order_by(Country.name).all()
                options = []

                # Dynamically get the value from the display column
                for country in countries:
                    if hasattr(country, self.list_display_column):
                        # Special handling for 'name' column - use localized name
                        if self.list_display_column == 'name':
                            value = get_localized_country_name(country)
                        else:
                            value = getattr(country, self.list_display_column)
                            # Handle None values
                            if value is None:
                                value = ''
                            # Handle JSONB/dict fields
                            elif isinstance(value, dict):
                                value = str(value) if value else ''
                            else:
                                value = str(value).strip()

                        if value:
                            options.append(value)

                # Remove duplicates while preserving order
                seen = set()
                unique_options = []
                for option in options:
                    if option not in seen:
                        seen.add(option)
                        unique_options.append(option)

                # Cache the result
                self._calculated_options_cache = {
                    'key': cache_key,
                    'options': unique_options
                }

                return unique_options

            elif self.lookup_list_id == 'indicator_bank':
                from app.models.indicator_bank import IndicatorBank
                indicators = IndicatorBank.query.order_by(IndicatorBank.name).all()
                options = []

                # Dynamically get the value from the display column
                for indicator in indicators:
                    if hasattr(indicator, self.list_display_column):
                        value = getattr(indicator, self.list_display_column)
                        # Handle None values
                        if value is None:
                            value = ''
                        # Handle JSONB/dict fields
                        elif isinstance(value, dict):
                            value = str(value) if value else ''
                        else:
                            value = str(value).strip()

                        if value:
                            options.append(value)

                # Remove duplicates while preserving order
                seen = set()
                unique_options = []
                for option in options:
                    if option not in seen:
                        seen.add(option)
                        unique_options.append(option)

                # Cache the result
                self._calculated_options_cache = {
                    'key': cache_key,
                    'options': unique_options
                }

                return unique_options

            elif self.lookup_list_id == 'national_society':
                from app.models.organization import NationalSociety
                national_societies = NationalSociety.query.order_by(NationalSociety.name).all()
                options = []

                # Get current locale for localization
                from app.utils.form_localization import get_translation_key
                current_locale = get_translation_key()

                # Dynamically get the value from the display column
                for ns in national_societies:
                    if hasattr(ns, self.list_display_column):
                        # Special handling for 'name' column - use localized name
                        if self.list_display_column == 'name':
                            localized_name = ns.get_name_translation(current_locale)
                            value = localized_name if localized_name and localized_name.strip() else ns.name
                        else:
                            value = getattr(ns, self.list_display_column)
                            # Handle None values
                            if value is None:
                                value = ''
                            # Handle JSONB/dict fields
                            elif isinstance(value, dict):
                                value = str(value) if value else ''
                            else:
                                value = str(value).strip()

                        if value:
                            options.append(value)

                # Remove duplicates while preserving order
                seen = set()
                unique_options = []
                for option in options:
                    if option not in seen:
                        seen.add(option)
                        unique_options.append(option)

                # Cache the result
                self._calculated_options_cache = {
                    'key': cache_key,
                    'options': unique_options
                }

                return unique_options

            # Get the lookup list (regular database lookup list)
            lookup_list = self.lookup_list
            if not lookup_list:
                return []

            # Get all rows
            rows = lookup_list.rows.order_by(LookupListRow.order).all()

            # Apply filters if they exist
            if self.list_filters_json:
                with suppress(json.JSONDecodeError, TypeError):
                    filters = json.loads(self.list_filters_json) if isinstance(self.list_filters_json, str) else self.list_filters_json
                    if isinstance(filters, list) and filters:
                        rows = self._apply_filters_to_rows(rows, filters, context_values=context_values)

            # Extract options from the specified display column
            options = []
            for row in rows:
                if row.data and self.list_display_column in row.data:
                    value = row.data[self.list_display_column]
                    if value is not None:
                        # Convert to string for consistency
                        str_value = str(value).strip()
                        if str_value:  # Only add non-empty values
                            options.append(str_value)

            # Remove duplicates while preserving order
            seen = set()
            unique_options = []
            for option in options:
                if option not in seen:
                    seen.add(option)
                    unique_options.append(option)

            # Cache the result
            self._calculated_options_cache = {
                'key': cache_key,
                'options': unique_options
            }

            return unique_options

        except Exception as e:
            # Log error but don't break the form
            import logging
            logging.error(f"Error getting calculated options for FormItem {self.id}: {str(e)}")
            return []

    def clear_calculated_options_cache(self):
        """Clear the cached calculated options to force recalculation."""
        if hasattr(self, '_calculated_options_cache'):
            delattr(self, '_calculated_options_cache')

    def _apply_filters_to_rows(self, rows, filters, context_values=None):
        """
        Apply list filters to rows and return filtered results.

        Args:
            rows: List of LookupListRow objects to filter
            filters: List of filter dictionaries with 'field', 'op', and 'value' keys

        Returns:
            list: Filtered list of LookupListRow objects
        """
        if not filters:
            return rows

        filtered_rows = []
        for row in rows:
            if self._row_matches_filters(row, filters, context_values=context_values):
                filtered_rows.append(row)

        return filtered_rows

    def _row_matches_filters(self, row, filters, context_values=None):
        """
        Check if a row matches all filter conditions.

        Supported operators:
        - eq: equals
        - ne: not equals
        - contains: contains substring (case-insensitive)
        - startswith: starts with substring (case-insensitive)
        - endswith: ends with substring (case-insensitive)
        - gt, gte, lt, lte: numeric comparisons
        - in: value in list
        - not_in: value not in list
        - is_empty: value is empty or None
        - is_not_empty: value is not empty and not None

        Args:
            row: LookupListRow object to check
            filters: List of filter dictionaries

        Returns:
            bool: True if row matches all filters, False otherwise
        """
        for filter_condition in filters:
            if not isinstance(filter_condition, dict):
                continue

            field = filter_condition.get('field')
            op = filter_condition.get('op', 'eq')
            # Resolve the filter value – either literal or from another field reference
            if 'value_field_id' in filter_condition and filter_condition['value_field_id'] is not None:
                if context_values and str(filter_condition['value_field_id']) in context_values:
                    value = context_values[str(filter_condition['value_field_id'])]
                else:
                    # If the referenced field has no value in context, treat filter as not satisfied
                    return False
            else:
                value = filter_condition.get('value')

            if not field or value is None:
                continue

            row_value = row.data.get(field)

            # Handle null/None values
            if row_value is None:
                # For 'is_empty' operator, None should match
                if op == 'is_empty':
                    continue
                # For all other operators, None doesn't match
                return False

            # Convert values to strings for comparison
            row_value_str = str(row_value).strip()
            filter_value_str = str(value).strip()

            # Handle empty string checks
            if op == 'is_empty':
                if row_value_str != '':
                    return False
                continue
            elif op == 'is_not_empty':
                if row_value_str == '':
                    return False
                continue

            # Apply operator
            if op == 'eq':
                if row_value_str != filter_value_str:
                    return False
            elif op == 'ne':
                if row_value_str == filter_value_str:
                    return False
            elif op == 'contains':
                if filter_value_str.lower() not in row_value_str.lower():
                    return False
            elif op == 'startswith':
                if not row_value_str.lower().startswith(filter_value_str.lower()):
                    return False
            elif op == 'endswith':
                if not row_value_str.lower().endswith(filter_value_str.lower()):
                    return False
            elif op in ['gt', 'gte', 'lt', 'lte']:
                # Numeric comparisons
                try:
                    row_num = float(row_value_str)
                    filter_num = float(filter_value_str)

                    if op == 'gt' and not (row_num > filter_num):
                        return False
                    elif op == 'gte' and not (row_num >= filter_num):
                        return False
                    elif op == 'lt' and not (row_num < filter_num):
                        return False
                    elif op == 'lte' and not (row_num <= filter_num):
                        return False
                except (ValueError, TypeError):
                    # If values can't be converted to numbers, treat as failed match
                    return False
            # Add support for 'in' operator for multiple values
            elif op == 'in':
                if isinstance(value, list):
                    if row_value_str not in [str(v).strip() for v in value]:
                        return False
                else:
                    # Single value in list
                    if row_value_str != filter_value_str:
                        return False
            elif op == 'not_in':
                if isinstance(value, list):
                    if row_value_str in [str(v).strip() for v in value]:
                        return False
                else:
                    # Single value not in list
                    if row_value_str == filter_value_str:
                        return False

        return True

    @property
    def field_type_for_js(self):
        """Returns the specific field type for JavaScript compatibility."""
        if self.is_document_field:
            return 'DOCUMENT'
        elif self.is_indicator:
            # For indicators, return the specific type or default based on type
            if self.type:
                type_lower = self.type.lower()
                if type_lower in ['number', 'count']:
                    return 'number'
                elif type_lower == 'percentage':
                    return 'percentage'
                elif type_lower in ['text', 'string']:
                    return 'text'
                elif type_lower == 'yesno':
                    return 'yesno'
                elif type_lower == 'date':
                    return 'date'
                elif type_lower == 'datetime':
                    return 'datetime'
                elif type_lower == 'currency':
                    return 'currency'
                else:
                    return type_lower
            return 'text'  # Default fallback
        elif self.is_question:
            # For questions, check question_type first
            if self.question_type and self.question_type.value == 'blank':
                return 'blank'
            # Then check type
            if self.type:
                type_lower = self.type.lower()
                if type_lower == 'blank':
                    return 'blank'
                return type_lower
            return 'text'  # Default fallback
        elif self.item_type and self.item_type.startswith('plugin_'):
            # For plugin items, return PLUGIN_{PLUGIN_TYPE}
            plugin_type = self.item_type.replace('plugin_', '')
            return f'PLUGIN_{plugin_type.upper()}'
        return 'text'

    # Note: id is now the primary key column (migrated from item_id)

    @property
    def question_type(self):
        """Returns question type as enum-like object for compatibility."""
        if not self.is_question or not self.type:
            return None

        # Create a simple enum-like object that has a .value attribute
        class QuestionTypeCompat:
            def __init__(self, type_value):
                self.value = type_value

        return QuestionTypeCompat(self.type)

    @property
    def indicator_bank_id_compat(self):
        """For indicators, returns indicator_bank_id; for others, returns None."""
        return self.indicator_bank_id if self.is_indicator else None

    @property
    def translations(self):
        """Returns the translations dictionary, initializing it if it doesn't exist."""
        if self.label_translations is None:
            return {}
        return self.label_translations

    def get_translation(self, language):
        """Get translation for a specific language."""
        if not self.translations:
            return None
        return self.translations.get(language)

    def set_translation(self, language, text):
        """Set translation for a specific language."""
        if self.label_translations is None:
            self.label_translations = {}
        self.label_translations[language] = text

    def get_definition_translation(self, language):
        """Get definition translation for a specific language."""
        if not self.definition_translations:
            return None
        return self.definition_translations.get(language)

    def set_definition_translation(self, language, text):
        """Set definition translation for a specific language."""
        if self.definition_translations is None:
            self.definition_translations = {}
        self.definition_translations[language] = text

    def get_translated_options(self, language):
        """Get translated options for a specific language, falling back to original options if no translation exists."""
        if not self.is_question or not self.options_translations:
            return self.options

        # Get the original options
        original_options = self.options
        if not original_options:
            return []

        # Try to find translations for the current language
        translated_options = []
        for option in original_options:
            # Find the translation entry for this option
            translation_entry = None
            for entry in self.options_translations:
                if entry.get('option_text') == option:
                    translation_entry = entry
                    break

            # Get the translated text for this language, or use original if no translation
            if translation_entry and translation_entry.get('translations', {}).get(language):
                translated_options.append(translation_entry['translations'][language])
            else:
                translated_options.append(option)

        return translated_options

    def get_description_translation(self, language):
        """Get description translation for a specific language."""
        if not self.description_translations:
            return None
        return self.description_translations.get(language)

    def set_description_translation(self, language, text):
        """Set description translation for a specific language."""
        if self.description_translations is None:
            self.description_translations = {}
        if text and text.strip():
            self.description_translations[language] = text.strip()
        elif language in self.description_translations:
            del self.description_translations[language]

    def __repr__(self):
        section_name = self.form_section.name if self.form_section else "N/A"
        template_name = self.template.name if self.template else "N/A"
        hierarchy_info = " (Sub)" if self.is_sub_item else ""
        item_type_display = self.item_type.title()

        if self.is_indicator:
            options_str = ', '.join(self.allowed_disaggregation_options) if self.allowed_disaggregation_options else "total"
            return f'<FormItem({item_type_display}) {self.display_order}. {self.label}{hierarchy_info} (Options: {options_str})>'
        elif self.is_question:
            q_type = self.question_type.value if self.question_type else "unknown"
            return f'<FormItem({item_type_display}) {self.display_order}. {self.label[:50]}...{hierarchy_info} (Type: {q_type}, Section: {section_name})>'
        elif self.is_document_field:
            return f'<FormItem({item_type_display}) {self.display_order}. {self.label}{hierarchy_info} (Section: {section_name})>'

        return f'<FormItem({item_type_display}) {self.display_order}. {self.label}{hierarchy_info}>'
