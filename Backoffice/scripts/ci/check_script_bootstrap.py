#!/usr/bin/env python3
"""
CI guard: fail when scripts in subfolders still resolve Backoffice/ one level short.

After ``scripts/`` reorganization, runnable modules live one level deeper
(``scripts/i18n/``, ``scripts/ops/``, …). Patterns that worked at
``scripts/foo.py`` — ``dirname(script_dir)``, ``Path(__file__).parent.parent`` —
now point at ``scripts/`` instead of ``Backoffice/``.

Usage (from Backoffice/):
    python scripts/ci/check_script_bootstrap.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

BACKOFFICE = Path(__file__).resolve().parents[2]
SCRIPTS = BACKOFFICE / "scripts"

SCAN_CATEGORIES = frozenset(
    {"ai", "assets", "ci", "dev", "i18n", "imports", "ops", "seeding"}
)

# ``backoffice_dir = os.path.dirname(script_dir)`` in a subfolder script → scripts/, not Backoffice/.
SINGLE_DIRNAME_BOOTSTRAP = re.compile(
    r"(?:backoffice|backend)_dir\s*=\s*os\.path\.dirname\(script_dir\)"
)

# ``Path(__file__).resolve().parent.parent / "docs"`` from scripts/i18n/ → scripts/docs.
SHALLOW_DOCS_PATH = re.compile(
    r'Path\(__file__\)\.resolve\(\)\.parent\.parent\s*/\s*[\'"]docs[\'"]'
)

# ``backoffice_root = Path(__file__).resolve().parent.parent`` (no third .parent).
SHALLOW_BACKOFFICE_ROOT = re.compile(
    r"(?:backoffice_root|_BACKOFFICE_ROOT)\s*=\s*Path\(__file__\)\.resolve\(\)\.parent\.parent\s*$",
    re.MULTILINE,
)

# Live PO/MO tree is Backoffice/translations/, not app/translations/.
WRONG_TRANSLATIONS_TREE = re.compile(
    r'[\'"]app[\'"]\s*/\s*[\'"]translations[\'"]|[\'"]app/translations[\'"]'
)


def _iter_scripts() -> list[Path]:
    paths: list[Path] = []
    for cat in sorted(SCAN_CATEGORIES):
        folder = SCRIPTS / cat
        if not folder.is_dir():
            continue
        paths.extend(sorted(folder.rglob("*.py")))
    return paths


def scan_file(path: Path) -> list[str]:
    if path.name == "check_script_bootstrap.py":
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{path}: could not read: {exc}"]

    rel = path.relative_to(BACKOFFICE).as_posix()
    errors: list[str] = []

    if SINGLE_DIRNAME_BOOTSTRAP.search(text):
        errors.append(
            f"{rel}: backoffice_dir = os.path.dirname(script_dir) resolves to scripts/ "
            f"— use _bootstrap.setup_cli_paths(__file__) or Path(__file__).resolve().parents[2]"
        )

    if SHALLOW_DOCS_PATH.search(text):
        errors.append(
            f"{rel}: Path(__file__).parent.parent / 'docs' resolves to scripts/docs "
            f"— use .parents[2] / 'docs'"
        )

    if SHALLOW_BACKOFFICE_ROOT.search(text):
        errors.append(
            f"{rel}: backoffice root uses .parent.parent (scripts/) "
            f"— use .parents[2] for Backoffice/"
        )

    if "i18n" in path.parts and WRONG_TRANSLATIONS_TREE.search(text):
        errors.append(
            f"{rel}: references app/translations — live tree is Backoffice/translations/"
        )

    return errors


def main() -> int:
    all_errors: list[str] = []
    for path in _iter_scripts():
        all_errors.extend(scan_file(path))

    if all_errors:
        print("[script-bootstrap] Stale one-level-short path resolution found:\n", file=sys.stderr)
        for err in sorted(all_errors):
            print(f"  • {err}", file=sys.stderr)
        print(
            "\n[script-bootstrap] See scripts/_bootstrap.py — use setup_cli_paths(__file__).",
            file=sys.stderr,
        )
        return 1

    print("[script-bootstrap] OK — no one-level-short Backoffice root resolution in scripts/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
