"""
Utility helpers for working with timezone-aware UTC datetimes.
"""
from datetime import datetime, timezone


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
