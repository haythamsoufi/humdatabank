"""Build report-embeddable dashboard HTML with chart-only PNG assets."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from .payload import build_payload
from .layouts import cumulative_table_rows
from .line_chart import (
    CHART_HEIGHT,
    CHART_PAD_L,
    CHART_PAD_R,
    _value_label_y_px,
    render_line_chart_svg,
    target_label_layout,
    x_percent,
    y_scale,
)
from .render_docx import render_donut_asset, render_line_chart_asset
DASHBOARD_WIDTH = 827
LABEL_COL = 290
DASHBOARD_PAD_H = 44
GRID_GAP = 12
_RAW_TABLE = ' markdown="0"'


def _indicator_colgroup() -> str:
    return f'<colgroup><col style="width:{LABEL_COL}px"><col></colgroup>'


def _chart_width() -> int:
    return DASHBOARD_WIDTH - DASHBOARD_PAD_H - LABEL_COL - GRID_GAP


def _esc(text: str | None) -> str:
    return html.escape(str(text or ""))


def _esc_multiline(text: str | None) -> str:
    """Escape text and keep it on one physical line for Pandoc raw HTML."""
    return _esc(text).replace("\n", "<br>")


def _render_value_labels(
    item: dict[str, Any],
    chart_width: int,
) -> str:
    annual_target = item.get("annual_target")
    _, y_max = y_scale(
        next((v for v in item["values"] if v is not None), 0),
        item["values"],
        annual_target,
    )
    parts: list[str] = []
    for i, (val, label) in enumerate(zip(item["values"], item["value_labels"])):
        if val is None or not label:
            continue
        ly, above = _value_label_y_px(i, val, item["values"], annual_target, y_max)
        if above:
            transform = "translate(-50%, -100%)"
        else:
            transform = "translateX(-50%)"
        y_pct = (ly / CHART_HEIGHT) * 100
        x_pct = x_percent(i, len(item["values"]), chart_width)
        parts.append(
            f'<span class="chart-value-label" style="left:{x_pct:.4f}%;top:{y_pct:.4f}%;'
            f'transform:{transform}">{_esc(label)}</span>'
        )
    return "".join(parts)


def _render_target_labels(
    item: dict[str, Any],
    target_label: str,
    chart_width: int,
) -> str:
    annual_target = item.get("annual_target")
    if annual_target is None:
        return ""
    y_px, _ = y_scale(annual_target, item["values"], annual_target)
    y_pct = (y_px / CHART_HEIGHT) * 100
    right_pct = ((chart_width - CHART_PAD_R + 6) / chart_width) * 100
    layout = target_label_layout(
        item["values"],
        item["value_labels"],
        annual_target,
        item.get("annual_target_label"),
        chart_width,
    )
    tag_transform = "translateY(4px)" if layout["tag_below"] else "translateY(-100%)"
    parts = [
        f'<span class="chart-target-tag" style="top:{y_pct:.4f}%;left:4px;transform:{tag_transform}">'
        f'{_esc(target_label)}</span>',
    ]
    if item.get("annual_target_label"):
        if layout["value_above"]:
            value_transform = "translateY(-100%)"
        elif layout["value_below"]:
            value_transform = "translateY(4px)"
        else:
            value_transform = "translateY(-50%)"
        parts.append(
            f'<span class="chart-target-value" style="top:{y_pct:.4f}%;left:{right_pct:.4f}%;'
            f'transform:{value_transform}">{_esc(item["annual_target_label"])}</span>'
        )
    return "".join(parts)


def _render_year_data_grid(item: dict[str, Any]) -> str:
    n = len(item["years"])
    if n == 0:
        return ""
    show_reporting, show_implementing = cumulative_table_rows(item)
    col_pct = 100.0 / n
    colgroup = "".join(f'<col style="width:{col_pct:.6f}%">' for _ in range(n))

    def _row(values: list[str], *, row_class: str = "") -> str:
        cls = f' class="{row_class}"' if row_class else ""
        cells = "".join(f"<td>{_esc(value)}</td>" for value in values)
        return f"<tr{cls}>{cells}</tr>"

    parts = [
        f'<table class="year-data-grid" role="presentation"{_RAW_TABLE}>',
        f"<colgroup>{colgroup}</colgroup>",
        _row(item["years"], row_class="year-row"),
    ]
    if show_reporting:
        parts.append(_row(item["reporting"]))
    if show_implementing:
        parts.append(_row(item["implementing"]))
    parts.append("</table>")
    return "".join(parts)



def _render_data_table(item: dict[str, Any], chart_width: int) -> str:
    del chart_width
    return f'<div class="table-data">{_render_year_data_grid(item)}</div>'


def _render_data_table_cells(item: dict[str, Any], chart_width: int) -> str:
    del chart_width
    return f'<td class="table-data">{_render_year_data_grid(item)}</td>'


def _render_metric_labels(labels: dict[str, str], item: dict[str, Any]) -> str:
    show_reporting, show_implementing = cumulative_table_rows(item)
    parts = [
        '<div class="metric-labels">',
        f'<span class="year-label">{_esc(labels["year"])}</span>',
    ]
    if show_reporting:
        parts.append(f'<span>{_esc(labels["reporting"])}</span>')
    if show_implementing:
        parts.append(f'<span>{_esc(labels["implementing"])}</span>')
    parts.append("</div>")
    return "".join(parts)


def _render_metric_label_rows(labels: dict[str, str], item: dict[str, Any]) -> str:
    show_reporting, show_implementing = cumulative_table_rows(item)
    rows = [f'<tr><td class="year-label">{_esc(labels["year"])}</td></tr>']
    if show_reporting:
        rows.append(f"<tr><td>{_esc(labels['reporting'])}</td></tr>")
    if show_implementing:
        rows.append(f"<tr><td>{_esc(labels['implementing'])}</td></tr>")
    return "".join(rows)


def _render_metric_labels_cells(labels: dict[str, str], item: dict[str, Any]) -> str:
    return (
        '<td class="metric-labels">'
        f'<table class="metric-label-grid" role="presentation"{_RAW_TABLE}>{_render_metric_label_rows(labels, item)}</table>'
        "</td>"
    )


def _render_unavailable_line_block(item: dict[str, Any]) -> str:
    return (
        f'<table class="indicator-row indicator-unavailable" role="presentation"{_RAW_TABLE}>'
        f"{_indicator_colgroup()}"
        "<tr>"
        f'<td class="indicator-text">{_esc(item["label"])}</td>'
        f'<td class="indicator-unavailable-message">{_esc(item.get("unavailable_label"))}</td>'
        "</tr></table>"
    )


def _render_line_block(
    item: dict[str, Any],
    *,
    chart_index: int,
    target_label: str,
    table_labels: dict[str, str],
    chart_width: int,
    chart_id_prefix: str = "sp",
    asset_refs: dict[str, str] | None = None,
) -> str:
    if item.get("unavailable"):
        return _render_unavailable_line_block(item)
    year_only = not item.get("show_ns_breakdown", True)
    footer_class = "x-axis-footer year-only" if year_only else "x-axis-footer"
    asset_refs = asset_refs or {}
    line_src = asset_refs.get(f"line_{chart_index}", "")
    if line_src:
        chart_inner = (
            f'<div class="line-chart-inner" style="--chart-width:{chart_width}">'
            f'<img class="line-chart-img" src="{_esc(line_src)}" alt="" '
            f'width="{chart_width}" height="110" role="presentation">'
            "</div>"
        )
    else:
        chart_svg = render_line_chart_svg(
            item, chart_width, chart_id=f"{chart_id_prefix}-line-{chart_index}",
        )
        chart_inner = (
            f'<div class="line-chart-inner" style="--chart-width:{chart_width}">'
            f"{chart_svg}"
            f'{_render_target_labels(item, target_label, chart_width)}'
            f'{_render_value_labels(item, chart_width)}'
            "</div>"
        )
    return (
        f'<table class="indicator-row" role="presentation"{_RAW_TABLE}>'
        f"{_indicator_colgroup()}"
        "<tr>"
        f'<td class="indicator-text">{_esc(item["label"])}</td>'
        f'<td class="line-chart-wrap">{chart_inner}</td>'
        "</tr>"
        '<tr class="x-axis-divider-row">'
        '<td class="x-axis-divider-left"></td>'
        '<td class="x-axis-divider-right"></td>'
        "</tr>"
        f'<tr class="{footer_class}">'
        f"{_render_metric_labels_cells(table_labels, item)}"
        f"{_render_data_table_cells(item, chart_width)}"
        "</tr>"
        "</table>"
    )


def _render_donut_block(item: dict[str, Any], *, donut_src: str) -> str:
    if item.get("unavailable"):
        return (
            f'<table class="donut-row indicator-unavailable" role="presentation"{_RAW_TABLE}>'
            "<tr>"
            f'<td class="indicator-text">{_esc(item["label"])}</td>'
            f'<td class="indicator-unavailable-message" colspan="2">{_esc(item.get("unavailable_label"))}</td>'
            "</tr></table>"
        )
    label_lines = _esc(item["value_label"]).replace("\n", "<br>")
    target_html = ""
    if item.get("target_label"):
        target_html = f'<td class="donut-target">{_esc_multiline(item["target_label"])}</td>'
    return (
        f'<table class="donut-row" role="presentation"{_RAW_TABLE}>'
        "<tr>"
        f'<td class="indicator-text">{_esc(item["label"])}</td>'
        '<td class="donut-visual">'
        f'<img class="donut-img" src="{_esc(donut_src)}" alt="" role="presentation">'
        f'<span class="donut-center-label">{label_lines}</span>'
        "</td>"
        f"{target_html}"
        "</tr></table>"
    )


def _render_donut_pair_item(item: dict[str, Any], *, donut_src: str) -> str:
    if item.get("unavailable"):
        return (
            f'<table class="donut-pair-item indicator-unavailable" role="presentation"{_RAW_TABLE}>'
            "<tr>"
            f'<td class="indicator-text">{_esc(item["label"])}</td>'
            f'<td class="indicator-unavailable-message">{_esc(item.get("unavailable_label"))}</td>'
            "</tr></table>"
        )
    label_lines = _esc(item["value_label"]).replace("\n", "<br>")
    return (
        f'<table class="donut-pair-item" role="presentation"{_RAW_TABLE}>'
        "<tr>"
        f'<td class="indicator-text">{_esc(item["label"])}</td>'
        '<td class="donut-visual">'
        f'<img class="donut-img" src="{_esc(donut_src)}" alt="" role="presentation">'
        f'<span class="donut-center-label">{label_lines}</span>'
        "</td>"
        "</tr></table>"
    )


def _append_section_tail(parts: list[str], footnote: str) -> None:
    """Wrap only the last dashboard block with the footnote for print/PDF."""
    footnote_html = f'<div class="footnote" markdown="0">{_esc_multiline(footnote)}</div>'
    if len(parts) > 1:
        last_block = parts.pop()
        parts.append(f'<div class="section-tail">{last_block}{footnote_html}</div>')
    else:
        parts.append(footnote_html)


def _render_sp_html(
    payload: dict[str, Any],
    asset_refs: dict[str, str],
) -> str:
    chart_width = _chart_width()
    target_label = payload["headers"]["target"]
    chart_id_prefix = payload["section"].lower()
    parts = [f'<div class="dash-title">{_esc(payload["title"])}</div>']

    for idx, item in enumerate(payload["cumulative"]):
        parts.append(
            _render_line_block(
                item,
                chart_index=idx,
                target_label=target_label,
                table_labels=payload["table_labels"],
                chart_width=chart_width,
                chart_id_prefix=chart_id_prefix,
                asset_refs=asset_refs,
            )
        )

    for row_idx, pair in enumerate(payload.get("donut_pairs", [])):
        pair_parts = [f'<table class="donut-pair" role="presentation"{_RAW_TABLE}><tr>']
        for col_idx, item in enumerate(pair):
            donut_src = asset_refs.get(f"pair_{row_idx}_{col_idx}_donut", "")
            pair_parts.append(f"<td>{_render_donut_pair_item(item, donut_src=donut_src)}</td>")
        pair_parts.append("</tr></table>")
        parts.append("".join(pair_parts))

    _append_section_tail(parts, payload["footnote"])
    return "".join(parts)


def build_dashboard_html(
    payload: dict[str, Any],
    asset_refs: dict[str, str],
) -> str:
    """Return inner HTML for a dashboard section (no wrapper)."""
    return _render_sp_html(payload, asset_refs)


def render_section_assets(
    payload: dict[str, Any],
    assets_dir: Path,
    *,
    language: str = "English",
) -> dict[str, str]:
    """Generate chart PNG assets; return map of asset key → relative filename."""
    assets_dir = Path(assets_dir)
    assets_dir.mkdir(parents=True, exist_ok=True)
    refs: dict[str, str] = {}

    if payload["type"] != "sp":
        return refs

    target_label = payload["headers"]["target"]
    for idx, item in enumerate(payload["cumulative"]):
        if item.get("unavailable"):
            continue
        filename = f"line_{idx}.png"
        render_line_chart_asset(
            item,
            target_label,
            assets_dir / filename,
            language=language,
        )
        refs[f"line_{idx}"] = filename

    for row_idx, pair in enumerate(payload.get("donut_pairs", [])):
        for col_idx, item in enumerate(pair):
            if item.get("unavailable"):
                continue
            filename = f"pair_{row_idx}_{col_idx}_donut.png"
            render_donut_asset(
                item, assets_dir / filename, language=language, show_label=False,
            )
            refs[f"pair_{row_idx}_{col_idx}_donut"] = filename

    return refs


def expected_asset_refs(payload: dict[str, Any]) -> dict[str, str]:
    """Map asset keys to filenames without rendering."""
    refs: dict[str, str] = {}
    if payload["type"] != "sp":
        return refs

    for row_idx, pair in enumerate(payload.get("donut_pairs", [])):
        for col_idx, item in enumerate(pair):
            if not item.get("unavailable"):
                refs[f"pair_{row_idx}_{col_idx}_donut"] = f"pair_{row_idx}_{col_idx}_donut.png"

    return refs


def build_section_embed(
    model,
    section: str,
    *,
    language: str = "English",
    assets_dir: Path,
    asset_url_prefix: str,
    render_assets: bool = True,
    mapping=None,
) -> str:
    """Build full embeddable dashboard HTML for one section."""
    payload = build_payload(model, section, language, mapping=mapping)
    if render_assets:
        local_refs = render_section_assets(payload, assets_dir, language=language)
    else:
        local_refs = expected_asset_refs(payload)
    url_refs = {key: f"{asset_url_prefix}/{filename}" for key, filename in local_refs.items()}
    inner = build_dashboard_html(payload, url_refs)
    direction = ' dir="rtl"' if language == "Arabic" else ""
    return f'<div class="pb-dashboard"{direction}>{inner}</div>'
