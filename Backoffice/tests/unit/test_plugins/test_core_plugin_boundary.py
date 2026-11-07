"""Ratchet on core -> plugin imports.

Core (``app/``) should depend on plugins only through ``BasePlugin`` hooks. Existing direct
imports are recorded in ``core_plugin_import_baseline.json``; a file may never gain imports and
new files may not add any. When you remove an import, refresh the baseline:

    python -m tests.unit.test_plugins.test_core_plugin_boundary --write
"""
from __future__ import annotations

import ast
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

BACKOFFICE = Path(__file__).resolve().parents[3]
APP_DIR = BACKOFFICE / "app"
BASELINE = Path(__file__).with_name("core_plugin_import_baseline.json")


def collect_core_plugin_imports() -> dict[str, dict[str, int]]:
    found: dict[str, Counter] = {}
    for path in sorted(APP_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        counter: Counter = Counter()
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                modules = [node.module]
            elif isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            for module in modules:
                parts = module.split(".")
                if parts[0] == "plugins" and len(parts) > 1:
                    counter[parts[1]] += 1
        if counter:
            found[path.relative_to(BACKOFFICE).as_posix()] = dict(counter)
    return found


@pytest.mark.unit
def test_core_does_not_gain_plugin_imports():
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    current = collect_core_plugin_imports()
    regressions = []
    for file, plugins in current.items():
        for plugin, count in plugins.items():
            allowed = baseline.get(file, {}).get(plugin, 0)
            if count > allowed:
                regressions.append(f"{file}: {count} import(s) of plugins.{plugin} (baseline {allowed})")
    assert not regressions, (
        "Core must not import plugin code directly; add a BasePlugin hook instead.\n"
        + "\n".join(regressions)
    )


@pytest.mark.unit
def test_baseline_is_not_stale():
    """Fail when imports were removed but the baseline still allows them (keeps the ratchet tight)."""
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    current = collect_core_plugin_imports()
    stale = []
    for file, plugins in baseline.items():
        for plugin, allowed in plugins.items():
            count = current.get(file, {}).get(plugin, 0)
            if count < allowed:
                stale.append(f"{file}: baseline {allowed}, now {count} for plugins.{plugin}")
    assert not stale, (
        "Core -> plugin imports went down. Refresh the baseline:\n"
        "  python -m tests.unit.test_plugins.test_core_plugin_boundary --write\n" + "\n".join(stale)
    )


if __name__ == "__main__":
    if "--write" in sys.argv:
        BASELINE.write_text(
            json.dumps(collect_core_plugin_imports(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"wrote {BASELINE}")
