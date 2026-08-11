"""
Platform Error Logging API endpoint.
Part of the /api/v1 blueprint.

This endpoint allows Azure platform error pages and the client reporter (403, 502, 503, 504) to log errors
for monitoring and debugging purposes. Client-side JavaScript runtime errors are accepted at
``/api/v1/client-error`` (see ``log_client_error``).

SECURITY: This endpoint is public but protected by:
- Rate limiting (10 requests per minute per IP) via Flask-Limiter
- Input validation and sanitization
- Length limits on all inputs
- No sensitive data exposure
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from flask import current_app, request
from app.utils.api_helpers import get_json_safe
from app.utils.api_responses import json_bad_request, json_error, json_ok, json_server_error
from app.utils.constants import (
    MAX_CLIENT_ERROR_MESSAGE_CHARS,
    MAX_CLIENT_ERROR_SOURCE_CHARS,
    MAX_CLIENT_ERROR_STACK_CHARS,
    MAX_ERROR_LOG_REQUEST_BYTES,
)

# Import the API blueprint from parent
from app.routes.api import api_bp

# Import utilities
from app.services.security.monitoring import SecurityMonitor
from app.services.platform.user_analytics_service import get_client_ip
from app.services.monitoring.platform_error_diagnostics import (
    attach_platform_5xx_diagnostics,
    is_platform_5xx,
)
from app.services.monitoring.worker_investigation import (
    log_worker_recovery,
    schedule_504_investigation,
)
from app.extensions import limiter
from app.utils.datetime_helpers import utcnow

PLATFORM_ERROR_DIAGNOSTICS_MAX_CONTEXT_BYTES = 12000

# Platform 5xx errors are client-reported and can burst heavily during an
# incident (many browser tabs/users hitting the same outage simultaneously).
# Each report already creates a SecurityEvent row; without a cooldown, each
# one would ALSO trigger a separate admin alert email (RBAC lookup + a
# background thread blocking on the mail API for up to its timeout). Cap
# email alerts to at most one per event type per window; the DB record and
# CRITICAL log line are still written for every report. See the 2026-07-22
# platform-502 + email-timeout incident.
PLATFORM_ERROR_ALERT_COOLDOWN_SECONDS = int(
    os.environ.get('PLATFORM_ERROR_ALERT_COOLDOWN_SECONDS', '600')
)

CLIENT_ERROR_IGNORED_MESSAGE_FRAGMENTS = (
    'AbortError',
    'message channel closed before a response was received',
    'ResizeObserver loop limit exceeded',
    'ResizeObserver loop completed with undelivered notifications',
    'Non-Error promise rejection captured',
)

CLIENT_ERROR_IGNORED_SOURCE_PREFIXES = (
    'chrome-extension://',
    'moz-extension://',
    'safari-extension://',
    'safari-web-extension://',
)


def _strip_control_chars(value: Optional[str], *, max_len: int) -> Optional[str]:
    """Remove control characters to reduce log-forging risk."""
    if not value:
        return None
    s = str(value)
    # Remove common control chars; keep printable ASCII/Unicode as-is.
    s = s.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    s = s.strip()
    if not s:
        return None
    return s[:max_len]


def sanitize_url(url):
    """Sanitize URL to remove sensitive query parameters and validate length."""
    url = _strip_control_chars(url, max_len=2000)
    if not url:
        return None

    # Remove common sensitive parameters
    sensitive_params = ['password', 'token', 'api_key', 'secret', 'auth', 'key', 'session', 'cookie']
    try:
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

        # Validate URL format
        parsed = urlparse(url)
        # Only accept http(s) URLs (these should come from window.location.href)
        if parsed.scheme and parsed.scheme.lower() not in ("http", "https"):
            return None
        if not parsed.scheme and not parsed.netloc and not parsed.path:
            # Invalid URL format, return None
            return None

        params = parse_qs(parsed.query)

        # Remove sensitive parameters
        cleaned_params = {k: v for k, v in params.items()
                         if not any(sensitive in k.lower() for sensitive in sensitive_params)}

        # Rebuild URL without sensitive params
        new_query = urlencode(cleaned_params, doseq=True)
        cleaned = parsed._replace(query=new_query)
        sanitized = urlunparse(cleaned)

        # Final length check
        return sanitized[:2000] if len(sanitized) > 2000 else sanitized
    except Exception as e:
        # If parsing fails, return None (don't log potentially malicious URLs)
        current_app.logger.warning("Failed to sanitize URL (first 100 chars): %s: %s", url[:100], e)
        return None


def sanitize_client_error_text(value, *, max_len: int) -> Optional[str]:
    """Sanitize free-text client error fields (message, stack)."""
    return _strip_control_chars(value, max_len=max_len)


def sanitize_client_error_source(value) -> Optional[str]:
    """Sanitize script URL / filename from the browser."""
    text = sanitize_client_error_text(value, max_len=MAX_CLIENT_ERROR_SOURCE_CHARS)
    if not text:
        return None
    lowered = text.lower()
    for prefix in CLIENT_ERROR_IGNORED_SOURCE_PREFIXES:
        if lowered.startswith(prefix):
            return None
    return text


def should_ignore_client_error(
    *,
    message: Optional[str],
    source: Optional[str] = None,
    kind: Optional[str] = None,
) -> bool:
    """Drop known-noise client errors before creating SecurityEvent rows."""
    msg = sanitize_client_error_text(message, max_len=MAX_CLIENT_ERROR_MESSAGE_CHARS)
    if not msg:
        return True

    if msg == 'Script error.' and not source:
        return True

    for fragment in CLIENT_ERROR_IGNORED_MESSAGE_FRAGMENTS:
        if fragment in msg:
            return True

    if kind == 'resource' and not msg:
        return True

    return False


def build_client_error_fingerprint(
    *,
    kind: str,
    message: Optional[str],
    source: Optional[str],
    line_no: Optional[int],
) -> str:
    """Stable key for deduplicating the same JS error within a UTC calendar day."""
    return '|'.join([
        kind or 'error',
        message or '',
        source or 'unknown',
        str(line_no if line_no is not None else ''),
    ])


def client_error_already_logged_today(fingerprint: str) -> bool:
    """Return True when an identical client JS error was already stored today (UTC)."""
    from app.models import SecurityEvent

    start_of_day = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (
        SecurityEvent.query
        .filter(
            SecurityEvent.event_type == 'client_javascript_error',
            SecurityEvent.timestamp >= start_of_day,
        )
        .with_entities(SecurityEvent.context_data)
        .all()
    )
    for (context_data,) in rows:
        if isinstance(context_data, dict) and context_data.get('fingerprint') == fingerprint:
            return True
    return False


@api_bp.route('/platform-error', methods=['POST'])
@limiter.limit("10 per minute", override_defaults=True)
def log_platform_error():
    """
    Log platform-level errors (403, 502, 503, 504) from Azure error pages or the client reporter.

    This endpoint is intentionally public (no auth required) since it's called
    from static error pages and fetch/ajax interceptors. Rate limiting should be handled at the infrastructure level.

    Expected JSON payload:
    {
        "error_code": 403|502|503|504,
        "url": "full URL where error occurred",
        "referrer": "referrer URL (optional)",
        "user_agent": "browser user agent (optional)",
        "timestamp": "ISO timestamp (optional)",
        "probe_delay_s": float (optional) — present only in JS recovery probes, not initial reports
    }

    When error_code is 504 and probe_delay_s is absent, a background investigation
    thread is started that re-snapshots worker state after a short delay and logs a
    [WORKER_INVESTIGATION] verdict.

    When probe_delay_s is present (JS recovery probe at T+5s / T+15s), the request
    is handled as a lightweight recovery confirmation and does not create a security event.

    Returns:
        JSON response with success status
    """
    import time as _time
    import json as json_lib

    received_at = _time.time()

    try:
        # Validate Content-Type
        content_type = request.headers.get('Content-Type', '')
        if not content_type.startswith('application/json'):
            return json_bad_request('Content-Type must be application/json', success=False)

        # Get JSON data with size limit
        if request.content_length and request.content_length > MAX_ERROR_LOG_REQUEST_BYTES:
            return json_error('Request payload too large', 413, success=False)

        data = get_json_safe()

        # Validate error code (must be integer)
        error_code = data.get('error_code')
        try:
            error_code = int(error_code)
        except (ValueError, TypeError):
            return json_bad_request('Invalid error_code. Must be an integer.', success=False)

        if error_code not in [403, 502, 503, 504]:
            return json_bad_request('Invalid error_code. Must be 403, 502, 503, or 504.', success=False)

        # Extract and sanitize URL (with length limits)
        url = sanitize_url(data.get('url'))
        referrer = sanitize_url(data.get('referrer'))

        # Validate and limit user agent length
        user_agent = _strip_control_chars(data.get('user_agent'), max_len=500) or ""

        # Validate timestamp format if provided
        timestamp = data.get('timestamp')
        if timestamp:
            try:
                # Validate ISO format
                datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                timestamp = None  # Invalid timestamp, ignore it

        # ── Recovery probe fast-path ───────────────────────────────────────────
        # JS sends follow-up beacons at T+5s and T+15s with probe_delay_s set.
        # These are cheap confirmations ("a worker is alive now") and do not
        # create a security event or start a new investigation.
        raw_probe_delay = data.get('probe_delay_s')
        if raw_probe_delay is not None and error_code == 504:
            try:
                probe_delay_s = float(raw_probe_delay)
            except (TypeError, ValueError):
                probe_delay_s = 0.0
            app = current_app._get_current_object()
            log_worker_recovery(
                app,
                url=url,
                probe_delay_s=probe_delay_s,
                reported_at=received_at - probe_delay_s if probe_delay_s > 0 else None,
            )
            return json_ok(success=True, message='Recovery probe logged')

        # Get client IP using utility function (handles proxies correctly)
        ip_address = get_client_ip() or 'unknown'

        # Map error codes to event types and severity
        error_mapping = {
            403: ('platform_403_forbidden', 'high'),
            502: ('platform_502_bad_gateway', 'high'),
            503: ('platform_503_service_unavailable', 'high'),
            504: ('platform_504_gateway_timeout', 'high'),
        }

        event_type, severity = error_mapping[error_code]

        # Prepare context data (all values sanitized and length-limited)
        context_data = {
            'url': url or 'unknown',
            'referrer': referrer or 'none',
            'user_agent': user_agent or 'unknown',
            'platform': 'azure_app_service',
            'source': 'client_reporter',
        }

        if timestamp:
            context_data['client_timestamp'] = timestamp

        diagnostics_summary = ''
        if is_platform_5xx(error_code):
            failed_path = url or 'unknown'
            context_data = attach_platform_5xx_diagnostics(
                context_data,
                error_code=error_code,
                failed_url=failed_path,
                max_json_bytes=PLATFORM_ERROR_DIAGNOSTICS_MAX_CONTEXT_BYTES,
            )
            diagnostics_summary = context_data.get('diagnostics_summary', '') or ''

        # Additional validation: ensure context_data doesn't exceed reasonable size
        context_json = json_lib.dumps(context_data, default=str)
        if len(context_json) > PLATFORM_ERROR_DIAGNOSTICS_MAX_CONTEXT_BYTES:
            # Truncate user_agent if needed
            max_ua_length = 500 - (len(context_json) - len(user_agent))
            if max_ua_length > 0:
                context_data['user_agent'] = user_agent[:max_ua_length]
            else:
                context_data['user_agent'] = 'truncated'
            context_data['context_truncated'] = True

        description = f'Platform error {error_code} occurred at {url or "unknown URL"}'
        if diagnostics_summary:
            description = f'{description}. {diagnostics_summary}'
        description = description[:500]

        # Log to SecurityMonitor (creates database record)
        # Note: Database writes are protected by rate limiting above
        try:
            SecurityMonitor.log_security_event(
                event_type=event_type,
                severity=severity,
                description=description,
                context_data=context_data,
                user_id=None,  # resolved from session when the reporter is authenticated
                alert_cooldown_seconds=PLATFORM_ERROR_ALERT_COOLDOWN_SECONDS,
            )
        except Exception as log_error:
            # If database logging fails, still log to application logs
            # This prevents database issues from breaking error logging entirely
            current_app.logger.error(
                f"Failed to log platform error to database: {log_error}",
                extra={'error_code': error_code, 'url': url[:200] if url else None, 'ip': ip_address}
            )

        # Also log to application logger for immediate visibility
        log_message = (
            f"Platform Error {error_code}: {url or 'unknown URL'} "
            f"(IP: {ip_address}, Referrer: {referrer or 'none'})"
        )
        if diagnostics_summary:
            log_message = f"{log_message} | {diagnostics_summary}"
        current_app.logger.warning(log_message)

        # ── 504-specific: deferred worker investigation ────────────────────────
        # Start a background thread that re-snapshots worker state after
        # _DELAY_SECONDS and logs a [WORKER_INVESTIGATION] verdict explaining
        # why no worker was available at the time of the timeout.
        if error_code == 504:
            try:
                app = current_app._get_current_object()
                schedule_504_investigation(app, url=url, reported_at=received_at)
            except Exception as exc:
                current_app.logger.warning(
                    'Could not schedule 504 worker investigation: %s', exc
                )

        return json_ok(success=True, message='Error logged successfully')

    except Exception as e:
        # Log the error but don't expose details to client
        current_app.logger.error(f"Error in platform error logging endpoint: {e}", exc_info=True)
        return json_server_error('Failed to log error', success=False)


@api_bp.route('/client-error', methods=['POST'])
@limiter.limit("30 per minute", override_defaults=True)
def log_client_error():
    """
    Log client-side JavaScript runtime errors for monitoring.

    Called from platform-error-reporter.js via window.onerror and
    unhandledrejection handlers. Intentionally public (no auth) with rate
    limiting; does not send admin alert emails; deduplicates identical errors per UTC day.

    Expected JSON payload:
    {
        "kind": "error" | "unhandledrejection",
        "message": "ReferenceError: ...",
        "source": "https://.../manage-assignment.js" (optional),
        "line": 1776 (optional),
        "column": 12 (optional),
        "stack": "..." (optional),
        "url": "page URL where error occurred",
        "referrer": "..." (optional),
        "user_agent": "..." (optional),
        "timestamp": "ISO timestamp" (optional)
    }
    """
    try:
        content_type = request.headers.get('Content-Type', '')
        if not content_type.startswith('application/json'):
            return json_bad_request('Content-Type must be application/json', success=False)

        if request.content_length and request.content_length > MAX_ERROR_LOG_REQUEST_BYTES:
            return json_error('Request payload too large', 413, success=False)

        data = get_json_safe()

        kind = sanitize_client_error_text(data.get('kind'), max_len=40) or 'error'
        if kind not in {'error', 'unhandledrejection'}:
            return json_bad_request('Invalid kind. Must be "error" or "unhandledrejection".', success=False)

        message = sanitize_client_error_text(data.get('message'), max_len=MAX_CLIENT_ERROR_MESSAGE_CHARS)
        source = sanitize_client_error_source(data.get('source'))
        stack = sanitize_client_error_text(data.get('stack'), max_len=MAX_CLIENT_ERROR_STACK_CHARS)
        url = sanitize_url(data.get('url'))
        referrer = sanitize_url(data.get('referrer'))
        user_agent = _strip_control_chars(data.get('user_agent'), max_len=500) or ""

        if should_ignore_client_error(message=message, source=source, kind=kind):
            return json_ok(success=True, message='Ignored client error')

        line_no = data.get('line')
        column_no = data.get('column')
        try:
            line_no = int(line_no) if line_no is not None else None
        except (TypeError, ValueError):
            line_no = None
        try:
            column_no = int(column_no) if column_no is not None else None
        except (TypeError, ValueError):
            column_no = None

        fingerprint = build_client_error_fingerprint(
            kind=kind,
            message=message,
            source=source,
            line_no=line_no,
        )
        if client_error_already_logged_today(fingerprint):
            return json_ok(success=True, message='Duplicate client error suppressed')

        timestamp = data.get('timestamp')
        if timestamp:
            try:
                datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                timestamp = None

        ip_address = get_client_ip() or 'unknown'

        context_data = {
            'kind': kind,
            'message': message,
            'source': source or 'unknown',
            'line': line_no,
            'column': column_no,
            'stack': stack or '',
            'url': url or 'unknown',
            'referrer': referrer or 'none',
            'user_agent': user_agent or 'unknown',
            'platform': 'browser',
            'reporter': 'client_reporter',
            'fingerprint': fingerprint,
        }
        if timestamp:
            context_data['client_timestamp'] = timestamp

        description = message[:500]
        if source and line_no is not None:
            description = f'{description} ({source}:{line_no})'
        description = description[:500]

        try:
            SecurityMonitor.log_security_event(
                event_type='client_javascript_error',
                severity='low',
                description=description,
                context_data=context_data,
                user_id=None,
                notify_admins=False,
            )
        except Exception as log_error:
            current_app.logger.error(
                "Failed to log client JavaScript error to database: %s",
                log_error,
                extra={'client_message': message[:200], 'url': (url or '')[:200], 'ip': ip_address},
            )

        current_app.logger.warning(
            "Client JavaScript error: %s (page: %s, IP: %s)",
            description,
            url or 'unknown',
            ip_address,
        )

        return json_ok(success=True, message='Error logged successfully')

    except Exception as e:
        current_app.logger.error("Error in client error logging endpoint: %s", e, exc_info=True)
        return json_server_error('Failed to log error', success=False)
