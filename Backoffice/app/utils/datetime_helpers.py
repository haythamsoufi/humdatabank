"""
Utility helpers for working with timezone-aware UTC datetimes and org-local time.

Storage and server logic use UTC. Timestamp columns are ``timestamp without time
zone`` and hold the UTC wall clock, so values come back naive. ``ensure_utc()``
labels those as UTC before any arithmetic. PostgreSQL sessions are pinned to UTC
so an aware bind parameter is not shifted by the server timezone.

IFRC operational schedules (e.g. FDS digests) use the organization timezone —
Geneva (Europe/Zurich, CET/CEST).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

# Timezone constants/helpers live in the top-level org_logging module so the
# Gunicorn master can use them without importing the app package; re-exported
# here for application code.
from org_logging import (  # noqa: F401
    ORG_TIMEZONE_NAME,
    get_org_timezone,
    get_timezone,
)

ORG_TIMEZONE_LABEL = "Geneva"


def utcnow():
    """Return a timezone-aware datetime representing current UTC time."""
    return datetime.now(timezone.utc)


def isoformat_utc():
    """Shortcut for utcnow().isoformat()."""
    return utcnow().isoformat()


def ensure_utc(dt):
    """
    Ensure a datetime is timezone-aware (UTC).
    If the datetime is naive, assume it's UTC and add timezone info.
    If it's already timezone-aware, convert to UTC.
    Returns None if dt is None.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Naive datetime - assume it's UTC
        return dt.replace(tzinfo=timezone.utc)
    # Already timezone-aware - convert to UTC
    return dt.astimezone(timezone.utc)


def naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """UTC wall clock with tzinfo removed.

    Bind this to ``timestamp without time zone`` columns. Those columns store
    UTC clock time and load back as naive datetimes.
    """
    aware = ensure_utc(dt)
    if aware is None:
        return None
    return aware.replace(tzinfo=None)


def parse_iso_utc(value) -> Optional[datetime]:
    """Parse an ISO-8601 datetime as UTC.

    Aware values are converted to UTC. Naive values are treated as UTC.
    A trailing ``Z`` is accepted. Returns None when *value* is empty or not
    a datetime.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return ensure_utc(value)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, datetime):
        return None
    return ensure_utc(parsed)


_UTC_MIN = datetime.min.replace(tzinfo=timezone.utc)
_UTC_MAX = datetime.max.replace(tzinfo=timezone.utc)


def utc_sort_key(dt: Optional[datetime], *, empty: str = "min") -> datetime:
    """Sort key that accepts naive UTC values, aware datetimes, and None.

    ``empty="min"`` places missing values first in ascending order.
    ``empty="max"`` places them last.
    """
    sentinel = _UTC_MAX if empty == "max" else _UTC_MIN
    if dt is None:
        return sentinel
    try:
        normalized = ensure_utc(dt)
    except AttributeError:
        return sentinel
    return normalized if normalized is not None else sentinel


def now_in_org_timezone() -> datetime:
    """Return current time in the organization timezone."""
    return datetime.now(get_org_timezone())


def org_day_start_utc(reference: Optional[datetime] = None) -> datetime:
    """Start of the calendar day in the org timezone, expressed as UTC-aware datetime."""
    org_tz = get_org_timezone()
    if reference is None:
        local_now = datetime.now(org_tz)
    else:
        local_now = ensure_utc(reference).astimezone(org_tz)
    local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_midnight.astimezone(timezone.utc)


def format_in_org_timezone(
    dt: Optional[datetime],
    fmt: str = "%Y-%m-%d %H:%M",
    *,
    suffix: Optional[str] = None,
) -> str:
    """Format a datetime in the organization timezone for display (emails, admin UI)."""
    if dt is None:
        return ""
    local = ensure_utc(dt).astimezone(get_org_timezone())
    label = suffix if suffix is not None else ORG_TIMEZONE_LABEL
    return f"{local.strftime(fmt)} {label}"
