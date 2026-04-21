# File: Backoffice/app/routes/admin/rbac_management.py
"""
RBAC Management Module - Manage Roles, Permissions, and Access Grants
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user
from app import db
from app.models.rbac import (
    RbacPermission, RbacRole, RbacRolePermission, RbacUserRole, RbacAccessGrant
)
from app.models import User, FormTemplate, AssignedForm
from app.routes.admin.shared import admin_required, admin_permission_required, system_manager_required
from app.services.user_analytics_service import log_admin_action
from app.utils.transactions import request_transaction_rollback
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.error_handling import handle_json_view_exception
from app.utils.api_responses import json_ok, json_server_error
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, desc

# RBAC management pages are part of user management, so keep them under /admin/users/*
#
# Canonical URLs:
# - /admin/users/roles/
# - /admin/users/permissions
# - /admin/users/grants
#
# Backwards compatible redirects/aliases are provided for legacy /admin/users/rbac/* paths.
bp = Blueprint("rbac_management", __name__, url_prefix="/admin/users")


# ============================================================================
# ROLES MANAGEMENT
# ============================================================================

@bp.route("/roles", methods=["GET"])
@bp.route("/roles/", methods=["GET"])
@admin_permission_required('admin.users.roles.assign')
@system_manager_required
def manage_roles():
    """List all RBAC roles"""
    try:
        roles = RbacRole.query.order_by(RbacRole.name).all()

        # Get user counts for each role
        role_user_counts = {}
        user_role_counts = (
            db.session.query(
                RbacUserRole.role_id,
                func.count(RbacUserRole.user_id).label('count')
            )
            .group_by(RbacUserRole.role_id)
            .all()
        )
        for role_id, count in user_role_counts:
            role_user_counts[role_id] = count

        # Get permission counts for each role
        role_perm_counts = {}
        role_permission_counts = (
            db.session.query(
                RbacRolePermission.role_id,
                func.count(RbacRolePermission.permission_id).label('count')
            )
            .group_by(RbacRolePermission.role_id)
            .all()
        )
        for role_id, count in role_permission_counts:
            role_perm_counts[role_id] = count

        return render_template(
            "admin/rbac/roles.html",
            roles=roles,
            role_user_counts=role_user_counts,
            role_perm_counts=role_perm_counts,
            title="Manage Roles"
        )
    except Exception as e:
        current_app.logger.error(f"Error loading roles: {e}", exc_info=True)
        flash("Error loading roles.", "danger")
        return redirect(url_for("admin.admin_dashboard"))


@bp.route("/roles/new", methods=["GET", "POST"])
@admin_permission_required('admin.users.roles.assign')
@system_manager_required
def new_role():
    """Create a new RBAC role"""
    if request.method == "POST":
        try:
            code = request.form.get('code', '').strip()
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            permission_ids = request.form.getlist('permissions')

            if not code or not name:
                flash("Role code and name are required.", "warning")
                return redirect(url_for("rbac_management.new_role"))

            # Check if code already exists
            existing = RbacRole.query.filter_by(code=code).first()
            if existing:
                flash(f"Role with code '{code}' already exists.", "warning")
                return redirect(url_for("rbac_management.new_role"))

            # Create role
            role = RbacRole(
                code=code,
                name=name,
                description=description
            )
            db.session.add(role)
            db.session.flush()

            # Assign permissions
            for perm_id in permission_ids:
                try:
                    perm_id_int = int(perm_id)
                    role_perm = RbacRolePermission(
                        role_id=role.id,
                        permission_id=perm_id_int
                    )
                    db.session.add(role_perm)
                except ValueError:
                    continue

            db.session.flush()

            log_admin_action(
                action_type='rbac_role_create',
                description=f"Created RBAC role: {role.name} ({role.code})",
                target_type='rbac_role',
                target_id=role.id,
                new_values={'code': role.code, 'name': role.name, 'permission_count': len(permission_ids)},
                risk_level='medium'
            )

            flash(f"Role '{role.name}' created successfully.", "success")
            return redirect(url_for("rbac_management.manage_roles"))

        except Exception as e:
            request_transaction_rollback()
            current_app.logger.error(f"Error creating role: {e}", exc_info=True)
            flash("Error creating role.", "danger")

    # GET - show form
    permissions = RbacPermission.query.order_by(RbacPermission.code).all()

    # Group permissions by module (split on first '.')
    permissions_by_module = {}
    for perm in permissions:
        module = perm.code.split('.')[0] if '.' in perm.code else 'other'
        if module not in permissions_by_module:
            permissions_by_module[module] = []
        permissions_by_module[module].append(perm)

    return render_template(
        "admin/rbac/role_form.html",
        role=None,
        permissions_by_module=permissions_by_module,
        title="Create New Role"
    )


@bp.route("/roles/<int:role_id>/edit", methods=["GET", "POST"])
@admin_permission_required('admin.users.roles.assign')
@system_manager_required
def edit_role(role_id):
    """Edit an existing RBAC role"""
    role = RbacRole.query.get_or_404(role_id)

    if request.method == "POST":
        try:
            old_name = role.name
            role.name = request.form.get('name', '').strip()
            role.description = request.form.get('description', '').strip()
            permission_ids = request.form.getlist('permissions')

            if not role.name:
                flash("Role name is required.", "warning")
                return redirect(url_for("rbac_management.edit_role", role_id=role_id))

            # Update permissions
            RbacRolePermission.query.filter_by(role_id=role.id).delete()
            for perm_id in permission_ids:
                try:
                    perm_id_int = int(perm_id)
                    role_perm = RbacRolePermission(
                        role_id=role.id,
                        permission_id=perm_id_int
                    )
                    db.session.add(role_perm)
                except ValueError:
                    continue

            db.session.flush()

            log_admin_action(
                action_type='rbac_role_update',
                description=f"Updated RBAC role: {role.name} ({role.code})",
                target_type='rbac_role',
                target_id=role.id,
                old_values={'name': old_name},
                new_values={'name': role.name, 'permission_count': len(permission_ids)},
                risk_level='medium'
            )

            flash(f"Role '{role.name}' updated successfully.", "success")
            return redirect(url_for("rbac_management.manage_roles"))

        except Exception as e:
            request_transaction_rollback()
            current_app.logger.error(f"Error updating role: {e}", exc_info=True)
            flash("An error occurred. Please try again.", "danger")

    # GET - show form
    permissions = RbacPermission.query.order_by(RbacPermission.code).all()

    # Group permissions by module
    permissions_by_module = {}
    for perm in permissions:
        module = perm.code.split('.')[0] if '.' in perm.code else 'other'
        if module not in permissions_by_module:
            permissions_by_module[module] = []
        permissions_by_module[module].append(perm)

    # Get current role permissions
    current_permission_ids = [
        rp.permission_id for rp in RbacRolePermission.query.filter_by(role_id=role.id).all()
    ]

    return render_template(
        "admin/rbac/role_form.html",
        role=role,
        current_permission_ids=current_permission_ids,
        permissions_by_module=permissions_by_module,
        title=f"Edit Role: {role.name}"
    )


@bp.route("/roles/<int:role_id>/delete", methods=["POST"])
@admin_permission_required('admin.users.roles.assign')
@system_manager_required
def delete_role(role_id):
    """Delete an RBAC role"""
    role = RbacRole.query.get_or_404(role_id)

    try:
        # Check if role has users
        user_count = RbacUserRole.query.filter_by(role_id=role.id).count()
        if user_count > 0:
            flash(f"Cannot delete role '{role.name}' - it is assigned to {user_count} user(s). Remove all users first.", "warning")
            return redirect(url_for("rbac_management.manage_roles"))

        role_name = role.name
        role_code = role.code

        # Delete role permissions first
        RbacRolePermission.query.filter_by(role_id=role.id).delete()

        # Delete role
        db.session.delete(role)
        db.session.flush()

        log_admin_action(
            action_type='rbac_role_delete',
            description=f"Deleted RBAC role: {role_name} ({role_code})",
            target_type='rbac_role',
            target_id=role_id,
            old_values={'code': role_code, 'name': role_name},
            risk_level='high'
        )

        flash(f"Role '{role_name}' deleted successfully.", "success")

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error deleting role: {e}", exc_info=True)
        flash("Error deleting role.", "danger")

    return redirect(url_for("rbac_management.manage_roles"))


# ============================================================================
# PERMISSIONS REFERENCE
# ============================================================================

@bp.route("/permissions", methods=["GET"])
@admin_permission_required('admin.users.roles.assign')
@system_manager_required
def list_permissions():
    """List all available permissions"""
    try:
        permissions = RbacPermission.query.order_by(RbacPermission.code).all()

        # Group by module
        permissions_by_module = {}
        for perm in permissions:
            module = perm.code.split('.')[0] if '.' in perm.code else 'other'
            if module not in permissions_by_module:
                permissions_by_module[module] = []
            permissions_by_module[module].append(perm)

        return render_template(
            "admin/rbac/permissions.html",
            permissions_by_module=permissions_by_module,
            title="Permissions Reference"
        )
    except Exception as e:
        current_app.logger.error(f"Error loading permissions: {e}", exc_info=True)
        flash("Error loading permissions.", "danger")
        return redirect(url_for("admin.admin_dashboard"))


# ============================================================================
# ACCESS GRANTS MANAGEMENT
# ============================================================================

@bp.route("/grants", methods=["GET"])
@admin_required
@system_manager_required
def manage_grants():
    """List all access grants"""
    try:
        grants = RbacAccessGrant.query.order_by(desc(RbacAccessGrant.created_at)).all()

        # Preload related data
        user_ids = [g.principal_id for g in grants if g.principal_type == 'user']
        role_ids = [g.principal_id for g in grants if g.principal_type == 'role']
        perm_ids = [g.permission_id for g in grants]
        template_ids = [g.template_id for g in grants if g.template_id]
        assigned_form_ids = [g.assigned_form_id for g in grants if g.assigned_form_id]

        users_by_id = {u.id: u for u in User.query.filter(User.id.in_(user_ids)).all()} if user_ids else {}
        roles_by_id = {r.id: r for r in RbacRole.query.filter(RbacRole.id.in_(role_ids)).all()} if role_ids else {}
        perms_by_id = {p.id: p for p in RbacPermission.query.filter(RbacPermission.id.in_(perm_ids)).all()} if perm_ids else {}
        templates_by_id = {t.id: t for t in FormTemplate.query.filter(FormTemplate.id.in_(template_ids)).all()} if template_ids else {}
        assignments_by_id = {a.id: a for a in AssignedForm.query.filter(AssignedForm.id.in_(assigned_form_ids)).all()} if assigned_form_ids else {}

        return render_template(
            "admin/rbac/grants.html",
            grants=grants,
            users_by_id=users_by_id,
            roles_by_id=roles_by_id,
            perms_by_id=perms_by_id,
            templates_by_id=templates_by_id,
            assignments_by_id=assignments_by_id,
            title="Manage Access Grants"
        )
    except Exception as e:
        current_app.logger.error(f"Error loading grants: {e}", exc_info=True)
        flash("Error loading grants.", "danger")
        return redirect(url_for("admin.admin_dashboard"))


@bp.route("/grants/new", methods=["GET", "POST"])
@admin_required
@system_manager_required
def new_grant():
    """Create a new access grant"""
    if request.method == "POST":
        try:
            principal_type = request.form.get('principal_type')  # 'user' or 'role'
            principal_id = request.form.get('principal_id', type=int)
            permission_id = request.form.get('permission_id', type=int)
            effect = request.form.get('effect', 'allow')  # 'allow' or 'deny'
            scope_kind = request.form.get('scope_kind', 'global')  # 'global', 'entity', 'template', 'assignment'

            # Scope parameters
            entity_type = request.form.get('entity_type')
            entity_id = request.form.get('entity_id', type=int)
            template_id = request.form.get('template_id', type=int)
            assigned_form_id = request.form.get('assigned_form_id', type=int)

            # Validate required fields
            principal_type = (principal_type or "").strip().lower()
            effect = (effect or "allow").strip().lower()
            scope_kind = (scope_kind or "global").strip().lower()
            entity_type = (entity_type or "").strip()

            if principal_type not in ("user", "role"):
                flash("Principal type must be 'user' or 'role'.", "warning")
                return redirect(url_for("rbac_management.new_grant"))
            if not principal_id or not permission_id:
                flash("Principal and permission are required.", "warning")
                return redirect(url_for("rbac_management.new_grant"))
            if effect not in ("allow", "deny"):
                flash("Effect must be 'allow' or 'deny'.", "warning")
                return redirect(url_for("rbac_management.new_grant"))
            if scope_kind not in ("global", "entity", "template", "assignment"):
                flash("Scope must be one of: global, entity, template, assignment.", "warning")
                return redirect(url_for("rbac_management.new_grant"))

            # Validate principal exists
            if principal_type == "user":
                if not User.query.get(int(principal_id)):
                    flash("Selected user does not exist.", "warning")
                    return redirect(url_for("rbac_management.new_grant"))
            else:
                if not RbacRole.query.get(int(principal_id)):
                    flash("Selected role does not exist.", "warning")
                    return redirect(url_for("rbac_management.new_grant"))

            # Validate permission exists
            if not RbacPermission.query.get(int(permission_id)):
                flash("Selected permission does not exist.", "warning")
                return redirect(url_for("rbac_management.new_grant"))

            # Validate scope payload and referenced objects
            if scope_kind == "global":
                entity_type = None
                entity_id = None
                template_id = None
                assigned_form_id = None
            elif scope_kind == "entity":
                if not entity_type or entity_id is None:
                    flash("Entity scope requires entity type and entity id.", "warning")
                    return redirect(url_for("rbac_management.new_grant"))
                # Defensive bounds (db column is String(50))
                if len(entity_type) > 50:
                    flash("Entity type is too long.", "warning")
                    return redirect(url_for("rbac_management.new_grant"))
                template_id = None
                assigned_form_id = None
            elif scope_kind == "template":
                if not template_id:
                    flash("Template scope requires a template id.", "warning")
                    return redirect(url_for("rbac_management.new_grant"))
                if not FormTemplate.query.get(int(template_id)):
                    flash("Selected template does not exist.", "warning")
                    return redirect(url_for("rbac_management.new_grant"))
                entity_type = None
                entity_id = None
                assigned_form_id = None
            else:  # assignment
                if not assigned_form_id:
                    flash("Assignment scope requires an assignment id.", "warning")
                    return redirect(url_for("rbac_management.new_grant"))
                if not AssignedForm.query.get(int(assigned_form_id)):
                    flash("Selected assignment does not exist.", "warning")
                    return redirect(url_for("rbac_management.new_grant"))
                entity_type = None
                entity_id = None
                template_id = None

            # Create grant
            grant = RbacAccessGrant(
                principal_type=principal_type,
                principal_id=principal_id,
                permission_id=permission_id,
                effect=effect,
                scope_kind=scope_kind,
                entity_type=entity_type if scope_kind == 'entity' else None,
                entity_id=entity_id if scope_kind == 'entity' else None,
                template_id=template_id if scope_kind == 'template' else None,
                assigned_form_id=assigned_form_id if scope_kind == 'assignment' else None
            )
            db.session.add(grant)
            db.session.flush()

            log_admin_action(
                action_type='rbac_grant_create',
                description=f"Created access grant: {effect} {permission_id} for {principal_type} {principal_id}",
                target_type='rbac_grant',
                target_id=grant.id,
                new_values={
                    'principal': f"{principal_type}:{principal_id}",
                    'permission_id': permission_id,
                    'effect': effect,
                    'scope_kind': scope_kind
                },
                risk_level='medium'
            )

            flash("Access grant created successfully.", "success")
            return redirect(url_for("rbac_management.manage_grants"))

        except IntegrityError as e:
            request_transaction_rollback()
            current_app.logger.warning(f"RBAC grant integrity error: {e}")
            flash(
                "Could not create access grant. A conflicting or duplicate grant already exists "
                "for the same principal, permission, and scope.",
                "warning",
            )
        except Exception as e:
            request_transaction_rollback()
            current_app.logger.error(f"Error creating grant: {e}", exc_info=True)
            flash("An error occurred. Please try again.", "danger")

    # GET - show form
    permissions = RbacPermission.query.order_by(RbacPermission.code).all()
    roles = RbacRole.query.order_by(RbacRole.name).all()
    users = User.query.filter_by(active=True).order_by(User.name, User.email).all()

    return render_template(
        "admin/rbac/grant_form.html",
        grant=None,
        permissions=permissions,
        roles=roles,
        users=users,
        title="Create Access Grant"
    )


@bp.route("/grants/<int:grant_id>/delete", methods=["POST"])
@admin_required
@system_manager_required
def delete_grant(grant_id):
    """Delete an access grant"""
    grant = RbacAccessGrant.query.get_or_404(grant_id)

    try:
        grant_info = {
            'principal': f"{grant.principal_type}:{grant.principal_id}",
            'permission_id': grant.permission_id,
            'effect': grant.effect,
            'scope_kind': grant.scope_kind
        }

        db.session.delete(grant)
        db.session.flush()

        log_admin_action(
            action_type='rbac_grant_delete',
            description=f"Deleted access grant: {grant.effect} for {grant.principal_type} {grant.principal_id}",
            target_type='rbac_grant',
            target_id=grant_id,
            old_values=grant_info,
            risk_level='medium'
        )

        flash("Access grant deleted successfully.", "success")

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error deleting grant: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")

    return redirect(url_for("rbac_management.manage_grants"))


# ============================================================================
# API ENDPOINTS (for AJAX/mobile)
# ============================================================================

@bp.route("/api/roles", methods=["GET"])
@admin_permission_required('admin.users.roles.assign')
@system_manager_required
def api_list_roles():
    """API: List all roles"""
    try:
        roles = RbacRole.query.order_by(RbacRole.name).all()
        return json_ok(
            success=True,
            roles=[
                {
                    'id': r.id,
                    'code': r.code,
                    'name': r.name,
                    'description': r.description
                }
                for r in roles
            ]
        )
    except Exception as e:
        current_app.logger.error(f"Error fetching roles: {e}", exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)


@bp.route("/api/permissions", methods=["GET"])
@admin_permission_required('admin.users.roles.assign')
@system_manager_required
def api_list_permissions():
    """API: List all permissions"""
    try:
        permissions = RbacPermission.query.order_by(RbacPermission.code).all()
        return json_ok(
            success=True,
            permissions=[
                {
                    'id': p.id,
                    'code': p.code,
                    'name': p.name,
                    'description': p.description
                }
                for p in permissions
            ]
        )
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/users/<int:user_id>/roles", methods=["GET"])
@admin_permission_required('admin.users.view')
def api_get_user_roles(user_id):
    """API: Get roles for a specific user"""
    try:
        user = User.query.get_or_404(user_id)
        user_roles = RbacUserRole.query.filter_by(user_id=user_id).all()
        role_ids = [ur.role_id for ur in user_roles]
        roles = RbacRole.query.filter(RbacRole.id.in_(role_ids)).all() if role_ids else []

        return json_ok(
            success=True,
            user={'id': user.id, 'email': user.email, 'name': user.name},
            roles=[
                {
                    'id': r.id,
                    'code': r.code,
                    'name': r.name,
                    'description': r.description
                }
                for r in roles
            ],
        )
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)
