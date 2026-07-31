"""Metadata and helpers for Quarto report assembly."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .calculations import part_title, section_title
from .config import resolve_excel
from .languages import LANGUAGES
from .layouts import section_codes
from .translations import load_parts_order, load_section_order, section_title_for


def report_parts(excel_path: Path | None = None) -> list[dict]:
    """Return ordered report parts and their sections from SectionOrder."""
    path = resolve_excel(excel_path)
    order = load_section_order(path)
    parts: list[dict] = []
    for part_id in load_parts_order(path):
        sections = list(order.get(part_id, []))
        if not sections:
            continue
        parts.append(
            {
                "id": part_id,
                "title": {lang: part_title(part_id, lang, path) for lang in LANGUAGES},
                "sections": sections,
            }
        )
    return parts


def report_titles(excel_path: Path | None = None) -> dict[str, str]:
    from .translations import t

    return {lang: t("report.title", lang, excel_path) for lang in LANGUAGES}


def report_section_assets_dir(root: Path, language: str, section: str) -> Path:
    """Chart-only PNG assets for one dashboard section."""
    return root / "figures" / language / section


def report_section_assets_ref(language: str, section: str) -> str:
    """URL prefix for chart assets embedded in HTML dashboards."""
    return f"figures/{language}/{section}"


def section_titles(
    model: pd.DataFrame,
    language: str,
    excel_path: Path | None = None,
) -> dict[str, str]:
    """Map section code (EF1, SP1, …) to localized dashboard title."""
    titles: dict[str, str] = {}
    for section in section_codes(excel_path):
        title = section_title_for(section, language, excel_path)
        if title:
            titles[section] = title
            continue
        subset = model[model["section"].astype(str).str.strip() == section]
        if subset.empty:
            titles[section] = section
            continue
        meta = subset.groupby("ID").first().iloc[0]
        fallback = section_title(meta, language)
        titles[section] = fallback or section
    return titles


def load_model(excel: Path | None = None) -> pd.DataFrame:
    from .data import build_model

    return build_model(resolve_excel(excel))
