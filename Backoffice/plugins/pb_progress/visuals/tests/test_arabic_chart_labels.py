"""Tests for Arabic chart label HTML overlays."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.calculations import format_value  # noqa: E402
from pb_figures.render_embed import _chart_label_html, _render_line_block  # noqa: E402


@pytest.mark.unit
def test_chart_label_html_splits_arabic_millions_with_bdi() -> None:
    label = format_value(219_300_000, None, "Arabic")
    html = _chart_label_html(label, language="Arabic")

    assert "مليون" in html
    assert "219.3" in html
    assert "<bdi" in html
    assert 'dir="rtl"' in html


@pytest.mark.unit
def test_render_line_block_arabic_png_includes_html_value_labels() -> None:
    item = {
        "label": "Indicator",
        "values": [164_500_000.0, 219_300_000.0, 184_800_000.0],
        "value_labels": [
            format_value(164_500_000, None, "Arabic"),
            format_value(219_300_000, None, "Arabic"),
            format_value(184_800_000, None, "Arabic"),
        ],
        "years": ["2021", "2022", "2023"],
        "reporting": ["1", "2", "3"],
        "implementing": ["1", "2", "3"],
        "show_ns_breakdown": True,
    }
    html = _render_line_block(
        item,
        chart_index=0,
        target_label="Target",
        table_labels={"year": "Year", "reporting": "R", "implementing": "I"},
        chart_width=481,
        asset_refs={"line_0": "line_0.png"},
        language="Arabic",
    )

    assert "line-chart-img" in html
    assert "chart-value-label" in html
    assert "<bdi" in html
    assert "مليون" in html
