"""Unit tests for app.utils.logging_handlers."""

import logging
import os
import tempfile
from unittest.mock import patch

import pytest

from app.utils.logging_handlers import SafeRotatingFileHandler, create_rotating_file_handler


class TestSafeRotatingFileHandler:
    def test_create_rotating_file_handler_returns_safe_handler(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.log")
            handler = create_rotating_file_handler(path, max_bytes=1024, backup_count=2)
            assert isinstance(handler, SafeRotatingFileHandler)
            handler.close()

    def test_rotate_uses_copy_fallback_on_windows_permission_error(self):
        handler = SafeRotatingFileHandler("dummy.log", maxBytes=10, backupCount=1)
        with (
            patch.object(handler, "baseFilename", "source.log"),
            patch("app.utils.logging_handlers.os.name", "nt"),
            patch(
                "logging.handlers.RotatingFileHandler.rotate",
                side_effect=PermissionError("locked"),
            ),
            patch("app.utils.logging_handlers.os.path.exists", return_value=True),
            patch("app.utils.logging_handlers.shutil.copy2") as copy_mock,
            patch("builtins.open", create=True) as open_mock,
        ):
            handler.rotate("source.log", "dest.log")
            copy_mock.assert_called_once_with("source.log", "dest.log")
            open_mock.assert_called_once_with("source.log", "w", encoding=handler.encoding)

    def test_rotate_raises_on_non_windows_permission_error(self):
        handler = SafeRotatingFileHandler("dummy.log", maxBytes=10, backupCount=1)
        with (
            patch("app.utils.logging_handlers.os.name", "posix"),
            patch(
                "logging.handlers.RotatingFileHandler.rotate",
                side_effect=PermissionError("locked"),
            ),
        ):
            with pytest.raises(PermissionError):
                handler.rotate("source.log", "dest.log")

    def test_doRollover_closes_stream_before_super(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "rollover.log")
            handler = SafeRotatingFileHandler(path, maxBytes=50, backupCount=1, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger = logging.getLogger("test.safe_rotating")
            logger.handlers.clear()
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)

            logger.info("line one")
            logger.info("line two enough to trigger rollover soon")

            assert handler.stream is not None
            handler.doRollover()
            assert handler.stream is not None

            logger.removeHandler(handler)
            handler.close()
