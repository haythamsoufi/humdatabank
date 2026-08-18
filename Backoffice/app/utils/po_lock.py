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

# ``filelock`` is a hard-pinned dependency (see requirements.txt) — this branch
# should only ever trigger if a deployed environment's installed packages have
# drifted from requirements.txt (e.g. a stale venv/image). Log loudly, but only
# once per process so a busy translation workload doesn't spam the error log.
_missing_filelock_warned = False


def filelock_protection_status() -> dict:
    """Report whether PO writes are actually protected by an OS-level lock.

    Surfaced in `catalog_hygiene.hygiene_report()` so a requirements/environment
    drift (filelock pinned but not actually installed) is visible operationally
    instead of only showing up as an occasional lost-update race under load.
    """
    if _filelock_available:
        return {"available": True, "message": "filelock is installed; PO writes are lock-protected."}
    return {
        "available": False,
        "message": (
            "filelock is NOT installed — PO writes are unprotected from concurrent "
            "Gunicorn worker races. filelock is pinned in requirements.txt; reinstall "
            "dependencies (pip install -r requirements.txt)."
        ),
    }


@contextmanager
def po_file_lock(po_path: str, timeout: int = LOCK_TIMEOUT_SECONDS):
    """Acquire an exclusive advisory lock for *po_path*.

    Creates a ``.po.lock`` sidecar file next to the PO file.  Falls back to a
    no-op (logged once per process at error level) when ``filelock`` is not
    installed — this should not happen in a correctly provisioned environment
    since filelock is a hard-pinned dependency; see filelock_protection_status().

    Raises ``RuntimeError`` if the lock cannot be acquired within *timeout* s.
    """
    if not _filelock_available:
        global _missing_filelock_warned
        if not _missing_filelock_warned:
            _missing_filelock_warned = True
            logger.error(
                "filelock is not installed — PO writes are NOT protected from "
                "concurrent Gunicorn workers. filelock is a pinned dependency; "
                "run: pip install -r requirements.txt"
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
