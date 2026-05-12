# ========== File: app/forms/system/indicator_bank_forms.py ==========
"""
Indicator Bank, Sector, and Common Word management forms for the platform.
These forms are grouped together as they are all related to indicator bank functionality.
"""

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, SubmitField, SelectField, BooleanField, IntegerField
from wtforms.validators import DataRequired, Optional, Length, ValidationError
from app.models import IndicatorBank, Sector, SubSector, IndicatorBankType, IndicatorBankUnit
from ..base import BaseForm, MultilingualFieldsMixin, FileUploadForm, CommonValidators, int_or_none


class IndicatorBankForm(BaseForm, MultilingualFieldsMixin):
    """Form for adding or editing an IndicatorBank entry."""

    name = StringField("Indicator Name", validators=[DataRequired(), Length(max=255)])
    # Central catalog IDs (see IndicatorBankType / IndicatorBankUnit)
    type = SelectField("Type", coerce=int, validators=[DataRequired()])
    unit = SelectField("Unit", coerce=int_or_none, validators=[Optional()])
    fdrs_kpi_code = StringField("FDRS KPI Code", validators=[Optional(), Length(max=50)],
                                render_kw={"placeholder": "e.g., FDRS KPI code"})
    definition = TextAreaField("Definition", validators=[Optional()],
                              render_kw={"rows": 4, "placeholder": "Detailed definition of this indicator"})

    # Management fields
    archived = BooleanField("Archived", default=False)
    emergency = BooleanField("Emergency Indicator", default=False)
    comments = TextAreaField("Comments", validators=[Optional()],
                            render_kw={"rows": 3, "placeholder": "Internal comments about this indicator"})
    related_programs = StringField("Related Programs", validators=[Optional()],
                                  render_kw={"placeholder": "Comma-separated list of related programs"})

    # Sector fields - Primary/Secondary/Tertiary (dropdowns)
    sector_primary = SelectField("Sector - Primary", coerce=int_or_none, validators=[Optional()])
    sector_secondary = SelectField("Sector - Secondary", coerce=int_or_none, validators=[Optional()])
    sector_tertiary = SelectField("Sector - Tertiary", coerce=int_or_none, validators=[Optional()])

    # Sub-Sector fields - Primary/Secondary/Tertiary (dropdowns)
    sub_sector_primary = SelectField("Sub-Sector - Primary", coerce=int_or_none, validators=[Optional()])
    sub_sector_secondary = SelectField("Sub-Sector - Secondary", coerce=int_or_none, validators=[Optional()])
    sub_sector_tertiary = SelectField("Sub-Sector - Tertiary", coerce=int_or_none, validators=[Optional()])

    submit = SubmitField("Save Indicator")

    def __init__(self, *args, **kwargs):
        # Ensure multilingual UnboundFields exist on the class before binding.
        # This makes the form future-proof: when an org enables a new language,
        # the corresponding name_<lang> field exists without schema changes.
        self.add_multilingual_name_fields("name", max_length=255)
        super(IndicatorBankForm, self).__init__(*args, **kwargs)
        # Populate choices after form is initialized
        self._populate_choices()

    def _populate_choices(self):
        """Populate the sector and subsector choices"""
        try:
            from app.routes.admin.shared import get_localized_sector_name, get_localized_subsector_name

            mtypes = (
                IndicatorBankType.query.filter_by(is_active=True)
                .order_by(IndicatorBankType.sort_order, IndicatorBankType.name)
                .all()
            )
            self.type.choices = [(t.id, t.name) for t in mtypes]
            munits = (
                IndicatorBankUnit.query.filter_by(is_active=True)
                .order_by(IndicatorBankUnit.sort_order, IndicatorBankUnit.name)
                .all()
            )
            self.unit.choices = [(None, "-- No unit --")] + [(u.id, u.name) for u in munits]

            # Get active sectors
            sectors = Sector.query.filter_by(is_active=True).order_by(Sector.display_order, Sector.name).all()
            sector_choices = [(None, "-- Select Sector --")] + [
                (s.id, get_localized_sector_name(s)) for s in sectors
            ]
            self.sector_primary.choices = sector_choices
            self.sector_secondary.choices = sector_choices
            self.sector_tertiary.choices = sector_choices

            # Get active subsectors
            subsectors = SubSector.query.filter_by(is_active=True).order_by(SubSector.display_order, SubSector.name).all()
            subsector_choices = [(None, "-- Select Sub-Sector --")] + [
                (s.id, get_localized_subsector_name(s)) for s in subsectors
            ]
            self.sub_sector_primary.choices = subsector_choices
            self.sub_sector_secondary.choices = subsector_choices
            self.sub_sector_tertiary.choices = subsector_choices

        except Exception as e:
            # Log the error properly
            import logging
            logging.error(f"Error populating sector/subsector choices: {e}")
            # Fallback to empty choices if there's an error
            empty_choices = [(None, "-- Select Sector --")]
            self.sector_primary.choices = empty_choices
            self.sector_secondary.choices = empty_choices
            self.sector_tertiary.choices = empty_choices

            empty_subsector_choices = [(None, "-- Select Sub-Sector --")]
            self.sub_sector_primary.choices = empty_subsector_choices
            self.sub_sector_secondary.choices = empty_subsector_choices
            self.sub_sector_tertiary.choices = empty_subsector_choices

    def populate_from_indicator_bank(self, indicator_bank):
        """Populates the form fields from an IndicatorBank instance."""
        # Ensure choices are populated before setting data
        self._populate_choices()

        from app.services.indicator_measurement_sync import (
            resolve_type_id_for_legacy_string,
            resolve_unit_id_for_legacy_string,
        )

        self.name.data = indicator_bank.name
        tid = indicator_bank.indicator_type_id
        if not tid and indicator_bank.type:
            tid = resolve_type_id_for_legacy_string(indicator_bank.type)
        self.type.data = tid
        uid = indicator_bank.indicator_unit_id
        if not uid and indicator_bank.unit:
            uid = resolve_unit_id_for_legacy_string(indicator_bank.unit)
        self.unit.data = uid
        self.fdrs_kpi_code.data = getattr(indicator_bank, 'fdrs_kpi_code', None) or ''
        self.definition.data = indicator_bank.definition

        # Populate multilingual fields from JSONB translations (do not fall back to English)
        translations = indicator_bank.name_translations if isinstance(indicator_bank.name_translations, dict) else {}
        try:
            from flask import current_app
            langs = current_app.config.get("TRANSLATABLE_LANGUAGES") or []
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug("TRANSLATABLE_LANGUAGES fallback: %s", e)
            langs = []
        for lang in langs:
            field = getattr(self, f"name_{lang}", None)
            if field is not None:
                val = translations.get(lang, "")
                field.data = val if isinstance(val, str) else ""

        self.archived.data = indicator_bank.archived
        self.emergency.data = indicator_bank.emergency
        self.comments.data = indicator_bank.comments
        self.related_programs.data = indicator_bank.related_programs

        # Handle sector data - convert from ID to ID (no change needed now)
        if indicator_bank.sector:
            self.sector_primary.data = indicator_bank.sector.get('primary')
            self.sector_secondary.data = indicator_bank.sector.get('secondary')
            self.sector_tertiary.data = indicator_bank.sector.get('tertiary')

        # Handle sub-sector data - convert from ID to ID (no change needed now)
        if indicator_bank.sub_sector:
            self.sub_sector_primary.data = indicator_bank.sub_sector.get('primary')
            self.sub_sector_secondary.data = indicator_bank.sub_sector.get('secondary')
            self.sub_sector_tertiary.data = indicator_bank.sub_sector.get('tertiary')

    def populate_indicator_bank(self, indicator_bank):
        """Populates an IndicatorBank instance from the form data."""
        indicator_bank.name = self.name.data
        indicator_bank.indicator_type_id = self.type.data
        indicator_bank.indicator_unit_id = self.unit.data
        indicator_bank.sync_type_unit_string_columns()
        indicator_bank.fdrs_kpi_code = (self.fdrs_kpi_code.data or '').strip() or None
        indicator_bank.definition = self.definition.data

        # Populate multilingual fields using the proper setter methods
        try:
            from flask import current_app
            langs = current_app.config.get("TRANSLATABLE_LANGUAGES") or []
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug("TRANSLATABLE_LANGUAGES fallback: %s", e)
            langs = []
        for lang in langs:
            field = getattr(self, f"name_{lang}", None)
            if field is not None:
                indicator_bank.set_name_translation(lang, field.data or "")

        indicator_bank.archived = self.archived.data
        indicator_bank.emergency = self.emergency.data
        indicator_bank.comments = self.comments.data
        indicator_bank.related_programs = self.related_programs.data

        # Handle sector data - store IDs directly
        sector_data = {}
        if self.sector_primary.data:
            sector_data['primary'] = self.sector_primary.data
        if self.sector_secondary.data:
            sector_data['secondary'] = self.sector_secondary.data
        if self.sector_tertiary.data:
            sector_data['tertiary'] = self.sector_tertiary.data
        indicator_bank.sector = sector_data if sector_data else None

        # Handle sub-sector data - store IDs directly
        sub_sector_data = {}
        if self.sub_sector_primary.data:
            sub_sector_data['primary'] = self.sub_sector_primary.data
        if self.sub_sector_secondary.data:
            sub_sector_data['secondary'] = self.sub_sector_secondary.data
        if self.sub_sector_tertiary.data:
            sub_sector_data['tertiary'] = self.sub_sector_tertiary.data
        indicator_bank.sub_sector = sub_sector_data if sub_sector_data else None


class SectorForm(FileUploadForm, MultilingualFieldsMixin):
    """Form for adding or editing a Sector."""

    name = StringField("Sector Name", validators=[DataRequired(), Length(max=100)])
    description = TextAreaField("Description", validators=[Optional()],
                               render_kw={"rows": 3, "placeholder": "Brief description of this sector"})
    display_order = IntegerField("Display Order", validators=[Optional()], default=0,
                                render_kw={"placeholder": "Order for sorting (0 = first)"})
    is_active = BooleanField("Active", default=True)

    # Logo upload
    logo_file = FileField(
        "Logo Image (JPG, PNG, GIF, WEBP, SVG)",
        validators=FileUploadForm.image_validators
    )

    # Icon fallback
    icon_class = StringField("FontAwesome Icon Class (fallback)", validators=[Optional(), Length(max=50)],
                            render_kw={"placeholder": "e.g., fas fa-heart"})

    submit = SubmitField("Save Sector")

    def __init__(self, *args, original_sector_id=None, **kwargs):
        # Create code-suffixed fields (name_fr, name_es, ...) based on runtime settings.
        self.add_multilingual_name_fields("name", max_length=100)
        super(SectorForm, self).__init__(*args, **kwargs)
        self.original_sector_id = original_sector_id

    def validate_name(self, field):
        """Validates that the sector name is unique."""
        CommonValidators.validate_unique_name(Sector, field, self.original_sector_id)


class SubSectorForm(FileUploadForm, MultilingualFieldsMixin):
    """Form for adding or editing a SubSector."""

    name = StringField("Sub-Sector Name", validators=[DataRequired(), Length(max=100)])
    description = TextAreaField("Description", validators=[Optional()],
                               render_kw={"rows": 3, "placeholder": "Brief description of this sub-sector"})
    sector_id = SelectField("Parent Sector (Optional)", coerce=int_or_none, validators=[Optional()])
    display_order = IntegerField("Display Order", validators=[Optional()], default=0,
                                render_kw={"placeholder": "Order for sorting (0 = first)"})
    is_active = BooleanField("Active", default=True)

    # Logo upload
    logo_file = FileField(
        "Logo Image (JPG, PNG, GIF, WEBP, SVG)",
        validators=FileUploadForm.image_validators
    )

    # Icon fallback
    icon_class = StringField("FontAwesome Icon Class (fallback)", validators=[Optional(), Length(max=50)],
                            render_kw={"placeholder": "e.g., fas fa-stethoscope"})

    submit = SubmitField("Save Sub-Sector")

    def __init__(self, *args, original_subsector_id=None, **kwargs):
        # Create code-suffixed fields (name_fr, name_es, ...) based on runtime settings.
        self.add_multilingual_name_fields("name", max_length=100)
        super(SubSectorForm, self).__init__(*args, **kwargs)
        self.original_subsector_id = original_subsector_id

        # Populate sector choices
        from app.routes.admin.shared import get_localized_sector_name
        self.sector_id.choices = [(None, "-- No Parent Sector --")] + [
            (s.id, get_localized_sector_name(s)) for s in Sector.query.filter_by(is_active=True).order_by(Sector.display_order, Sector.name).all()
        ]

    def validate_name(self, field):
        """Validates that the sub-sector name is unique."""
        CommonValidators.validate_unique_name(SubSector, field, self.original_subsector_id)


class CommonWordForm(BaseForm, MultilingualFieldsMixin):
    """Form for adding or editing a CommonWord entry."""

    term = StringField("Term", validators=[DataRequired(), Length(max=255)],
                      render_kw={"placeholder": "e.g., Emergency, Response, Humanitarian"})
    meaning = TextAreaField("Meaning", validators=[DataRequired()],
                           render_kw={"rows": 4, "placeholder": "Definition or explanation of this term"})

    is_active = BooleanField("Active", default=True)

    submit = SubmitField("Save Common Word")

    def __init__(self, *args, **kwargs):
        # Create code-suffixed fields (meaning_fr, meaning_es, ...) based on runtime settings.
        self.add_multilingual_name_fields("meaning", max_length=2000)
        super(CommonWordForm, self).__init__(*args, **kwargs)

    def populate_common_word(self, common_word):
        """Populate the common word object with form data."""
        common_word.term = self.term.data
        common_word.meaning = self.meaning.data
        common_word.is_active = self.is_active.data

        # Set translations dynamically
        try:
            from flask import current_app
            langs = current_app.config.get("TRANSLATABLE_LANGUAGES") or []
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug("TRANSLATABLE_LANGUAGES fallback: %s", e)
            langs = []
        for lang in langs:
            field = getattr(self, f"meaning_{lang}", None)
            if field is not None:
                common_word.set_meaning_translation(lang, field.data or "")

    def populate_from_common_word(self, common_word):
        """Populate the form with data from an existing common word."""
        self.term.data = common_word.term
        self.meaning.data = common_word.meaning
        self.is_active.data = common_word.is_active

        # Get translations dynamically (do not fall back to English)
        translations = common_word.meaning_translations if isinstance(common_word.meaning_translations, dict) else {}
        try:
            from flask import current_app
            langs = current_app.config.get("TRANSLATABLE_LANGUAGES") or []
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug("TRANSLATABLE_LANGUAGES fallback: %s", e)
            langs = []
        for lang in langs:
            field = getattr(self, f"meaning_{lang}", None)
            if field is not None:
                val = translations.get(lang, "")
                field.data = val if isinstance(val, str) else ""
