# ========== File: app/forms/form_builder/section_forms.py ==========
"""
Form section management forms for the platform.
"""

from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField, SelectField, IntegerField, FloatField
from wtforms.validators import DataRequired, Optional, Length
from ..base import BaseForm, int_or_none


class FormSectionForm(BaseForm):
    """Form for adding or editing a Form Section."""

    name = StringField("Section Name", validators=[DataRequired(), Length(min=2, max=100)])
    order = FloatField("Order (e.g., 1, 1.1, 1.2 for sub-sections)", validators=[Optional()], default=0)
    # Replaced numeric page number with dropdown of named pages
    page_id = SelectField("Page", coerce=int_or_none, validators=[Optional()], default=None)
    section_type = SelectField(
        "Section Type",
        choices=[
            ('standard', 'Standard'),
            ('repeat', 'Repeat Section'),
            ('dynamic_indicators', 'Dynamic Indicators')
        ],
        validators=[Optional()],
        default='standard'
    )
    # Dynamic indicators configuration fields
    max_dynamic_indicators = IntegerField("Max Dynamic Indicators", validators=[Optional()])
    add_indicator_note = TextAreaField("Add Indicator Note", validators=[Optional()])
    # Skip logic support for sections
    relevance_condition = TextAreaField("Relevance Condition", validators=[Optional()])

    submit = SubmitField("Save Section")
