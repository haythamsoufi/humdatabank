# ========== File: app/forms/system/indicator_bank_forms.py ==========
"""
Indicator Bank, Sector, and Common Word management forms for the platform.
These forms are grouped together as they are all related to indicator bank functionality.
"""

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from app.utils.request_utils import get_request_data
from wtforms import StringField, TextAreaField, SubmitField, SelectField, BooleanField, IntegerField
from wtforms.validators import DataRequired, Optional, Length, ValidationError
from sqlalchemy.orm.attributes import flag_modified
from app.extensions import db
from app.models import (
    IndicatorBank,
    IndicatorBankSpef,
    IndicatorBankType,
    IndicatorBankUnit,
    Sector,
    SubSector,
)
from ..base import BaseForm, MultilingualFieldsMixin, FileUploadForm, CommonValidators, int_or_none


def _split_csv_tags(value):
    if not value:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _join_csv_tags(tags):
    if not tags:
        return ""
    if isinstance(tags, list):
        return ", ".join(str(t).strip() for t in tags if str(t).strip())
    return str(tags).strip()


def _optional_area_code(value):
    """Coerce SelectField value to a SPEF code string, or empty string when cleared."""
    if value is None:
        return ""
    return str(value).strip()


def _spef_choice_label(code, name=None):
    code = (code or "").strip()
    name = (name or "").strip()
    if code and name:
        return f"{code} — {name}"
    return code or name or ""


class IndicatorBankForm(BaseForm, MultilingualFieldsMixin):
    """Form for adding or editing an IndicatorBank entry."""

    name = TextAreaField(
        "Indicator Name",
        validators=[DataRequired(), Length(max=255)],
        render_kw={"rows": 3, "placeholder": "Indicator name"},
    )
    # Central catalog IDs (see IndicatorBankType / IndicatorBankUnit)
    type = SelectField("Type", coerce=int, validators=[DataRequired()])
    unit = SelectField("Unit", coerce=int_or_none, validators=[Optional()])
    fdrs_kpi_code = StringField("FDRS KPI Code", validators=[Optional(), Length(max=50)],
                                render_kw={"placeholder": "e.g., FDRS KPI code"})
    definition = TextAreaField("Definition", validators=[Optional()],
                              render_kw={"rows": 4, "placeholder": "Detailed definition of this indicator"})
    aggregated_label = TextAreaField(
        "Aggregated Label",
        validators=[Optional()],
        render_kw={
            "rows": 3,
            "placeholder": "e.g., Number of National Societies that develop and/or implement a strategy…",
        },
    )
    # SPEF area code from IndicatorBankSpef catalog (denormalized onto IndicatorBank.area)
    area = SelectField(
        "Area",
        coerce=_optional_area_code,
        validators=[Optional()],
        choices=[],
    )
    data_source = TextAreaField(
        "Data Source",
        validators=[Optional()],
        render_kw={"rows": 3, "placeholder": "Where this indicator's data comes from"},
    )
    disaggregation_guidance = TextAreaField(
        "Disaggregation Guidance",
        validators=[Optional()],
        render_kw={"rows": 3, "placeholder": "e.g., SAD, sex/age breakdown guidance from IFRC"},
    )
    tags = StringField(
        "Tags",
        validators=[Optional()],
        render_kw={"placeholder": "Comma-separated tags"},
    )

    # Management fields
    archived = BooleanField("Archived", default=False)
    emergency = BooleanField("Emergency Indicator", default=False)
    comments = TextAreaField("Comments", validators=[Optional()],
                            render_kw={"rows": 3, "placeholder": "Internal comments about this indicator"})

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
        self.add_multilingual_name_fields("name", max_length=255, use_textarea=True, textarea_rows=3)
        self.add_multilingual_name_fields("aggregated_label", max_length=2000, use_textarea=True, textarea_rows=3)
        super(IndicatorBankForm, self).__init__(*args, **kwargs)
        self._populate_choices()

    def _populate_choices(self):
        """Populate type/unit/SPEF area and sector/subsector choices."""
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

            spef_rows = (
                IndicatorBankSpef.query.filter_by(is_active=True)
                .order_by(IndicatorBankSpef.sort_order, IndicatorBankSpef.code)
                .all()
            )
            self.area.choices = [("", "-- Select Area --")] + [
                (row.code, _spef_choice_label(row.code, row.name)) for row in spef_rows
            ]

            sectors = Sector.query.filter_by(is_active=True).order_by(Sector.display_order, Sector.name).all()
            sector_choices = [(None, "-- Select Sector --")] + [
                (s.id, get_localized_sector_name(s)) for s in sectors
            ]
            self.sector_primary.choices = sector_choices
            self.sector_secondary.choices = sector_choices
            self.sector_tertiary.choices = sector_choices

            subsectors = SubSector.query.filter_by(is_active=True).order_by(SubSector.display_order, SubSector.name).all()
            subsector_choices = [(None, "-- Select Sub-Sector --")] + [
                (s.id, get_localized_subsector_name(s)) for s in subsectors
            ]
            self.sub_sector_primary.choices = subsector_choices
            self.sub_sector_secondary.choices = subsector_choices
            self.sub_sector_tertiary.choices = subsector_choices

        except Exception as e:
            import logging
            logging.error(f"Error populating sector/subsector choices: {e}")
            self.area.choices = [("", "-- Select Area --")]
            empty_choices = [(None, "-- Select Sector --")]
            self.sector_primary.choices = empty_choices
            self.sector_secondary.choices = empty_choices
            self.sector_tertiary.choices = empty_choices

            empty_subsector_choices = [(None, "-- Select Sub-Sector --")]
            self.sub_sector_primary.choices = empty_subsector_choices
            self.sub_sector_secondary.choices = empty_subsector_choices
            self.sub_sector_tertiary.choices = empty_subsector_choices

    def _ensure_area_choice(self, code, label=None):
        """Keep a legacy/inactive SPEF code selectable when editing an existing indicator."""
        code = (code or "").strip()
        if not code:
            return
        existing = {choice_code for choice_code, _label in (self.area.choices or [])}
        if code in existing:
            return
        self.area.choices = list(self.area.choices or [("", "-- Select Area --")]) + [
            (code, label or code)
        ]

    @staticmethod
    def _resolve_spef_by_code(code):
        code = (code or "").strip()
        if not code:
            return None
        return (
            IndicatorBankSpef.query
            .filter(db.func.upper(IndicatorBankSpef.code) == code.upper())
            .first()
        )

    def _apply_area_selection(self, indicator_bank):
        """Set SPEF FK and denormalized area/area_label from the selected catalog code."""
        code = (self.area.data or "").strip() or None
        if not code:
            indicator_bank.indicator_spef_id = None
            indicator_bank.area = None
            indicator_bank.area_label = None
            return

        spef = self._resolve_spef_by_code(code)
        if spef is not None:
            indicator_bank.indicator_spef_id = spef.id
            indicator_bank.area = (spef.code or "")[:16]
            indicator_bank.area_label = spef.name
            return

        # Selected value is not in the catalog (should be rare with a select); keep the code only.
        indicator_bank.indicator_spef_id = None
        indicator_bank.area = code[:16]
        indicator_bank.area_label = None

    def _translatable_languages(self):
        try:
            from flask import current_app
            return current_app.config.get("TRANSLATABLE_LANGUAGES") or []
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug("TRANSLATABLE_LANGUAGES fallback: %s", e)
            return []

    def _populate_multilingual_field(self, translations, field_prefix):
        langs = self._translatable_languages()
        for lang in langs:
            field = getattr(self, f"{field_prefix}_{lang}", None)
            if field is not None:
                val = (translations or {}).get(lang, "")
                field.data = val if isinstance(val, str) else ""

    def _apply_multilingual_field(self, indicator, field_prefix, setter_name):
        langs = self._translatable_languages()
        setter = getattr(indicator, setter_name)
        for lang in langs:
            field = getattr(self, f"{field_prefix}_{lang}", None)
            if field is not None:
                setter(lang, field.data or "")

    @staticmethod
    def _non_empty_values_from_request(field_name):
        data = get_request_data()
        return [str(value).strip() for value in data.getlist(field_name) if value and str(value).strip()]

    @classmethod
    def monitoring_questions_from_request(cls):
        values = cls._non_empty_values_from_request("monitoring_questions")
        return values or None

    @classmethod
    def related_programs_from_request(cls):
        values = cls._non_empty_values_from_request("related_programs")
        return values or None

    def populate_from_indicator_bank(self, indicator_bank):
        """Populates the form fields from an IndicatorBank instance."""
        self._populate_choices()

        from app.services.indicators.measurement_sync import (
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
        self.aggregated_label.data = indicator_bank.aggregated_label or ''
        area_code = (indicator_bank.area or '').strip()
        if not area_code and getattr(indicator_bank, 'spef_area', None) is not None:
            area_code = (indicator_bank.spef_area.code or '').strip()
        self._ensure_area_choice(
            area_code,
            _spef_choice_label(area_code, getattr(indicator_bank, 'area_label', None)),
        )
        self.area.data = area_code
        self.data_source.data = indicator_bank.data_source or ''
        self.disaggregation_guidance.data = indicator_bank.disaggregation_guidance or ''
        self.tags.data = _join_csv_tags(indicator_bank.tags_list)

        translations = indicator_bank.name_translations if isinstance(indicator_bank.name_translations, dict) else {}
        self._populate_multilingual_field(translations, "name")

        agg_translations = (
            indicator_bank.aggregated_label_translations
            if isinstance(indicator_bank.aggregated_label_translations, dict)
            else {}
        )
        self._populate_multilingual_field(agg_translations, "aggregated_label")

        self.archived.data = indicator_bank.archived
        self.emergency.data = indicator_bank.emergency
        self.comments.data = indicator_bank.comments

        if indicator_bank.sector:
            self.sector_primary.data = indicator_bank.sector.get('primary')
            self.sector_secondary.data = indicator_bank.sector.get('secondary')
            self.sector_tertiary.data = indicator_bank.sector.get('tertiary')

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
        indicator_bank.aggregated_label = (self.aggregated_label.data or '').strip() or None
        self._apply_area_selection(indicator_bank)
        indicator_bank.data_source = (self.data_source.data or '').strip() or None
        indicator_bank.disaggregation_guidance = (self.disaggregation_guidance.data or '').strip() or None
        indicator_bank.monitoring_questions = self.monitoring_questions_from_request()
        tag_list = _split_csv_tags(self.tags.data)
        indicator_bank.tags = tag_list or None

        self._apply_multilingual_field(indicator_bank, "name", "set_name_translation")
        self._apply_multilingual_field(indicator_bank, "aggregated_label", "set_aggregated_label_translation")
        flag_modified(indicator_bank, "name_translations")
        flag_modified(indicator_bank, "aggregated_label_translations")

        indicator_bank.archived = self.archived.data
        indicator_bank.emergency = self.emergency.data
        indicator_bank.comments = self.comments.data
        program_values = self._non_empty_values_from_request("related_programs")
        indicator_bank.related_programs_list = program_values or None

        sector_data = {}
        if self.sector_primary.data:
            sector_data['primary'] = self.sector_primary.data
        if self.sector_secondary.data:
            sector_data['secondary'] = self.sector_secondary.data
        if self.sector_tertiary.data:
            sector_data['tertiary'] = self.sector_tertiary.data
        indicator_bank.sector = sector_data if sector_data else None

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

    logo_file = FileField(
        "Logo Image (JPG, PNG, GIF, WEBP, SVG)",
        validators=FileUploadForm.image_validators
    )

    icon_class = StringField("FontAwesome Icon Class (fallback)", validators=[Optional(), Length(max=50)],
                            render_kw={"placeholder": "e.g., fas fa-heart"})

    submit = SubmitField("Save Sector")

    def __init__(self, *args, original_sector_id=None, **kwargs):
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

    icon_class = StringField("FontAwesome Icon Class", validators=[Optional(), Length(max=50)],
                            render_kw={"placeholder": "e.g., fas fa-stethoscope"})

    submit = SubmitField("Save Sub-Sector")

    def __init__(self, *args, original_subsector_id=None, **kwargs):
        self.add_multilingual_name_fields("name", max_length=100)
        super(SubSectorForm, self).__init__(*args, **kwargs)
        self.original_subsector_id = original_subsector_id

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
        self.add_multilingual_name_fields("meaning", max_length=2000)
        super(CommonWordForm, self).__init__(*args, **kwargs)

    def populate_common_word(self, common_word):
        """Populate the common word object with form data."""
        common_word.term = self.term.data
        common_word.meaning = self.meaning.data
        common_word.is_active = self.is_active.data

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
        flag_modified(common_word, "meaning_translations")

    def populate_from_common_word(self, common_word):
        """Populate the form with data from an existing common word."""
        self.term.data = common_word.term
        self.meaning.data = common_word.meaning
        self.is_active.data = common_word.is_active

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
