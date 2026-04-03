from app.utils.transactions import request_transaction_rollback
from contextlib import suppress
# File: Backoffice/app/routes/admin/user_management.py
from app.utils.datetime_helpers import utcnow
from app.utils.sql_utils import safe_ilike_pattern
"""
User Management Module - User CRUD operations and role management
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user
from app import db
from collections import defaultdict
from app.models import User, Country, UserEntityPermission, NSBranch, NSSubBranch, NSLocalUnit, SecretariatDivision, SecretariatDepartment, CountryAccessRequest
from app.models import (
    Notification,
    NotificationPreferences,
    NotificationCampaign,
    EmailDeliveryLog,
    EntityActivityLog,
    UserLoginLog,
    UserActivityLog,
    UserSessionLog,
    AdminActionLog,
    SecurityEvent,
    TemplateShare,
    DynamicIndicatorData,
    RepeatGroupInstance,
    SubmittedDocument,
    IndicatorBankHistory,
    IndicatorSuggestion,
    CommonWord,
    FormTemplate,
    FormTemplateVersion,
    SystemSettings,
    APIKey,
    PasswordResetToken,
    AIConversation,
    AIMessage,
)
from app.models.organization import SecretariatRegionalOffice, SecretariatClusterOffice
from app.models.enums import EntityType
from app.forms.system import UserForm
from app.routes.admin.shared import permission_required
from app.utils.form_localization import get_localized_country_name
from app.services.entity_service import EntityService
from app.utils.user_analytics import log_admin_action
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.api_responses import json_bad_request, json_forbidden, json_not_found, json_ok, json_ok_result, json_server_error, json_error, require_json_keys
from app.utils.error_handling import handle_json_view_exception
from app.utils.entity_groups import get_enabled_entity_groups, get_allowed_entity_type_codes
from app.models.system import UserDevice

bp = Blueprint("user_management", __name__, url_prefix="/admin")


def _apply_role_type_and_implications(
    requested_role_ids: list[int] | list,
    *,
    role_type: str | None,
    drop_role_codes: set[str] | None = None,
) -> list[int]:
    """
    Backend enforcement for role-type defaults and role implications.

    - If role_type == 'focal_point': ensure Assignment Viewer + Assignment Editor & Submitter are present.
    - Always drop deprecated "documents upload only" role(s) from the request (we treat upload as part of Editor & Submitter).

    Best-effort: if RBAC tables aren't available, returns cleaned ints only.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)

    cleaned: list[int] = []
    for rid in (requested_role_ids or []):
        with suppress(Exception):
            if rid is None:
                continue
            cleaned.append(int(rid))

    # de-dupe while preserving order
    seen = set()
    cleaned = [r for r in cleaned if not (r in seen or seen.add(r))]

    _log.debug("[_apply_role_type] ENTER role_type=%r, cleaned_ids=%s", role_type, cleaned)

    try:
        from app.models.rbac import RbacRole
    except Exception as e:
        current_app.logger.debug("RbacRole import failed: %s", e)
        return cleaned

    drop_role_codes = drop_role_codes or set()
    normalized_role_type = (role_type or "").strip().lower()

    # Auto-downgrade: "admin" without any admin_* roles and without assignment_approver
    # is effectively a focal point.  The UI does this client-side too, but we enforce here
    # as a safety net.
    if normalized_role_type == "admin" and cleaned:
        try:
            _rows = (
                RbacRole.query.with_entities(RbacRole.id, RbacRole.code)
                .filter(RbacRole.id.in_(cleaned))
                .all()
            )
            _codes = {str(code) for _, code in _rows if code}
            has_admin = any(c.startswith("admin_") or c == "system_manager" for c in _codes)
            has_approver = "assignment_approver" in _codes
            _log.debug("[_apply_role_type] auto-downgrade check: codes=%s, has_admin=%s, has_approver=%s", _codes, has_admin, has_approver)
            if not has_admin and not has_approver:
                normalized_role_type = "focal_point"
                _log.debug("[_apply_role_type] DOWNGRADED to focal_point")
        except Exception as e:
            current_app.logger.debug("_apply_role_type auto-downgrade check failed: %s", e)

    _log.debug("[_apply_role_type] normalized_role_type=%s", normalized_role_type)

    required_codes: list[str] = []
    if normalized_role_type == "focal_point":
        required_codes = ["assignment_viewer", "assignment_editor_submitter"]

        # IMPORTANT: Role Type is mutually exclusive between "Admin" and "Focal Point".
        # If the user is saved as a focal point, strip all admin roles regardless of what the form submitted
        # (UI may hide admin sections but not uncheck them).
        try:
            cleaned_rows = (
                RbacRole.query.with_entities(RbacRole.id, RbacRole.code)
                .filter(RbacRole.id.in_(cleaned))
                .all()
            )
            code_by_id = {int(rid): str(code) for rid, code in cleaned_rows if rid and code}
            cleaned = [
                rid
                for rid in cleaned
                if not (code_by_id.get(int(rid), "").startswith("admin_") or code_by_id.get(int(rid), "") == "system_manager")
            ]
        except Exception as e:
            current_app.logger.debug("RBAC code_by_id query failed: %s", e)

    # Assignment roles are now independent of admin_core — they must be explicitly assigned.
    # Do not auto-inject assignment roles based on admin role presence.

    # Resolve role IDs in bulk
    target_codes = set(drop_role_codes) | set(required_codes)
    if not target_codes:
        return cleaned

    rows = (
        RbacRole.query.with_entities(RbacRole.id, RbacRole.code)
        .filter(RbacRole.code.in_(list(target_codes)))
        .all()
    )
    id_by_code = {str(code): int(rid) for rid, code in rows if rid and code}

    # Drop deprecated codes (if present)
    drop_ids = {id_by_code[c] for c in drop_role_codes if c in id_by_code}
    if drop_ids:
        cleaned = [rid for rid in cleaned if rid not in drop_ids]

    # Add required codes (if present)
    for c in required_codes:
        rid = id_by_code.get(c)
        if rid and rid not in cleaned:
            cleaned.append(rid)

    return cleaned


def _get_allowed_non_country_entity_types():
    """Entity type codes for enabled groups excluding 'countries'."""
    groups = [g for g in get_enabled_entity_groups() if g != 'countries']
    return list(get_allowed_entity_type_codes(groups))


def _is_azure_sso_enabled() -> bool:
    """
    Return True when Azure AD B2C (OIDC) login is configured.

    When enabled, users may not have a local password (passwords are managed externally).
    """
    return bool(
        current_app.config.get("AZURE_B2C_TENANT")
        and current_app.config.get("AZURE_B2C_POLICY")
        and current_app.config.get("AZURE_B2C_CLIENT_ID")
        and current_app.config.get("AZURE_B2C_CLIENT_SECRET")
    )

# === User Management Routes ===
@bp.route("/users", methods=["GET"])
@permission_required('admin.users.view')
def manage_users():
    # Default ordering for the Users grid: stable, predictable by primary key
    users = User.query.order_by(User.id.asc()).all()
    # Preload RBAC roles for display (avoid N+1 queries in templates)
    rbac_roles_by_user_id = {}
    try:
        from app.models.rbac import RbacUserRole, RbacRole
        user_ids = [u.id for u in users]
        user_roles = RbacUserRole.query.filter(RbacUserRole.user_id.in_(user_ids)).all() if user_ids else []
        role_ids = list({ur.role_id for ur in user_roles})
        roles = RbacRole.query.filter(RbacRole.id.in_(role_ids)).all() if role_ids else []
        roles_by_id = {r.id: r for r in roles}
        for ur in user_roles:
            r = roles_by_id.get(ur.role_id)
            if not r:
                continue
            rbac_roles_by_user_id.setdefault(ur.user_id, []).append({"id": r.id, "code": r.code, "name": r.name})
    except Exception as e:
        current_app.logger.debug("rbac_roles_by_user_id query failed: %s", e)
        rbac_roles_by_user_id = {}

    # Preload entity permission counts + country names (avoid N+1 queries in templates)
    entity_counts_by_user_id = {}
    user_countries_by_id = {}
    try:
        from sqlalchemy import func

        user_ids = [u.id for u in users]
        if user_ids:
            # Counts by (user_id, entity_type)
            rows = (
                db.session.query(
                    UserEntityPermission.user_id,
                    UserEntityPermission.entity_type,
                    func.count(UserEntityPermission.id),
                )
                .filter(UserEntityPermission.user_id.in_(user_ids))
                .group_by(UserEntityPermission.user_id, UserEntityPermission.entity_type)
                .all()
            )
            for uid, etype, cnt in rows:
                entity_counts_by_user_id.setdefault(int(uid), {})[str(etype)] = int(cnt or 0)

            # Country names per user
            country_rows = (
                db.session.query(UserEntityPermission.user_id, Country.name)
                .join(Country, Country.id == UserEntityPermission.entity_id)
                .filter(
                    UserEntityPermission.user_id.in_(user_ids),
                    UserEntityPermission.entity_type == "country",
                )
                .order_by(Country.name.asc())
                .all()
            )
            for uid, cname in country_rows:
                user_countries_by_id.setdefault(int(uid), []).append(cname)
    except Exception as e:
        current_app.logger.debug("entity_counts/user_countries query failed: %s", e)
        entity_counts_by_user_id = {}
        user_countries_by_id = {}
    # Get all countries and group by region
    countries_by_region = defaultdict(list)
    all_countries = Country.query.order_by(Country.region, Country.name).all()
    for country in all_countries:
        region_name = country.region if country.region else "Unassigned Region"
        countries_by_region[region_name].append(country)

    pending_requests_count = CountryAccessRequest.query.filter_by(status='pending').count()

    return render_template("admin/user_management/users.html",
                           users=users,
                           title="Manage Users",
                           Country=Country,
                           countries_by_region=countries_by_region,
                           get_localized_country_name=get_localized_country_name,
                           pending_requests_count=pending_requests_count,
                           rbac_roles_by_user_id=rbac_roles_by_user_id,
                           entity_counts_by_user_id=entity_counts_by_user_id,
                           user_countries_by_id=user_countries_by_id)

@bp.route("/access-requests", methods=["GET"])
@permission_required('admin.access_requests.view')
def access_requests():
    """List and manage country access requests."""
    from app.utils.app_settings import get_auto_approve_access_requests
    pending_requests = CountryAccessRequest.query.filter_by(status='pending').order_by(CountryAccessRequest.created_at.asc()).all()
    processed_requests = CountryAccessRequest.query.filter(CountryAccessRequest.status.in_(['approved', 'rejected'])) \
        .order_by(CountryAccessRequest.processed_at.desc().nullslast(), CountryAccessRequest.created_at.desc()).limit(100).all()
    return render_template(
        "admin/user_management/access_requests.html",
        title="Country Access Requests",
        pending_requests=pending_requests,
        processed_requests=processed_requests,
        auto_approve_enabled=get_auto_approve_access_requests()
    )

@bp.route("/access-requests/<int:request_id>/approve", methods=["POST"])
@permission_required('admin.access_requests.approve')
def approve_access_request(request_id):
    """Approve a country access request and grant the permission."""
    req = CountryAccessRequest.query.get_or_404(request_id)
    if req.status != 'pending':
        flash("This request has already been processed.", "info")
        return redirect(url_for("user_management.access_requests"))
    try:
        # Grant permission
        user = User.query.get_or_404(req.user_id)
        country = Country.query.get_or_404(req.country_id)
        user.add_entity_permission(entity_type='country', entity_id=country.id)
        # Mark request as approved
        req.status = 'approved'
        req.processed_by_user_id = current_user.id
        req.processed_at = db.func.now()

        db.session.flush()  # Flush before logging

        # Log admin action
        log_admin_action(
            action_type='access_request_approve',
            description=f'Approved country access request for {user.email} to {country.name}',
            target_type='country_access_request',
            target_id=request_id,
            target_description=f'User: {user.email}, Country: {country.name}',
            new_values={
                'user_id': user.id,
                'user_email': user.email,
                'country_id': country.id,
                'country_name': country.name,
                'status': 'approved'
            },
            risk_level='low'
        )

        db.session.flush()

        # Send notification to user about being added to country
        try:
            from app.utils.notifications import notify_user_added_to_country
            notify_user_added_to_country(user.id, country.id)
        except Exception as e:
            current_app.logger.error(f"Error sending user added to country notification: {e}", exc_info=True)
            # Don't fail the approval if notification fails

        flash(f"Approved access for {user.email} to {country.name}.", "success")
    except Exception as e:
        request_transaction_rollback()
        flash("Could not approve request.", "danger")
    return redirect(url_for("user_management.access_requests"))

@bp.route("/access-requests/<int:request_id>/reject", methods=["POST"])
@permission_required('admin.access_requests.reject')
def reject_access_request(request_id):
    """Reject a country access request."""
    req = CountryAccessRequest.query.get_or_404(request_id)
    if req.status != 'pending':
        flash("This request has already been processed.", "info")
        return redirect(url_for("user_management.access_requests"))
    try:
        user = User.query.get(req.user_id)
        country = Country.query.get(req.country_id)

        req.status = 'rejected'
        req.processed_by_user_id = current_user.id
        req.processed_at = db.func.now()

        db.session.flush()  # Flush before logging

        # Log admin action
        log_admin_action(
            action_type='access_request_reject',
            description=f'Rejected country access request for {user.email if user else "unknown"} to {country.name if country else "unknown"}',
            target_type='country_access_request',
            target_id=request_id,
            target_description=f'User: {user.email if user else "unknown"}, Country: {country.name if country else "unknown"}',
            new_values={
                'user_id': req.user_id,
                'user_email': user.email if user else None,
                'country_id': req.country_id,
                'country_name': country.name if country else None,
                'status': 'rejected'
            },
            risk_level='low'
        )

        db.session.flush()
        flash("Request rejected.", "info")
    except Exception as e:
        request_transaction_rollback()
        flash("An error occurred. Please try again.", "danger")
    return redirect(url_for("user_management.access_requests"))

@bp.route("/access-requests/approve-all", methods=["POST"])
@permission_required('admin.access_requests.approve')
def approve_all_access_requests():
    """Approve all pending country access requests at once."""
    pending = CountryAccessRequest.query.filter_by(status='pending').all()
    if not pending:
        flash("No pending requests to approve.", "info")
        return redirect(url_for("user_management.access_requests"))

    approved_count = 0
    errors = []
    for req in pending:
        try:
            user = User.query.get(req.user_id)
            country = Country.query.get(req.country_id)
            if not user or not country:
                continue
            user.add_entity_permission(entity_type='country', entity_id=country.id)
            req.status = 'approved'
            req.processed_by_user_id = current_user.id
            req.processed_at = db.func.now()
            db.session.flush()

            log_admin_action(
                action_type='access_request_approve',
                description=f'Bulk-approved country access request for {user.email} to {country.name}',
                target_type='country_access_request',
                target_id=req.id,
                target_description=f'User: {user.email}, Country: {country.name}',
                new_values={
                    'user_id': user.id,
                    'user_email': user.email,
                    'country_id': country.id,
                    'country_name': country.name,
                    'status': 'approved'
                },
                risk_level='low'
            )
            db.session.flush()

            try:
                from app.utils.notifications import notify_user_added_to_country
                notify_user_added_to_country(user.id, country.id)
            except Exception as e:
                current_app.logger.debug("notify_user_added_to_country failed: %s", e)

            approved_count += 1
        except Exception as e:
            errors.append("Validation error.")

    if approved_count:
        flash(f"Approved {approved_count} request(s).", "success")
    if errors:
        flash(f"{len(errors)} request(s) could not be approved.", "danger")
    return redirect(url_for("user_management.access_requests"))


@bp.route("/users/new", methods=["GET", "POST"])
@permission_required('admin.users.create')
def new_user():
    """Admin route to add a new user."""
    form = UserForm()
    enabled_entity_groups = get_enabled_entity_groups()
    allowed_non_country_entity_types = _get_allowed_non_country_entity_types()
    from app.services.authorization_service import AuthorizationService
    from app.models.rbac import RbacRole
    azure_sso_enabled = _is_azure_sso_enabled()
    current_is_sys_mgr = AuthorizationService.is_system_manager(current_user)
    can_assign_rbac_roles = AuthorizationService.has_rbac_permission(current_user, "admin.users.roles.assign")

    # Only a system manager can assign the System Manager RBAC role
    sys_role = RbacRole.query.filter_by(code="system_manager").first()
    if sys_role and not current_is_sys_mgr:
        # Hide from choices
        form.rbac_roles.choices = [(rid, label) for (rid, label) in (form.rbac_roles.choices or []) if rid != sys_role.id]

    # Prevent privilege escalation: non-system-managers cannot assign certain high-privilege roles.
    restricted_role_ids = set()
    try:
        restricted_codes = ["system_manager", "admin_full", "admin_plugins_manager"]
        rows = RbacRole.query.filter(RbacRole.code.in_(restricted_codes)).with_entities(RbacRole.id).all()
        restricted_role_ids = {int(r[0]) for r in rows if r and r[0] is not None}
    except Exception as e:
        current_app.logger.debug("restricted_role_ids query failed: %s", e)
        restricted_role_ids = set()
    if not current_is_sys_mgr and restricted_role_ids:
        form.rbac_roles.choices = [
            (rid, label)
            for (rid, label) in (form.rbac_roles.choices or [])
            if int(rid) not in restricted_role_ids
        ]

    # If the current admin cannot assign roles, do not render/validate roles on this form.
    # (We will apply a safe default RBAC role on the backend.)
    if not can_assign_rbac_roles:
        form.rbac_roles.choices = []
    else:
        # Hide deprecated upload-only role: document upload is part of Editor & Submitter.
        # The role exists for backward compatibility but should not be assigned directly.
        try:
            deprecated = RbacRole.query.filter_by(code="assignment_documents_uploader").first()
            if deprecated:
                form.rbac_roles.choices = [
                    (rid, label)
                    for (rid, label) in (form.rbac_roles.choices or [])
                    if int(rid) != int(deprecated.id)
                ]
        except Exception as e:
            current_app.logger.debug("deprecated role filter failed: %s", e)

        # Non-system-managers can only assign admin roles they already have.
        # (They may still assign non-admin roles like assignment_* as needed.)
        if not current_is_sys_mgr and (form.rbac_roles.choices or []):
            form.rbac_roles.choices = _filter_role_choices_for_actor(form.rbac_roles.choices, current_user)

    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        name = form.name.data
        title = form.title.data
        assigned_country_ids = form.countries.data if 'countries' in enabled_entity_groups else []

        # Check if a user with this email already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("A user with this email address already exists.", "danger")
        else:
            # Check for restricted role assignments
            has_restricted_role = False
            if sys_role and (sys_role.id in (form.rbac_roles.data or [])) and not AuthorizationService.is_system_manager(current_user):
                flash("Only a System Manager can assign the System Manager role.", "danger")
                has_restricted_role = True

            plugins_role = RbacRole.query.filter_by(code="admin_plugins_manager").first()
            if plugins_role and (plugins_role.id in (form.rbac_roles.data or [])) and not AuthorizationService.is_system_manager(current_user):
                flash("Only a System Manager can assign the Plugins role.", "danger")
                has_restricted_role = True

            if not has_restricted_role:
                # For Azure SSO deployments, passwords are managed externally (users may have no local password).
                # For local auth deployments, require a password when creating a new user.
                if (not azure_sso_enabled) and (not password):
                    flash("Password is required to create a new user.", "danger")
                else:
                    # Create new user
                    new_user = User(email=email, name=name, title=title)
                    # Hash the password before saving (local auth only)
                    if (not azure_sso_enabled) and password:
                        new_user.set_password(password)

                    # Persist user early so we can reference new_user.id for related rows
                    db.session.add(new_user)
                    db.session.flush()  # Flush to get the user ID

                    # Assign countries to the new user (legacy)
                    if 'countries' in enabled_entity_groups and assigned_country_ids:
                        selected_countries = Country.query.filter(Country.id.in_(assigned_country_ids)).all()

                        # Also create entity permissions for these countries
                        for country in selected_countries:
                            perm = UserEntityPermission(
                                user_id=new_user.id,
                                entity_type=EntityType.country.value,
                                entity_id=country.id
                            )
                            db.session.add(perm)

                    # Assign RBAC roles (best-effort; no-op if RBAC not migrated)
                    if can_assign_rbac_roles and getattr(form, "rbac_roles", None) is not None and getattr(form.rbac_roles, "choices", None):
                        requested_role_ids = list(form.rbac_roles.data or [])
                        if (not current_is_sys_mgr) and restricted_role_ids:
                            requested_role_ids = [rid for rid in requested_role_ids if int(rid) not in restricted_role_ids]
                        # Backend enforcement: role_type defaults + drop deprecated upload-only role.
                        role_type = request.form.get("role_type")
                        requested_role_ids = _apply_role_type_and_implications(
                            requested_role_ids,
                            role_type=role_type,
                            drop_role_codes={"assignment_documents_uploader"},
                        )
                        if not current_is_sys_mgr:
                            requested_role_ids, dropped = _filter_requested_admin_roles_for_actor(requested_role_ids, current_user)
                            if dropped:
                                flash("Some admin roles were not applied because you can only assign admin roles you already have.", "warning")
                        _set_user_rbac_roles(new_user, requested_role_ids)
                    else:
                        _ensure_user_has_default_rbac_role(new_user, default_role_code="assignment_viewer")

                    # Handle entity permissions from form (NS Structure and Secretariat)
                    entity_permissions = request.form.getlist('entity_permissions')

                    # Group permissions by entity type
                    permissions_by_type = {}
                    for perm_str in entity_permissions:
                        if ':' in perm_str:
                            entity_type, entity_id = perm_str.split(':', 1)
                            try:
                                entity_id = int(entity_id)
                                # Skip countries - they're handled separately above
                                if entity_type != EntityType.country.value and entity_type in allowed_non_country_entity_types:
                                    if entity_type not in permissions_by_type:
                                        permissions_by_type[entity_type] = []
                                    permissions_by_type[entity_type].append(entity_id)
                            except (ValueError, TypeError):
                                continue  # Skip invalid entity IDs

                    # Add entity permissions
                    for entity_type, entity_ids in permissions_by_type.items():
                        for entity_id in entity_ids:
                            perm = UserEntityPermission(
                                user_id=new_user.id,
                                entity_type=entity_type,
                                entity_id=entity_id
                            )
                            db.session.add(perm)
                    db.session.flush()

                    # Log admin action for user creation
                    log_admin_action(
                        action_type='user_create',
                        description=f'Created new user: {new_user.email}',
                        target_type='user',
                        target_id=new_user.id,
                        target_description=f'{new_user.name or new_user.email}',
                        new_values={
                            'email': new_user.email,
                            'name': new_user.name,
                            'title': new_user.title,
                            'country_ids': assigned_country_ids or [],
                            'entity_permissions': entity_permissions
                        },
                        risk_level='medium'
                    )

                    db.session.flush()

                    # Send welcome email
                    try:
                        from app.utils.email_service import send_welcome_email
                        send_welcome_email(new_user)
                    except Exception as e:
                        current_app.logger.error(f"Failed to send welcome email to {new_user.email}: {e}", exc_info=True)
                        # Don't fail user creation if email fails

                    flash(f"User {new_user.email} created successfully.", "success")
                    return redirect(url_for("user_management.manage_users"))

    # Fetch countries and group by region for the template
    countries_by_region = _get_countries_by_region()

    return render_template("admin/user_management/user_form.html",
                           form=form,
                           title="Add New User",
                           countries_by_region=countries_by_region,
                           get_localized_country_name=get_localized_country_name,
                           enabled_entity_types=enabled_entity_groups,
                           azure_sso_enabled=azure_sso_enabled)

@bp.route("/users/edit_user/<int:user_id>", methods=["GET", "POST"])
@permission_required('admin.users.edit')
def edit_user(user_id):
    """Admin route to edit an existing user."""
    user = User.query.get_or_404(user_id)
    form = UserForm()
    enabled_entity_groups = get_enabled_entity_groups()
    allowed_non_country_entity_types = _get_allowed_non_country_entity_types()
    from app.services.authorization_service import AuthorizationService
    from app.models.rbac import RbacRole
    azure_sso_enabled = _is_azure_sso_enabled()

    sys_role = RbacRole.query.filter_by(code="system_manager").first()
    current_is_sys_mgr = AuthorizationService.is_system_manager(current_user)
    user_is_sys_mgr = AuthorizationService.is_system_manager(user)
    can_assign_rbac_roles = AuthorizationService.has_rbac_permission(current_user, "admin.users.roles.assign")
    editing_self = bool(
        getattr(current_user, "is_authenticated", False)
        and int(getattr(current_user, "id", 0) or 0) == int(getattr(user, "id", 0) or 0)
    )
    target_is_admin = bool(AuthorizationService.is_admin(user))

    # Only System Managers can modify *other* admins.
    if (not current_is_sys_mgr) and (not editing_self) and target_is_admin:
        flash("Only a System Manager can modify an admin user.", "danger")
        return redirect(url_for("user_management.manage_users"))

    # Prevent privilege escalation: non-system-managers cannot change their own RBAC roles.
    # Keep roles visible but read-only on the frontend.
    roles_read_only = bool(editing_self and not current_is_sys_mgr)
    if roles_read_only:
        can_assign_rbac_roles = False

    # Only a system manager can assign the System Manager RBAC role
    if sys_role and not current_is_sys_mgr:
        form.rbac_roles.choices = [(rid, label) for (rid, label) in (form.rbac_roles.choices or []) if rid != sys_role.id]

    # Prevent privilege escalation: non-system-managers cannot assign certain high-privilege roles.
    restricted_role_ids = set()
    try:
        restricted_codes = ["system_manager", "admin_full", "admin_plugins_manager"]
        rows = RbacRole.query.filter(RbacRole.code.in_(restricted_codes)).with_entities(RbacRole.id).all()
        restricted_role_ids = {int(r[0]) for r in rows if r and r[0] is not None}
    except Exception as e:
        current_app.logger.debug("restricted_role_ids query failed: %s", e)
        restricted_role_ids = set()
    if not current_is_sys_mgr and restricted_role_ids:
        form.rbac_roles.choices = [
            (rid, label)
            for (rid, label) in (form.rbac_roles.choices or [])
            if int(rid) not in restricted_role_ids
        ]

    # If the current admin cannot assign roles, do not render/validate roles on this form.
    # (We will preserve existing RBAC roles on save.)
    if not can_assign_rbac_roles and not roles_read_only:
        form.rbac_roles.choices = []
    else:
        # Hide deprecated upload-only role: document upload is part of Editor & Submitter.
        try:
            deprecated = RbacRole.query.filter_by(code="assignment_documents_uploader").first()
            if deprecated:
                form.rbac_roles.choices = [
                    (rid, label)
                    for (rid, label) in (form.rbac_roles.choices or [])
                    if int(rid) != int(deprecated.id)
                ]
        except Exception as e:
            current_app.logger.debug("deprecated role filter failed: %s", e)

        # Non-system-managers can only assign admin roles they already have.
        if (not current_is_sys_mgr) and can_assign_rbac_roles and (form.rbac_roles.choices or []):
            form.rbac_roles.choices = _filter_role_choices_for_actor(form.rbac_roles.choices, current_user)

    if form.validate_on_submit():
        # Enforce RBAC restrictions around System Manager role
        if user_is_sys_mgr and not current_is_sys_mgr:
            flash("Only a System Manager can modify a System Manager user.", "danger")
            countries_by_region = _get_countries_by_region()
            return render_template("admin/user_management/user_form.html",
                                   form=form,
                                   user=user,
                                   title=f"Edit User: {user.email}",
                                   countries_by_region=countries_by_region,
                                   get_localized_country_name=get_localized_country_name,
                                   enabled_entity_types=enabled_entity_groups,
                                   azure_sso_enabled=azure_sso_enabled)
        if sys_role and (sys_role.id in (form.rbac_roles.data or [])) and not current_is_sys_mgr:
            flash("Only a System Manager can assign the System Manager role.", "danger")
            countries_by_region = _get_countries_by_region()
            return render_template("admin/user_management/user_form.html",
                                   form=form,
                                   user=user,
                                   title=f"Edit User: {user.email}",
                                   countries_by_region=countries_by_region,
                                   get_localized_country_name=get_localized_country_name,
                                   enabled_entity_types=enabled_entity_groups,
                                   azure_sso_enabled=azure_sso_enabled)

        # Enforce RBAC restrictions around Plugins role
        plugins_role = RbacRole.query.filter_by(code="admin_plugins_manager").first()
        if plugins_role and (plugins_role.id in (form.rbac_roles.data or [])) and not current_is_sys_mgr:
            flash("Only a System Manager can assign the Plugins role.", "danger")
            countries_by_region = _get_countries_by_region()
            return render_template("admin/user_management/user_form.html",
                                   form=form,
                                   user=user,
                                   title=f"Edit User: {user.email}",
                                   countries_by_region=countries_by_region,
                                   get_localized_country_name=get_localized_country_name,
                                   enabled_entity_types=enabled_entity_groups,
                                   azure_sso_enabled=azure_sso_enabled)

        # Store old values for audit logging
        try:
            from app.models.rbac import RbacUserRole
            old_rbac_role_ids = [ur.role_id for ur in RbacUserRole.query.filter_by(user_id=user.id).all()]
        except Exception as e:
            current_app.logger.debug("old_rbac_role_ids query failed: %s", e)
            old_rbac_role_ids = []

        old_values = {
            'email': user.email,
            'name': user.name,
            'title': user.title,
            'rbac_role_ids': old_rbac_role_ids,
            'country_ids': [c.id for c in user.countries.all()] if hasattr(user, "countries") else []
        }

        # Update user details
        user.email = form.email.data
        user.name = form.name.data
        user.title = form.title.data

        # Update RBAC roles (best-effort; no-op if RBAC not migrated)
        import logging as _logging
        _log = _logging.getLogger(__name__)
        _log.warning("[role-downgrade-backend] can_assign_rbac_roles=%s, form.rbac_roles=%s, choices=%s",
                     can_assign_rbac_roles,
                     getattr(form, "rbac_roles", "MISSING"),
                     bool(getattr(getattr(form, "rbac_roles", None), "choices", None)))
        if can_assign_rbac_roles and getattr(form, "rbac_roles", None) is not None and getattr(form.rbac_roles, "choices", None):
            requested_role_ids = list(form.rbac_roles.data or [])
            _log.warning("[role-downgrade-backend] requested_role_ids from form: %s", requested_role_ids)
            if (not current_is_sys_mgr) and restricted_role_ids:
                requested_role_ids = [rid for rid in requested_role_ids if int(rid) not in restricted_role_ids]
            # Backend enforcement: role_type defaults + drop deprecated upload-only role.
            role_type = request.form.get("role_type")
            _log.warning("[role-downgrade-backend] role_type from form: %s", role_type)
            requested_role_ids = _apply_role_type_and_implications(
                requested_role_ids,
                role_type=role_type,
                drop_role_codes={"assignment_documents_uploader"},
            )
            if not current_is_sys_mgr:
                requested_role_ids, dropped = _filter_requested_admin_roles_for_actor(requested_role_ids, current_user)
                if dropped:
                    flash("Some admin roles were not applied because you can only assign admin roles you already have.", "warning")
            _log.warning("[role-downgrade-backend] FINAL requested_role_ids to save: %s", requested_role_ids)
            _set_user_rbac_roles(user, requested_role_ids)
        else:
            _log.warning("[role-downgrade-backend] SKIPPED role update (condition failed)")

        # Update password if provided (local auth only)
        if (not azure_sso_enabled) and form.password.data:
            user.set_password(form.password.data)

        # Update country assignments (legacy)
        if 'countries' in enabled_entity_groups:
            selected_country_ids = form.countries.data
            if selected_country_ids:
                selected_countries = Country.query.filter(Country.id.in_(selected_country_ids)).all()

                # Sync entity permissions for countries
                # Remove old country permissions
                UserEntityPermission.query.filter_by(
                    user_id=user.id,
                    entity_type=EntityType.country.value
                ).delete()

                # Add new country permissions
                for country in selected_countries:
                    perm = UserEntityPermission(
                        user_id=user.id,
                        entity_type=EntityType.country.value,
                        entity_id=country.id
                    )
                    db.session.add(perm)
            else:
                selected_country_ids = []
                # Remove all country permissions
                UserEntityPermission.query.filter_by(
                    user_id=user.id,
                    entity_type=EntityType.country.value
                ).delete()
        else:
            # Preserve existing assignments when countries are disabled
            selected_country_ids = [c.id for c in user.countries.all()] if hasattr(user, "countries") else []

        # Handle notification preferences
        from app.services.notification_service import NotificationService
        from app.models import NotificationType

        # Get or create notification preferences for the user
        preferences = NotificationService.get_notification_preferences(user.id)

        # Get enabled notification types from form
        email_types = request.form.getlist('notification_type_email')
        push_types = request.form.getlist('notification_type_push')

        # Get all notification types to determine if all are selected
        all_types = [nt.value for nt in NotificationType]

        # Determine if all types are selected
        all_email_selected = len(email_types) == len(all_types)
        all_push_selected = len(push_types) == len(all_types)

        # Update notification preferences from form data
        # email_notifications and push_notifications are determined by whether any types are selected
        frequency = request.form.get('notification_frequency', 'instant')
        preferences.email_notifications = all_email_selected or len(email_types) > 0
        preferences.sound_enabled = request.form.get('sound_enabled') == 'on'
        preferences.notification_frequency = frequency
        preferences.push_notifications = all_push_selected or len(push_types) > 0

        # Handle digest day and time
        if frequency == 'daily' or frequency == 'weekly':
            preferences.digest_time = request.form.get('digest_time') or None
            if frequency == 'weekly':
                preferences.digest_day = request.form.get('digest_day') or None
            else:
                preferences.digest_day = None  # Clear day for daily
        else:
            preferences.digest_day = None
            preferences.digest_time = None

        # If all types are selected, send empty list (backend interprets as all enabled)
        preferences.notification_types_enabled = [] if all_email_selected else email_types
        preferences.push_notification_types_enabled = [] if all_push_selected else push_types

        # Handle entity permissions from form (NS Structure and Secretariat)
        # Always remove all non-country entity permissions first, then add back what's in the form
        entity_permissions = request.form.getlist('entity_permissions')

        # Define all possible entity types (excluding countries which are handled separately)
        all_entity_types = allowed_non_country_entity_types

        # Remove all old entity permissions (excluding countries)
        for entity_type in all_entity_types:
            UserEntityPermission.query.filter_by(
                user_id=user.id,
                entity_type=entity_type
            ).delete()

        # Parse and add new entity permissions from form
        permissions_by_type = {}
        for perm_str in entity_permissions:
            if ':' in perm_str:
                entity_type, entity_id = perm_str.split(':', 1)
                try:
                    entity_id = int(entity_id)
                    # Skip countries - they're handled separately above
                    if entity_type != EntityType.country.value and entity_type in all_entity_types:
                        if entity_type not in permissions_by_type:
                            permissions_by_type[entity_type] = []
                        permissions_by_type[entity_type].append(entity_id)
                except (ValueError, TypeError):
                    continue  # Skip invalid entity IDs

        # Add new entity permissions
        for entity_type, entity_ids in permissions_by_type.items():
            for entity_id in entity_ids:
                perm = UserEntityPermission(
                    user_id=user.id,
                    entity_type=entity_type,
                    entity_id=entity_id
                )
                db.session.add(perm)

        # Prepare new values for audit logging
        try:
            from app.models.rbac import RbacUserRole
            new_rbac_role_ids = [ur.role_id for ur in RbacUserRole.query.filter_by(user_id=user.id).all()]
        except Exception as e:
            current_app.logger.debug("new_rbac_role_ids query failed: %s", e)
            new_rbac_role_ids = []

        new_values = {
            'email': user.email,
            'name': user.name,
            'title': user.title,
            'rbac_role_ids': new_rbac_role_ids,
            'country_ids': selected_country_ids or [],
            'entity_permissions': entity_permissions,
            'password_changed': bool(form.password.data)
        }

        # Determine risk level based on changes
        risk_level = 'low'
        if set(old_values.get('rbac_role_ids') or []) != set(new_values.get('rbac_role_ids') or []) or form.password.data:
            risk_level = 'medium'
        old_sys = bool(sys_role and sys_role.id in (old_values.get("rbac_role_ids") or []))
        new_sys = bool(sys_role and sys_role.id in (new_values.get("rbac_role_ids") or []))
        if old_sys != new_sys:
            risk_level = 'high'

        db.session.flush()  # Flush before logging

        # Log admin action for user update
        log_admin_action(
            action_type='user_update',
            description=f'Updated user: {user.email}',
            target_type='user',
            target_id=user.id,
            target_description=f'{user.name or user.email}',
            old_values=old_values,
            new_values=new_values,
            risk_level=risk_level
        )

        db.session.flush()
        flash(f"User '{user.name}' has been updated successfully.", "success")
        return redirect(url_for('user_management.manage_users'))

    # Pre-populate form with user data for GET request
    if request.method == 'GET':
        form.email.data = user.email
        form.name.data = user.name
        form.title.data = user.title
        form.countries.data = [c.id for c in user.countries.all()] if hasattr(user, "countries") else []

        # Pre-populate RBAC roles (best-effort)
        try:
            from app.models.rbac import RbacUserRole
            form.rbac_roles.data = [ur.role_id for ur in RbacUserRole.query.filter_by(user_id=user.id).all()]
        except Exception as e:
            current_app.logger.debug("form.rbac_roles populate failed: %s", e)
            form.rbac_roles.data = []

    # Fetch countries and group by region for the template
    countries_by_region = _get_countries_by_region()

    # Load notification preferences for the user
    from app.services.notification_service import NotificationService
    from app.routes.notifications import get_notification_types_for_user

    preferences = NotificationService.get_notification_preferences(user.id)
    notification_types_info = get_notification_types_for_user(user)

    # Ensure push notification fields exist (for backward compatibility)
    if not hasattr(preferences, 'push_notifications'):
        preferences.push_notifications = True
    if not hasattr(preferences, 'push_notification_types_enabled'):
        preferences.push_notification_types_enabled = []
    # Ensure digest fields exist (for backward compatibility)
    if not hasattr(preferences, 'digest_day'):
        preferences.digest_day = None
    if not hasattr(preferences, 'digest_time'):
        preferences.digest_time = None

    # Load registered devices ordered by last activity then creation (most recent first)
    # Get all devices including logged-out ones (for admin view)
    registered_devices = UserDevice.query.filter_by(user_id=user.id) \
        .order_by(UserDevice.last_active_at.desc().nullslast(), UserDevice.created_at.desc().nullslast()) \
        .all()

    # Determine the effective role type based on the user's actual RBAC roles.
    computed_role_type = "admin"
    try:
        from app.models.rbac import RbacUserRole, RbacRole
        user_role_codes = {
            str(code)
            for code, in (
                RbacUserRole.query.join(RbacRole, RbacUserRole.role_id == RbacRole.id)
                .with_entities(RbacRole.code)
                .filter(RbacUserRole.user_id == user.id)
                .all()
            )
        }
        has_admin_roles = any(c.startswith("admin_") or c == "system_manager" for c in user_role_codes)
        if not has_admin_roles:
            computed_role_type = "focal_point"
    except Exception as e:
        current_app.logger.debug("computed_role_type check failed: %s", e)

    return render_template("admin/user_management/user_form.html",
                           form=form,
                           user=user,
                           title=f"Edit User: {user.email}",
                           countries_by_region=countries_by_region,
                           get_localized_country_name=get_localized_country_name,
                           enabled_entity_types=enabled_entity_groups,
                           azure_sso_enabled=azure_sso_enabled,
                           roles_read_only=roles_read_only,
                           preferences=preferences,
                           notification_types_info=notification_types_info,
                           registered_devices=registered_devices,
                           computed_role_type=computed_role_type)


def _get_role_ids_by_code_for_user(user: User) -> dict:
    """Return a mapping of role_code -> role_id for roles assigned to a user (best-effort)."""
    try:
        from app.models.rbac import RbacUserRole, RbacRole
    except Exception as e:
        current_app.logger.debug("RbacUserRole/RbacRole import failed: %s", e)
        return {}
    try:
        rows = (
            RbacUserRole.query.join(RbacRole, RbacUserRole.role_id == RbacRole.id)
            .with_entities(RbacRole.code, RbacRole.id)
            .filter(RbacUserRole.user_id == int(getattr(user, "id", 0) or 0))
            .all()
        )
        return {str(code): int(rid) for code, rid in rows if code and rid}
    except Exception as e:
        current_app.logger.debug("_role_code_to_id_map query failed: %s", e)
        return {}


def _filter_requested_admin_roles_for_actor(requested_role_ids, actor: User):
    """
    Enforce: non-system-managers may only assign admin_* roles that they already have.
    Returns (filtered_role_ids, dropped_admin_role_ids).
    """
    try:
        from app.models.rbac import RbacRole
    except Exception as e:
        current_app.logger.debug("RbacRole import failed (_clean_requested_role_ids): %s", e)
        return list(requested_role_ids or []), []

    cleaned = []
    for rid in (requested_role_ids or []):
        try:
            cleaned.append(int(rid))
        except Exception as e:
            current_app.logger.debug("rid int parse failed: %s", e)
            continue
    if not cleaned:
        return [], []

    actor_role_ids_by_code = _get_role_ids_by_code_for_user(actor)
    actor_admin_role_ids = {rid for code, rid in actor_role_ids_by_code.items() if str(code).startswith("admin_")}

    # Resolve requested role codes
    role_rows = RbacRole.query.with_entities(RbacRole.id, RbacRole.code).filter(RbacRole.id.in_(cleaned)).all()
    code_by_id = {int(rid): str(code) for rid, code in role_rows if rid and code}

    dropped = []
    kept = []
    for rid in cleaned:
        code = code_by_id.get(int(rid), "")
        if code.startswith("admin_") and int(rid) not in actor_admin_role_ids:
            dropped.append(int(rid))
            continue
        kept.append(int(rid))
    return kept, dropped


def _filter_role_choices_for_actor(choices, actor: User):
    """
    Filter WTForms rbac_roles choices so non-system-managers only see admin_* roles they already have.
    Choices are [(id, label), ...].
    """
    try:
        from app.models.rbac import RbacRole
    except Exception as e:
        current_app.logger.debug("RbacRole import failed (_role_choices): %s", e)
        return list(choices or [])

    actor_role_ids_by_code = _get_role_ids_by_code_for_user(actor)
    actor_admin_role_ids = {rid for code, rid in actor_role_ids_by_code.items() if str(code).startswith("admin_")}

    ids = []
    for rid, _label in (choices or []):
        try:
            ids.append(int(rid))
        except Exception as e:
            current_app.logger.debug("rid int parse (_role_choices): %s", e)
            continue
    if not ids:
        return list(choices or [])

    rows = RbacRole.query.with_entities(RbacRole.id, RbacRole.code).filter(RbacRole.id.in_(ids)).all()
    code_by_id = {int(rid): str(code) for rid, code in rows if rid and code}

    filtered = []
    for rid, label in (choices or []):
        try:
            rid_int = int(rid)
        except Exception as e:
            current_app.logger.debug("rid_int parse failed: %s", e)
            continue
        code = code_by_id.get(rid_int, "")
        if code.startswith("admin_") and rid_int not in actor_admin_role_ids:
            continue
        filtered.append((rid_int, label))
    return filtered

@bp.route("/users/<int:user_id>/devices/<int:device_id>/kickout", methods=["POST"])
@permission_required('admin.users.devices.kickout')
def kickout_device(user_id, device_id):
    """Kick out (end session) for a specific device. Keeps device registered."""
    try:
        from datetime import datetime

        # Verify user exists
        user = User.query.get_or_404(user_id)

        # Verify device exists and belongs to user
        device = UserDevice.query.filter_by(id=device_id, user_id=user_id).first_or_404()

        # Check if device is already logged out
        if device.logged_out_at:
            return json_bad_request('Device is already logged out')

        # Mark device as logged out
        device.logged_out_at = utcnow()
        db.session.flush()

        # Log admin action
        log_admin_action(
            admin_user_id=current_user.id,
            action_type='kickout_device',
            target_user_id=user_id,
            details={
                'device_id': device_id,
                'platform': device.platform,
                'device_name': device.device_name,
                'device_token_preview': device.device_token[:15] + '...' if device.device_token else None
            }
        )

        current_app.logger.info(
            f"Admin {current_user.id} kicked out device {device_id} for user {user_id}"
        )

        return json_ok(message='Device session ended successfully')

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

@bp.route("/users/<int:user_id>/devices/<int:device_id>/remove", methods=["DELETE"])
@permission_required('admin.users.devices.remove')
def remove_device(user_id, device_id):
    """Remove a device from the registry. Permanently deletes the device record."""
    try:
        # Verify user exists
        user = User.query.get_or_404(user_id)

        # Verify device exists and belongs to user
        device = UserDevice.query.filter_by(id=device_id, user_id=user_id).first_or_404()

        # Store device info for logging before deletion
        device_info = {
            'device_id': device_id,
            'platform': device.platform,
            'device_name': device.device_name,
            'device_token_preview': device.device_token[:15] + '...' if device.device_token else None,
            'was_logged_out': device.logged_out_at is not None
        }

        # Delete the device
        db.session.delete(device)
        db.session.flush()

        # Log admin action
        log_admin_action(
            admin_user_id=current_user.id,
            action_type='remove_device',
            target_user_id=user_id,
            details=device_info
        )

        current_app.logger.info(
            f"Admin {current_user.id} removed device {device_id} for user {user_id}"
        )

        return json_ok(message='Device removed successfully')

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

@bp.route("/users/delete/<int:user_id>", methods=["POST"])
@permission_required('admin.users.delete')
def delete_user(user_id):
    # Only system managers can delete users
    from app.services.authorization_service import AuthorizationService
    if not current_user.is_authenticated or not AuthorizationService.is_system_manager(current_user):
        flash("Only system managers can delete users.", "danger")
        return redirect(url_for("user_management.manage_users"))

    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for("user_management.manage_users"))

    # Store user info for audit logging before deletion
    user_email = user.email
    user_name = user.name

    try:
        # Cascade first; if it raises, no audit entry is written for a deletion that never happened.
        # user_email / user_name are captured above so they survive after the user record is deleted.
        _cascade_delete_user_related(user)

        log_admin_action(
            action_type='user_delete',
            description=f'Deleted user: {user_email}',
            target_type='user',
            target_id=user_id,
            target_description=f'{user_name or user_email}',
            old_values={
                'email': user_email,
                'name': user_name,
            },
            risk_level='high'
        )

        flash(f"User {user_email} deleted successfully.", "success")
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error deleting user {user_id} ({user_email}): {e}", exc_info=True)
        flash(
            "Unable to delete user due to existing linked data. "
            "You can deactivate the user instead so they cannot log in.",
            "warning"
        )

    return redirect(url_for("user_management.manage_users"))


@bp.route("/api/users", methods=["GET"])
@permission_required('admin.users.view')
def api_users_list():
    """API endpoint to get users list in JSON format for Flutter app"""
    try:
        # Relationship is dynamic, so eager loading via selectinload is not supported
        users = User.query.order_by(User.id.asc()).all()
        user_ids = [user.id for user in users]

        # Pre-fetch RBAC roles for all users (avoid N+1 queries)
        roles_by_user_id = {}
        try:
            from app.models.rbac import RbacUserRole, RbacRole
            user_roles = RbacUserRole.query.filter(RbacUserRole.user_id.in_(user_ids)).all() if user_ids else []
            role_ids = list({ur.role_id for ur in user_roles})
            roles = RbacRole.query.filter(RbacRole.id.in_(role_ids)).all() if role_ids else []
            roles_by_id = {r.id: r for r in roles}
            for ur in user_roles:
                roles_by_user_id.setdefault(ur.user_id, []).append(roles_by_id.get(ur.role_id))
        except Exception as e:
            current_app.logger.debug("roles_by_user_id query failed: %s", e)
            roles_by_user_id = {}

        # PERFORMANCE: Pre-fetch all user entity permissions in bulk
        all_permissions = UserEntityPermission.query.filter(
            UserEntityPermission.user_id.in_(user_ids)
        ).all()

        # Group permissions by user_id and entity_type
        permissions_by_user = {}
        for perm in all_permissions:
            if perm.user_id not in permissions_by_user:
                permissions_by_user[perm.user_id] = {}
            if perm.entity_type not in permissions_by_user[perm.user_id]:
                permissions_by_user[perm.user_id][perm.entity_type] = 0
            permissions_by_user[perm.user_id][perm.entity_type] += 1

        # PERFORMANCE: Pre-fetch all countries for all users
        # Get all country IDs from user entity permissions
        country_permission_user_ids = [
            user_id for user_id, perms in permissions_by_user.items()
            if 'country' in perms
        ]
        country_ids = set()
        for perm in all_permissions:
            if perm.entity_type == 'country':
                country_ids.add(perm.entity_id)

        # Fetch all countries in one query
        from app.models import Country
        countries_by_id = {}
        if country_ids:
            countries = Country.query.filter(Country.id.in_(country_ids)).all()
            countries_by_id = {country.id: country for country in countries}

        # Build user-country mapping from permissions
        user_countries_map = {}
        for perm in all_permissions:
            if perm.entity_type == 'country' and perm.entity_id in countries_by_id:
                if perm.user_id not in user_countries_map:
                    user_countries_map[perm.user_id] = []
                user_countries_map[perm.user_id].append(countries_by_id[perm.entity_id])

        users_data = []
        for user in users:
            # Get user's countries from pre-fetched map
            user_countries = []
            for country in user_countries_map.get(user.id, []):
                user_countries.append({
                    'id': country.id,
                    'name': country.name,
                    'code': country.iso3,
                })

            # Get entity counts from pre-fetched permissions
            entity_counts = {}
            user_perms = permissions_by_user.get(user.id, {})

            if user_perms.get('ns_branch', 0) > 0:
                entity_counts['branches'] = user_perms['ns_branch']
            if user_perms.get('ns_subbranch', 0) > 0:
                entity_counts['sub_branches'] = user_perms['ns_subbranch']
            if user_perms.get('ns_localunit', 0) > 0:
                entity_counts['local_units'] = user_perms['ns_localunit']
            if user_perms.get('division', 0) > 0:
                entity_counts['divisions'] = user_perms['division']
            if user_perms.get('department', 0) > 0:
                entity_counts['departments'] = user_perms['department']
            if user_perms.get('regional_office', 0) > 0:
                entity_counts['regional_offices'] = user_perms['regional_office']

            cluster_perms = user_perms.get('cluster_office', 0)
            if cluster_perms > 0:
                entity_counts['cluster_offices'] = cluster_perms

            rbac_roles = []
            for r in (roles_by_user_id.get(user.id) or []):
                if not r:
                    continue
                rbac_roles.append({"id": r.id, "code": r.code, "name": r.name})

            users_data.append({
                'id': user.id,
                'email': user.email,
                'name': user.name,
                'title': user.title,
                'rbac_roles': rbac_roles,
                'active': user.active,
                'chatbot_enabled': user.chatbot_enabled,
                'profile_color': user.profile_color,
                'country_ids': [c.id for c in user_countries_map.get(user.id, [])],
                'countries': user_countries,
                'entity_counts': entity_counts if entity_counts else None,
            })

        return json_ok(status='success', data=users_data)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/users/profile-summary", methods=["GET"])
@permission_required('admin.users.view')
def api_users_profile_summary():
    """Return lightweight user profile summaries for AG Grid hover popups."""
    try:
        user_ids_raw = request.args.getlist('user_ids')
        if not user_ids_raw:
            user_ids_csv = (request.args.get('user_ids') or '').strip()
            if user_ids_csv:
                user_ids_raw = [part.strip() for part in user_ids_csv.split(',') if part.strip()]

        emails_raw = request.args.getlist('emails')
        if not emails_raw:
            emails_csv = (request.args.get('emails') or '').strip()
            if emails_csv:
                emails_raw = [part.strip() for part in emails_csv.split(',') if part.strip()]

        user_ids = []
        for value in user_ids_raw:
            with suppress(Exception):
                user_ids.append(int(value))

        emails = [str(email).strip().lower() for email in (emails_raw or []) if str(email).strip()]

        if not user_ids and not emails:
            return json_ok(status='success', profiles=[])

        query = User.query
        filters = []
        if user_ids:
            filters.append(User.id.in_(list(set(user_ids))))
        if emails:
            filters.append(db.func.lower(User.email).in_(list(set(emails))))
        if filters:
            from sqlalchemy import or_
            query = query.filter(or_(*filters))

        users = query.all()
        if not users:
            return json_ok(status='success', profiles=[])

        found_user_ids = [u.id for u in users]

        # Fetch last presence (most recent session activity) per user
        last_presence_by_user_id = {}
        with suppress(Exception):
            from sqlalchemy import func as sa_func
            last_presence_rows = (
                db.session.query(
                    UserSessionLog.user_id,
                    sa_func.max(UserSessionLog.last_activity).label('last_presence')
                )
                .filter(UserSessionLog.user_id.in_(found_user_ids))
                .group_by(UserSessionLog.user_id)
                .all()
            )
            for row in last_presence_rows:
                last_presence_by_user_id[row.user_id] = row.last_presence

        roles_by_user_id = {}
        with suppress(Exception):
            from app.models.rbac import RbacRole, RbacUserRole

            user_roles = RbacUserRole.query.filter(RbacUserRole.user_id.in_(found_user_ids)).all()
            role_ids = list({ur.role_id for ur in user_roles})
            roles = RbacRole.query.filter(RbacRole.id.in_(role_ids)).all() if role_ids else []
            roles_by_id = {r.id: r for r in roles}
            for ur in user_roles:
                role = roles_by_id.get(ur.role_id)
                if not role:
                    continue
                roles_by_user_id.setdefault(ur.user_id, []).append(role.name or role.code)

        all_permissions = UserEntityPermission.query.filter(
            UserEntityPermission.user_id.in_(found_user_ids)
        ).all()

        country_count_by_user_id = {}
        entity_counts_by_user_id = {}
        for perm in all_permissions:
            uid = int(perm.user_id)
            etype = str(perm.entity_type or '')
            if etype == 'country':
                country_count_by_user_id[uid] = country_count_by_user_id.get(uid, 0) + 1
            elif etype:
                bucket = entity_counts_by_user_id.setdefault(uid, {})
                bucket[etype] = int(bucket.get(etype, 0)) + 1

        profiles = []
        for user in users:
            profile_color = user.profile_color
            if not profile_color:
                with suppress(Exception):
                    profile_color = user.generate_profile_color()

            entity_counts = entity_counts_by_user_id.get(user.id, {})
            entity_summary_parts = []
            for key, value in sorted(entity_counts.items()):
                if int(value) > 0:
                    entity_summary_parts.append(f"{key.replace('_', ' ')}: {value}")

            last_presence_dt = last_presence_by_user_id.get(user.id)
            last_presence_iso = last_presence_dt.isoformat() + 'Z' if last_presence_dt else None

            profiles.append({
                'id': user.id,
                'name': user.name or '',
                'email': user.email or '',
                'title': user.title or '',
                'profile_color': profile_color or '#3B82F6',
                'active': bool(user.active),
                'last_presence': last_presence_iso,
                'rbac_roles': roles_by_user_id.get(user.id, []),
                'countries_count': int(country_count_by_user_id.get(user.id, 0)),
                'entity_counts': entity_counts,
                'entity_summary': ', '.join(entity_summary_parts),
            })

        return json_ok(status='success', profiles=profiles)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

@bp.route("/api/users/access-requests/count", methods=["GET"])
@permission_required('admin.access_requests.view')
def api_access_requests_count():
    """API endpoint to get pending access requests count"""
    try:
        count = CountryAccessRequest.query.filter_by(status='pending').count()
        return json_ok(status='success', data={'count': count})
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

@bp.route("/api/users/<int:user_id>/deletion-preview", methods=["GET"])
@permission_required('admin.users.delete')
def api_user_deletion_preview(user_id):
    """API endpoint to get user deletion preview in JSON format"""
    from app.services.authorization_service import AuthorizationService
    if not current_user.is_authenticated or not AuthorizationService.is_system_manager(current_user):
        return json_forbidden('Only system managers can delete users.')
    user = User.query.get_or_404(user_id)
    try:
        preview = _get_user_deletion_preview(user)
        return json_ok(status='success', data=preview)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

@bp.route("/users/<int:user_id>/deletion-preview", methods=["GET"])
@permission_required('admin.users.delete')
def user_deletion_preview(user_id):
    """Return a JSON preview of relational data that will be deleted or unassigned if this user is deleted."""
    from app.services.authorization_service import AuthorizationService
    if not current_user.is_authenticated or not AuthorizationService.is_system_manager(current_user):
        return json_forbidden('Only system managers can delete users.')
    user = User.query.get_or_404(user_id)
    try:
        preview = _get_user_deletion_preview(user)
        return json_ok(preview=preview)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/users/<int:user_id>/activate", methods=["POST"])
@permission_required('admin.users.deactivate')
def api_activate_user(user_id):
    """API endpoint to activate a user"""
    try:
        from app.services.authorization_service import AuthorizationService
        user = User.query.get_or_404(user_id)
        if user.id == current_user.id:
            return json_bad_request('You cannot activate your own account')
        if (not AuthorizationService.is_system_manager(current_user)) and AuthorizationService.is_admin(user):
            return json_forbidden('Only a System Manager can modify an admin user')
        old_active = bool(getattr(user, 'active', True))
        user.active = True
        user.deactivated_at = None

        db.session.flush()
        log_admin_action(
            action_type='user_update',
            description=f'Activated user: {user.email}',
            target_type='user',
            target_id=user.id,
            target_description=f'{user.name or user.email}',
            old_values={'active': old_active},
            new_values={'active': True},
            risk_level='medium'
        )
        db.session.flush()
        return json_ok(status='success', message='User activated successfully')
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

@bp.route("/api/users/<int:user_id>/deactivate", methods=["POST"])
@permission_required('admin.users.deactivate')
def api_deactivate_user(user_id):
    """API endpoint to deactivate a user"""
    try:
        from app.services.authorization_service import AuthorizationService
        user = User.query.get_or_404(user_id)
        if user.id == current_user.id:
            return json_bad_request('You cannot deactivate your own account')
        if (not AuthorizationService.is_system_manager(current_user)) and AuthorizationService.is_admin(user):
            return json_forbidden('Only a System Manager can modify an admin user')
        old_active = bool(getattr(user, 'active', True))
        user.active = False
        user.deactivated_at = db.func.now()

        db.session.flush()
        log_admin_action(
            action_type='user_update',
            description=f'Deactivated user: {user.email}',
            target_type='user',
            target_id=user.id,
            target_description=f'{user.name or user.email}',
            old_values={'active': old_active},
            new_values={'active': False},
            risk_level='medium'
        )
        db.session.flush()
        return json_ok(status='success', message='User deactivated successfully')
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

@bp.route("/users/archive/<int:user_id>", methods=["POST"])
@permission_required('admin.users.deactivate')
def archive_user(user_id):
    """Deactivate/Reactivate a user account (soft toggle)."""
    from app.services.authorization_service import AuthorizationService
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "danger")
        return redirect(url_for("user_management.manage_users"))
    if (not AuthorizationService.is_system_manager(current_user)) and AuthorizationService.is_admin(user):
        flash("Only a System Manager can modify an admin user.", "danger")
        return redirect(url_for("user_management.manage_users"))
    toggled_ok = False
    try:
        old_active = bool(getattr(user, 'active', True))
        new_active = not old_active
        user.active = new_active
        user.deactivated_at = None if new_active else db.func.now()

        db.session.flush()

        action = "reactivated" if new_active else "deactivated"
        log_admin_action(
            action_type='user_update',
            description=f'{action.capitalize()} user: {user.email}',
            target_type='user',
            target_id=user.id,
            target_description=f'{user.name or user.email}',
            old_values={'active': old_active},
            new_values={'active': new_active},
            risk_level='medium'
        )

        flash(f"User {user.email} {action} successfully.", "success")
        toggled_ok = True
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error toggling user active state {user_id}: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")

    # On success redirect back to the edit page so the button reflects the new state;
    # on failure redirect to the list (the edit page state would be stale anyway).
    if toggled_ok:
        return redirect(url_for("user_management.edit_user", user_id=user_id))
    return redirect(url_for("user_management.manage_users"))

# === Entity Permission Management Routes ===

@bp.route("/users/<int:user_id>/entities", methods=["GET"])
@permission_required('admin.users.grants.manage')
def get_user_entities(user_id):
    """Get all entities assigned to a user."""
    user = User.query.get_or_404(user_id)

    # Get all entity permissions for this user
    entity_permissions = UserEntityPermission.query.filter_by(user_id=user_id).all()

    entities_data = []
    for perm in entity_permissions:
        entity = EntityService.get_entity(perm.entity_type, perm.entity_id)
        if entity:
            entities_data.append({
                'permission_id': perm.id,
                'entity_type': perm.entity_type,
                'entity_id': perm.entity_id,
                'entity_name': EntityService.get_entity_name(perm.entity_type, perm.entity_id, include_hierarchy=True)
            })

    return json_ok(entities=entities_data)

@bp.route("/users/<int:user_id>/entities/add", methods=["POST"])
@permission_required('admin.users.grants.manage')
def add_user_entity(user_id):
    """Add an entity permission to a user."""
    try:
        user = User.query.get_or_404(user_id)

        data = get_json_safe()
        err = require_json_keys(data, ['entity_type', 'entity_id'])
        if err:
            return err

        entity_type = data.get('entity_type')
        entity_id = data.get('entity_id')

        if not entity_type or not str(entity_type).strip():
            return json_bad_request('entity_type is required')

        # Convert entity_id to int if it's a string
        try:
            entity_id = int(entity_id)
        except (ValueError, TypeError):
            return json_bad_request('entity_id must be a valid integer')

        # Validate entity exists
        entity = EntityService.get_entity(entity_type, entity_id)
        if not entity:
            return json_not_found('Entity not found')

        # Check if permission already exists
        existing_perm = UserEntityPermission.query.filter_by(
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id
        ).first()

        if existing_perm:
            return json_error('Permission already exists', 409)

        # Create new permission
        new_perm = UserEntityPermission(
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id
        )
        db.session.add(new_perm)

        # For country entities, also add to legacy user.countries
        if entity_type == EntityType.country.value:
            country = Country.query.get(entity_id)
            if country and country not in user.countries:
                user.countries.append(country)

        db.session.flush()

        return json_ok(
            permission_id=new_perm.id,
            entity_name=EntityService.get_entity_name(entity_type, entity_id, include_hierarchy=True),
        )
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

@bp.route("/users/<int:user_id>/entities/remove/<int:permission_id>", methods=["DELETE"])
@permission_required('admin.users.grants.manage')
def remove_user_entity(user_id, permission_id):
    """Remove an entity permission from a user."""
    try:
        user = User.query.get_or_404(user_id)
        perm = UserEntityPermission.query.filter_by(id=permission_id, user_id=user_id).first_or_404()

        # For country entities, also remove from legacy user.countries
        if perm.entity_type == EntityType.country.value:
            country = Country.query.get(perm.entity_id)
            if country and country in user.countries:
                user.countries.remove(country)

        db.session.delete(perm)
        db.session.flush()

        return json_ok()
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

@bp.route("/entities/search", methods=["GET"])
@permission_required('admin.users.grants.manage')
def search_entities():
    """Search for entities of a specific type."""
    entity_type = request.args.get('type')
    query = request.args.get('q', '').strip()

    if not entity_type:
        return json_bad_request('entity type is required')

    results = []

    try:
        safe_pattern = safe_ilike_pattern(query)
        if entity_type == EntityType.country.value:
            entities = Country.query.filter(Country.name.ilike(safe_pattern)).order_by(Country.name).limit(20).all()
            for entity in entities:
                results.append({
                    'id': entity.id,
                    'name': entity.name,
                    'display_name': entity.name,
                    'entity_type': entity_type
                })

        elif entity_type == EntityType.national_society.value:
            from app.models.organization import NationalSociety
            entities = NationalSociety.query.filter_by(is_active=True).join(Country).filter(
                db.or_(
                    NationalSociety.name.ilike(safe_pattern),
                    Country.name.ilike(safe_pattern)
                )
            ).order_by(Country.name, NationalSociety.name).limit(20).all()
            for entity in entities:
                country_name = entity.country.name if entity.country else ""
                display_name = f"{entity.name} ({country_name})" if country_name else entity.name
                results.append({
                    'id': entity.id,
                    'name': entity.name,
                    'display_name': display_name,
                    'entity_type': entity_type
                })

        elif entity_type == EntityType.ns_branch.value:
            entities = NSBranch.query.join(Country).filter(
                db.or_(
                    NSBranch.name.ilike(safe_pattern),
                    Country.name.ilike(safe_pattern)
                )
            ).order_by(Country.name, NSBranch.name).limit(20).all()
            for entity in entities:
                results.append({
                    'id': entity.id,
                    'name': entity.name,
                    'display_name': EntityService.get_entity_name(entity_type, entity.id, include_hierarchy=True),
                    'entity_type': entity_type
                })

        elif entity_type == EntityType.ns_subbranch.value:
            entities = NSSubBranch.query.join(NSBranch).join(Country).filter(
                NSSubBranch.name.ilike(safe_pattern)
            ).order_by(Country.name, NSBranch.name, NSSubBranch.name).limit(20).all()
            for entity in entities:
                results.append({
                    'id': entity.id,
                    'name': entity.name,
                    'display_name': EntityService.get_entity_name(entity_type, entity.id, include_hierarchy=True),
                    'entity_type': entity_type
                })

        elif entity_type == EntityType.division.value:
            entities = SecretariatDivision.query.filter(
                SecretariatDivision.name.ilike(safe_pattern)
            ).order_by(SecretariatDivision.name).limit(20).all()
            for entity in entities:
                results.append({
                    'id': entity.id,
                    'name': entity.name,
                    'display_name': entity.name,
                    'entity_type': entity_type
                })

        elif entity_type == EntityType.department.value:
            entities = SecretariatDepartment.query.join(SecretariatDivision).filter(
                db.or_(
                    SecretariatDepartment.name.ilike(safe_pattern),
                    SecretariatDivision.name.ilike(safe_pattern)
                )
            ).order_by(SecretariatDivision.name, SecretariatDepartment.name).limit(20).all()
            for entity in entities:
                results.append({
                    'id': entity.id,
                    'name': entity.name,
                    'display_name': EntityService.get_entity_name(entity_type, entity.id, include_hierarchy=True),
                    'entity_type': entity_type
                })

        elif entity_type == EntityType.regional_office.value:
            entities = SecretariatRegionalOffice.query.filter(
                SecretariatRegionalOffice.name.ilike(safe_pattern)
            ).order_by(SecretariatRegionalOffice.display_order, SecretariatRegionalOffice.name).limit(20).all()
            for entity in entities:
                results.append({
                    'id': entity.id,
                    'name': entity.name,
                    'display_name': entity.name,
                    'entity_type': entity_type
                })

        elif entity_type == EntityType.cluster_office.value:
            entities = SecretariatClusterOffice.query.join(SecretariatRegionalOffice).filter(
                db.or_(
                    SecretariatClusterOffice.name.ilike(safe_pattern),
                    SecretariatRegionalOffice.name.ilike(safe_pattern)
                )
            ).order_by(SecretariatRegionalOffice.name, SecretariatClusterOffice.name).limit(20).all()
            for entity in entities:
                results.append({
                    'id': entity.id,
                    'name': entity.name,
                    'display_name': EntityService.get_entity_name(entity_type, entity.id, include_hierarchy=True),
                    'entity_type': entity_type
                })

        return json_ok(results=results)

    except Exception as e:
        return json_server_error(GENERIC_ERROR_MESSAGE)

@bp.route("/structure/ns-hierarchy", methods=["GET"])
@permission_required('admin.users.grants.manage')
def get_ns_hierarchy():
    """Get NS structure hierarchy. If country_id provided, return branches-only for that country; otherwise grouped by country."""
    try:
        country_id = request.args.get('country_id', type=int)

        def build_branch_tree_for_country(country):
            items = []
            branches = NSBranch.query.filter_by(country_id=country.id, is_active=True).order_by(NSBranch.name).all()
            for branch in branches:
                branch_data = {
                    'id': branch.id,
                    'name': branch.name,
                    'code': branch.code,
                    'type': 'ns_branch',
                    'parent_id': country.id,
                    'children': []
                }
                subbranches = NSSubBranch.query.filter_by(branch_id=branch.id, is_active=True).order_by(NSSubBranch.name).all()
                for subbranch in subbranches:
                    subbranch_data = {
                        'id': subbranch.id,
                        'name': subbranch.name,
                        'code': subbranch.code,
                        'type': 'ns_subbranch',
                        'parent_id': branch.id,
                        'children': []
                    }
                    local_units = NSLocalUnit.query.filter_by(
                        branch_id=branch.id,
                        subbranch_id=subbranch.id,
                        is_active=True
                    ).order_by(NSLocalUnit.name).all()
                    for local_unit in local_units:
                        subbranch_data['children'].append({
                            'id': local_unit.id,
                            'name': local_unit.name,
                            'code': local_unit.code,
                            'type': 'ns_localunit',
                            'parent_id': subbranch.id
                        })
                    branch_data['children'].append(subbranch_data)
                direct_local_units = NSLocalUnit.query.filter(
                    NSLocalUnit.branch_id == branch.id,
                    NSLocalUnit.subbranch_id.is_(None),
                    NSLocalUnit.is_active == True
                ).order_by(NSLocalUnit.name).all()
                for local_unit in direct_local_units:
                    branch_data['children'].append({
                        'id': local_unit.id,
                        'name': local_unit.name,
                        'code': local_unit.code,
                        'type': 'ns_localunit',
                        'parent_id': branch.id
                    })
                items.append(branch_data)
            return items

        # If a country_id is provided, return a flat list of branches for that country
        if country_id:
            country = Country.query.get_or_404(country_id)
            hierarchy = build_branch_tree_for_country(country)
            return json_ok(hierarchy=hierarchy)

        # Default: grouped by country for backward compatibility
        countries = Country.query.order_by(Country.name).all()
        hierarchy = []
        for country in countries:
            children = build_branch_tree_for_country(country)
            if children:
                hierarchy.append({
                    'id': country.id,
                    'name': country.name,
                    'type': 'country',
                    'children': children
                })
        return json_ok(hierarchy=hierarchy)

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

@bp.route("/structure/secretariat-hierarchy", methods=["GET"])
@permission_required('admin.users.grants.manage')
def get_secretariat_hierarchy():
    """Get Secretariat structure hierarchy (divisions and departments)."""
    try:
        # Get all divisions (avoid eager loading on dynamic relationships)
        divisions = SecretariatDivision.query.filter_by(is_active=True).order_by(SecretariatDivision.display_order, SecretariatDivision.name).all()

        hierarchy = []
        for division in divisions:
            division_data = {
                'id': division.id,
                'name': division.name,
                'code': division.code,
                'type': 'division',
                'children': []
            }

            # Get departments for this division
            departments = SecretariatDepartment.query.filter_by(
                division_id=division.id,
                is_active=True
            ).order_by(SecretariatDepartment.display_order, SecretariatDepartment.name).all()

            for department in departments:
                division_data['children'].append({
                    'id': department.id,
                    'name': department.name,
                    'code': department.code,
                    'type': 'department',
                    'parent_id': division.id
                })

            hierarchy.append(division_data)

        return json_ok(hierarchy=hierarchy)

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

@bp.route("/entities/hierarchical", methods=["GET"])
@permission_required('admin.users.grants.manage')
def get_hierarchical_entities():
    """Get all entities grouped hierarchically for entity selection."""
    try:
        entity_types = request.args.getlist('types')  # List of entity types to include

        if not entity_types:
            return json_bad_request('At least one entity type must be specified')

        result = {}

        # Countries grouped by region
        if 'country' in entity_types:
            countries_by_region = defaultdict(list)
            countries = Country.query.order_by(Country.region, Country.name).all()
            for country in countries:
                region = country.region if country.region else "Unassigned Region"
                countries_by_region[region].append({
                    'id': country.id,
                    'name': country.name,
                    'type': 'country',
                    'entity_type': 'country'
                })
            result['countries'] = dict(countries_by_region)

        # National Societies grouped by country
        if 'national_society' in entity_types:
            from app.models.organization import NationalSociety
            national_societies_by_country = defaultdict(list)
            national_societies = NationalSociety.query.filter_by(is_active=True).join(Country).order_by(Country.name, NationalSociety.name).all()
            for ns in national_societies:
                country_name = ns.country.name if ns.country else "Unknown"
                national_societies_by_country[country_name].append({
                    'id': ns.id,
                    'name': ns.name,
                    'type': 'national_society',
                    'entity_type': 'national_society',
                    'country_id': ns.country_id
                })
            result['national_societies'] = dict(national_societies_by_country)

        # NS Branches grouped by country
        if 'ns_branch' in entity_types:
            ns_branches_by_country = defaultdict(list)
            branches = NSBranch.query.filter_by(is_active=True).join(Country).order_by(Country.name, NSBranch.name).all()
            for branch in branches:
                country_name = branch.country.name if branch.country else "Unknown"
                ns_branches_by_country[country_name].append({
                    'id': branch.id,
                    'name': branch.name,
                    'type': 'ns_branch',
                    'entity_type': 'ns_branch',
                    'country_id': branch.country_id
                })
            result['ns_branches'] = dict(ns_branches_by_country)

        # NS Sub-branches grouped by country (via branch)
        if 'ns_subbranch' in entity_types:
            ns_subbranches_by_country = defaultdict(list)
            subbranches = NSSubBranch.query.filter_by(is_active=True).join(NSBranch).join(Country).order_by(Country.name, NSBranch.name, NSSubBranch.name).all()
            for subbranch in subbranches:
                country_name = subbranch.branch.country.name if subbranch.branch and subbranch.branch.country else "Unknown"
                ns_subbranches_by_country[country_name].append({
                    'id': subbranch.id,
                    'name': subbranch.name,
                    'type': 'ns_subbranch',
                    'entity_type': 'ns_subbranch',
                    'branch_id': subbranch.branch_id,
                    'country_id': subbranch.branch.country_id if subbranch.branch else None
                })
            result['ns_subbranches'] = dict(ns_subbranches_by_country)

        # NS Local Units grouped by country (via branch)
        if 'ns_localunit' in entity_types:
            ns_localunits_by_country = defaultdict(list)
            local_units = NSLocalUnit.query.filter_by(is_active=True).join(NSBranch).join(Country).order_by(Country.name, NSBranch.name, NSLocalUnit.name).all()
            for local_unit in local_units:
                country_name = local_unit.branch.country.name if local_unit.branch and local_unit.branch.country else "Unknown"
                ns_localunits_by_country[country_name].append({
                    'id': local_unit.id,
                    'name': local_unit.name,
                    'type': 'ns_localunit',
                    'entity_type': 'ns_localunit',
                    'branch_id': local_unit.branch_id,
                    'country_id': local_unit.branch.country_id if local_unit.branch else None
                })
            result['ns_localunits'] = dict(ns_localunits_by_country)

        # Divisions (top level, no grouping)
        if 'division' in entity_types:
            divisions = SecretariatDivision.query.filter_by(is_active=True).order_by(SecretariatDivision.display_order, SecretariatDivision.name).all()
            result['divisions'] = [{
                'id': div.id,
                'name': div.name,
                'type': 'division',
                'entity_type': 'division'
            } for div in divisions]

        # Departments grouped by division
        if 'department' in entity_types:
            departments_by_division = defaultdict(list)
            departments = SecretariatDepartment.query.filter_by(is_active=True).join(SecretariatDivision).order_by(SecretariatDivision.name, SecretariatDepartment.name).all()
            for dept in departments:
                division_name = dept.division.name if dept.division else "Unknown"
                departments_by_division[division_name].append({
                    'id': dept.id,
                    'name': dept.name,
                    'type': 'department',
                    'entity_type': 'department',
                    'division_id': dept.division_id
                })
            result['departments'] = dict(departments_by_division)

        # Regional Offices (top level, no grouping)
        if 'regional_office' in entity_types:
            regional_offices = SecretariatRegionalOffice.query.filter_by(is_active=True).order_by(SecretariatRegionalOffice.display_order, SecretariatRegionalOffice.name).all()
            result['regional_offices'] = [{
                'id': ro.id,
                'name': ro.name,
                'type': 'regional_office',
                'entity_type': 'regional_office'
            } for ro in regional_offices]

        # Cluster Offices grouped by regional office
        if 'cluster_office' in entity_types:
            cluster_offices_by_region = defaultdict(list)
            cluster_offices = SecretariatClusterOffice.query.filter_by(is_active=True).join(SecretariatRegionalOffice).order_by(SecretariatRegionalOffice.name, SecretariatClusterOffice.name).all()
            for co in cluster_offices:
                region_name = co.regional_office.name if co.regional_office else "Unknown"
                cluster_offices_by_region[region_name].append({
                    'id': co.id,
                    'name': co.name,
                    'type': 'cluster_office',
                    'entity_type': 'cluster_office',
                    'regional_office_id': co.regional_office_id
                })
            result['cluster_offices'] = dict(cluster_offices_by_region)

        return json_ok_result(result)

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

@bp.route("/structure/secretariat-regions-hierarchy", methods=["GET"])
@permission_required('admin.users.grants.manage')
def get_secretariat_regions_hierarchy():
    """Get Secretariat Regions hierarchy (regional offices > cluster offices)."""
    try:
        # Load regional offices
        regions = SecretariatRegionalOffice.query.filter_by(is_active=True).order_by(SecretariatRegionalOffice.display_order, SecretariatRegionalOffice.name).all()

        hierarchy = []
        for region in regions:
            node = {
                'id': region.id,
                'name': region.name,
                'code': region.code,
                'type': 'regional_office',
                'children': []
            }

            clusters = SecretariatClusterOffice.query.filter_by(regional_office_id=region.id, is_active=True) \
                .order_by(SecretariatClusterOffice.display_order, SecretariatClusterOffice.name).all()
            for cluster in clusters:
                node['children'].append({
                    'id': cluster.id,
                    'name': cluster.name,
                    'code': cluster.code,
                    'type': 'cluster_office',
                    'parent_id': region.id
                })

            hierarchy.append(node)

        return json_ok(hierarchy=hierarchy)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

# === Helper Functions ===

def _get_countries_by_region():
    """Get countries grouped by region for form display"""
    countries_by_region = defaultdict(list)
    all_countries = Country.query.order_by(Country.region, Country.name).all()
    for country in all_countries:
        region_name = country.region if country.region else "Unassigned Region"
        countries_by_region[region_name].append(country)
    return countries_by_region

def _set_user_rbac_roles(user: User, role_ids):
    """Replace RBAC roles for a user (idempotent).

    Safe no-op if RBAC tables are not available (pre-migration).
    """
    try:
        from app.models.rbac import RbacUserRole
    except Exception as e:
        current_app.logger.debug("RbacUserRole import failed: %s", e)
        return

    user_id = getattr(user, "id", None)
    if not user_id:
        return

    cleaned = []
    for rid in (role_ids or []):
        with suppress(Exception):
            if rid is None:
                continue
            cleaned.append(int(rid))
    # de-dupe while preserving order
    seen = set()
    cleaned = [r for r in cleaned if not (r in seen or seen.add(r))]

    # Replace all user roles
    RbacUserRole.query.filter_by(user_id=user_id).delete()
    for rid in cleaned:
        db.session.add(RbacUserRole(user_id=user_id, role_id=rid))


def _ensure_user_has_default_rbac_role(user: User, *, default_role_code: str = "assignment_viewer") -> None:
    """
    Ensure the user has at least one RBAC role (safe default) when the current
    actor is not allowed to assign roles via the UI.

    Best-effort: no-op if RBAC tables are not available yet.
    """
    try:
        from app.models.rbac import RbacRole, RbacUserRole
    except Exception as e:
        current_app.logger.debug("RbacRole/RbacUserRole import failed: %s", e)
        return

    user_id = getattr(user, "id", None)
    if not user_id:
        return

    try:
        existing = RbacUserRole.query.filter_by(user_id=user_id).first()
        if existing:
            return
    except Exception as e:
        current_app.logger.debug("RBAC grant check failed: %s", e)
        return

    role = RbacRole.query.filter_by(code=default_role_code).first()
    if not role:
        # Create a minimal role record if seeding hasn't been run yet.
        role = RbacRole(code=default_role_code, name="Assignment Viewer", description="Read-only access to assignments.")
        db.session.add(role)
        db.session.flush()

    # Assign the role
    db.session.add(RbacUserRole(user_id=user_id, role_id=int(role.id)))

def _get_user_deletion_preview(user: User) -> dict:
    """Build a summary of data that will be deleted or unassigned when deleting the given user."""
    uid = user.id
    # Some tables reference user-owned rows indirectly (e.g., EmailDeliveryLog -> Notification).
    # Use subqueries so the preview matches what the delete cascade will actually remove.
    notif_ids_select = db.select(Notification.id).where(Notification.user_id == uid)
    will_delete = {
        'notifications': Notification.query.filter_by(user_id=uid).count(),
        'notification_preferences': 1 if NotificationPreferences.query.filter_by(user_id=uid).first() else 0,
        'entity_activity_logs': EntityActivityLog.query.filter_by(user_id=uid).count(),
        'country_access_requests': CountryAccessRequest.query.filter_by(user_id=uid).count(),
        'admin_action_logs': AdminActionLog.query.filter_by(admin_user_id=uid).count(),
        'user_session_logs': UserSessionLog.query.filter_by(user_id=uid).count(),
        'template_shares_given': TemplateShare.query.filter_by(shared_by_user_id=uid).count(),
        'template_shares_received': TemplateShare.query.filter_by(shared_with_user_id=uid).count(),
        'dynamic_indicator_data': DynamicIndicatorData.query.filter_by(added_by_user_id=uid).count(),
        'repeat_group_instances': RepeatGroupInstance.query.filter_by(created_by_user_id=uid).count(),
        'submitted_documents': SubmittedDocument.query.filter_by(uploaded_by_user_id=uid).count(),
        'indicator_bank_history': IndicatorBankHistory.query.filter_by(user_id=uid).count(),
        'entity_permissions': UserEntityPermission.query.filter_by(user_id=uid).count(),
        'user_devices': UserDevice.query.filter_by(user_id=uid).count(),
        # Delete logs either owned by this user, OR linked to notifications owned by this user
        'email_delivery_logs': EmailDeliveryLog.query.filter(
            db.or_(
                EmailDeliveryLog.user_id == uid,
                EmailDeliveryLog.notification_id.in_(notif_ids_select),
            )
        ).count(),
        'password_reset_tokens': PasswordResetToken.query.filter_by(user_id=uid).count(),
        'api_keys': APIKey.query.filter_by(user_id=uid).count(),
        'notification_campaigns': NotificationCampaign.query.filter_by(created_by=uid).count(),
        'ai_conversations': AIConversation.query.filter_by(user_id=uid).count(),
        'ai_messages': AIMessage.query.filter_by(user_id=uid).count(),
        'user_activity_logs': UserActivityLog.query.filter_by(user_id=uid).count(),
    }
    will_unassign = {
        'user_login_logs': UserLoginLog.query.filter_by(user_id=uid).count(),
        'security_events_reported': SecurityEvent.query.filter_by(user_id=uid).count(),
        'security_events_resolved_by': SecurityEvent.query.filter_by(resolved_by_user_id=uid).count(),
        'country_access_requests_processed': CountryAccessRequest.query.filter_by(processed_by_user_id=uid).count(),
        'api_keys_created_by': APIKey.query.filter_by(created_by_user_id=uid).count(),
        'system_settings_updated': SystemSettings.query.filter_by(updated_by_user_id=uid).count(),
        'indicator_suggestions_reviewed': IndicatorSuggestion.query.filter_by(reviewed_by_user_id=uid).count(),
        'common_words_created': CommonWord.query.filter_by(created_by_user_id=uid).count(),
    }
    return {
        'will_delete': will_delete,
        'will_unassign': will_unassign,
    }

def _cascade_delete_user_related(user: User) -> None:
    """Delete or unassign records that reference the given user, then delete the user itself."""
    uid = user.id

    # 1) Clear entity permissions (legacy countries derived from permissions)
    UserEntityPermission.query.filter_by(user_id=uid).delete(synchronize_session=False)

    # 2) Delete direct ownership rows that must not remain
    # IMPORTANT: delete dependent rows first to satisfy FK constraints (e.g. email_delivery_log -> notification)
    notif_ids_select = db.select(Notification.id).where(Notification.user_id == uid)
    EmailDeliveryLog.query.filter(
        db.or_(
            EmailDeliveryLog.user_id == uid,
            EmailDeliveryLog.notification_id.in_(notif_ids_select),
        )
    ).delete(synchronize_session=False)
    Notification.query.filter_by(user_id=uid).delete(synchronize_session=False)
    prefs = NotificationPreferences.query.filter_by(user_id=uid).first()
    if prefs:
        db.session.delete(prefs)
    EntityActivityLog.query.filter_by(user_id=uid).delete(synchronize_session=False)
    CountryAccessRequest.query.filter_by(user_id=uid).delete(synchronize_session=False)
    AdminActionLog.query.filter_by(admin_user_id=uid).delete(synchronize_session=False)
    UserSessionLog.query.filter_by(user_id=uid).delete(synchronize_session=False)
    TemplateShare.query.filter(
        db.or_(TemplateShare.shared_by_user_id == uid, TemplateShare.shared_with_user_id == uid)
    ).delete(synchronize_session=False)
    DynamicIndicatorData.query.filter_by(added_by_user_id=uid).delete(synchronize_session=False)
    RepeatGroupInstance.query.filter_by(created_by_user_id=uid).delete(synchronize_session=False)
    SubmittedDocument.query.filter_by(uploaded_by_user_id=uid).delete(synchronize_session=False)
    IndicatorBankHistory.query.filter_by(user_id=uid).delete(synchronize_session=False)
    UserDevice.query.filter_by(user_id=uid).delete(synchronize_session=False)
    PasswordResetToken.query.filter_by(user_id=uid).delete(synchronize_session=False)
    APIKey.query.filter_by(user_id=uid).delete(synchronize_session=False)
    NotificationCampaign.query.filter_by(created_by=uid).delete(synchronize_session=False)
    # AI chat tables do not define DB-level cascade; delete children first
    AIMessage.query.filter_by(user_id=uid).delete(synchronize_session=False)
    AIConversation.query.filter_by(user_id=uid).delete(synchronize_session=False)

    # 3) Unassign nullable references to preserve history
    # user_activity_log.user_id is NOT NULL in the current schema; delete these logs instead
    UserActivityLog.query.filter_by(user_id=uid).delete(synchronize_session=False)
    UserLoginLog.query.filter_by(user_id=uid).update({'user_id': None}, synchronize_session=False)
    SecurityEvent.query.filter_by(user_id=uid).update({'user_id': None}, synchronize_session=False)
    SecurityEvent.query.filter_by(resolved_by_user_id=uid).update({'resolved_by_user_id': None}, synchronize_session=False)
    CountryAccessRequest.query.filter_by(processed_by_user_id=uid).update({'processed_by_user_id': None}, synchronize_session=False)
    APIKey.query.filter_by(created_by_user_id=uid).update({'created_by_user_id': None}, synchronize_session=False)
    SystemSettings.query.filter_by(updated_by_user_id=uid).update({'updated_by_user_id': None}, synchronize_session=False)
    IndicatorSuggestion.query.filter_by(reviewed_by_user_id=uid).update({'reviewed_by_user_id': None}, synchronize_session=False)
    CommonWord.query.filter_by(created_by_user_id=uid).update({'created_by_user_id': None}, synchronize_session=False)

    # 4) Nullify optional creator/owner pointers on forms
    FormTemplate.query.filter_by(created_by=uid).update({'created_by': None}, synchronize_session=False)
    FormTemplate.query.filter_by(owned_by=uid).update({'owned_by': None}, synchronize_session=False)
    FormTemplateVersion.query.filter_by(created_by=uid).update({'created_by': None}, synchronize_session=False)
    FormTemplateVersion.query.filter_by(updated_by=uid).update({'updated_by': None}, synchronize_session=False)

    # 5) Commit intermediate cleanup before deleting the user
    db.session.flush()

    # 6) Finally delete the user
    db.session.delete(user)
    db.session.flush()
