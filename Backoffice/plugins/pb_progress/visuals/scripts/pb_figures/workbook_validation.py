"""Pre-build checks for SG Report workbooks."""

from __future__ import annotations

from pathlib import Path

from .config import resolve_excel
from .data import load_mapping
from .layouts import section_has_indicators
from .report_meta import report_parts


def sections_without_indicators(excel_path: Path | str | None = None) -> list[str]:
    """Return configured section codes that have no Mapping rows."""
    path = resolve_excel(excel_path)
    mapping = load_mapping(path)
    missing: list[str] = []
    seen: set[str] = set()
    for part in report_parts(path):
        for section in part["sections"]:
            if section in seen:
                continue
            seen.add(section)
            if not section_has_indicators(mapping, section):
                missing.append(section)
    return missing
