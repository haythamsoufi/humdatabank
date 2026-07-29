#!/usr/bin/env python3
"""
CI guard: fail when app/tests/ops files reference moved scripts at flat paths.

After ``scripts/`` reorganization, runnable modules live in subfolders
(``i18n/``, ``seeding/``, ``imports/``, …). References like
``scripts/compile_translations.py`` or ``from scripts.seed_email_templates import …``
break at runtime but are invisible when tests mock the old module path.

Usage (from repo root or Backoffice/):
    python Backoffice/scripts/ci/check_script_references.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

BACKOFFICE = Path(__file__).resolve().parents[2]
SCRIPTS = BACKOFFICE / "scripts"
REPO_ROOT = BACKOFFICE.parent

ACTIVE_CATEGORIES = frozenset(
    {"ai", "assets", "ci", "codemods", "dev", "i18n", "imports", "ops", "seeding"}
)

SCAN_PATHS: list[Path] = [
    BACKOFFICE / "app",
    BACKOFFICE / "tests",
    BACKOFFICE / "entrypoint.sh",
    BACKOFFICE / "Dockerfile",
    REPO_ROOT / ".github" / "workflows" / "backoffice-ci.yml",
    REPO_ROOT / ".github" / "workflows" / "security-scan.yml",
    REPO_ROOT / ".github" / "workflows" / "deploy-to-webapp.yml",
    REPO_ROOT / "azure-webapp" / "azure_webapp_run_script.ps1",
]

# Flat ``scripts/<name>.py`` path (not ``scripts/i18n/...``).
FLAT_SCRIPT_PATH = re.compile(r"""(?<![/\w])scripts/([a-z_0-9]+)\.py""", re.IGNORECASE)
# ``from scripts.<module> import`` or ``patch("scripts.<module>.…")`` — single segment only.
FLAT_SCRIPT_MODULE = re.compile(
    r"""
    (?:
        from\s+scripts\.([a-z_0-9]+)\s+import
      | patch\(\s*["']scripts\.([a-z_0-9]+)\.
    )
    """,
    re.VERBOSE,
)

SKIP_SUFFIXES = {".pyc", ".mo", ".pot", ".po"}


def _basename_index() -> dict[str, list[str]]:
    """Map ``compile_translations.py`` -> ``['i18n/compile_translations.py']``."""
    index: dict[str, list[str]] = {}
    for cat in sorted(ACTIVE_CATEGORIES):
        folder = SCRIPTS / cat
        if not folder.is_dir():
            continue
        for path in folder.rglob("*.py"):
            rel = path.relative_to(SCRIPTS).as_posix()
            index.setdefault(path.name, []).append(rel)
    return index


def _iter_source_files(root: Path):
    if root.is_file():
        yield root
        return
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if "__pycache__" in path.parts:
            continue
        if path.suffix in {".py", ".sh", ".yml", ".yaml", ".ps1", ".md"} or path.name == "Dockerfile":
            yield path


def _is_stale_flat_name(name: str, index: dict[str, list[str]]) -> str | None:
    filename = f"{name}.py" if not name.endswith(".py") else name
    if (SCRIPTS / filename).is_file():
        return None
    locations = index.get(filename if filename.endswith(".py") else f"{name}.py", [])
    if not locations:
        return None
    return locations[0] if len(locations) == 1 else ", ".join(locations)


def scan_file(path: Path, index: dict[str, list[str]]) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{path}: could not read: {exc}"]

    rel = path.relative_to(REPO_ROOT).as_posix() if path.is_relative_to(REPO_ROOT) else str(path)
    errors: list[str] = []

    for match in FLAT_SCRIPT_PATH.finditer(text):
        hint = _is_stale_flat_name(match.group(1), index)
        if hint:
            errors.append(
                f"{rel}: stale path 'scripts/{match.group(1)}.py' — use 'scripts/{hint}'"
            )

    for match in FLAT_SCRIPT_MODULE.finditer(text):
        module = match.group(1) or match.group(2)
        hint = _is_stale_flat_name(module, index)
        if hint:
            category = hint.split("/", 1)[0]
            errors.append(
                f"{rel}: stale import/patch 'scripts.{module}' — "
                f"use 'scripts.{category}.{module.replace('.py', '')}'"
            )

    return errors


def main() -> int:
    index = _basename_index()
    all_errors: list[str] = []

    for scan_root in SCAN_PATHS:
        if not scan_root.exists():
            continue
        for path in _iter_source_files(scan_root):
            all_errors.extend(scan_file(path, index))

    if all_errors:
        print("[script-refs] Stale script references found:\n", file=sys.stderr)
        for err in sorted(all_errors):
            print(f"  • {err}", file=sys.stderr)
        print(
            "\n[script-refs] See Backoffice/scripts/README.md for the current layout.",
            file=sys.stderr,
        )
        return 1

    print("[script-refs] OK — no stale flat script references in app/tests/ops wiring.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
