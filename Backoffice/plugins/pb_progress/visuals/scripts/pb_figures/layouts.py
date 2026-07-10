"""Per-section dashboard layout derived from SG Report.xlsx → Mapping sheet."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .calculations import chartable_value

from .translations import TranslationsError, load_parts_order, load_section_order

SECTION_COLUMN = "Strategic Priority / Enabling Function"

# Fallback when SectionOrder sheet is unavailable (CLI choices, tests).
KNOWN_SECTION_CODES: tuple[str, ...] = (
    "CC1",
    "EF1", "EF2", "EF3", "EF4",
    "SP1", "SP2", "SP3", "SP4", "SP5",
)

SECTION_FOOTNOTE_KEYS: dict[str, str] = {
    "SP1": "sp1",
    "SP2": "sp2",
    "EF4": "ef4",
}

# Temporarily hidden indicators by section (see README → Maintenance).
TEMPORARILY_HIDDEN: dict[str, frozenset[str]] = {}

# Sections where Distinct indicators use historical line charts instead of donuts.
LINE_CHART_SECTIONS: frozenset[str] = frozenset({"SP4"})


def section_codes(excel_path: Path | str | None = None) -> list[str]:
    """All dashboard section codes in SectionOrder sheet order."""
    try:
        order = load_section_order(excel_path)
        codes: list[str] = []
        for part_id in load_parts_order(excel_path):
            codes.extend(order.get(part_id, []))
        if codes:
            return list(dict.fromkeys(codes))
    except TranslationsError:
        pass
    return list(KNOWN_SECTION_CODES)


# Backwards-compatible alias used across the pipeline.
SECTION_CODES: list[str] = list(KNOWN_SECTION_CODES)


def _normalize_id(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def _section_column_name(frame: pd.DataFrame) -> str:
    if SECTION_COLUMN in frame.columns:
        return SECTION_COLUMN
    mapped = f"{SECTION_COLUMN}_map"
    if mapped in frame.columns:
        return mapped
    return "section"


def mapping_indicator_rows(mapping: pd.DataFrame, section: str) -> pd.DataFrame:
    """Mapping rows for one section in Excel row order (first ID occurrence wins)."""
    section_col = _section_column_name(mapping)
    subset = mapping[mapping[section_col].astype(str).str.strip() == section].copy()
    if subset.empty:
        return subset

    subset["_row_order"] = range(len(subset))
    subset["ID"] = subset["ID"].map(_normalize_id)
    subset = subset[subset["ID"].notna()]
    return subset.drop_duplicates(subset=["ID"], keep="first").sort_values("_row_order")


NS_TABLE_STANDARD = "standard"
NS_TABLE_IMPLEMENTING_COUNT = "implementing_count"


def is_distinct_ns_count_indicator(indicator_type: str | None, unit: str | None) -> bool:
    type_text = str(indicator_type or "").strip()
    unit_text = str(unit or "").strip()
    return type_text == "Distinct" and unit_text == "NSs"


def ns_table_mode(indicator_type: str | None, unit: str | None) -> str:
    """Table layout below line charts.

    standard: year + reporting (Count) + implementing (Implementing)
    implementing_count: year + reporting row labelled as reporting but showing Implementing
    """
    if is_distinct_ns_count_indicator(indicator_type, unit):
        return NS_TABLE_IMPLEMENTING_COUNT
    return NS_TABLE_STANDARD


def cumulative_table_rows(item: dict) -> tuple[bool, bool]:
    """Return (show_reporting_row, show_implementing_row) for a cumulative payload item."""
    if not item.get("show_ns_breakdown", True):
        return False, False
    if item.get("ns_table_mode") == NS_TABLE_IMPLEMENTING_COUNT:
        return True, False
    return True, True


def show_ns_breakdown(indicator_type: str | None, unit: str | None) -> bool:
    """Whether the footer includes NS rows below the year row."""
    return True


def _is_line_indicator(indicator_type: str | None, unit: str | None, *, ef_section: bool) -> bool:
    type_text = str(indicator_type or "").strip()
    unit_text = str(unit or "").strip()
    if not type_text or type_text.lower() == "nan":
        return False
    if ef_section:
        return True
    if type_text == "Cumulative":
        return True
    return type_text == "Distinct" and unit_text == "NSs"


def _is_donut_indicator(indicator_type: str | None, unit: str | None) -> bool:
    type_text = str(indicator_type or "").strip()
    unit_text = str(unit or "").strip()
    return type_text == "Distinct" and unit_text != "NSs"


def _chunk_indicator_pairs(ids: list[str]) -> list[list[str]]:
    """Group donut indicators into rows of up to two."""
    return [ids[index : index + 2] for index in range(0, len(ids), 2)]


def build_section_layout(section: str, mapping: pd.DataFrame) -> dict:
    """Build chart layout for one section from Mapping row order and Type/Unit."""
    rows = mapping_indicator_rows(mapping, section)
    ef_section = section.startswith("EF")

    cumulative_ids: list[str] = []
    donut_ids: list[str] = []

    for _, row in rows.iterrows():
        indicator_id = row["ID"]
        indicator_type = row.get("Type")
        unit = row.get("Unit")
        if _is_line_indicator(indicator_type, unit, ef_section=ef_section) or (
            section in LINE_CHART_SECTIONS and _is_donut_indicator(indicator_type, unit)
        ):
            cumulative_ids.append(indicator_id)
        elif not ef_section and _is_donut_indicator(indicator_type, unit):
            donut_ids.append(indicator_id)

    donut_pairs = _chunk_indicator_pairs(donut_ids)

    return {
        "cumulative_ids": cumulative_ids,
        "donut_pairs": donut_pairs,
        "footnote_key": SECTION_FOOTNOTE_KEYS.get(section, "default"),
        "cumulative_weight": max(len(cumulative_ids) * 1.1, 1.5),
        "donut_weight": 0.75,
    }


def visible_indicator_ids(section: str, ids: list[str]) -> list[str]:
    hidden = TEMPORARILY_HIDDEN.get(section, frozenset())
    return [indicator_id for indicator_id in ids if indicator_id not in hidden]


def visible_donut_pairs(section: str, pairs: list[list[str]]) -> list[list[str]]:
    hidden = TEMPORARILY_HIDDEN.get(section, frozenset())
    visible: list[list[str]] = []
    for pair in pairs:
        filtered = [indicator_id for indicator_id in pair if indicator_id not in hidden]
        if filtered:
            visible.append(filtered)
    return visible


def visible_donut_rows(section: str, rows: list[dict]) -> list[dict]:
    hidden = TEMPORARILY_HIDDEN.get(section, frozenset())
    return [row for row in rows if row.get("id") not in hidden]


def visible_donut_pair(section: str, ids: list[str] | None) -> list[str] | None:
    if not ids:
        return None
    hidden = TEMPORARILY_HIDDEN.get(section, frozenset())
    filtered = [indicator_id for indicator_id in ids if indicator_id not in hidden]
    return filtered or None


def mapping_from_model(model: pd.DataFrame) -> pd.DataFrame:
    """One Mapping row per indicator, preserving Excel row order when available."""
    section_col = _section_column_name(model)
    cols = ["ID", "Type", "Unit", "_mapping_order", section_col]
    available = [col for col in cols if col in model.columns]
    meta = model.groupby("ID", as_index=False).first()[available]
    if section_col != SECTION_COLUMN:
        meta = meta.rename(columns={section_col: SECTION_COLUMN})
    if "_mapping_order" in meta.columns:
        return meta.sort_values("_mapping_order")
    return meta


def indicator_has_values(model: pd.DataFrame, section: str, indicator_id: str) -> bool:
    """True when Final contains at least one plottable Value for this indicator."""
    rows = model[
        (model["section"].astype(str).str.strip() == section)
        & (model["ID"].astype(str).str.strip() == str(indicator_id).strip())
    ]
    if rows.empty:
        return False
    return any(chartable_value(raw) is not None for raw in rows["Value"])


def indicators_with_data(model: pd.DataFrame, section: str, ids: list[str]) -> list[str]:
    """Keep Mapping order for all layout indicators, including those without Final values."""
    del model, section  # layout order is authoritative; availability is handled per indicator
    return list(ids)


def section_has_indicators(mapping: pd.DataFrame, section: str) -> bool:
    """True when Mapping defines at least one indicator for the section."""
    return not mapping_indicator_rows(mapping, section).empty
