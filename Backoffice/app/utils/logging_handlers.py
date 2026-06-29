"""Windows-safe rotating file handlers and org-timezone log formatters."""

import logging
import os
import shutil
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from app.utils.datetime_helpers import ORG_TIMEZONE_NAME, get_org_timezone

DEFAULT_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S %Z"


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


def create_app_log_formatter(
    fmt: str,
    datefmt: str = DEFAULT_LOG_DATEFMT,
) -> OrgTimezoneFormatter:
    """Standard application log formatter (Geneva timestamps)."""
    return OrgTimezoneFormatter(fmt, datefmt=datefmt)


class SafeRotatingFileHandler(RotatingFileHandler):
    """
    RotatingFileHandler that tolerates Windows file locking.

    Standard RotatingFileHandler.rename() fails on Windows when the log file
    is still open (multiple handlers, IDE tail, or a second dev server). Close
    the stream before rollover and fall back to copy+truncate when rename fails.
    """

    def rotate(self, source, dest):
        try:
            super().rotate(source, dest)
        except (OSError, PermissionError):
            if os.name != "nt":
                raise
            try:
                if os.path.exists(source):
                    shutil.copy2(source, dest)
                    with open(source, "w", encoding=self.encoding):
                        pass
            except (OSError, PermissionError):
                # Another process still holds the file — skip rotation this cycle.
                pass

    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        super().doRollover()


def create_rotating_file_handler(
    path: str,
    max_bytes: int,
    backup_count: int,
    encoding: str = "utf-8",
) -> SafeRotatingFileHandler:
    """Create a SafeRotatingFileHandler for the given log path."""
    return SafeRotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding=encoding,
    )
