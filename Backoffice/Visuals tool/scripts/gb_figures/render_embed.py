"""Build report-embeddable dashboard HTML with chart-only PNG assets."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from .payload import build_payload
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
from .render_docx import render_donut_asset
DASHBOARD_WIDTH = 827
LABEL_COL = 290
DASHBOARD_PAD_H = 44
GRID_GAP = 12


def _chart_width() -> int:
    return DASHBOARD_WIDTH - DASHBOARD_PAD_H - LABEL_COL - GRID_GAP


def _esc(text: str | None) -> str:
    return html.escape(str(text or ""))


def _esc_multiline(text: str | None) -> str:
    """Escape text and keep it on one physical line for Pandoc raw HTML."""
    return _esc(text).replace("\n", "<br>")


def _format_ef_cell_html(cell: dict[str, Any]) -> str:
    if not cell.get("value"):
        return _esc(cell["text"])
    main = cell.get("main", cell["text"])
    suffix = cell.get("suffix", "")
    if not suffix:
        return f'<span class="value-main">{_esc(main)}</span>'
    return (
        f'<span class="value-main">{_esc(main)}</span>'
        f'<span class="value-suffix">{_esc(suffix)}</span>'
    )


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


def _render_positioned_row(
    values: list[str],
    count: int,
    chart_width: int,
    *,
    cell_class: str = "",
) -> str:
    cls = f"table-cell {cell_class}".strip()
    cells = "".join(
        f'<span class="{cls}" style="left:{x_percent(i, count, chart_width):.4f}%">'
        f'{_esc(v)}</span>'
        for i, v in enumerate(values)
    )
    return f'<div class="table-row">{cells}</div>'


def _render_table_vlines(count: int, chart_width: int) -> str:
    if count <= 1:
        return ""
    parts: list[str] = []
    for i in range(count - 1):
        pct = (x_percent(i, count, chart_width) + x_percent(i + 1, count, chart_width)) / 2
        parts.append(f'<span class="table-vline" style="left:{pct:.4f}%"></span>')
    return "".join(parts)


def _render_data_table(item: dict[str, Any], chart_width: int) -> str:
    n = len(item["years"])
    parts = [
        '<div class="table-data">',
        _render_table_vlines(n, chart_width),
        _render_positioned_row(item["years"], n, chart_width, cell_class="year-cell"),
    ]
    if item.get("show_ns_breakdown", True):
        parts.extend([
            _render_positioned_row(item["reporting"], n, chart_width),
            _render_positioned_row(item["implementing"], n, chart_width),
        ])
    parts.append("</div>")
    return "".join(parts)


def _render_metric_labels(labels: dict[str, str], *, show_ns_breakdown: bool = True) -> str:
    parts = [
        '<div class="metric-labels">',
        f'<span class="year-label">{_esc(labels["year"])}</span>',
    ]
    if show_ns_breakdown:
        parts.extend([
            f'<span>{_esc(labels["reporting"])}</span>',
            f'<span>{_esc(labels["implementing"])}</span>',
        ])
    parts.append("</div>")
    return "".join(parts)


def _render_line_block(
    item: dict[str, Any],
    *,
    chart_index: int,
    target_label: str,
    table_labels: dict[str, str],
    chart_width: int,
) -> str:
    year_only = not item.get("show_ns_breakdown", True)
    footer_class = "x-axis-footer year-only" if year_only else "x-axis-footer"
    chart_svg = render_line_chart_svg(item, chart_width, chart_id=f"sp-line-{chart_index}")
    return (
        '<div class="indicator-row">'
        f'<div class="indicator-text">{_esc(item["label"])}</div>'
        '<div class="line-chart-wrap">'
        f'<div class="line-chart-inner" style="--chart-width:{chart_width}">'
        f"{chart_svg}"
        f'{_render_target_labels(item, target_label, chart_width)}'
        f'{_render_value_labels(item, chart_width)}'
        "</div>"
        "</div>"
        '<div class="x-axis-divider-row">'
        '<div class="x-axis-divider-left"></div>'
        '<div class="x-axis-divider-right"></div>'
        "</div>"
        f'<div class="{footer_class}">'
        f'{_render_metric_labels(table_labels, show_ns_breakdown=not year_only)}'
        f'{_render_data_table(item, chart_width)}'
        "</div>"
        "</div>"
    )


def _render_donut_block(item: dict[str, Any], *, donut_src: str) -> str:
    label_lines = _esc(item["value_label"]).replace("\n", "<br>")
    target_html = ""
    if item.get("target_label"):
        target_html = f'<div class="donut-target">{_esc_multiline(item["target_label"])}</div>'
    return (
        '<div class="donut-row">'
        f'<div class="indicator-text">{_esc(item["label"])}</div>'
        '<div class="donut-visual">'
        f'<img class="donut-img" src="{_esc(donut_src)}" alt="" role="presentation">'
        f'<span class="donut-center-label">{label_lines}</span>'
        "</div>"
        f"{target_html}"
        "</div>"
    )


def _render_donut_pair_item(item: dict[str, Any], *, donut_src: str) -> str:
    label_lines = _esc(item["value_label"]).replace("\n", "<br>")
    return (
        '<div class="donut-pair-item">'
        f'<div class="indicator-text">{_esc(item["label"])}</div>'
        '<div class="donut-visual">'
        f'<img class="donut-img" src="{_esc(donut_src)}" alt="" role="presentation">'
        f'<span class="donut-center-label">{label_lines}</span>'
        "</div>"
        "</div>"
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
    parts = [f'<div class="dash-title">{_esc(payload["title"])}</div>']

    for idx, item in enumerate(payload["cumulative"]):
        parts.append(
            _render_line_block(
                item,
                chart_index=idx,
                target_label=target_label,
                table_labels=payload["table_labels"],
                chart_width=chart_width,
            )
        )

    if payload.get("donut_pair"):
        pair_parts = ['<div class="donut-pair">']
        for idx, item in enumerate(payload["donut_pair"]):
            donut_src = asset_refs[f"pair_{idx}_donut"]
            pair_parts.append(_render_donut_pair_item(item, donut_src=donut_src))
        pair_parts.append("</div>")
        parts.append("".join(pair_parts))

    for idx, item in enumerate(payload.get("donuts", [])):
        donut_src = asset_refs[f"donut_{idx}_donut"]
        parts.append(_render_donut_block(item, donut_src=donut_src))

    _append_section_tail(parts, payload["footnote"])
    return "".join(parts)


def _ef_colgroup(show_target: bool, n_years: int) -> str:
    if n_years <= 0:
        return ""
    year_width = (60 if show_target else 55) / n_years
    parts = ["<colgroup><col>"]
    if show_target:
        parts.append('<col style="width:120px">')
    parts.extend(f'<col style="width:{year_width:.4f}%">' for _ in range(n_years))
    parts.append("</colgroup>")
    return "".join(parts)


def _render_ef_html(payload: dict[str, Any]) -> str:
    show_target = payload.get("show_target_column", True)
    no_target_class = "" if show_target else " no-target"
    n_years = len(payload["headers"]["years"])
    parts = [
        f'<div class="dash-title">{_esc(payload["title"])}</div>',
        '<div class="section-tail">',
        f'<table class="ef-table{no_target_class}">',
        _ef_colgroup(show_target, n_years),
        "<thead><tr>",
        f'<th>{_esc(payload["headers"]["indicator"])}</th>',
    ]
    if show_target:
        parts.append(f'<th>{_esc(payload["headers"]["target"])}</th>')
    parts.extend(f"<th>{_esc(y)}</th>" for y in payload["headers"]["years"])
    parts.append("</tr></thead><tbody>")
    for row in payload["rows"]:
        parts.append("<tr>")
        parts.append(f"<td>{_esc(row['label'])}</td>")
        if show_target:
            parts.append(f"<td>{_esc(row['target'])}</td>")
        parts.extend(
            f'<td class="{"value-cell" if c["value"] else ""}">{_format_ef_cell_html(c)}</td>'
            for c in row["years"]
        )
        parts.append("</tr>")
    parts.extend([
        "</tbody></table>",
        f'<div class="footnote" markdown="0">{_esc_multiline(payload["footnote"])}</div>',
        "</div>",
    ])
    return "".join(parts)


def build_dashboard_html(
    payload: dict[str, Any],
    asset_refs: dict[str, str],
) -> str:
    """Return inner HTML for a dashboard section (no wrapper)."""
    if payload["type"] == "ef":
        return _render_ef_html(payload)
    return _render_sp_html(payload, asset_refs)


def render_section_assets(
    payload: dict[str, Any],
    assets_dir: Path,
    *,
    language: str = "English",
    session=None,
) -> dict[str, str]:
    """Generate chart PNG assets; return map of asset key → relative filename."""
    assets_dir = Path(assets_dir)
    assets_dir.mkdir(parents=True, exist_ok=True)
    refs: dict[str, str] = {}

    if payload["type"] != "sp":
        return refs

    if payload.get("donut_pair"):
        for idx, item in enumerate(payload["donut_pair"]):
            filename = f"pair_{idx}_donut.png"
            render_donut_asset(
                item, assets_dir / filename, language=language, show_label=False, session=session,
            )
            refs[f"pair_{idx}_donut"] = filename

    for idx, item in enumerate(payload.get("donuts", [])):
        filename = f"donut_{idx}_donut.png"
        render_donut_asset(
            item, assets_dir / filename, language=language, show_label=False, session=session,
        )
        refs[f"donut_{idx}_donut"] = filename

    return refs


def expected_asset_refs(payload: dict[str, Any]) -> dict[str, str]:
    """Map asset keys to filenames without rendering."""
    refs: dict[str, str] = {}
    if payload["type"] != "sp":
        return refs

    if payload.get("donut_pair"):
        for idx in range(len(payload["donut_pair"])):
            refs[f"pair_{idx}_donut"] = f"pair_{idx}_donut.png"

    for idx in range(len(payload.get("donuts", []))):
        refs[f"donut_{idx}_donut"] = f"donut_{idx}_donut.png"

    return refs


def build_section_embed(
    model,
    section: str,
    *,
    language: str = "English",
    assets_dir: Path,
    asset_url_prefix: str,
    session=None,
    render_assets: bool = True,
) -> str:
    """Build full embeddable dashboard HTML for one section."""
    payload = build_payload(model, section, language)
    if render_assets:
        local_refs = render_section_assets(payload, assets_dir, language=language, session=session)
    else:
        local_refs = expected_asset_refs(payload)
    url_refs = {key: f"{asset_url_prefix}/{filename}" for key, filename in local_refs.items()}
    inner = build_dashboard_html(payload, url_refs)
    direction = ' dir="rtl"' if language == "Arabic" else ""
    return f'<div class="gb-dashboard"{direction}>{inner}</div>'
