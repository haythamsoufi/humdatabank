# ========== File: app/forms/shared/utility_forms.py ==========
"""
Shared utility forms used across multiple domains in the platform.
"""

from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length
from ..base import BaseForm


class DeleteForm(BaseForm):
    """Simple form for delete operations to ensure CSRF protection."""
    submit = SubmitField("Delete")


class PublicSubmissionDetailsForm(BaseForm):
    """Form for collecting user details (name, email) for public submissions."""
    submitter_name = StringField("Your Name", validators=[DataRequired(), Length(max=100)])
    submitter_email = StringField("Your Email", validators=[DataRequired(), Email(), Length(max=255)])
    # CSRF token is automatically included by FlaskForm
