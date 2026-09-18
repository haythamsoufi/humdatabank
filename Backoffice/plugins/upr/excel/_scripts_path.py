"""Put UPR plugin scripts and core ``scripts/imports`` on ``sys.path``."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_PLUGIN_DIR = Path(__file__).resolve().parents[1]
_SCRIPTS_PATH = _PLUGIN_DIR / "scripts"
_CORE_IMPORTS = _PLUGIN_DIR.parents[1] / "scripts" / "imports"

# Reset to None in tests to force re-resolution.
_SCRIPTS_DIR: Optional[str] = None


def ensure_scripts_in_path() -> str:
    """Insert ``plugins/upr/scripts`` and core ``scripts/imports`` onto ``sys.path``."""
    global _SCRIPTS_DIR
    plugin_scripts = str(_SCRIPTS_PATH)
    core_imports = str(_CORE_IMPORTS)
    for path in (plugin_scripts, core_imports):
        if path not in sys.path:
            sys.path.insert(0, path)
    _SCRIPTS_DIR = plugin_scripts
    return plugin_scripts
