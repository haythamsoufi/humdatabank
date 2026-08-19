"""Pytest markers for the UPR visuals plugin."""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
BACKOFFICE_ROOT = PLUGIN_ROOT.parent.parent
_backoffice = str(BACKOFFICE_ROOT)
if _backoffice not in sys.path:
    sys.path.insert(0, _backoffice)


def pytest_collection_modifyitems(items) -> None:
    plugin_root = PLUGIN_ROOT.as_posix().lower()
    for item in items:
        if plugin_root in item.path.as_posix().lower():
            item.add_marker(__import__("pytest").mark.upr_visuals)
