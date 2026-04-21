# Backoffice/app/routes/api/mobile/auth.py
"""Authentication routes: token issuance, refresh, SSO exchange, logout, password, profile."""

from contextlib import suppress

from flask import request, current_app, session
from flask_login import current_user, logout_user

from app import db
from app.utils.api_helpers import get_json_safe
from app.utils.mobile_auth import mobile_auth_required
from app.utils.mobile_responses import (
    mobile_ok, mobile_error, mobile_bad_request,
    mobile_auth_error, mobile_forbidden, mobile_server_error,
)
from app.utils.rate_limiting import auth_rate_limit, mobile_rate_limit
from app.routes.api.mobile import mobile_bp


@mobile_bp.route('/auth/token', methods=['POST'])
@auth_rate_limit()
def issue_tokens():
    """Issue JWT access + refresh tokens for mobile clients."""
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
        return mobile_bad_request('Email and password are required.')

    if _is_account_locked_out(email):
        log_login_attempt(email, success=False, failure_reason='account_locked')
        return mobile_error('Too many failed login attempts. Please try again later.', 429, 'ACCOUNT_LOCKED')

    user = UserService.get_by_email(email)
    if not user or not user.check_password(password):
        log_login_attempt(email, success=False, failure_reason='wrong_password' if user else 'user_not_found')
        return mobile_auth_error('Invalid email or password.')

    if not user.is_active:
        log_login_attempt(email, success=False, failure_reason='account_disabled')
        return mobile_forbidden('Your account is deactivated. Please contact an administrator.')

    log_login_attempt(email, success=True, user=user)
    jwt_session_id = str(_uuid.uuid4())
    start_user_session(user, jwt_session_id)
    log_user_activity(
        activity_type='login',
        description=f'User {email} obtained mobile JWT tokens',
        context_data={'user_id': user.id, 'auth_method': 'jwt', 'jwt_session_id': jwt_session_id},
    )

    tokens = issue_token_pair(user.id, session_id=jwt_session_id)
    return mobile_ok(data={
        'access_token': tokens['access_token'],
        'refresh_token': tokens['refresh_token'],
        'token_type': tokens['token_type'],
        'expires_in': tokens['expires_in'],
        'user': {
            'id': user.id,
            'email': user.email,
            'name': user.name,
            'title': user.title,
        },
    })


@mobile_bp.route('/auth/refresh', methods=['POST'])
@mobile_rate_limit(requests_per_minute=10)
def refresh_token():
    """Refresh an expired access token using a valid refresh token."""
    import uuid as _uuid
    from app.utils.mobile_jwt import (
        decode_mobile_token, issue_token_pair,
        blacklist_refresh_jti, is_refresh_jti_used,
    )
    from app.models import User, UserSessionLog

    data = get_json_safe()
    refresh = data.get('refresh_token', '')

    if not refresh:
        return mobile_bad_request('refresh_token is required')

    try:
        claims = decode_mobile_token(refresh, expected_type='refresh')
    except Exception:
        return mobile_auth_error('Invalid or expired refresh token.')

    # Refresh token rotation: reject previously consumed tokens.
    if claims.jti and is_refresh_jti_used(claims.jti):
        current_app.logger.warning(
            "SECURITY: Refresh token reuse detected (jti=%s, user=%s, sid=%s). "
            "Possible token theft — blacklisting session.",
            claims.jti, claims.user_id, claims.sid,
        )
        if claims.sid:
            from app.services.user_analytics_service import add_session_to_blacklist
            add_session_to_blacklist(claims.sid)
        return mobile_auth_error('Refresh token has already been used. Please log in again.')

    if claims.sid:
        from app.services.user_analytics_service import is_session_blacklisted
        if is_session_blacklisted(claims.sid):
            return mobile_auth_error('Session has been revoked.')

    user = User.query.get(claims.user_id)
    if not user or not user.is_active:
        return mobile_auth_error('User account not found or deactivated.')

    # Consume the old refresh token so it cannot be replayed.
    if claims.jti:
        blacklist_refresh_jti(claims.jti)

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
    return mobile_ok(data={
        'access_token': tokens['access_token'],
        'refresh_token': tokens['refresh_token'],
        'token_type': tokens['token_type'],
        'expires_in': tokens['expires_in'],
    })


@mobile_bp.route('/auth/exchange-session', methods=['POST'])
@mobile_auth_required
def exchange_session_for_tokens():
    """Exchange a valid Flask session cookie for a JWT token pair (Azure SSO bridge)."""
    import uuid as _uuid
    from app.utils.mobile_jwt import issue_token_pair
    from app.services.user_analytics_service import start_user_session, log_user_activity
    from flask import session as flask_session

    jwt_session_id = flask_session.get('session_id') or str(_uuid.uuid4())

    if not flask_session.get('session_id'):
        start_user_session(current_user, jwt_session_id)
        log_user_activity(
            activity_type='login',
            description=f'User {current_user.email} exchanged session cookie for JWT tokens',
            context_data={'user_id': current_user.id, 'auth_method': 'jwt_exchange'},
        )

    tokens = issue_token_pair(current_user.id, session_id=jwt_session_id)
    return mobile_ok(data={
        'access_token': tokens['access_token'],
        'refresh_token': tokens['refresh_token'],
        'token_type': tokens['token_type'],
        'expires_in': tokens['expires_in'],
        'user': {
            'id': current_user.id,
            'email': current_user.email,
            'name': current_user.name,
            'title': current_user.title,
        },
    })


@mobile_bp.route('/auth/session', methods=['GET'])
@mobile_auth_required
def session_check():
    """Lightweight session / JWT validity check."""
    return mobile_ok(data={
        'user': {
            'id': current_user.id,
            'email': current_user.email,
            'name': current_user.name,
            'title': current_user.title,
            'active': current_user.is_active,
        },
    })


@mobile_bp.route('/auth/logout', methods=['POST'])
def mobile_logout():
    """Logout: blacklist the JWT session and clear the Flask session.

    Intentionally does not use @mobile_auth_required so that logout succeeds
    even when the access token has just expired.  The Bearer token *signature*
    is still verified — only the expiry check is relaxed — so the endpoint
    cannot be abused to blacklist arbitrary sessions with a forged token.
    """
    from app.services.user_analytics_service import (
        log_user_activity_for_user, end_user_session,
        add_session_to_blacklist, get_client_info,
    )
    from app.models.core import UserLoginLog, UserSessionLog

    jwt_sid = None
    _user = current_user if current_user.is_authenticated else None

    # Extract the session ID from the Bearer token.
    # Accept a non-expired token first; fall back to an expired-but-signed token
    # so logout always propagates to the server even if the access token just aged out.
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token:
            from app.utils.mobile_jwt import decode_mobile_token, decode_mobile_token_ignoring_expiry
            try:
                claims = decode_mobile_token(token, expected_type="access")
                jwt_sid = claims.sid
                if _user is None or not _user.is_authenticated:
                    from app.models import User
                    u = User.query.get(claims.user_id)
                    if u and u.is_active:
                        login_user(u, remember=False)
                        _user = u
            except Exception:
                with suppress(Exception):
                    claims = decode_mobile_token_ignoring_expiry(token)
                    if claims.token_type == "access":
                        jwt_sid = claims.sid
                        if _user is None:
                            from app.models import User
                            _user = User.query.get(claims.user_id)

    # Blacklist the JWT session so any outstanding tokens for this session are rejected.
    if jwt_sid:
        with suppress(Exception):
            add_session_to_blacklist(jwt_sid)

    # End the UserSessionLog record.
    # log_logout() reads the session ID from the Flask session, which is empty
    # for JWT-only mobile requests.  Call end_user_session() directly with the
    # JWT sid so the session row is properly marked as inactive.
    if jwt_sid:
        with suppress(Exception):
            end_user_session(jwt_sid, 'logout')

    # Log the logout event (best-effort).
    with suppress(Exception):
        if _user:
            session_duration = None
            with suppress(Exception):
                sess_log = UserSessionLog.query.filter_by(session_id=jwt_sid).first() if jwt_sid else None
                if sess_log and sess_log.duration_minutes is not None:
                    session_duration = sess_log.duration_minutes

            client_info = get_client_info()
            logout_log = UserLoginLog(
                user_id=_user.id,
                email_attempted=_user.email,
                event_type='logout',
                ip_address=client_info['ip_address'],
                user_agent=client_info['user_agent'],
                browser=client_info['browser'],
                operating_system=client_info['operating_system'],
                device_type=client_info['device_type'],
                session_duration_minutes=session_duration,
            )
            db.session.add(logout_log)

            log_user_activity_for_user(
                _user.id,
                'logout',
                f'User {_user.email} logged out via mobile API',
                {'user_id': _user.id, 'session_duration_minutes': session_duration},
            )

    with suppress(Exception):
        db.session.flush()

    logout_user()
    session.clear()
    return mobile_ok(message='Logged out successfully.')


@mobile_bp.route('/auth/change-password', methods=['POST'])
@mobile_rate_limit(requests_per_minute=5)
@mobile_auth_required
def mobile_change_password():
    """Change the current user's password."""
    data = get_json_safe()
    current_password = data.get('current_password') or ''
    new_password = data.get('new_password') or ''

    if not current_password or not new_password:
        return mobile_bad_request('current_password and new_password are required.')

    if not current_user.check_password(current_password):
        return mobile_auth_error('Current password is incorrect.')

    from app.utils.password_validator import validate_password_strength
    is_valid, errors = validate_password_strength(
        new_password,
        user_email=current_user.email,
        user_name=current_user.name,
    )
    if not is_valid:
        return mobile_bad_request('; '.join(errors))

    try:
        current_user.set_password(new_password)
        db.session.flush()

        from app.services.user_analytics_service import log_user_activity
        log_user_activity(
            activity_type='password_change',
            description=f'User {current_user.email} changed password via mobile API',
            context_data={'user_id': current_user.id},
        )
        return mobile_ok(message='Password changed successfully.', requires_reauth=True)
    except Exception as e:
        current_app.logger.error("Password change failed: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error('Could not change password. Please try again.')


@mobile_bp.route('/auth/profile', methods=['GET'])
@mobile_auth_required
def mobile_profile():
    """Return the current user's profile data."""
    from app.services.authorization_service import AuthorizationService

    user = current_user
    role_codes = AuthorizationService.get_role_codes(user)
    rbac_roles = [{'code': code} for code in role_codes if code]
    access = AuthorizationService.access_level(user)

    return mobile_ok(data={
        'user': {
            'id': user.id,
            'email': user.email,
            'name': user.name,
            'title': user.title,
            'chatbot_enabled': getattr(user, 'chatbot_enabled', False),
            'profile_color': getattr(user, 'profile_color', '#3B82F6'),
            'active': user.is_active,
            'rbac_roles': rbac_roles,
            'role': access,
        },
    })


@mobile_bp.route('/auth/profile', methods=['PUT', 'PATCH'])
@mobile_auth_required
def mobile_update_profile():
    """Update the current user's profile."""
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
        return mobile_ok(message='Profile updated successfully.')
    except Exception as e:
        current_app.logger.error("Profile update failed: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error('Could not update profile. Please try again.')
