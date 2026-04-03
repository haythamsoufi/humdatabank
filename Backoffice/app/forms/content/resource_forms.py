# ========== File: app/forms/content/resource_forms.py ==========
"""
Resource management forms for the platform.
"""

import logging

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, SubmitField, SelectField, DateField
from wtforms.validators import DataRequired, Optional, Length
from ..base import BaseForm, MultilingualForm, FileUploadForm, _get_language_display_name


def _add_language_fields_to_class(cls):
    """Add language-specific fields to the form class before it's instantiated"""
    from config import Config
    from flask_wtf.file import FileAllowed
    languages = getattr(Config, 'LANGUAGES', ['en'])

    # Language display names mapping
    lang_names = {
        'en': 'English', 'fr': 'French', 'es': 'Spanish', 'ar': 'Arabic',
        'ru': 'Russian', 'zh': 'Chinese', 'hi': 'Hindi'
    }

    # Define validators (same as in FileUploadForm base class)
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

    # Create fields as class attributes so WTForms can properly bind them
    for lang_code in languages:
        lang_name = lang_names.get(lang_code, lang_code.upper())

        # Title field
        title_field_name = f'title_{lang_code}'
        if not hasattr(cls, title_field_name):
            setattr(cls, title_field_name,
                   StringField(f"Title ({lang_name})",
                              validators=[Optional(), Length(max=255)]))

        # Description field
        desc_field_name = f'description_{lang_code}'
        if not hasattr(cls, desc_field_name):
            setattr(cls, desc_field_name,
                   TextAreaField(f"Description ({lang_name})",
                                validators=[Optional(), Length(max=2000)]))

        # Document field
        doc_field_name = f'document_{lang_code}'
        if not hasattr(cls, doc_field_name):
            setattr(cls, doc_field_name,
                   FileField(f"Document File ({lang_name}) - PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT",
                            validators=document_validators))

        # Thumbnail field
        thumb_field_name = f'thumbnail_{lang_code}'
        if not hasattr(cls, thumb_field_name):
            setattr(cls, thumb_field_name,
                   FileField(f"Thumbnail Image ({lang_name}) - JPG, PNG, GIF, WEBP",
                            validators=image_validators))

    return cls


@_add_language_fields_to_class
class ResourceForm(MultilingualForm, FileUploadForm):
    """Form for managing resources and publications."""

    # Resource type selection
    resource_type = SelectField(
        "Resource Type",
        choices=[('publication', 'Publication'), ('other', 'Other')],
        validators=[DataRequired()],
        default='publication'
    )

    publication_date = DateField("Publication Date (Optional)", format='%Y-%m-%d', validators=[Optional()])

    # Default language (English) fields
    default_title = StringField("Default Title (English)", validators=[DataRequired(), Length(max=255)])
    default_description = TextAreaField("Default Description (English)", validators=[Optional(), Length(max=2000)])

    submit = SubmitField("Save Resource")

    def __init__(self, *args, **kwargs):
        # Get languages first (before calling super) by calling the function directly
        from ..base import _get_supported_language_codes
        runtime_languages = _get_supported_language_codes()

        # Add missing language fields to the class if needed
        ResourceForm._add_missing_language_fields_to_class(runtime_languages)

        super(ResourceForm, self).__init__(*args, **kwargs)

    @classmethod
    def _add_missing_language_fields_to_class(cls, languages):
        """Dynamically add language fields to the class for any languages that don't exist yet."""
        from flask_wtf.file import FileAllowed

        # Define validators (same as in FileUploadForm base class)
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

        # Create fields for any languages that don't exist yet on the class
        for lang_code in languages:
            lang_name = _get_language_display_name(lang_code)

            # Title field
            title_field_name = f'title_{lang_code}'
            if not hasattr(cls, title_field_name):
                setattr(cls, title_field_name,
                       StringField(f"Title ({lang_name})",
                                  validators=[Optional(), Length(max=255)]))

            # Description field
            desc_field_name = f'description_{lang_code}'
            if not hasattr(cls, desc_field_name):
                setattr(cls, desc_field_name,
                       TextAreaField(f"Description ({lang_name})",
                                    validators=[Optional(), Length(max=2000)]))

            # Document field
            doc_field_name = f'document_{lang_code}'
            if not hasattr(cls, doc_field_name):
                setattr(cls, doc_field_name,
                       FileField(f"Document File ({lang_name}) - PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT",
                                validators=document_validators))

            # Thumbnail field
            thumb_field_name = f'thumbnail_{lang_code}'
            if not hasattr(cls, thumb_field_name):
                setattr(cls, thumb_field_name,
                       FileField(f"Thumbnail Image ({lang_name}) - JPG, PNG, GIF, WEBP",
                                validators=image_validators))

        # Rebuild unbound fields for WTForms
        cls._rebuild_unbound_fields()

    @classmethod
    def _rebuild_unbound_fields(cls):
        """Rebuild WTForms `_unbound_fields` after dynamically adding fields."""
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
            if not hasattr(cls, '_unbound_fields'):
                cls._unbound_fields = []
