"""Org-timezone logging helpers, importable without the ``app`` package.

This module lives at the repository top level so the Gunicorn master process
(config/gunicorn.conf.py ``on_starting``) can configure timezone-correct log
formatting without importing ``app/__init__`` (Flask, SQLAlchemy, config) —
the master never serves requests and should stay light.

Application code continues to import these helpers via
``app.utils.datetime_helpers`` / ``app.utils.logging_handlers``, which
re-export them from here.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

# IFRC HQ — Geneva shares the Europe/Zurich IANA zone (CET/CEST).
ORG_TIMEZONE_NAME = (os.environ.get("APP_TIMEZONE") or "Europe/Zurich").strip() or "Europe/Zurich"

DEFAULT_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S %Z"


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


class OrgTimezoneFormatter(logging.Formatter):
    """Format log timestamps in the organization timezone (Geneva / Europe/Zurich)."""

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc).astimezone(get_org_timezone())
        fmt = datefmt or DEFAULT_LOG_DATEFMT
        return dt.strftime(fmt)


def configure_process_org_timezone() -> str:
    """Set process TZ so localtime-based logs (e.g. gunicorn access) use org timezone."""
    os.environ["TZ"] = ORG_TIMEZONE_NAME
    if hasattr(time, "tzset"):
        time.tzset()
    return ORG_TIMEZONE_NAME


def install_org_timezone_werkzeug_access_log() -> bool:
    """Make the Werkzeug dev-server access line use the org timezone.

    Werkzeug stamps ``127.0.0.1 - - [dd/Mon/yyyy HH:MM:SS]`` with ``time.localtime()``. On Windows
    ``time.tzset`` does not exist and the CRT does not understand the IANA name we put in ``TZ``,
    so those lines come out in UTC while app lines (``OrgTimezoneFormatter``) show Geneva time.
    Idempotent. Returns True when the patch is (already) installed.
    """
    try:
        from werkzeug.serving import WSGIRequestHandler
    except Exception:
        return False
    if getattr(WSGIRequestHandler.log_date_time_string, "_org_timezone", False):
        return True

    def log_date_time_string(self) -> str:  # noqa: ARG001 - signature mandated by http.server
        now = datetime.now(timezone.utc).astimezone(get_org_timezone())
        return now.strftime("%d/%b/%Y %H:%M:%S %Z")

    log_date_time_string._org_timezone = True  # type: ignore[attr-defined]
    WSGIRequestHandler.log_date_time_string = log_date_time_string  # type: ignore[method-assign]
    return True


def create_app_log_formatter(
    fmt: str,
    datefmt: str = DEFAULT_LOG_DATEFMT,
) -> OrgTimezoneFormatter:
    """Standard application log formatter (Geneva timestamps)."""
    return OrgTimezoneFormatter(fmt, datefmt=datefmt)
