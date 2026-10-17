# ========== File: app/forms/system/user_forms.py ==========
"""
User management forms for the platform.
"""

import logging
from flask_babel import _

logger = logging.getLogger(__name__)
from flask_wtf import FlaskForm
from wtforms import BooleanField, StringField, PasswordField, SelectMultipleField, SubmitField
from wtforms.validators import DataRequired, Email, Optional, ValidationError, Regexp
from wtforms.widgets import ListWidget, CheckboxInput
from app.models import Country, User
from ..base import BaseForm


class UserForm(BaseForm):
    """Form for adding or editing a User."""

    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[Optional()])
    name = StringField('Name', validators=[DataRequired()])
    title = StringField('Title', validators=[Optional()])
    profile_color = StringField(
        _('Profile colour'),
        validators=[
            Optional(),
            Regexp(
                r'^#[0-9A-Fa-f]{6}$',
                message=_('Profile colour must be a #RRGGBB value.'),
            ),
        ],
        default='#3B82F6',
    )

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

    # Access Groups (multi-select). Organizational groups (Finance, HR, ...) used
    # only to scope assignment visibility; they carry no permissions. Stored in
    # rbac_role (kind='group') and persisted through the same membership table as
    # roles, but rendered and validated separately from the Roles picker.
    access_groups = SelectMultipleField(
        "Access Groups",
        coerce=lambda x: int(x) if x else None,
        option_widget=CheckboxInput(),
        widget=ListWidget(prefix_label=False),
        validators=[Optional()],
    )

    countries = SelectMultipleField(
        "Assigned Countries",
        coerce=lambda x: int(x) if x else None,
        option_widget=CheckboxInput(),
        widget=ListWidget(prefix_label=False),
        validators=[Optional()]
    )
    # Only rendered/used when creating a user; edit_user ignores it.
    send_welcome_email = BooleanField("Send welcome email", default=True)
    submit = SubmitField("Save User")

    def __init__(self, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)
        # Populate country choices dynamically
        self.countries.choices = [(c.id, c.name) for c in Country.query.order_by(Country.name).all()]

        # Populate RBAC role + access group choices dynamically (best-effort; RBAC
        # may not be migrated yet). Roles and Access Groups are split by kind so
        # the two pickers never mix.
        try:
            from app.models.rbac import RbacRole, ROLE_KIND_GROUP
            all_roles = RbacRole.query.order_by(RbacRole.name).all()
            self.rbac_roles.choices = [
                (r.id, r.name) for r in all_roles if r.kind != ROLE_KIND_GROUP
            ]
            self.access_groups.choices = [
                (r.id, r.name) for r in all_roles if r.kind == ROLE_KIND_GROUP
            ]
        except Exception as e:
            logger.debug("RBAC roles/groups choices failed: %s", e)
            self.rbac_roles.choices = []
            self.access_groups.choices = []

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
