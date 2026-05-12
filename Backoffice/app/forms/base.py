# ========== File: app/forms/base.py ==========
"""
Base forms and utilities for the platform forms system.
Contains common functionality, validators, and base classes used across all form domains.
"""

import logging

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, TextAreaField, SubmitField, SelectField, SelectMultipleField,
    DateField, PasswordField, IntegerField, HiddenField, RadioField, BooleanField,
    FloatField, DateTimeField
)
from wtforms.validators import DataRequired, Email, Optional, Length, ValidationError, NumberRange
from wtforms.widgets import ListWidget, CheckboxInput
from app.models import Country, IndicatorBank, FormTemplate, User, FormSection, QuestionType
from config import Config
import json


# ========== UTILITY FUNCTIONS ==========

def _get_supported_language_codes() -> list[str]:
    """Return supported language codes, preferring runtime app settings."""
    try:
        from flask import current_app
        langs = current_app.config.get("SUPPORTED_LANGUAGES")
        if isinstance(langs, list) and langs:
            return [str(c).strip().lower() for c in langs if str(c).strip()]
    except (RuntimeError, TypeError, AttributeError):
        pass  # No app context or invalid config
    langs = getattr(Config, "LANGUAGES", None) or ["en"]
    return [str(c).strip().lower() for c in langs if str(c).strip()]


def _get_translatable_language_codes() -> list[str]:
    """Return supported languages excluding the base ('en')."""
    try:
        from flask import current_app
        langs = current_app.config.get("TRANSLATABLE_LANGUAGES")
        if isinstance(langs, list):
            return [str(c).strip().lower() for c in langs if str(c).strip() and str(c).strip().lower() != "en"]
    except (RuntimeError, TypeError, AttributeError):
        pass  # No app context or invalid config
    supported = _get_supported_language_codes()
    return [c for c in supported if c != "en"]


def _get_language_display_name(code: str) -> str:
    code = (code or "").strip().lower()
    if not code:
        return ""
    return (
        getattr(Config, "LANGUAGE_DISPLAY_NAMES", {}).get(code)
        or getattr(Config, "ALL_LANGUAGES_DISPLAY_NAMES", {}).get(code)
        or code.upper()
    )


def int_or_none(value):
    """Coerces value to int, returns None on ValueError or TypeError."""
    try:
        # Check if value is not None and is not an empty string before converting
        if value is not None and str(value).strip() != '':
            return int(value)
        return None  # Return None for None, empty strings, or strings with only whitespace
    except (ValueError, TypeError):
        return None  # Return None if conversion fails


def lookup_list_id_coerce(value):
    """Coerces value to int for database IDs, or returns string for plugin identifiers."""
    if value is None or str(value).strip() == '':
        return None

    # Check if it's a plugin lookup list (non-numeric ID)
    if not str(value).strip().isdigit():
        return str(value).strip()

    # Try to convert to int for database IDs
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


# ========== BASE FORM CLASSES ==========

class BaseForm(FlaskForm):
    """Base form class with common functionality."""

    def __init__(self, *args, **kwargs):
        super(BaseForm, self).__init__(*args, **kwargs)
        self._setup_multilingual_fields()

    def _setup_multilingual_fields(self):
        """Setup multilingual field handling if needed."""
        pass


class MultilingualForm(BaseForm):
    """Base form class for forms that support multiple languages."""

    def __init__(self, *args, **kwargs):
        super(MultilingualForm, self).__init__(*args, **kwargs)
        self.languages = _get_supported_language_codes()
        self.language_display_names = getattr(Config, 'LANGUAGE_DISPLAY_NAMES', {}) or {}

    def _create_language_fields(self, field_name, field_class, validators=None, **kwargs):
        """Dynamically create language-specific fields to avoid code duplication."""
        if validators is None:
            validators = [Optional()]

        for lang_code in self.languages:
            lang_name = _get_language_display_name(lang_code)
            field_key = f'{field_name}_{lang_code}'

            if not hasattr(self, field_key):
                setattr(self, field_key,
                       field_class(f"{field_name.title()} ({lang_name})",
                                 validators=validators, **kwargs))


class FileUploadForm(BaseForm):
    """Base form class for forms that handle file uploads."""

    # Common file validators
    document_validators = [
        Optional(),
        FileAllowed(['pdf', 'doc', 'docx', 'txt', 'xls', 'xlsx', 'ppt', 'pptx'],
                   'Allowed document types: PDF, Word, Excel, PowerPoint, Text')
    ]

    image_validators = [
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'],
                   'Allowed image types: JPG, PNG, GIF, WEBP, SVG')
    ]


# ========== COMMON FIELD DEFINITIONS ==========

class CommonFields:
    """Common field definitions used across multiple forms."""

    # Layout fields
    LAYOUT_COLUMN_WIDTH_CHOICES = [
        ('12', 'Full Width (12/12)'),
        ('6', 'Half Width (6/12)'),
        ('4', 'One Third (4/12)'),
        ('3', 'One Quarter (3/12)'),
        ('8', 'Two Thirds (8/12)'),
        ('9', 'Three Quarters (9/12)')
    ]

    # Data availability fields
    DATA_AVAILABILITY_FIELDS = {
        'allow_data_not_available': BooleanField('Allow "Data not available" option', default=False),
        'allow_not_applicable': BooleanField('Allow "Not applicable" option', default=False),
        'indirect_reach': BooleanField('Indirect reach', default=False)
    }

    # Skip logic fields
    SKIP_LOGIC_FIELDS = {
        'relevance_condition': HiddenField('Relevance Condition'),
        'validation_condition': HiddenField('Validation Condition'),
        'validation_message': TextAreaField('Validation Message',
                                          validators=[Optional(), Length(max=500)],
                                          render_kw={"rows": 2, "placeholder": "Message to show if validation fails"})
    }

    # Layout fields
    LAYOUT_FIELDS = {
        'layout_column_width': SelectField('Column Width',
                                         choices=LAYOUT_COLUMN_WIDTH_CHOICES,
                                         default='12',
                                         validators=[DataRequired()]),
        'layout_break_after': BooleanField('Force New Row After This Item', default=False)
    }


# ========== COMMON VALIDATORS ==========

class CommonValidators:
    """Common validation functions used across forms."""

    @staticmethod
    def validate_unique_name(model_class, field, exclude_id=None):
        """Validates that a name field is unique within a model class."""
        query = model_class.query.filter_by(name=field.data)
        if exclude_id:
            query = query.filter(model_class.id != exclude_id)
        existing = query.first()
        if existing:
            raise ValidationError(f'A {model_class.__name__.lower()} with this name already exists.')

    @staticmethod
    def validate_iso3_unique(field, exclude_id=None):
        """Validates that ISO3 code is unique."""
        query = Country.query.filter_by(iso3=field.data.upper())
        if exclude_id:
            query = query.filter(Country.id != exclude_id)
        existing = query.first()
        if existing:
            raise ValidationError('A country with this ISO3 code already exists.')

    @staticmethod
    def validate_age_groups_config(field, selected_disaggregation_options, indicator_unit, indicator_type):
        """Validates custom age groups configuration."""
        # Check if age disaggregation is selected
        age_disaggregation_selected = 'age' in selected_disaggregation_options or 'sex_age' in selected_disaggregation_options

        # Check if the unit supports age disaggregation
        from app.utils.indicator_utils import supports_disaggregation
        allows_age_disaggregation_unit = indicator_unit and supports_disaggregation(indicator_unit, indicator_type)

        # If age disaggregation is selected but the unit doesn't support it
        if age_disaggregation_selected and not allows_age_disaggregation_unit:
            raise ValidationError(f"Age disaggregation is only allowed for indicators with units 'people', 'volunteers', or 'staff'. This indicator has unit '{indicator_unit or 'N/A'}'.")

        # Validate format if custom age groups are provided
        if field.data and field.data.strip():
            parts = [part.strip() for part in field.data.split(',')]
            if not all(parts):
                raise ValidationError('Custom age groups must not contain empty parts. Ensure format is like "0-4,5-9".')
            for part in parts:
                # Basic check for valid characters in age groups
                if not all(c.isalnum() or c in ['-', '+', '<', '>', '=', ' '] for c in part):
                    raise ValidationError(f"Custom age group '{part}' contains invalid characters.")


# ========== FORM MIXINS ==========

class MultilingualFieldsMixin:
    """Mixin to add multilingual field support to forms.

    WTForms binds fields defined on the class at construction time. To ensure
    multilingual fields are properly bound (with .data, .label, etc.), we add
    them as UnboundFields on the class before calling the base __init__.
    """

    @staticmethod
    def _rebuild_unbound_fields(form_cls) -> None:
        """Rebuild WTForms `_unbound_fields` after dynamically adding fields.

        WTForms FormMeta computes `_unbound_fields` at the start of instantiation.
        If fields are added at runtime, WTForms may mark `_unbound_fields` as None,
        which breaks form initialization (it tries to iterate None).
        """
        try:
            fields = []
            for name in dir(form_cls):
                if name.startswith("_"):
                    continue
                unbound_field = getattr(form_cls, name, None)
                if hasattr(unbound_field, "_formfield"):
                    fields.append((name, unbound_field))
            # Stable sort: creation order, then name
            fields.sort(key=lambda x: (x[1].creation_counter, x[0]))
            form_cls._unbound_fields = fields
        except Exception as e:
            logging.getLogger(__name__).debug("_rebuild_unbound_fields fallback: %s", e)
            # Fallback: keep at least an empty list to avoid NoneType iteration
            form_cls._unbound_fields = []

    def add_multilingual_name_fields(self, base_field_name="name", max_length=100):
        """Declare multilingual name fields on the class so WTForms binds them.

        Generates code-suffixed fields only (e.g., `_fr`, `_es`, `_ar`).
        """
        added_any = False
        for lang_code in _get_translatable_language_codes():
            lang_name = _get_language_display_name(lang_code)
            # Variant 1: code suffix (e.g., name_fr)
            field_name_code = f'{base_field_name}_{lang_code}'
            if not hasattr(self.__class__, field_name_code):
                setattr(
                    self.__class__,
                    field_name_code,
                    StringField(
                        f"{base_field_name.title()} ({lang_name})",
                        validators=[Optional(), Length(max=max_length)]
                    ),
                )
                added_any = True

        # WTForms may set `_unbound_fields` to None when fields are added dynamically.
        # Rebuild before the base `__init__` binds fields to avoid NoneType iteration.
        if added_any or getattr(self.__class__, "_unbound_fields", None) is None:
            self._rebuild_unbound_fields(self.__class__)


class LayoutFieldsMixin:
    """Mixin to add layout fields to forms."""

    def add_layout_fields(self):
        """Add layout configuration fields to the form."""
        for field_name, field_def in CommonFields.LAYOUT_FIELDS.items():
            if not hasattr(self, field_name):
                setattr(self, field_name, field_def)


class DataAvailabilityMixin:
    """Mixin to add data availability fields to forms."""

    def add_data_availability_fields(self):
        """Add data availability configuration fields to the form."""
        for field_name, field_def in CommonFields.DATA_AVAILABILITY_FIELDS.items():
            if not hasattr(self, field_name):
                setattr(self, field_name, field_def)


class SkipLogicMixin:
    """Mixin to add skip logic fields to forms."""

    def add_skip_logic_fields(self):
        """Add skip logic configuration fields to the form."""
        for field_name, field_def in CommonFields.SKIP_LOGIC_FIELDS.items():
            if not hasattr(self, field_name):
                setattr(self, field_name, field_def)
