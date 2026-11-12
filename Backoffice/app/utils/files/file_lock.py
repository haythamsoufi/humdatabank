"""Cross-process file locking and atomic JSON writes for shared instance files."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LOCK_TIMEOUT_SECONDS = 30

try:
    from filelock import FileLock, Timeout as LockTimeout
    _filelock_available = True
except ImportError:  # pragma: no cover
    _filelock_available = False
    LockTimeout = Exception


@contextmanager
def shared_file_lock(path: str | Path, timeout: int = LOCK_TIMEOUT_SECONDS):
    """Advisory lock for any shared file (sidecar ``<path>.lock``)."""
    if not _filelock_available:
        logger.warning(
            "filelock is not installed — shared file writes are NOT protected. "
            "Run: pip install filelock"
        )
        yield
        return

    lock_path = str(Path(path).with_suffix(Path(path).suffix + ".lock"))
    lock = FileLock(lock_path, timeout=timeout)
    try:
        with lock:
            yield
    except LockTimeout:
        raise RuntimeError(
            f"Could not acquire lock for {path!r} within {timeout}s."
        ) from None


def atomic_json_write(path: str | Path, data: Any, *, indent: int = 2) -> None:
    """Write JSON atomically via temp file + os.replace under shared lock."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with shared_file_lock(path):
        fd, tmp = tempfile.mkstemp(
            suffix=".tmp",
            prefix=f"{path.name}.",
            dir=str(path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=indent, ensure_ascii=False)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
