"""Discover report languages and column mappings from SG Report.xlsx."""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

import pandas as pd

# Column layout in Mapping sheet (header row 3).
LANGUAGE_SPECS: dict[str, dict[str, str]] = {
    "English": {
        "indicator": "English",
        "section": "SP EN",
        "target": "Target",
        "annual_target": "Annual Target",
    },
    "French": {
        "indicator": "French",
        "section": "SP FR",
        "target": "Target",
        "annual_target": "Annual Target",
    },
    "Spanish": {
        "indicator": "Spanish",
        "section": "SP SP",
        "target": "Target",
        "annual_target": "Annual Target",
    },
    "Arabic": {
        "indicator": "Arabic",
        "section": "SP AR",
        "target": "Target AR",
        "annual_target": "Annual Target AR",
    },
}

LANGUAGE_SLUGS = {
    "English": "english",
    "French": "french",
    "Spanish": "spanish",
    "Arabic": "arabic",
}

# Backward-compatible aliases used across the package.
INDICATOR_COLUMNS = tuple(LANGUAGE_SPECS.keys())
LANG_COLUMNS = {lang: spec["indicator"] for lang, spec in LANGUAGE_SPECS.items()}
SP_LANG_COLUMNS = {lang: spec["section"] for lang, spec in LANGUAGE_SPECS.items()}
LANGUAGES = INDICATOR_COLUMNS


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip() == ""


def language_spec(language: str) -> dict[str, str]:
    if language not in LANGUAGE_SPECS:
        raise KeyError(f"Unsupported language: {language}")
    return LANGUAGE_SPECS[language]


def is_rtl(language: str) -> bool:
    return language == "Arabic"


ARABIC_VISUAL_FONT = "Tajawal"
LATIN_DOCX_FONT = "Open Sans"
DEFAULT_VISUAL_FONT = '"Open Sans", "Segoe UI", system-ui, -apple-system, sans-serif'


def visual_font_css(language: str) -> str:
    """CSS font-family stack for dashboard/chart visuals."""
    if language == "Arabic":
        return f'"{ARABIC_VISUAL_FONT}", "Segoe UI", sans-serif'
    return DEFAULT_VISUAL_FONT


def discover_languages(mapping: pd.DataFrame) -> tuple[str, ...]:
    """Return languages with non-empty indicator and section columns in Mapping."""
    found: list[str] = []
    for language, spec in LANGUAGE_SPECS.items():
        indicator_col = spec["indicator"]
        section_col = spec["section"]
        if indicator_col not in mapping.columns or section_col not in mapping.columns:
            continue
        indicator_text = mapping[indicator_col].dropna().astype(str).str.strip()
        section_text = mapping[section_col].dropna().astype(str).str.strip()
        if indicator_text.eq("").all() and section_text.eq("").all():
            continue
        found.append(language)
    return tuple(found) if found else ("English",)


def resolve_build_languages(excel: Path | str | None = None) -> tuple[str, ...]:
    """Languages to build — honours PB_REPORT_LANGUAGE, else Excel-detected languages."""
    requested = (os.environ.get("PB_REPORT_LANGUAGE") or "").strip()
    if requested.lower() not in ("", "all", "*"):
        return (requested,)
    if requested.lower() in ("all", "*"):
        return LANGUAGES
    from .config import resolve_excel
    from .data import load_sg_report

    path = resolve_excel(excel)
    return discover_languages(load_sg_report(path)["mapping"])


def excel_text(row: pd.Series, language: str, field: str) -> str:
    """Read translated text from a Mapping row using the Excel column for `field`."""
    spec = language_spec(language)
    col = spec[field]
    value = row.get(col)

    if _is_empty(value) and language == "Arabic" and field in ("target", "annual_target"):
        fallback_col = language_spec("English")[field]
        value = row.get(fallback_col)

    if _is_empty(value) and language != "English":
        fallback_col = language_spec("English")[field]
        value = row.get(fallback_col)

    if _is_empty(value):
        return ""
    return str(value).strip()


def language_slug(language: str) -> str:
    return LANGUAGE_SLUGS.get(language, language.lower().replace(" ", "-"))


def docx_filename(language: str) -> str:
    return f"pb-report-{language_slug(language)}.docx"


def pdf_filename(language: str) -> str:
    return f"pb-report-{language_slug(language)}.pdf"
