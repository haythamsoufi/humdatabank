"""
User Analytics and Activity Logging Utilities

This module provides functions for tracking user activities, login attempts,
session analytics, and security events for the platform.
"""

from datetime import datetime, timedelta
from typing import Optional
from flask import request, session, current_app, has_request_context, g
from flask_login import current_user
from sqlalchemy import and_, or_, func, inspect, text
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

    return {
        'ip_address': get_client_ip(),
        'user_agent': user_agent_string,
        'browser': browser_str,
        'operating_system': os_str,
        'device_type': get_device_type(user_agent)
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


def detect_bot_user_agent(user_agent_string):
    """
    Detect if the user agent appears to be from a bot or automated tool.

    Args:
        user_agent_string (str): User agent string from the request

    Returns:
        bool: True if bot is detected
    """
    if not user_agent_string:
        return True  # No user agent is suspicious

    user_agent_lower = user_agent_string.lower()

    # Common bot patterns
    bot_patterns = [
        'bot', 'crawler', 'spider', 'scraper', 'wget', 'curl',
        'python-requests', 'urllib', 'http', 'api', 'monitoring',
        'test', 'automation', 'script', 'tool', 'check',
        'postman', 'insomnia', 'httpie'
    ]

    # Check if any bot pattern is in the user agent
    for pattern in bot_patterns:
        if pattern in user_agent_lower:
            return True

    # Check for very short user agents (usually automated)
    if len(user_agent_string.strip()) < 10:
        return True

    # Check for missing typical browser indicators
    browser_indicators = ['mozilla', 'webkit', 'gecko', 'chrome', 'safari', 'firefox', 'edge']
    has_browser_indicator = any(indicator in user_agent_lower for indicator in browser_indicators)

    if not has_browser_indicator:
        return True

    return False


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
        update_session_activity(normalized_activity_type)

        _commit_or_flush()

    except Exception as e:
        current_app.logger.error(f"Error logging user activity: {str(e)}")
        _rollback_transaction("log_user_activity_error")


def _update_session_activity_explicit(session_id: Optional[str], activity_type: str) -> None:
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

        session_log.last_activity = utcnow()

        normalized_activity_type = normalize_activity_type(activity_type)

        if normalized_activity_type == 'page_view':
            session_log.page_views += 1
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
) -> None:
    """
    Log a user activity using a standalone transaction, without Flask request/current_user dependencies.
    Safe to call from response.call_on_close or background contexts.
    """
    if not user_id:
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
            _update_session_activity_explicit(session_id, normalized_activity_type)
    except Exception as e:
        current_app.logger.error(f"Error logging user activity (explicit): {str(e)}")


def log_user_activity_for_user(user_id, activity_type, description=None, context_data=None, response_time_ms=None, status_code=None):
    """
    Log an activity for a specific user ID, even if they are not the current session user.
    Useful for system-triggered events like account creation or password resets.
    """
    if not user_id:
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


def update_session_activity(activity_type):
    """
    Update session activity statistics.

    Args:
        activity_type (str): Type of activity performed
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

            if normalized_activity_type == 'page_view':
                session_log.page_views += 1
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


# Global set to store blacklisted session IDs for force logout
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

    Args:
        session_id (str): Session ID to check

    Returns:
        bool: True if session is blacklisted
    """
    global _blacklisted_sessions
    return session_id in _blacklisted_sessions


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
