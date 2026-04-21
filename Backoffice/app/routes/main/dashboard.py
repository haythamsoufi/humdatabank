from flask import render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_required, current_user
from app.models import db, User, AssignedForm, Country, FormTemplate, FormTemplateVersion, FormData, PublicSubmission, SubmittedDocument, FormSection, FormItem, FormItemType, QuestionType, EntityActivityLog, CountryAccessRequest
from app.models.assignments import AssignmentEntityStatus
from app.models.core import UserEntityPermission
from app.models.rbac import RbacUserRole, RbacRole
from app.models.enums import EntityType
from app.models.system import CountryAccessRequestStatus
from app.services.entity_service import EntityService
from sqlalchemy import and_, or_, func, case
from sqlalchemy.orm import aliased, joinedload
from app.services import get_user_countries
from app.utils.constants import SELECTED_COUNTRY_ID_SESSION_KEY, SELF_REPORT_PERIOD_NAME
from app.utils.form_localization import get_localized_country_name, get_localized_national_society_name as _get_localized_national_society_name
from datetime import datetime
from app.services.notification.core import get_country_recent_activities
from app.forms.shared import DeleteForm
from app.forms.assignments import ReopenAssignmentForm, ApproveAssignmentForm
from app.forms.auth_forms import RequestCountryAccessForm
from flask_babel import _
from app.utils.entity_groups import get_allowed_entity_type_codes, get_enabled_entity_groups
from contextlib import suppress
from app.utils.datetime_helpers import utcnow
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_responses import json_bad_request, json_ok, json_server_error
from app.utils.error_handling import handle_json_view_exception
from app.services.app_settings_service import is_organization_email

from app.routes.main import bp
from app.routes.main.helpers import (
    SELECTED_ENTITY_TYPE_SESSION_KEY,
    SELECTED_ENTITY_ID_SESSION_KEY,
    _parse_int,
    _extract_changed_matrix_values,
    get_localized_template_name,
    localized_field_name,
    format_activity_value,
    render_activity_summary,
    render_matrix_change,
)


@bp.route("/", methods=["GET", "POST"])
@login_required
def dashboard():
    """
    Main dashboard page for logged-in users.
    Displays a welcome message, allows entity selection (countries, branches, departments, etc.),
    and lists assigned forms for the selected entity with their completion rates, including data
    from public forms, combined in the assignments section.
    Also allows users to self-assign templates marked for self-reporting.
    """
    # Get user entities (all entity types user has access to)
    user_entities = []
    user_countries = []

    # RBAC-only: entities are derived from explicit entity permissions, with a fallback
    # for users that have none configured yet (e.g. system managers).
    entity_permissions = UserEntityPermission.query.filter_by(user_id=current_user.id).all()
    if entity_permissions:
        for perm in entity_permissions:
            entity = EntityService.get_entity(perm.entity_type, perm.entity_id)
            if entity:
                user_entities.append({
                    'entity_type': perm.entity_type,
                    'entity_id': perm.entity_id,
                    'entity': entity
                })
    else:
        all_entities = EntityService.get_entities_for_user(current_user)
        for entity in all_entities:
            entity_type = None
            if isinstance(entity, Country):
                entity_type = EntityType.country.value
            else:
                for et, model_class in EntityService.ENTITY_MODEL_MAP.items():
                    if isinstance(entity, model_class):
                        entity_type = et
                        break
            if entity_type:
                entity_id = getattr(entity, 'id', None)
                if entity_id:
                    user_entities.append({
                        'entity_type': entity_type,
                        'entity_id': entity_id,
                        'entity': entity
                    })

    enabled_entity_groups = get_enabled_entity_groups()
    allowed_entity_types = get_allowed_entity_type_codes(enabled_entity_groups)
    if allowed_entity_types:
        user_entities = [
            entity for entity in user_entities
            if entity['entity_type'] in allowed_entity_types
        ]
    else:
        user_entities = []

    user_countries = [
        e['entity'] for e in user_entities
        if e['entity_type'] == EntityType.country.value and isinstance(e['entity'], Country)
    ]
    countries_group_enabled = 'countries' in enabled_entity_groups

    selected_entity = None
    selected_entity_type = None
    selected_entity_id = None
    selected_country = None  # For backward compatibility
    # assigned_forms will now be a list of AssignmentEntityStatus objects
    assigned_forms_statuses = []
    # NEW: List to hold assignment statuses with calculated completion rates
    assigned_forms_with_completion = []
    # NEW: List to hold public form assignments with completion rates (now using AssignedForm)
    public_assignments_with_completion = []
    # NEW: List of templates available for self-reporting
    self_report_templates = []

    # NEW: Combined list for display
    all_forms_for_display = []
    # NEW: Separate lists for current and past assignments
    current_assignments = []
    past_assignments = []

    # NEW: Dictionary to hold public submissions grouped by assigned_form_id
    public_submissions_by_assignment = {}

    # NEW: Instantiate DeleteForm for CSRF protection on delete actions
    delete_form = DeleteForm()
    # NEW: Instantiate ReopenAssignmentForm for CSRF protection on reopen action
    reopen_form = ReopenAssignmentForm()
    # NEW: Instantiate ApproveAssignmentForm for CSRF protection on approve action
    approve_form = ApproveAssignmentForm()
    # NEW: Instantiate RequestCountryAccessForm for country access requests
    request_access_form = RequestCountryAccessForm(user_id=current_user.id)
    can_request_multiple_countries = is_organization_email(getattr(current_user, "email", ""))

    show_country_select = False
    show_entity_select = False
    current_date = utcnow().date()
    # NEW: Initialize focal points lists
    ns_focal_points = []
    org_focal_points = []

    current_app.logger.debug(f"User {current_user.email} accessed dashboard.")
    current_app.logger.debug(f"User has {len(user_entities)} entities assigned")
    current_app.logger.debug(f"Initial session[{SELECTED_ENTITY_TYPE_SESSION_KEY}]: {session.get(SELECTED_ENTITY_TYPE_SESSION_KEY)}")
    current_app.logger.debug(f"Initial session[{SELECTED_ENTITY_ID_SESSION_KEY}]: {session.get(SELECTED_ENTITY_ID_SESSION_KEY)}")

    # Load access requests so users with existing access can still track pending ones
    pending_access_requests = []
    all_access_requests = []
    non_org_has_counting_request = False
    try:
        all_access_requests = (
            CountryAccessRequest.query.filter_by(user_id=current_user.id)
            .options(joinedload(CountryAccessRequest.country))
            .order_by(CountryAccessRequest.created_at.desc())
            .all()
        )

        # Check if approved requests still have access (may have been revoked by admin)
        for req in all_access_requests:
            if not req.country and req.country_id:
                req.country = Country.query.get(req.country_id)

            # For approved requests, check if user still has access
            if req.status == CountryAccessRequestStatus.APPROVED and req.country_id:
                # Check if user still has entity permission for this country
                has_access = current_user.has_entity_access(EntityType.country.value, req.country_id)
                # Add a computed attribute to indicate if access was revoked
                req._access_revoked = not has_access
            else:
                req._access_revoked = False

        pending_access_requests = [
            req for req in all_access_requests if req.status == CountryAccessRequestStatus.PENDING
        ]
        # For non-org users: only PENDING or APPROVED (with access still active) count toward the one-request limit; rejected/revoked do not
        non_org_has_counting_request = False
        if not can_request_multiple_countries:
            for req in all_access_requests:
                if req.status == CountryAccessRequestStatus.PENDING:
                    non_org_has_counting_request = True
                    break
                if req.status == CountryAccessRequestStatus.APPROVED and not getattr(req, '_access_revoked', True):
                    non_org_has_counting_request = True
                    break
    except Exception as access_error:
        current_app.logger.error(f"Failed to load country access requests for {current_user.email}: {access_error}", exc_info=True)
        all_access_requests = []
        pending_access_requests = []
        non_org_has_counting_request = False

    if not user_entities:
        if len(pending_access_requests) == 0:
            flash(_("Your user account is not associated with any enabled entities. Please contact an administrator."), "warning")
        current_app.logger.warning(f"User {current_user.email} has no enabled entities assigned.")
        # selected_country remains None, which will hide entity-specific sections
    else:
        # User has one or more countries
        if countries_group_enabled and len(user_countries) > 1:
            # Show country selection dropdown if user has multiple countries
            show_country_select = True
            current_app.logger.debug(f"User {current_user.email} has multiple countries, showing country select.")

        # Show entity selection dropdown if user has multiple entities (any type)
        if len(user_entities) > 1:
            show_entity_select = True

        if request.method == "POST":
            # Check if the POST is for country selection
            if countries_group_enabled and 'country_select' in request.form:
                selected_country_id_str = request.form.get('country_select')
                current_app.logger.debug(f"Dashboard POST request: Country Selection. Selected country ID string from form: {selected_country_id_str}")
                if selected_country_id_str:
                    try:
                        selected_country_id = int(selected_country_id_str)
                        temp_selected_country = Country.query.get(selected_country_id)
                        # Validate that the selected country is one of the user's assigned countries
                        if temp_selected_country and temp_selected_country in user_countries:
                            session[SELECTED_COUNTRY_ID_SESSION_KEY] = selected_country_id
                            selected_country = temp_selected_country
                            current_app.logger.debug(f"User {current_user.email} selected valid country {selected_country.name} (ID: {selected_country.id}) via POST. Session updated.")
                        else:
                            # Invalid country selected, clear session and flash message
                            session.pop(SELECTED_COUNTRY_ID_SESSION_KEY, None)
                            selected_country = None # Will be set to a default below
                            flash(_("Invalid country selection or country not assigned to you."), "warning")
                            current_app.logger.warning(f"User {current_user.email} submitted invalid country ID {selected_country_id_str} via POST.")
                    except ValueError:
                        # Invalid ID format, clear session and flash message
                        session.pop(SELECTED_COUNTRY_ID_SESSION_KEY, None)
                        selected_country = None # Will be set to a default below
                        flash(_("Invalid country ID format."), "warning")
                        current_app.logger.error(f"User {current_user.email} submitted non-integer country ID '{selected_country_id_str}' via POST.")
                else:
                     # No country selected in the form, clear session (will default below)
                     session.pop(SELECTED_COUNTRY_ID_SESSION_KEY, None)
                     selected_country = None # Will be set to a default below
                     current_app.logger.warning(f"User {current_user.email} submitted POST without a country selection.")

            # NEW: Handle POST for entity selection (multi-entity support)
            elif 'entity_select' in request.form:
                entity_select_value = request.form.get('entity_select', '')
                current_app.logger.debug(f"Dashboard POST request: Entity Selection. Raw value: '{entity_select_value}'")
                if entity_select_value and ':' in entity_select_value:
                    try:
                        selected_type, selected_id_str = entity_select_value.split(':', 1)
                        selected_id = int(selected_id_str)

                        # Validate that the selected entity is one of the user's accessible entities
                        user_entity_pairs = {(e['entity_type'], e['entity_id']) for e in user_entities}
                        if (selected_type, selected_id) in user_entity_pairs or current_user.has_entity_access(selected_type, selected_id):
                            session[SELECTED_ENTITY_TYPE_SESSION_KEY] = selected_type
                            session[SELECTED_ENTITY_ID_SESSION_KEY] = selected_id

                            # Set legacy country session for compatibility
                            with suppress(Exception):
                                related_country = EntityService.get_country_for_entity(selected_type, selected_id)
                                if related_country:
                                    session[SELECTED_COUNTRY_ID_SESSION_KEY] = related_country.id

                            current_app.logger.debug(f"User {current_user.email} selected entity {selected_type}:{selected_id} via POST. Session updated.")
                        else:
                            session.pop(SELECTED_ENTITY_TYPE_SESSION_KEY, None)
                            session.pop(SELECTED_ENTITY_ID_SESSION_KEY, None)
                            flash(_("Invalid entity selection or entity not assigned to you."), "warning")
                            current_app.logger.warning(f"User {current_user.email} submitted invalid entity selection '{entity_select_value}'.")
                    except ValueError:
                        flash(_("Invalid entity ID format."), "warning")
                        current_app.logger.error(f"User {current_user.email} submitted non-integer entity ID in '{entity_select_value}'.")
                else:
                    flash(_("Invalid entity selection."), "warning")
                    current_app.logger.warning(f"User {current_user.email} submitted POST with missing or malformed entity_select value.")

            # NEW: Handle POST for self-reporting template selection
            elif countries_group_enabled and 'self_report_template_id' in request.form and SELECTED_COUNTRY_ID_SESSION_KEY in session:
                 selected_template_id_str = request.form.get('self_report_template_id')
                 selected_country_id_from_session = session[SELECTED_COUNTRY_ID_SESSION_KEY]
                 selected_country = Country.query.get(selected_country_id_from_session)

                 current_app.logger.debug(f"Dashboard POST request: Self-Report. Template ID string: {selected_template_id_str}, Selected Country ID from session: {selected_country_id_from_session}")


                 if selected_template_id_str and selected_country:
                     try:
                         selected_template_id = int(selected_template_id_str)
                         # Check if template is enabled for self-report via published version
                         template_to_assign = FormTemplate.query.join(
                             FormTemplateVersion,
                             and_(
                                 FormTemplate.id == FormTemplateVersion.template_id,
                                 FormTemplateVersion.status == 'published'
                             )
                         ).filter(
                             FormTemplate.id == selected_template_id,
                             FormTemplateVersion.add_to_self_report == True
                         ).first()

                         if template_to_assign and selected_country in user_countries:
                                 assigned_form = AssignedForm(
                                     template_id=template_to_assign.id,
                                     period_name=SELF_REPORT_PERIOD_NAME,
                                     assigned_at=utcnow() # Use current time for uniqueness
                                 )
                                 db.session.add(assigned_form)
                                 db.session.flush() # Flush to get the assigned_form.id
                                 current_app.logger.debug(f"Created new AssignedForm ID {assigned_form.id} for self-report period for template {template_to_assign.id}.")

                                 # Create the new AssignmentEntityStatus entry
                                 new_acs = AssignmentEntityStatus(
                                     assigned_form_id=assigned_form.id,
                                     entity_type='country',
                                     entity_id=selected_country.id,
                                     status='Pending', # Default status
                                     due_date=None # No default due date for self-reported forms
                                 )
                                 db.session.add(new_acs)

                                 current_app.logger.debug(f"Country {selected_country.id} linked to AssignedForm {assigned_form.id} via AssignmentEntityStatus {new_acs.id}.")


                                 try:
                                     db.session.flush()

                                     # Send notification about self-report creation
                                     try:
                                         from app.services.notification.core import notify_self_report_created
                                         notify_self_report_created(new_acs)
                                     except Exception as e:
                                         current_app.logger.error(f"Error sending self-report created notification: {e}", exc_info=True)

                                     flash(_("Template '%(template)s' has been added to your assignments for %(country)s.", template=template_to_assign.name, country=selected_country.name), "success")
                                     current_app.logger.debug(f"Successfully created self-report AssignmentEntityStatus ID {new_acs.id}.")
                                 except Exception as e:
                                     from app.utils.transactions import request_transaction_rollback
                                     request_transaction_rollback()
                                     flash(_("An error occurred. Please try again."), "danger")
                                     current_app.logger.error(f"Error during DB commit for self-report assignment: {e}", exc_info=True)

                         else:
                              flash(_("Invalid template selection or country not assigned to you."), "warning")
                              current_app.logger.warning(f"User {current_user.email} submitted invalid self-report template ID {selected_template_id_str} or country {selected_country_id_from_session} is not assigned.")

                     except ValueError:
                          flash(_("Invalid template ID format."), "warning")
                          current_app.logger.error(f"User {current_user.email} submitted non-integer self-report template ID '{selected_template_id_str}'.")
                 else:
                      flash(_("Please select a template to self-report."), "warning")
                      current_app.logger.warning(f"User {current_user.email} submitted self-report POST without template selection or selected country is missing.")

            # After handling either country selection or self-report, redirect to GET to show updated state
            return redirect(url_for("main.dashboard"))


                                 # If it's a GET request or POST handling didn't redirect, determine the selected entity
        # Check for entity selection in session (new multi-entity system)
        if SELECTED_ENTITY_TYPE_SESSION_KEY in session and SELECTED_ENTITY_ID_SESSION_KEY in session:
            retrieved_entity_type = session.get(SELECTED_ENTITY_TYPE_SESSION_KEY)
            retrieved_entity_id = session.get(SELECTED_ENTITY_ID_SESSION_KEY)
            current_app.logger.debug(f"Found entity {retrieved_entity_type}:{retrieved_entity_id} in session.")
            temp_entity = EntityService.get_entity(retrieved_entity_type, retrieved_entity_id)
            # Validate that the entity in session is still accessible to the user
            if temp_entity and retrieved_entity_type in allowed_entity_types:
                if current_user.has_entity_access(retrieved_entity_type, retrieved_entity_id):
                    selected_entity_type = retrieved_entity_type
                    selected_entity_id = retrieved_entity_id
                    selected_entity = temp_entity
                    # Set selected_country for backward compatibility if it's a country
                    if retrieved_entity_type == EntityType.country.value:
                        selected_country = temp_entity
                        session[SELECTED_COUNTRY_ID_SESSION_KEY] = retrieved_entity_id  # Backward compatibility
                    current_app.logger.debug(f"Using entity {retrieved_entity_type}:{retrieved_entity_id} from session.")
                else:
                    # Entity in session is not valid for the user, clear session
                    session.pop(SELECTED_ENTITY_TYPE_SESSION_KEY, None)
                    session.pop(SELECTED_ENTITY_ID_SESSION_KEY, None)
                    current_app.logger.warning(f"Entity {retrieved_entity_type}:{retrieved_entity_id} from session is no longer valid for user {current_user.email}. Clearing session.")
            else:
                session.pop(SELECTED_ENTITY_TYPE_SESSION_KEY, None)
                session.pop(SELECTED_ENTITY_ID_SESSION_KEY, None)
                current_app.logger.warning(f"Entity {retrieved_entity_type}:{retrieved_entity_id} from session is not enabled or no longer available for user {current_user.email}. Clearing session.")

        # Legacy: Check for country selection in session (backward compatibility)
        elif countries_group_enabled and SELECTED_COUNTRY_ID_SESSION_KEY in session:
            retrieved_country_id = session[SELECTED_COUNTRY_ID_SESSION_KEY]
            current_app.logger.debug(f"Found country ID {retrieved_country_id} in session (legacy).")
            temp_selected_country = Country.query.get(retrieved_country_id)
            # Validate that the country in session is still assigned to the user
            if temp_selected_country:
                user_country_ids = [c.id for c in user_countries] if user_countries else []
                if temp_selected_country.id in user_country_ids or current_user.has_entity_access(EntityType.country.value, temp_selected_country.id):
                    selected_country = temp_selected_country
                    selected_entity_type = EntityType.country.value
                    selected_entity_id = temp_selected_country.id
                    selected_entity = temp_selected_country
                    session[SELECTED_ENTITY_TYPE_SESSION_KEY] = EntityType.country.value
                    session[SELECTED_ENTITY_ID_SESSION_KEY] = temp_selected_country.id
                    current_app.logger.debug(f"Using country {selected_country.name} (ID: {selected_country.id}) from session.")
                else:
                    session.pop(SELECTED_COUNTRY_ID_SESSION_KEY, None)
                    current_app.logger.warning(f"Country ID {retrieved_country_id} from session is no longer valid for user {current_user.email}. Clearing session.")

        # If selected_entity is still None, default to first entity (alphabetically sorted)
        if selected_entity is None and user_entities:
            # Sort entities alphabetically by display name before selecting the first one
            def get_sort_key(e):
                display_name = EntityService.get_entity_name(
                    e['entity_type'],
                    e['entity_id'],
                    include_hierarchy=True
                )
                return (display_name or '').lower()

            sorted_entities = sorted(user_entities, key=get_sort_key)
            # Default to the first entity in the alphabetically sorted list
            first_entity = sorted_entities[0]
            selected_entity_type = first_entity['entity_type']
            selected_entity_id = first_entity['entity_id']
            selected_entity = first_entity['entity']
            if selected_entity_type == EntityType.country.value:
                selected_country = selected_entity
                session[SELECTED_COUNTRY_ID_SESSION_KEY] = selected_country.id  # Backward compatibility
            session[SELECTED_ENTITY_TYPE_SESSION_KEY] = selected_entity_type
            session[SELECTED_ENTITY_ID_SESSION_KEY] = selected_entity_id
            current_app.logger.debug(f"No valid entity in session for user {current_user.email}. Defaulting to first alphabetical entity {selected_entity_type}:{selected_entity_id}. Session updated.")

        # Fetch data for the selected entity if available
        if selected_entity and selected_entity_type and selected_entity_id:
            # Get country for the entity (needed for activities and some other features)
            entity_country = EntityService.get_country_for_entity(selected_entity_type, selected_entity_id)
            if entity_country:
                selected_country = entity_country  # Ensure selected_country is set for compatibility

            entity_display_name = EntityService.get_entity_name(selected_entity_type, selected_entity_id, include_hierarchy=True)
            current_app.logger.debug(f"Fetching assigned forms statuses for selected entity {entity_display_name} ({selected_entity_type}:{selected_entity_id}).")

            # Query AssignmentEntityStatus for the selected entity (supports all entity types)
            AF = aliased(AssignedForm)
            # Include active assignments and closed ones (closed sets is_active=False but we still show them under Past Assignments)
            assigned_forms_statuses = (
                AssignmentEntityStatus.query
                .join(AF, AF.id == AssignmentEntityStatus.assigned_form_id)
                .options(
                    db.joinedload(AssignmentEntityStatus.assigned_form).joinedload(AssignedForm.template)
                )
                .filter(
                    AssignmentEntityStatus.entity_type == selected_entity_type,
                    AssignmentEntityStatus.entity_id == selected_entity_id,
                    or_(AF.is_active == True, AF.is_closed == True)
                )
                .order_by(
                    AssignmentEntityStatus.due_date.asc().nulls_last(),
                    AF.assigned_at.desc()
                )
                .all()
            )

            current_app.logger.debug(f"Found {len(assigned_forms_statuses)} assigned form statuses for {entity_display_name}.")

            # Pre-compute per-template item counts to avoid repeated queries inside the loop
            template_ids = {
                aes.assigned_form.template.id
                for aes in assigned_forms_statuses
                if aes.assigned_form and aes.assigned_form.template
            }

            countable_item_counts_by_template = {}
            document_counts_by_template = {}

            if template_ids:
                # Single pass aggregation for countable items (all non-document fields)
                counts_rows = (
                    db.session.query(
                        FormSection.template_id,
                        func.sum(case((FormItem.item_type != 'document_field', 1), else_=0)).label('countable_count')
                    )
                    .join(FormItem, FormItem.section_id == FormSection.id)
                    .filter(FormSection.template_id.in_(template_ids))
                    .group_by(FormSection.template_id)
                    .all()
                )
                for tpl_id, cnt in counts_rows:
                    countable_item_counts_by_template[tpl_id] = int(cnt or 0)

                # Document fields (all): count every document field regardless of required flag
                document_counts_by_template = dict(
                    db.session.query(FormSection.template_id, func.count())
                    .join(FormItem, FormItem.section_id == FormSection.id)
                    .filter(
                        FormSection.template_id.in_(template_ids),
                        FormItem.item_type == 'document_field'
                    )
                    .group_by(FormSection.template_id)
                    .all()
                )

                required_doc_counts_by_template = dict(
                    db.session.query(FormSection.template_id, func.count())
                    .join(FormItem, FormItem.section_id == FormSection.id)
                    .filter(
                        FormSection.template_id.in_(template_ids),
                        and_(FormItem.item_type == 'document_field', FormItem.is_required == True)
                    )
                    .group_by(FormSection.template_id)
                    .all()
                )

            # Batch compute the last modified user per assignment (by latest EntityActivityLog for this entity/country)
            last_modified_user_by_assignment = {}
            contributors_by_assignment = {}
            if assigned_forms_statuses:
                aes_ids = [aes.id for aes in assigned_forms_statuses]
                # Precompute counts of filled data entries per assignment.
                # Non-matrix items: count if value is set, disagg_data is set, or marked not-applicable.
                # Matrix items are handled separately below so that the entire matrix table
                # counts as ONE filled item when ANY cell contains data.
                filled_non_matrix_counts = dict(
                    db.session.query(FormData.assignment_entity_status_id, func.count(FormData.id))
                    .join(FormItem, FormData.form_item_id == FormItem.id)
                    .filter(
                        FormData.assignment_entity_status_id.in_(aes_ids),
                        FormItem.item_type != 'matrix',
                        or_(
                            FormData.value.isnot(None),
                            FormData.disagg_data.isnot(None),
                            FormData.not_applicable == True
                        )
                    )
                    .group_by(FormData.assignment_entity_status_id)
                    .all()
                )

                # Matrix items: each matrix table counts as 1 filled item if ANY cell has
                # meaningful data (ignoring internal metadata keys).
                matrix_entries = (
                    db.session.query(
                        FormData.assignment_entity_status_id,
                        FormData.disagg_data,
                        FormData.not_applicable,
                    )
                    .join(FormItem, FormData.form_item_id == FormItem.id)
                    .filter(
                        FormData.assignment_entity_status_id.in_(aes_ids),
                        FormItem.item_type == 'matrix',
                        or_(
                            FormData.disagg_data.isnot(None),
                            FormData.not_applicable == True,
                        )
                    )
                    .all()
                )
                matrix_filled_counts = {}
                for aes_id, disagg, na in matrix_entries:
                    is_filled = False
                    if na:
                        is_filled = True
                    elif disagg and isinstance(disagg, dict):
                        # A matrix is "filled" when at least one non-metadata cell has a value
                        is_filled = any(
                            v is not None and str(v).strip() != ''
                            for k, v in disagg.items()
                            if not k.startswith('_')
                        )
                    if is_filled:
                        matrix_filled_counts[aes_id] = matrix_filled_counts.get(aes_id, 0) + 1

                # Merge non-matrix and matrix filled counts
                filled_data_counts = dict(filled_non_matrix_counts)
                for aes_id, cnt in matrix_filled_counts.items():
                    filled_data_counts[aes_id] = filled_data_counts.get(aes_id, 0) + cnt

                # Precompute counts of documents submitted per assignment (all document fields)
                filled_document_counts = dict(
                    db.session.query(SubmittedDocument.assignment_entity_status_id, func.count(SubmittedDocument.id))
                    .join(FormItem, SubmittedDocument.form_item_id == FormItem.id)
                    .filter(
                        SubmittedDocument.assignment_entity_status_id.in_(aes_ids),
                        FormItem.item_type == 'document_field'
                    )
                    .group_by(SubmittedDocument.assignment_entity_status_id)
                    .all()
                )
                # Only compute last modified users when a country context exists
                if selected_country is not None:
                    subq = (
                        db.session.query(
                            EntityActivityLog.assignment_id.label('aid'),
                            func.max(EntityActivityLog.timestamp).label('max_ts')
                        )
                        .filter(
                            EntityActivityLog.entity_type == 'country',
                            EntityActivityLog.entity_id == selected_country.id,
                            EntityActivityLog.assignment_id.in_(aes_ids)
                        )
                        .group_by(EntityActivityLog.assignment_id)
                    ).subquery()

                    aid_uid_rows = (
                        db.session.query(subq.c.aid, EntityActivityLog.user_id)
                        .join(
                            EntityActivityLog,
                            and_(
                                EntityActivityLog.assignment_id == subq.c.aid,
                                EntityActivityLog.timestamp == subq.c.max_ts
                            )
                        )
                        .all()
                    )

                    user_ids = {uid for _, uid in aid_uid_rows if uid is not None}
                    user_map = {}
                    if user_ids:
                        user_map = {u.id: u for u in User.query.filter(User.id.in_(user_ids)).all()}
                    last_modified_user_by_assignment = {aid: user_map.get(uid) for aid, uid in aid_uid_rows}

                    # Batch compute contributors per assignment (distinct users, ordered by latest activity)
                    contributors_by_assignment = {}
                    contrib_rows = (
                        db.session.query(
                            EntityActivityLog.assignment_id.label('aid'),
                            EntityActivityLog.user_id.label('uid'),
                            func.max(EntityActivityLog.timestamp).label('last_ts'),
                        )
                        .filter(
                            EntityActivityLog.entity_type == 'country',
                            EntityActivityLog.entity_id == selected_country.id,
                            EntityActivityLog.assignment_id.in_(aes_ids),
                            EntityActivityLog.user_id.isnot(None),
                        )
                        .group_by(EntityActivityLog.assignment_id, EntityActivityLog.user_id)
                        .all()
                    )

                    contrib_user_ids = {uid for _, uid, _ in contrib_rows if uid is not None}
                    contrib_user_map = {}
                    if contrib_user_ids:
                        contrib_user_map = {
                            u.id: u for u in User.query.filter(User.id.in_(contrib_user_ids)).all()
                        }

                    # Build {assignment_id: [User, ...]} sorted by last activity desc
                    tmp = {}
                    for aid, uid, last_ts in contrib_rows:
                        user = contrib_user_map.get(uid)
                        if not user:
                            continue
                        tmp.setdefault(aid, []).append((last_ts, user))

                    for aid, items in tmp.items():
                        items.sort(key=lambda x: x[0] or datetime.min, reverse=True)
                        contributors_by_assignment[aid] = [u for _, u in items]
                else:
                    last_modified_user_by_assignment = {}
                    contributors_by_assignment = {}

            # Calculate completion rate for each AssignmentEntityStatus and prepare for combined list
            for aes in assigned_forms_statuses:
                template = aes.assigned_form.template

                # Calculate total items in the template (All non-document fields + All Document Fields)
                # Using unified FormItem approach, excluding Blank/Note fields
                template_id = template.id if template else None
                total_countable_items = countable_item_counts_by_template.get(template_id, 0) if template_id else 0
                total_document_fields = document_counts_by_template.get(template_id, 0) if template_id else 0

                total_possible_items = (
                    total_countable_items + total_document_fields
                )

                # Calculate filled items for this specific assignment country status
                filled_data_entries_count = filled_data_counts.get(aes.id, 0)
                filled_documents_count = filled_document_counts.get(aes.id, 0)

                filled_items = filled_data_entries_count + filled_documents_count

                if total_possible_items > 0:
                    completion_rate = (filled_items / total_possible_items) * 100
                else:
                    completion_rate = 0.0 # Handle templates with no items

                # NEW: Get the last modified user from CountryActivityLog
                last_modified_user = last_modified_user_by_assignment.get(aes.id)
                contributors = contributors_by_assignment.get(aes.id, []) if contributors_by_assignment else []
                if (not contributors) and last_modified_user:
                    contributors = [last_modified_user]

                # Add to combined list
                all_forms_for_display.append({
                    'type': 'assigned',
                    'name': f"{aes.assigned_form.period_name} - {template.name if template else 'Template Missing'}",
                    'status': aes.status,
                    'status_timestamp': aes.status_timestamp,
                    'date_info': aes.due_date,
                    'completion_rate': completion_rate,
                    'completion_filled_items': filled_items,
                    'completion_total_items': total_possible_items,
                    'item_object': aes,
                    'is_public': False,
                    'last_modified_user': last_modified_user,
                    'contributors': contributors,
                    'submitted_by_user': aes.submitted_by_user,
                    'approved_by_user': aes.approved_by_user,
                    'submitted_at': aes.submitted_at,
                })


            # NEW: Fetch PublicSubmission records for the selected country
            if selected_country is not None:
                current_app.logger.debug(f"Fetching public submissions for selected country {selected_country.name} (ID: {selected_country.id}).")

                public_submissions = PublicSubmission.query.filter_by(country_id=selected_country.id)\
                    .options(
                        db.joinedload(PublicSubmission.assigned_form).joinedload(AssignedForm.template) # Eager load assignment and template
                    )\
                    .order_by(PublicSubmission.submitted_at.desc()).all() # Order by submitted date

                current_app.logger.debug(f"Found {len(public_submissions)} public submissions for {selected_country.name}.")

                # Group public submissions by assigned_form_id
                for submission in public_submissions:
                     if submission.assigned_form_id not in public_submissions_by_assignment:
                         public_submissions_by_assignment[submission.assigned_form_id] = []
                     public_submissions_by_assignment[submission.assigned_form_id].append(submission)

            # NEW: Add public submission information to existing assignments
            for item in all_forms_for_display:
                if item['type'] == 'assigned':
                    aes = item['item_object']
                    assigned_form_id = aes.assigned_form_id

                    # Check if this assignment has public submissions
                    if assigned_form_id in public_submissions_by_assignment:
                        submissions_list = public_submissions_by_assignment[assigned_form_id]
                        item['public_submissions'] = submissions_list
                        item['public_submission_count'] = len(submissions_list)
                        item['latest_public_submission'] = submissions_list[0]  # Most recent submission
                        # Remove from the dict so it won't be processed as standalone
                        del public_submissions_by_assignment[assigned_form_id]

            # NEW: Process remaining public submissions (standalone - no corresponding assignment)
            for pa_id, submissions_list in public_submissions_by_assignment.items():
                 # Get the parent assigned form (assuming all submissions in the list have the same parent)
                 assigned_form = submissions_list[0].assigned_form

                 if assigned_form and assigned_form.template:
                     template = assigned_form.template

                     section_ids = [s.id for s in template.sections]
                     total_template_indicators = FormItem.query.filter(
                         FormItem.section_id.in_(section_ids),
                         FormItem.item_type == 'indicator'
                     ).count()
                     total_template_questions = FormItem.query.filter(
                         FormItem.section_id.in_(section_ids),
                         FormItem.item_type == 'question',
                         and_(
                             or_(FormItem.question_type.is_(None), FormItem.question_type != QuestionType.blank),
                             or_(FormItem.type.is_(None), FormItem.type != 'blank')
                         )
                     ).count()
                     total_template_matrices = FormItem.query.filter(
                         FormItem.section_id.in_(section_ids),
                         FormItem.item_type == 'matrix'
                     ).count()
                     total_required_document_fields = FormItem.query.filter(
                         FormItem.section_id.in_(section_ids),
                         FormItem.item_type == 'document_field',
                         FormItem.is_required == True
                     ).count()

                     total_possible_items = total_template_indicators + total_template_questions + total_template_matrices + total_required_document_fields

                     latest_submission = submissions_list[0]

                     aes = AssignmentEntityStatus.query.filter_by(
                         assigned_form_id=assigned_form.id,
                         entity_type='country',
                         entity_id=latest_submission.country_id
                     ).first()
                     if aes:
                         filled_non_matrix = db.session.query(FormData)\
                             .join(FormItem, FormData.form_item_id == FormItem.id)\
                             .filter(
                                 FormData.assignment_entity_status_id == aes.id,
                                 FormItem.item_type != 'matrix',
                                 or_(
                                     FormData.value.isnot(None),
                                     FormData.disagg_data.isnot(None),
                                     FormData.not_applicable == True
                                 )
                             ).count()

                         matrix_rows = db.session.query(FormData.disagg_data, FormData.not_applicable)\
                             .join(FormItem, FormData.form_item_id == FormItem.id)\
                             .filter(
                                 FormData.assignment_entity_status_id == aes.id,
                                 FormItem.item_type == 'matrix',
                                 or_(
                                     FormData.disagg_data.isnot(None),
                                     FormData.not_applicable == True,
                                 )
                             ).all()
                         filled_matrices = 0
                         for disagg, na in matrix_rows:
                             if na:
                                 filled_matrices += 1
                             elif disagg and isinstance(disagg, dict):
                                 if any(
                                     v is not None and str(v).strip() != ''
                                     for k, v in disagg.items()
                                     if not k.startswith('_')
                                 ):
                                     filled_matrices += 1

                         filled_data_entries_count = filled_non_matrix + filled_matrices
                     else:
                         filled_data_entries_count = 0

                     if aes:
                         filled_required_documents_count = db.session.query(SubmittedDocument)\
                             .join(FormItem, SubmittedDocument.form_item_id == FormItem.id)\
                             .filter(
                                 SubmittedDocument.assignment_entity_status_id == aes.id,
                                 and_(
                                     FormItem.item_type == 'document_field',
                                     FormItem.is_required == True
                                 )
                             ).count()
                     else:
                         filled_required_documents_count = 0

                     filled_items = filled_data_entries_count + filled_required_documents_count

                     if total_possible_items > 0:
                         completion_rate = (filled_items / total_possible_items) * 100
                     else:
                         completion_rate = 0.0

                     all_forms_for_display.append({
                         'type': 'public',
                         'name': template.name,
                         'period': assigned_form.period_name,
                         'date_info': latest_submission.submitted_at,
                         'completion_rate': completion_rate,
                        'completion_filled_items': filled_items,
                        'completion_total_items': total_possible_items,
                         'item_object': assigned_form,
                         'is_public': True,
                         'view_data_link': url_for('assignment_management.view_public_submissions', assignment_id=assigned_form.id),
                         'submission_count': len(submissions_list)
                     })
                 else:
                     current_app.logger.warning(f"Public Submission group found with no associated AssignedForm ID {pa_id} or template missing.")


            # Sort the combined list - sort by date_info, with None dates last
            all_forms_for_display.sort(key=lambda x: x['date_info'] if x['date_info'] is not None else datetime.max, reverse=False)

            # NEW: Separate assignments into current and past based on status and timestamp
            from datetime import timedelta, timezone
            one_month_ago = utcnow() - timedelta(days=30)
            one_year_ago = utcnow() - timedelta(days=365)

            for item in all_forms_for_display:
                if item['type'] == 'assigned':
                    # Closed assignments always go to past (with Reopen for admins)
                    try:
                        aes = item['item_object']
                        af = aes.assigned_form if aes else None
                        if af and af.is_effectively_closed:
                            past_assignments.append(item)
                            continue
                    except (AttributeError, TypeError):
                        pass
                    # For assigned forms, check if they should be in past submissions
                    if item['status'] == 'Requires Revision':
                        past_assignments.append(item)
                    elif item['status'] in ('Approved', 'Pending', 'In Progress'):
                        # Ensure status_timestamp is timezone-aware for comparison
                        status_ts = item.get('status_timestamp')
                        if status_ts is None:
                            try:
                                status_ts = item['item_object'].assigned_form.assigned_at
                            except Exception as e:
                                current_app.logger.debug("status_ts lookup failed: %s", e)
                                status_ts = None
                        if status_ts and status_ts.tzinfo is None:
                            status_ts = status_ts.replace(tzinfo=timezone.utc)
                        if item['status'] == 'Approved':
                            if status_ts and status_ts < one_month_ago:
                                past_assignments.append(item)
                            else:
                                current_assignments.append(item)
                        else:  # Pending or In Progress: move to past if older than 1 year
                            if status_ts and status_ts < one_year_ago:
                                past_assignments.append(item)
                            else:
                                current_assignments.append(item)
                    else:
                        current_assignments.append(item)
                else:
                    # Public submissions always go to current for now
                    current_assignments.append(item)


            # NEW: Fetch and categorize focal points for the selected context (only if country is known)
            if selected_country is not None:
                all_focal_points_for_country = (
                    User.query
                    .join(UserEntityPermission, User.id == UserEntityPermission.user_id)
                    .join(RbacUserRole, User.id == RbacUserRole.user_id)
                    .join(RbacRole, RbacUserRole.role_id == RbacRole.id)
                    .filter(
                        RbacRole.code == "assignment_editor_submitter",
                        UserEntityPermission.entity_type == 'country',
                        UserEntityPermission.entity_id == selected_country.id
                    )
                    .distinct()
                    .order_by(User.name)
                    .all()
                )

                from app.utils.organization_helpers import is_org_email
                admin_role_user_ids = set(
                    uid for (uid,) in db.session.query(RbacUserRole.user_id)
                    .join(RbacRole, RbacUserRole.role_id == RbacRole.id)
                    .filter(RbacRole.code.in_(["system_manager", "admin_core"]))
                    .all()
                )
                ns_focal_points = [fp for fp in all_focal_points_for_country if not is_org_email(fp.email)]
                org_focal_points = [
                    fp for fp in all_focal_points_for_country
                    if is_org_email(fp.email) and fp.id not in admin_role_user_ids
                ]
                current_app.logger.debug(f"Found {len(ns_focal_points)} NS focal points and {len(org_focal_points)} organization focal points for {selected_country.name}.")
            else:
                ns_focal_points = []
                org_focal_points = []

            # NEW: Fetch templates available for self-reporting for the selected country
            self_report_templates = FormTemplate.query.join(
                FormTemplateVersion,
                and_(
                    FormTemplate.id == FormTemplateVersion.template_id,
                    FormTemplateVersion.status == 'published'
                )
            ).filter(
                FormTemplateVersion.add_to_self_report == True
            ).all()
            # Sort by name (from published version) in Python since it's a property
            self_report_templates.sort(key=lambda t: t.name if t.name else "")

            current_app.logger.debug(
                f"Found {len(self_report_templates)} templates available for self-reporting (including already assigned ones) for {entity_display_name}."
            )


        else:
             current_app.logger.debug("No country selected or available for fetching assigned forms statuses.")

    # NEW: Fetch recent activities for the user and selected country
    recent_activities = []

    if selected_country:
        # Get recent activities for this country (last month, initial load of 10)
        recent_activities = get_country_recent_activities(
            country_id=selected_country.id,
            days=30,
            limit=10
        )

        current_app.logger.debug(f"Found {len(recent_activities)} recent activities for {selected_country.name}")

        # Post-process recent activities so matrix-style field changes only include changed cells
        try:
            for activity in recent_activities:
                params = getattr(activity, 'summary_params', None)
                if not isinstance(params, dict):
                    params = {}
                    activity.summary_params = params

                # Add period information if assignment_id is available
                assignment_id = getattr(activity, 'assignment_id', None)
                if assignment_id and 'period' not in params:
                    try:
                        aes = AssignmentEntityStatus.query.get(assignment_id)
                        if aes and aes.assigned_form:
                            period_name = aes.assigned_form.period_name
                            params['period'] = period_name
                            template_name = params.get('template', '')
                            if template_name:
                                params['template_period'] = f"{template_name} - {period_name}"
                    except Exception as e:
                        current_app.logger.debug(f"Could not get period for activity {assignment_id}: {e}")

                key = getattr(activity, 'summary_key', None)

                # Single field change
                if key == 'activity.form_data_updated.single':
                    old_val = params.get('old')
                    new_val = params.get('new')
                    trimmed_old, trimmed_new = _extract_changed_matrix_values(old_val, new_val)
                    if trimmed_old is not None and trimmed_new is not None:
                        params['old'] = trimmed_old
                        params['new'] = trimmed_new

                # Multiple field changes – each change entry may be matrix-style
                elif key == 'activity.form_data_updated.multiple' and isinstance(params.get('changes'), list):
                    for change in params['changes']:
                        if not isinstance(change, dict):
                            continue
                        old_val = change.get('old')
                        new_val = change.get('new')
                        trimmed_old, trimmed_new = _extract_changed_matrix_values(old_val, new_val)
                        if trimmed_old is not None and trimmed_new is not None:
                            change['old'] = trimmed_old
                            change['new'] = trimmed_new
        except Exception as e:
            current_app.logger.error(
                f"Error post-processing recent activities for matrix diffs: {e}",
                exc_info=True
            )

    # Always render the dashboard; the template handles None values where applicable
    return render_template("core/dashboard.html",
                       user=current_user,
                       user_countries=user_countries,
                       user_entities=user_entities,
                       selected_country=selected_country,
                       selected_entity=selected_entity,
                       selected_entity_type=selected_entity_type,
                       selected_entity_id=selected_entity_id,
                       all_forms_for_display=all_forms_for_display,
                       current_assignments=current_assignments,
                       past_assignments=past_assignments,
                       show_country_select=show_country_select,
                       show_entity_select=show_entity_select,
                       title=_("Dashboard"),
                       current_date=current_date,
                       ns_focal_points=ns_focal_points,
                       org_focal_points=org_focal_points,
                       self_report_templates=self_report_templates,
                       delete_form=delete_form,
                       reopen_form=reopen_form,
                       recent_activities=recent_activities,
                       approve_form=approve_form,
                       request_access_form=request_access_form,
                       pending_access_requests=pending_access_requests,
                       all_access_requests=all_access_requests,
                       can_request_multiple_countries=can_request_multiple_countries,
                       non_org_has_counting_request=non_org_has_counting_request,
                       enabled_entity_types=enabled_entity_groups,
                       get_localized_country_name=get_localized_country_name,
                       get_localized_national_society_name=_get_localized_national_society_name)


@bp.route("/load_more_activities", methods=["POST"])
@login_required
def load_more_activities():
    """Load more recent activities with pagination."""
    from app.services.notification.core import get_country_recent_activities

    try:
        offset = _parse_int(request.form.get('offset', 0), 'offset', minimum=0)
        limit = _parse_int(request.form.get('limit', 10), 'limit', minimum=1)
        country_id = _parse_int(request.form.get('country_id'), 'country_id', minimum=1)

        # Verify user has access to this country
        user_countries = get_user_countries()  # Uses current_user internally
        country_ids = [c['id'] for c in user_countries]  # Returns list of dicts, not objects

        from app.services.authorization_service import AuthorizationService
        if not AuthorizationService.has_country_access(current_user, country_id):
            from app.utils.api_responses import json_forbidden
            return json_forbidden('Access denied')

        # Get more activities - when loading more, go beyond the 1 month limit
        fetch_limit = offset + limit + 1
        all_activities = get_country_recent_activities(
            country_id=country_id,
            days=365,
            limit=fetch_limit
        )

        # Get the next batch
        more_activities = all_activities[offset:offset + limit] if offset < len(all_activities) else []
        has_more = len(all_activities) >= fetch_limit

        # Post-process activities (same as dashboard)
        for activity in more_activities:
            params = getattr(activity, 'summary_params', None)
            if not isinstance(params, dict):
                params = {}
                activity.summary_params = params

            # Add period information if assignment_id is available
            assignment_id = getattr(activity, 'assignment_id', None)
            if assignment_id and 'period' not in params:
                try:
                    aes = AssignmentEntityStatus.query.get(assignment_id)
                    if aes and aes.assigned_form:
                        period_name = aes.assigned_form.period_name
                        params['period'] = period_name
                        template_name = params.get('template', '')
                        if template_name:
                            params['template_period'] = f"{template_name} - {period_name}"
                except Exception as e:
                    current_app.logger.debug(f"Could not get period for activity {assignment_id}: {e}")

            # Trim matrix-style diffs so we only render changed cells
            try:
                key = getattr(activity, 'summary_key', None)

                if key == 'activity.form_data_updated.single':
                    old_val = params.get('old')
                    new_val = params.get('new')
                    trimmed_old, trimmed_new = _extract_changed_matrix_values(old_val, new_val)
                    if trimmed_old is not None and trimmed_new is not None:
                        params['old'] = trimmed_old
                        params['new'] = trimmed_new

                elif key == 'activity.form_data_updated.multiple' and isinstance(params.get('changes'), list):
                    for change in params['changes']:
                        if not isinstance(change, dict):
                            continue
                        old_val = change.get('old')
                        new_val = change.get('new')
                        trimmed_old, trimmed_new = _extract_changed_matrix_values(old_val, new_val)
                        if trimmed_old is not None and trimmed_new is not None:
                            change['old'] = trimmed_old
                            change['new'] = trimmed_new
            except Exception as e:
                current_app.logger.debug(f"Matrix diff trimming failed for load_more activities: {e}")

        # Render activities to HTML using template partial
        activity_html = render_template('core/activity_items_partial.html',
                                       recent_activities=more_activities,
                                       get_localized_template_name=get_localized_template_name,
                                       localized_field_name=localized_field_name,
                                       format_activity_value=format_activity_value,
                                       render_activity_summary=render_activity_summary,
                                       render_matrix_change=render_matrix_change,
                                       _=_,
                                       url_for=url_for)

        return json_ok(html=activity_html, has_more=has_more, count=len(more_activities))
    except ValueError as err:
        current_app.logger.warning(f"Invalid pagination parameters: {err}")
        return json_bad_request('Invalid request parameters.')
    except Exception as e:
        current_app.logger.error(f"Error loading more activities: {e}", exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)


@bp.route("/mark_notifications_read", methods=["POST"])
@login_required
def mark_notifications_read():
    """Mark selected notifications as read via AJAX."""
    from app.services.notification.service import NotificationService
    from app.utils.api_responses import json_bad_request, json_server_error, json_ok
    from app.utils.api_helpers import get_json_safe

    try:
        notification_ids = get_json_safe().get('notification_ids', [])
        if not notification_ids:
            return json_bad_request('No notifications specified')

        # Convert to list of ints if needed
        if isinstance(notification_ids, str):
            notification_ids = [int(id.strip()) for id in notification_ids.split(',') if id.strip().isdigit()]

        # Mark notifications as read (service handles ownership validation)
        success = NotificationService.mark_as_read(notification_ids, current_user.id)

        if success:
            return json_ok()
        else:
            return json_server_error('Failed to update notifications')

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)
