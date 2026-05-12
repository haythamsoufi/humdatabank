# ========== File: app/forms/system/country_forms.py ==========
"""
Country management forms for the platform.
"""

from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField, SelectField, BooleanField
from wtforms.validators import DataRequired, Optional, Length, ValidationError
from app.models import Country
from ..base import BaseForm, MultilingualFieldsMixin, CommonValidators
from config import Config


class CountryForm(BaseForm, MultilingualFieldsMixin):
    """Form for adding or editing a Country."""

    name = StringField("Country Name", validators=[DataRequired(), Length(min=2, max=100)])
    short_name = StringField("Short Name", validators=[Optional(), Length(max=50)])
    iso3 = StringField("ISO3 Code", validators=[DataRequired(), Length(min=3, max=3, message="ISO3 code must be exactly 3 characters.")])
    national_society_name = StringField("National Society Name", validators=[Optional(), Length(max=255)])

    # Additional fields
    status = SelectField("Status", choices=[("Active", "Active"), ("Inactive", "Inactive")], validators=[Optional()], default="Active")
    # Store ISO codes (e.g. "en", "fr") so orgs can use any language without schema changes.
    # Choices are populated dynamically in __init__ from Config.ALL_LANGUAGES_DISPLAY_NAMES.
    preferred_language = SelectField("Preferred Language", choices=[], validators=[Optional()], default="en")
    currency_code = StringField("Currency Code", validators=[Optional(), Length(max=3)])

    submit = SubmitField("Save Country")

    def __init__(self, *args, **kwargs):
        # Extract original_country_id for validation
        self.original_country_id = kwargs.pop('original_country_id', None)

        # Ensure multilingual UnboundFields exist on the class before binding
        self.add_multilingual_name_fields("name", max_length=100)
        self.add_multilingual_name_fields("national_society_name", max_length=255)

        # Now let WTForms bind fields
        super(CountryForm, self).__init__(*args, **kwargs)

        # Populate language choices (ISO-639-1)
        all_names = getattr(Config, "ALL_LANGUAGES_DISPLAY_NAMES", {}) or {}
        # Always include English first if present
        codes = sorted(all_names.keys(), key=lambda c: all_names.get(c, c).lower())
        if "en" in codes:
            codes.remove("en")
            codes.insert(0, "en")
        self.preferred_language.choices = [(c, all_names.get(c, c.upper())) for c in codes]

    def validate_iso3(self, field):
        """Validates that the ISO3 code is unique."""
        CommonValidators.validate_iso3_unique(field, self.original_country_id)
