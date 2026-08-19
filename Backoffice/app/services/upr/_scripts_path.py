"""Shared helper to make ``scripts/imports`` importable from UPR Flask services.

The UPR Excel import/export services are thin Flask-facing wrappers around
standalone engines that live under ``Backoffice/scripts/imports`` (so those
engines stay runnable outside the Flask app, e.g. from CLI backfills).  Each
wrapper needs the same one-time ``sys.path`` setup; this module centralises
that instead of repeating it per-service.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

# Cached resolved scripts/imports directory; set on first use inside an app context.
_SCRIPTS_DIR: Optional[str] = None


def ensure_scripts_in_path() -> None:
    """Insert ``scripts/imports`` (and ``scripts``) onto ``sys.path`` if not already present.

    Safe to call repeatedly; resolution only happens once per process. Must be
    called from within a Flask app context (uses ``current_app.root_path``).
    """
    global _SCRIPTS_DIR
    if _SCRIPTS_DIR is not None:
        return
    from flask import current_app

    scripts_dir = os.path.normpath(os.path.join(current_app.root_path, "..", "scripts"))
    imports_dir = os.path.join(scripts_dir, "imports")
    for path in (imports_dir, scripts_dir):
        if path not in sys.path:
            sys.path.insert(0, path)
    _SCRIPTS_DIR = imports_dir
