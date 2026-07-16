"""Windows-safe rotating file handlers and org-timezone log formatters."""

import os
import shutil
from logging.handlers import RotatingFileHandler

# The timezone formatter helpers live in the top-level org_logging module so
# the Gunicorn master can use them without importing the app package;
# re-exported here for application code.
from org_logging import (  # noqa: F401
    DEFAULT_LOG_DATEFMT,
    ORG_TIMEZONE_NAME,
    OrgTimezoneFormatter,
    configure_process_org_timezone,
    create_app_log_formatter,
)


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
