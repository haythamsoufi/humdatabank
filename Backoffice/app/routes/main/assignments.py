from flask import redirect, url_for, flash, session, current_app, request
from flask_login import login_required, current_user
from app.models import db, User, Country, CountryAccessRequest
from app.models.assignments import AssignmentEntityStatus
from app.models.core import UserEntityPermission
from app.models.rbac import RbacUserRole, RbacRole
from app.models.enums import EntityType
from app.models.system import CountryAccessRequestStatus
from sqlalchemy import or_
from app.utils.constants import SELECTED_COUNTRY_ID_SESSION_KEY
from app.forms.assignments import ReopenAssignmentForm, ApproveAssignmentForm
from app.forms.auth_forms import RequestCountryAccessForm
from flask_babel import _
from app.utils.datetime_helpers import utcnow
from app.utils.transactions import request_transaction_rollback
from app.services.app_settings_service import is_organization_email

from app.routes.main import bp


@bp.route("/select_country/<int:country_id>", methods=["POST"])
@login_required
def select_country(country_id):
    current_app.logger.warning("select_country route was called, but dashboard route handles POST. This route might be redundant.")
    return redirect(url_for("main.dashboard"))

# NEW: Route to handle reopening an assignment
@bp.route("/reopen_assignment/<int:aes_id>", methods=["POST"])
@login_required
def reopen_assignment(aes_id):
    """
    Reopens an assignment by changing its status to 'In Progress'.
    Uses AuthorizationService for granular RBAC checks.
    """
    from app.services.authorization_service import AuthorizationService

    assignment_entity_status = AssignmentEntityStatus.query.get_or_404(aes_id)

    # Check RBAC permission
    if not AuthorizationService.can_reopen_assignment(assignment_entity_status, current_user):
        flash("You do not have permission to reopen this assignment.", "danger")
        current_app.logger.warning(f"User {current_user.email} attempted to reopen assignment {aes_id} without sufficient permission.")
        return redirect(url_for("main.dashboard"))

    # Validate CSRF token
    form = ReopenAssignmentForm()
    if not form.validate_on_submit():
        flash("Invalid request. Please try again.", "danger")
        current_app.logger.warning(f"CSRF validation failed for reopen assignment {aes_id} for user {current_user.email}.")
        return redirect(url_for("main.dashboard"))

    if assignment_entity_status:
        try:
            assignment_entity_status.status = 'In Progress'
            assignment_entity_status.status_timestamp = utcnow()  # Set timestamp when status changes
            db.session.flush()

            # Send notification to focal points about reopening
            try:
                from app.services.notification.core import notify_assignment_reopened
                created = notify_assignment_reopened(assignment_entity_status)
            except Exception as e:
                current_app.logger.error(f"Error sending assignment reopened notification: {e}", exc_info=True)

            flash(f"Assignment '{assignment_entity_status.assigned_form.template.name if assignment_entity_status.assigned_form.template else 'Template Missing'}' for {assignment_entity_status.country.name if assignment_entity_status.country else 'N/A'} has been reopened.", "success")
        except Exception as e:
            request_transaction_rollback()
            flash("Error reopening assignment.", "danger")
            current_app.logger.error(f"Error during DB commit for reopening assignment {aes_id}: {e}", exc_info=True)
    else:
        flash("Assignment not found.", "danger")
        current_app.logger.warning(f"Admin {current_user.email} attempted to reopen non-existent assignment {aes_id}.")

    # Redirect back to the dashboard, preserving the selected country if possible
    selected_country_id = session.get(SELECTED_COUNTRY_ID_SESSION_KEY)
    if selected_country_id:
         return redirect(url_for("main.dashboard", country_id=selected_country_id))
    else:
         return redirect(url_for("main.dashboard"))

# NEW: Route to handle approving an assignment
@bp.route("/approve_assignment/<int:aes_id>", methods=["POST"])
@login_required
def approve_assignment(aes_id):
    """
    Approves an assignment by changing its status to 'Approved'.
    Uses AuthorizationService for granular RBAC checks.
    """
    from app.services.authorization_service import AuthorizationService

    assignment_entity_status = AssignmentEntityStatus.query.get_or_404(aes_id)

    # Check RBAC permission
    if not AuthorizationService.can_approve_assignment(assignment_entity_status, current_user):
        flash("You do not have permission to approve this assignment.", "danger")
        current_app.logger.warning(f"User {current_user.email} attempted to approve assignment {aes_id} without sufficient permission.")
        return redirect(url_for("main.dashboard"))

    # Validate CSRF token
    form = ApproveAssignmentForm()
    if not form.validate_on_submit():
        flash("Invalid request. Please try again.", "danger")
        current_app.logger.warning(f"CSRF validation failed for approve assignment {aes_id} for user {current_user.email}.")
        return redirect(url_for("main.dashboard"))

    if assignment_entity_status:
        try:
            assignment_entity_status.status = 'Approved'
            assignment_entity_status.status_timestamp = utcnow()  # Set timestamp when status changes
            assignment_entity_status.approved_by_user_id = current_user.id
            db.session.flush()

            # Send notification to focal points about approval
            try:
                from app.services.notification.core import notify_assignment_approved
                notify_assignment_approved(assignment_entity_status)
            except Exception as e:
                current_app.logger.error(f"Error sending assignment approved notification: {e}", exc_info=True)

            flash(f"Assignment '{assignment_entity_status.assigned_form.template.name if assignment_entity_status.assigned_form.template else 'Template Missing'}' for {assignment_entity_status.country.name if assignment_entity_status.country else 'N/A'} has been approved.", "success")
            current_app.logger.info(f"AssignmentEntityStatus ID {aes_id} status changed to 'Approved' by admin {current_user.email}.")
        except Exception as e:
            request_transaction_rollback()
            flash("An error occurred. Please try again.", "danger")
            current_app.logger.error(f"Error during DB commit for approving assignment {aes_id}: {e}", exc_info=True)
    else:
        flash("Assignment not found.", "danger")
        current_app.logger.warning(f"Admin {current_user.email} attempted to approve non-existent assignment {aes_id}.")

    # Redirect back to the dashboard, preserving the selected country if possible
    selected_country_id = session.get(SELECTED_COUNTRY_ID_SESSION_KEY)
    if selected_country_id:
         return redirect(url_for("main.dashboard", country_id=selected_country_id))
    else:
         return redirect(url_for("main.dashboard"))

@bp.route("/request_country_access", methods=["POST"])
@login_required
def request_country_access():
    """Handle country access request submission from dashboard. Supports multiple countries."""
    form = RequestCountryAccessForm()
    can_request_multiple_countries = is_organization_email(getattr(current_user, "email", ""))
    return_to = request.form.get('return_to', '').strip()
    redirect_endpoint = 'auth.account_settings' if return_to == 'account_settings' else 'main.dashboard'

    if form.validate_on_submit():
        try:
            requested_country_ids = form.requested_country_id.data
            if requested_country_ids and len(requested_country_ids) > 0:
                # Ensure we have a list
                if not isinstance(requested_country_ids, list):
                    requested_country_ids = [requested_country_ids]

                if not can_request_multiple_countries and len(requested_country_ids) > 1:
                    flash(
                        _(
                            'Only users with an organization email can request access to multiple countries at once. Please select a single country.'
                        ),
                        'warning'
                    )
                    return redirect(url_for(redirect_endpoint))

                # Non-org users can only ever have one "counting" request
                if not can_request_multiple_countries:
                    existing_requests = CountryAccessRequest.query.filter(
                        CountryAccessRequest.user_id == current_user.id
                    ).filter(
                        (CountryAccessRequest.status == CountryAccessRequestStatus.PENDING) |
                        (CountryAccessRequest.status == CountryAccessRequestStatus.APPROVED)
                    ).all()
                    has_counting_request = False
                    for req in existing_requests:
                        if req.status == CountryAccessRequestStatus.PENDING:
                            has_counting_request = True
                            break
                        if req.status == CountryAccessRequestStatus.APPROVED and req.country_id:
                            if current_user.has_entity_access(EntityType.country.value, req.country_id):
                                has_counting_request = True
                                break
                    if has_counting_request:
                        flash(
                            _('You can only request access to one country in total. You have already submitted a request.'),
                            'warning'
                        )
                        return redirect(url_for(redirect_endpoint))

                created_requests = []
                skipped_already_pending = []
                skipped_already_has_access = []
                skipped_invalid = []

                # Get all admins and system managers (excluding the requester) for notifications
                from app.services.notification.core import create_notification
                from app.models.enums import NotificationType
                admin_role_ids = (
                    db.session.query(RbacRole.id)
                    .filter(
                        or_(
                            RbacRole.code == "system_manager",
                            RbacRole.code == "admin_core",
                            RbacRole.code.like("admin\\_%", escape="\\"),
                        )
                    )
                    .subquery()
                )
                admin_users = (
                    User.query.join(RbacUserRole, User.id == RbacUserRole.user_id)
                    .filter(RbacUserRole.role_id.in_(admin_role_ids), User.id != current_user.id)
                    .distinct()
                    .all()
                )
                admin_user_ids = [admin.id for admin in admin_users] if admin_users else []
                user_name = current_user.name or current_user.email

                # Process each country
                for country_id in requested_country_ids:
                    try:
                        country_id_int = int(country_id)

                        # Check if user already has a pending request for this country
                        existing_request = CountryAccessRequest.query.filter_by(
                            user_id=current_user.id,
                            country_id=country_id_int,
                            status=CountryAccessRequestStatus.PENDING
                        ).first()

                        if existing_request:
                            country = Country.query.get(country_id_int)
                            country_name = country.name if country else f'Country ID {country_id_int}'
                            skipped_already_pending.append(country_name)
                            continue

                        # Check if user already has access to this country
                        country = Country.query.get(country_id_int)
                        if not country:
                            skipped_invalid.append(f'ID {country_id_int}')
                            continue

                        user_permissions = UserEntityPermission.query.filter_by(
                            user_id=current_user.id,
                            entity_type='country',
                            entity_id=country.id
                        ).first()

                        if user_permissions:
                            skipped_already_has_access.append(country.name)
                            continue

                        # Check auto-approve setting
                        from app.services.app_settings_service import get_auto_approve_access_requests
                        auto_approve = get_auto_approve_access_requests()

                        access_request = CountryAccessRequest(
                            user_id=current_user.id,
                            country_id=country_id_int,
                            request_message=form.request_message.data or None,
                            status=CountryAccessRequestStatus.PENDING
                        )
                        db.session.add(access_request)
                        db.session.flush()

                        if auto_approve:
                            current_user.add_entity_permission(entity_type='country', entity_id=country.id)
                            access_request.status = CountryAccessRequestStatus.APPROVED
                            access_request.processed_at = db.func.now()
                            access_request.admin_notes = 'Auto-approved'
                            db.session.flush()
                            try:
                                from app.services.notification.core import notify_user_added_to_country
                                notify_user_added_to_country(current_user.id, country.id)
                            except Exception as e:
                                current_app.logger.debug("notify_user_added_to_country failed: %s", e)

                        created_requests.append(access_request)

                        # Notify admins and system managers about the access request
                        if admin_user_ids and not auto_approve:
                            try:
                                country_name = country.name if country else 'Unknown Country'

                                notifications = create_notification(
                                    user_ids=admin_user_ids,
                                    notification_type=NotificationType.access_request_received,
                                    title_key='notification.access_request_received.title',
                                    title_params=None,
                                    message_key='notification.access_request_received.message',
                                    message_params={
                                        'user_name': user_name,
                                        'country_name': country_name
                                    },
                                    entity_type='country',
                                    entity_id=country_id_int,
                                    related_object_type='country_access_request',
                                    related_object_id=access_request.id,
                                    related_url=url_for('user_management.access_requests'),
                                    priority='normal',
                                    icon='fas fa-user-plus'
                                )

                                if notifications:
                                    current_app.logger.info(
                                        f"Created {len(notifications)} notifications for admins about access request "
                                        f"from {current_user.email} for country {country_name}"
                                    )
                            except Exception as e:
                                current_app.logger.error(
                                    f"Error creating notifications for access request: {e}",
                                    exc_info=True
                                )
                    except (ValueError, TypeError) as e:
                        current_app.logger.warning(f"Invalid country ID in request: {country_id}, error: {e}")
                        skipped_invalid.append(str(country_id))
                        continue

                db.session.flush()

                # Provide user feedback
                if created_requests:
                    all_auto = all(r.status == CountryAccessRequestStatus.APPROVED for r in created_requests)
                    if all_auto:
                        if len(created_requests) == 1:
                            flash(_('Your country access request has been approved. You now have access.'), 'success')
                        else:
                            flash(_('Your access requests for %(count)d countries have been approved.', count=len(created_requests)), 'success')
                    elif len(created_requests) == 1:
                        flash(_('Your country access request has been submitted. An admin will review it shortly.'), 'success')
                    else:
                        flash(_('Your access requests for %(count)d countries have been submitted. An admin will review them shortly.', count=len(created_requests)), 'success')

                    current_app.logger.info(
                        f"User {current_user.email} requested access to {len(created_requests)} countries: "
                        f"{[r.country_id for r in created_requests]}"
                    )

                # Inform about skipped countries
                if skipped_already_pending:
                    if len(skipped_already_pending) == 1:
                        flash(_('You already have a pending request for: %(country)s', country=skipped_already_pending[0]), 'info')
                    else:
                        flash(_('You already have pending requests for: %(countries)s', countries=', '.join(skipped_already_pending)), 'info')

                if skipped_already_has_access:
                    if len(skipped_already_has_access) == 1:
                        flash(_('You already have access to: %(country)s', country=skipped_already_has_access[0]), 'info')
                    else:
                        flash(_('You already have access to: %(countries)s', countries=', '.join(skipped_already_has_access)), 'info')

                if skipped_invalid:
                    flash(_('Some countries could not be processed. Please try again.'), 'warning')

                # If no requests were created and nothing was skipped, show error
                if not created_requests and not skipped_already_pending and not skipped_already_has_access:
                    flash(_('No valid countries were selected. Please try again.'), 'warning')
            else:
                flash(_('Please select at least one country.'), 'danger')
        except Exception as e:
            request_transaction_rollback()
            flash(_('Could not submit request. Please try again.'), 'danger')
            current_app.logger.error(f"Error creating country access request: {e}", exc_info=True)
    else:
        # Form validation errors
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{getattr(form, field).label.text}: {error}", 'danger')

    return redirect(url_for(redirect_endpoint))
