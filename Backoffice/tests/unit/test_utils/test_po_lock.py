"""Unit tests for app/utils/po_lock.py: cross-process PO locking and the sentinel."""
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from app.utils import po_lock


@pytest.mark.unit
class TestFilelockProtectionStatus:
    def test_reports_available_when_filelock_installed(self):
        # filelock is a hard-pinned dependency (requirements.txt); in a correctly
        # provisioned dev/CI environment this must report available.
        status = po_lock.filelock_protection_status()
        assert status["available"] is True
        assert "lock-protected" in status["message"]

    def test_reports_unavailable_when_filelock_missing(self):
        with patch.object(po_lock, "_filelock_available", False):
            status = po_lock.filelock_protection_status()
        assert status["available"] is False
        assert "NOT installed" in status["message"]


@pytest.mark.unit
class TestPoFileLock:
    def test_lock_creates_sidecar_and_yields(self, tmp_path):
        po_path = tmp_path / "messages.po"
        po_path.write_text("# po")

        entered = False
        with po_lock.po_file_lock(str(po_path)):
            entered = True
            assert (tmp_path / "messages.po.lock").exists()
        assert entered is True

    def test_lock_is_released_after_context_exits(self, tmp_path):
        po_path = tmp_path / "messages.po"
        po_path.write_text("# po")

        with po_lock.po_file_lock(str(po_path)):
            pass

        # A second acquisition must succeed immediately (proves the first was released).
        with po_lock.po_file_lock(str(po_path), timeout=2):
            pass

    def test_timeout_raises_runtime_error(self, tmp_path):
        from filelock import FileLock

        po_path = tmp_path / "messages.po"
        po_path.write_text("# po")
        lock_path = str(Path(str(po_path)).with_suffix(".po.lock"))

        holder = FileLock(lock_path)
        holder.acquire()
        try:
            with pytest.raises(RuntimeError):
                with po_lock.po_file_lock(str(po_path), timeout=1):
                    pass
        finally:
            holder.release()

    def test_missing_filelock_falls_back_to_noop_and_warns_once(self, tmp_path):
        po_path = tmp_path / "messages.po"
        po_path.write_text("# po")

        with patch.object(po_lock, "_filelock_available", False), \
             patch.object(po_lock, "_missing_filelock_warned", False), \
             patch.object(po_lock.logger, "error") as mock_error:
            for _ in range(3):
                with po_lock.po_file_lock(str(po_path)):
                    pass

        mock_error.assert_called_once()
        # No lock sidecar should be created in the fallback path.
        assert not (tmp_path / "messages.po.lock").exists()


@pytest.mark.unit
class TestTouchTranslationSentinel:
    def test_creates_sentinel_file(self, tmp_path):
        po_lock.touch_translation_sentinel(str(tmp_path))
        sentinel = tmp_path / po_lock.SENTINEL_FILENAME
        assert sentinel.exists()

    def test_content_changes_across_calls(self, tmp_path):
        po_lock.touch_translation_sentinel(str(tmp_path))
        sentinel = tmp_path / po_lock.SENTINEL_FILENAME
        first = sentinel.read_text(encoding="ascii")
        time.sleep(0.01)
        po_lock.touch_translation_sentinel(str(tmp_path))
        second = sentinel.read_text(encoding="ascii")
        assert first != second

    def test_none_dir_is_a_safe_noop(self):
        po_lock.touch_translation_sentinel(None)  # must not raise

    def test_unwritable_dir_is_swallowed(self):
        # A nonexistent parent directory raises inside write_text; must be caught.
        po_lock.touch_translation_sentinel("Z:/definitely/not/a/real/path/on/this/machine")
