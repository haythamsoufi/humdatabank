"""
Utility helpers for working with timezone-aware UTC datetimes and org-local time.

Storage and server logic use UTC. IFRC operational schedules (e.g. FDS digests) use
the organization timezone — Geneva (Europe/Zurich, CET/CEST).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

# IFRC HQ — Geneva shares the Europe/Zurich IANA zone (CET/CEST).
ORG_TIMEZONE_NAME = (os.environ.get("APP_TIMEZONE") or "Europe/Zurich").strip() or "Europe/Zurich"
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


def get_timezone(tz_name: str) -> Any:
    """Return a tzinfo for an IANA timezone name, falling back to UTC."""
    if not tz_name:
        return timezone.utc
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(tz_name)
    except Exception:
        try:
            import pytz

            return pytz.timezone(tz_name)
        except Exception:
            return timezone.utc


def get_org_timezone() -> Any:
    """Return tzinfo for the organization timezone (Geneva / Europe/Zurich)."""
    return get_timezone(ORG_TIMEZONE_NAME)


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
