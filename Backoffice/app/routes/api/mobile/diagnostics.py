# Backoffice/app/routes/api/mobile/diagnostics.py
"""Client-reported failure diagnostics from the mobile app.

The app shows users a generic message when something fails on-device (for example
saving a form for offline use). This endpoint lets the app send the real error so
it can be read in the security-events list. Events are audit-only: low severity,
never emailed.
"""

from __future__ import annotations

import json
import re

from flask import current_app, request
from flask_login import current_user

from app.routes.api.mobile import mobile_bp
from app.services.security.monitoring import SecurityMonitor
from app.utils.api_helpers import get_json_safe
from app.utils.mobile_auth import mobile_auth_required
from app.utils.mobile_responses import mobile_bad_request, mobile_ok, mobile_server_error
from app.utils.rate_limiting import mobile_rate_limit

MOBILE_CLIENT_ERROR_EVENT_TYPE = 'mobile_client_error'
ALLOWED_CATEGORIES = frozenset({'offline_download', 'offline_open'})

MAX_REQUEST_BYTES = 64 * 1024
MAX_MESSAGE_CHARS = 1000
MAX_STACK_CHARS = 6000
MAX_SHORT_CHARS = 200
MAX_DETAIL_KEYS = 30
MAX_DETAIL_VALUE_CHARS = 1500
MAX_DETAIL_LIST_ITEMS = 60
MAX_DETAIL_LIST_ITEM_CHARS = 400
MAX_CONTEXT_BYTES = 24 * 1024

_CONTROL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
_SECRET_PATTERNS = (
    (re.compile(r'(?i)\b(cookie|set-cookie|authorization)(\s*[:=]\s*)[^\n]+'), r'\1\2[redacted]'),
    (re.compile(r'(?i)bearer\s+[A-Za-z0-9._~+/=-]+'), 'Bearer [redacted]'),
    (
        re.compile(r'(?i)\b(session|token|access_token|refresh_token|api_key|password|secret)=[^&\s"\']+'),
        r'\1=[redacted]',
    ),
)


def _redact(text: str) -> str:
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _clean(value, *, max_len: int, multiline: bool = False) -> str | None:
    """Coerce untrusted input to bounded, redacted text without control characters."""
    if value is None:
        return None
    text = str(value)
    text = _CONTROL_CHARS.sub(' ', text)
    if not multiline:
        text = text.replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')
    text = _redact(text).strip()
    return text[:max_len] if text else None


def _clean_detail_value(value):
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, (list, tuple)):
        items = []
        for item in list(value)[:MAX_DETAIL_LIST_ITEMS]:
            cleaned = _clean(item, max_len=MAX_DETAIL_LIST_ITEM_CHARS)
            if cleaned:
                items.append(cleaned)
        return items
    return _clean(value, max_len=MAX_DETAIL_VALUE_CHARS, multiline=True)


def _clean_details(details) -> dict:
    if not isinstance(details, dict):
        return {}
    out = {}
    for key in list(details)[:MAX_DETAIL_KEYS]:
        clean_key = _clean(key, max_len=60)
        if clean_key:
            out[clean_key] = _clean_detail_value(details[key])
    return out


def _optional_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if 0 <= parsed <= 2_000_000_000 else None


@mobile_bp.route('/diagnostics/client-error', methods=['POST'])
@mobile_rate_limit(requests_per_minute=20)
@mobile_auth_required(track_session_activity=False)
def log_mobile_client_error():
    """Record a failure that happened inside the mobile app.

    Expected JSON::

        {
          "category": "offline_download",
          "message": "Offline copy is incomplete: ...",
          "error_type": "AssignmentOfflineBundleException",
          "stack": "...",
          "assignment_id": 123,
          "template_id": 45,
          "language": "en",
          "app_version": "1.4.0",
          "platform": "ios",
          "details": {"missing_assets": ["/static/js/x.js"], "log_tail": ["..."]}
        }
    """
    try:
        if request.content_length and request.content_length > MAX_REQUEST_BYTES:
            return mobile_bad_request('Payload too large')

        data = get_json_safe()
        category = _clean(data.get('category'), max_len=40)
        if category not in ALLOWED_CATEGORIES:
            return mobile_bad_request('Unsupported category')

        message = _clean(data.get('message'), max_len=MAX_MESSAGE_CHARS) or 'unknown error'
        error_type = _clean(data.get('error_type'), max_len=MAX_SHORT_CHARS) or 'unknown'

        context_data = {
            'category': category,
            'message': message,
            'error_type': error_type,
            'stack': _clean(data.get('stack'), max_len=MAX_STACK_CHARS, multiline=True) or '',
            'assignment_id': _optional_int(data.get('assignment_id')),
            'template_id': _optional_int(data.get('template_id')),
            'language': _clean(data.get('language'), max_len=10),
            'app_version': _clean(data.get('app_version'), max_len=40)
            or _clean(request.headers.get('X-App-Version'), max_len=40),
            'platform': _clean(data.get('platform'), max_len=20),
            'device_model': _clean(data.get('device_model'), max_len=80),
            'os_version': _clean(data.get('os_version'), max_len=40),
            'details': _clean_details(data.get('details')),
            'platform_surface': 'mobile_app',
            'reporter': 'mobile_client',
        }

        if len(json.dumps(context_data, default=str)) > MAX_CONTEXT_BYTES:
            context_data['details'] = {'truncated': True}
            context_data['stack'] = context_data['stack'][:1000]

        description = f'[{category}] {error_type}: {message}'[:500]

        SecurityMonitor.log_security_event(
            event_type=MOBILE_CLIENT_ERROR_EVENT_TYPE,
            severity='low',
            description=description,
            context_data=context_data,
            user_id=current_user.id,
            notify_admins=False,
        )
        return mobile_ok(message='Diagnostic recorded')
    except Exception as exc:
        current_app.logger.error('Mobile client diagnostic failed: %s', exc, exc_info=True)
        return mobile_server_error('Failed to record diagnostic')
