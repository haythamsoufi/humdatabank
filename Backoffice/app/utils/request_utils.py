# -*- coding: utf-8 -*-
"""
Shared request utilities for JSON/AJAX detection.
Centralizes is_json_request to replace ad-hoc X-Requested-With / request.is_json checks.
"""
from flask import request

from app.utils.api_helpers import get_json_safe


class _JsonFormProxy:
    """Drop-in replacement for ``request.form`` backed by a parsed JSON dict.

    Supports the subset of the ImmutableMultiDict API used across route
    handlers and helpers: ``.get()``, ``.getlist()``, ``__contains__``,
    ``__getitem__``, ``.keys()``, ``.to_dict()``.
    """

    __slots__ = ("_data",)

    def __init__(self, data: dict):
        self._data = data if data is not None else {}

    # --- dict-like access ---
    def get(self, key, default=None, type=None):      # noqa: A002  (shadows builtin; matches Werkzeug sig)
        val = self._data.get(key, default)
        if type is not None and val is not None:
            try:
                val = type(val)
            except (ValueError, TypeError):
                val = default
        return val

    def getlist(self, key):
        val = self._data.get(key, [])
        if isinstance(val, list):
            return list(val)
        return [val] if val is not None else []

    def __contains__(self, key):
        return key in self._data

    def __getitem__(self, key):
        return self._data[key]

    def keys(self):
        return self._data.keys()

    def to_dict(self):
        return dict(self._data)


def get_request_data():
    """Return a form-data-like object for the current request.

    When Content-Type is ``application/json``, returns a
    :class:`_JsonFormProxy` wrapping the parsed body so callers can keep
    using ``.get()`` / ``.getlist()`` / ``in`` without branching.

    Otherwise returns ``request.form`` directly.

    Usage in handlers::

        data = get_request_data()
        version_id = data.get('version_id')
        items = data.getlist('items')
    """
    if _is_json_body():
        return _JsonFormProxy(get_json_safe() or {})
    return request.form


def get_request_field(data, key, default=None, coerce=None):
    """Read a single field from a request-data object (proxy or form).

    *data* can be a :class:`_JsonFormProxy`, ``request.form``, or ``None``
    (falls back to ``request.form``).
    """
    src = data if data is not None else request.form
    val = src.get(key, default)
    if coerce is not None and val is not None:
        try:
            val = coerce(val)
        except (ValueError, TypeError):
            val = default
    return val


def get_request_list(data, key):
    """Read a multi-value field from a request-data object."""
    src = data if data is not None else request.form
    if hasattr(src, 'getlist'):
        return src.getlist(key)
    val = src.get(key, [])
    return val if isinstance(val, list) else [val]


def is_static_asset_request(req=None):
    """True for high-volume static URLs that should not touch the database.

    Accessing ``current_user`` (e.g. ``current_user.is_authenticated``) triggers
    Flask-Login's user loader, which opens a SQLAlchemy connection. Asset
    requests (/static/, plugin static, favicon) should not require the DB when
    the primary page load already established the session.
    """
    req = req or request
    path = req.path or ""
    if path.startswith("/static/") or path.startswith("/plugins/static/"):
        return True
    if path in ("/favicon.ico", "/manifest.webmanifest"):
        return True
    if path.startswith("/manifest"):
        return True
    ep = req.endpoint
    if ep == "static":
        return True
    if ep and ep.startswith("plugin_static."):
        return True
    return False


def is_json_request():
    """True if the current request expects a JSON response (API/AJAX)."""
    accept = request.headers.get("Accept", "")
    content_type = request.headers.get("Content-Type", "")
    path = request.path or ""
    # Broader admin API detection: /admin/ with 'api' in path
    is_admin_api = path.startswith("/admin/") and "api" in path
    return (
        request.is_json
        or (content_type.startswith("application/json") if content_type else False)
        or "application/json" in accept
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.args.get("ajax") == "1"
        or path.startswith("/admin/api/")
        or path.startswith("/admin/users/api/")
        or path.startswith("/admin/users/rbac/api/")
        or is_admin_api
    )


def _is_json_body():
    """True when the request body is JSON (based on Content-Type, not AJAX headers)."""
    content_type = request.headers.get("Content-Type", "")
    return request.is_json or content_type.startswith("application/json")


def get_json_or_form(default=None):
    """
    Return parsed JSON body or request.form as dict depending on request type.
    Use when a route accepts both JSON and form-encoded bodies.
    Always returns a dict (ImmutableMultiDict.to_dict() for form data).

    Uses Content-Type to decide format, not X-Requested-With / is_json_request(),
    so FormData submissions from AJAX calls are correctly read from request.form.
    """
    if _is_json_body():
        return get_json_safe(default) or {}
    return request.form.to_dict()


def parse_ids_from_request(key: str = "ids") -> list[int]:
    """
    Parse a list of integer IDs from the current request.

    Accepts either JSON body {key: [1, 2, 3]} or form-encoded key="1,2,3".
    Returns deduplicated list preserving order. Invalid values are skipped.
    """
    ids: list[int] = []
    if is_json_request():
        payload = get_json_safe() or {}
        raw_ids = payload.get(key) or []
        if isinstance(raw_ids, list):
            for v in raw_ids:
                try:
                    ids.append(int(v))
                except (TypeError, ValueError):
                    continue
    else:
        ids_str = (request.form.get(key) or "").strip()
        if ids_str:
            for part in ids_str.split(","):
                part = part.strip()
                if not part:
                    continue
                try:
                    ids.append(int(part))
                except (TypeError, ValueError):
                    continue
    seen: set[int] = set()
    return [i for i in ids if i not in seen and not seen.add(i)]


# --- Mobile app embedded WebView (Flutter InAppWebView) ----------------------------

# Must match MobileApp/lib/services/webview_service.dart defaultRequestHeaders.
MOBILE_APP_WEBVIEW_HEADER = "X-Mobile-App"
MOBILE_APP_WEBVIEW_HEADER_VALUE = "IFRC-Databank-Flutter"
MOBILE_APP_EMBED_COOKIE_NAME = "HD_MOBILE_EMBED"
MOBILE_APP_EMBED_COOKIE_VALUE = "1"


def mobile_app_webview_embed_active() -> bool:
    """True when the Humanitarian Databank mobile app is loading this page in its WebView.

    Uses the custom header sent on the initial document request and a short-lived
    cookie set from that header so follow-up navigations (clicks, redirects) still
    render without the full backoffice chrome even when extra headers are not replayed.
    """
    h = (request.headers.get(MOBILE_APP_WEBVIEW_HEADER) or "").strip()
    if h == MOBILE_APP_WEBVIEW_HEADER_VALUE:
        return True
    return (request.cookies.get(MOBILE_APP_EMBED_COOKIE_NAME) or "") == MOBILE_APP_EMBED_COOKIE_VALUE


def mark_mobile_app_webview_embed_request() -> None:
    """Set a request flag when the mobile WebView header is present (used by after_request)."""
    from flask import g

    g._hd_mobile_webview_header = (
        (request.headers.get(MOBILE_APP_WEBVIEW_HEADER) or "").strip()
        == MOBILE_APP_WEBVIEW_HEADER_VALUE
    )


def persist_mobile_app_embed_cookie(response):
    """If this request carried the mobile WebView header, persist embed mode for later navigations."""
    from flask import current_app, g, request

    if not getattr(g, "_hd_mobile_webview_header", False):
        return response
    try:
        secure = bool(current_app.config.get("SESSION_COOKIE_SECURE", False)) or request.is_secure
        response.set_cookie(
            MOBILE_APP_EMBED_COOKIE_NAME,
            MOBILE_APP_EMBED_COOKIE_VALUE,
            path="/",
            httponly=True,
            samesite="Lax",
            secure=secure,
        )
    except Exception:
        pass
    return response


def clear_mobile_app_embed_cookie(response):
    """Remove embed-mode cookie (e.g. on logout)."""
    try:
        response.delete_cookie(MOBILE_APP_EMBED_COOKIE_NAME, path="/")
    except Exception:
        pass
    return response
