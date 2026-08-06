"""Load UI translations and section order for P&B report builds."""

from __future__ import annotations

import json
import os
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

# Tie-break when multiple parts share the same minimum order value (legacy per-part rows).
_PART_RANK = {"cc": 0, "sp": 1, "ef": 2}


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


def _parse_section_order_rows(rows: list[dict[str, object]]) -> tuple[dict[str, list[str]], tuple[str, ...]]:
    parsed: dict[str, list[tuple[int, str]]] = {}
    part_min_order: dict[str, int] = {}
    for row in rows:
        part = str(row.get("part", "") or "").strip().lower()
        section = str(row.get("section", "") or "").strip()
        order = row.get("order")
        if not part or not section or order is None or (isinstance(order, float) and pd.isna(order)):
            continue
        order_int = int(order)
        parsed.setdefault(part, []).append((order_int, section))
        part_min_order[part] = min(part_min_order.get(part, order_int), order_int)

    section_order = {part: [section for _, section in sorted(items)] for part, items in parsed.items()}
    if not section_order:
        return {}, ()

    parts_order = tuple(
        sorted(
            part_min_order.keys(),
            key=lambda part_id: (part_min_order[part_id], _PART_RANK.get(part_id, 99), part_id),
        )
    )
    return section_order, parts_order


def _section_order_from_env() -> tuple[dict[str, list[str]], tuple[str, ...]] | None:
    raw = (os.environ.get("PB_REPORT_SECTION_ORDER") or "").strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list):
        return None
    section_order, parts_order = _parse_section_order_rows(payload)
    if not section_order:
        return None
    return section_order, parts_order


def _section_titles_from_env() -> dict[str, dict[str, str]] | None:
    raw = (os.environ.get("PB_REPORT_SECTION_TITLES") or "").strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    result: dict[str, dict[str, str]] = {}
    for code, entry in payload.items():
        if not isinstance(code, str) or not isinstance(entry, dict):
            continue
        langs = {
            str(lang): str(text).strip()
            for lang, text in entry.items()
            if text is not None and str(text).strip()
        }
        if langs:
            result[code] = langs
    return result or None


def _bundle_cache_key(path: Path) -> tuple[str, str, str]:
    return (
        str(path.resolve()),
        os.environ.get("PB_REPORT_SECTION_ORDER", ""),
        os.environ.get("PB_REPORT_SECTION_TITLES", ""),
    )


@lru_cache(maxsize=8)
def _load_bundle(
    cache_key: tuple[str, str, str],
) -> tuple[dict[str, dict[str, str]], dict[str, list[str]], tuple[str, ...]]:
    excel_path_str, _section_order_key, _section_titles_key = cache_key
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

    env_titles = _section_titles_from_env()
    if env_titles:
        translations.update(env_titles)

    env_order = _section_order_from_env()
    if env_order is not None:
        section_order, parts_order = env_order

    if not translations:
        raise TranslationsError(f"{path.name} → Translations sheet has no usable rows")

    if not section_order:
        raise TranslationsError(f"{path.name} → section order is empty")

    return translations, section_order, parts_order


def clear_cache() -> None:
    _load_bundle.cache_clear()


def load_translations(excel_path: Path | str | None = None) -> dict[str, dict[str, str]]:
    translations, _, _ = _load_bundle(_bundle_cache_key(resolve_excel(excel_path)))
    return translations


def load_section_order(excel_path: Path | str | None = None) -> dict[str, list[str]]:
    _, section_order, _ = _load_bundle(_bundle_cache_key(resolve_excel(excel_path)))
    return section_order


def load_parts_order(excel_path: Path | str | None = None) -> tuple[str, ...]:
    """Report part ids (e.g. cc, sp, ef) sorted by the lowest order row per part."""
    _, _, parts_order = _load_bundle(_bundle_cache_key(resolve_excel(excel_path)))
    return parts_order


def t(code: str, language: str, excel_path: Path | str | None = None) -> str:
    """Return translated string for `code` and `language`, falling back to English."""
    translations = load_translations(excel_path)
    entry = translations.get(code, {})
    return entry.get(language) or entry.get("English") or ""


def section_title_for(section: str, language: str, excel_path: Path | str | None = None) -> str:
    return t(f"section.{section}", language, excel_path)
