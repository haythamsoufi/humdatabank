"""Load UI translations and section order from SG Report.xlsx."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from .config import resolve_excel
from .defaults import default_translations_bundle

EXCEL_TO_LANG = {
    "EN": "English",
    "FR": "French",
    "SP": "Spanish",
    "AR": "Arabic",
}

REQUIRED_SHEETS = ("Translations", "SectionOrder")


def _translation_cell(value: object) -> str | None:
    """Return stripped cell text, or None for blank/NaN cells."""
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


class TranslationsError(RuntimeError):
    """Raised when required translation sheets are missing from the Excel workbook."""


def _parse_translations_sheet(trans_df: pd.DataFrame) -> dict[str, dict[str, str]]:
    if trans_df.empty or "id" not in trans_df.columns:
        return {}

    translations: dict[str, dict[str, str]] = {}
    for _, row in trans_df.iterrows():
        code = str(row.get("id", "") or "").strip()
        if not code:
            continue
        entry: dict[str, str] = {}
        for excel_col, lang in EXCEL_TO_LANG.items():
            if excel_col in trans_df.columns:
                text = _translation_cell(row.get(excel_col))
                if text:
                    entry[lang] = text
        if entry:
            translations[code] = entry
    return translations


def _parse_section_order_sheet(order_df: pd.DataFrame) -> tuple[dict[str, list[str]], tuple[str, ...]]:
    if order_df.empty or not {"part", "section", "order"}.issubset(order_df.columns):
        return {}, ()

    parsed: dict[str, list[tuple[int, str]]] = {}
    part_min_order: dict[str, int] = {}
    for _, row in order_df.iterrows():
        part = str(row.get("part", "") or "").strip().lower()
        section = str(row.get("section", "") or "").strip()
        order = row.get("order")
        if not part or not section or pd.isna(order):
            continue
        order_int = int(order)
        parsed.setdefault(part, []).append((order_int, section))
        part_min_order[part] = min(part_min_order.get(part, order_int), order_int)

    section_order = {part: [section for _, section in sorted(items)] for part, items in parsed.items()}
    if not section_order:
        return {}, ()

    parts_order = tuple(
        sorted(part_min_order.keys(), key=lambda part_id: (part_min_order[part_id], part_id))
    )
    return section_order, parts_order


@lru_cache(maxsize=8)
def _load_bundle(
    excel_path_str: str,
) -> tuple[dict[str, dict[str, str]], dict[str, list[str]], tuple[str, ...]]:
    path = Path(excel_path_str)
    if not path.exists():
        raise TranslationsError(f"Excel workbook not found: {path}")

    default_translations, default_section_order, default_parts_order = default_translations_bundle()
    translations = dict(default_translations)
    section_order = dict(default_section_order)
    parts_order = default_parts_order

    try:
        trans_df = pd.read_excel(path, sheet_name="Translations", keep_default_na=False)
    except ValueError:
        trans_df = pd.DataFrame()
    except (PermissionError, OSError) as exc:
        raise TranslationsError(f"Cannot read {path.name}: {exc}") from exc
    else:
        parsed_translations = _parse_translations_sheet(trans_df)
        if parsed_translations:
            translations.update(parsed_translations)

    try:
        order_df = pd.read_excel(path, sheet_name="SectionOrder", keep_default_na=False)
    except ValueError:
        order_df = pd.DataFrame()
    except (PermissionError, OSError) as exc:
        raise TranslationsError(f"Cannot read {path.name}: {exc}") from exc
    else:
        parsed_section_order, parsed_parts_order = _parse_section_order_sheet(order_df)
        if parsed_section_order:
            section_order = parsed_section_order
        if parsed_parts_order:
            parts_order = parsed_parts_order

    if not translations:
        raise TranslationsError(f"{path.name} → Translations sheet has no usable rows")

    if not section_order:
        raise TranslationsError(f"{path.name} → SectionOrder sheet has no usable rows")

    return translations, section_order, parts_order


def clear_cache() -> None:
    _load_bundle.cache_clear()


def load_translations(excel_path: Path | str | None = None) -> dict[str, dict[str, str]]:
    translations, _, _ = _load_bundle(str(resolve_excel(excel_path)))
    return translations


def load_section_order(excel_path: Path | str | None = None) -> dict[str, list[str]]:
    _, section_order, _ = _load_bundle(str(resolve_excel(excel_path)))
    return section_order


def load_parts_order(excel_path: Path | str | None = None) -> tuple[str, ...]:
    """Report part ids (e.g. cc, sp, ef) sorted by the lowest SectionOrder row per part."""
    _, _, parts_order = _load_bundle(str(resolve_excel(excel_path)))
    return parts_order


def t(code: str, language: str, excel_path: Path | str | None = None) -> str:
    """Return translated string for `code` and `language`, falling back to English."""
    translations = load_translations(excel_path)
    entry = translations.get(code, {})
    return entry.get(language) or entry.get("English") or ""


def section_title_for(section: str, language: str, excel_path: Path | str | None = None) -> str:
    return t(f"section.{section}", language, excel_path)
