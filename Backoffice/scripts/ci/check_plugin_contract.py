#!/usr/bin/env python3
"""Static plugin contract check (stdlib only, runs in seconds, no database).

Every plugin under ``Backoffice/plugins/<id>/`` (and the starter package in
``app/sample_plugin_package``) must satisfy the rules below. The rules are the
machine-checkable half of ``Backoffice/plugins/README.md`` ("Plugin contract")
and ``.cursor/rules/plugin-development.mdc``.

Rules
-----
naming            folder name == ``plugin_id`` (lowercase letters, digits, underscores)
manifest          ``plugin.json`` with the required keys; ``plugin_id`` and ``version``
                  match ``plugin.py``
plugin-class      ``plugin.py`` defines a ``BasePlugin`` subclass
settings-route    a GET route ending in ``/settings`` (served at
                  ``/admin/plugins/<id>/settings``) exists, either written out or via
                  ``BasePluginRoutes.create_standard_routes(bp, renderer)``
settings-guard    that route is guarded with ``PLUGIN_MANAGE_PERMISSION`` /
                  ``admin.plugins.manage`` / ``plugin_admin_route_wrapper`` /
                  ``system_manager_required``
settings-template a ``settings.html`` that extends ``core/layout.html`` and includes
                  ``plugins/_plugin_info_card.html``
readme            ``README.md`` is present and not trivially short
tests             at least one ``test_*.py`` under ``plugins/<id>/tests/`` or
                  ``tests/unit/test_plugins/test_<id>*.py``
bundled           the id is listed in ``plugins/metadata.py::BUNDLED_PLUGIN_IDS``

Authoritative runtime checks (the URL really resolves, templates render) live in
``tests/unit/test_plugins/test_plugin_contract.py``.

Exit code 1 when any non-exempt rule fails. ``EXEMPT`` entries must carry a reason
and are checked for staleness, so the list can only shrink.

Usage (from ``Backoffice/``)::

    python scripts/ci/check_plugin_contract.py
    python scripts/ci/check_plugin_contract.py --plugin global_awards
    python scripts/ci/check_plugin_contract.py --github   # ::error annotations
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

BACKOFFICE = Path(__file__).resolve().parents[2]
PLUGINS_DIR = BACKOFFICE / "plugins"
STARTER_DIR = BACKOFFICE / "app" / "sample_plugin_package"
TESTS_DIR = BACKOFFICE / "tests" / "unit" / "test_plugins"

PLUGIN_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+([-+][0-9A-Za-z.-]+)?$")
MANIFEST_REQUIRED = ("plugin_id", "name", "display_name", "version", "description", "author", "license")
GUARD_RE = re.compile(
    r"(PLUGIN_MANAGE_PERMISSION|admin\.plugins\.manage|plugin_admin_route_wrapper|system_manager_required)"
)
MIN_README_CHARS = 200

# (plugin_id, rule) -> reason. Plugins that predate the contract. New plugins must not
# be added here; a stale entry (rule now passes) fails the check so the list shrinks.
EXEMPT: dict[tuple[str, str], str] = {
    ("emergency_operations", "manifest"): "predates the contract; plugin.json would change loader behaviour",
    ("emergency_operations", "readme"): "predates the contract",
    ("fdrs", "manifest"): "predates the contract; plugin.json would change loader behaviour",
    ("fdrs", "readme"): "predates the contract",
    ("global_awards", "readme"): "predates the contract",
    ("ifrc", "manifest"): "predates the contract; plugin.json would change loader behaviour",
    ("ifrc", "readme"): "predates the contract",
    ("interactive_map", "manifest"): "predates the contract; plugin.json would change loader behaviour",
    ("interactive_map", "readme"): "predates the contract",
    ("upr", "manifest"): "predates the contract; plugin.json would change loader behaviour",
    ("upr", "readme"): "predates the contract",
    # The starter is a template, not a shipped plugin.
    ("sample_plugin", "tests"): "starter package; copies must add tests",
}


@dataclass(frozen=True)
class Finding:
    plugin: str
    rule: str
    message: str


# ── helpers ────────────────────────────────────────────────────────────────


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None


def _module_constants(tree: ast.Module | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if tree is None:
        return out
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value.value
    return out


def _plugin_classes(tree: ast.Module | None) -> list[ast.ClassDef]:
    if tree is None:
        return []
    classes = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            bases = {ast.unparse(b).split(".")[-1] for b in node.bases}
            if "BasePlugin" in bases:
                classes.append(node)
    return classes


def _property_value(cls: ast.ClassDef, name: str, constants: dict[str, str]) -> str | None:
    for node in cls.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Return) and stmt.value is not None:
                    if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                        return stmt.value.value
                    if isinstance(stmt.value, ast.Name):
                        return constants.get(stmt.value.id)
    return None


def _plugin_py_files(plugin_dir: Path) -> list[Path]:
    files = []
    for path in plugin_dir.rglob("*.py"):
        rel = path.relative_to(plugin_dir).parts
        if "__pycache__" in rel or "tests" in rel or path.name.startswith("test_"):
            continue
        files.append(path)
    return files


def _settings_routes(plugin_dir: Path) -> list[tuple[Path, str, list[str], str]]:
    """Return (file, function name, decorators, route path) for GET-capable ``.../settings`` routes."""
    found = []
    for path in _plugin_py_files(plugin_dir):
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorators = [ast.unparse(d) for d in node.decorator_list]
            for deco in node.decorator_list:
                if not (
                    isinstance(deco, ast.Call)
                    and isinstance(deco.func, ast.Attribute)
                    and deco.func.attr in ("route", "get")
                    and deco.args
                ):
                    continue
                path_arg = ast.unparse(deco.args[0])
                if not re.search(r"/settings['\"]$", path_arg) or re.match(r"f?['\"]/api/", path_arg):
                    continue
                methods = next((ast.unparse(k.value) for k in deco.keywords if k.arg == "methods"), "['GET']")
                if deco.func.attr == "get" or "GET" in methods.upper():
                    found.append((path, node.name, decorators, path_arg))
    return found


def _url_prefixes(plugin_dir: Path) -> set[str]:
    """Every ``url_prefix="..."`` string literal passed to a call inside the plugin."""
    prefixes: set[str] = set()
    for path in _plugin_py_files(plugin_dir):
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "url_prefix" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        prefixes.add(kw.value.value.rstrip("/"))
    return prefixes


def _route_resolves_to_settings_url(path_arg: str, plugin_id: str, prefixes: set[str]) -> bool:
    """True when the route is served at ``/admin/plugins/<plugin_id>/settings``."""
    expected = f"/admin/plugins/{plugin_id}"
    if "/admin/plugins/" in path_arg:
        return "{" in path_arg or expected + "/settings" in path_arg
    return expected in prefixes


def _uses_standard_settings_route(plugin_dir: Path) -> bool:
    """``create_standard_routes(bp, renderer)`` registers a guarded ``/settings`` page."""
    for path in _plugin_py_files(plugin_dir):
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "create_standard_routes"
                and (len(node.args) >= 2 or any(k.arg == "template_renderer" for k in node.keywords))
            ):
                return True
    return False


def _bundled_ids() -> set[str]:
    tree = _parse(PLUGINS_DIR / "metadata.py")
    if tree is None:
        return set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "BUNDLED_PLUGIN_IDS" for t in node.targets):
            try:
                return set(ast.literal_eval(node.value))
            except (ValueError, SyntaxError):
                return set()
    return set()


def _has_tests(plugin_dir: Path, plugin_id: str) -> bool:
    own = plugin_dir / "tests"
    if own.is_dir() and any(own.rglob("test_*.py")):
        return True
    return any(TESTS_DIR.glob(f"test_{plugin_id}*.py"))


# ── per-plugin check ───────────────────────────────────────────────────────


def check_plugin(plugin_dir: Path, *, starter: bool = False) -> list[Finding]:
    folder = plugin_dir.name
    findings: list[Finding] = []

    def add(rule: str, message: str, plugin_id: str | None = None) -> None:
        findings.append(Finding(plugin_id or folder, rule, message))

    plugin_py = plugin_dir / "plugin.py"
    tree = _parse(plugin_py)
    classes = _plugin_classes(tree)
    constants = _module_constants(tree)
    constants_py = plugin_dir / "constants.py"
    if constants_py.is_file():
        constants = {**_module_constants(_parse(constants_py)), **constants}

    if not plugin_py.is_file() or tree is None:
        add("plugin-class", "plugin.py is missing or does not parse")
        return findings
    if not classes:
        add("plugin-class", "plugin.py must define a class inheriting BasePlugin")
        return findings

    cls = classes[0]
    code_id = _property_value(cls, "plugin_id", constants)
    code_version = _property_value(cls, "version", constants)
    plugin_id = code_id or folder

    # naming
    if not PLUGIN_ID_RE.match(plugin_id):
        add("naming", f"plugin_id {plugin_id!r} must match {PLUGIN_ID_RE.pattern}", plugin_id)
    if not starter and code_id and code_id != folder:
        add("naming", f"folder {folder!r} must equal plugin_id {code_id!r}", plugin_id)
    if code_id is None:
        add("naming", "plugin_id property must return a string literal or a module constant", plugin_id)

    # manifest
    manifest_path = plugin_dir / "plugin.json"
    if not manifest_path.is_file():
        add("manifest", "plugin.json is missing", plugin_id)
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            manifest = None
            add("manifest", f"plugin.json is not valid JSON: {exc}", plugin_id)
        if isinstance(manifest, dict):
            missing = [k for k in MANIFEST_REQUIRED if not str(manifest.get(k) or "").strip()]
            if missing:
                add("manifest", f"plugin.json missing keys: {', '.join(missing)}", plugin_id)
            if code_id and manifest.get("plugin_id") != code_id:
                add("manifest", f"plugin.json plugin_id {manifest.get('plugin_id')!r} != plugin.py {code_id!r}", plugin_id)
            if code_version and manifest.get("version") != code_version:
                add("manifest", f"plugin.json version {manifest.get('version')!r} != plugin.py {code_version!r}", plugin_id)
            if manifest.get("version") and not SEMVER_RE.match(str(manifest["version"])):
                add("manifest", f"version {manifest['version']!r} is not semver (1.2.3)", plugin_id)

    # settings page
    prefixes = _url_prefixes(plugin_dir)
    routes = [r for r in _settings_routes(plugin_dir) if _route_resolves_to_settings_url(r[3], plugin_id, prefixes)]
    standard = _uses_standard_settings_route(plugin_dir) and f"/admin/plugins/{plugin_id}" in prefixes
    if not routes and not standard:
        add(
            "settings-route",
            f"no GET route served at /admin/plugins/{plugin_id}/settings (check the route path and the "
            "blueprint url_prefix; the URL must use the plugin id, not a legacy name)",
            plugin_id,
        )
    else:
        for path, func, decorators, _route in routes:
            if not any(GUARD_RE.search(d) for d in decorators):
                rel = path.relative_to(plugin_dir).as_posix()
                add(
                    "settings-guard",
                    f"{rel}:{func} needs PLUGIN_MANAGE_PERMISSION (or plugin_admin_route_wrapper / system_manager_required)",
                    plugin_id,
                )

    templates = [p for p in plugin_dir.rglob("settings.html") if "__pycache__" not in p.parts]
    if not templates:
        add("settings-template", "templates/settings.html is missing", plugin_id)
    else:
        text = "\n".join(t.read_text(encoding="utf-8", errors="replace") for t in templates)
        if "core/layout.html" not in text:
            add("settings-template", "settings.html must extend core/layout.html", plugin_id)
        if "plugins/_plugin_info_card.html" not in text:
            add("settings-template", 'settings.html must {% include "plugins/_plugin_info_card.html" %}', plugin_id)

    # docs + tests
    readme = plugin_dir / "README.md"
    if not readme.is_file() or len(readme.read_text(encoding="utf-8", errors="replace").strip()) < MIN_README_CHARS:
        add("readme", f"README.md missing or shorter than {MIN_README_CHARS} characters", plugin_id)
    if not _has_tests(plugin_dir, plugin_id):
        add("tests", f"no tests: add plugins/{plugin_id}/tests/test_*.py", plugin_id)

    # registration
    if starter:
        pass
    elif plugin_id not in _bundled_ids():
        add("bundled", "add the id to BUNDLED_PLUGIN_IDS in plugins/metadata.py", plugin_id)

    return findings


def discover_plugins() -> list[tuple[Path, bool]]:
    plugins = [
        (p, False)
        for p in sorted(PLUGINS_DIR.iterdir())
        if p.is_dir() and not p.name.startswith((".", "_")) and (p / "plugin.py").exists()
    ]
    if STARTER_DIR.is_dir():
        plugins.append((STARTER_DIR, True))
    return plugins


def run(only: str | None = None) -> tuple[list[Finding], list[str]]:
    """Return (blocking findings, stale exemption messages)."""
    all_findings: list[Finding] = []
    seen_ids: set[str] = set()
    for plugin_dir, starter in discover_plugins():
        findings = check_plugin(plugin_dir, starter=starter)
        ids = {f.plugin for f in findings} or {plugin_dir.name}
        seen_ids |= ids | {plugin_dir.name}
        if only and only not in ids | {plugin_dir.name}:
            continue
        all_findings.extend(findings)

    # Folder-name for the starter is "sample_plugin_package" but its id is "sample_plugin".
    blocking = [f for f in all_findings if (f.plugin, f.rule) not in EXEMPT]
    stale = []
    if not only:
        fired = {(f.plugin, f.rule) for f in all_findings}
        for key, reason in sorted(EXEMPT.items()):
            if key not in fired:
                stale.append(f"stale exemption {key[0]}/{key[1]} ({reason}): the rule now passes, delete the entry")
    return blocking, stale


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plugin", help="check one plugin id only")
    parser.add_argument("--github", action="store_true", help="emit GitHub ::error annotations")
    args = parser.parse_args(argv)

    blocking, stale = run(args.plugin)
    for f in blocking:
        line = f"[{f.plugin}] {f.rule}: {f.message}"
        print(f"::error title=Plugin contract::{line}" if args.github else line)
    for msg in stale:
        print(f"::error title=Plugin contract::{msg}" if args.github else msg)

    if blocking or stale:
        print(
            "\nPlugin contract violated. See Backoffice/plugins/README.md#plugin-contract-enforced",
            file=sys.stderr,
        )
        return 1
    print(f"Plugin contract OK ({len(discover_plugins())} plugin folders checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
