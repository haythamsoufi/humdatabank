"""Metadata and helpers for Quarto report assembly."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .calculations import part_title, section_title
from .config import resolve_excel
from .languages import LANGUAGES
from .layouts import SECTION_CODES
from .translations import load_section_order, t


def _sections_for_part(part_id: str, excel_path: Path | None = None) -> list[str]:
    order = load_section_order(excel_path)
    return list(order.get(part_id, []))


def report_parts(excel_path: Path | None = None) -> list[dict]:
    path = resolve_excel(excel_path)
    return [
        {
            "id": "sp",
            "title": {lang: part_title("sp", lang) for lang in LANGUAGES},
            "sections": _sections_for_part("sp", path),
        },
        {
            "id": "ef",
            "title": {lang: part_title("ef", lang) for lang in LANGUAGES},
            "sections": _sections_for_part("ef", path),
        },
    ]


def report_titles(excel_path: Path | None = None) -> dict[str, str]:
    return {lang: t("report.title", lang, excel_path) for lang in LANGUAGES}


def report_section_assets_dir(root: Path, language: str, section: str) -> Path:
    """Chart-only PNG assets for one dashboard section."""
    return root / "report" / "figures" / language / section


def report_section_assets_ref(language: str, section: str) -> str:
    """URL prefix for chart assets embedded in HTML dashboards."""
    return f"figures/{language}/{section}"


def section_titles(model: pd.DataFrame, language: str) -> dict[str, str]:
    """Map section code (EF1, SP1, …) to localized dashboard title."""
    titles: dict[str, str] = {}
    for section in SECTION_CODES:
        subset = model[model["section"] == section]
        if subset.empty:
            titles[section] = section
            continue
        meta = subset.groupby("ID").first().iloc[0]
        titles[section] = section_title(meta, language)
    return titles


def load_model(excel: Path | None = None) -> pd.DataFrame:
    from .data import build_model

    return build_model(resolve_excel(excel))
