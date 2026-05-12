import logging

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, SelectField, SelectMultipleField, TextAreaField
from wtforms.validators import DataRequired, Email, Optional, Length, EqualTo

logger = logging.getLogger(__name__)

class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Login")

class AccountSettingsForm(FlaskForm):
    name = StringField('Name', validators=[Optional()])
    title = StringField('Title', validators=[Optional()])
    chatbot_enabled = BooleanField('Enable AI Chatbot')
    profile_color = SelectField('Profile Color', validators=[Optional()])
    submit = SubmitField('Save Changes')

    def __init__(self, *args, **kwargs):
        super(AccountSettingsForm, self).__init__(*args, **kwargs)
        # Import here to avoid circular imports
        from app.utils.profile_utils import PROFILE_COLORS

        # Color names mapping
        color_names = {
            '#3B82F6': 'Blue',
            '#EF4444': 'Red',
            '#10B981': 'Green',
            '#F59E0B': 'Yellow',
            '#8B5CF6': 'Purple',
            '#F97316': 'Orange',
            '#EC4899': 'Pink',
            '#06B6D4': 'Cyan',
            '#84CC16': 'Lime',
            '#F43F5E': 'Rose',
            '#6366F1': 'Indigo',
            '#14B8A6': 'Teal',
            '#FBBF24': 'Amber',
            '#A855F7': 'Violet',
            '#E11D48': 'Rose Red',
            '#0EA5E9': 'Sky Blue',
            '#22C55E': 'Emerald',
            '#F59E0B': 'Amber',
            '#8B5CF6': 'Violet',
            '#EC4899': 'Pink'
        }

        self.profile_color.choices = [(color, f"■ {color_names.get(color, 'Custom')}") for color in PROFILE_COLORS]


class RegisterForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    name = StringField('Name', validators=[Optional(), Length(max=100)])
    title = StringField('Title', validators=[Optional(), Length(max=100)])
    requested_country_id = SelectField('Requested Country', coerce=lambda x: int(x) if x else None, validators=[DataRequired(message='Please select a country')])
    request_message = TextAreaField('Additional Information (optional)', validators=[Optional(), Length(max=1000)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8, max=128)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match')])
    submit = SubmitField('Create Account')

    def __init__(self, *args, **kwargs):
        super(RegisterForm, self).__init__(*args, **kwargs)
        try:
            # Import here to avoid circular imports
            from app.models import Country
            countries = Country.query.order_by(Country.name).all()
            self.requested_country_id.choices = [('', '— Select a country —')] + [(c.id, c.name) for c in countries]
        except Exception as e:
            logger.debug("Could not load countries for RegisterForm: %s", e)
            self.requested_country_id.choices = [('', '— Select a country —')]


class ForgotPasswordForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    submit = SubmitField('Send Reset Link')


class RequestCountryAccessForm(FlaskForm):
    requested_country_id = SelectMultipleField('Requested Countries', coerce=int, validators=[DataRequired(message='Please select at least one country')])
    request_message = TextAreaField('Message to admins (optional)', validators=[Optional(), Length(max=1000)])
    submit = SubmitField('Request Access')

    def __init__(self, *args, **kwargs):
        # Extract user_id from kwargs if provided
        user_id = kwargs.pop('user_id', None)
        super(RequestCountryAccessForm, self).__init__(*args, **kwargs)
        try:
            # Import here to avoid circular imports
            from app.models import Country
            from app.models.core import UserEntityPermission
            from app.models.enums import EntityType

            countries = Country.query.order_by(Country.name).all()

            # Get countries user already has access to
            user_country_ids = set()
            if user_id:
                user_permissions = UserEntityPermission.query.filter_by(
                    user_id=user_id,
                    entity_type=EntityType.country.value
                ).all()
                user_country_ids = {perm.entity_id for perm in user_permissions}

            # Build choices - we'll add the "already have access" text in the template/JS
            self.requested_country_id.choices = [(c.id, c.name) for c in countries]

            # Store which countries have access for template use
            self._user_has_access = user_country_ids
        except Exception as e:
            # Log the error for debugging
            import logging
            logging.error(f"Error initializing RequestCountryAccessForm: {e}", exc_info=True)
            # In case DB not available (e.g., during initialization), provide an empty list
            self.requested_country_id.choices = []
            self._user_has_access = set()


class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=8, max=128)])
    confirm_password = PasswordField('Confirm New Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match')])
    submit = SubmitField('Reset Password')
