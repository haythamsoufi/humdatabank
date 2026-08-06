"""Line chart positioning math and HTML injection helpers."""

from __future__ import annotations

import html
import re
from pathlib import Path

from .config import COLOR_TARGET, COLOR_VALUE
from .font_faces import tajawal_face_css
from .languages import is_rtl
from .styles import resolve_style, style_payload

_LATIN_CHART_FONT = '"Open Sans", "Segoe UI", sans-serif'
_ARABIC_CHART_FONT = '"Tajawal", sans-serif'
_ARABIC_MILLIONS_NUM_FIRST = re.compile(r"^([\d.,]+)\s+(.+)$")
_ARABIC_MILLIONS_WORD_FIRST = re.compile(r"^(.+?)\s+([\d.,]+)$")

# Chart canvas constants (pixels)
CHART_HEIGHT = 110
CHART_PAD_L = 24
CHART_PAD_R = 52
CHART_PAD_TOP = 22
CHART_PAD_BOTTOM = 8
LABEL_ABOVE_OFFSET = 10
LABEL_BELOW_OFFSET = 16
MIN_LABEL_CLEARANCE_FROM_BOTTOM = 12

LINE_CHART_JS_PATH = Path(__file__).parent / "templates" / "line_chart.js"
_LINE_CHART_JS_PLACEHOLDER = "__LINE_CHART_JS__"


def _chart_font_family(language: str) -> str:
    return _ARABIC_CHART_FONT if is_rtl(language) else _LATIN_CHART_FONT


def _svg_font_family_attr(language: str) -> str:
    """Escape font-family for double-quoted SVG/XML attributes."""
    return html.escape(_chart_font_family(language), quote=True)


def _svg_embedded_style(css: str) -> str:
    return f"<style><![CDATA[{css}]]></style>"


def _svg_style_defs(language: str) -> str:
    if not is_rtl(language):
        return ""
    return f"<defs>{_svg_embedded_style(tajawal_face_css(inline=True))}</defs>"


def _svg_chart_text(
    label: str,
    *,
    x: float,
    y: float,
    language: str,
    fill: str,
    font_size: int | str,
    font_weight: str = "700",
    text_anchor: str = "middle",
    dominant_baseline: str | None = None,
) -> str:
    font_family = _svg_font_family_attr(language)
    baseline_attr = f' dominant-baseline="{dominant_baseline}"' if dominant_baseline else ""
    text = str(label or "").strip()
    if not text:
        return ""

    if is_rtl(language):
        match = _ARABIC_MILLIONS_WORD_FIRST.match(text)
        if not match:
            match_num_first = _ARABIC_MILLIONS_NUM_FIRST.match(text)
            if match_num_first:
                num, word = match_num_first.group(1), match_num_first.group(2).strip()
            else:
                num, word = None, text
        else:
            word, num = match.group(1).strip(), match.group(2)

        if num:
            inner = (
                f'<tspan>{html.escape(word)} </tspan>'
                f'<tspan direction="ltr" unicode-bidi="embed">{html.escape(num)}</tspan>'
            )
        else:
            inner = html.escape(word)
        return (
            f'<text x="{x:.2f}" y="{y:.2f}" text-anchor="{text_anchor}" fill="{fill}" '
            f'font-size="{font_size}" font-weight="{font_weight}" font-family="{font_family}" '
            f'direction="rtl"{baseline_attr}>{inner}</text>'
        )

    return (
        f'<text x="{x:.2f}" y="{y:.2f}" text-anchor="{text_anchor}" fill="{fill}" '
        f'font-size="{font_size}" font-weight="{font_weight}" font-family="{font_family}"{baseline_attr}>'
        f"{html.escape(text)}</text>"
    )


# ---------------------------------------------------------------------------
# Positioning helpers
# ---------------------------------------------------------------------------

def y_scale(
    value: float,
    values: list[float | None],
    annual_target: float | None,
) -> tuple[float, float]:
    numeric = [v for v in values if v is not None]
    all_y = list(numeric)
    if annual_target is not None:
        all_y.append(annual_target)
    y_max = max(all_y) * 1.18 if all_y else 1
    pad_t, pad_b = 22, 8
    y_px = pad_t + (CHART_HEIGHT - pad_t - pad_b) * (1 - value / y_max)
    return y_px, y_max


def x_percent(index: int, count: int, width: int) -> float:
    w = width - CHART_PAD_L - CHART_PAD_R
    step = w / (count - 1) if count > 1 else 0
    x = CHART_PAD_L + index * step
    return (x / width) * 100


def _nearest_value(values: list[float | None], index: int, direction: int) -> float | None:
    step = -1 if direction < 0 else 1
    i = index + step
    while 0 <= i < len(values):
        if values[i] is not None:
            return values[i]
        i += step
    return None


def chart_data_bottom_y() -> float:
    return CHART_PAD_TOP + (CHART_HEIGHT - CHART_PAD_TOP - CHART_PAD_BOTTOM)


def value_label_above(
    index: int,
    value: float,
    values: list[float | None],
    annual_target: float | None,
    y_max: float,
) -> bool:
    prev = _nearest_value(values, index, -1)
    nxt = _nearest_value(values, index, 1)
    above = True
    if prev is not None and nxt is not None and value <= prev and value <= nxt:
        above = False
    if annual_target is not None and abs(value - annual_target) < y_max * 0.08:
        above = value < annual_target
    return above


def _value_label_y_px(
    index: int,
    value: float,
    values: list[float | None],
    annual_target: float | None,
    y_max: float,
) -> tuple[float, bool]:
    above = value_label_above(index, value, values, annual_target, y_max)
    v_y, _ = y_scale(value, values, annual_target)
    if above:
        return v_y - LABEL_ABOVE_OFFSET, True
    below_y = v_y + LABEL_BELOW_OFFSET
    if below_y > chart_data_bottom_y() - MIN_LABEL_CLEARANCE_FROM_BOTTOM:
        return v_y - LABEL_ABOVE_OFFSET, True
    return below_y, False


def target_label_layout(
    values: list[float | None],
    value_labels: list[str],
    annual_target: float | None,
    annual_target_label: str | None,
    chart_width: int,
) -> dict[str, bool]:
    """Return placement hints to reduce overlap between target and value labels."""
    if annual_target is None:
        return {"tag_below": False, "value_above": False, "value_below": False}

    numeric = [v for v in values if v is not None]
    n = len(values)
    _, y_max = y_scale(numeric[0] if numeric else 0, values, annual_target)
    ty_px, _ = y_scale(annual_target, values, annual_target)

    tag_below = False
    tag_top = ty_px - 12
    tag_bottom = ty_px
    for i, val in enumerate(values):
        if not value_labels[i] or val is None:
            continue
        if x_percent(i, n, chart_width) > 30:
            continue
        ly, _ = _value_label_y_px(i, val, values, annual_target, y_max)
        if not (tag_bottom < ly - 10 or tag_top > ly):
            tag_below = True
            break

    value_above = False
    value_below = False
    for i, val in enumerate(values):
        if not value_labels[i] or val is None:
            continue
        if x_percent(i, n, chart_width) < 65:
            continue
        ly, above = _value_label_y_px(i, val, values, annual_target, y_max)
        if abs(val - annual_target) < y_max * 0.08:
            value_above = not above
            value_below = above
            break
        if abs(ly - ty_px) < 12:
            value_above = True
            break

    if (
        annual_target_label
        and n
        and value_labels[-1]
        and values[-1] is not None
        and abs(values[-1] - annual_target) < y_max * 0.02
        and value_labels[-1] == annual_target_label
    ):
        value_above = True

    return {"tag_below": tag_below, "value_above": value_above, "value_below": value_below}


def _line_segments(coords: list[tuple[float, float] | None]) -> list[list[tuple[float, float]]]:
    segments: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for point in coords:
        if point is None:
            if len(current) > 1:
                segments.append(current)
            current = []
            continue
        current.append(point)
    if len(current) > 1:
        segments.append(current)
    return segments


def render_line_chart_svg(
    item: dict,
    width: int,
    *,
    chart_id: str = "line",
    show_target_line: bool = True,
    show_value_labels: bool = False,
    show_target_labels: bool = False,
    target_label: str | None = None,
    language: str = "English",
) -> str:
    """Render line geometry as SVG (labels optional for PNG assets)."""
    values = item["values"]
    height = CHART_HEIGHT
    pad_l = CHART_PAD_L
    pad_r = CHART_PAD_R
    pad_t = CHART_PAD_TOP
    pad_b = CHART_PAD_BOTTOM
    plot_w = width - pad_l - pad_r

    numeric = [v for v in values if v is not None]
    annual_target = item.get("annual_target")
    y_candidates = list(numeric)
    if annual_target is not None:
        y_candidates.append(annual_target)
    y_max = max(y_candidates) * 1.18 if y_candidates else 1

    count = len(values)
    x_step = plot_w / (count - 1) if count > 1 else 0

    def x_at(index: int) -> float:
        return pad_l + index * x_step

    def y_at(value: float) -> float:
        return pad_t + (height - pad_t - pad_b) * (1 - value / y_max)

    coords: list[tuple[float, float] | None] = [
        (x_at(i), y_at(v)) if v is not None else None for i, v in enumerate(values)
    ]
    segments = _line_segments(coords)
    uid = re.sub(r"[^a-zA-Z0-9_-]", "", chart_id or "line")

    parts = [
        f'<svg class="line-chart-svg" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMinYMid meet" xmlns="http://www.w3.org/2000/svg">',
    ]

    style = resolve_style()
    fx = style["line_chart_effects"]
    marker_ring = fx.get("marker_ring", False)
    stroke_width = style["line_stroke_width"]
    marker_r = style.get("marker_radius", 3.5)
    is_modern = style.get("name") == "modern"
    label_layout = target_label_layout(
        values,
        item["value_labels"],
        annual_target,
        item.get("annual_target_label"),
        width,
    )

    if fx.get("area_fill") or fx.get("line_shadow"):
        parts.append("<defs>")
        if is_rtl(language):
            parts.append(_svg_embedded_style(tajawal_face_css(inline=True)))
        if fx.get("area_fill"):
            top_op = "0.16" if is_modern else "0.10"
            mid_op = "0.05" if is_modern else "0.04"
            parts.append(
                f'<linearGradient id="{uid}-area" gradientUnits="userSpaceOnUse" '
                f'x1="0" y1="{pad_t}" x2="0" y2="{pad_t + (height - pad_t - pad_b)}">'
                f'<stop offset="0%" stop-color="{COLOR_VALUE}" stop-opacity="{top_op}"/>'
                f'<stop offset="50%" stop-color="{COLOR_VALUE}" stop-opacity="{mid_op}"/>'
                f'<stop offset="100%" stop-color="{COLOR_VALUE}" stop-opacity="0"/>'
                f"</linearGradient>"
            )
        if fx.get("line_shadow"):
            dy = "1.5" if is_modern else "1"
            blur = "1.6" if is_modern else "1.2"
            opacity = "0.18" if is_modern else "0.14"
            parts.append(
                f'<filter id="{uid}-shadow" x="-4%" y="-4%" width="108%" height="112%">'
                f'<feDropShadow dx="0" dy="{dy}" stdDeviation="{blur}" '
                f'flood-color="{COLOR_VALUE}" flood-opacity="{opacity}"/>'
                f"</filter>"
            )
        parts.append("</defs>")
    elif is_rtl(language):
        parts.append(_svg_style_defs(language))

    if annual_target is not None and show_target_line:
        ty = y_at(annual_target)
        target_stroke = 'stroke-width="1.5" stroke-dasharray="4 3"' if is_modern else 'stroke-width="2"'
        parts.append(
            f'<line x1="{pad_l}" y1="{ty:.2f}" x2="{pad_l + plot_w:.2f}" y2="{ty:.2f}" '
            f'stroke="{COLOR_TARGET}" {target_stroke}/>'
        )
        if show_target_labels and target_label:
            tag_y = ty + 4 if label_layout["tag_below"] else ty - 5
            tag_baseline = "hanging" if label_layout["tag_below"] else "auto"
            parts.append(
                _svg_chart_text(
                    target_label,
                    x=pad_l + 4,
                    y=tag_y,
                    language=language,
                    fill=COLOR_TARGET,
                    font_size=9,
                    text_anchor="start",
                    dominant_baseline=tag_baseline,
                )
            )
        if show_target_labels and item.get("annual_target_label"):
            value_y = ty
            value_baseline = "middle"
            if label_layout["value_above"]:
                value_y = ty - 5
                value_baseline = "auto"
            elif label_layout["value_below"]:
                value_y = ty + 4
                value_baseline = "hanging"
            parts.append(
                _svg_chart_text(
                    str(item["annual_target_label"]),
                    x=pad_l + plot_w + 6,
                    y=value_y,
                    language=language,
                    fill=COLOR_TARGET,
                    font_size=10,
                    text_anchor="start",
                    dominant_baseline=value_baseline,
                )
            )

    if fx.get("area_fill"):
        bottom_y = pad_t + (height - pad_t - pad_b)
        for segment in segments:
            first = segment[0]
            last = segment[-1]
            mid = " ".join(f"L {x:.2f},{y:.2f}" for x, y in segment[1:])
            parts.append(
                f'<path d="M {first[0]:.2f},{first[1]:.2f} {mid} '
                f'L {last[0]:.2f},{bottom_y:.2f} L {first[0]:.2f},{bottom_y:.2f} Z" '
                f'fill="url(#{uid}-area)"/>'
            )

    shadow_attr = f' filter="url(#{uid}-shadow)"' if fx.get("line_shadow") else ""
    for segment in segments:
        points = " ".join(f"{x:.2f},{y:.2f}" for x, y in segment)
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="{COLOR_VALUE}" stroke-width="{stroke_width}" '
            f'stroke-linejoin="round" stroke-linecap="round"{shadow_attr}/>'
        )

    for i, value in enumerate(values):
        if value is None:
            continue
        cx = x_at(i)
        cy = y_at(value)
        if marker_ring:
            ring_r = marker_r + 1.5
            parts.append(
                f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{ring_r}" fill="#ffffff" '
                f'stroke="{COLOR_VALUE}" stroke-width="1.5"/>'
            )
            parts.append(
                f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{max(marker_r - 1.0, 1.5)}" fill="{COLOR_VALUE}"/>'
            )
        else:
            parts.append(
                f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{marker_r}" fill="{COLOR_VALUE}"/>'
            )

        if show_value_labels:
            label = item["value_labels"][i]
            if label:
                ly, _ = _value_label_y_px(i, value, values, annual_target, y_max)
                parts.append(
                    _svg_chart_text(
                        str(label),
                        x=cx,
                        y=ly,
                        language=language,
                        fill=COLOR_VALUE,
                        font_size=10,
                    )
                )

    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# HTML injection helpers
# ---------------------------------------------------------------------------

def line_chart_effects_payload() -> dict[str, bool]:
    return dict(style_payload()["line_chart_effects"])


def inject_line_chart_js(html: str) -> str:
    if _LINE_CHART_JS_PLACEHOLDER not in html:
        raise ValueError(f"Template missing placeholder {_LINE_CHART_JS_PLACEHOLDER}")
    js = LINE_CHART_JS_PATH.read_text(encoding="utf-8")
    return html.replace(_LINE_CHART_JS_PLACEHOLDER, js)
