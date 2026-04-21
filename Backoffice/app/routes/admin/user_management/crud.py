"""HTML / form-based user CRUD routes and access-request management."""

from app.utils.transactions import request_transaction_rollback
from app.utils.datetime_helpers import utcnow
from collections import defaultdict
import re

from flask import render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user

from app import db
from app.models import User, Country, UserEntityPermission, CountryAccessRequest
from app.models.enums import EntityType
from app.forms.system import UserForm
from app.routes.admin.shared import permission_required
from app.utils.form_localization import get_localized_country_name
from app.services.user_analytics_service import log_admin_action
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_responses import json_bad_request, json_forbidden, json_ok
from app.utils.error_handling import handle_json_view_exception
from app.utils.entity_groups import get_enabled_entity_groups
from app.utils.profile_utils import PROFILE_COLORS
from app.models.system import UserDevice

from . import bp
from .helpers import (
    _apply_role_type_and_implications,
    _get_allowed_non_country_entity_types,
    _is_azure_sso_enabled,
    _compute_role_type_for_user_id,
    _filter_requested_admin_roles_for_actor,
    _filter_role_choices_for_actor,
    _get_countries_by_region,
    _set_user_rbac_roles,
    _ensure_user_has_default_rbac_role,
    _get_user_deletion_preview,
    _cascade_delete_user_related,
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
    from app.services.app_settings_service import get_auto_approve_access_requests
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
            from app.services.notification.core import notify_user_added_to_country
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
                from app.services.notification.core import notify_user_added_to_country
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
                    pc = (form.profile_color.data or "").strip() if getattr(form, "profile_color", None) else ""
                    new_user.profile_color = pc if pc else "#3B82F6"
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
                            'profile_color': new_user.profile_color,
                            'country_ids': assigned_country_ids or [],
                            'entity_permissions': entity_permissions
                        },
                        risk_level='medium'
                    )

                    db.session.flush()

                    # Send welcome email
                    try:
                        from app.services.email.service import send_welcome_email
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
                           azure_sso_enabled=azure_sso_enabled,
                           profile_palette_hexes=PROFILE_COLORS)

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
                                   azure_sso_enabled=azure_sso_enabled,
                                   profile_palette_hexes=PROFILE_COLORS)
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
                                   azure_sso_enabled=azure_sso_enabled,
                                   profile_palette_hexes=PROFILE_COLORS)

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
                                   azure_sso_enabled=azure_sso_enabled,
                                   profile_palette_hexes=PROFILE_COLORS)

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
            'profile_color': user.profile_color,
            'rbac_role_ids': old_rbac_role_ids,
            'country_ids': [c.id for c in user.countries.all()] if hasattr(user, "countries") else []
        }

        # Update user details
        user.email = form.email.data
        user.name = form.name.data
        user.title = form.title.data
        _pc_raw = getattr(form, "profile_color", None) and form.profile_color.data
        user.profile_color = _pc_raw.strip() if _pc_raw else "#3B82F6"

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
        from app.services.notification.service import NotificationService
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
            'profile_color': user.profile_color,
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
        pc = (user.profile_color or "#3B82F6").strip()
        if not re.match(r"^#[0-9A-Fa-f]{6}$", pc):
            pc = "#3B82F6"
        form.profile_color.data = pc
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
    from app.services.notification.service import NotificationService
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

    computed_role_type = _compute_role_type_for_user_id(user.id)

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
                           computed_role_type=computed_role_type,
                           profile_palette_hexes=PROFILE_COLORS)


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

        log_admin_action(
            action_type='kickout_device',
            description=f"Ended session for device {device_id} (user {user_id})",
            target_type='user',
            target_id=user_id,
            target_description=user.email if user else None,
            new_values={
                'device_id': device_id,
                'platform': device.platform,
                'device_name': device.device_name,
                'device_token_preview': device.device_token[:15] + '...' if device.device_token else None,
            },
            risk_level='medium',
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

        log_admin_action(
            action_type='remove_device',
            description=f"Removed device {device_id} from user {user_id}",
            target_type='user',
            target_id=user_id,
            target_description=user.email if user else None,
            new_values=device_info,
            risk_level='medium',
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
