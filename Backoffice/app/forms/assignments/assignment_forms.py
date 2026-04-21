# ========== File: app/forms/assignments/assignment_forms.py ==========
"""
Assignment management forms for the platform.
"""

from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, SelectMultipleField, DateField, BooleanField, HiddenField
from wtforms.validators import DataRequired, Optional
from wtforms.widgets import ListWidget, CheckboxInput
from app.models import FormTemplate, Country, User
from app.models.rbac import RbacUserRole, RbacRole, RbacRolePermission, RbacPermission
from ..base import BaseForm


class AssignedFormForm(BaseForm):
    """Form for creating a new Assigned Form (Assignment)."""

    template_id = SelectField("Form Template", coerce=lambda x: int(x) if x else None, validators=[DataRequired()])
    countries = SelectMultipleField(
        "Select Countries",
        coerce=lambda x: int(x) if x else None,
        option_widget=CheckboxInput(),
        widget=ListWidget(prefix_label=False),
        validators=[Optional()]  # Avoids 'required' on individual checkboxes
    )
    period_name = StringField("Reporting Period Name", validators=[DataRequired()])
    due_date = DateField("Due Date (for all selected countries)", format='%Y-%m-%d', validators=[Optional()])
    expiry_date = DateField("Expiry Date (assignment will be treated as Closed after this date)", format='%Y-%m-%d', validators=[Optional()])

    # Public URL generation options
    generate_public_url = BooleanField("Generate public URL for this assignment", default=False)
    public_url_active = BooleanField("Public URL active by default", default=True)

    # Notify assigned entities when assignment is created
    send_notifications = BooleanField("Notify assigned entities when assignment is created", default=True)

    # Data owner governance — who is accountable for this collection cycle
    data_owner_id = SelectField(
        "Data Owner",
        coerce=lambda x: int(x) if x and str(x).isdigit() else None,
        validators=[Optional()],
    )

    # Duplicate confirmation (used by client/server guard when template+period already exists)
    confirm_duplicate = HiddenField(default="0")

    submit = SubmitField("Create Assignment")

    def __init__(self, *args, **kwargs):
        super(AssignedFormForm, self).__init__(*args, **kwargs)
        # Populate template and country choices dynamically
        # Only allow templates that have a published version
        templates = FormTemplate.query.filter(
            FormTemplate.published_version_id.isnot(None)
        ).all()
        # Sort by name (from published version) in Python since it's a property
        templates.sort(key=lambda t: t.name if t.name else "")
        self.template_id.choices = [(t.id, t.name) for t in templates]
        self.countries.choices = [(c.id, c.name) for c in Country.query.order_by(Country.name).all()]
        # Populate data owner choices: only active users with admin-level assignment access
        from app import db
        from sqlalchemy import distinct
        admin_user_ids = (
            db.session.query(distinct(RbacUserRole.user_id))
            .join(RbacRole, RbacUserRole.role_id == RbacRole.id)
            .join(RbacRolePermission, RbacRole.id == RbacRolePermission.role_id)
            .join(RbacPermission, RbacRolePermission.permission_id == RbacPermission.id)
            .filter(RbacPermission.code.in_([
                "admin.assignments.view",
                "admin.assignments.edit",
                "admin.assignments.create",
            ]))
            .subquery()
        )
        admin_users = (
            User.query
            .filter(User.active == True, User.id.in_(admin_user_ids))
            .order_by(User.name)
            .all()
        )
        self.data_owner_id.choices = [("", "— Select data owner —")] + [
            (u.id, f"{u.name} ({u.email})") for u in admin_users
        ]


class AssignmentEntityStatusForm(BaseForm):
    """Form for editing the status and due date of an entity (country, branch, etc.) within an assignment."""

    status = SelectField("Status", choices=[
        ("Pending", "Pending"),
        ("In Progress", "In Progress"),
        ("Submitted", "Submitted"),
        ("Approved", "Approved"),
        ("Requires Revision", "Requires Revision")
    ], validators=[DataRequired()])
    due_date = DateField("Due Date", format='%Y-%m-%d', validators=[Optional()])
    submit = SubmitField("Save Status")


class ReopenAssignmentForm(BaseForm):
    """Form for reopening assignments (primarily for CSRF protection)."""
    # This form is primarily for CSRF protection
    # Add any other fields if needed for the reopen action in the future
    pass


class ApproveAssignmentForm(BaseForm):
    """Form for approving assignments (primarily for CSRF protection)."""
    # This form is primarily for CSRF protection
    pass
