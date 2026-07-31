"""Pure-Python SVG donut charts for P&B figures."""

from __future__ import annotations

import html
import math
from typing import Any

from .styles import resolve_style


def _esc(text: str | None) -> str:
    return html.escape(str(text or ""))


def _donut_has_target(item: dict[str, Any]) -> bool:
    target = float(item.get("target") or 0)
    return math.isfinite(target) and target > 0


def _render_donut_label(cx: float, cy: float, label: str | None, *, text_color: str) -> str:
    lines = str(label or "").split("\n")
    if len(lines) <= 1:
        return (
            f'<text x="{cx}" y="{cy + 4}" text-anchor="middle" font-size="11" '
            f'font-weight="700" fill="{text_color}">{_esc(label)}</text>'
        )
    line_height = 11
    start_y = cy + 2 - ((len(lines) - 1) * line_height) / 2
    parts = [
        f'<text text-anchor="middle" font-size="11" font-weight="700" fill="{text_color}">',
    ]
    for index, line in enumerate(lines):
        parts.append(f'<tspan x="{cx}" y="{start_y + index * line_height}">{_esc(line)}</tspan>')
    parts.append("</text>")
    return "".join(parts)


def render_donut_svg(
    item: dict[str, Any],
    *,
    show_label: bool = True,
    language: str = "English",
) -> str:
    """Render a donut chart as SVG (mirrors chart_asset.html renderDonut)."""
    del language  # reserved for future RTL font selection in SVG
    colors = resolve_style()["colors"]
    value_color = colors["value"]
    gap_color = colors["gap"]
    text_color = colors["text"]

    size = 64
    cx = cy = 32
    radius = 26
    stroke = 10

    if item.get("unavailable"):
        label = item.get("unavailable_label") or item.get("value_label") or ""
        label_svg = _render_donut_label(cx, cy, label, text_color=text_color) if show_label else ""
        return (
            f'<svg viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">'
            f"{label_svg}</svg>"
        )

    label_svg = ""
    if show_label:
        label_svg = _render_donut_label(cx, cy, item.get("value_label"), text_color=text_color)

    if not _donut_has_target(item):
        return (
            f'<svg viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">'
            f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="{value_color}" '
            f'stroke-width="{stroke}"/>'
            f"{label_svg}</svg>"
        )

    value = max(float(item.get("value") or 0), 0)
    target = max(float(item.get("target") or 0), value)
    pct = min(value / target, 1) if target else 0
    circumference = 2 * math.pi * radius
    filled = circumference * pct
    gap = circumference - filled

    return (
        f'<svg viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">'
        f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="{gap_color}" '
        f'stroke-width="{stroke}"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="{value_color}" '
        f'stroke-width="{stroke}" stroke-dasharray="{filled} {gap}" '
        f'stroke-dashoffset="{circumference * 0.25}" stroke-linecap="butt"/>'
        f"{label_svg}</svg>"
    )
