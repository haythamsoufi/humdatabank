# ========== File: app/forms/form_builder/template_forms.py ==========
"""
Form template management forms for the platform.
"""

from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField, SelectField, BooleanField, SelectMultipleField
from wtforms.validators import DataRequired, Optional, Length
from sqlalchemy import or_, select
from flask_babel import lazy_gettext as _
from app import db
from app.models import FormTemplate, User
from app.models.rbac import RbacUserRole, RbacRole
from ..base import BaseForm, MultilingualFieldsMixin, int_or_none


class FormTemplateForm(BaseForm):
    """Form for adding or editing a Form Template."""

    name = StringField(_("Template Name"), validators=[DataRequired(), Length(min=3, max=100)])
    description = TextAreaField(_("Description"), validators=[Optional(), Length(max=500)])
    add_to_self_report = BooleanField(_("Allow Self-Reporting (Add to Dashboard Dropdown)"), default=False)
    display_order_visible = BooleanField(_("Display Order Numbers (Show section/field numbering in data entry forms)"), default=False)
    is_paginated = BooleanField(_("Paginated Template (Enable multi-page navigation)"), default=False)
    enable_export_pdf = BooleanField(_("Enable Export PDF button"), default=False)
    enable_export_excel = BooleanField(_("Enable Export Excel button"), default=False)
    enable_import_excel = BooleanField(_("Enable Import Excel button"), default=False)
    enable_ai_validation = BooleanField(_("Enable Run AI validation button"), default=False)
    owned_by = SelectField(_("Template Owner"), coerce=int_or_none, validators=[Optional()])
    shared_with_admins = SelectMultipleField(_("Shared Access"), coerce=int, validators=[Optional()])

    submit = SubmitField(_("Save Template"))

    def __init__(self, *args, **kwargs):
        super(FormTemplateForm, self).__init__(*args, **kwargs)

        # Populate admin choices (only admin and system_manager roles) — used for both owner and sharing
        admin_role_ids = select(RbacRole.id).where(
            or_(
                RbacRole.code == "system_manager",
                RbacRole.code == "admin_core",
                RbacRole.code.like("admin\\_%", escape="\\"),
            )
        )
        admin_users = (
            User.query.join(RbacUserRole, User.id == RbacUserRole.user_id)
            .filter(User.active == True, RbacUserRole.role_id.in_(admin_role_ids))
            .distinct()
            .order_by(User.name, User.email)
            .all()
        )
        self.owned_by.choices = [(None, _('Select Owner'))] + [(u.id, u.name or u.email) for u in admin_users]
        self.shared_with_admins.choices = [(u.id, u.name or u.email) for u in admin_users]
