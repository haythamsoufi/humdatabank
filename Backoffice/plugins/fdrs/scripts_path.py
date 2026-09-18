"""Resolve and expose FDRS plugin script directories on sys.path."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_PLUGIN_DIR = Path(__file__).resolve().parent
_SCRIPTS_DIR = _PLUGIN_DIR / "scripts"


def fdrs_scripts_dir() -> str:
    return str(_SCRIPTS_DIR)


def ensure_fdrs_scripts_in_path() -> str:
    """Put plugin scripts + core ``scripts/imports`` on ``sys.path``."""
    core_imports = str(_PLUGIN_DIR.parents[1] / "scripts" / "imports")
    plugin_scripts = fdrs_scripts_dir()
    for path in (plugin_scripts, core_imports):
        if path not in sys.path:
            sys.path.insert(0, path)
    return plugin_scripts
