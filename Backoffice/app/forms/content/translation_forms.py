# ========== File: app/forms/content/translation_forms.py ==========
"""
Translation management forms for the platform.
"""

import logging

from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Optional, Length
from ..base import BaseForm
from flask import current_app, has_app_context


def _get_enabled_language_codes():
    """Return enabled language codes, safe outside app context."""
    try:
        from config import Config as _FormConfig
    except Exception as e:
        logging.getLogger(__name__).debug("Config import fallback: %s", e)
        _FormConfig = None

    if has_app_context():
        langs = current_app.config.get("SUPPORTED_LANGUAGES") or []
    else:
        langs = []
    if not langs and _FormConfig is not None:
        langs = getattr(_FormConfig, "LANGUAGES", ["en"]) or ["en"]

    # Normalize to base ISO code
    normalized = []
    seen = set()
    for l in (langs or []):
        code = str(l or "").strip().lower().replace("-", "_").split("_", 1)[0]
        if not code or code in seen:
            continue
        seen.add(code)
        normalized.append(code)
    if "en" not in seen:
        normalized.insert(0, "en")
    return normalized


def _add_translation_fields_to_class(cls, languages=None):
    """Add msgstr_<lang> translation fields to the form class.

    Must run before WTForms binds fields (i.e., before BaseForm.__init__).
    """
    try:
        from config import Config as _FormConfig
        _lang_names = getattr(_FormConfig, 'LANGUAGE_DISPLAY_NAMES', {}) or {}
        _all_lang_names = getattr(_FormConfig, 'ALL_LANGUAGES_DISPLAY_NAMES', {}) or {}
        _languages = languages or getattr(_FormConfig, 'LANGUAGES', ['en'])
    except Exception as e:
        logging.getLogger(__name__).debug("_add_translation_fields config fallback: %s", e)
        _lang_names = {'en': 'English'}
        _all_lang_names = {}
        _languages = ['en']

    # Create fields as class attributes so WTForms can properly bind them
    for _code in _languages:
        display = _lang_names.get(_code) or _all_lang_names.get(_code) or _code.upper()
        _label = f"{display} Translation"
        field_name = f'msgstr_{_code}'
        if not hasattr(cls, field_name):
            setattr(cls, field_name,
                   TextAreaField(_label, validators=[Optional(), Length(max=1000)]))

    return cls


def _rebuild_unbound_fields(cls) -> None:
    """Rebuild WTForms `_unbound_fields` after dynamically adding fields.

    WTForms FormMeta computes `_unbound_fields` at the start of instantiation.
    If we add fields during `__init__`, FormMeta marks `_unbound_fields` as None,
    which breaks Form initialization. We fix that by rebuilding the list before
    calling the base `__init__`.
    """
    try:
        fields = []
        for name in dir(cls):
            if name.startswith("_"):
                continue
            unbound_field = getattr(cls, name, None)
            if hasattr(unbound_field, "_formfield"):
                fields.append((name, unbound_field))
        fields.sort(key=lambda x: (x[1].creation_counter, x[0]))
        cls._unbound_fields = fields
    except Exception as e:
        logging.getLogger(__name__).debug("_rebuild_unbound_fields fallback: %s", e)
        # Fallback: keep at least an empty list to avoid NoneType iteration
        cls._unbound_fields = []


class TranslationForm(BaseForm):
    """Form for managing translations for all languages."""

    msgid = StringField("Message ID", validators=[DataRequired(), Length(max=500)])
    submit = SubmitField("Save Translation")
    delete = SubmitField("Delete Translation")

    def __init__(self, *args, **kwargs):
        # Attach language fields dynamically based on runtime enabled languages
        # (supports newly added languages without code/migrations).
        langs = _get_enabled_language_codes()
        _add_translation_fields_to_class(self.__class__, langs)
        _rebuild_unbound_fields(self.__class__)
        super().__init__(*args, **kwargs)
