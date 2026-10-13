"""Renderer-independent description of the UPR Analysis visuals.

A **view** is the single source of truth for what the Analysis shows. The tab,
the PDF export and the presentation all consume the same JSON-serialisable
structure; only the renderer differs. Nothing here knows about ApexCharts,
HTML, WeasyPrint or slides.

View (``impact_views.build_impact_view`` / ``narrative_views.build_narrative_views``)::

    {
      "title", "lead",                  # section heading
      "kpis":    [KPI, ...],
      "visuals": [Visual, ...],         # in display order
      "notes":   [str, ...],            # footnotes
      "warnings":[str, ...],            # e.g. a document feed that is down
      "has_data": bool,
    }

KPI::

    {"id", "label", "value", "format", "year",
     "delta": {"direction", "text", "context", "note"} | None}   # note: free text, no arrow

Visual::

    {
      "id", "title", "hint", "wide": bool,
      "kind": "chart" | "panels" | "gaps",
      "chart":  Chart,                 # kind == "chart"
      "panels": [{"id", "name", "color", "value", "year", "chart": Chart}],   # "panels"
      "gaps":   [{"id", "label", "count", "table": Table}],                   # "gaps"
      "table":  Table | None,          # the same numbers as a drill-down table
      "table_label": str | None,
      "findings": [Finding, ...],      # what the data says; [] when nobody has written any
    }

Finding (see :func:`finding`)::

    {"id", "title": str | None, "text", "tone": "info" | "positive" | "attention",
     "focus": {"categories": [str]} | None}    # chart categories the finding is about

Findings explain a visual: the tab and the A4 report list them under the chart,
the presentation reveals them one by one (and highlights the ``focus``
categories on the chart).

Chart::

    {
      "categories": [str], "series": [Series],
      "axes": {"primary": Axis, "secondary": Axis?},
      "stacked", "height", "column_width", "border_radius", "curve", "stroke_width",
      "legend", "data_labels", "x_title", "gradient": [shade, from, to] | None,
    }
    Series = {"name", "kind": "column"|"line"|"area", "data": [number|None],
              "color", "axis": "primary"|"secondary", "format", "dashed"}
    Axis   = {"format", "opposite", "min", "max", "tick_amount"}

Table::

    {"title", "note", "legend", "columns": [str],
     "rows": [{"cells": [Cell], "countries": [{"cells": [Cell]}]}]}
    Cell = str | number | None | {"value": ..., "midyear": True}

``format`` is one of :data:`FORMATS`; renderers turn a raw value into text with
it. Keeping raw values (not pre-formatted strings) lets a chart axis, a tooltip,
a KPI and a table cell all share one number.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

from plugins.upr.catalog import IFRC_NAVY, IFRC_RED

FORMATS = ("int", "money", "pct", "abs_int")

FINDING_TONES = ("info", "positive", "attention")

COLORS = {
    "navy": IFRC_NAVY,
    "red": IFRC_RED,
    "amber": "#f39200",
    "teal": "#2a9d8f",
    "green": "#6ba543",
    "blue": "#3d7edb",
    "purple": "#8b5a9e",
    "grey": "#58595b",
}


def round_int(value: Any) -> int | None:
    """Round half up (the browser's ``Math.round``); ``None`` stays ``None``."""
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(math.floor(value + 0.5))


def trim_number(value: float | int) -> str:
    """``12.0`` -> ``"12"``, ``12.5`` -> ``"12.5"``."""
    number = float(value)
    return str(int(number)) if number.is_integer() else str(number)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and not math.isnan(value)


def year_label(year: Any, in_progress_years: Iterable[Any] = ()) -> str:
    """``2025`` -> ``"2025"``; ``"2025 *"`` while the year is still open."""
    return f"{year} *" if year in set(in_progress_years) else str(year)


# -- series projection -------------------------------------------------------


def years_of(points: Iterable[Mapping[str, Any]] | None) -> list[Any]:
    return [p.get("year") for p in points or []]


def column(points: Iterable[Mapping[str, Any]] | None, key: str) -> list[int | None]:
    """One rounded value per point (gaps stay ``None``)."""
    return [round_int(p.get(key)) for p in points or []]


def along(
    years: Iterable[Any], points: Iterable[Mapping[str, Any]] | None, key: str
) -> list[int | None]:
    """Project a year-keyed series onto a shared list of years (gaps -> ``None``)."""
    by_year = {p.get("year"): p.get(key) for p in points or []}
    return [round_int(by_year.get(year)) for year in years]


def at_year(points: Iterable[Mapping[str, Any]] | None, year: Any) -> Mapping[str, Any] | None:
    for point in points or []:
        if point.get("year") == year:
            return point
    return None


def value_or_none(point: Mapping[str, Any] | None, key: str) -> Any:
    if not point or point.get(key) is None:
        return None
    return point[key]


# -- builders ----------------------------------------------------------------


def axis(
    fmt: str = "int",
    *,
    opposite: bool = False,
    minimum: float | None = None,
    maximum: float | None = None,
    tick_amount: int | None = None,
) -> dict[str, Any]:
    return {
        "format": fmt,
        "opposite": opposite,
        "min": minimum,
        "max": maximum,
        "tick_amount": tick_amount,
    }


def series(
    name: str,
    data: Sequence[Any],
    *,
    kind: str = "column",
    color: str,
    axis_id: str = "primary",
    fmt: str = "int",
    dashed: bool = False,
) -> dict[str, Any]:
    return {
        "name": name,
        "kind": kind,
        "data": list(data),
        "color": color,
        "axis": axis_id,
        "format": fmt,
        "dashed": dashed,
    }


def chart(
    categories: Sequence[str],
    series_list: Sequence[dict[str, Any]],
    *,
    axes: Mapping[str, dict[str, Any]] | None = None,
    stacked: bool = False,
    height: int = 300,
    column_width: str = "60%",
    border_radius: int = 3,
    curve: str = "smooth",
    stroke_width: int = 3,
    legend: bool = True,
    data_labels: bool = False,
    x_title: str | None = None,
    gradient: Sequence[float] | None = None,
) -> dict[str, Any]:
    return {
        "categories": list(categories),
        "series": list(series_list),
        "axes": dict(axes or {"primary": axis()}),
        "stacked": stacked,
        "height": height,
        "column_width": column_width,
        "border_radius": border_radius,
        "curve": curve,
        "stroke_width": stroke_width,
        "legend": legend,
        "data_labels": data_labels,
        "x_title": x_title,
        "gradient": list(gradient) if gradient else None,
    }


def midyear_cell(value: Any, on: bool) -> Any:
    """Flag a reporting figure that comes from the mid-year report."""
    if not on or value is None:
        return value
    return {"value": value, "midyear": True}


def raw_value(cell: Any) -> Any:
    if isinstance(cell, dict) and "value" in cell:
        return cell["value"]
    return cell


def _has_figure(cells: Sequence[Any]) -> bool:
    return any(index > 0 and is_number(raw_value(v)) and raw_value(v) != 0 for index, v in enumerate(cells))


def _rank(cells: Sequence[Any]) -> float:
    best = 0.0
    for value in cells:
        number = raw_value(value)
        if is_number(number) and abs(number) > best:
            best = abs(number)
    return best


def country_rows(rows: Iterable[Sequence[Any]]) -> list[dict[str, Any]]:
    """Drill-down lines under a year: drop all-zero rows, largest figure first.

    Each input row is a list of cells whose first cell is the country name.
    """
    kept = [list(cells) for cells in rows if _has_figure(cells)]
    kept.sort(key=lambda cells: (-_rank(cells), str(cells[0]).casefold()))
    return [{"cells": cells} for cells in kept]


def table_row(cells: Sequence[Any], countries: Iterable[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"cells": list(cells), "countries": list(countries or [])}


def latest_first(rows: Iterable[tuple[Any, dict[str, Any]]]) -> list[dict[str, Any]]:
    """Order ``(sort_key, row)`` pairs newest first. ``sort_key`` is a year or a round order."""
    ordered = sorted(rows, key=lambda pair: pair[0] or 0, reverse=True)
    return [row for _, row in ordered]


def table(
    title: str,
    columns: Sequence[str],
    rows: Iterable[dict[str, Any]],
    *,
    note: str = "",
    legend: str = "",
) -> dict[str, Any]:
    return {
        "title": title,
        "note": note,
        "legend": legend,
        "columns": list(columns),
        "rows": list(rows),
    }


def plain_rows(rows: Iterable[Sequence[Any]]) -> list[dict[str, Any]]:
    """Rows without drill-down."""
    return [table_row(cells) for cells in rows]


def visual(
    visual_id: str,
    title: str,
    hint: str,
    *,
    kind: str = "chart",
    wide: bool = False,
    chart: dict[str, Any] | None = None,
    panels: list[dict[str, Any]] | None = None,
    gaps: list[dict[str, Any]] | None = None,
    table: dict[str, Any] | None = None,
    table_label: str | None = None,
    findings: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": visual_id,
        "title": title,
        "hint": hint,
        "wide": wide,
        "kind": kind,
        "chart": chart,
        "panels": panels,
        "gaps": gaps,
        "table": table,
        "table_label": table_label,
        "findings": [dict(f) for f in findings or ()],
    }


def finding(
    finding_id: str,
    text: str,
    *,
    title: str | None = None,
    tone: str = "info",
    categories: Iterable[str] | None = None,
) -> dict[str, Any]:
    """One finding about a visual, as ready-to-show text.

    ``categories`` names the chart categories (x-axis labels, exactly as in the
    chart) the finding is about; the presentation highlights them when the finding
    is revealed. Leave it out for a finding about the visual as a whole.
    """
    if tone not in FINDING_TONES:
        raise ValueError(f"unknown finding tone {tone!r}; expected one of {FINDING_TONES}")
    focus = {"categories": [str(c) for c in categories]} if categories else None
    return {"id": finding_id, "title": title, "text": text, "tone": tone, "focus": focus}


# -- KPI cards ----------------------------------------------------------------


def delta_view(delta: Mapping[str, Any] | None, labels: Mapping[str, str]) -> dict[str, Any] | None:
    """How a headline figure changed, as ready-to-show text and a direction."""
    from plugins.upr.analysis_labels import fill

    if not delta or delta.get("latest") is None:
        return None
    if delta.get("note"):
        return {"direction": "flat", "text": delta["note"], "context": None, "note": True}

    direction = "flat"
    if delta.get("change_abs") is not None:
        change = delta["change_abs"]
        if change > 0:
            direction = "up"
        elif change < 0:
            direction = "down"
        text = ("+" if change > 0 else "") + trim_number(change) + (delta.get("change_unit") or "")
    elif delta.get("change_pct") is None:
        text = labels["no_previous"]
    else:
        change = delta["change_pct"]
        if change > 0:
            direction = "up"
        elif change < 0:
            direction = "down"
        text = ("+" if change > 0 else "") + trim_number(change) + "%"

    context = None
    if delta.get("previous_year") is not None:
        context = fill(labels["vs_previous"], year=delta["previous_year"])
    return {"direction": direction, "text": text, "context": context, "note": False}


def with_abs_change(delta: Mapping[str, Any] | None, unit: str = "") -> dict[str, Any]:
    """Show a rate or a tiny count as a plain difference instead of a percentage."""
    out = dict(delta or {})
    if out.get("latest") is not None and out.get("previous") is not None:
        out["change_abs"] = math.floor((out["latest"] - out["previous"]) * 10 + 0.5) / 10
        out["change_unit"] = unit
    return out


def kpi(
    kpi_id: str,
    label: str,
    value: Any,
    fmt: str,
    delta: Mapping[str, Any] | None,
    labels: Mapping[str, str],
) -> dict[str, Any]:
    latest_year = (delta or {}).get("latest_year")
    return {
        "id": kpi_id,
        "label": label,
        "value": value,
        "format": fmt,
        "year": latest_year,
        "delta": delta_view(delta, labels),
    }


def pct_text(value: Any) -> str:
    """One-decimal percentage for text and table cells (``—`` when missing)."""
    if not is_number(value):
        return "—"
    return trim_number(math.floor(value * 10 + 0.5) / 10) + "%"


def format_int_text(value: Any) -> str:
    """Thousands-separated integer for text built on the server (``—`` when missing)."""
    rounded = round_int(value)
    return "—" if rounded is None else f"{rounded:,}"
