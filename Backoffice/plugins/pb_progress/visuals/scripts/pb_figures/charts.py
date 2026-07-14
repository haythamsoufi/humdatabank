"""Chart builders that mirror Tableau worksheet types in P&B figures.twb."""

from __future__ import annotations

import math

import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .calculations import (
    annual_target_label,
    annual_target_value,
    format_donut_value,
    format_value,
    gap_value,
    headers,
    indicator_format_unit,
    indicator_label,
    not_applicable,
    not_available,
    out_of_suffix,
    table_row_labels,
    target_label_ef,
    target_label_sp,
    year_display,
)
from .config import COLOR_DIVIDER, COLOR_GAP, COLOR_TARGET, COLOR_VALUE
from .styles import resolve_style


def _wrap_indicator_label(text: str, width: int = 40) -> str:
    return "\n".join(textwrap.wrap(text, width=width))


def _value_label_position(
    index: int,
    value: float,
    values: list[float],
    annual_target: float | None,
    ymax: float,
) -> tuple[float, str]:
    """Pick y offset and vertical alignment to reduce label collisions."""
    offset = ymax * 0.06
    above = value + offset
    below = max(value - offset, ymax * 0.02)

    if annual_target is not None and abs(value - annual_target) <= ymax * 0.06:
        if value >= annual_target:
            return below, "top"
        return above, "bottom"

    prev = values[index - 1] if index > 0 else None
    nxt = values[index + 1] if index < len(values) - 1 else None
    if prev is not None and nxt is not None:
        if value >= prev and value >= nxt:
            return above, "bottom"
        if value <= prev and value <= nxt:
            if value <= ymax * 0.12:
                return above, "bottom"
            return below, "top"

    if index == 0:
        return above, "bottom"

    if index == len(values) - 1 and annual_target is not None:
        if abs(value - annual_target) <= max(annual_target, value) * 0.2:
            return below - offset * 0.5, "top"

    return above, "bottom"


def _active_style() -> dict:
    return resolve_style()


def _theme_color(key: str, fallback: str) -> str:
    return _active_style()["colors"].get(key, fallback)


def _plot_line_series(
    chart_ax,
    x: np.ndarray,
    values: list[float],
    *,
    effects: dict[str, bool] | None = None,
) -> None:
    """Draw the value line with optional area fill, shadow, and marker styling."""
    style = _active_style()
    fx = {**style["line_chart_effects"], **(effects or {})}
    stroke_w = style["line_stroke_width"]
    value_color = _theme_color("value", COLOR_VALUE)

    is_modern = style.get("name") == "modern"
    marker_r = float(style.get("marker_radius", 3.5))
    # Matplotlib markersize is roughly diameter in points; map SVG radius → size.
    marker_size = marker_r * 2.0

    if fx.get("area_fill"):
        chart_ax.fill_between(
            x, values, 0, color=value_color, alpha=0.10 if is_modern else 0.06, zorder=1
        )

    if fx.get("line_shadow"):
        chart_ax.plot(
            x,
            values,
            color=value_color,
            linewidth=3.5 if is_modern else 3,
            alpha=0.12 if is_modern else 0.10,
            solid_capstyle="round",
            zorder=2,
        )

    marker_kw: dict = {
        "color": value_color,
        "linewidth": stroke_w,
        "marker": "o",
        "markersize": marker_size,
        "zorder": 3,
        "solid_capstyle": "round",
        "solid_joinstyle": "round",
    }
    if fx.get("marker_ring"):
        marker_kw.update(
            markerfacecolor="#ffffff",
            markeredgecolor=value_color,
            markeredgewidth=1.5,
            markersize=max(marker_size + 1.0, 6),
        )
    else:
        marker_kw.update(markerfacecolor=value_color, markeredgecolor=value_color, markeredgewidth=0)

    chart_ax.plot(x, values, **marker_kw)


def draw_sp_column_headers(ax, language: str = "English") -> None:
    """Column header row aligned to indicator / chart column layout."""
    hdr = headers(language)
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    # Align with 36% label column | 64% chart area (matches cumulative panels)
    columns = [
        (0.00, hdr["indicator"]),
        (0.37, hdr["year"]),
        (0.45, hdr["ns_implementing"]),
        (0.56, hdr["ns_reporting"]),
        (0.76, hdr["annual_target"]),
        (0.92, hdr["target"]),
    ]
    for x, label in columns:
        ax.text(x, 0.5, label, ha="left", va="center", fontsize=6.5, fontweight="bold")


def _donut_has_target(target: float | None) -> bool:
    if target is None:
        return False
    try:
        numeric = float(target)
    except (TypeError, ValueError):
        return False
    return math.isfinite(numeric) and numeric > 0


def draw_donut_on_ax(
    ax,
    value: float,
    target: float,
    *,
    language: str = "English",
    indicator_id: str | None = None,
    unit: str | None = None,
    radius: float = 0.32,
) -> None:
    if _donut_has_target(target):
        gap = gap_value(target, value)
        sizes = [value, gap] if gap > 0 else [value, 0.0001]
        colors = [_theme_color("value", COLOR_VALUE), _theme_color("gap", COLOR_GAP)]
    else:
        sizes = [1]
        colors = [_theme_color("value", COLOR_VALUE)]
    ax.axis("off")
    ax.set_aspect("equal")
    ax.set_xlim(-0.55, 0.55)
    ax.set_ylim(-0.55, 0.55)
    ax.pie(
        sizes,
        colors=colors,
        startangle=90,
        radius=radius,
        wedgeprops={"width": radius * 0.45, "edgecolor": "white"},
    )
    hole = radius * 0.55
    centre = plt.Circle((0, 0), hole, fc="white")
    ax.add_artist(centre)
    if indicator_id == "Katya01":
        label = format_donut_value(value, unit, language) or not_available(language)
    else:
        label = format_value(value, unit, language) or not_available(language)
    ax.text(0, 0, label, ha="center", va="center", fontsize=9, fontweight="bold")


def draw_ef_data_table(
    ax,
    subset: pd.DataFrame,
    *,
    language: str = "English",
    id_order: list[str] | None = None,
) -> None:
    meta = (
        subset.groupby("ID", as_index=False)
        .agg(
            {
                "English": "first", "French": "first", "Spanish": "first", "Arabic": "first",
                "Unit": "first", "Target": "first", "Target AR": "first", "FDRS KPI": "first",
            }
        )
    )
    if id_order:
        meta["sort_key"] = meta["ID"].map({v: i for i, v in enumerate(id_order)})
        meta = meta.sort_values("sort_key")
    else:
        meta = meta.sort_values("ID")

    years = sorted(subset["Year"].unique())
    row_data: list[tuple[str, str, list[str]]] = []
    for _, indicator in meta.iterrows():
        indicator_id = indicator["ID"]
        label = indicator_label(indicator, language)
        target = target_label_ef(indicator, language)
        year_cells = []
        for year in years:
            row = subset[(subset["ID"] == indicator_id) & (subset["Year"] == year)]
            if row.empty:
                year_cells.append(not_applicable(language))
                continue
            val = row["Value"].sum()
            formatted = format_value(val, indicator_format_unit(indicator), language)
            suffix = out_of_suffix(
                val, indicator.get("Unit"),
                row["Count"].iloc[0] if "Count" in row else None,
                str(int(row["TotalReported"].iloc[0])) if pd.notna(row["TotalReported"].iloc[0]) else None,
                language,
            )
            year_cells.append(not_applicable(language) if formatted is None else f"{formatted}{suffix or ''}")
        row_data.append((label, target, year_cells))

    show_target = any(str(target).strip() for _, target, _ in row_data)
    rows: list[list[str]] = []
    for label, target, year_cells in row_data:
        row_cells = [label]
        if show_target:
            row_cells.append(target)
        row_cells.extend(year_cells)
        rows.append(row_cells)

    hdr = headers(language)
    col_labels = [hdr["indicator"]]
    if show_target:
        col_labels.append(hdr["target"])
    col_labels.extend(year_display(y) for y in years)
    n_years = len(years)
    year_width = (0.50 if show_target else 0.62) / max(n_years, 1)
    col_widths = [0.38]
    if show_target:
        col_widths.append(0.12)
    col_widths.extend([year_width] * n_years)
    ax.axis("off")
    table = ax.table(
        cellText=rows,
        colLabels=col_labels,
        loc="upper center",
        cellLoc="center",
        colWidths=col_widths,
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.6)
    value_col_start = 2 if show_target else 1
    for (r, c), cell in table.get_celld().items():
        if r == 0:
            cell.set_text_props(fontweight="bold")
        if c == 0:
            cell.set_text_props(ha="left")
        if c >= value_col_start and r > 0:
            cell.get_text().set_color(COLOR_VALUE)
            cell.get_text().set_fontweight("bold")
    return show_target


def draw_cumulative_indicator(
    label_ax,
    chart_ax,
    table_ax,
    indicator: pd.Series,
    data: pd.DataFrame,
    *,
    language: str = "English",
    ns_breakdown: bool | None = None,
    reporting_field: str = "Count",
) -> None:
    """Draw one line-chart indicator panel onto existing axes."""
    years = data["Year"].tolist()
    values = [float(v) if pd.notna(v) else float("nan") for v in data["Value"].tolist()]
    reporting = data[reporting_field].tolist() if reporting_field in data.columns else data["Count"].tolist()
    implementing = data["Implementing"].tolist()
    total_reported = data["TotalReported"].tolist() if "TotalReported" in data.columns else reporting
    annual_target = annual_target_value(indicator)
    unit = indicator_format_unit(indicator)
    label = _wrap_indicator_label(indicator_label(indicator, language))
    hdr = headers(language)
    table_mode = ns_table_mode(indicator.get("Type"), indicator.get("Unit"))
    if ns_breakdown is False:
        show_reporting_row = False
        show_implementing_row = False
    elif table_mode in {NS_TABLE_IMPLEMENTING_COUNT, NS_TABLE_NS_UNIT}:
        show_reporting_row = True
        show_implementing_row = False
    else:
        show_reporting_row = True
        show_implementing_row = True

    row_labels_dict = table_row_labels(language)
    row_labels = [row_labels_dict["year"]]
    table_rows = [[year_display(y) for y in years]]
    # NS-unit indicators: the charted value already is the "implementing" count,
    # so the one visible row shows the total NSs in this reporting round instead.
    reporting_values = (
        total_reported if table_mode in {NS_TABLE_IMPLEMENTING_COUNT, NS_TABLE_NS_UNIT} else reporting
    )
    if show_reporting_row:
        row_labels.append(row_labels_dict["reporting"])
        table_rows.append([
            str(int(v)) if pd.notna(v) else not_applicable(language) for v in reporting_values
        ])
    if show_implementing_row:
        row_labels.append(row_labels_dict["implementing"])
        table_rows.append([
            str(int(v)) if pd.notna(v) else not_applicable(language) for v in implementing
        ])

    label_ax.axis("off")
    label_ax.text(0.02, 0.5, label, ha="left", va="center", fontsize=9,
                  fontfamily="sans-serif", linespacing=1.25, transform=label_ax.transAxes)
    label_ax.axvline(0.98, color=_theme_color("divider", COLOR_DIVIDER), linewidth=0.8, ymin=0.08, ymax=0.92)

    x = np.arange(len(years))
    finite_values = [v for v in values if not math.isnan(v)]
    ymax_candidates = list(finite_values)
    if annual_target is not None:
        ymax_candidates.append(annual_target)
    ymax = max(ymax_candidates) * 1.28 if ymax_candidates else 1
    chart_ax.set_xlim(-0.2, len(years) - 1 + 0.65)
    chart_ax.set_ylim(0, ymax)
    chart_ax.axis("off")

    style_name = _active_style().get("name")
    if annual_target is not None:
        target_kw: dict = {
            "color": _theme_color("target", COLOR_TARGET),
            "linewidth": 1.5 if style_name == "modern" else 2,
            "xmin": 0.02,
            "xmax": 0.92,
        }
        if style_name == "modern":
            target_kw["linestyle"] = (0, (4, 3))
        chart_ax.axhline(annual_target, **target_kw)
        target_label = (
            annual_target_label(indicator, language)
            or format_value(annual_target, unit, language)
            or str(int(annual_target))
        )
        target_y = annual_target
        if annual_target_label(indicator, language):
            for i, val in enumerate(values):
                if math.isnan(val) or abs(val - annual_target) < ymax * 0.06:
                    _, va = _value_label_position(i, val, values, annual_target, ymax)
                    if va == "bottom":
                        target_y = annual_target + ymax * 0.04
                    else:
                        target_y = annual_target - ymax * 0.04
                    break
        chart_ax.text(len(years) - 1 + 0.55, target_y, target_label,
                      color=COLOR_TARGET, fontsize=9, fontweight="bold", va="center", ha="left")

    _plot_line_series(chart_ax, x, values)

    for i, (xi, val) in enumerate(zip(x, values)):
        if math.isnan(val):
            continue
        text = format_value(val, unit, language)
        if not text:
            continue
        y_text, va = _value_label_position(i, val, values, annual_target, ymax)
        if y_text < ymax * 0.1:
            y_text = val + ymax * 0.05
            va = "bottom"
        chart_ax.text(xi, y_text, text, ha="center", va=va, fontsize=9,
                      fontweight="bold", color=COLOR_VALUE, clip_on=True)

    table_ax.axis("off")
    table = table_ax.table(cellText=table_rows, rowLabels=row_labels, loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.35)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("white")
        cell.set_linewidth(0)
        cell.set_facecolor("white")
        if col == -1:
            cell.set_text_props(ha="left", fontweight="normal")
            cell.PAD = 0.05
        else:
            cell.set_text_props(ha="center")




# ---------------------------------------------------------------------------
# Full-dashboard composers (matplotlib path)
# ---------------------------------------------------------------------------

import matplotlib.gridspec as gridspec  # noqa: E402 (grouped with other matplotlib imports above)

from .calculations import section_footnote, section_title  # noqa: E402
from .config import DASHBOARD_SIZES  # noqa: E402
from .layouts import (  # noqa: E402
    NS_TABLE_IMPLEMENTING_COUNT,
    NS_TABLE_NS_UNIT,
    build_section_layout,
    indicator_has_values,
    indicators_with_data,
    mapping_from_model,
    section_has_indicators,
    ns_table_mode,
    visible_donut_pairs,
    visible_indicator_ids,
)
from .payload import (  # noqa: E402
    _indicator_meta,
    _indicator_meta_from_mapping,
    _latest_chartable_value,
    _section_meta_row,
)


def draw_unavailable_cumulative_indicator(
    label_ax,
    message_ax,
    indicator: pd.Series,
    *,
    language: str = "English",
) -> None:
    label_ax.axis("off")
    label_ax.text(
        0.02,
        0.5,
        _wrap_indicator_label(indicator_label(indicator, language)),
        ha="left",
        va="center",
        fontsize=9,
        fontfamily="sans-serif",
        linespacing=1.25,
        transform=label_ax.transAxes,
    )
    label_ax.axvline(0.98, color=_theme_color("divider", COLOR_DIVIDER), linewidth=0.8, ymin=0.08, ymax=0.92)
    message_ax.axis("off")
    message_ax.text(
        0.5,
        0.5,
        not_available(language),
        ha="center",
        va="center",
        fontsize=10,
        color="#888888",
        style="italic",
        transform=message_ax.transAxes,
    )


def _section_subset(model: pd.DataFrame, section: str) -> pd.DataFrame:
    return model[model["section"] == section].copy()


def _draw_title(ax, text: str) -> None:
    ax.axis("off")
    ax.text(0, 0.6, text, ha="left", va="center", fontsize=11, fontweight="bold")


def _draw_footnote(ax, text: str) -> None:
    ax.axis("off")
    ax.axhline(0.95, color=_theme_color("divider", COLOR_DIVIDER), linewidth=0.8)
    ax.text(0, 0.5, text, ha="left", va="center", fontsize=6.5, wrap=True)


def _draw_target_box(ax, text: str) -> None:
    ax.axis("off")
    ax.text(0.5, 0.5, text, ha="center", va="center", fontsize=8, linespacing=1.3)


def _draw_donut_row(
    fig,
    gs,
    model,
    mapping: pd.DataFrame,
    section: str,
    indicator_id: str,
    language: str,
) -> None:
    inner = gs.subgridspec(1, 3, width_ratios=[0.38, 0.22, 0.18], wspace=0.06)
    label_ax = fig.add_subplot(inner[0, 0])
    donut_ax = fig.add_subplot(inner[0, 1])
    target_ax = fig.add_subplot(inner[0, 2])

    if not indicator_has_values(model, section, indicator_id):
        meta = _indicator_meta_from_mapping(mapping, section, indicator_id)
        label_ax.axis("off")
        label_ax.text(
            0.02,
            0.5,
            _wrap_indicator_label(indicator_label(meta, language), width=32),
            ha="left",
            va="center",
            fontsize=8,
            linespacing=1.2,
        )
        donut_ax.axis("off")
        donut_ax.text(
            0.5,
            0.5,
            not_available(language),
            ha="center",
            va="center",
            fontsize=9,
            color="#888888",
        )
        target_ax.axis("off")
        return

    meta = _indicator_meta(model, section, indicator_id)
    value, _ = _latest_chartable_value(model, section, indicator_id)
    if value is None:
        donut_ax.axis("off")
        donut_ax.text(
            0.5,
            0.5,
            not_available(language),
            ha="center",
            va="center",
            fontsize=9,
            color="#888888",
        )
        target_ax.axis("off")
        return
    target_raw = meta.get("Target value")
    target = float(target_raw) if pd.notna(target_raw) else 0.0

    label_ax.axis("off")
    label_ax.text(
        0.02, 0.5, _wrap_indicator_label(indicator_label(meta, language), width=32),
        ha="left", va="center", fontsize=8, linespacing=1.2,
    )
    label_ax.axvline(0.98, color=_theme_color("divider", COLOR_DIVIDER), linewidth=0.8, ymin=0.1, ymax=0.9)
    draw_donut_on_ax(donut_ax, value, target, language=language, indicator_id=indicator_id, unit=indicator_format_unit(meta))
    target_text = target_label_sp(meta, language)
    if target_text:
        _draw_target_box(target_ax, target_text)


def _draw_donut_pair(
    fig,
    gs,
    model,
    mapping: pd.DataFrame,
    section: str,
    indicator_ids: list[str],
    language: str,
) -> None:
    inner = gs.subgridspec(1, 2, wspace=0.08)
    for col, indicator_id in enumerate(indicator_ids):
        cell = inner[0, col].subgridspec(1, 2, width_ratios=[0.58, 0.42], wspace=0.04)
        label_ax = fig.add_subplot(cell[0, 0])
        donut_ax = fig.add_subplot(cell[0, 1])
        if not indicator_has_values(model, section, indicator_id):
            meta = _indicator_meta_from_mapping(mapping, section, indicator_id)
            label_ax.axis("off")
            label_ax.text(
                0,
                0.5,
                _wrap_indicator_label(indicator_label(meta, language), width=28),
                ha="left",
                va="center",
                fontsize=7.5,
                linespacing=1.15,
            )
            donut_ax.axis("off")
            donut_ax.text(
                0.5,
                0.5,
                not_available(language),
                ha="center",
                va="center",
                fontsize=8,
                color="#888888",
            )
            continue
        meta = _indicator_meta(model, section, indicator_id)
        value, _ = _latest_chartable_value(model, section, indicator_id)
        if value is None:
            donut_ax.axis("off")
            donut_ax.text(
                0.5,
                0.5,
                not_available(language),
                ha="center",
                va="center",
                fontsize=8,
                color="#888888",
            )
            continue
        target_raw = meta.get("Target value")
        target = float(target_raw) if pd.notna(target_raw) else 0.0
        label_ax.axis("off")
        label_ax.text(0, 0.5, _wrap_indicator_label(indicator_label(meta, language), width=28),
                      ha="left", va="center", fontsize=7.5, linespacing=1.15)
        draw_donut_on_ax(donut_ax, value, target, language=language, indicator_id=indicator_id, unit=indicator_format_unit(meta))


def render_sp_dashboard(
    model: pd.DataFrame,
    section: str,
    *,
    language: str = "English",
    output_path=None,
    mapping: pd.DataFrame | None = None,
) -> plt.Figure:
    mapping = mapping if mapping is not None else mapping_from_model(model)
    layout = build_section_layout(section, mapping)
    cumulative_ids = indicators_with_data(
        model,
        section,
        visible_indicator_ids(section, layout["cumulative_ids"]),
    )
    donut_pairs = [
        indicators_with_data(model, section, pair_ids)
        for pair_ids in visible_donut_pairs(section, layout.get("donut_pairs", []))
    ]
    if not section_has_indicators(mapping, section):
        raise ValueError(f"No indicators configured for {section}")

    subset = _section_subset(model, section)
    meta0 = _section_meta_row(model, mapping, section)
    row_weights: list[float] = [0.30, 0.55, layout.get("cumulative_weight", len(cumulative_ids) * 1.1)]
    row_weights.extend([layout.get("donut_weight", 0.75)] * len(donut_pairs))
    row_weights.append(0.14)

    height = DASHBOARD_SIZES.get(section, (827, 700))[1] / 100
    fig = plt.figure(figsize=(8.27, height))
    outer = gridspec.GridSpec(
        len(row_weights), 1, figure=fig, height_ratios=row_weights,
        top=0.96, bottom=0.03, left=0.04, right=0.96, hspace=0.22,
    )

    row = 0
    _draw_title(fig.add_subplot(outer[row]), section_title(meta0, language))
    row += 1
    draw_sp_column_headers(fig.add_subplot(outer[row]), language)
    row += 1

    cum_gs = outer[row].subgridspec(len(cumulative_ids), 1, hspace=0.45)
    for i, indicator_id in enumerate(cumulative_ids):
        panel = cum_gs[i].subgridspec(1, 2, width_ratios=[0.36, 0.64], wspace=0.06)
        content = panel[0, 1].subgridspec(2, 1, height_ratios=[0.68, 0.32], hspace=0.12)
        if not indicator_has_values(model, section, indicator_id):
            indicator = _indicator_meta_from_mapping(mapping, section, indicator_id)
            draw_unavailable_cumulative_indicator(
                fig.add_subplot(panel[0, 0]),
                fig.add_subplot(panel[0, 1]),
                indicator,
                language=language,
            )
            continue
        indicator = _indicator_meta(model, section, indicator_id)
        data = subset[subset["ID"] == indicator_id].sort_values("Year")
        draw_cumulative_indicator(
            fig.add_subplot(panel[0, 0]), fig.add_subplot(content[0]), fig.add_subplot(content[1]),
            indicator, data, language=language,
        )
    row += 1

    for pair in donut_pairs:
        _draw_donut_pair(fig, outer[row], model, mapping, section, pair, language)
        row += 1

    _draw_footnote(fig.add_subplot(outer[row]), section_footnote(section, language))

    if output_path:
        from pathlib import Path as _Path
        _Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, bbox_inches="tight", facecolor="white", dpi=120)
    return fig


def render_ef_dashboard(
    model: pd.DataFrame,
    section: str,
    *,
    language: str = "English",
    output_path=None,
    mapping: pd.DataFrame | None = None,
) -> plt.Figure:
    mapping = mapping if mapping is not None else mapping_from_model(model)
    if not section_has_indicators(mapping, section):
        raise ValueError(f"No indicators configured for {section}")

    subset = _section_subset(model, section)
    meta0 = _section_meta_row(model, mapping, section)
    layout = build_section_layout(section, mapping)
    cumulative_ids = indicators_with_data(
        model,
        section,
        visible_indicator_ids(section, layout["cumulative_ids"]),
    )

    row_weights: list[float] = [0.30, 0.55, len(cumulative_ids) * 1.1, 0.14]
    height = DASHBOARD_SIZES.get(section, (827, 600))[1] / 100
    fig = plt.figure(figsize=(8.27, height))
    outer = gridspec.GridSpec(
        len(row_weights), 1, figure=fig, height_ratios=row_weights,
        top=0.96, bottom=0.03, left=0.04, right=0.96, hspace=0.22,
    )

    row = 0
    _draw_title(fig.add_subplot(outer[row]), section_title(meta0, language))
    row += 1
    draw_sp_column_headers(fig.add_subplot(outer[row]), language)
    row += 1

    cum_gs = outer[row].subgridspec(len(cumulative_ids), 1, hspace=0.45)
    for i, indicator_id in enumerate(cumulative_ids):
        panel = cum_gs[i].subgridspec(1, 2, width_ratios=[0.36, 0.64], wspace=0.06)
        content = panel[0, 1].subgridspec(2, 1, height_ratios=[0.68, 0.32], hspace=0.12)
        if not indicator_has_values(model, section, indicator_id):
            indicator = _indicator_meta_from_mapping(mapping, section, indicator_id)
            draw_unavailable_cumulative_indicator(
                fig.add_subplot(panel[0, 0]),
                fig.add_subplot(panel[0, 1]),
                indicator,
                language=language,
            )
            continue
        indicator = _indicator_meta(model, section, indicator_id)
        data = subset[subset["ID"] == indicator_id].sort_values("Year")
        draw_cumulative_indicator(
            fig.add_subplot(panel[0, 0]), fig.add_subplot(content[0]), fig.add_subplot(content[1]),
            indicator, data, language=language, ns_breakdown=True,
        )
    row += 1

    _draw_footnote(fig.add_subplot(outer[row]), section_footnote(section, language))

    if output_path:
        from pathlib import Path as _Path
        _Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, bbox_inches="tight", facecolor="white", dpi=120)
    return fig


def render_dashboard(
    model: pd.DataFrame,
    section: str,
    *,
    language: str = "English",
    output_path=None,
    renderer: str | None = None,
    session=None,
    mapping: pd.DataFrame | None = None,
) -> plt.Figure | Path:
    """Render a dashboard section. Default renderer is HTML/SVG (publication quality)."""
    import os
    chosen = renderer or os.environ.get("PB_FIGURES_RENDERER", "html")
    if chosen == "html":
        from .render_html import render_dashboard_html
        return render_dashboard_html(
            model,
            section,
            language=language,
            output_path=output_path,
            session=session,
            mapping=mapping,
        )
    if section.startswith("EF"):
        return render_ef_dashboard(
            model, section, language=language, output_path=output_path, mapping=mapping,
        )
    return render_sp_dashboard(
        model, section, language=language, output_path=output_path, mapping=mapping,
    )
