"""
API Key Management Forms
"""

from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, DateTimeField, BooleanField, SelectField
from wtforms.validators import DataRequired, Optional, NumberRange, Length
from datetime import datetime, timedelta
from app.utils.datetime_helpers import utcnow


class APIKeyForm(FlaskForm):
    """Form for creating/editing API keys"""

    client_name = StringField(
        'Client Name',
        validators=[DataRequired(), Length(max=255)],
        description='Human-readable name for this API key (e.g., "Mobile App", "External Integration")'
    )

    client_description = TextAreaField(
        'Description',
        validators=[Optional(), Length(max=1000)],
        description='Optional description of what this API key is used for'
    )

    rate_limit_per_minute = IntegerField(
        'Rate Limit (per minute)',
        validators=[Optional(), NumberRange(min=1, max=10000)],
        default=60,
        description='Maximum number of API requests allowed per minute for this key'
    )

    expires_at = DateTimeField(
        'Expiration Date',
        validators=[Optional()],
        format='%Y-%m-%dT%H:%M',
        description='Optional expiration date for this API key (leave blank for no expiration)'
    )

    def validate_expires_at(self, field):
        """Ensure expiration date is in the future if provided"""
        if field.data and field.data <= utcnow():
            from wtforms.validators import ValidationError
            raise ValidationError('Expiration date must be in the future')


class APIKeyRevokeForm(FlaskForm):
    """Form for revoking API keys"""

    revocation_reason = TextAreaField(
        'Revocation Reason',
        validators=[Optional(), Length(max=500)],
        description='Optional reason for revoking this API key'
    )
