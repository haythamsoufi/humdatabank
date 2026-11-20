"""Time zone of the person currently browsing the back office.

Storage and server logic stay in UTC. The browser reports its IANA zone in the
``hdb_tz`` cookie; pages then render clocks in that zone. Until the cookie
exists, display falls back to UTC and client-side formatting still uses the
live browser zone.
"""

from __future__ import annotations

VIEWER_TIMEZONE_COOKIE = "hdb_tz"
_MAX_LEN = 64


def is_valid_timezone_name(name: str) -> bool:
    """True when *name* is an IANA zone both zoneinfo and pytz can load.

    Flask-Babel turns the selector result into a pytz timezone, so a name that
    only zoneinfo accepts would 500 the page on the first formatted timestamp.
    """
    if not isinstance(name, str):
        return False
    candidate = name.strip()
    if not candidate or len(candidate) > _MAX_LEN:
        return False
    if any(ch in candidate for ch in "\r\n\x00;=, "):
        return False
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(candidate)
    except Exception:
        return False
    try:
        import pytz

        pytz.timezone(candidate)
    except Exception:
        return False
    return True


def viewer_timezone_name() -> str:
    """IANA name for this request, or ``UTC`` when the browser has not sent one."""
    try:
        from flask import g, has_request_context, request
    except Exception:
        return "UTC"
    if not has_request_context():
        return "UTC"
    cached = getattr(g, "_viewer_timezone_name", None)
    if isinstance(cached, str):
        return cached
    raw = (request.cookies.get(VIEWER_TIMEZONE_COOKIE) or "").strip()
    name = raw if is_valid_timezone_name(raw) else "UTC"
    g._viewer_timezone_name = name
    return name
