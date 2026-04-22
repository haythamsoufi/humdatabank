"""
User Analytics and Activity Logging Utilities

This module provides functions for tracking user activities, login attempts,
session analytics, and security events for the platform.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from io import StringIO
from typing import Any, Dict, List, Optional, Tuple
import csv
from flask import request, session, current_app, has_request_context, g
from flask_babel import gettext as _
from flask_login import current_user
from sqlalchemy import and_, or_, func, inspect, text, Integer
from app import db
from app.utils.datetime_helpers import utcnow, ensure_utc
from app.models import (
    UserLoginLog, UserActivityLog, UserSessionLog,
    AdminActionLog, SecurityEvent, User
)
import json
import re
from urllib.parse import urlparse
from user_agents import parse
from app.utils.transactions import request_transaction_rollback
from app.utils.constants import DEFAULT_SESSION_CLEANUP_LOCK_ID
from app.utils.activity_types import normalize_activity_type
from app.utils.page_view_paths import (
    merge_page_view_path_count,
    page_view_path_key_from_request,
)

# Mobile JWT auth calls _update_session_activity_explicit(..., 'action') on every
# API request to refresh last_activity only; device heartbeat uses 'heartbeat'.
# These must not increment actions_performed (that counter is for form saves,
# submits, file uploads, and other meaningful actions — not per-request pings).
_SESSION_LOG_TOUCH_ONLY_TYPES = frozenset({'action', 'heartbeat'})

# Legitimate native HTTP stacks (mobile apps, not web crawlers). These often omit
# Mozilla/WebKit tokens; treat as non-bot before keyword/heuristic checks.
_NATIVE_CLIENT_UA_MARKERS = frozenset({
    'dart/',           # Dart dart:io HttpClient (Flutter, package:http)
    '(dart:io)',
    'okhttp',          # Android OkHttp (Flutter Android / common plugins)
    'cfnetwork',       # iOS CFNetwork / URLSession
    'alamofire',
    'cronet',          # Chromium network stack (some Android builds)
})


def _resolve_user_session_id_for_logging() -> Optional[str]:
    """Flask login session id or mobile JWT sid; correlates UserActivityLog with UserSessionLog."""
    try:
        sid = session.get('session_id')
        if sid:
            return str(sid)[:255]
    except Exception:
        pass
    if has_request_context():
        jwt_sid = getattr(g, '_mobile_jwt_sid', None)
        if jwt_sid:
            return str(jwt_sid)[:255]
    return None


def get_client_info():
    """Extract client information from the request."""
    user_agent_string = request.headers.get('User-Agent', '')
    user_agent = parse(user_agent_string)

    # Handle browser information with fallbacks
    browser_family = user_agent.browser.family if user_agent.browser.family else 'Unknown'
    browser_version = user_agent.browser.version_string if user_agent.browser.version_string else ''

    # Format browser string - only include version if it exists and is not empty
    if browser_version and browser_version.strip():
        browser_str = f"{browser_family} {browser_version}"
    else:
        browser_str = browser_family

    # Handle OS information with fallbacks
    os_family = user_agent.os.family if user_agent.os.family else 'Unknown'
    os_version = user_agent.os.version_string if user_agent.os.version_string else ''

    # Format OS string - only include version if it exists and is not empty
    if os_version and os_version.strip():
        os_str = f"{os_family} {os_version}"
    else:
        os_str = os_family

    device_type = get_device_type(user_agent)

    # Flutter mobile clients send explicit platform headers that are far more
    # reliable than UA-string parsing (Dart's default UA looks like a desktop).
    x_platform = request.headers.get('X-Platform', '').strip().lower()
    x_os_version = request.headers.get('X-OS-Version', '').strip()
    if x_platform in ('ios', 'android'):
        device_type = 'Mobile'
        browser_str = 'Humanitarian Databank App'
        if x_os_version:
            os_str = x_os_version  # e.g. "iOS 17.2" or "Android 14"

    return {
        'ip_address': get_client_ip(),
        'user_agent': user_agent_string,
        'browser': browser_str,
        'operating_system': os_str,
        'device_type': device_type,
    }


def _is_auto_managed_request() -> bool:
    """Check whether the request lifecycle is auto-managed by the transaction middleware."""
    return has_request_context() and bool(getattr(g, "_auto_txn_managed", False))


def _commit_or_flush():
    """
    Flush changes during managed requests, otherwise commit immediately.
    """
    if _is_auto_managed_request():
        db.session.flush()
    else:
        db.session.commit()


def _rollback_transaction(reason: str) -> None:
    """Rollback the current transaction and signal the middleware to skip auto-commit."""
    request_transaction_rollback(reason=reason)


def _strip_ip_port(ip):
    """Strip port suffix from an IP address string.

    Handles IPv4:port (1.2.3.4:5678) and [IPv6]:port ([::1]:5678).
    Raw IPv6 with multiple colons is left untouched.
    """
    if not ip or ip == 'unknown':
        return ip
    if ip.startswith('['):
        bracket_end = ip.find(']')
        if bracket_end != -1:
            return ip[1:bracket_end]
    elif ip.count(':') == 1:
        return ip.rsplit(':', 1)[0]
    return ip


def get_client_ip():
    """Get the client's IP address, considering proxies.

    Strips port suffixes that some proxies (e.g. Azure App Service) append
    to X-Forwarded-For entries (``1.2.3.4:53708`` → ``1.2.3.4``).
    """
    if request.headers.get('X-Forwarded-For'):
        ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        ip = request.headers.get('X-Real-IP').strip()
    else:
        ip = request.remote_addr or 'unknown'
    return _strip_ip_port(ip)


def get_device_type(user_agent):
    """Determine device type from user agent."""
    if not user_agent:
        return 'Unknown'

    if user_agent.is_mobile:
        return 'Mobile'
    elif user_agent.is_tablet:
        return 'Tablet'
    else:
        return 'Desktop'


def session_log_device_icon_classes(
    user_agent: Optional[str] = None,
    device_type: Optional[str] = None,
    operating_system: Optional[str] = None,
) -> str:
    """
    Font Awesome classes for admin session lists (OS / brand + form-factor fallback).

    Mirrors logic in MobileApp ``session_logs_screen.dart`` (_sessionDeviceLeadingIcon)
    and fixes template checks that compared lowercase ``mobile`` to stored ``Mobile``.
    """
    dt = (device_type or '').strip().lower()
    os_part = (operating_system or '').strip().lower()
    ua = (user_agent or '').strip().lower()
    combined = f'{os_part} {ua}'

    def _contains(*needles: str) -> bool:
        return any(n in combined for n in needles)

    # Android (check before generic Linux — Android UAs often include "Linux")
    if _contains('android'):
        return 'fab fa-android text-green-600'

    # Apple: iOS / iPadOS / macOS
    if _contains('iphone', 'ipod', 'ipad', 'ios', 'ipados', 'mac os', 'macos', 'macintosh'):
        return 'fab fa-apple text-gray-700'

    if _contains('windows'):
        return 'fab fa-windows text-blue-600'

    if _contains('linux') and 'android' not in combined:
        return 'fab fa-linux text-orange-600'

    if dt == 'tablet':
        return 'fas fa-tablet-alt text-gray-500'
    if dt == 'mobile':
        return 'fas fa-mobile-alt text-gray-500'
    return 'fas fa-laptop text-gray-500'


def log_login_attempt(email, success=True, user=None, session_id=None, failure_reason=None):
    """
    Log a user login attempt (successful or failed).

    Args:
        email (str): Email address attempted
        success (bool): Whether the login was successful
        user (User): User object if login was successful
        session_id (str): Session ID for successful logins
        failure_reason (str): Reason for failure ('wrong_password', 'user_not_found', etc.)
    """
    try:
        client_info = get_client_info()

        # Returns a reason string if suspicious, None otherwise
        suspicious_reason = check_suspicious_login(client_info['ip_address'], email, success)
        is_suspicious = bool(suspicious_reason)

        # Count recent failed attempts for this email/IP
        failed_count = get_recent_failed_attempts(email, client_info['ip_address'])

        # Detect potential bots based on user agent
        is_bot = detect_bot_user_agent(client_info['user_agent'])

        # Get referrer information
        referrer = request.referrer if hasattr(request, 'referrer') else None

        login_log = UserLoginLog(
            user_id=user.id if user and success else None,
            email_attempted=email,
            event_type='login_success' if success else 'login_failed',
            ip_address=client_info['ip_address'],
            user_agent=client_info['user_agent'],
            browser=client_info['browser'],
            operating_system=client_info['operating_system'],
            device_type=client_info['device_type'],
            is_suspicious=is_suspicious,
            failed_attempts_count=failed_count,
            session_id=session_id,
            failure_reason=failure_reason if not success else None,
            is_bot_detected=is_bot,
            referrer_url=referrer
        )

        db.session.add(login_log)
        _commit_or_flush()

        # Create security event for failed logins or suspicious activity
        if not success or is_suspicious:
            create_security_event_for_login(
                email, success, is_suspicious, client_info,
                failure_reason, suspicious_reason,
            )

    except Exception as e:
        current_app.logger.error(f"Error logging login attempt: {str(e)}")
        _rollback_transaction("log_login_attempt_error")


def analyze_ua_for_bot(user_agent_string: Optional[str]) -> Tuple[bool, Optional[str]]:
    """
    Heuristic bot/automation detection from the User-Agent string (same rules as login logging).

    Returns:
        (is_bot, reason_if_bot) — reason is a short admin-facing explanation when is_bot is True.
    """
    if not user_agent_string:
        return True, _('No User-Agent header was sent.')

    user_agent_lower = user_agent_string.lower()

    if any(marker in user_agent_lower for marker in _NATIVE_CLIENT_UA_MARKERS):
        return False, None

    bot_patterns = [
        'bot', 'crawler', 'spider', 'scraper', 'wget', 'curl',
        'python-requests', 'urllib',
        # Do not use bare 'http' — it matches legitimate stacks like OkHttp.
        'api', 'monitoring',
        'test', 'automation', 'script', 'tool', 'check',
        'postman', 'insomnia', 'httpie'
    ]

    for pattern in bot_patterns:
        if pattern in user_agent_lower:
            return True, _(
                'User-Agent contains an automation-related keyword: "%(keyword)s".',
                keyword=pattern,
            )

    if len(user_agent_string.strip()) < 10:
        return True, _(
            'User-Agent is very short (under 10 characters), which often indicates an automated client.'
        )

    browser_indicators = ['mozilla', 'webkit', 'gecko', 'chrome', 'safari', 'firefox', 'edge']
    has_browser_indicator = any(indicator in user_agent_lower for indicator in browser_indicators)

    if not has_browser_indicator:
        return True, _(
            'User-Agent does not include typical browser tokens (Mozilla, WebKit, Chrome, Safari, Firefox, Edge, etc.).'
        )

    return False, None


def detect_bot_user_agent(user_agent_string):
    """
    Detect if the user agent appears to be from a bot or automated tool.

    Args:
        user_agent_string (str): User agent string from the request

    Returns:
        bool: True if bot is detected
    """
    is_bot, _ = analyze_ua_for_bot(user_agent_string)
    return is_bot


def bot_user_agent_explanation(user_agent_string: Optional[str]) -> Optional[str]:
    """Human-readable reason for bot flag, or None if the UA would not be flagged."""
    is_bot, reason = analyze_ua_for_bot(user_agent_string)
    return reason if is_bot else None


def log_logout(user, session_duration_minutes=None):
    """
    Log a user logout event.

    Args:
        user (User): User object
        session_duration_minutes (int): Duration of the session in minutes
    """
    try:
        client_info = get_client_info()

        logout_log = UserLoginLog(
            user_id=user.id,
            email_attempted=user.email,
            event_type='logout',
            ip_address=client_info['ip_address'],
            user_agent=client_info['user_agent'],
            browser=client_info['browser'],
            operating_system=client_info['operating_system'],
            device_type=client_info['device_type'],
            session_duration_minutes=session_duration_minutes
        )

        db.session.add(logout_log)

        # End session log
        end_user_session(session.get('session_id'), 'logout')

        _commit_or_flush()

    except Exception as e:
        current_app.logger.error(f"Error logging logout: {str(e)}")
        _rollback_transaction("log_logout_error")


# Endpoints that should never write UserActivityLog rows (polling / background admin APIs).
_SKIP_USER_ACTIVITY_LOG_ENDPOINTS = frozenset({
    'admin_analytics_api.session_logs_list_api',
    'admin_analytics_api.login_logs_list_api',
    'user_management.api_users_profile_summary',
    'main.api_users_profile_summary',
    'forms_api.api_presence_active_users',
    'utilities.refresh_csrf_token',
    'utilities.refresh_csrf_token_get',
    'forms_api.api_search_indicator_bank',
    'forms_api.get_lookup_list_options',
    'forms_api.get_lookup_list_config_ui',
    'forms_api.api_render_dynamic_indicator',
    'user_management.get_user_entities',
    'user_management.get_ns_hierarchy',
    'user_management.get_secretariat_hierarchy',
    'user_management.get_secretariat_regions_hierarchy',
    'ai_v2.chat',
    'ai_v2.issue_token',
    'ai_documents.list_ifrc_api_documents',
    'ai_documents.list_ifrc_api_types',
    'ai_ws',
    'ai_management.list_system_documents',
    'settings.api_check_updates',
    'utilities.api_translation_services',
})


def _should_skip_activity_user_log_endpoint(endpoint: Optional[str]) -> bool:
    """High-volume or background calls — not useful in the audit trail."""
    if not endpoint:
        return False
    if endpoint in _SKIP_USER_ACTIVITY_LOG_ENDPOINTS:
        return True
    if endpoint.rsplit(".", 1)[-1] == "device_heartbeat":
        return True
    # Embedded user analytics fragment on user edit form (?partial=1)
    if endpoint == "analytics.user_analytics":
        try:
            from flask import has_request_context, request as flask_request

            if has_request_context() and flask_request.args.get("partial", "0") == "1":
                return True
        except Exception:
            pass
    return False


def log_user_activity(activity_type, description=None, context_data=None, response_time_ms=None, status_code=None):
    """
    Log a user activity.

    Args:
        activity_type (str): Type of activity (e.g., 'page_view', 'form_submit')
        description (str): Optional description of the activity
        context_data (dict): Additional context data
        response_time_ms (int): Response time in milliseconds
        status_code (int): HTTP response status code
    """
    if not current_user.is_authenticated:
        return

    if _should_skip_activity_user_log_endpoint(request.endpoint):
        return

    try:
        client_info = get_client_info()

        # Safely constrain string fields to column limits
        endpoint_val = (request.endpoint or '')[:255] if request.endpoint else None
        method_val = (request.method or '')[:10] if request.method else None
        url_path_val = (request.path or '')[:500] if request.path else None
        referrer_val = (request.referrer or '')[:500] if request.referrer else None
        ip_address_val = (client_info.get('ip_address') or '')[:45]
        user_agent_val = client_info.get('user_agent')  # Text field, no limit

        normalized_activity_type = normalize_activity_type(activity_type)

        activity_log = UserActivityLog(
            user_id=current_user.id,
            user_session_id=_resolve_user_session_id_for_logging(),
            activity_type=normalized_activity_type,
            activity_description=description,
            endpoint=endpoint_val,
            http_method=method_val,
            url_path=url_path_val,
            referrer=referrer_val,
            ip_address=ip_address_val,
            user_agent=user_agent_val,
            context_data=context_data,
            response_time_ms=response_time_ms,
            response_status_code=status_code
        )

        db.session.add(activity_log)

        # Update session statistics
        pv_key = None
        if normalized_activity_type == "page_view":
            if context_data and isinstance(context_data, dict):
                pv_key = context_data.get("page_view_path_key")
            if not pv_key:
                pv_key = page_view_path_key_from_request(request)
        update_session_activity(
            normalized_activity_type, page_view_path_key=pv_key
        )

        _commit_or_flush()

    except Exception as e:
        current_app.logger.error(f"Error logging user activity: {str(e)}")
        _rollback_transaction("log_user_activity_error")


def increment_session_page_views_without_activity_log() -> None:
    """
    Middleware-only: bump ``UserSessionLog.page_views`` without inserting ``UserActivityLog``.

    Automatic GET tracking used to write one audit row per navigation, which dominated
    the table while the audit UI hid ``page_view`` by default. Session analytics
    (dashboards, session detail) still need accurate page-view counts.

    Explicit ``page_view`` rows (e.g. mobile ``screen_view`` via ``log_user_activity``)
    are unchanged.
    """
    if not current_user.is_authenticated:
        return
    try:
        pv_key = page_view_path_key_from_request(request)
        update_session_activity("page_view", page_view_path_key=pv_key)
        _commit_or_flush()
    except Exception as e:
        current_app.logger.error(
            "Error incrementing session page views (no activity log): %s", e
        )
        _rollback_transaction("increment_session_page_views_without_activity_log_error")


def increment_session_page_views_without_activity_log_deferred(
    session_id: Optional[str],
    page_view_path_key: Optional[str] = None,
) -> None:
    """Deferred middleware path: session counter only, no ``UserActivityLog`` row."""
    if not session_id:
        return
    try:
        from app.utils.transactions import atomic

        with atomic(remove_session=True):
            _update_session_activity_explicit(
                session_id, "page_view", page_view_path_key=page_view_path_key
            )
    except Exception as e:
        current_app.logger.error(
            "Error incrementing session page views deferred (no activity log): %s", e
        )


def _update_session_activity_explicit(
    session_id: Optional[str],
    activity_type: str,
    page_view_path_key: Optional[str] = None,
) -> None:
    """
    Update session activity statistics without relying on Flask request/session context.
    Intended for deferred/background logging.
    """
    if not session_id:
        return
    try:
        session_log = UserSessionLog.query.filter_by(session_id=session_id).first()
        if not session_log:
            return

        # Don't update a session that has already been ended (e.g. by inactivity
        # cleanup). The refresh_token endpoint will have created a new session
        # with a fresh session_id; activity for the resumed session will be
        # tracked under that new row instead.
        if not session_log.is_active:
            return

        session_log.last_activity = utcnow()

        normalized_activity_type = normalize_activity_type(activity_type)

        if normalized_activity_type in _SESSION_LOG_TOUCH_ONLY_TYPES:
            return

        if normalized_activity_type == 'page_view':
            session_log.page_views += 1
            merge_page_view_path_count(session_log, page_view_path_key or "/")
        elif normalized_activity_type in ['form_submitted', 'form_saved', 'data_save']:
            session_log.forms_submitted += 1
            session_log.actions_performed += 1
        elif normalized_activity_type == 'file_uploaded':
            session_log.files_uploaded += 1
            session_log.actions_performed += 1
        else:
            session_log.actions_performed += 1
    except Exception as e:
        current_app.logger.error(f"Error updating session activity (explicit): {str(e)}")


def log_user_activity_explicit(
    *,
    user_id: int,
    session_id: Optional[str],
    activity_type: str,
    description: Optional[str],
    context_data: Optional[dict],
    response_time_ms: Optional[int],
    status_code: Optional[int],
    endpoint: Optional[str],
    http_method: Optional[str],
    url_path: Optional[str],
    referrer: Optional[str],
    ip_address: str,
    user_agent: Optional[str],
    page_view_path_key: Optional[str] = None,
) -> None:
    """
    Log a user activity using a standalone transaction, without Flask request/current_user dependencies.
    Safe to call from response.call_on_close or background contexts.
    """
    if not user_id:
        return

    if _should_skip_activity_user_log_endpoint((endpoint or "").strip() or None):
        return

    from app.utils.transactions import atomic

    normalized_activity_type = normalize_activity_type(activity_type)

    # Safely constrain string fields to column limits
    endpoint_val = (endpoint or '')[:255] if endpoint else None
    method_val = (http_method or '')[:10] if http_method else None
    url_path_val = (url_path or '')[:500] if url_path else None
    referrer_val = (referrer or '')[:500] if referrer else None
    ip_address_val = (ip_address or '')[:45]
    user_agent_val = user_agent  # Text field, no limit

    try:
        with atomic(remove_session=True):
            activity_log = UserActivityLog(
                user_id=user_id,
                user_session_id=(str(session_id)[:255] if session_id else None),
                activity_type=normalized_activity_type,
                activity_description=description,
                endpoint=endpoint_val,
                http_method=method_val,
                url_path=url_path_val,
                referrer=referrer_val,
                ip_address=ip_address_val or 'unknown',
                user_agent=user_agent_val,
                context_data=context_data,
                response_time_ms=response_time_ms,
                response_status_code=status_code
            )

            db.session.add(activity_log)
            pv_key = page_view_path_key
            if normalized_activity_type == "page_view" and pv_key is None and context_data:
                pv_key = context_data.get("page_view_path_key")
            _update_session_activity_explicit(
                session_id, normalized_activity_type, page_view_path_key=pv_key
            )
    except Exception as e:
        current_app.logger.error(f"Error logging user activity (explicit): {str(e)}")


def log_user_activity_for_user(user_id, activity_type, description=None, context_data=None, response_time_ms=None, status_code=None):
    """
    Log an activity for a specific user ID, even if they are not the current session user.
    Useful for system-triggered events like account creation or password resets.
    """
    if not user_id:
        return
    if has_request_context() and _should_skip_activity_user_log_endpoint(request.endpoint):
        return
    try:
        has_ctx = has_request_context()
        if has_ctx:
            client_info = get_client_info()
            endpoint_val = (request.endpoint or '')[:255] if request.endpoint else None
            method_val = (request.method or '')[:10] if request.method else None
            url_path_val = (request.path or '')[:500] if request.path else None
            referrer_val = (request.referrer or '')[:500] if request.referrer else None
            ip_address_val = (client_info.get('ip_address') or '')[:45]
            user_agent_val = client_info.get('user_agent')
        else:
            endpoint_val = None
            method_val = None
            url_path_val = None
            referrer_val = None
            ip_address_val = 'unknown'
            user_agent_val = None

        normalized_activity_type = normalize_activity_type(activity_type)

        activity_log = UserActivityLog(
            user_id=user_id,
            user_session_id=_resolve_user_session_id_for_logging(),
            activity_type=normalized_activity_type,
            activity_description=description,
            endpoint=endpoint_val,
            http_method=method_val,
            url_path=url_path_val,
            referrer=referrer_val,
            ip_address=ip_address_val,
            user_agent=user_agent_val,
            context_data=context_data,
            response_time_ms=response_time_ms,
            response_status_code=status_code
        )
        db.session.add(activity_log)
        _commit_or_flush()
    except Exception as e:
        current_app.logger.error(f"Error logging activity for user {user_id}: {str(e)}")
        _rollback_transaction("log_user_activity_for_user_error")


def start_user_session(user, session_id):
    """
    Start tracking a user session.

    Args:
        user (User): User object
        session_id (str): Session ID
    """
    try:
        client_info = get_client_info()

        session_log = UserSessionLog(
            user_id=user.id,
            session_id=session_id,
            ip_address=client_info['ip_address'],
            user_agent=client_info['user_agent'],
            browser=client_info['browser'],
            operating_system=client_info['operating_system'],
            device_type=client_info['device_type']
        )

        db.session.add(session_log)
        _commit_or_flush()

    except Exception as e:
        current_app.logger.error(f"Error starting user session: {str(e)}")
        _rollback_transaction("start_user_session_error")


def update_session_activity(activity_type, page_view_path_key: Optional[str] = None):
    """
    Update session activity statistics.

    Args:
        activity_type (str): Type of activity performed
        page_view_path_key: Canonical path key when activity_type is page_view
    """
    try:
        # Check if the session is in a failed state and rollback if needed
        if db.session.is_active and db.session.dirty:
            _rollback_transaction("update_session_activity_dirty_state")

        session_id = session.get('session_id')
        if not session_id:
            return

        normalized_activity_type = normalize_activity_type(activity_type)
        session_log = UserSessionLog.query.filter_by(session_id=session_id).first()
        if session_log:
            session_log.last_activity = utcnow()

            if normalized_activity_type in _SESSION_LOG_TOUCH_ONLY_TYPES:
                return

            if normalized_activity_type == 'page_view':
                session_log.page_views += 1
                merge_page_view_path_count(
                    session_log, page_view_path_key or "/"
                )
            elif normalized_activity_type in ['form_submitted', 'form_saved', 'data_save']:
                session_log.forms_submitted += 1
                session_log.actions_performed += 1
            elif normalized_activity_type == 'file_uploaded':
                session_log.files_uploaded += 1
                session_log.actions_performed += 1
            else:
                session_log.actions_performed += 1

    except Exception as e:
        current_app.logger.error(f"Error updating session activity: {str(e)}")
        _rollback_transaction("update_session_activity_error")


def end_user_session(session_id, ended_by='logout'):
    """
    End a user session and calculate duration.

    Args:
        session_id (str): Session ID to end
        ended_by (str): How the session ended ('logout', 'timeout', 'system')
    """
    try:
        if not session_id:
            return

        session_log = UserSessionLog.query.filter_by(session_id=session_id).first()
        if session_log and session_log.is_active:
            session_log.session_end = utcnow()
            session_log.is_active = False
            session_log.ended_by = ended_by

            # Calculate duration
            # Ensure both datetimes are timezone-aware to avoid subtraction errors
            session_end_aware = ensure_utc(session_log.session_end)
            session_start_aware = ensure_utc(session_log.session_start)
            duration = session_end_aware - session_start_aware
            session_log.duration_minutes = int(duration.total_seconds() / 60)

    except Exception as e:
        current_app.logger.error(f"Error ending user session: {str(e)}")


def effective_session_duration_minutes(session_log):
    """
    Wall-clock session length in minutes (login to session close).

    When ``session_end`` is set, duration is always derived from
    ``session_end - session_start`` (UTC-normalized) so the value matches the
    timestamps shown in the UI. This includes idle time after the last request
    until the session is ended (timeout, logout, or cleanup). Stored
    ``duration_minutes`` can be wrong (e.g. legacy naive/aware subtraction or bad
    writes) and is only used as a fallback when ``session_end`` is missing.

    For time until the last recorded activity only, use
    ``effective_session_active_duration_minutes``.
    """
    if session_log is None:
        return None
    if session_log.session_start is None:
        return None
    session_start_aware = ensure_utc(session_log.session_start)

    if session_log.session_end is not None:
        session_end_aware = ensure_utc(session_log.session_end)
        delta = session_end_aware - session_start_aware
        return max(0, int(delta.total_seconds() / 60))

    if getattr(session_log, 'is_active', False):
        delta = utcnow() - session_start_aware
        return max(0, int(delta.total_seconds() / 60))

    if session_log.duration_minutes is not None:
        return session_log.duration_minutes
    return None


def effective_session_active_duration_minutes(session_log):
    """
    Minutes from ``session_start`` to ``last_activity`` (UTC-normalized).

    Represents how long the user was generating activity before the last bump;
    it does not include idle time after ``last_activity`` until the session row
    is closed (unlike ``effective_session_duration_minutes``).
    """
    if session_log is None or session_log.session_start is None:
        return None
    session_start_aware = ensure_utc(session_log.session_start)
    if session_log.last_activity is None:
        return 0
    last_aware = ensure_utc(session_log.last_activity)
    delta = last_aware - session_start_aware
    return max(0, int(delta.total_seconds() / 60))


def user_session_log_active_duration_minutes_sql():
    """
    SQL expression for whole minutes between ``session_start`` and ``last_activity``.

    Used for ``min_duration`` filtering alongside ``duration_minutes``. Returns
    ``None`` when the dialect is not supported (filter omits the active branch).
    """
    dialect = db.engine.dialect.name
    start = UserSessionLog.session_start
    last = UserSessionLog.last_activity
    if dialect == 'postgresql':
        return func.coalesce(
            func.cast(
                func.floor(func.extract('epoch', last - start) / 60.0),
                Integer,
            ),
            0,
        )
    if dialect == 'sqlite':
        return func.coalesce(
            func.cast(
                (func.julianday(last) - func.julianday(start)) * (24 * 60),
                Integer,
            ),
            0,
        )
    if dialect in ('mysql', 'mariadb'):
        return func.coalesce(func.timestampdiff(text('MINUTE'), start, last), 0)
    return None


# Global set to store blacklisted session IDs for force logout.
# SECURITY NOTE: This is per-process; in multi-worker deployments a
# force-logout may not take effect on every worker. For production, consider
# moving this to a shared store (Redis or database) so all workers honour the
# blacklist immediately.
_blacklisted_sessions = set()


def add_session_to_blacklist(session_id):
    """
    Add a session ID to the blacklist for immediate termination.

    Args:
        session_id (str): Session ID to blacklist
    """
    global _blacklisted_sessions
    _blacklisted_sessions.add(session_id)
    current_app.logger.info(f"Session {session_id} added to blacklist for force logout")


def is_session_blacklisted(session_id):
    """
    Check if a session ID is blacklisted for termination.

    Checks the in-memory set first (fast path), then falls back to the DB so
    that force-logouts survive server restarts and work across Gunicorn workers
    that each maintain their own in-memory copy.

    Args:
        session_id (str): Session ID to check

    Returns:
        bool: True if session is blacklisted
    """
    global _blacklisted_sessions
    if session_id in _blacklisted_sessions:
        return True
    # DB fallback: treat admin-ended sessions as blacklisted regardless of which
    # worker originally called add_session_to_blacklist.
    try:
        row = (
            UserSessionLog.query
            .with_entities(UserSessionLog.is_active, UserSessionLog.ended_by)
            .filter_by(session_id=session_id)
            .first()
        )
        if row and not row.is_active and row.ended_by == 'admin_action':
            # Warm the in-process cache so subsequent calls are fast.
            _blacklisted_sessions.add(session_id)
            return True
    except Exception as e:
        current_app.logger.debug("DB blacklist check failed (using in-memory only): %s", e)
    return False


def remove_session_from_blacklist(session_id):
    """
    Remove a session ID from the blacklist (cleanup after logout).

    Args:
        session_id (str): Session ID to remove from blacklist
    """
    global _blacklisted_sessions
    _blacklisted_sessions.discard(session_id)
    current_app.logger.info(f"Session {session_id} removed from blacklist")


def log_admin_action(action_type, description, target_type=None, target_id=None,
                    target_description=None, old_values=None, new_values=None,
                    risk_level='low', country_id=None, country_name=None):
    """
    Log an administrative action.

    Args:
        action_type (str): Type of admin action
        description (str): Description of the action
        target_type (str): Type of target object (e.g., 'user', 'form')
        target_id (int): ID of the target object
        target_description (str): Description of the target
        old_values (dict): Previous values before change
        new_values (dict): New values after change
        risk_level (str): Risk level of the action
        country_id (int): Optional country ID associated with this action
        country_name (str): Optional country name (looked up automatically if country_id is provided)
    """
    from app.services.authorization_service import AuthorizationService
    if not current_user.is_authenticated or not AuthorizationService.is_admin(current_user):
        return

    try:
        client_info = get_client_info()

        # Inject country info into new_values so extract_country_info can find it
        if country_id:
            if new_values is None:
                new_values = {}
            new_values = dict(new_values)
            new_values['country_id'] = country_id
            if country_name:
                new_values['country_name'] = country_name
            elif not new_values.get('country_name'):
                try:
                    from app.models import Country
                    country = Country.query.get(int(country_id))
                    if country:
                        new_values['country_name'] = country.name
                except Exception:
                    pass

        admin_log = AdminActionLog(
            admin_user_id=current_user.id,
            action_type=action_type,
            action_description=description,
            target_type=target_type,
            target_id=target_id,
            target_description=target_description,
            ip_address=client_info['ip_address'],
            user_agent=client_info['user_agent'],
            endpoint=request.endpoint,
            old_values=old_values,
            new_values=new_values,
            risk_level=risk_level,
            requires_review=(risk_level in ['high', 'critical'])
        )

        db.session.add(admin_log)
        _commit_or_flush()

        # Create security event for high-risk actions
        if risk_level in ['high', 'critical']:
            create_security_event(
                event_type='high_risk_admin_action',
                severity=risk_level,
                description=f"High-risk admin action: {description}",
                context_data={'admin_action_id': admin_log.id}
            )

    except Exception as e:
        current_app.logger.error(f"Error logging admin action: {str(e)}")
        _rollback_transaction("log_admin_action_error")


def create_security_event(event_type, severity, description, context_data=None, user_id: Optional[int] = None):
    """
    Create a security event.

    Args:
        event_type (str): Type of security event
        severity (str): Severity level
        description (str): Description of the event
        context_data (dict): Additional context data
        user_id (int, optional): Associated user ID (overrides current_user)
    """
    try:
        client_info = get_client_info()

        security_event = SecurityEvent(
            user_id=user_id if user_id is not None else (current_user.id if current_user.is_authenticated else None),
            event_type=event_type,
            severity=severity,
            description=description,
            ip_address=client_info['ip_address'],
            user_agent=client_info['user_agent'],
            context_data=context_data
        )

        db.session.add(security_event)
        _commit_or_flush()

    except Exception as e:
        current_app.logger.error(f"Error creating security event: {str(e)}")
        _rollback_transaction("create_security_event_error")


def _ipv4_subnet(ip, prefix_octets=3):
    """Return the first *prefix_octets* octets of an IPv4 address as a string.

    Returns ``None`` for non-IPv4 or malformed addresses.
    """
    if not ip or ':' in ip:
        return None
    parts = ip.split('.')
    if len(parts) != 4:
        return None
    return '.'.join(parts[:prefix_octets])


def check_suspicious_login(ip_address, email, success):
    """Check if a login attempt appears suspicious.

    Returns:
        str or None: Human-readable reason if suspicious, ``None`` otherwise.
        The caller can treat a truthy return as ``is_suspicious=True``.
    """
    one_hour_ago = utcnow() - timedelta(hours=1)

    # Rule 1 — Brute force: ≥ 5 failed attempts from the same IP in the last hour
    recent_failures = UserLoginLog.query.filter(
        and_(
            UserLoginLog.ip_address == ip_address,
            UserLoginLog.event_type == 'login_failed',
            UserLoginLog.timestamp > one_hour_ago,
        )
    ).count()

    if recent_failures >= 5:
        return f'brute_force: {recent_failures} failed attempts from this IP in the last hour'

    # Rule 2 — Credential stuffing: ≥ 10 distinct emails tried from same IP in the last hour
    recent_emails = db.session.query(
        func.count(func.distinct(UserLoginLog.email_attempted))
    ).filter(
        and_(
            UserLoginLog.ip_address == ip_address,
            UserLoginLog.timestamp > one_hour_ago,
        )
    ).scalar()

    if recent_emails >= 10:
        return f'credential_stuffing: {recent_emails} different emails from this IP in the last hour'

    # Rule 3 — New network on a successful login.
    #
    # To avoid flooding alerts for users with dynamic IPs or multiple
    # offices, the check:
    #   a) requires ≥ 3 previous successful logins (need enough history to
    #      establish a baseline),
    #   b) compares at IPv4 /24 subnet level so minor IP changes within
    #      the same ISP block are tolerated.
    if success:
        user = User.query.filter_by(email=email).first()
        if user:
            previous_ips = db.session.query(
                func.distinct(UserLoginLog.ip_address)
            ).filter(
                and_(
                    UserLoginLog.user_id == user.id,
                    UserLoginLog.event_type == 'login_success',
                    UserLoginLog.timestamp > utcnow() - timedelta(days=30),
                )
            ).all()

            previous_ip_list = [row[0] for row in previous_ips if row[0]]

            if len(previous_ip_list) >= 3:
                current_subnet = _ipv4_subnet(ip_address)
                if current_subnet:
                    known_subnets = {_ipv4_subnet(ip) for ip in previous_ip_list}
                    known_subnets.discard(None)
                    if current_subnet not in known_subnets:
                        return (
                            f'new_network: IP {ip_address} is outside all previously '
                            f'seen /24 subnets ({len(known_subnets)} known subnets)'
                        )
                else:
                    if ip_address not in previous_ip_list:
                        return f'new_ip: {ip_address} not seen before (non-IPv4 comparison)'

    return None


def get_recent_failed_attempts(email, ip_address):
    """Get count of recent failed login attempts."""
    return UserLoginLog.query.filter(
        and_(
            or_(
                UserLoginLog.email_attempted == email,
                UserLoginLog.ip_address == ip_address
            ),
            UserLoginLog.event_type == 'login_failed',
            UserLoginLog.timestamp > utcnow() - timedelta(hours=1)
        )
    ).count()


def create_security_event_for_login(email, success, is_suspicious, client_info, failure_reason, suspicious_reason=None):
    """Create security events for login attempts."""
    if not success:
        failed_count = get_recent_failed_attempts(email, client_info['ip_address'])
        if failed_count >= 5:
            severity = 'high' if failed_count >= 10 else 'medium'
            create_security_event(
                event_type='multiple_failed_logins',
                severity=severity,
                description=f"Multiple failed login attempts for {email} from {client_info['ip_address']} (Reason: {failure_reason or 'Unknown'})",
                context_data={
                    'failed_count': failed_count,
                    'email': email,
                    'failure_reason': failure_reason,
                    'ip_address': client_info['ip_address']
                }
            )

    if is_suspicious:
        reason_label = suspicious_reason or failure_reason or 'unknown'
        outcome = 'successful' if success else 'failed'
        create_security_event(
            event_type='suspicious_login',
            severity='medium',
            description=f"Suspicious {outcome} login for {email} from {client_info['ip_address']} ({reason_label})",
            context_data={
                'email': email,
                'success': success,
                'failure_reason': failure_reason,
                'suspicious_reason': suspicious_reason,
                'ip_address': client_info['ip_address']
            }
        )


# Analytics and Reporting Functions

def get_user_login_analytics(user_id=None, days=30):
    """Get login analytics for a user or all users."""
    query = UserLoginLog.query.filter(
        UserLoginLog.timestamp > utcnow() - timedelta(days=days)
    )

    if user_id:
        query = query.filter(UserLoginLog.user_id == user_id)

    logs = query.all()

    analytics = {
        'total_logins': len([l for l in logs if l.event_type == 'login_success']),
        'failed_attempts': len([l for l in logs if l.event_type == 'login_failed']),
        'unique_ips': len(set(l.ip_address for l in logs)),
        'suspicious_attempts': len([l for l in logs if l.is_suspicious]),
        'device_breakdown': {},
        'browser_breakdown': {},
        'daily_activity': {}
    }

    # Device and browser breakdowns
    for log in logs:
        if log.device_type:
            # Normalize device type to ensure consistency (capitalize first letter)
            device_type = log.device_type.lower().capitalize() if log.device_type else 'Unknown'
            analytics['device_breakdown'][device_type] = analytics['device_breakdown'].get(device_type, 0) + 1
        if log.browser:
            analytics['browser_breakdown'][log.browser] = analytics['browser_breakdown'].get(log.browser, 0) + 1

    # Daily activity
    for log in logs:
        date_key = log.timestamp.strftime('%Y-%m-%d')
        if date_key not in analytics['daily_activity']:
            analytics['daily_activity'][date_key] = {'logins': 0, 'failures': 0}

        if log.event_type == 'login_success':
            analytics['daily_activity'][date_key]['logins'] += 1
        else:
            analytics['daily_activity'][date_key]['failures'] += 1

    return analytics


def get_user_activity_analytics(user_id=None, days=30):
    """Get activity analytics for a user or all users."""
    query = UserActivityLog.query.filter(
        UserActivityLog.timestamp > utcnow() - timedelta(days=days)
    )

    if user_id:
        query = query.filter(UserActivityLog.user_id == user_id)

    logs = query.all()

    analytics = {
        'total_activities': len(logs),
        'activity_breakdown': {},
        'daily_activity': {},
        'popular_pages': {},
        'average_response_time': 0
    }

    response_times = []

    for log in logs:
        # Activity type breakdown
        analytics['activity_breakdown'][log.activity_type] = analytics['activity_breakdown'].get(log.activity_type, 0) + 1

        # Daily activity
        date_key = log.timestamp.strftime('%Y-%m-%d')
        analytics['daily_activity'][date_key] = analytics['daily_activity'].get(date_key, 0) + 1

        # Popular pages
        if log.url_path:
            analytics['popular_pages'][log.url_path] = analytics['popular_pages'].get(log.url_path, 0) + 1

        # Response times
        if log.response_time_ms:
            response_times.append(log.response_time_ms)

    if response_times:
        analytics['average_response_time'] = sum(response_times) / len(response_times)

    return analytics


PAGE_PATH_ANALYTICS_DISPLAY_LIMIT = 500


def merge_page_view_path_histograms(
    session_histograms: List[Optional[Dict[str, Any]]],
) -> Tuple[Dict[str, int], Dict[str, int]]:
    """
    Merge per-session ``page_view_path_counts`` JSON dicts.

    Returns:
        total_views: path key -> sum of counts across sessions
        session_hits: path key -> number of sessions where that key had count > 0
    """
    total_views: Dict[str, int] = defaultdict(int)
    session_hits: Dict[str, int] = defaultdict(int)

    for raw in session_histograms:
        if not isinstance(raw, dict):
            continue
        seen_in_session = set()
        for k, v in raw.items():
            key = str(k) if k is not None else ""
            try:
                n = int(v)
            except (TypeError, ValueError):
                n = 0
            if n <= 0:
                continue
            total_views[key] += n
            if key not in seen_in_session:
                seen_in_session.add(key)
                session_hits[key] += 1

    return dict(total_views), dict(session_hits)


def aggregate_page_view_path_histogram(
    *,
    user_id: Optional[int] = None,
    days: int = 30,
    path_prefix: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Aggregate ``UserSessionLog.page_view_path_counts`` across sessions in a time window.

    Uses ``session_start >= utcnow() - days`` (same window as user analytics).

    Args:
        user_id: If set, only sessions for this user.
        days: Lookback days (clamped 1..3660).
        path_prefix: If set, only include path keys whose lowercase string startswith this
            (stripped, compared case-insensitively).

    Returns:
        paths: sorted list of {path, total_views, session_hits}
        sessions_in_scope: session rows counted
        period: {days, from_iso, to_iso}
        distinct_path_count: len(paths)
    """
    try:
        inspector = inspect(db.engine)
        if not inspector.has_table(UserSessionLog.__tablename__):
            return _empty_page_path_histogram(days)

        d = max(1, min(int(days or 30), 3660))
        from_dt = utcnow() - timedelta(days=d)

        q = db.session.query(UserSessionLog.page_view_path_counts).filter(
            UserSessionLog.session_start >= from_dt
        )
        if user_id is not None:
            q = q.filter(UserSessionLog.user_id == int(user_id))

        histograms: List[Optional[Dict[str, Any]]] = []
        sessions_in_scope = 0
        for (pvc,) in q.yield_per(500):
            sessions_in_scope += 1
            histograms.append(pvc if isinstance(pvc, dict) else None)

        total_views, session_hits = merge_page_view_path_histograms(histograms)

        prefix = (path_prefix or "").strip().lower()
        if prefix:
            keys = [k for k in total_views if str(k).lower().startswith(prefix)]
        else:
            keys = list(total_views.keys())

        paths: List[Dict[str, Any]] = []
        for key in keys:
            tv = total_views.get(key, 0)
            sh = session_hits.get(key, 0)
            paths.append(
                {
                    "path": key,
                    "total_views": int(tv),
                    "session_hits": int(sh),
                }
            )
        paths.sort(key=lambda row: (-row["total_views"], row["path"]))

        now = utcnow()
        return {
            "paths": paths,
            "sessions_in_scope": sessions_in_scope,
            "period": {
                "days": d,
                "from_iso": from_dt.isoformat(),
                "to_iso": now.isoformat(),
            },
            "distinct_path_count": len(paths),
            "display_limit": PAGE_PATH_ANALYTICS_DISPLAY_LIMIT,
        }
    except Exception as e:
        current_app.logger.error("aggregate_page_view_path_histogram: %s", e)
        return _empty_page_path_histogram(days)


def _empty_page_path_histogram(days: int) -> Dict[str, Any]:
    d = max(1, min(int(days or 30), 3660))
    from_dt = utcnow() - timedelta(days=d)
    now = utcnow()
    return {
        "paths": [],
        "sessions_in_scope": 0,
        "period": {
            "days": d,
            "from_iso": from_dt.isoformat(),
            "to_iso": now.isoformat(),
        },
        "distinct_path_count": 0,
        "display_limit": PAGE_PATH_ANALYTICS_DISPLAY_LIMIT,
    }


def format_page_path_histogram_csv(paths: List[Dict[str, Any]]) -> str:
    """CSV text for path, total_views, session_hits (UTF-8 with header)."""
    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(["path", "total_views", "sessions_with_path"])
    for row in paths:
        w.writerow(
            [
                row.get("path", ""),
                row.get("total_views", 0),
                row.get("session_hits", 0),
            ]
        )
    return buf.getvalue()


def get_security_events_summary(days=30):
    """
    Get a summary of security events for the past N days.

    Args:
        days (int): Number of days to look back

    Returns:
        dict: Summary statistics
    """
    cutoff_date = utcnow() - timedelta(days=days)

    try:
        events = SecurityEvent.query.filter(
            SecurityEvent.timestamp >= cutoff_date
        ).all()

        # Group events by severity and type
        severity_counts = {}
        type_counts = {}

        for event in events:
            severity_counts[event.severity] = severity_counts.get(event.severity, 0) + 1
            type_counts[event.event_type] = type_counts.get(event.event_type, 0) + 1

        return {
            'total_events': len(events),
            'severity_breakdown': severity_counts,
            'type_breakdown': type_counts,
            'unresolved_events': len([e for e in events if not e.is_resolved]),
            'high_severity_events': len([e for e in events if e.severity in ['high', 'critical']])
        }

    except Exception as e:
        current_app.logger.error(f"Error getting security events summary: {str(e)}")
        return {}


def cleanup_inactive_sessions(inactivity_hours=None, max_session_hours=None):
    """
    Clean up inactive sessions and sessions that have exceeded maximum duration.

    Each browser / device login creates a separate UserSessionLog row (same user_id can
    have several is_active=True rows until logout or cleanup). This does not enforce
    a single session per user account.

    Args:
        inactivity_hours (int): Hours of inactivity before session is considered stale
        max_session_hours (int): Maximum session duration in hours
    """
    lock_conn = None
    lock_acquired = False
    lock_id = None
    try:
        from config import Config
        from flask import current_app

        inspector = inspect(db.engine)
        table_name = UserSessionLog.__tablename__

        if not inspector.has_table(table_name):
            current_app.logger.info(f"Skipping session cleanup - table '{table_name}' not created yet")
            return 0

        lock_id = int(current_app.config.get('SESSION_CLEANUP_LOCK_ID', DEFAULT_SESSION_CLEANUP_LOCK_ID))

        # PostgreSQL advisory lock avoids duplicate cleanup across workers; SQLite etc. skip the lock.
        dialect = db.engine.dialect.name
        if dialect == "postgresql":
            lock_conn = db.engine.connect()
            lock_acquired = bool(
                lock_conn.execute(
                    text("SELECT pg_try_advisory_lock(:lock_id)"),
                    {"lock_id": lock_id},
                ).scalar()
            )
            if not lock_acquired:
                current_app.logger.info("Skipping session cleanup - another worker is running cleanup")
                lock_conn.close()
                lock_conn = None
                return 0

        # Use config values if not provided
        if inactivity_hours is None:
            inactivity_hours = Config.SESSION_INACTIVITY_TIMEOUT.total_seconds() / 3600
        if max_session_hours is None:
            max_session_hours = Config.PERMANENT_SESSION_LIFETIME.total_seconds() / 3600

        inactivity_cutoff = utcnow() - timedelta(hours=inactivity_hours)
        max_duration_cutoff = utcnow() - timedelta(hours=max_session_hours)

        # Find sessions to expire due to inactivity
        inactive_sessions = UserSessionLog.query.filter(
            and_(
                UserSessionLog.is_active == True,
                UserSessionLog.last_activity < inactivity_cutoff
            )
        ).all()

        # Find sessions that have exceeded maximum duration
        long_sessions = UserSessionLog.query.filter(
            and_(
                UserSessionLog.is_active == True,
                UserSessionLog.session_start < max_duration_cutoff
            )
        ).all()

        # Combine and deduplicate sessions to close
        sessions_to_close = set(inactive_sessions + long_sessions)

        count = 0
        for session_log in sessions_to_close:
            session_log.session_end = utcnow()
            session_log.is_active = False

            # Determine why session was ended
            if session_log in inactive_sessions and session_log in long_sessions:
                session_log.ended_by = 'timeout_and_max_duration'
            elif session_log in inactive_sessions:
                session_log.ended_by = 'inactivity_timeout'
            else:
                session_log.ended_by = 'max_duration_exceeded'

            # Calculate duration
            # Ensure both datetimes are timezone-aware to avoid subtraction errors
            session_end_aware = ensure_utc(session_log.session_end)
            session_start_aware = ensure_utc(session_log.session_start)
            duration = session_end_aware - session_start_aware
            session_log.duration_minutes = int(duration.total_seconds() / 60)

            count += 1

        if count > 0:
            _commit_or_flush()
            current_app.logger.info(f"Cleaned up {count} inactive/expired sessions")

        return count

    except Exception as e:
        current_app.logger.error(f"Error cleaning up inactive sessions: {str(e)}")
        _rollback_transaction("cleanup_inactive_sessions_error")
        return 0
    finally:
        if lock_conn is not None:
            try:
                if lock_acquired and lock_id is not None and db.engine.dialect.name == "postgresql":
                    lock_conn.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id})
            except Exception as unlock_error:
                current_app.logger.warning(f"Failed to release session cleanup lock: {unlock_error}")
            finally:
                lock_conn.close()


def get_active_sessions_count():
    """Get the count of currently active sessions."""
    try:
        return UserSessionLog.query.filter(UserSessionLog.is_active == True).count()
    except Exception as e:
        current_app.logger.error(f"Error getting active sessions count: {str(e)}")
        return 0


def get_session_analytics(days=30):
    """
    Get session analytics for the past N days.

    Args:
        days (int): Number of days to analyze

    Returns:
        dict: Session analytics data
    """
    try:
        cutoff_date = utcnow() - timedelta(days=days)

        sessions = UserSessionLog.query.filter(
            UserSessionLog.session_start >= cutoff_date
        ).all()

        if not sessions:
            return {
                'total_sessions': 0,
                'active_sessions': 0,
                'average_duration': 0,
                'total_page_views': 0,
                'sessions_by_day': [],
                'duration_distribution': {}
            }

        # Calculate metrics
        total_sessions = len(sessions)
        active_sessions = len([s for s in sessions if s.is_active])

        # Average duration (only for completed sessions)
        completed_sessions = [s for s in sessions if s.duration_minutes is not None]
        avg_duration = sum(s.duration_minutes for s in completed_sessions) / len(completed_sessions) if completed_sessions else 0

        # Total page views
        total_page_views = sum(s.page_views or 0 for s in sessions)

        # Sessions by day
        sessions_by_day = {}
        for session in sessions:
            day = session.session_start.date()
            sessions_by_day[day] = sessions_by_day.get(day, 0) + 1

        # Duration distribution
        duration_ranges = {
            '0-15 min': 0,
            '15-30 min': 0,
            '30-60 min': 0,
            '1-2 hours': 0,
            '2-4 hours': 0,
            '4+ hours': 0
        }

        for session in completed_sessions:
            duration = session.duration_minutes
            if duration <= 15:
                duration_ranges['0-15 min'] += 1
            elif duration <= 30:
                duration_ranges['15-30 min'] += 1
            elif duration <= 60:
                duration_ranges['30-60 min'] += 1
            elif duration <= 120:
                duration_ranges['1-2 hours'] += 1
            elif duration <= 240:
                duration_ranges['2-4 hours'] += 1
            else:
                duration_ranges['4+ hours'] += 1

        return {
            'total_sessions': total_sessions,
            'active_sessions': active_sessions,
            'average_duration': round(avg_duration, 1),
            'total_page_views': total_page_views,
            'sessions_by_day': sorted(sessions_by_day.items()),
            'duration_distribution': duration_ranges
        }

    except Exception as e:
        current_app.logger.error(f"Error getting session analytics: {str(e)}")
        return {}
