# Backoffice/app/routes/api/mobile/admin_users.py
"""Admin user management routes: list, detail, update, activate/deactivate, RBAC roles."""

import re

from flask import request, current_app
from flask_login import current_user

from app import db
from app.utils.api_helpers import get_json_safe
from app.utils.api_pagination import validate_pagination_params
from app.utils.mobile_auth import mobile_auth_required
from app.utils.mobile_responses import (
    mobile_ok,
    mobile_bad_request,
    mobile_not_found,
    mobile_server_error,
    mobile_paginated,
    mobile_forbidden,
)
from app.utils.sql_utils import safe_ilike_pattern
from app.routes.api.mobile import mobile_bp


@mobile_bp.route('/admin/users', methods=['GET'])
@mobile_auth_required(permission='admin.users.view')
def list_users():
    """Paginated user list (admin). Payload matches GET /admin/api/users rows."""
    from app.models import User
    from app.routes.admin.user_management.helpers import build_admin_user_list_rows

    page, per_page = validate_pagination_params(request.args, default_per_page=50, max_per_page=200)
    search = request.args.get('search', '').strip()

    query = User.query
    if search:
        pattern = safe_ilike_pattern(search)
        query = query.filter(
            db.or_(User.email.ilike(pattern), User.name.ilike(pattern))
        )
    query = query.order_by(User.name.asc().nullslast(), User.email.asc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    users = build_admin_user_list_rows(paginated.items)

    return mobile_paginated(
        items=users,
        total=paginated.total,
        page=paginated.page,
        per_page=paginated.per_page,
    )


@mobile_bp.route('/admin/users/<int:user_id>', methods=['GET'])
@mobile_auth_required(permission='admin.users.view')
def get_user(user_id):
    """User detail (admin). Same fields as GET /admin/api/users/<id>."""
    from app.routes.admin.user_management.helpers import build_admin_user_detail_dict

    payload = build_admin_user_detail_dict(user_id)
    if not payload:
        return mobile_not_found('User not found')

    return mobile_ok(data={
        'user': payload,
    })


@mobile_bp.route('/admin/users/<int:user_id>', methods=['PUT', 'PATCH'])
@mobile_auth_required(permission='admin.users.edit')
def update_user(user_id):
    """Update user profile fields and/or RBAC roles (admin). Mirrors /admin/api/users/<id> JSON PATCH."""
    from app.models import User
    from app.models.rbac import RbacRole, RbacUserRole
    from app.services.authorization_service import AuthorizationService
    from app.services.user_analytics_service import log_admin_action
    from app.routes.admin.user_management.helpers import (
        _set_user_rbac_roles,
        _filter_requested_admin_roles_for_actor,
    )

    user = User.query.get(user_id)
    if not user:
        return mobile_not_found('User not found')

    data = get_json_safe()
    if not isinstance(data, dict):
        return mobile_bad_request('Expected JSON body')

    allowed = {'name', 'title', 'active', 'chatbot_enabled', 'profile_color', 'rbac_role_ids'}
    if not allowed.intersection(data.keys()):
        return mobile_bad_request('No updatable fields in request')

    current_is_sys_mgr = AuthorizationService.is_system_manager(current_user)
    editing_self = bool(current_user.id == user.id)
    target_is_admin = bool(AuthorizationService.is_admin(user))
    user_is_sys_mgr = bool(AuthorizationService.is_system_manager(user))

    if (not current_is_sys_mgr) and (not editing_self) and target_is_admin:
        return mobile_forbidden('Only a System Manager can modify an admin user.')

    if user_is_sys_mgr and not current_is_sys_mgr:
        return mobile_forbidden('Only a System Manager can modify a System Manager user.')

    try:
        old_rbac_role_ids = [ur.role_id for ur in RbacUserRole.query.filter_by(user_id=user.id).all()]
    except Exception as e:
        current_app.logger.debug('old_rbac_role_ids query failed: %s', e)
        old_rbac_role_ids = []

    old_values = {
        'name': user.name,
        'title': user.title,
        'active': user.active,
        'chatbot_enabled': user.chatbot_enabled,
        'profile_color': user.profile_color,
        'rbac_role_ids': old_rbac_role_ids,
    }

    if 'name' in data:
        raw = data.get('name')
        if raw is None:
            user.name = None
        else:
            name = str(raw).strip()
            if len(name) > 100:
                return mobile_bad_request('Name must be 100 characters or less')
            user.name = name if name else None

    if 'title' in data:
        raw = data.get('title')
        if raw is None or (isinstance(raw, str) and not str(raw).strip()):
            user.title = None
        else:
            t = str(raw).strip()
            if len(t) > 100:
                return mobile_bad_request('Title must be 100 characters or less')
            user.title = t

    if 'chatbot_enabled' in data:
        user.chatbot_enabled = bool(data.get('chatbot_enabled'))

    if 'profile_color' in data:
        raw_pc = data.get('profile_color')
        if raw_pc is None:
            pass
        else:
            pc = str(raw_pc).strip()
            if not pc:
                return mobile_bad_request('profile_color cannot be empty')
            if not re.match(r'^#[0-9A-Fa-f]{6}$', pc):
                return mobile_bad_request('profile_color must be a #RRGGBB hex value')
            user.profile_color = pc

    if 'active' in data:
        new_active = bool(data.get('active'))
        if not new_active and user.id == current_user.id:
            return mobile_bad_request('You cannot deactivate your own account')
        user.active = new_active
        if new_active:
            user.deactivated_at = None
        else:
            user.deactivated_at = db.func.now()

    if 'rbac_role_ids' in data:
        if not AuthorizationService.has_rbac_permission(current_user, 'admin.users.roles.assign'):
            return mobile_forbidden('You do not have permission to assign roles.')
        roles_read_only = bool(editing_self and not current_is_sys_mgr)
        if roles_read_only:
            return mobile_bad_request('You cannot change your own roles.')

        raw_ids = data.get('rbac_role_ids')
        if not isinstance(raw_ids, list):
            return mobile_bad_request('rbac_role_ids must be a list')
        requested_role_ids = []
        for x in raw_ids:
            try:
                requested_role_ids.append(int(x))
            except Exception:
                return mobile_bad_request('Invalid role id in rbac_role_ids')

        sys_role = RbacRole.query.filter_by(code='system_manager').first()
        plugins_role = RbacRole.query.filter_by(code='admin_plugins_manager').first()

        restricted_role_ids = set()
        try:
            restricted_codes = ['system_manager', 'admin_full', 'admin_plugins_manager']
            rows = RbacRole.query.filter(RbacRole.code.in_(restricted_codes)).with_entities(RbacRole.id).all()
            restricted_role_ids = {int(r[0]) for r in rows if r and r[0] is not None}
        except Exception as e:
            current_app.logger.debug('restricted_role_ids query failed: %s', e)

        if not current_is_sys_mgr and restricted_role_ids:
            requested_role_ids = [rid for rid in requested_role_ids if int(rid) not in restricted_role_ids]

        if sys_role and (sys_role.id in requested_role_ids) and not current_is_sys_mgr:
            return mobile_bad_request('Only a System Manager can assign the System Manager role.')

        if plugins_role and (plugins_role.id in requested_role_ids) and not current_is_sys_mgr:
            return mobile_bad_request('Only a System Manager can assign the Plugins role.')

        if not current_is_sys_mgr:
            requested_role_ids, _dropped = _filter_requested_admin_roles_for_actor(requested_role_ids, current_user)

        if not requested_role_ids:
            return mobile_bad_request('rbac_role_ids must include at least one role')

        _set_user_rbac_roles(user, requested_role_ids)

    try:
        db.session.flush()

        try:
            new_rbac_role_ids = [ur.role_id for ur in RbacUserRole.query.filter_by(user_id=user.id).all()]
        except Exception as e:
            current_app.logger.debug('new_rbac_role_ids query failed: %s', e)
            new_rbac_role_ids = old_rbac_role_ids

        new_values = {
            'name': user.name,
            'title': user.title,
            'active': user.active,
            'chatbot_enabled': user.chatbot_enabled,
            'profile_color': user.profile_color,
            'rbac_role_ids': new_rbac_role_ids,
        }

        risk_level = 'low'
        if old_values.get('active') != new_values.get('active'):
            risk_level = 'medium'
        if set(old_values.get('rbac_role_ids') or []) != set(new_values.get('rbac_role_ids') or []):
            risk_level = 'medium'

        log_admin_action(
            action_type='user_update',
            description=f'Updated user (mobile API): {user.email}',
            target_type='user',
            target_id=user.id,
            target_description=f'{user.name or user.email}',
            old_values=old_values,
            new_values=new_values,
            risk_level=risk_level,
        )
        db.session.flush()
        return mobile_ok(message='User updated')
    except Exception as e:
        current_app.logger.error('update_user: %s', e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()


@mobile_bp.route('/admin/users/<int:user_id>/activate', methods=['POST'])
@mobile_auth_required(permission='admin.users.deactivate')
def activate_user(user_id):
    """Activate a user account (admin)."""
    from app.models import User
    from app.services.authorization_service import AuthorizationService

    user = User.query.get(user_id)
    if not user:
        return mobile_not_found('User not found')
    if user.id == current_user.id:
        return mobile_bad_request('You cannot activate your own account')
    if not AuthorizationService.is_system_manager(current_user) and AuthorizationService.is_admin(user):
        return mobile_bad_request('Only a System Manager can modify an admin user')

    user.active = True
    user.deactivated_at = None
    try:
        db.session.flush()
        return mobile_ok(message='User activated')
    except Exception as e:
        current_app.logger.error('activate_user: %s', e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()


@mobile_bp.route('/admin/users/<int:user_id>/deactivate', methods=['POST'])
@mobile_auth_required(permission='admin.users.deactivate')
def deactivate_user(user_id):
    """Deactivate a user account (admin)."""
    from app.models import User
    from app.services.authorization_service import AuthorizationService

    user = User.query.get(user_id)
    if not user:
        return mobile_not_found('User not found')
    if user.id == current_user.id:
        return mobile_bad_request('You cannot deactivate your own account')
    if not AuthorizationService.is_system_manager(current_user) and AuthorizationService.is_admin(user):
        return mobile_bad_request('Only a System Manager can modify an admin user')

    user.active = False
    user.deactivated_at = db.func.now()
    try:
        db.session.flush()
        return mobile_ok(message='User deactivated')
    except Exception as e:
        current_app.logger.error('deactivate_user: %s', e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()


@mobile_bp.route('/admin/users/rbac-roles', methods=['GET'])
@mobile_auth_required(permission='admin.users.view')
def list_rbac_roles():
    """List available RBAC roles."""
    from app.models.rbac import RbacRole
    roles = RbacRole.query.order_by(RbacRole.name.asc()).all()
    return mobile_ok(data={
        'roles': [
            {'id': r.id, 'code': r.code, 'name': r.name, 'description': r.description}
            for r in roles
        ],
    })
