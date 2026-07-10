"""Visual style presets for P&B figure dashboards."""

from __future__ import annotations

import os
from typing import Any, TypedDict


class LineChartEffects(TypedDict):
    area_fill: bool
    line_shadow: bool
    marker_ring: bool


class StyleColors(TypedDict):
    value: str
    target: str
    gap: str
    text: str
    muted: str
    divider: str
    bg: str


class StylePreset(TypedDict):
    name: str
    colors: StyleColors
    line_chart_effects: LineChartEffects
    line_stroke_width: float
    marker_radius: float


# IFRC brand colours (fixed across all themes)
_BRAND_VALUE = "#c22526"
_BRAND_TARGET = "#f28e2b"
_BRAND_GAP = "#c1c1c1"

STYLE_NAMES = ("classic", "modern", "professional")
DEFAULT_STYLE = "classic"
ENV_VAR = "PB_FIGURES_STYLE"

_STYLES: dict[str, StylePreset] = {
    "classic": {
        "name": "classic",
        "colors": {
            "value": _BRAND_VALUE,
            "target": _BRAND_TARGET,
            "gap": _BRAND_GAP,
            "text": "#1a1a1a",
            "muted": "#666666",
            "divider": "#d8d8d8",
            "bg": "#ffffff",
        },
        "line_chart_effects": {
            "area_fill": False,
            "line_shadow": False,
            "marker_ring": False,
        },
        "line_stroke_width": 2.5,
        "marker_radius": 3.5,
    },
    "modern": {
        "name": "modern",
        "colors": {
            "value": _BRAND_VALUE,
            "target": _BRAND_TARGET,
            "gap": _BRAND_GAP,
            "text": "#111111",
            "muted": "#737373",
            "divider": "#eeeeee",
            "bg": "#ffffff",
        },
        "line_chart_effects": {
            "area_fill": True,
            "line_shadow": True,
            "marker_ring": False,
        },
        "line_stroke_width": 2.75,
        "marker_radius": 2.25,
    },
    "professional": {
        "name": "professional",
        "colors": {
            "value": _BRAND_VALUE,
            "target": _BRAND_TARGET,
            "gap": _BRAND_GAP,
            "text": "#1a1a1a",
            "muted": "#4a4a4a",
            "divider": "#e8e8e8",
            "bg": "#ffffff",
        },
        "line_chart_effects": {
            "area_fill": True,
            "line_shadow": False,
            "marker_ring": False,
        },
        "line_stroke_width": 2.0,
        "marker_radius": 3.0,
    },
}


def resolve_style(name: str | None = None) -> StylePreset:
    """Return the active style preset.

    Resolution order: explicit ``name`` argument, then ``PB_FIGURES_STYLE`` env var,
    then ``DEFAULT_STYLE`` (classic).
    """
    chosen = (name or os.environ.get(ENV_VAR) or DEFAULT_STYLE).strip().lower()
    if chosen not in _STYLES:
        valid = ", ".join(STYLE_NAMES)
        raise ValueError(f"Unknown figure style {chosen!r}; choose one of: {valid}")
    return dict(_STYLES[chosen])


def style_payload(name: str | None = None) -> dict[str, Any]:
    """JSON-serialisable style fields for dashboard payloads."""
    preset = resolve_style(name)
    return {
        "style": preset["name"],
        "colors": dict(preset["colors"]),
        "line_chart_effects": dict(preset["line_chart_effects"]),
        "line_stroke_width": preset["line_stroke_width"],
        "marker_radius": preset["marker_radius"],
    }
