# Backoffice/app/routes/api/mobile.py
"""
Dedicated mobile API surface -- ``/api/mobile/v1/``.

All endpoints use the ``@mobile_auth_required`` decorator which handles JWT
Bearer authentication, session fallback, and optional RBAC checks in one place.

This is the **only** mobile API surface.  Legacy session-based auth routes
(``/api/v1/auth/*``) have been removed.  The Flutter app should use JWT tokens
obtained via ``/auth/token`` for all authenticated requests.
"""

from contextlib import suppress

from flask import Blueprint, request, current_app, session
from flask_login import current_user, logout_user

from app import db
from app.utils.api_responses import (
    json_ok, json_bad_request, json_not_found, json_server_error,
    json_auth_required, json_forbidden, json_error,
    GENERIC_ERROR_MESSAGE,
)
from app.utils.api_helpers import get_json_safe
from app.utils.mobile_auth import mobile_auth_required
from app.extensions import csrf
from app.utils.rate_limiting import auth_rate_limit
from app.utils.sql_utils import safe_ilike_pattern
from app.utils.api_pagination import validate_pagination_params

mobile_bp = Blueprint('mobile_api', __name__, url_prefix='/api/mobile/v1')


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@mobile_bp.route('/auth/token', methods=['POST'])
@auth_rate_limit()
def issue_tokens():
    """
    Issue JWT access + refresh tokens for mobile clients.

    Accepts ``{email, password}`` and returns a token pair.  The mobile app
    can use ``Authorization: Bearer <access_token>`` on subsequent requests
    instead of session cookies.
    """
    import uuid as _uuid
    from app.utils.mobile_jwt import issue_token_pair
    from app.services.user_analytics_service import (
        log_login_attempt, start_user_session, log_user_activity,
    )
    from app.services import UserService
    from app.routes.auth import _is_account_locked_out

    data = get_json_safe()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return json_bad_request('Email and password are required.')

    if _is_account_locked_out(email):
        log_login_attempt(email, success=False, failure_reason='account_locked')
        return json_error('Too many failed login attempts. Please try again later.', 429)

    user = UserService.get_by_email(email)
    if not user or not user.check_password(password):
        log_login_attempt(email, success=False, failure_reason='wrong_password' if user else 'user_not_found')
        return json_auth_required('Invalid email or password.')

    if not user.is_active:
        log_login_attempt(email, success=False, failure_reason='account_disabled')
        return json_forbidden('Your account is deactivated. Please contact an administrator.')

    log_login_attempt(email, success=True, user=user)
    jwt_session_id = str(_uuid.uuid4())
    start_user_session(user, jwt_session_id)
    log_user_activity(
        activity_type='login',
        description=f'User {email} obtained mobile JWT tokens',
        context_data={'user_id': user.id, 'auth_method': 'jwt', 'jwt_session_id': jwt_session_id},
    )

    tokens = issue_token_pair(user.id, session_id=jwt_session_id)
    tokens['user'] = {
        'id': user.id,
        'email': user.email,
        'name': user.name,
        'title': user.title,
    }
    return json_ok(**tokens)


@mobile_bp.route('/auth/refresh', methods=['POST'])
def refresh_token():
    """
    Refresh an expired access token using a valid refresh token.

    Accepts ``{refresh_token}`` and returns a new full token pair
    (access + refresh).  Issuing a new refresh token on every refresh
    rolls the 30-day inactivity window forward so active users never
    need to re-login.

    If the session tied to the refresh token was ended by inactivity
    cleanup while the user was away, a new session is started
    automatically so the resumed activity appears as a distinct session
    in the session logs rather than updating the old ended row.
    """
    import uuid as _uuid
    from app.utils.mobile_jwt import decode_mobile_token, issue_token_pair
    from app.models import User, UserSessionLog

    data = get_json_safe()
    refresh = data.get('refresh_token', '')

    if not refresh:
        return json_bad_request('refresh_token is required')

    try:
        claims = decode_mobile_token(refresh, expected_type='refresh')
    except Exception:
        return json_auth_required('Invalid or expired refresh token.')

    # Honour admin force-logout blacklist on refresh as well.
    if claims.sid:
        from app.services.user_analytics_service import is_session_blacklisted
        if is_session_blacklisted(claims.sid):
            return json_auth_required('Session has been revoked.')

    user = User.query.get(claims.user_id)
    if not user or not user.is_active:
        return json_auth_required('User account not found or deactivated.')

    # If the session that was embedded in the old tokens is no longer active
    # (e.g. it was ended by the inactivity-cleanup job while the user was
    # away), start a fresh session so the resumed activity is recorded as a
    # new entry in session logs instead of updating the already-ended row.
    session_id = claims.sid
    if session_id:
        old_session = UserSessionLog.query.filter_by(session_id=session_id).first()
        if old_session is None or not old_session.is_active:
            from app.services.user_analytics_service import start_user_session, log_user_activity
            session_id = str(_uuid.uuid4())
            start_user_session(user, session_id)
            log_user_activity(
                activity_type='login',
                description=f'User {user.email} resumed mobile session after inactivity',
                context_data={
                    'user_id': user.id,
                    'auth_method': 'jwt_refresh',
                    'new_session_id': session_id,
                    'previous_session_id': claims.sid,
                },
            )

    tokens = issue_token_pair(user.id, session_id=session_id)
    return json_ok(**tokens)


@mobile_bp.route('/auth/exchange-session', methods=['POST'])
@csrf.exempt
@mobile_auth_required
def exchange_session_for_tokens():
    """
    Exchange a valid Flask session cookie for a JWT token pair.

    This is the bridge for Azure SSO users: after the WebView completes
    and the Flask session cookie is established, the mobile app calls this
    endpoint (with the cookie) to obtain JWT tokens for subsequent API calls.
    """
    import uuid as _uuid
    from app.utils.mobile_jwt import issue_token_pair
    from app.services.user_analytics_service import start_user_session, log_user_activity
    from flask import session as flask_session

    # Reuse any existing session_id from the Flask session, or create a new one.
    jwt_session_id = flask_session.get('session_id') or str(_uuid.uuid4())

    # Ensure a UserSessionLog row exists for JWT-issued sessions.
    if not flask_session.get('session_id'):
        start_user_session(current_user, jwt_session_id)
        log_user_activity(
            activity_type='login',
            description=f'User {current_user.email} exchanged session cookie for JWT tokens',
            context_data={'user_id': current_user.id, 'auth_method': 'jwt_exchange'},
        )

    tokens = issue_token_pair(current_user.id, session_id=jwt_session_id)
    tokens['user'] = {
        'id': current_user.id,
        'email': current_user.email,
        'name': current_user.name,
        'title': current_user.title,
    }
    return json_ok(**tokens)


@mobile_bp.route('/auth/session', methods=['GET'])
@mobile_auth_required
def session_check():
    """Lightweight session / JWT validity check -- returns the current user."""
    user = current_user
    return json_ok(user={
        'id': user.id,
        'email': user.email,
        'name': user.name,
        'title': user.title,
        'active': user.is_active,
    })


@mobile_bp.route('/auth/logout', methods=['POST'])
@mobile_auth_required
def mobile_logout():
    """
    Logout endpoint for mobile clients.

    For JWT-authenticated sessions, blacklists the session so outstanding
    tokens are rejected on subsequent requests.  For session-authenticated
    requests, clears the Flask session.
    """
    from flask import g
    from app.utils.datetime_helpers import utcnow
    from app.services.user_analytics_service import log_user_activity, log_logout

    session_start = session.get('session_start')
    session_duration = None
    with suppress(Exception):
        if session_start:
            from datetime import datetime
            start_dt = datetime.fromisoformat(session_start)
            session_duration = int((utcnow() - start_dt).total_seconds() / 60)

    log_user_activity(
        activity_type='logout',
        description=f'User {current_user.email} logged out via mobile API',
        context_data={
            'user_id': current_user.id,
            'session_duration_minutes': session_duration,
        },
    )
    log_logout(current_user, session_duration_minutes=session_duration)

    jwt_sid = getattr(g, '_mobile_jwt_sid', None)
    if jwt_sid:
        from app.services.user_analytics_service import add_session_to_blacklist
        add_session_to_blacklist(jwt_sid)

    logout_user()
    session.clear()
    return json_ok(message='Logged out successfully.')


@mobile_bp.route('/auth/change-password', methods=['POST'])
@mobile_auth_required
def mobile_change_password():
    """
    Change the current user's password.

    Accepts ``{current_password, new_password}`` as JSON.
    """
    data = get_json_safe()
    current_password = data.get('current_password') or ''
    new_password = data.get('new_password') or ''

    if not current_password or not new_password:
        return json_bad_request('current_password and new_password are required.')

    if not current_user.check_password(current_password):
        return json_auth_required('Current password is incorrect.')

    from app.utils.password_validator import validate_password_strength
    is_valid, errors = validate_password_strength(
        new_password,
        user_email=current_user.email,
        user_name=current_user.name,
    )
    if not is_valid:
        return json_bad_request('; '.join(errors))

    try:
        current_user.set_password(new_password)
        db.session.flush()

        from app.services.user_analytics_service import log_user_activity
        log_user_activity(
            activity_type='password_change',
            description=f'User {current_user.email} changed password via mobile API',
            context_data={'user_id': current_user.id},
        )
        return json_ok(message='Password changed successfully.', requires_reauth=True)
    except Exception as e:
        current_app.logger.error("Password change failed: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return json_server_error('Could not change password. Please try again.')


@mobile_bp.route('/auth/profile', methods=['GET'])
@mobile_auth_required
def mobile_profile():
    """Return the current user's profile data."""
    from app.services.authorization_service import AuthorizationService

    user = current_user
    role_codes = AuthorizationService.get_role_codes(user)
    # Flutter derives coarse navigation role (admin / system_manager / focal_point)
    # from this list when `role` is absent — see MobileApp user_profile_service.
    rbac_roles = [{'code': code} for code in role_codes if code]
    access = AuthorizationService.access_level(user)

    return json_ok(user={
        'id': user.id,
        'email': user.email,
        'name': user.name,
        'title': user.title,
        'chatbot_enabled': getattr(user, 'chatbot_enabled', False),
        'profile_color': getattr(user, 'profile_color', '#3B82F6'),
        'active': user.is_active,
        'rbac_roles': rbac_roles,
        # Explicit coarse role for clients that do not parse rbac_roles (matches Flutter _normalizeRole).
        'role': access,
    })


@mobile_bp.route('/auth/profile', methods=['PUT', 'PATCH'])
@mobile_auth_required
def mobile_update_profile():
    """
    Update the current user's profile.

    Accepts ``{name, title, chatbot_enabled, profile_color}`` as JSON.
    """
    data = get_json_safe()

    if 'name' in data:
        current_user.name = data['name'] or None
    if 'title' in data:
        current_user.title = data['title'] or None
    if 'chatbot_enabled' in data:
        current_user.chatbot_enabled = bool(data['chatbot_enabled'])
    if 'profile_color' in data:
        current_user.profile_color = data['profile_color'] or '#3B82F6'

    try:
        db.session.flush()

        from app.services.user_analytics_service import log_user_activity
        log_user_activity(
            activity_type='profile_update',
            description=f'User {current_user.email} updated profile via mobile API',
            context_data={'user_id': current_user.id, 'updated_fields': list(data.keys())},
        )
        return json_ok(message='Profile updated successfully.')
    except Exception as e:
        current_app.logger.error("Profile update failed: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return json_server_error('Could not update profile. Please try again.')


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@mobile_bp.route('/notifications', methods=['GET'])
@mobile_auth_required
def list_notifications():
    """List notifications for the current user."""
    from app.services.notification.service import NotificationService

    page, per_page = validate_pagination_params(request.args, default_per_page=20)
    unread_only = request.args.get('unread_only', 'false').lower() in ('1', 'true', 'yes')
    notification_type = request.args.get('type')

    result = NotificationService.get_notifications(
        user_id=current_user.id,
        page=page,
        per_page=per_page,
        unread_only=unread_only,
        notification_type=notification_type,
    )
    return json_ok(**result)


@mobile_bp.route('/notifications/count', methods=['GET'])
@mobile_auth_required
def notification_count():
    """Return unread notification count."""
    from app.services.notification.service import NotificationService
    count = NotificationService.get_unread_count(current_user.id)
    return json_ok(unread_count=count)


@mobile_bp.route('/notifications/mark-read', methods=['POST'])
@mobile_auth_required
def mark_notifications_read():
    """Mark notifications as read."""
    from app.services.notification.service import NotificationService
    data = get_json_safe()
    notification_ids = data.get('notification_ids')
    mark_all = data.get('mark_all', False)

    try:
        if mark_all:
            NotificationService.mark_all_as_read(current_user.id)
        elif notification_ids:
            NotificationService.mark_as_read(notification_ids, current_user.id)
        else:
            return json_bad_request('notification_ids or mark_all required')
        return json_ok(message='Notifications marked as read')
    except Exception as e:
        current_app.logger.error("mark_notifications_read: %s", e, exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)


@mobile_bp.route('/notifications/mark-unread', methods=['POST'])
@mobile_auth_required
def mark_notifications_unread():
    """Mark notifications as unread."""
    from app.services.notification.service import NotificationService
    data = get_json_safe()
    notification_ids = data.get('notification_ids', [])
    if not notification_ids:
        return json_bad_request('notification_ids required')

    try:
        NotificationService.mark_as_unread(notification_ids, current_user.id)
        return json_ok(message='Notifications marked as unread')
    except Exception as e:
        current_app.logger.error("mark_notifications_unread: %s", e, exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)


@mobile_bp.route('/notifications/preferences', methods=['GET'])
@mobile_auth_required
def get_notification_preferences():
    """Return current user's notification preferences."""
    from app.services.notification.service import NotificationService
    prefs = NotificationService.get_notification_preferences(current_user.id)
    return json_ok(preferences={
        'email_notifications': prefs.email_notifications,
        'notification_frequency': prefs.notification_frequency,
        'sound_enabled': prefs.sound_enabled,
        'push_notifications': prefs.push_notifications,
        'notification_types_enabled': prefs.notification_types_enabled or [],
        'push_notification_types_enabled': prefs.push_notification_types_enabled or [],
        'digest_day': prefs.digest_day,
        'digest_time': prefs.digest_time,
        'timezone': getattr(prefs, 'timezone', None),
    })


@mobile_bp.route('/notifications/preferences', methods=['POST'])
@mobile_auth_required
def update_notification_preferences():
    """Update notification preferences."""
    from app.services.notification.service import NotificationService
    data = get_json_safe()
    try:
        NotificationService.update_notification_preferences(
            user_id=current_user.id,
            email_notifications=data.get('email_notifications'),
            notification_types_enabled=data.get('notification_types_enabled'),
            notification_frequency=data.get('notification_frequency'),
            sound_enabled=data.get('sound_enabled'),
            push_notifications=data.get('push_notifications'),
            push_notification_types_enabled=data.get('push_notification_types_enabled'),
            digest_day=data.get('digest_day'),
            digest_time=data.get('digest_time'),
            timezone=data.get('timezone'),
        )
        return json_ok(message='Preferences updated')
    except Exception as e:
        current_app.logger.error("update_notification_preferences: %s", e, exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------

@mobile_bp.route('/devices/register', methods=['POST'])
@mobile_auth_required
def register_device():
    """Register a device for push notifications."""
    from app.services.notification.push import PushNotificationService
    data = get_json_safe()
    device_token = data.get('device_token')
    platform = data.get('platform')

    if not device_token:
        return json_bad_request('device_token is required')
    if not platform or platform not in ('ios', 'android'):
        return json_bad_request('platform must be "ios" or "android"')

    ip_address = (
        request.headers.getlist("X-Forwarded-For")[0].split(',')[0].strip()
        if request.headers.getlist("X-Forwarded-For")
        else request.remote_addr
    )

    result = PushNotificationService.register_device(
        user_id=current_user.id,
        device_token=device_token,
        platform=platform,
        app_version=data.get('app_version'),
        device_model=data.get('device_model'),
        device_name=data.get('device_name'),
        os_version=data.get('os_version'),
        ip_address=ip_address,
        timezone=data.get('timezone'),
    )
    if result.get('success'):
        return json_ok(**result)
    return json_bad_request(result.get('error', 'Registration failed'))


@mobile_bp.route('/devices/unregister', methods=['POST'])
@mobile_auth_required
def unregister_device():
    """Unregister a device for push notifications."""
    from app.services.notification.push import PushNotificationService
    data = get_json_safe()
    device_token = data.get('device_token')
    if not device_token:
        return json_bad_request('device_token is required')

    result = PushNotificationService.unregister_device(
        user_id=current_user.id, device_token=device_token
    )
    if result.get('success'):
        return json_ok(**result)
    return json_bad_request(result.get('error', 'Unregistration failed'))


@mobile_bp.route('/devices/heartbeat', methods=['POST'])
@mobile_auth_required
def device_heartbeat():
    """Lightweight heartbeat to update device last_active_at."""
    from app.services.notification.push import PushNotificationService
    from app.services.user_analytics_service import _update_session_activity_explicit
    from flask import session as flask_session, g

    data = get_json_safe()
    device_token = data.get('device_token') or request.headers.get('X-Device-Token')
    if not device_token:
        return json_bad_request('device_token is required')

    updated = PushNotificationService.update_device_activity(
        user_id=current_user.id, device_token=device_token
    )

    # Keep UserSessionLog.last_activity current so the 2-hour cleanup job does
    # not incorrectly mark active mobile sessions as timed out.
    session_id = flask_session.get('session_id') or getattr(g, '_mobile_jwt_sid', None)
    if session_id:
        _update_session_activity_explicit(session_id, 'heartbeat')

    return json_ok(updated=updated)


# ---------------------------------------------------------------------------
# Admin -- Users
# ---------------------------------------------------------------------------

@mobile_bp.route('/admin/users', methods=['GET'])
@mobile_auth_required(permission='admin.users.view')
def list_users():
    """List users (admin)."""
    from app.models import User
    from app.services.authorization_service import AuthorizationService

    page, per_page = validate_pagination_params(request.args, default_per_page=50, max_per_page=200)
    search = request.args.get('search', '').strip()

    query = User.query
    if search:
        pattern = safe_ilike_pattern(search)
        query = query.filter(
            db.or_(
                User.email.ilike(pattern),
                User.name.ilike(pattern),
            )
        )
    query = query.order_by(User.name.asc().nullslast(), User.email.asc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    users = []
    for u in paginated.items:
        users.append({
            'id': u.id,
            'email': u.email,
            'name': u.name,
            'title': u.title,
            'active': u.is_active,
            'is_admin': AuthorizationService.is_admin(u),
        })

    return json_ok(
        users=users,
        total=paginated.total,
        page=paginated.page,
        per_page=paginated.per_page,
        total_pages=paginated.pages,
    )


@mobile_bp.route('/admin/users/<int:user_id>', methods=['GET'])
@mobile_auth_required(permission='admin.users.view')
def get_user(user_id):
    """Get user detail (admin)."""
    from app.models import User
    from app.models.core import UserEntityPermission
    from app.services.authorization_service import AuthorizationService

    user = User.query.get_or_404(user_id)
    entity_perms = UserEntityPermission.query.filter_by(user_id=user_id).all()

    return json_ok(user={
        'id': user.id,
        'email': user.email,
        'name': user.name,
        'title': user.title,
        'active': user.is_active,
        'is_admin': AuthorizationService.is_admin(user),
        'entity_permissions': [
            {'entity_type': p.entity_type, 'entity_id': p.entity_id}
            for p in entity_perms
        ],
    })


@mobile_bp.route('/admin/users/<int:user_id>', methods=['PUT', 'PATCH'])
@mobile_auth_required(permission='admin.users.edit')
def update_user(user_id):
    """Update user profile fields and/or RBAC roles (admin)."""
    from app.models import User
    from app.services.authorization_service import AuthorizationService

    user = User.query.get(user_id)
    if not user:
        return json_not_found('User not found')

    data = get_json_safe()
    if 'name' in data:
        user.name = data['name'] or None
    if 'title' in data:
        user.title = data['title'] or None

    if 'rbac_role_ids' in data:
        from app.models.rbac import RbacRole, RbacUserRole
        if not AuthorizationService.is_system_manager(current_user):
            sm_role = RbacRole.query.filter_by(code='system_manager').first()
            if sm_role and sm_role.id in (data['rbac_role_ids'] or []):
                return json_bad_request('Only system managers can assign the system_manager role.')

        RbacUserRole.query.filter_by(user_id=user_id).delete()
        for role_id in (data['rbac_role_ids'] or []):
            role = RbacRole.query.get(role_id)
            if role:
                db.session.add(RbacUserRole(user_id=user_id, role_id=role_id))

    try:
        db.session.flush()
        return json_ok(message='User updated')
    except Exception as e:
        current_app.logger.error("update_user: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return json_server_error(GENERIC_ERROR_MESSAGE)


@mobile_bp.route('/admin/users/<int:user_id>/activate', methods=['POST'])
@mobile_auth_required(permission='admin.users.deactivate')
def activate_user(user_id):
    """Activate a user account (admin)."""
    from app.models import User
    from app.services.authorization_service import AuthorizationService

    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        return json_bad_request('You cannot activate your own account')
    if not AuthorizationService.is_system_manager(current_user) and AuthorizationService.is_admin(user):
        return json_bad_request('Only a System Manager can modify an admin user')

    user.active = True
    user.deactivated_at = None
    try:
        db.session.flush()
        return json_ok(message='User activated')
    except Exception as e:
        current_app.logger.error("activate_user: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return json_server_error(GENERIC_ERROR_MESSAGE)


@mobile_bp.route('/admin/users/<int:user_id>/deactivate', methods=['POST'])
@mobile_auth_required(permission='admin.users.deactivate')
def deactivate_user(user_id):
    """Deactivate a user account (admin)."""
    from app.models import User
    from app.services.authorization_service import AuthorizationService

    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        return json_bad_request('You cannot deactivate your own account')
    if not AuthorizationService.is_system_manager(current_user) and AuthorizationService.is_admin(user):
        return json_bad_request('Only a System Manager can modify an admin user')

    user.active = False
    user.deactivated_at = db.func.now()
    try:
        db.session.flush()
        return json_ok(message='User deactivated')
    except Exception as e:
        current_app.logger.error("deactivate_user: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return json_server_error(GENERIC_ERROR_MESSAGE)


# ---------------------------------------------------------------------------
# Admin -- Access Requests
# ---------------------------------------------------------------------------

@mobile_bp.route('/admin/access-requests', methods=['GET'])
@mobile_auth_required(permission='admin.access_requests.view')
def list_access_requests():
    """List country access requests (admin)."""
    from app.models.core import CountryAccessRequest, Country, User as UserModel

    status = request.args.get('status', 'pending')
    requests_q = CountryAccessRequest.query.filter_by(status=status).order_by(
        CountryAccessRequest.created_at.desc()
    )
    items = []
    for req in requests_q.all():
        user = UserModel.query.get(req.user_id)
        country = Country.query.get(req.country_id)
        items.append({
            'id': req.id,
            'user_id': req.user_id,
            'user_email': user.email if user else None,
            'user_name': user.name if user else None,
            'country_id': req.country_id,
            'country_name': country.name if country else None,
            'status': req.status,
            'created_at': req.created_at.isoformat() if req.created_at else None,
        })
    return json_ok(access_requests=items, total=len(items))


@mobile_bp.route('/admin/access-requests/<int:request_id>/approve', methods=['POST'])
@mobile_auth_required(permission='admin.access_requests.approve')
def approve_access_request(request_id):
    """Approve a country access request (admin)."""
    from app.models.core import CountryAccessRequest, Country
    from app.models import User as UserModel

    req = CountryAccessRequest.query.get_or_404(request_id)
    if req.status != 'pending':
        return json_bad_request('This request has already been processed.')

    try:
        user = UserModel.query.get_or_404(req.user_id)
        country = Country.query.get_or_404(req.country_id)
        user.add_entity_permission(entity_type='country', entity_id=country.id)
        req.status = 'approved'
        req.processed_by_user_id = current_user.id
        req.processed_at = db.func.now()
        db.session.flush()
        return json_ok(message='Access request approved')
    except Exception as e:
        current_app.logger.error("approve_access_request: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return json_server_error(GENERIC_ERROR_MESSAGE)


@mobile_bp.route('/admin/access-requests/<int:request_id>/reject', methods=['POST'])
@mobile_auth_required(permission='admin.access_requests.reject')
def reject_access_request(request_id):
    """Reject a country access request (admin)."""
    from app.models.core import CountryAccessRequest

    req = CountryAccessRequest.query.get_or_404(request_id)
    if req.status != 'pending':
        return json_bad_request('This request has already been processed.')

    try:
        req.status = 'rejected'
        req.processed_by_user_id = current_user.id
        req.processed_at = db.func.now()
        db.session.flush()
        return json_ok(message='Access request rejected')
    except Exception as e:
        current_app.logger.error("reject_access_request: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return json_server_error(GENERIC_ERROR_MESSAGE)


# ---------------------------------------------------------------------------
# Admin -- Send Notification
# ---------------------------------------------------------------------------

@mobile_bp.route('/admin/notifications/send', methods=['POST'])
@mobile_auth_required(permission='admin.notifications.manage')
def admin_send_notification():
    """Send push/email notification to selected users (admin)."""
    from app.services.notification.push import PushNotificationService
    data = get_json_safe()

    title = data.get('title', '').strip()
    body = data.get('body', '').strip()
    user_ids = data.get('user_ids', [])

    if not title or not body:
        return json_bad_request('title and body are required')
    if not user_ids:
        return json_bad_request('user_ids is required')

    try:
        result = PushNotificationService.send_push_to_users(
            user_ids=user_ids,
            title=title,
            body=body,
            data=data.get('data'),
        )
        return json_ok(**result)
    except Exception as e:
        current_app.logger.error("admin_send_notification: %s", e, exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)


# ---------------------------------------------------------------------------
# Admin -- Sessions
# ---------------------------------------------------------------------------

@mobile_bp.route('/admin/sessions/<session_id>/end', methods=['POST'])
@mobile_auth_required(permission='admin.analytics.view')
def end_session(session_id):
    """End a user session and blacklist it (admin)."""
    from flask import g
    from app.models.core import UserSessionLog
    from app.services.user_analytics_service import (
        add_session_to_blacklist, end_user_session, log_admin_action,
    )
    from app.utils.datetime_helpers import utcnow

    try:
        session_log = UserSessionLog.query.filter_by(session_id=session_id).first()
        if not session_log:
            return json_not_found('Session not found.')
        if not session_log.is_active:
            return json_bad_request('Session is already ended.')

        user_email = session_log.user.email if session_log.user else 'Unknown'
        target_user = session_log.user

        end_user_session(session_id, ended_by='admin_action')
        add_session_to_blacklist(session_id)

        if (current_user.is_authenticated and target_user and
                current_user.id == target_user.id and
                session.get('session_id') == session_id):
            session.clear()
            logout_user()

        log_admin_action(
            action_type='end_user_session',
            description=f'Ended session for {user_email} via mobile admin API',
            target_type='user_session',
            target_id=session_log.id,
            target_description=f'Session {session_id} for {user_email}',
            new_values={
                'session_id': session_id,
                'ended_by': 'admin_action',
                'end_time': utcnow().isoformat(),
            },
            risk_level='medium',
        )
        db.session.flush()
        return json_ok(message='Session ended and blacklisted.')
    except Exception as e:
        current_app.logger.error("end_session: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return json_server_error(GENERIC_ERROR_MESSAGE)
