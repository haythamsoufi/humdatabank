"""Form submission routes -- public forms, public submission CRUD, self-report deletion."""
from __future__ import annotations

from contextlib import suppress
import json

from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_babel import _
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from sqlalchemy.orm import joinedload

from app import get_locale
from app.models import (
    db, AssignedForm, AssignmentEntityStatus, Country, FormItem, FormPage,
    FormSection, PublicSubmission, PublicSubmissionStatus, QuestionType,
)
from app.services.entity_service import EntityService
from app.services.form_processing_service import get_form_items_for_section, slugify_age_group
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_responses import json_bad_request, json_ok, json_server_error
from app.utils.constants import SELF_REPORT_PERIOD_NAME
from app.utils.form_authorization import admin_required
from app.utils.form_localization import (
    get_localized_country_name,
    get_localized_indicator_definition,
    get_localized_indicator_type,
    get_localized_indicator_unit,
    get_localized_page_name,
    get_localized_template_name,
    get_translation_key,
)
from app.utils.transactions import request_transaction_rollback
from config import Config

from .helpers import (
    _load_existing_data_for_public_submission,
    _prepare_submitted_documents_for_template,
)


def register_submission_routes(bp):
    """Register all submission-related routes onto the forms blueprint."""

    @bp.route("/public-submission/<int:submission_id>/view", methods=["GET"])
    @admin_required
    def view_public_submission(submission_id):
        """View public submission details (read-only)."""
        return handle_public_submission_form(submission_id, is_edit_mode=False)

    @bp.route("/public-submission/<int:submission_id>/edit", methods=["GET", "POST"])
    @admin_required
    def edit_public_submission(submission_id):
        """Edit public submission data."""
        return handle_public_submission_form(submission_id, is_edit_mode=True)

    @bp.route("/public-submission/<int:submission_id>/approve", methods=["POST"])
    @admin_required
    def approve_public_submission(submission_id):
        """Approve a public submission."""
        submission = PublicSubmission.query.get_or_404(submission_id)
        csrf_form = FlaskForm()

        if csrf_form.validate_on_submit():
            try:
                submission.status = PublicSubmissionStatus.approved
                db.session.flush()
                flash(f"Public Submission for {submission.country.name} approved.", "success")
            except Exception as e:
                request_transaction_rollback()
                flash("An error occurred. Please try again.", "danger")
                current_app.logger.error(f"Error approving public submission {submission_id}: {e}", exc_info=True)
        else:
            flash("Approval failed due to a security issue. Please try again.", "danger")

        return redirect(url_for('forms.view_public_submission', submission_id=submission_id))

    @bp.route("/public-submission/<int:submission_id>/reject", methods=["POST"])
    @admin_required
    def reject_public_submission(submission_id):
        """Reject a public submission."""
        submission = PublicSubmission.query.get_or_404(submission_id)
        csrf_form = FlaskForm()

        if csrf_form.validate_on_submit():
            try:
                submission.status = PublicSubmissionStatus.rejected
                db.session.flush()
                flash(f"Public Submission for {submission.country.name} rejected.", "success")
            except Exception as e:
                request_transaction_rollback()
                flash("An error occurred. Please try again.", "danger")
                current_app.logger.error(f"Error rejecting public submission {submission_id}: {e}", exc_info=True)
        else:
            flash("Rejection failed due to a security issue. Please try again.", "danger")

        return redirect(url_for('forms.view_public_submission', submission_id=submission_id))

    @bp.route("/public-submission/<int:submission_id>/delete", methods=["POST"])
    @admin_required
    def delete_public_submission(submission_id):
        """Delete a public submission."""
        submission = PublicSubmission.query.get_or_404(submission_id)
        csrf_form = FlaskForm()

        if csrf_form.validate_on_submit():
            try:
                country_name = submission.country.name if submission.country else 'N/A'

                from app.services import storage_service as _ss
                for doc in submission.submitted_documents:
                    try:
                        _ss.delete(
                            _ss.submitted_document_rel_storage_category(doc.storage_path),
                            doc.storage_path,
                        )
                    except Exception as e:
                        current_app.logger.error(f"Error deleting document file {doc.storage_path}: {e}", exc_info=True)

                db.session.delete(submission)
                db.session.flush()
                flash(f"Public Submission for {country_name} deleted successfully.", "success")

                return redirect(url_for("main.dashboard"))

            except Exception as e:
                request_transaction_rollback()
                flash("An error occurred. Please try again.", "danger")
                current_app.logger.error(f"Error deleting public submission {submission_id}: {e}", exc_info=True)
        else:
            flash("Deletion failed due to a security issue. Please try again.", "danger")

        return redirect(url_for('forms.view_public_submission', submission_id=submission_id))

    @bp.route("/public-submission/<int:submission_id>/status", methods=["POST"])
    @admin_required
    def update_public_submission_status(submission_id):
        """Update public submission status via AJAX."""
        submission = PublicSubmission.query.get_or_404(submission_id)
        csrf_form = FlaskForm()

        if csrf_form.validate_on_submit():
            try:
                new_status = request.form.get('status')
                if new_status in ['pending', 'approved', 'rejected']:
                    submission.status = getattr(PublicSubmissionStatus, new_status)
                    db.session.flush()
                    flash(f"Public Submission for {submission.country.name} status updated to {new_status}.", "success")
                    return {"success": True, "message": "Status updated successfully"}
                else:
                    return json_bad_request("Invalid status value", success=False)
            except Exception as e:
                request_transaction_rollback()
                current_app.logger.error(f"Error updating public submission {submission_id} status: {e}", exc_info=True)
                return json_server_error(GENERIC_ERROR_MESSAGE, success=False)
        else:
            return json_bad_request("Security validation failed", success=False)

    @bp.route("/debug/public-form-test", methods=["GET", "POST"])
    @login_required
    def debug_public_form_test():
        """Debug route to test public form logging.

        Security: Protected by @login_required and only available in DEBUG mode.
        """
        if not current_app.config.get('DEBUG', False):
            abort(404)

        current_app.logger.debug("=== DEBUG PUBLIC FORM TEST ===")
        current_app.logger.debug(f"Method: {request.method}")
        current_app.logger.debug(f"Form data: {dict(request.form)}")
        current_app.logger.debug(f"Files data: {dict(request.files)}")

        if request.method == "POST":
            csrf_form = FlaskForm()
            current_app.logger.debug(f"CSRF token present: {'csrf_token' in request.form}")
            current_app.logger.debug(f"CSRF validation: {csrf_form.validate_on_submit()}")
            current_app.logger.debug(f"CSRF errors: {csrf_form.errors}")

            return json_ok(
                status="success",
                csrf_valid=csrf_form.validate_on_submit(),
                csrf_errors=csrf_form.errors,
                form_data=dict(request.form)
            )

        return json_ok(status="debug_route_working")

    @bp.route("/public/<uuid:public_token>", methods=["GET", "POST"])
    def fill_public_form(public_token):
        """Main public form filling route - allows external users to submit data."""
        return _fill_public_form_impl(public_token)

    @bp.route("/public-submission/<int:submission_id>/success", methods=["GET"])
    def public_submission_success(submission_id):
        """Show success page after public form submission."""
        submission = PublicSubmission.query.get_or_404(submission_id)
        return render_template("admin/public/public_submission_success.html",
                               title="Submission Successful",
                               submission=submission)

    @bp.route("/delete_self_report_assignment/<int:aes_id>", methods=["POST"])
    @login_required
    def delete_self_report_assignment(aes_id):
        assignment_entity_status = AssignmentEntityStatus.query.get_or_404(aes_id)
        from app.services.authorization_service import AuthorizationService
        if not AuthorizationService.check_self_report_access(assignment_entity_status, current_user):
            flash("Access denied.", "warning"); return redirect(url_for("main.dashboard"))
        if assignment_entity_status.assigned_form.period_name != SELF_REPORT_PERIOD_NAME:
            flash("You can only delete self-reported assignments.", "warning"); return redirect(url_for("main.dashboard"))
        csrf_form = FlaskForm()
        if csrf_form.validate_on_submit():
            try:
                template_name = (
                    assignment_entity_status.assigned_form.template.name
                    if assignment_entity_status.assigned_form and assignment_entity_status.assigned_form.template
                    else "Template"
                )
                country_name = (
                    assignment_entity_status.country.name
                    if assignment_entity_status.country
                    else "Unknown"
                )

                db.session.delete(assignment_entity_status)
                db.session.flush()
                flash(
                    f"Self-reported assignment '{template_name}' for {country_name} deleted successfully.",
                    "success",
                )
            except Exception as e:
                request_transaction_rollback(); flash("Error deleting self-reported assignment.", "danger")
        else:
            flash("Deletion failed due to a security issue.", "danger")
        return redirect(url_for("main.dashboard"))


def handle_public_submission_form(submission_id, is_edit_mode=False):
    """Handle public submission form viewing/editing for admins and focal points."""
    submission = PublicSubmission.query.options(
        db.joinedload(PublicSubmission.assigned_form).joinedload(AssignedForm.template),
        db.joinedload(PublicSubmission.country)
    ).get_or_404(submission_id)

    from app.services.authorization_service import AuthorizationService
    if AuthorizationService.is_system_manager(current_user) or AuthorizationService.has_rbac_permission(current_user, 'admin.assignments.public_submissions.manage'):
        can_edit = True
    elif AuthorizationService.has_country_access(current_user, submission.country_id) and AuthorizationService.has_rbac_permission(current_user, 'assignment.enter'):
        can_edit = True
    else:
        can_edit = False

    if request.args.get('edit') == 'true':
        can_edit = True
    elif request.args.get('edit') == 'false':
        can_edit = False

    form_template = submission.assigned_form.template

    all_sections = FormSection.query.filter_by(
        template_id=form_template.id,
        version_id=form_template.published_version_id
    ).order_by(FormSection.order).all()

    main_sections = []
    sub_sections_by_parent = {}

    for section_obj in all_sections:
        if section_obj.parent_section_id is None:
            main_sections.append(section_obj)
        else:
            parent_id = section_obj.parent_section_id
            if parent_id not in sub_sections_by_parent:
                sub_sections_by_parent[parent_id] = []
            sub_sections_by_parent[parent_id].append(section_obj)

    sections = all_sections

    class DummyACS:
        def __init__(self, submission_id, assigned_form, country):
            self.id = submission_id
            self.assigned_form = assigned_form
            self.country = country
            self.status = "Public Submission"
            self.country_id = country.id

    dummy_acs = DummyACS(submission.id, submission.assigned_form, submission.country)

    for section in sections:
        section.fields_ordered = get_form_items_for_section(section, dummy_acs)

        if section.section_type == 'dynamic_indicators':
            section.data_entry_display_filters_config = getattr(section, 'data_entry_display_filters_list', [])

    if request.method == "POST" and can_edit:
        csrf_form = FlaskForm()
        if csrf_form.validate_on_submit():
            try:
                action = request.form.get('action', 'save')

                new_country_id = request.form.get('country_id')
                if new_country_id and new_country_id != str(submission.country_id):
                    try:
                        new_country = Country.query.get(int(new_country_id))
                        if new_country:
                            submission.country_id = new_country.id
                            db.session.flush()
                            flash(f'Country changed to {new_country.name}', 'success')
                    except (ValueError, TypeError):
                        flash('Invalid country selection', 'danger')

                from app.services.form_data_service import FormDataService

                sections = submission.assigned_form.sections_ordered

                submission_result = FormDataService.process_form_submission(
                    submission, sections, csrf_form=None
                )

                if not submission_result['success']:
                    for error in submission_result['validation_errors']:
                        flash(error, "danger")
                    return redirect(url_for("forms.edit_public_submission", submission_id=submission_id))

                field_changes_tracker = submission_result['field_changes']

                def parse_field_value_for_display(value):
                    if value is None:
                        return "None"
                    elif isinstance(value, dict) and 'values' in value:
                        total = sum(v for v in value['values'].values() if isinstance(v, (int, float)))
                        return f"Total: {total} (Disaggregated: {value['mode']})"
                    elif isinstance(value, str) and value.startswith('{'):
                        with suppress(Exception):
                            parsed = json.loads(value)
                            if isinstance(parsed, dict) and 'values' in parsed:
                                total = sum(v for v in parsed['values'].values() if isinstance(v, (int, float)))
                                return f"Total: {total} (Disaggregated: {parsed['mode']})"
                    return str(value)

                for change in field_changes_tracker:
                    if change.get('type') in ['added', 'updated']:
                        old_val = parse_field_value_for_display(change.get('old_value'))
                        new_val = parse_field_value_for_display(change.get('new_value'))
                        current_app.logger.info(f"Field '{change.get('field_name', 'Unknown')}' {change['type']}: {old_val} -> {new_val}")

                flash("Form data saved successfully.", "success")
                flash("Public submission updated successfully.", "success")

                if action == 'save':
                    return redirect(url_for("forms.view_public_submission", submission_id=submission_id))

            except Exception as e:
                request_transaction_rollback()
                flash("An error occurred. Please try again.", "danger")
                current_app.logger.error(f"Error saving public submission {submission_id}: {e}", exc_info=True)
        else:
            flash("Form submission failed due to a security issue. Please try again.", "danger")

    repeat_groups_data = {}
    existing_data_processed = _load_existing_data_for_public_submission(submission)

    existing_data_processed['repeat_groups_data'] = repeat_groups_data

    existing_submitted_documents = _prepare_submitted_documents_for_template(submission)

    section_statuses = {}
    for section in sections:
        if hasattr(section, 'fields_ordered') and section.fields_ordered:
            section_statuses[section.name] = 'Completed'
        else:
            section_statuses[section.name] = 'N/A'

    csrf_form = FlaskForm()

    from wtforms import SelectField, StringField, EmailField, SubmitField
    from wtforms.validators import DataRequired, Email

    class DummyCountrySelectForm(FlaskForm):
        country_id = SelectField("Select Your Country", coerce=int, validators=[DataRequired()])

    class DummySubmissionDetailsForm(FlaskForm):
        submitter_name = StringField("Your Name", validators=[DataRequired()])
        submitter_email = EmailField("Your Email", validators=[DataRequired(), Email()])
        submit = SubmitField("Submit Form")

    country_select_form = DummyCountrySelectForm()
    sorted_countries = sorted(submission.assigned_form.public_countries, key=lambda c: c.name)
    country_choices = [(c.id, c.name) for c in sorted_countries]
    country_select_form.country_id.choices = country_choices
    country_select_form.country_id.data = submission.country.id

    submission_details_form = DummySubmissionDetailsForm()
    submission_details_form.submitter_name.data = submission.submitter_name
    submission_details_form.submitter_email.data = submission.submitter_email

    available_indicators_by_section = {}
    for section in all_sections:
        if section.section_type == 'dynamic_indicators':
            section.data_entry_display_filters_config = getattr(section, 'data_entry_display_filters_list', [])
            available_indicators_by_section[section.id] = []
        else:
            available_indicators_by_section[section.id] = []

    for page in FormPage.query.filter_by(template_id=form_template.id, version_id=form_template.published_version_id).order_by(FormPage.order).all():
        page.display_name = get_localized_page_name(page)

    page_ids_processed = set()
    for section in all_sections:
        if section.page and section.page.id not in page_ids_processed:
            section.page.display_name = get_localized_page_name(section.page)
            page_ids_processed.add(section.page.id)

    current_locale_short = (str(get_locale()) if get_locale() else 'en').split('_', 1)[0]
    for section in all_sections:
        translated_name = None
        if section.name_translations and isinstance(section.name_translations, dict):
            translated_name = section.name_translations.get(current_locale_short) or section.name_translations.get('en')
        section.display_name = translated_name.strip() if isinstance(translated_name, str) and translated_name.strip() else section.name

    translation_key = get_translation_key()

    template_structure = form_template
    template_structure.sections = all_sections

    if can_edit:
        title = f"Edit Submission: {submission.country.name} - {submission.submitted_at.strftime('%Y-%m-%d %H:%M')}"
    else:
        title = f"View Submission: {submission.country.name} - {submission.submitted_at.strftime('%Y-%m-%d %H:%M')}"

    return render_template("forms/entry_form/entry_form.html",
                         title=title,
                         assignment=submission.assigned_form,
                         assignment_status=dummy_acs,
                         template_structure=template_structure,
                         form=csrf_form,
                         existing_data=existing_data_processed,
                         existing_submitted_documents=existing_submitted_documents,
                         entity_repo_document_ids=frozenset(),
                         section_statuses=section_statuses,
                         slugify_age_group=slugify_age_group,
                         config=Config,
                         can_edit=can_edit,
                         is_preview_mode=False,
                         QuestionType=QuestionType,
                         isinstance=isinstance,
                         json=json,
                         hasattr=hasattr,
                         available_indicators_by_section=available_indicators_by_section,
                         get_localized_country_name=get_localized_country_name,
                         translation_key=translation_key,
                         get_localized_indicator_definition=get_localized_indicator_definition,
                         get_localized_indicator_type=get_localized_indicator_type,
                         get_localized_indicator_unit=get_localized_indicator_unit,
                         get_localized_template_name=get_localized_template_name,
                         submission=submission,
                         is_public_submission=True,
                         country_select_form=country_select_form,
                         submission_details_form=submission_details_form,
                         plugin_manager=current_app.plugin_manager if hasattr(current_app, 'plugin_manager') else None,
                         form_integration=current_app.form_integration if hasattr(current_app, 'form_integration') else None)


def _fill_public_form_impl(public_token):
    """Main public form filling route - allows external users to submit data."""
    current_app.logger.debug(f"=== PUBLIC FORM ROUTE ENTRY ===")
    current_app.logger.debug(f"Method: {request.method}")
    current_app.logger.debug(f"Public token: {public_token}")
    current_app.logger.debug(f"Request URL: {request.url}")

    existing_data_processed = {}
    existing_submitted_documents_dict = {}

    assigned_form = AssignedForm.query.filter_by(unique_token=str(public_token)).options(
        joinedload(AssignedForm.template)
    ).first()

    if not assigned_form:
        return render_template("admin/public/public_form_unavailable.html",
                               title="Form Not Found",
                               message="This form link is not valid or has been removed.")

    if not assigned_form.is_public_active:
        return render_template("admin/public/public_form_unavailable.html",
                               title="Form Unavailable",
                               message="This form is currently not active.")

    if getattr(assigned_form, "is_active", True) is False:
        return render_template("admin/public/public_form_unavailable.html",
                               title="Form Unavailable",
                               message="This form is currently inactive.")

    form_template = assigned_form.template
    sections = FormSection.query.filter_by(template_id=form_template.id, version_id=form_template.published_version_id).order_by(FormSection.order).all()

    from wtforms import SelectField, StringField, EmailField, SubmitField
    from wtforms.validators import DataRequired, Email

    class PublicCountrySelectForm(FlaskForm):
        country_id = SelectField("Select Your Country", coerce=int, validators=[DataRequired()])

    class PublicSubmissionDetailsForm(FlaskForm):
        submitter_name = StringField("Your Name", validators=[DataRequired()])
        submitter_email = EmailField("Your Email", validators=[DataRequired(), Email()])
        submit = SubmitField("Submit Form")

    class DummyACS:
        def __init__(self):
            self.id = None

    class DummyStatus:
        def __init__(self, status, template, country, period_name):
            self.status = status
            self.id = None
            self.assigned_form = type('DummyAssignedForm', (), {
                'template': template,
                'period_name': period_name
            })()
            self.country = country

    dummy_acs = DummyACS()

    for section in sections:
        form_items = get_form_items_for_section(section, dummy_acs)
        current_section_fields = []

        for item in form_items:
            item.conditions = []
            item.validations_from_db = []
            item.is_required_for_js = item.is_required
            item.layout_column_width = getattr(item, 'layout_column_width', 12)
            item.layout_break_after = getattr(item, 'layout_break_after', False)

            current_section_fields.append(item)

        current_section_fields.sort(key=lambda x: x.order)
        section.fields_ordered = current_section_fields

    sorted_countries = sorted(assigned_form.public_countries, key=lambda c: c.name)

    country_choices = [(c.id, c.name) for c in sorted_countries]

    if not country_choices:
        current_app.logger.warning(f"Public form link {public_token} has no countries assigned.")
        return render_template("admin/public/public_form_unavailable.html",
                               title="Form Unavailable",
                               message="This form is not configured for any countries.")

    country_select_form = PublicCountrySelectForm()
    country_select_form.country_id.choices = country_choices
    submission_details_form = PublicSubmissionDetailsForm()
    csrf_form = FlaskForm()

    selected_country = None

    if request.method == "POST" and 'submit_form' in request.form:
        current_app.logger.debug(f"=== PUBLIC FORM POST DEBUG ===")
        current_app.logger.debug(f"Public form POST request received for token: {public_token}")
        current_app.logger.debug(f"Form data keys: {list(request.form.keys())}")
        current_app.logger.debug(f"Files data keys: {list(request.files.keys())}")
        current_app.logger.debug(f"CSRF token in form: {'csrf_token' in request.form}")

        csrf_valid = csrf_form.validate_on_submit()
        current_app.logger.debug(f"CSRF form valid: {csrf_valid}")
        current_app.logger.debug(f"CSRF form errors: {csrf_form.errors}")

        submission_valid = submission_details_form.validate_on_submit()
        current_app.logger.debug(f"Submission form valid: {submission_valid}")
        current_app.logger.debug(f"Submission form errors: {submission_details_form.errors}")

        country_valid = country_select_form.country_id.validate(country_select_form)
        current_app.logger.debug(f"Country form valid: {country_valid}")
        current_app.logger.debug(f"Country form errors: {country_select_form.errors}")

        current_app.logger.debug(f"Submitter name: {request.form.get('submitter_name', 'NOT_FOUND')}")
        current_app.logger.debug(f"Submitter email: {request.form.get('submitter_email', 'NOT_FOUND')}")
        current_app.logger.debug(f"Country ID: {request.form.get('country_id', 'NOT_FOUND')}")

        if csrf_valid and submission_valid and country_valid:
            selected_country_id = country_select_form.country_id.data
            selected_country = Country.query.get(selected_country_id)

            valid_countries = assigned_form.public_countries

            if not selected_country or selected_country not in valid_countries:
                flash("Invalid country selection during submission.", "danger")
            else:
                try:
                    submission = PublicSubmission(
                        assigned_form_id=assigned_form.id,
                        country_id=selected_country.id,
                        submitter_name=submission_details_form.submitter_name.data,
                        submitter_email=submission_details_form.submitter_email.data,
                        status=PublicSubmissionStatus.pending
                    )
                    db.session.add(submission)
                    db.session.flush()

                    from app.services.form_data_service import FormDataService

                    submission_result = FormDataService.process_form_submission(
                        submission, sections, csrf_form=None
                    )

                    if not submission_result['success']:
                        for error in submission_result['validation_errors']:
                            flash(error, "danger")
                        return redirect(url_for("forms.fill_public_form", public_token=public_token))

                    field_changes_tracker = submission_result['field_changes']

                    def parse_field_value_for_display(value):
                        if value is None:
                            return "None"
                        elif isinstance(value, dict) and 'values' in value:
                            total = sum(v for v in value['values'].values() if isinstance(v, (int, float)))
                            return f"Total: {total} (Disaggregated: {value['mode']})"
                        elif isinstance(value, str) and value.startswith('{'):
                            with suppress(Exception):
                                parsed = json.loads(value)
                                if isinstance(parsed, dict) and 'values' in parsed:
                                    total = sum(v for v in parsed['values'].values() if isinstance(v, (int, float)))
                                    return f"Total: {total} (Disaggregated: {parsed['mode']})"
                        return str(value)

                    for change in field_changes_tracker:
                        if change.get('type') in ['added', 'updated']:
                            old_val = parse_field_value_for_display(change.get('old_value'))
                            new_val = parse_field_value_for_display(change.get('new_value'))
                            current_app.logger.info(f"Field '{change.get('field_name', 'Unknown')}' {change['type']}: {old_val} -> {new_val}")

                    missing_required_fields = []
                    all_required_fields_completed = True

                    if submission_result['success']:
                        try:
                            from app.services.notification.core import notify_public_submission_received
                            notify_public_submission_received(submission)
                        except Exception as e:
                            current_app.logger.error(f"Error sending public submission notification: {e}", exc_info=True)

                        return redirect(url_for('forms.public_submission_success', submission_id=submission.id))
                    else:
                        request_transaction_rollback()
                        for error in submission_result['validation_errors']:
                            flash(error, "warning")

                except Exception as e:
                    request_transaction_rollback()
                    flash("An error occurred during submission. Please try again.", "danger")
                    current_app.logger.error(f"Error during public form submission: {e}", exc_info=True)
        else:
            current_app.logger.debug(f"=== VALIDATION FAILED ===")
            if not csrf_valid:
                flash("Form submission failed due to a security issue. Please try again.", "danger")
                current_app.logger.warning(f"CSRF validation failed for public form {public_token}. Errors: {csrf_form.errors}")
            elif not submission_valid:
                flash("Form submission failed due to validation errors. Please check your entries.", "danger")
                current_app.logger.warning(f"Submission form validation failed for public form {public_token}. Errors: {submission_details_form.errors}")
            elif not country_valid:
                flash("Form submission failed due to validation errors. Please check your entries.", "danger")
                current_app.logger.warning(f"Country form validation failed for public form {public_token}. Errors: {country_select_form.errors}")
            else:
                flash("Form submission failed due to validation errors. Please check your entries.", "danger")
                current_app.logger.warning(f"Unknown validation failure for public form {public_token}")

    selected_country_id_from_args = request.args.get('country_id', type=int)
    if selected_country_id_from_args:
        selected_country = Country.query.get(selected_country_id_from_args)
        valid_countries = assigned_form.public_countries

        if selected_country and selected_country in valid_countries:
            country_select_form.country_id.data = selected_country.id

    period_name = assigned_form.period_name or "Public Submission"

    assignment_status = DummyStatus(
        status="In Progress",
        template=form_template,
        country=sorted_countries[0] if sorted_countries else None,
        period_name=period_name
    )

    section_statuses = {section.name: 'Not Started' for section in sections}

    for page in FormPage.query.filter_by(template_id=form_template.id, version_id=form_template.published_version_id).order_by(FormPage.order).all():
        page.display_name = get_localized_page_name(page)

    page_ids_processed = set()
    for section in sections:
        if section.page and section.page.id not in page_ids_processed:
            section.page.display_name = get_localized_page_name(section.page)
            page_ids_processed.add(section.page.id)

    current_locale_short = (str(get_locale()) if get_locale() else 'en').split('_', 1)[0]
    for section in sections:
        translated_name = None
        if section.name_translations and isinstance(section.name_translations, dict):
            translated_name = section.name_translations.get(current_locale_short) or section.name_translations.get('en')
        section.display_name = translated_name.strip() if isinstance(translated_name, str) and translated_name.strip() else section.name

    available_indicators_by_section = {}
    for section in sections:
        available_indicators_by_section[section.id] = []

        if section.section_type == 'dynamic_indicators':
            section.data_entry_display_filters_config = getattr(section, 'data_entry_display_filters_list', [])

    return render_template("forms/entry_form/entry_form.html",
                           title=get_localized_template_name(form_template),
                           assignment=assigned_form,
                           assignment_status=assignment_status,
                           template_structure=form_template,
                           form=submission_details_form,
                           csrf_form=csrf_form,
                           existing_data={},
                           existing_submitted_documents={},
                           entity_repo_document_ids=frozenset(),
                           section_statuses=section_statuses,
                           slugify_age_group=slugify_age_group,
                           config=Config,
                           can_edit=True,
                           QuestionType=QuestionType,
                           isinstance=isinstance,
                           json=json,
                           hasattr=hasattr,
                           available_indicators_by_section=available_indicators_by_section,
                           get_localized_country_name=get_localized_country_name,
                           translation_key=get_translation_key(),
                           get_localized_indicator_definition=get_localized_indicator_definition,
                           get_localized_indicator_type=get_localized_indicator_type,
                           get_localized_indicator_unit=get_localized_indicator_unit,
                           get_localized_template_name=get_localized_template_name,
                           is_public_submission=True,
                           is_preview_mode=False,
                           country_select_form=country_select_form,
                           submission_details_form=submission_details_form,
                           public_token=public_token,
                           form_action=url_for('forms.fill_public_form', public_token=public_token),
                           plugin_manager=current_app.plugin_manager if hasattr(current_app, 'plugin_manager') else None,
                           form_integration=current_app.form_integration if hasattr(current_app, 'form_integration') else None)
