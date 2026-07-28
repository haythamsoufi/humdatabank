"""Shared path helpers for Backoffice/scripts (any subfolder depth)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def backoffice_dir(from_file: str | Path | None = None) -> Path:
    """Return the Backoffice/ root directory."""
    start = Path(from_file or __file__).resolve()
    for parent in (start.parent, *start.parents):
        if (parent / "app").is_dir() and (parent / "config.py").is_file():
            return parent
    raise RuntimeError(f"Cannot locate Backoffice root from {start}")


def scripts_dir(from_file: str | Path | None = None) -> Path:
    return backoffice_dir(from_file) / "scripts"


def imports_dir(from_file: str | Path | None = None) -> Path:
    return scripts_dir(from_file) / "imports"


def ensure_imports_in_path(from_file: str | Path | None = None) -> str:
    """Insert scripts/imports on sys.path for import_fdrs_form_data, import_upr_excel_data, etc."""
    path = str(imports_dir(from_file))
    if path not in sys.path:
        sys.path.insert(0, path)
    return path


def ensure_backoffice_in_path(from_file: str | Path | None = None) -> str:
    """Insert Backoffice/ on sys.path so ``from app import …`` works in CLI scripts."""
    path = str(backoffice_dir(from_file))
    if path not in sys.path:
        sys.path.insert(0, path)
    return path


def setup_cli_paths(from_file: str | Path) -> tuple[Path, Path]:
    """Standard bootstrap for runnable scripts: Backoffice + imports on sys.path."""
    root = backoffice_dir(from_file)
    ensure_backoffice_in_path(from_file)
    ensure_imports_in_path(from_file)
    return root, imports_dir(from_file)
