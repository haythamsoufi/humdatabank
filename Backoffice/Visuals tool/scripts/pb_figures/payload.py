"""Build JSON payloads for HTML/SVG dashboard rendering."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .calculations import (
    annual_target_label,
    annual_target_value,
    chartable_value,
    format_donut_value,
    format_value,
    headers,
    indicator_label,
    not_applicable,
    not_available,
    out_of_suffix,
    section_footnote,
    section_title,
    table_row_labels,
    target_label_sp,
    year_display,
)
from .config import DASHBOARD_SIZES
from .styles import style_payload
from .layouts import (
    build_section_layout,
    indicator_has_values,
    indicators_with_data,
    mapping_from_model,
    mapping_indicator_rows,
    show_ns_breakdown,
    visible_donut_pairs,
    visible_indicator_ids,
)


def _indicator_meta_from_mapping(
    mapping: pd.DataFrame,
    section: str,
    indicator_id: str,
) -> pd.Series:
    rows = mapping_indicator_rows(mapping, section)
    match = rows[rows["ID"].astype(str).str.strip() == str(indicator_id).strip()]
    if match.empty:
        raise KeyError(f"Indicator {indicator_id} not found in Mapping for {section}")
    return match.iloc[0]


def _section_meta_row(model: pd.DataFrame, mapping: pd.DataFrame, section: str) -> pd.Series:
    subset = model[model["section"] == section]
    if not subset.empty:
        return subset.groupby("ID").first().iloc[0]
    rows = mapping_indicator_rows(mapping, section)
    if rows.empty:
        raise ValueError(f"No indicators configured for {section}")
    return rows.iloc[0]


def _build_unavailable_cumulative_payload(
    mapping: pd.DataFrame,
    section: str,
    indicator_id: str,
    language: str,
) -> dict[str, Any]:
    indicator = _indicator_meta_from_mapping(mapping, section, indicator_id)
    return {
        "label": indicator_label(indicator, language),
        "unavailable": True,
        "unavailable_label": not_available(language),
        "annual_target": None,
        "annual_target_label": None,
        "years": [],
        "values": [],
        "value_labels": [],
        "reporting": [],
        "implementing": [],
        "show_ns_breakdown": show_ns_breakdown(indicator.get("Type"), indicator.get("Unit")),
    }


def _build_unavailable_donut_payload(
    mapping: pd.DataFrame,
    section: str,
    indicator_id: str,
    language: str,
) -> dict[str, Any]:
    indicator = _indicator_meta_from_mapping(mapping, section, indicator_id)
    return {
        "label": indicator_label(indicator, language),
        "unavailable": True,
        "unavailable_label": not_available(language),
        "value": None,
        "value_label": not_available(language),
        "target": 0.0,
        "target_label": target_label_sp(indicator, language),
    }


def _indicator_meta(model: pd.DataFrame, section: str, indicator_id: str) -> pd.Series:
    rows = model[(model["section"] == section) & (model["ID"] == indicator_id)]
    return rows.groupby("ID").first().iloc[0]


def _latest_value(model: pd.DataFrame, section: str, indicator_id: str) -> tuple[float, pd.DataFrame]:
    rows = model[(model["section"] == section) & (model["ID"] == indicator_id)].sort_values("Year")
    latest = rows.iloc[-1]
    return float(latest["Value"]), rows


def _latest_chartable_value(
    model: pd.DataFrame,
    section: str,
    indicator_id: str,
) -> tuple[float | None, pd.DataFrame]:
    rows = model[(model["section"] == section) & (model["ID"] == indicator_id)].sort_values("Year")
    for _, row in reversed(list(rows.iterrows())):
        value = chartable_value(row["Value"])
        if value is not None:
            return value, rows
    return None, rows


def _build_ef_cumulative_payload(
    model: pd.DataFrame,
    mapping: pd.DataFrame,
    section: str,
    indicator_id: str,
    language: str,
) -> dict[str, Any]:
    """Line-chart payload for one EF indicator."""
    if not indicator_has_values(model, section, indicator_id):
        payload = _build_unavailable_cumulative_payload(mapping, section, indicator_id, language)
        payload["show_ns_breakdown"] = True
        return payload
    indicator = _indicator_meta(model, section, indicator_id)
    rows = model[(model["section"] == section) & (model["ID"] == indicator_id)].sort_values("Year")
    unit = indicator.get("Unit")
    annual_target = annual_target_value(indicator)

    years: list[str] = []
    values: list[float | None] = []
    value_labels: list[str] = []
    reporting: list[str] = []
    implementing: list[str] = []

    for _, row in rows.iterrows():
        year = str(row["Year"])
        val_raw = row["Value"]
        val = chartable_value(val_raw)
        years.append(year_display(year))
        formatted = format_value(val, unit, language) if val is not None else None
        if formatted is None:
            values.append(None)
            value_labels.append(not_applicable(language))
        else:
            values.append(val)
            value_labels.append(formatted)

        total_reported = row.get("TotalReported")
        impl = row.get("Implementing")
        reporting.append(
            str(int(total_reported)) if pd.notna(total_reported) else not_applicable(language)
        )
        implementing.append(str(int(impl)) if pd.notna(impl) else not_applicable(language))

    if not any(value is not None for value in values):
        payload = _build_unavailable_cumulative_payload(mapping, section, indicator_id, language)
        payload["show_ns_breakdown"] = True
        return payload

    return {
        "label": indicator_label(indicator, language),
        "annual_target": annual_target,
        "annual_target_label": annual_target_label(indicator, language),
        "years": years,
        "values": values,
        "value_labels": value_labels,
        "reporting": reporting,
        "implementing": implementing,
        "show_ns_breakdown": True,
    }


def _build_cumulative_payload(
    model: pd.DataFrame,
    mapping: pd.DataFrame,
    section: str,
    indicator_id: str,
    language: str,
) -> dict[str, Any]:
    if not indicator_has_values(model, section, indicator_id):
        return _build_unavailable_cumulative_payload(mapping, section, indicator_id, language)
    indicator = _indicator_meta(model, section, indicator_id)
    rows = model[(model["section"] == section) & (model["ID"] == indicator_id)].sort_values("Year")
    unit = indicator.get("Unit")
    annual_target = annual_target_value(indicator)

    years: list[str] = []
    values: list[float | None] = []
    value_labels: list[str] = []
    reporting: list[str] = []
    implementing: list[str] = []

    for _, row in rows.iterrows():
        year = str(row["Year"])
        val = chartable_value(row["Value"])
        years.append(year_display(year))
        values.append(val)
        value_labels.append(format_value(val, unit, language) if val is not None else "")
        count = row.get("Count")
        impl = row.get("Implementing")
        reporting.append(str(int(count)) if pd.notna(count) else not_applicable(language))
        implementing.append(str(int(impl)) if pd.notna(impl) else not_applicable(language))

    if not any(value is not None for value in values):
        return _build_unavailable_cumulative_payload(mapping, section, indicator_id, language)

    return {
        "label": indicator_label(indicator, language),
        "annual_target": annual_target,
        "annual_target_label": annual_target_label(indicator, language),
        "years": years,
        "values": values,
        "value_labels": value_labels,
        "reporting": reporting,
        "implementing": implementing,
        "show_ns_breakdown": show_ns_breakdown(indicator.get("Type"), indicator.get("Unit")),
    }


def _build_donut_payload(
    model: pd.DataFrame,
    mapping: pd.DataFrame,
    section: str,
    indicator_id: str,
    language: str,
) -> dict[str, Any]:
    if not indicator_has_values(model, section, indicator_id):
        return _build_unavailable_donut_payload(mapping, section, indicator_id, language)
    indicator = _indicator_meta(model, section, indicator_id)
    value, _ = _latest_chartable_value(model, section, indicator_id)
    if value is None:
        return _build_unavailable_donut_payload(mapping, section, indicator_id, language)
    target_raw = indicator.get("Target value")
    target = float(target_raw) if pd.notna(target_raw) else 0.0
    unit = indicator.get("Unit")
    if indicator_id == "Katya01":
        value_label = format_donut_value(value, unit, language) or not_available(language)
    else:
        value_label = format_value(value, unit, language) or not_available(language)
    return {
        "label": indicator_label(indicator, language),
        "value": value,
        "value_label": value_label,
        "target": target,
        "target_label": target_label_sp(indicator, language),
    }


def build_sp_payload(
    model: pd.DataFrame,
    section: str,
    language: str = "English",
    mapping: pd.DataFrame | None = None,
) -> dict[str, Any]:
    mapping = mapping if mapping is not None else mapping_from_model(model)
    layout = build_section_layout(section, mapping)
    subset = model[model["section"] == section]

    meta0 = _section_meta_row(model, mapping, section)
    hdr = headers(language)
    width, height = DASHBOARD_SIZES.get(section, (827, 800))

    cumulative_ids = indicators_with_data(
        model,
        section,
        visible_indicator_ids(section, layout["cumulative_ids"]),
    )
    cumulative = [
        _build_cumulative_payload(model, mapping, section, indicator_id, language)
        for indicator_id in cumulative_ids
    ]

    donuts: list[dict[str, Any]] = []
    donut_pairs: list[list[dict[str, Any]]] = []

    for pair_ids in visible_donut_pairs(section, layout.get("donut_pairs", [])):
        pair = [
            _build_donut_payload(model, mapping, section, indicator_id, language)
            for indicator_id in indicators_with_data(model, section, pair_ids)
        ]
        if pair:
            donut_pairs.append(pair)

    return {
        "type": "sp",
        "section": section,
        "language": language,
        "title": section_title(meta0, language),
        "width": width,
        "height": height,
        "headers": {
            "indicator": hdr["indicator"],
            "year": hdr["year"],
            "implementing": hdr["ns_implementing"],
            "reporting": hdr["ns_reporting"],
            "annual_target": hdr["annual_target"],
            "target": hdr["target"],
        },
        "table_labels": table_row_labels(language),
        "footnote": section_footnote(section, language),
        "cumulative": cumulative,
        "donuts": donuts,
        "donut_pairs": donut_pairs,
        **style_payload(),
    }


def build_ef_payload(
    model: pd.DataFrame,
    section: str,
    language: str = "English",
    mapping: pd.DataFrame | None = None,
) -> dict[str, Any]:
    mapping = mapping if mapping is not None else mapping_from_model(model)
    layout = build_section_layout(section, mapping)

    meta0 = _section_meta_row(model, mapping, section)
    hdr = headers(language)
    width, height = DASHBOARD_SIZES.get(section, (827, 600))

    indicator_ids = indicators_with_data(
        model,
        section,
        visible_indicator_ids(section, layout["cumulative_ids"]),
    )
    cumulative = [
        _build_ef_cumulative_payload(model, mapping, section, indicator_id, language)
        for indicator_id in indicator_ids
    ]

    return {
        "type": "sp",
        "section": section,
        "language": language,
        "title": section_title(meta0, language),
        "width": width,
        "height": height,
        "headers": {
            "indicator": hdr["indicator"],
            "year": hdr["year"],
            "implementing": hdr["ns_implementing"],
            "reporting": hdr["ns_reporting"],
            "annual_target": hdr["annual_target"],
            "target": hdr["target"],
        },
        "table_labels": table_row_labels(language),
        "footnote": section_footnote(section, language),
        "cumulative": cumulative,
        "donuts": [],
        "donut_pairs": [],
        **style_payload(),
    }


def build_payload(
    model: pd.DataFrame,
    section: str,
    language: str = "English",
    mapping: pd.DataFrame | None = None,
) -> dict[str, Any]:
    if section.startswith("EF"):
        return build_ef_payload(model, section, language, mapping=mapping)
    return build_sp_payload(model, section, language, mapping=mapping)
