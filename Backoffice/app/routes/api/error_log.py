"""
Platform Error Logging API endpoint.
Part of the /api/v1 blueprint.

This endpoint allows Azure platform error pages (403, 502, 503) to log errors
for monitoring and debugging purposes.

SECURITY: This endpoint is public but protected by:
- Rate limiting (10 requests per minute per IP) via Flask-Limiter
- Input validation and sanitization
- Length limits on all inputs
- No sensitive data exposure
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from flask import current_app, request
from app.utils.api_helpers import get_json_safe
from app.utils.api_responses import json_bad_request, json_error, json_ok, json_server_error
from app.utils.constants import MAX_ERROR_LOG_REQUEST_BYTES

# Import the API blueprint from parent
from app.routes.api import api_bp

# Import utilities
from app.services.security.monitoring import SecurityMonitor
from app.services.user_analytics_service import get_client_ip
from app.extensions import limiter


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


@api_bp.route('/platform-error', methods=['POST'])
@limiter.limit("10 per minute", override_defaults=True)
def log_platform_error():
    """
    Log platform-level errors (403, 502, 503) from Azure error pages.

    This endpoint is intentionally public (no auth required) since it's called
    from static error pages. Rate limiting should be handled at the infrastructure level.

    Expected JSON payload:
    {
        "error_code": 403|502|503,
        "url": "full URL where error occurred",
        "referrer": "referrer URL (optional)",
        "user_agent": "browser user agent (optional)",
        "timestamp": "ISO timestamp (optional)"
    }

    Returns:
        JSON response with success status
    """
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

        if error_code not in [403, 502, 503]:
            return json_bad_request('Invalid error_code. Must be 403, 502, or 503.', success=False)

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

        # Get client IP using utility function (handles proxies correctly)
        ip_address = get_client_ip() or 'unknown'

        # Map error codes to event types and severity
        error_mapping = {
            403: ('platform_403_forbidden', 'high'),
            502: ('platform_502_bad_gateway', 'high'),
            503: ('platform_503_service_unavailable', 'high')
        }

        event_type, severity = error_mapping[error_code]

        # Prepare context data (all values sanitized and length-limited)
        context_data = {
            'url': url or 'unknown',
            'referrer': referrer or 'none',
            'user_agent': user_agent or 'unknown',
            'platform': 'azure_app_service',
            'source': 'custom_error_page'
        }

        if timestamp:
            context_data['client_timestamp'] = timestamp

        # Additional validation: ensure context_data doesn't exceed reasonable size
        import json as json_lib
        context_json = json_lib.dumps(context_data)
        if len(context_json) > 2000:  # Limit total context size
            # Truncate user_agent if needed
            max_ua_length = 500 - (len(context_json) - len(user_agent))
            if max_ua_length > 0:
                context_data['user_agent'] = user_agent[:max_ua_length]
            else:
                context_data['user_agent'] = 'truncated'

        # Log to SecurityMonitor (creates database record)
        # Note: Database writes are protected by rate limiting above
        try:
            SecurityMonitor.log_security_event(
                event_type=event_type,
                severity=severity,
                description=f'Platform error {error_code} occurred at {url or "unknown URL"}'[:500],  # Limit description length
                context_data=context_data,
                user_id=None  # Platform errors don't have authenticated users
            )
        except Exception as log_error:
            # If database logging fails, still log to application logs
            # This prevents database issues from breaking error logging entirely
            current_app.logger.error(
                f"Failed to log platform error to database: {log_error}",
                extra={'error_code': error_code, 'url': url[:200] if url else None, 'ip': ip_address}
            )

        # Also log to application logger for immediate visibility
        current_app.logger.warning(
            f"Platform Error {error_code}: {url or 'unknown URL'} "
            f"(IP: {ip_address}, Referrer: {referrer or 'none'})"
        )

        return json_ok(success=True, message='Error logged successfully')

    except Exception as e:
        # Log the error but don't expose details to client
        current_app.logger.error(f"Error in platform error logging endpoint: {e}", exc_info=True)
        return json_server_error('Failed to log error', success=False)
