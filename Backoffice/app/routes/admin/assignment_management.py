from app.utils.transactions import request_transaction_rollback
from contextlib import suppress
# File: Backoffice/app/routes/admin/assignment_management.py
from app.utils.datetime_helpers import utcnow
"""
Assignment Management Module - Form assignments and public assignments
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_babel import _
from flask_login import current_user
from app import db
from collections import defaultdict
from datetime import datetime, timedelta
from app.models import (
    FormTemplate, AssignedForm, Country, User, AssignmentEntityStatus,
    PublicSubmission, PublicSubmissionStatus,
    SubmittedDocument, NSBranch, NSSubBranch, NSLocalUnit, SecretariatDivision, SecretariatDepartment
)
from app.models.enums import EntityType
from app.forms.assignments import (
    AssignedFormForm, AssignmentEntityStatusForm
)
from app.forms.shared import DeleteForm
from app.utils.api_responses import json_error, json_bad_request, json_not_found, json_ok, json_server_error
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.error_handling import handle_json_view_exception
from app.routes.admin.shared import admin_required, permission_required
from app.utils.request_utils import is_json_request
from app.models.forms import FormData, DynamicIndicatorData, RepeatGroupInstance, RepeatGroupData
from app.utils.form_localization import get_localized_country_name
from app.utils.country_utils import get_countries_by_region
from app.services.entity_service import EntityService
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SubmitField, DateField
from wtforms.validators import Optional, DataRequired
from app.utils.entity_groups import get_enabled_entity_groups

bp = Blueprint("assignment_management", __name__, url_prefix="/admin")

# --- Internal utilities ---
def _delete_assignment_entity_status_with_children(aes):
    """
    Safely delete an AssignmentEntityStatus and all dependent rows to avoid FK violations.
    This removes:
      - FormData linked via assignment_entity_status_id
      - DynamicIndicatorData linked via assignment_entity_status_id
      - RepeatGroupData for RepeatGroupInstances linked via assignment_entity_status_id
      - RepeatGroupInstances linked via assignment_entity_status_id
      - SubmittedDocument linked via assignment_entity_status_id
    Then deletes the AES itself.
    """
    # Delete simple children that directly FK the AES
    FormData.query.filter_by(assignment_entity_status_id=aes.id).delete(synchronize_session=False)
    DynamicIndicatorData.query.filter_by(assignment_entity_status_id=aes.id).delete(synchronize_session=False)

    # Delete repeat structures in correct order (data -> instances)
    instances = RepeatGroupInstance.query.filter_by(assignment_entity_status_id=aes.id).all()
    if instances:
        instance_ids = [inst.id for inst in instances]
        if instance_ids:
            RepeatGroupData.query.filter(RepeatGroupData.repeat_instance_id.in_(instance_ids)).delete(synchronize_session=False)
        for inst in instances:
            db.session.delete(inst)

    # Delete submitted documents tied to this AES
    SubmittedDocument.query.filter_by(assignment_entity_status_id=aes.id).delete(synchronize_session=False)

    # Finally, delete the AES itself
    db.session.delete(aes)

# Define the form for editing overall assignment details
class EditAssignmentDetailsForm(FlaskForm):
    template_id = SelectField("Form Template", coerce=int, validators=[DataRequired()])
    period_name = StringField("Period Name", validators=[DataRequired()])
    due_date = DateField("Due Date", validators=[Optional()])
    expiry_date = DateField("Expiry Date (assignment will be treated as Closed after this date)", format='%Y-%m-%d', validators=[Optional()])
    data_owner_id = SelectField(
        "Data Owner",
        coerce=lambda x: int(x) if x and str(x).isdigit() else None,
        validators=[Optional()],
    )
    submit = SubmitField("Update Assignment")

    def __init__(self, *args, **kwargs):
        super(EditAssignmentDetailsForm, self).__init__(*args, **kwargs)
        # Only allow templates that have a published version
        templates = FormTemplate.query.filter(
            FormTemplate.published_version_id.isnot(None)
        ).all()
        # Sort by name (from published version) in Python since it's a property
        templates.sort(key=lambda t: t.name if t.name else "")
        self.template_id.choices = [(t.id, t.name) for t in templates]
        # Populate data owner choices
        active_users = User.query.filter_by(active=True).order_by(User.name).all()
        self.data_owner_id.choices = [("", "— Select data owner —")] + [
            (u.id, f"{u.name} ({u.email})") for u in active_users
        ]

# === Assignment Management Routes ===
@bp.route("/assignments", methods=["GET"])
@permission_required('admin.assignments.view')
def manage_assignments():
    assignments = AssignedForm.query.options(
        db.joinedload(AssignedForm.template),
    ).order_by(AssignedForm.period_name.desc()).all()

    # Return JSON for API requests (mobile app)
    if is_json_request():
        assignments_data = []
        for assignment in assignments:
            template_name = assignment.template.name if assignment.template else None
            public_url = assignment.public_url if hasattr(assignment, 'public_url') and assignment.public_url else None

            # Count public submissions if available
            public_submission_count = None
            if hasattr(assignment, 'public_submissions'):
                # Count all public submissions (regardless of status)
                # The enum only has: pending, approved, rejected (no 'submitted' status)
                public_submission_count = assignment.public_submissions.count()

            assignments_data.append({
                'id': assignment.id,
                'period_name': assignment.period_name or 'Unnamed Assignment',
                'template_name': template_name,
                'template_id': assignment.template_id if assignment.template else None,
                'has_public_url': assignment.has_public_url() if hasattr(assignment, 'has_public_url') else False,
                'is_public_active': assignment.is_public_active if hasattr(assignment, 'is_public_active') else False,
                'public_url': public_url,
                'public_submission_count': public_submission_count,
            })
        return json_ok(assignments=assignments_data, count=len(assignments_data))

    return render_template("admin/assignments/assignments.html",
                         assignments=assignments,
                         title="Manage Assignments")

@bp.route("/assignments/gantt", methods=["GET"])
@permission_required('admin.assignments.view')
def assignments_gantt():
    """Display assignments in a Gantt chart timeline view grouped by template."""
    assignments = AssignedForm.query.options(
        db.joinedload(AssignedForm.template),
    ).order_by(AssignedForm.assigned_at.asc()).all()

    # Pre-load all country-type statuses in one query to avoid N+1
    assignment_ids = [a.id for a in assignments]
    all_statuses = (
        AssignmentEntityStatus.query
        .filter(
            AssignmentEntityStatus.assigned_form_id.in_(assignment_ids),
            AssignmentEntityStatus.entity_type == 'country',
        )
        .all()
    ) if assignment_ids else []
    statuses_by_assignment = defaultdict(list)
    for aes in all_statuses:
        statuses_by_assignment[aes.assigned_form_id].append(aes)

    # Group assignments by template
    template_groups = {}
    all_unique_countries = set()

    for assignment in assignments:
        template_name = assignment.template.name if assignment.template else 'Template Missing'

        if template_name not in template_groups:
            template_groups[template_name] = {
                'template_name': template_name,
                'assignments': [],
                'unique_countries': set(),
                'active_count': 0
            }

        # Get the earliest due date from country statuses (pre-loaded)
        earliest_due_date = None
        statuses = statuses_by_assignment[assignment.id]
        if statuses:
            due_dates = [aes.due_date for aes in statuses if aes.due_date]
            if due_dates:
                earliest_due_date = min(due_dates)

        if not earliest_due_date:
            earliest_due_date = assignment.assigned_at + timedelta(days=30)

        assignment_country_ids = {aes.entity_id for aes in statuses}

        assignment_data = {
            'id': assignment.id,
            'name': assignment.period_name,
            'template': template_name,
            'start_date': assignment.assigned_at.strftime('%Y-%m-%d'),
            'end_date': earliest_due_date.strftime('%Y-%m-%d'),
            'assigned_at': assignment.assigned_at,
            'due_date': earliest_due_date,
            'countries_count': len(assignment_country_ids),
            'public_active': assignment.is_public_active,
            'has_public_url': assignment.has_public_url()
        }

        template_groups[template_name]['assignments'].append(assignment_data)
        template_groups[template_name]['unique_countries'].update(assignment_country_ids)
        all_unique_countries.update(assignment_country_ids)

        if assignment.is_public_active:
            template_groups[template_name]['active_count'] += 1

    # Convert sets to counts and add to template groups
    for template_group in template_groups.values():
        template_group['total_countries'] = len(template_group['unique_countries'])
        # Remove the set as it's not JSON serializable
        del template_group['unique_countries']

    # Convert to list and sort by template name
    grouped_assignments = list(template_groups.values())
    grouped_assignments.sort(key=lambda x: x['template_name'])

    # Add total unique countries count to the template context
    total_unique_countries = len(all_unique_countries)

    return render_template("admin/assignments/gantt_chart.html",
                         grouped_assignments=grouped_assignments,
                         total_unique_countries=total_unique_countries,
                         title="Assignments Timeline")

@bp.route("/assignments/new", methods=["GET", "POST"])
@permission_required('admin.assignments.create')
def new_assignment():
    form = AssignedFormForm()
    enabled_entity_groups = get_enabled_entity_groups()

    if form.validate_on_submit():
        try:
            # Server-side guard: ensure selected template has a published version
            selected_template = FormTemplate.query.get(form.template_id.data)
            if not selected_template or not selected_template.published_version_id:
                flash("Cannot create assignment: selected template has no published version.", "warning")
                return render_template("admin/assignments/manage_assignment.html",
                                     form=form,
                                     assignment=None,
                                     title="Create New Assignment",
                                     countries_by_region=get_countries_by_region(),
                                     get_localized_country_name=get_localized_country_name,
                                     enabled_entity_types=enabled_entity_groups)

            # Duplicate guard: never auto-reactivate. Require explicit confirmation to create a duplicate.
            period_name = (form.period_name.data or '').strip()
            form.period_name.data = period_name  # normalize server-side
            existing = AssignedForm.query.filter_by(
                template_id=form.template_id.data,
                period_name=period_name
            ).first() if period_name else None
            confirm_duplicate = (request.form.get("confirm_duplicate") == "1")
            if existing and not confirm_duplicate:
                # JS on the create page should preflight this and ask for confirmation without losing selections.
                # This is a server-side safety net for non-JS/direct POSTs.
                flash(
                    _("An assignment already exists for this template and period (ID %(id)s). Confirm to create a duplicate, or edit/reactivate the existing one instead.",
                      id=existing.id),
                    "warning"
                )
                return redirect(url_for("assignment_management.new_assignment"))

            new_assignment = AssignedForm(
                template_id=form.template_id.data,
                period_name=period_name,
                expiry_date=form.expiry_date.data if form.expiry_date.data else None,
                data_owner_id=form.data_owner_id.data or None,
                activated_by_user_id=current_user.id,
            )

            # Warn if active and no data owner (soft enforcement)
            if not new_assignment.data_owner_id:
                flash(_("No data owner was set for this assignment. Consider assigning one for governance accountability."), "warning")

            # Handle public URL generation if requested
            if form.generate_public_url.data:
                new_assignment.generate_public_url()
                new_assignment.is_public_active = form.public_url_active.data

            db.session.add(new_assignment)
            db.session.flush()

            # Collect all entities to add to the assignment
            created_aes_list = []
            entity_counts = defaultdict(int)

            # Process countries from form.countries.data
            selected_country_ids = form.countries.data
            if selected_country_ids:
                for country_id in selected_country_ids:
                    country = Country.query.get(country_id)
                    if country:
                        aes = AssignmentEntityStatus(
                            assigned_form_id=new_assignment.id,
                            entity_type=EntityType.country.value,
                            entity_id=country_id,
                            status='Pending',
                            due_date=form.due_date.data if form.due_date.data else None
                        )
                        db.session.add(aes)
                        created_aes_list.append(aes)
                        entity_counts[EntityType.country.value] += 1

            # Process other entity types from entity_permissions (format: "entity_type:entity_id")
            entity_permissions = request.form.getlist('entity_permissions')
            current_app.logger.info(f"Creating assignment: Received {len(entity_permissions)} entity_permissions: {entity_permissions}")
            if entity_permissions:
                for entity_permission in entity_permissions:
                    try:
                        entity_type_str, entity_id_str = entity_permission.split(':', 1)
                        entity_id = int(entity_id_str)

                        # Validate entity type
                        try:
                            entity_type = EntityType(entity_type_str)
                        except ValueError:
                            current_app.logger.warning(f"Invalid entity type in entity_permissions: {entity_type_str}")
                            continue

                        # Skip countries as they're already processed above
                        if entity_type == EntityType.country:
                            continue

                        # Validate entity exists
                        entity = EntityService.get_entity(entity_type.value, entity_id)
                        if not entity:
                            current_app.logger.warning(f"Entity not found: {entity_type.value}:{entity_id}")
                            continue

                        # Check if already added (shouldn't happen, but safety check)
                        existing = AssignmentEntityStatus.query.filter_by(
                            assigned_form_id=new_assignment.id,
                            entity_type=entity_type.value,
                            entity_id=entity_id
                        ).first()
                        if existing:
                            continue

                        # Create AssignmentEntityStatus
                        aes = AssignmentEntityStatus(
                            assigned_form_id=new_assignment.id,
                            entity_type=entity_type.value,
                            entity_id=entity_id,
                            status='Pending',
                            due_date=form.due_date.data if form.due_date.data else None
                        )
                        db.session.add(aes)
                        created_aes_list.append(aes)
                        entity_counts[entity_type.value] += 1
                    except (ValueError, AttributeError) as e:
                        current_app.logger.warning(f"Error processing entity_permission '{entity_permission}': {e}", exc_info=True)
                        continue

            # Commit all entities
            current_app.logger.info(f"Creating assignment: Total entities to create: {len(created_aes_list)} (countries: {entity_counts.get(EntityType.country.value, 0)}, others: {sum(v for k, v in entity_counts.items() if k != EntityType.country.value)})")
            if created_aes_list:
                db.session.flush()

                # Send notifications to focal points only if requested
                send_notifications = getattr(form.send_notifications, 'data', True)
                if send_notifications:
                    try:
                        from app.services.notification.core import notify_assignment_created
                        for aes in created_aes_list:
                            try:
                                notify_assignment_created(aes)
                            except Exception as e:
                                current_app.logger.error(f"Error sending assignment created notification for AES {aes.id}: {e}", exc_info=True)
                                # Don't fail the assignment creation if notification fails
                    except Exception as e:
                        current_app.logger.error(f"Error importing notification function: {e}", exc_info=True)
                        # Don't fail the assignment creation if notification fails

                # Create success message with entity counts
                total_entities = len(created_aes_list)
                entity_parts = []
                for entity_type, count in entity_counts.items():
                    entity_parts.append(f"{count} {entity_type.replace('_', ' ')}")

                success_msg = f"Assignment '{new_assignment.period_name}' created successfully with {total_entities} entities ({', '.join(entity_parts)})."
                if new_assignment.has_public_url():
                    public_status = "active" if new_assignment.is_public_active else "inactive"
                    success_msg += f" Public URL generated and is {public_status}."
                flash(success_msg, "success")
            else:
                success_msg = f"Assignment '{new_assignment.period_name}' created successfully. No entities assigned yet."
                if new_assignment.has_public_url():
                    public_status = "active" if new_assignment.is_public_active else "inactive"
                    success_msg += f" Public URL generated and is {public_status}."
                flash(success_msg, "success")

            return redirect(url_for("assignment_management.manage_assignments"))
        except Exception as e:
            request_transaction_rollback()
            flash("Error creating assignment.", "danger")
            current_app.logger.error(f"Error creating assignment: {e}", exc_info=True)

    # Prepare country data for template
    countries_by_region = get_countries_by_region()

    return render_template("admin/assignments/manage_assignment.html",
                         form=form,
                         assignment=None,
                         title="Create New Assignment",
                         countries_by_region=countries_by_region,
                         get_localized_country_name=get_localized_country_name,
                         enabled_entity_types=enabled_entity_groups)


@bp.route("/assignments/check_duplicate", methods=["GET"])
@permission_required('admin.assignments.create')
def check_assignment_duplicate():
    """Duplicate checker for the create-assignment UI preflight."""
    template_id = request.args.get("template_id", type=int)
    period_name = (request.args.get("period_name") or "").strip()

    if not template_id or not period_name:
        return json_ok(exists=False)

    existing = AssignedForm.query.filter_by(template_id=template_id, period_name=period_name).first()
    if not existing:
        return json_ok(exists=False)

    template_name = None
    with suppress(Exception):
        template_name = existing.template.name if existing.template else None

    return json_ok(exists=True, assignment={
        "id": existing.id,
        "template_id": existing.template_id,
        "template_name": template_name,
        "period_name": existing.period_name,
        "is_active": bool(getattr(existing, "is_active", True)),
        "is_closed": bool(getattr(existing, "is_closed", False)),
        "is_effectively_closed": bool(getattr(existing, "is_effectively_closed", False)),
    })

@bp.route("/assignments/edit/<int:assignment_id>", methods=["GET", "POST"])
@permission_required('admin.assignments.edit')
def edit_assignment(assignment_id):
    assignment = AssignedForm.query.get_or_404(assignment_id)
    form = EditAssignmentDetailsForm(obj=assignment)
    enabled_entity_groups = get_enabled_entity_groups()

    if form.validate_on_submit():
        try:
            assignment.template_id = form.template_id.data
            assignment.period_name = form.period_name.data
            assignment.expiry_date = form.expiry_date.data if form.expiry_date.data else None
            assignment.data_owner_id = form.data_owner_id.data or None

            # Warn if active assignment has no data owner
            if assignment.is_active and not assignment.data_owner_id:
                flash(_("This active assignment has no data owner. Consider assigning one for governance accountability."), "warning")

            # Update due dates for all countries in this assignment
            if form.due_date.data:
                for aes in assignment.country_statuses:
                    aes.due_date = form.due_date.data

            db.session.flush()
            flash(f"Assignment '{assignment.period_name}' updated successfully.", "success")
            return redirect(url_for("assignment_management.manage_assignments"))
        except Exception as e:
            request_transaction_rollback()
            flash("An error occurred. Please try again.", "danger")
            current_app.logger.error(f"Error updating assignment {assignment_id}: {e}", exc_info=True)

    # Get assignment country entity statuses (for backward compatibility)
    assignment_countries = assignment.country_statuses.all()
    # Get all assignment entity statuses (for entity management)
    assignment_entities = assignment.entity_statuses.all()
    countries_by_region = get_countries_by_region()

    # Import EntityService for template use
    from app.services.entity_service import EntityService

    # Create form for editing assignment entity status
    edit_aes_form = AssignmentEntityStatusForm()

    return render_template("admin/assignments/manage_assignment.html",
                         assignment=assignment,
                         form=form,
                         assignment_countries=assignment_countries,
                         assignment_entities=assignment_entities,
                         countries_by_region=countries_by_region,
                         edit_aes_form=edit_aes_form,
                         get_localized_country_name=get_localized_country_name,
                         EntityService=EntityService,
                         title=f"Edit Assignment: {assignment.period_name}",
                         enabled_entity_types=enabled_entity_groups)

@bp.route("/assignments/edit/<int:assignment_id>/add_countries", methods=["POST"])
@permission_required('admin.assignments.entities.manage')
def add_countries_to_assignment(assignment_id):
    assignment = AssignedForm.query.get_or_404(assignment_id)
    selected_country_ids = request.form.getlist('country_ids')

    if not selected_country_ids:
        flash("No countries selected.", "warning")
        return redirect(url_for("assignment_management.edit_assignment", assignment_id=assignment_id))

    try:
        added_count = 0
        created_aes_list = []
        for country_id in selected_country_ids:
            existing = AssignmentEntityStatus.query.filter_by(
                assigned_form_id=assignment_id,
                entity_type=EntityType.country.value,
                entity_id=country_id
            ).first()
            if not existing:
                aes = AssignmentEntityStatus(
                    assigned_form_id=assignment_id,
                    entity_type=EntityType.country.value,
                    entity_id=country_id,
                    status='Pending'
                )
                db.session.add(aes)
                created_aes_list.append(aes)
                added_count += 1

        db.session.flush()

        # Send notifications to focal points for each newly added assignment
        try:
            from app.services.notification.core import notify_assignment_created
            for aes in created_aes_list:
                try:
                    notify_assignment_created(aes)
                except Exception as e:
                    current_app.logger.error(f"Error sending assignment created notification for AES {aes.id}: {e}", exc_info=True)
                    # Don't fail the operation if notification fails
        except Exception as e:
            current_app.logger.error(f"Error importing notification function: {e}", exc_info=True)
            # Don't fail the operation if notification fails

        flash(f"Added {added_count} countries to assignment.", "success")
    except Exception as e:
        request_transaction_rollback()
        flash("Error adding countries.", "danger")
        current_app.logger.error(f"Error adding countries to assignment {assignment_id}: {e}", exc_info=True)

    return redirect(url_for("assignment_management.edit_assignment", assignment_id=assignment_id))

@bp.route("/assignments/edit/<int:assignment_id>/remove_country/<int:country_id>", methods=["POST"])
@permission_required('admin.assignments.entities.manage')
def remove_country_from_assignment(assignment_id, country_id):
    aes = AssignmentEntityStatus.query.filter_by(
        assigned_form_id=assignment_id,
        entity_type=EntityType.country.value,
        entity_id=country_id
    ).first_or_404()

    try:
        country_name = Country.query.get(country_id).name if Country.query.get(country_id) else 'Country'
        _delete_assignment_entity_status_with_children(aes)
        db.session.flush()
        flash(f"Removed {country_name} from assignment.", "success")
    except Exception as e:
        request_transaction_rollback()
        flash("An error occurred. Please try again.", "danger")
        current_app.logger.error(f"Error removing country {country_id} from assignment {assignment_id}: {e}", exc_info=True)

    return redirect(url_for("assignment_management.edit_assignment", assignment_id=assignment_id))

# === Entity-Based Assignment Routes ===

@bp.route("/assignments/<int:assignment_id>/entities", methods=["GET"])
@permission_required('admin.assignments.entities.manage')
def get_assignment_entities(assignment_id):
    """Get all entities assigned to an assignment."""
    assignment = AssignedForm.query.get_or_404(assignment_id)

    # Get all entity statuses for this assignment
    entity_statuses = AssignmentEntityStatus.query.filter_by(assigned_form_id=assignment_id).all()

    entities_data = []
    for aes in entity_statuses:
        entity = EntityService.get_entity(aes.entity_type, aes.entity_id)
        if entity:
            entities_data.append({
                'status_id': aes.id,
                'entity_type': aes.entity_type,
                'entity_id': aes.entity_id,
                'entity_name': EntityService.get_entity_name(aes.entity_type, aes.entity_id, include_hierarchy=True),
                'status': aes.status,
                'due_date': aes.due_date.strftime('%Y-%m-%d') if aes.due_date else None,
                'is_public_available': aes.is_public_available
            })

    return json_ok(entities=entities_data)

@bp.route("/assignments/<int:assignment_id>/entities/add", methods=["POST"])
@permission_required('admin.assignments.entities.manage')
def add_entity_to_assignment(assignment_id):
    """Add an entity to an assignment."""
    assignment = AssignedForm.query.get_or_404(assignment_id)

    entity_type = request.json.get('entity_type')
    entity_id = request.json.get('entity_id')
    due_date = request.json.get('due_date')

    if not entity_type or not entity_id:
        return json_error('entity_type and entity_id are required', 400)

    # Validate entity exists
    entity = EntityService.get_entity(entity_type, entity_id)
    if not entity:
        return json_error('Entity not found', 404)

    # Check if entity is already assigned
    existing = AssignmentEntityStatus.query.filter_by(
        assigned_form_id=assignment_id,
        entity_type=entity_type,
        entity_id=entity_id
    ).first()

    if existing:
        return json_error('Entity already assigned to this assignment', 409)

    # Create new assignment entity status
    try:
        due_date_obj = datetime.strptime(due_date, '%Y-%m-%d') if due_date else None
    except (ValueError, TypeError):
        due_date_obj = None

    new_aes = AssignmentEntityStatus(
        assigned_form_id=assignment_id,
        entity_type=entity_type,
        entity_id=entity_id,
        status='Pending',
        due_date=due_date_obj
    )
    db.session.add(new_aes)
    db.session.flush()

    # Send notification to focal points for all entity types
    try:
        from app.services.notification.core import notify_assignment_created
        notify_assignment_created(new_aes)
    except Exception as e:
        current_app.logger.error(f"Error sending assignment created notification for AES {new_aes.id}: {e}", exc_info=True)
        # Don't fail the operation if notification fails

    return json_ok(status_id=new_aes.id, entity_name=EntityService.get_entity_name(entity_type, entity_id, include_hierarchy=True))

@bp.route("/assignments/<int:assignment_id>/entities/remove/<int:status_id>", methods=["DELETE"])
@permission_required('admin.assignments.entities.manage')
def remove_entity_from_assignment(assignment_id, status_id):
    """Remove an entity from an assignment."""
    aes = AssignmentEntityStatus.query.filter_by(id=status_id, assigned_form_id=assignment_id).first_or_404()

    _delete_assignment_entity_status_with_children(aes)
    db.session.flush()

    return json_ok()

@bp.route("/assignments/<int:assignment_id>/entities/<int:status_id>", methods=["PUT"])
@permission_required('admin.assignments.entities.manage')
def update_entity_status(assignment_id, status_id):
    """Update the status of an entity assignment."""
    aes = AssignmentEntityStatus.query.filter_by(id=status_id, assigned_form_id=assignment_id).first_or_404()

    status = request.json.get('status')
    due_date = request.json.get('due_date')
    is_public_available = request.json.get('is_public_available')

    if status:
        aes.status = status
        _now = utcnow()
        aes.status_timestamp = _now
        if status == 'Approved':
            aes.approved_by_user_id = current_user.id
        elif status == 'Submitted':
            aes.submitted_by_user_id = current_user.id
            aes.submitted_at = _now

    if due_date:
        with suppress(Exception):
            aes.due_date = datetime.strptime(due_date, '%Y-%m-%d')

    if is_public_available is not None:
        aes.is_public_available = is_public_available

    db.session.flush()

    return json_ok()


@bp.route("/assignments/<int:assignment_id>/entities/bulk-remove", methods=["POST"])
@permission_required('admin.assignments.entities.manage')
def bulk_remove_entities_from_assignment(assignment_id):
    """Remove multiple entities from an assignment by status IDs."""
    data = get_json_safe()
    status_ids = data.get('status_ids') or []
    if not status_ids or not isinstance(status_ids, list):
        return json_bad_request('status_ids array required')
    assignment = AssignedForm.query.get_or_404(assignment_id)
    removed = 0
    for sid in status_ids:
        aes = AssignmentEntityStatus.query.filter_by(id=int(sid), assigned_form_id=assignment_id).first()
        if aes:
            _delete_assignment_entity_status_with_children(aes)
            removed += 1
    db.session.flush()
    flash(f"Removed {removed} entit{'y' if removed == 1 else 'ies'} from the assignment.", "success")
    return json_ok(removed=removed)


@bp.route("/assignments/<int:assignment_id>/entities/bulk-update-status", methods=["POST"])
@permission_required('admin.assignments.entities.manage')
def bulk_update_entity_status(assignment_id):
    """Update the status (and optionally due_date) of multiple entity assignments."""
    data = get_json_safe()
    status_ids = data.get('status_ids') or []
    new_status = (data.get('status') or '').strip()
    due_date_str = data.get('due_date')
    if not status_ids or not isinstance(status_ids, list):
        return json_bad_request('status_ids array required')
    if not new_status:
        return json_bad_request('status required')
    due_date_obj = None
    if due_date_str:
        try:
            due_date_obj = datetime.strptime(due_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            pass
    updated = 0
    for sid in status_ids:
        aes = AssignmentEntityStatus.query.filter_by(id=int(sid), assigned_form_id=assignment_id).first()
        if aes:
            aes.status = new_status
            _now = utcnow()
            aes.status_timestamp = _now
            if new_status == 'Approved':
                aes.approved_by_user_id = current_user.id
            elif new_status == 'Submitted':
                aes.submitted_by_user_id = current_user.id
                aes.submitted_at = _now
            if due_date_obj is not None:
                aes.due_date = due_date_obj
            updated += 1
    db.session.flush()
    flash(f"Updated status for {updated} entit{'y' if updated == 1 else 'ies'}.", "success")
    return json_ok(updated=updated)


@bp.route("/assignment_entity_status/edit/<int:aes_id>", methods=["POST"])
@permission_required('admin.assignments.entities.manage')
def edit_assignment_entity_status(aes_id):
    aes = AssignmentEntityStatus.query.get_or_404(aes_id)
    form = AssignmentEntityStatusForm(request.form)

    if form.validate():
        try:
            aes.status = form.status.data
            _now = utcnow()
            aes.status_timestamp = _now
            aes.due_date = form.due_date.data
            if form.status.data == 'Approved':
                aes.approved_by_user_id = current_user.id
            elif form.status.data == 'Submitted':
                aes.submitted_by_user_id = current_user.id
                aes.submitted_at = _now
            db.session.flush()
            flash(f"Status updated for {EntityService.get_entity_name(aes.entity_type, aes.entity_id)}.", "success")
        except Exception as e:
            request_transaction_rollback()
            flash("Error updating status.", "danger")
            current_app.logger.error(f"Error updating assignment entity status {aes_id}: {e}", exc_info=True)

    return redirect(url_for("assignment_management.edit_assignment", assignment_id=aes.assigned_form_id))

@bp.route("/assignments/delete/<int:assignment_id>", methods=["POST"])
@permission_required('admin.assignments.delete')
def delete_assignment(assignment_id):
    assignment = AssignedForm.query.get_or_404(assignment_id)

    try:
        # Delete related entity statuses and their children first
        aes_list = AssignmentEntityStatus.query.filter_by(assigned_form_id=assignment_id).all()
        for aes in aes_list:
            _delete_assignment_entity_status_with_children(aes)
        db.session.delete(assignment)
        db.session.flush()
        flash(f"Assignment '{assignment.period_name}' deleted successfully.", "success")
    except Exception as e:
        request_transaction_rollback()
        flash("An error occurred. Please try again.", "danger")
        current_app.logger.error(f"Error deleting assignment {assignment_id}: {e}", exc_info=True)

    return redirect(url_for("assignment_management.manage_assignments"))

@bp.route("/assignments/<int:assignment_id>/toggle_active", methods=["POST"])
@permission_required('admin.assignments.edit')
def toggle_assignment_active(assignment_id):
    """Toggle assignment active state (deactivate / activate)."""
    assignment = AssignedForm.query.get_or_404(assignment_id)
    try:
        assignment.is_active = not assignment.is_active
        if assignment.is_active:
            assignment.activated_by_user_id = current_user.id
        else:
            assignment.deactivated_by_user_id = current_user.id
        db.session.flush()
        status = "activated" if assignment.is_active else "deactivated"
        flash(f"Assignment '{assignment.period_name}' {status}.", "success")
    except Exception as e:
        request_transaction_rollback()
        flash("Error toggling assignment.", "danger")
        current_app.logger.error(f"Error toggling assignment {assignment_id}: {e}", exc_info=True)
    return redirect(url_for("assignment_management.manage_assignments"))


@bp.route("/assignments/<int:assignment_id>/close", methods=["POST"])
@permission_required('admin.assignments.edit')
def close_assignment(assignment_id):
    """Close an assignment (e.g. after one year). Admins can reopen it later."""
    assignment = AssignedForm.query.get_or_404(assignment_id)
    try:
        assignment.is_closed = True
        assignment.is_active = False
        assignment.deactivated_by_user_id = current_user.id
        db.session.flush()
        flash(_("Assignment '%(name)s' has been closed.", name=assignment.period_name), "success")
    except Exception as e:
        request_transaction_rollback()
        flash("An error occurred. Please try again.", "danger")
        current_app.logger.error(f"Error closing assignment {assignment_id}: {e}", exc_info=True)
    return redirect(url_for("assignment_management.manage_assignments"))


@bp.route("/assignments/<int:assignment_id>/reopen_closed", methods=["POST"])
@permission_required('admin.assignments.edit')
def reopen_closed_assignment(assignment_id):
    """Reopen a closed assignment (admin only). Clears explicit close and expiry so it stays open."""
    assignment = AssignedForm.query.get_or_404(assignment_id)
    try:
        assignment.is_closed = False
        assignment.is_active = True
        assignment.expiry_date = None  # Clear expiry so assignment stays open until a new expiry is set
        assignment.activated_by_user_id = current_user.id
        db.session.flush()
        flash(f"Assignment '{assignment.period_name}' has been reopened.", "success")
    except Exception as e:
        request_transaction_rollback()
        flash("Error reopening assignment.", "danger")
        current_app.logger.error(f"Error reopening closed assignment {assignment_id}: {e}", exc_info=True)
    return redirect(url_for("assignment_management.manage_assignments"))


@bp.route("/assignments/<int:assignment_id>/generate_public_url", methods=["POST"])
@permission_required('admin.assignments.public_submissions.manage')
def generate_public_url(assignment_id):
    """Generate a public URL for an existing assignment."""
    assignment = AssignedForm.query.get_or_404(assignment_id)

    try:
        if not assignment.has_public_url():
            assignment.generate_public_url()
            assignment.is_public_active = True
            db.session.flush()
            flash(f"Public URL generated for assignment '{assignment.period_name}'.", "success")
        else:
            flash(f"Assignment '{assignment.period_name}' already has a public URL.", "info")
    except Exception as e:
        request_transaction_rollback()
        flash("An error occurred. Please try again.", "danger")
        current_app.logger.error(f"Error generating public URL for assignment {assignment_id}: {e}", exc_info=True)

    next_url = request.form.get('next') or url_for("assignment_management.manage_assignments")
    return redirect(next_url)

@bp.route("/assignments/<int:assignment_id>/toggle_public_access", methods=["POST"])
@permission_required('admin.assignments.public_submissions.manage')
def toggle_public_access(assignment_id):
    """Toggle public access for an assignment's public URL."""
    assignment = AssignedForm.query.get_or_404(assignment_id)

    try:
        if assignment.has_public_url():
            assignment.toggle_public_access()
            db.session.flush()
            status = "activated" if assignment.is_public_active else "deactivated"
            flash(f"Public URL for assignment '{assignment.period_name}' {status}.", "success")
        else:
            flash(f"Assignment '{assignment.period_name}' does not have a public URL.", "warning")
    except Exception as e:
        request_transaction_rollback()
        flash("Error toggling public access.", "danger")
        current_app.logger.error(f"Error toggling public access for assignment {assignment_id}: {e}", exc_info=True)

    next_url = request.form.get('next') or url_for("assignment_management.manage_assignments")
    return redirect(next_url)

@bp.route("/public-submissions", methods=["GET"])
@permission_required('admin.assignments.public_submissions.manage')
def list_public_submissions():
    """View all public submissions across all assignments."""
    # Get all public submissions with related data
    submissions = PublicSubmission.query.options(
        db.joinedload(PublicSubmission.assigned_form).joinedload(AssignedForm.template),
        db.joinedload(PublicSubmission.country)
    ).order_by(PublicSubmission.submitted_at.desc()).all()

    # CSRF form for inline POST actions in the template (status updates, deletes)
    delete_form = DeleteForm()

    return render_template("admin/assignments/public_submissions.html",
                         assignment=None,  # No assignment for "all" view
                         submissions=submissions,
                         delete_form=delete_form,
                         title="All Public Submissions")

@bp.route("/assignments/<int:assignment_id>/view_public_submissions", methods=["GET"])
@permission_required('admin.assignments.public_submissions.manage')
def view_public_submissions(assignment_id):
    """View public submissions for an assignment."""
    assignment = AssignedForm.query.get_or_404(assignment_id)

    if not assignment.has_public_url():
        flash(f"Assignment '{assignment.period_name}' does not have a public URL.", "warning")
        return redirect(url_for("assignment_management.manage_assignments"))

    # Get public submissions for this assignment
    submissions = PublicSubmission.query.options(
        db.joinedload(PublicSubmission.country)
    ).filter_by(assigned_form_id=assignment_id).order_by(PublicSubmission.submitted_at.desc()).all()
    # CSRF form for inline POST actions in the template (status updates, deletes)
    delete_form = DeleteForm()

    return render_template("admin/assignments/public_submissions.html",
                         assignment=assignment,
                         submissions=submissions,
                         delete_form=delete_form,
                         title=f"Public Submissions: {assignment.period_name}")

@bp.route("/assignments/<int:assignment_id>/add_country_to_public/<int:country_id>", methods=["POST"])
@permission_required('admin.assignments.public_submissions.manage')
def add_country_to_public(assignment_id, country_id):
    """Add a country to public reporting for an assignment."""
    assignment = AssignedForm.query.get_or_404(assignment_id)
    country = Country.query.get_or_404(country_id)

    if not assignment.has_public_url():
        flash(f"Assignment '{assignment.period_name}' does not have a public URL.", "warning")
        return redirect(url_for("assignment_management.edit_assignment", assignment_id=assignment_id))

    try:
        aes = AssignmentEntityStatus.query.filter_by(
            assigned_form_id=assignment_id,
            entity_type=EntityType.country.value,
            entity_id=country_id
        ).first()
        if not aes:
            flash(f"Country '{country.name}' is not assigned to this assignment.", "warning")
            return redirect(url_for("assignment_management.edit_assignment", assignment_id=assignment_id))
        aes.is_public_available = True
        db.session.flush()

        flash(f"Country '{country.name}' added to public reporting.", "success")
    except Exception as e:
        request_transaction_rollback()
        flash("An error occurred. Please try again.", "danger")
        current_app.logger.error(f"Error adding country {country_id} to public reporting for assignment {assignment_id}: {e}", exc_info=True)

    return redirect(url_for("assignment_management.edit_assignment", assignment_id=assignment_id))

@bp.route("/assignments/<int:assignment_id>/remove_country_from_public/<int:country_id>", methods=["POST"])
@permission_required('admin.assignments.public_submissions.manage')
def remove_country_from_public(assignment_id, country_id):
    """Remove a country from public reporting for an assignment."""
    assignment = AssignedForm.query.get_or_404(assignment_id)
    country = Country.query.get_or_404(country_id)

    if not assignment.has_public_url():
        flash(f"Assignment '{assignment.period_name}' does not have a public URL.", "warning")
        return redirect(url_for("assignment_management.edit_assignment", assignment_id=assignment_id))

    try:
        aes = AssignmentEntityStatus.query.filter_by(
            assigned_form_id=assignment_id,
            entity_type=EntityType.country.value,
            entity_id=country_id
        ).first()
        if aes:
            aes.is_public_available = False
            db.session.flush()
            flash(f"Country '{country.name}' removed from public reporting.", "success")
        else:
            flash(f"Country '{country.name}' is not assigned to this assignment.", "warning")
    except Exception as e:
        request_transaction_rollback()
        flash("Error removing country from public reporting.", "danger")
        current_app.logger.error(f"Error removing country {country_id} from public reporting for assignment {assignment_id}: {e}", exc_info=True)

    return redirect(url_for("assignment_management.edit_assignment", assignment_id=assignment_id))

@bp.route("/assignments/<int:assignment_id>/bulk-enable-public", methods=["POST"])
@permission_required('admin.assignments.public_submissions.manage')
def bulk_enable_public_reporting(assignment_id):
    """Enable public reporting for multiple countries at once."""
    assignment = AssignedForm.query.get_or_404(assignment_id)

    if not assignment.has_public_url():
        return json_bad_request("Assignment does not have a public URL.", success=False)

    try:
        country_ids_str = request.form.get('country_ids', '')
        if not country_ids_str:
            return json_bad_request("No countries selected.", success=False)

        country_ids = [int(id.strip()) for id in country_ids_str.split(',') if id.strip()]
        enabled_count = 0

        for country_id in country_ids:
            aes = AssignmentEntityStatus.query.filter_by(
                assigned_form_id=assignment_id,
                entity_type=EntityType.country.value,
                entity_id=country_id
            ).first()
            if aes and not aes.is_public_available:
                aes.is_public_available = True
                enabled_count += 1

        db.session.flush()

        return json_ok(
            message=f"Public reporting enabled for {enabled_count} countries.",
            enabled_count=enabled_count
        )

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/assignments/<int:assignment_id>/entities/bulk-update-public", methods=["POST"])
@permission_required('admin.assignments.public_submissions.manage')
def bulk_update_public_availability(assignment_id):
    """Enable or disable public reporting for selected entity statuses."""
    assignment = AssignedForm.query.get_or_404(assignment_id)
    if not assignment.has_public_url():
        return json_bad_request("Assignment does not have a public URL.")

    data = get_json_safe()
    status_ids = data.get('status_ids') or []
    enable = data.get('enable', True)

    if not status_ids or not isinstance(status_ids, list):
        return json_bad_request("status_ids array required")

    updated = 0
    for aes in AssignmentEntityStatus.query.filter(
        AssignmentEntityStatus.id.in_(status_ids),
        AssignmentEntityStatus.assigned_form_id == assignment_id
    ):
        if aes.is_public_available != enable:
            aes.is_public_available = enable
            updated += 1

    db.session.flush()
    action = "enabled" if enable else "disabled"
    return json_ok(updated=updated, message=f"Public reporting {action} for {updated} entit{'y' if updated == 1 else 'ies'}.")


@bp.route("/assignments/<int:assignment_id>/entities/bulk-update-due-date", methods=["POST"])
@permission_required('admin.assignments.entities.manage')
def bulk_update_due_date_selected(assignment_id):
    """Update the due_date of selected entity assignments."""
    AssignedForm.query.get_or_404(assignment_id)
    data = get_json_safe()
    status_ids = data.get('status_ids') or []
    due_date_str = data.get('due_date')

    if not status_ids or not isinstance(status_ids, list):
        return json_bad_request('status_ids array required')
    if not due_date_str:
        return json_bad_request('due_date required')

    try:
        due_date_obj = datetime.strptime(due_date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return json_bad_request('Invalid date format')

    safe_ids = [int(sid) for sid in status_ids]
    updated = AssignmentEntityStatus.query.filter(
        AssignmentEntityStatus.id.in_(safe_ids),
        AssignmentEntityStatus.assigned_form_id == assignment_id,
    ).update({"due_date": due_date_obj}, synchronize_session="fetch")

    db.session.flush()
    return json_ok(updated=updated)


@bp.route("/public-submissions/<int:submission_id>/update-status", methods=["POST"])
@permission_required('admin.assignments.public_submissions.manage')
def update_public_submission_status(submission_id):
    """Update the status of a public submission."""
    try:
        submission = PublicSubmission.query.get_or_404(submission_id)
        new_status = request.form.get('status')

        if new_status not in ['pending', 'approved', 'rejected']:
            flash("Invalid status. Must be pending, approved, or rejected.", "danger")
            return redirect(url_for("assignment_management.list_public_submissions"))

        submission.status = PublicSubmissionStatus(new_status)
        db.session.flush()

        flash(f"Submission status updated to {new_status}.", "success")
        return redirect(url_for("assignment_management.list_public_submissions"))

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error updating public submission status: {e}", exc_info=True)
        flash("Error updating submission status.", "danger")
        return redirect(url_for("assignment_management.list_public_submissions"))

@bp.route("/public-submissions/<int:submission_id>/delete", methods=["POST"])
@permission_required('admin.assignments.public_submissions.manage')
def delete_public_submission(submission_id):
    """Delete a public submission."""
    try:
        submission = PublicSubmission.query.get_or_404(submission_id)

        # Delete associated documents first
        for doc in submission.documents:
            db.session.delete(doc)

        # Delete the submission
        db.session.delete(submission)
        db.session.flush()

        flash("Public submission deleted successfully.", "success")
        return redirect(url_for("assignment_management.list_public_submissions"))

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error deleting public submission: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for("assignment_management.list_public_submissions"))
