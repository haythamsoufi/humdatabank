"""
Cross-process file locking and change notification for PO file operations.

Under Gunicorn (multiple worker processes) every worker can receive an admin
request that writes to the same .po file concurrently.  Without coordination
the read-modify-write cycle is vulnerable to lost updates and file corruption.

This module provides:

* ``po_file_lock(po_path)`` — context manager that MUST wrap every .po
  read + save pair.  Uses ``filelock.FileLock`` (OS-level advisory lock via
  a ``.po.lock`` sidecar file).

* ``touch_translation_sentinel(translations_dir)`` — writes a single sentinel
  file (``translations/.sentinel``) after any PO/MO change.  The translation
  watcher checks this one file instead of rescanning all locale directories on
  every tick, making cache-refresh propagation to peer workers both faster and
  more reliable on network file systems (Azure Files SMB).

Usage::

    from app.utils.po_lock import po_file_lock, touch_translation_sentinel

    with po_file_lock(po_file_path):
        po = polib.pofile(po_file_path)
        # ... mutate entries ...
        po.save(po_file_path)

    touch_translation_sentinel(translations_dir)

The lock is automatically released when the ``with`` block exits.
A ``RuntimeError`` is raised if the lock cannot be acquired within
``LOCK_TIMEOUT_SECONDS``; callers should surface this to the user rather than
silently skipping the save.
"""

import logging
import time
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

LOCK_TIMEOUT_SECONDS = 30

# Sentinel file name written inside the translations root after any PO/MO write.
# The translation watcher monitors this single file for mtime changes so that
# all Gunicorn workers refresh their Babel cache promptly without scanning every
# locale directory on every poll tick.
SENTINEL_FILENAME = ".sentinel"

try:
    from filelock import FileLock, Timeout as LockTimeout
    _filelock_available = True
except ImportError:  # pragma: no cover
    _filelock_available = False
    LockTimeout = Exception


@contextmanager
def po_file_lock(po_path: str, timeout: int = LOCK_TIMEOUT_SECONDS):
    """Acquire an exclusive advisory lock for *po_path*.

    Creates a ``.po.lock`` sidecar file next to the PO file.  Falls back to a
    no-op (with a one-time warning) when ``filelock`` is not installed.

    Raises ``RuntimeError`` if the lock cannot be acquired within *timeout* s.
    """
    if not _filelock_available:
        logger.warning(
            "filelock is not installed — PO writes are NOT protected from "
            "concurrent Gunicorn workers.  Run: pip install filelock"
        )
        yield
        return

    lock_path = str(Path(po_path).with_suffix(".po.lock"))
    lock = FileLock(lock_path, timeout=timeout)
    try:
        with lock:
            yield
    except LockTimeout:
        raise RuntimeError(
            f"Could not acquire PO lock for {po_path!r} within {timeout}s. "
            "Another worker is writing to this file — please retry."
        ) from None


def touch_translation_sentinel(translations_dir: str | None = None) -> None:
    """Update the sentinel file to signal all workers that translations changed.

    Workers whose ``TranslationWatcher`` is running will detect the mtime
    change on this single file (instead of polling all locale dirs) and call
    ``flask_babel.refresh()`` within one poll interval.

    Safe to call from any context — errors are logged but never propagated.
    """
    if not translations_dir:
        return
    try:
        sentinel = Path(translations_dir) / SENTINEL_FILENAME
        # Write the current epoch so the file content changes on every call
        # (some network file systems only update mtime on content change).
        sentinel.write_text(str(time.time()), encoding="ascii")
    except Exception as exc:
        logger.debug("touch_translation_sentinel failed: %s", exc)
