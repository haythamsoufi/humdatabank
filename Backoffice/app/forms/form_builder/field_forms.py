# ========== File: app/forms/form_builder/field_forms.py ==========
"""
Form field management forms for indicators, questions, documents, matrices, and plugin items.
"""

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, TextAreaField, SubmitField, SelectField, SelectMultipleField,
    BooleanField, FloatField, HiddenField, IntegerField
)
from wtforms.validators import DataRequired, Optional, Length, ValidationError
from wtforms.widgets import ListWidget, CheckboxInput
from app.models import IndicatorBank, QuestionType, LookupList
from config import Config
import json
import logging

logger = logging.getLogger(__name__)
from ..base import (
    BaseForm, MultilingualFieldsMixin, LayoutFieldsMixin, DataAvailabilityMixin,
    SkipLogicMixin, int_or_none, lookup_list_id_coerce, CommonValidators
)


class IndicatorForm(BaseForm, LayoutFieldsMixin, DataAvailabilityMixin, SkipLogicMixin):
    """Form for adding or editing an Indicator within a Form Template."""

    # Use the custom coerce function to handle potential None/empty string values
    indicator_bank_id = SelectField("Standard Indicator (from Bank)", coerce=int_or_none, validators=[DataRequired(message="Please select a standard indicator.")])
    # Use the custom coerce function for section_id as well
    section_id = SelectField("Section", coerce=int_or_none, validators=[DataRequired(message="Please select a section.")])
    order = FloatField("Order in Section (e.g., 1, 1.1, 1.2 for sub-indicators)", validators=[Optional()], default=0)
    is_required = BooleanField("Required Field", default=False)

    # Indicator-specific configuration fields
    allowed_disaggregation_options = SelectMultipleField(
        # MODIFIED LABEL: Updated label to reflect broader applicability
        'Allowed Disaggregation Options (only for number indicators with units like "people", "volunteers", "staff")',
        choices=list(Config.DISAGGREGATION_MODES.items()),
        widget=ListWidget(prefix_label=False),
        validators=[Optional()],
        default=["total"]
    )
    age_groups_config = StringField('Custom Age Groups (comma-separated). Leave empty for defaults if age disaggregation is allowed.', validators=[Optional()])

    submit = SubmitField("Save Indicator")

    def __init__(self, *args, **kwargs):
        # Extract indicator_bank_choices_with_unit from kwargs before calling super
        self._indicator_bank_choices_with_unit = kwargs.pop('indicator_bank_choices_with_unit', [])
        super(IndicatorForm, self).__init__(*args, **kwargs)

        # Add layout and data availability fields
        self.add_layout_fields()
        self.add_data_availability_fields()
        self.add_skip_logic_fields()

        choices = []
        try:
            # Use the list passed in kwargs if available, otherwise query the DB
            if self._indicator_bank_choices_with_unit:
                 choices = self._indicator_bank_choices_with_unit
            else:
                all_ib_objects = IndicatorBank.query.order_by(IndicatorBank.name).all()
                for ib in all_ib_objects:
                    if ib and hasattr(ib, 'id') and hasattr(ib, 'name') and hasattr(ib, 'type'):
                        # Store unit as a data attribute for JS access
                        choices.append({
                            'value': ib.id,
                            'label': ib.name,
                            'type': ib.type,
                            'unit': ib.unit if ib.unit else ''
                        })
        except Exception as e:
            logger.error("Could not populate IndicatorForm choices from IndicatorBank: %s", e, exc_info=True)

        # For WTForms SelectField, choices must be (value, label) tuples
        # Ensure value is string representation of ID or empty string for the default
        self.indicator_bank_id.choices = [(str(c['value']), c['label']) for c in choices] if choices else [("", "No standard indicators available")]
        self.section_id.choices = []  # Sections will be populated dynamically in the route

    def validate_age_groups_config(self, field):
        # Get the selected indicator bank item to check its unit
        selected_indicator_bank_id = self.indicator_bank_id.data
        indicator_from_bank = None
        if selected_indicator_bank_id is not None:
            # Try to find the indicator in the list passed via kwargs first
            selected_choice_data = next((item for item in self._indicator_bank_choices_with_unit if item['value'] == selected_indicator_bank_id), None)
            if selected_choice_data:
                 # Create a dummy object with necessary attributes for validation
                 class DummyIndicatorBank:
                     def __init__(self, id, name, type, unit):
                         self.id = id
                         self.name = name
                         self.type = type
                         self.unit = unit
                 indicator_from_bank = DummyIndicatorBank(
                     selected_choice_data['value'],
                     selected_choice_data['label'], # Use label as name for dummy
                     selected_choice_data['type'],
                     selected_choice_data['unit']
                 )
            else:
                # Fallback to querying the database if not found in kwargs list
                indicator_from_bank = IndicatorBank.query.get(selected_indicator_bank_id)

        # Get selected disaggregation options
        selected_options = self.allowed_disaggregation_options.data or []

        # Use the common validator
        CommonValidators.validate_age_groups_config(field, selected_options,
                                                   indicator_from_bank.unit if indicator_from_bank else None,
                                                   indicator_from_bank.type if indicator_from_bank else None)


class QuestionForm(BaseForm, LayoutFieldsMixin, DataAvailabilityMixin, SkipLogicMixin):
    """Form for adding or editing a Question within a Form Template."""

    # Use the custom coerce function for section_id
    section_id = SelectField("Section", coerce=int_or_none, validators=[DataRequired(message="Please select a section.")])
    # Question text can be left empty for Blank/Note blocks
    label = TextAreaField("Question Text", validators=[Optional(), Length(max=500)])
    question_type = SelectField(
        "Question Type",
        choices=[(qt.value, 'Blank / Note' if qt.value == 'blank' else qt.value.replace('_', ' ').title()) for qt in QuestionType],
        validators=[DataRequired()]
    )
    order = FloatField("Order in Section (e.g., 1, 1.1, 1.2 for sub-questions)", validators=[Optional()], default=0)
    is_required = BooleanField("Required Field", default=False)

    definition = TextAreaField("Definition", validators=[Optional()],
                              render_kw={"rows": 4, "placeholder": "Detailed definition/description of this question"})
    unit = StringField("Unit", validators=[Optional(), Length(max=50)],
                      render_kw={"placeholder": "e.g., People, %, Items, Days"})
    type = SelectField("Type", choices=[
        ('', 'Select Type...'),
        ('Number', 'Number'),
        ('Percentage', 'Percentage'),
        ('Text', 'Text'),
        ('Boolean', 'Boolean/Yes-No'),
        ('Date', 'Date'),
        ('Choice', 'Choice/Selection')
    ], validators=[Optional()])

    options_json = HiddenField("Options (JSON)")
    options_translations_json = HiddenField("Options Translations (JSON)")

    options_source = SelectField("Options Source", choices=[
        ('manual', 'Manual Options'),
        ('calculated', 'Calculated from List')
    ], validators=[Optional()], default='manual')
    lookup_list_id = SelectField("Lookup List", coerce=lookup_list_id_coerce, validators=[Optional()])
    list_display_column = StringField("Display Column", validators=[Optional()])
    list_filters_json = HiddenField("List Filters (JSON)")

    submit = SubmitField("Save Question")

    def __init__(self, *args, **kwargs):
        super(QuestionForm, self).__init__(*args, **kwargs)

        # Add layout and data availability fields
        self.add_layout_fields()
        self.add_data_availability_fields()
        self.add_skip_logic_fields()

        self.section_id.choices = []  # Sections will be populated dynamically in the route

        # Populate lookup list choices (DB lists + plugin/system lists)
        plugin_choices = []
        try:
            from flask import current_app
            if getattr(current_app, 'form_integration', None):
                plugin_lists = current_app.form_integration.get_plugin_lookup_lists() or []
                plugin_choices = [(pl.get('id'), pl.get('name')) for pl in plugin_lists if pl.get('id') and pl.get('name')]
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug("form_integration fallback: %s", e)
            # Fallback to legacy hardcoded emergency operations if integration unavailable
            plugin_choices = [('emergency_operations', 'Emergency Operations')]

        # Add system lists (Country Map, Indicator Bank, and National Society)
        system_choices = [
            ('country_map', 'Country Map'),
            ('indicator_bank', 'Indicator Bank'),
            ('national_society', 'National Society')
        ]

        self.lookup_list_id.choices = [('', 'Select a list...')] + [
            (ll.id, ll.name) for ll in LookupList.query.order_by(LookupList.name).all()
        ] + plugin_choices + system_choices

    def validate_options_json(self, field):
        # Only require options for single_choice and multiple_choice types
        if self.question_type.data in [QuestionType.single_choice.value, QuestionType.multiple_choice.value]:
            # Check if using calculated lists
            if hasattr(self, 'options_source') and self.options_source.data == 'calculated':
                # For calculated lists, validate lookup_list_id instead of options_json
                if not self.lookup_list_id.data:
                    raise ValidationError("A lookup list must be selected for calculated options.")

                # For plugin/system lists, allow any known non-numeric id; otherwise require numeric DB ID
                if not str(self.lookup_list_id.data).isdigit():
                    # System choices that are always valid
                    system_choice_ids = {'country_map', 'indicator_bank', 'national_society', 'emergency_operations'}

                    # Check if it's a system choice first - if so, skip further validation
                    if str(self.lookup_list_id.data) in system_choice_ids:
                        pass  # System choice is valid, continue to display column validation
                    else:
                        # Not a system choice, check if it's a valid plugin list
                        try:
                            from flask import current_app
                            valid_ids = set()
                            if getattr(current_app, 'form_integration', None):
                                plugin_lists = current_app.form_integration.get_plugin_lookup_lists() or []
                                valid_ids = {str(pl.get('id')) for pl in plugin_lists if pl.get('id')}
                            # Accept only known plugin/system ids
                            if str(self.lookup_list_id.data) not in valid_ids:
                                raise ValidationError("Invalid lookup list ID.")
                        except ValidationError:
                            raise
                        except Exception as e:
                            import logging
                            logging.getLogger(__name__).debug("plugin lookup validation fallback: %s", e)
                            # If integration unavailable, only accept system choices
                            if str(self.lookup_list_id.data) not in system_choice_ids:
                                raise ValidationError("Invalid lookup list ID.")
                else:
                    # Numeric: must be a valid DB list id
                    try:
                        int(self.lookup_list_id.data)
                    except (ValueError, TypeError):
                        raise ValidationError("Invalid lookup list ID.")

                if not self.list_display_column.data:
                    raise ValidationError("A display column must be selected for calculated options.")
                # options_json can be empty for calculated lists
                return

            # For manual options, validate options_json
            if not field.data or not field.data.strip():
                raise ValidationError("Options are required for this question type.")
            try:
                options = json.loads(field.data)
                if not isinstance(options, list) or not options:
                    raise ValidationError("Options must be a non-empty JSON array.")
                # Optional: Add more checks for the format of items within the array if needed
                # e.g., check if they are strings or objects with value/label
            except json.JSONDecodeError:
                raise ValidationError("Invalid JSON format for options.")
        else:
             # If options_json is provided for a type that doesn't use it, maybe clear it or warn
             # For now, we'll just let it pass validation if the type doesn't require options
             pass

    def validate_label(self, field):
        """Require question text for all types except blank/note."""
        if self.question_type.data != 'blank':
            if not field.data or not field.data.strip():
                raise ValidationError('Question text is required for this question type.')
            if len(field.data.strip()) < 3:
                raise ValidationError('Question text must be at least 3 characters long.')


class DocumentFieldForm(BaseForm, LayoutFieldsMixin, SkipLogicMixin):
    """Form for adding or editing a Document Field within a Documents Section."""

    section_id = SelectField("Section", coerce=int_or_none, validators=[DataRequired(message="Please select a section.")])
    label = StringField("Document Label", validators=[DataRequired(), Length(min=2, max=255)])
    order = FloatField("Order in Section (e.g., 1, 1.1, 1.2 for sub-documents)", validators=[Optional()], default=0)
    description = TextAreaField("Description", validators=[Optional(), Length(max=500)])
    is_required = BooleanField("Required Document", default=False)
    max_documents = IntegerField("Maximum Documents Allowed", validators=[Optional()],
                                render_kw={"min": 1, "placeholder": "Unlimited"})

    submit = SubmitField("Save Document Field")

    def __init__(self, *args, **kwargs):
        super(DocumentFieldForm, self).__init__(*args, **kwargs)

        # Add layout fields
        self.add_layout_fields()

        # Add skip logic fields
        self.add_skip_logic_fields()

        self.section_id.choices = []  # Sections will be populated dynamically in the route


class MatrixForm(BaseForm, LayoutFieldsMixin, DataAvailabilityMixin, SkipLogicMixin):
    """Form for adding or editing a Matrix Table within a Form Template."""

    section_id = SelectField("Section", coerce=int_or_none, validators=[DataRequired(message="Please select a section.")])
    label = StringField("Matrix Label", validators=[Optional(), Length(max=255)])
    order = FloatField("Order in Section (e.g., 1, 1.1, 1.2 for sub-items)", validators=[Optional()], default=0)
    description = TextAreaField("Description", validators=[Optional(), Length(max=500)])

    # --- Matrix Configuration (stored in config JSON) ---
    matrix_config = HiddenField('Matrix Configuration')  # JSON string with rows and columns

    # --- Translation Fields ---
    label_translations = HiddenField('Label Translations')
    description_translations = HiddenField('Description Translations')

    # --- Additional Configuration Fields ---
    is_required = BooleanField("Required Matrix", default=False)

    submit = SubmitField("Save Matrix")

    def __init__(self, *args, **kwargs):
        super(MatrixForm, self).__init__(*args, **kwargs)

        # Add layout and data availability fields
        self.add_layout_fields()
        self.add_data_availability_fields()
        self.add_skip_logic_fields()

        self.section_id.choices = []  # Sections will be populated dynamically in the route


class PluginItemForm(BaseForm, LayoutFieldsMixin, DataAvailabilityMixin, SkipLogicMixin):
    """Form for adding or editing Plugin Items within a Form Template."""

    # Use the custom coerce function for section_id
    section_id = SelectField("Section", coerce=int_or_none, validators=[DataRequired(message="Please select a section.")])
    # Plugin items can have labels and descriptions
    label = TextAreaField("Field Label", validators=[Optional(), Length(max=500)])
    description = TextAreaField("Description", validators=[Optional(), Length(max=500)])
    order = FloatField("Order in Section (e.g., 1, 1.1, 1.2 for sub-items)", validators=[Optional()], default=0)
    is_required = BooleanField("Required Field", default=False)

    submit = SubmitField("Save Plugin Item")

    def __init__(self, *args, **kwargs):
        super(PluginItemForm, self).__init__(*args, **kwargs)

        # Add layout and data availability fields
        self.add_layout_fields()
        self.add_data_availability_fields()
        self.add_skip_logic_fields()

        self.section_id.choices = []  # Sections will be populated dynamically in the route
