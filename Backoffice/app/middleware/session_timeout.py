"""
Session Timeout Middleware

Handles session timeout checking and user logout for inactive sessions.
"""

from flask import session, redirect, url_for
from flask_login import logout_user, current_user
from app.utils.request_utils import is_static_asset_request
from app.utils.redirect_utils import get_current_relative_url
from datetime import datetime, timezone
from config import Config
from app.services.user_analytics_service import (
    end_user_session,
    remove_session_from_blacklist,
    is_session_blacklisted,
)
from contextlib import suppress


def check_session_timeout():
    """Check if the current session has timed out based on inactivity."""
    if current_user.is_authenticated and 'last_activity' in session:
        with suppress((ValueError, KeyError)):
            last_activity = datetime.fromisoformat(session['last_activity'])
            # Normalize to timezone-aware UTC if naive
            if last_activity.tzinfo is None:
                last_activity = last_activity.replace(tzinfo=timezone.utc)
            now_utc = datetime.now(timezone.utc)
            if now_utc - last_activity > Config.SESSION_INACTIVITY_TIMEOUT:
                return True
    return False


def handle_session_timeout():
    """
    Middleware function to check and handle session timeouts.
    Should be called in before_request hook.
    """
    from flask import request

    # Static assets: avoid DB via Flask-Login user load on every CSS/JS request
    if is_static_asset_request(request):
        return None

    # Skip session timeout check for JSON API routes (mobile app uses both prefixes)
    if request.path.startswith('/api/v1/') or request.path.startswith('/api/mobile/v1/'):
        return None

    # Skip auth-related routes that must be accessible without a valid session.
    # Without this, a blacklisted session hitting /login/azure or /login causes
    # an infinite redirect loop: the middleware redirects to /login, but /login
    # still carries the blacklisted session_id cookie, triggering the same check.
    _auth_prefixes = ('/login', '/auth/', '/register', '/forgot-password', '/reset-password')
    if request.path == '/login' or request.path.startswith(_auth_prefixes):
        return None

    # Check if the session is blacklisted
    if is_session_blacklisted(session.get('session_id')):
        _sid = session.get('session_id')
        logout_user()
        session.clear()
        remove_session_from_blacklist(_sid)
        return redirect(url_for('auth.login', next=get_current_relative_url()))

    # Check session timeout using the centralized function
    if check_session_timeout():
        # End the user session
        _sid = session.get('session_id')
        end_user_session(_sid, 'timeout')
        # Log out the user
        logout_user()
        # Remove the session from the blacklist since we're handling it
        remove_session_from_blacklist(_sid)
        # Fully clear the session to prevent stale session_id from re-triggering
        session.clear()
        # Redirect to login page, preserving intended page for after re-login
        return redirect(url_for('auth.login', next=get_current_relative_url()))

    return None


def register_session_timeout_middleware(app):
    """Register session timeout middleware with the Flask app."""
    @app.before_request
    def session_timeout_middleware():
        return handle_session_timeout()
