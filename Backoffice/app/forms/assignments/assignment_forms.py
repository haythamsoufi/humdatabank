# ========== File: app/forms/assignments/assignment_forms.py ==========
"""
Assignment management forms for the platform.
"""

from flask_wtf import FlaskForm
from flask_login import current_user
from wtforms import StringField, SubmitField, SelectField, SelectMultipleField, DateField, BooleanField, HiddenField
from wtforms.validators import DataRequired, Optional
from wtforms.widgets import ListWidget, CheckboxInput
from app.models import FormTemplate, Country, User
from app.utils.form_localization import build_template_select_choices
from app.models.rbac import RbacUserRole, RbacRole, RbacRolePermission, RbacPermission
from app.models.enums import AssignmentEntityStatusValue
from ..base import BaseForm
from app.models.assignments import (
    SUBMISSION_REVIEW_RECIPIENT_FDS,
    SUBMISSION_REVIEW_RECIPIENT_SPECIFIC,
    SUBMISSION_REVIEW_RECIPIENT_MODES,
)


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
    custom_name = StringField("Custom Name (optional)", validators=[Optional()])
    due_date = DateField("Due Date (for all selected countries)", format='%Y-%m-%d', validators=[Optional()])
    expiry_date = DateField("Expiry Date (assignment will be treated as Closed after this date)", format='%Y-%m-%d', validators=[Optional()])

    # Public URL generation options
    generate_public_url = BooleanField("Generate public URL for this assignment", default=False)
    public_url_active = BooleanField("Public URL active by default", default=True)

    # Notify assigned entities when assignment is created
    send_notifications = BooleanField("Notify assigned entities when assignment is created", default=True)

    notify_admins = BooleanField(
        "CC admins on notification emails",
        default=False,
    )

    # NS must send for org delegation review before upstream submit
    requires_delegation_review = BooleanField(
        "Require delegation review before final submission",
        default=False,
    )

    enable_upr_country_reporting_excel = BooleanField(
        "Enable UPR Country Reporting Excel import/export",
        default=False,
    )

    enable_unified_country_plan_excel = BooleanField(
        "Enable Unified Country Plan Excel import/export",
        default=False,
    )

    enable_export_excel = BooleanField(
        "Enable Export Excel button",
        default=False,
    )

    enable_import_excel = BooleanField(
        "Enable Import Excel button",
        default=False,
    )

    enable_export_pdf = BooleanField(
        "Enable Export PDF button",
        default=False,
    )

    # Data owner governance — who is accountable for this collection cycle
    data_owner_id = SelectField(
        "Data Owner",
        coerce=lambda x: int(x) if x and str(x).isdigit() else None,
        validators=[Optional()],
    )

    submission_review_recipient_mode = SelectField(
        "Submission review notification",
        choices=[
            (SUBMISSION_REVIEW_RECIPIENT_FDS, "Designated FDS member for the submitting country"),
            (SUBMISSION_REVIEW_RECIPIENT_SPECIFIC, "Specific IFRC admin(s)"),
        ],
        default=SUBMISSION_REVIEW_RECIPIENT_FDS,
    )
    submission_review_recipient_user_ids = HiddenField(validators=[Optional()])

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
        self.template_id.choices = build_template_select_choices(templates)
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
            .scalar_subquery()
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
        if not self.is_submitted() and current_user.is_authenticated:
            valid_owner_ids = {owner_id for owner_id, _ in self.data_owner_id.choices if owner_id}
            if current_user.id in valid_owner_ids:
                self.data_owner_id.data = current_user.id

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        if self.submission_review_recipient_mode.data == SUBMISSION_REVIEW_RECIPIENT_SPECIFIC:
            user_ids = []
            raw = self.submission_review_recipient_user_ids.data
            if raw:
                seen = set()
                for part in str(raw).split(','):
                    part = part.strip()
                    if part.isdigit():
                        uid = int(part)
                        if uid not in seen:
                            seen.add(uid)
                            user_ids.append(uid)
            if not user_ids:
                self.submission_review_recipient_user_ids.errors.append(
                    "Select at least one IFRC admin to notify when submissions arrive."
                )
                return False
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
                .scalar_subquery()
            )
            valid_count = (
                User.query
                .filter(User.active == True, User.id.in_(user_ids), User.id.in_(admin_user_ids))
                .count()
            )
            if valid_count != len(user_ids):
                self.submission_review_recipient_user_ids.errors.append(
                    "All selected reviewers must be active IFRC admins."
                )
                return False
        return True


class AssignmentEntityStatusForm(BaseForm):
    """Form for editing the status and due date of an entity (country, branch, etc.) within an assignment."""

    status = SelectField("Status", choices=AssignmentEntityStatusValue.choices(), validators=[DataRequired()])
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
