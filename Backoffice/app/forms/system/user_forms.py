# ========== File: app/forms/system/user_forms.py ==========
"""
User management forms for the platform.
"""

import logging
from flask_babel import _

logger = logging.getLogger(__name__)
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectMultipleField, SubmitField
from wtforms.validators import DataRequired, Email, Optional, ValidationError
from wtforms.widgets import ListWidget, CheckboxInput
from app.models import Country, User
from ..base import BaseForm


class UserForm(BaseForm):
    """Form for adding or editing a User."""

    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[Optional()])
    name = StringField('Name', validators=[DataRequired()])
    title = StringField('Title', validators=[Optional()])

    # RBAC roles (multi-select). Users can have multiple roles simultaneously.
    rbac_roles = SelectMultipleField(
        "Roles",
        coerce=lambda x: int(x) if x else None,
        option_widget=CheckboxInput(),
        widget=ListWidget(prefix_label=False),
        # NOTE: Do not use DataRequired here. With checkbox widgets, browsers may treat
        # every checkbox as required and block submission unless all are checked.
        # We enforce "at least one role" via validate_rbac_roles instead.
        validators=[Optional()],
    )

    countries = SelectMultipleField(
        "Assigned Countries",
        coerce=lambda x: int(x) if x else None,
        option_widget=CheckboxInput(),
        widget=ListWidget(prefix_label=False),
        validators=[Optional()]
    )
    submit = SubmitField("Save User")

    def __init__(self, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)
        # Populate country choices dynamically
        self.countries.choices = [(c.id, c.name) for c in Country.query.order_by(Country.name).all()]

        # Populate RBAC role choices dynamically (best-effort; RBAC may not be migrated yet)
        try:
            from app.models.rbac import RbacRole
            self.rbac_roles.choices = [(r.id, r.name) for r in RbacRole.query.order_by(RbacRole.name).all()]
        except Exception as e:
            logger.debug("RBAC roles choices failed: %s", e)
            self.rbac_roles.choices = []

    def validate_rbac_roles(self, field):
        """
        Require at least one role when the field is present.

        This avoids relying on HTML 'required' behavior for checkbox lists.
        """
        # If RBAC isn't available / no choices loaded, don't block the form here.
        if not getattr(self.rbac_roles, "choices", None):
            return
        if not field.data:
            raise ValidationError(_("Please select at least one role."))
