"""Windows-safe rotating file handlers for application logging."""

import logging
import os
import shutil
from logging.handlers import RotatingFileHandler


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
