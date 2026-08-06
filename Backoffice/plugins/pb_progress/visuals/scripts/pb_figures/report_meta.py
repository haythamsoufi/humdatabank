"""Metadata and helpers for Quarto report assembly."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from .calculations import part_title, section_title
from .config import resolve_excel
from .languages import LANGUAGES
from .layouts import section_codes
from .translations import load_parts_order, load_section_order, section_title_for, t

_DEFAULT_REPORT_AUTHOR = "IFRC — FDS Team"
_AUTHOR_LABEL_FALLBACK = {
    "English": "Author",
    "French": "Auteur",
    "Spanish": "Autor",
    "Arabic": "المؤلف",
}
_PUBLISHED_LABEL_FALLBACK = {
    "English": "Published",
    "French": "Publié",
    "Spanish": "Publicado",
    "Arabic": "تاريخ النشر",
}
_TOC_TITLE_FALLBACK = {
    "English": "Contents",
    "French": "Sommaire",
    "Spanish": "Contenido",
    "Arabic": "المحتويات",
}
_TOC_EXPAND_FALLBACK = {
    "English": "Expand table of contents",
    "French": "Développer le sommaire",
    "Spanish": "Expandir índice",
    "Arabic": "توسيع جدول المحتويات",
}
_TOC_COLLAPSE_FALLBACK = {
    "English": "Collapse table of contents",
    "French": "Réduire le sommaire",
    "Spanish": "Contraer índice",
    "Arabic": "طي جدول المحتويات",
}
_MONTH_NAMES: dict[str, list[str]] = {
    "English": [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ],
    "French": [
        "janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre",
    ],
    "Spanish": [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ],
    "Arabic": [
        "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
        "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
    ],
}

CC_PART_ID = "cc"


def section_uses_part_heading_only(part_id: str) -> bool:
    """Cross-cutting uses ui.part.cc only; section.CC* titles are not shown as subheadings."""
    return str(part_id or "").strip().lower() == CC_PART_ID


def cross_cutting_section(section: str) -> bool:
    """True for CC1, CC2, … (all sections under the cc report part)."""
    return str(section or "").strip().upper().startswith("CC")


def report_parts(excel_path: Path | None = None) -> list[dict]:
    """Return ordered report parts and their sections from SPEF / build config."""
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
    return {lang: t("report.title", lang, excel_path) for lang in LANGUAGES}


def report_author(language: str, excel_path: Path | None = None) -> str:
    return t("report.author", language, excel_path) or _DEFAULT_REPORT_AUTHOR


def report_author_label(language: str, excel_path: Path | None = None) -> str:
    return t("ui.author", language, excel_path) or _AUTHOR_LABEL_FALLBACK.get(language, "Author")


def report_published_label(language: str, excel_path: Path | None = None) -> str:
    return t("ui.published", language, excel_path) or _PUBLISHED_LABEL_FALLBACK.get(language, "Published")


def report_toc_label(language: str, excel_path: Path | None = None) -> str:
    return t("ui.contents", language, excel_path) or _TOC_TITLE_FALLBACK.get(language, "Contents")


def report_toc_expand_label(language: str, excel_path: Path | None = None) -> str:
    return t("ui.toc_expand", language, excel_path) or _TOC_EXPAND_FALLBACK.get(language, "Expand table of contents")


def report_toc_collapse_label(language: str, excel_path: Path | None = None) -> str:
    return t("ui.toc_collapse", language, excel_path) or _TOC_COLLAPSE_FALLBACK.get(language, "Collapse table of contents")


def format_report_date(language: str, when: date | None = None) -> str:
    """Localized long date for the Quarto title block (D MMMM YYYY style)."""
    when = when or date.today()
    month = _MONTH_NAMES.get(language, _MONTH_NAMES["English"])[when.month - 1]
    if language == "Spanish":
        return f"{when.day} de {month} de {when.year}"
    return f"{when.day} {month} {when.year}"


def report_header_meta(
    languages: tuple[str, ...] | list[str],
    excel_path: Path | None = None,
    *,
    published_on: date | None = None,
) -> dict[str, dict[str, str]]:
    """Per-language strings for the HTML report title block."""
    path = resolve_excel(excel_path)
    published_on = published_on or date.today()
    titles = report_titles(path)
    meta: dict[str, dict[str, str]] = {}
    for language in languages:
        meta[language] = {
            "title": titles.get(language) or titles.get("English", ""),
            "author": report_author(language, path),
            "authorLabel": report_author_label(language, path),
            "publishedLabel": report_published_label(language, path),
            "date": format_report_date(language, published_on),
            "contentsLabel": report_toc_label(language, path),
            "tocExpandLabel": report_toc_expand_label(language, path),
            "tocCollapseLabel": report_toc_collapse_label(language, path),
        }
    return meta


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
