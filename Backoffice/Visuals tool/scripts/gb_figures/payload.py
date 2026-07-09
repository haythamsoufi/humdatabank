"""Build JSON payloads for HTML/SVG dashboard rendering."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .calculations import (
    annual_target_label,
    annual_target_value,
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
    target_label_ef,
    target_label_sp,
    year_display,
)
from .config import DASHBOARD_SIZES
from .styles import style_payload
from .layouts import (
    EF_ID_ORDERS,
    SP_LAYOUTS,
    show_ns_breakdown,
    visible_donut_pair,
    visible_donut_rows,
    visible_indicator_ids,
)


def _indicator_meta(model: pd.DataFrame, section: str, indicator_id: str) -> pd.Series:
    rows = model[(model["section"] == section) & (model["ID"] == indicator_id)]
    return rows.groupby("ID").first().iloc[0]


def _latest_value(model: pd.DataFrame, section: str, indicator_id: str) -> tuple[float, pd.DataFrame]:
    rows = model[(model["section"] == section) & (model["ID"] == indicator_id)].sort_values("Year")
    latest = rows.iloc[-1]
    return float(latest["Value"]), rows


def _build_cumulative_payload(
    model: pd.DataFrame,
    section: str,
    indicator_id: str,
    language: str,
) -> dict[str, Any]:
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
        val = float(row["Value"]) if pd.notna(row["Value"]) else None
        years.append(year_display(year))
        values.append(val)
        value_labels.append(format_value(val, unit, language) if val is not None else "")
        count = row.get("Count")
        impl = row.get("Implementing")
        reporting.append(str(int(count)) if pd.notna(count) else not_applicable(language))
        implementing.append(str(int(impl)) if pd.notna(impl) else not_applicable(language))

    return {
        "label": indicator_label(indicator, language),
        "annual_target": annual_target,
        "annual_target_label": annual_target_label(indicator, language),
        "years": years,
        "values": values,
        "value_labels": value_labels,
        "reporting": reporting,
        "implementing": implementing,
        "show_ns_breakdown": show_ns_breakdown(indicator_id),
    }


def _build_donut_payload(
    model: pd.DataFrame,
    section: str,
    indicator_id: str,
    language: str,
) -> dict[str, Any]:
    indicator = _indicator_meta(model, section, indicator_id)
    value, _ = _latest_value(model, section, indicator_id)
    target = float(indicator["Target value"])
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


def build_sp_payload(model: pd.DataFrame, section: str, language: str = "English") -> dict[str, Any]:
    layout = SP_LAYOUTS[section]
    subset = model[model["section"] == section]
    if subset.empty:
        raise ValueError(f"No data for {section}")

    meta0 = subset.groupby("ID").first().iloc[0]
    hdr = headers(language)
    width, height = DASHBOARD_SIZES.get(section, (827, 800))

    cumulative_ids = visible_indicator_ids(section, layout["cumulative_ids"])
    cumulative = [
        _build_cumulative_payload(model, section, indicator_id, language)
        for indicator_id in cumulative_ids
    ]

    donuts: list[dict[str, Any]] = []
    donut_pair: list[dict[str, Any]] | None = None

    visible_pair = visible_donut_pair(section, layout.get("donut_pair"))
    if visible_pair:
        donut_pair = [
            _build_donut_payload(model, section, indicator_id, language)
            for indicator_id in visible_pair
        ]
    else:
        donuts = [
            _build_donut_payload(model, section, donut["id"], language)
            for donut in visible_donut_rows(section, layout.get("donut_rows", []))
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
        "donuts": donuts,
        "donut_pair": donut_pair,
        **style_payload(),
    }


def build_ef_payload(model: pd.DataFrame, section: str, language: str = "English") -> dict[str, Any]:
    subset = model[model["section"] == section]
    if subset.empty:
        raise ValueError(f"No data for {section}")

    meta0 = subset.groupby("ID").first().iloc[0]
    hdr = headers(language)
    id_order = EF_ID_ORDERS.get(section)
    width, height = DASHBOARD_SIZES.get(section, (827, 600))
    years = sorted(subset["Year"].unique())

    meta = (
        subset.groupby("ID", as_index=False)
        .agg({"English": "first", "French": "first", "Spanish": "first", "Arabic": "first",
              "Unit": "first", "Target": "first", "Target AR": "first", "FDRS KPI": "first"})
    )
    if id_order:
        meta["sort_key"] = meta["ID"].map({v: i for i, v in enumerate(id_order)})
        meta = meta.sort_values("sort_key")
    else:
        meta = meta.sort_values("ID")

    rows: list[dict[str, Any]] = []
    for _, indicator in meta.iterrows():
        indicator_id = indicator["ID"]
        year_cells: list[dict[str, str]] = []
        for year in years:
            row = subset[(subset["ID"] == indicator_id) & (subset["Year"] == year)]
            if row.empty:
                year_cells.append({"text": not_applicable(language), "value": False})
                continue
            val = row["Value"].sum()
            formatted = format_value(val, indicator.get("Unit"), language)
            suffix = out_of_suffix(
                val,
                indicator.get("Unit"),
                row["Count"].iloc[0] if "Count" in row else None,
                str(int(row["TotalReported"].iloc[0])) if pd.notna(row["TotalReported"].iloc[0]) else None,
                language,
            )
            if formatted is None:
                year_cells.append({"text": not_applicable(language), "value": False})
            else:
                year_cells.append({
                    "text": f"{formatted}{suffix or ''}",
                    "value": True,
                    "main": formatted,
                    "suffix": suffix or "",
                })

        rows.append({
            "label": indicator_label(indicator, language),
            "target": target_label_ef(indicator, language),
            "years": year_cells,
        })

    show_target_column = any(str(row["target"]).strip() for row in rows)

    return {
        "type": "ef",
        "section": section,
        "language": language,
        "title": section_title(meta0, language),
        "width": width,
        "height": height,
        "show_target_column": show_target_column,
        "headers": {
            "indicator": hdr["indicator"],
            "target": hdr["target"],
            "years": [year_display(str(y)) for y in years],
        },
        "footnote": section_footnote(section, language),
        "rows": rows,
        **style_payload(),
    }


def build_payload(model: pd.DataFrame, section: str, language: str = "English") -> dict[str, Any]:
    if section.startswith("EF"):
        return build_ef_payload(model, section, language)
    return build_sp_payload(model, section, language)
