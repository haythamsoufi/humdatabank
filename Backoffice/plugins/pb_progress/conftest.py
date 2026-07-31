"""Shared pytest setup for all P&B progress plugin tests."""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent
VISUALS_SCRIPTS = PLUGIN_ROOT / "visuals" / "scripts"
TESTS_ROOT = PLUGIN_ROOT / "tests"

for path in (VISUALS_SCRIPTS, TESTS_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


def pytest_collection_modifyitems(items) -> None:
    """Tag every test under plugins/pb_progress for selective runs."""
    plugin_root = PLUGIN_ROOT.as_posix().lower()
    for item in items:
        if plugin_root in item.path.as_posix().lower():
            item.add_marker(__import__("pytest").mark.pb_progress)
