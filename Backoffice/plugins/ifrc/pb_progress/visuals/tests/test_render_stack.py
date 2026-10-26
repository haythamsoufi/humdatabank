"""Tests for pure-Python P&B render stack helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.line_chart import render_line_chart_svg  # noqa: E402
from pb_figures.donut_chart import render_donut_svg  # noqa: E402
from pb_figures.render_pdf import prepare_html_for_pdf  # noqa: E402
from pb_figures.svg_raster import write_svg_png  # noqa: E402


class TestDonutSvg(unittest.TestCase):
    def test_render_donut_svg_includes_target_arc(self) -> None:
        svg = render_donut_svg({"value": 50, "target": 100, "value_label": "50"})
        self.assertIn("stroke-dasharray", svg)
        self.assertIn("50", svg)

    def test_unavailable_donut_renders_message(self) -> None:
        svg = render_donut_svg(
            {"unavailable": True, "unavailable_label": "N/A"},
            show_label=True,
        )
        self.assertIn("N/A", svg)


class TestPrepareHtmlForPdf(unittest.TestCase):
    def test_prepare_html_includes_pdf_dashboard_layout_css(self) -> None:
        html = "<html><head></head><body><div class=\"pb-lang-panel\" data-lang=\"English\"></div></body></html>"
        prepared = prepare_html_for_pdf(html, "English")
        self.assertIn("pb-pdf-export", prepared)
        self.assertIn("aspect-ratio: 481 / 110", prepared)
        self.assertIn("div.year-data-grid", prepared)

    def test_prepare_html_shows_one_language_panel(self) -> None:
        html = """
        <html><head></head><body>
          <div class="pb-lang-panel" data-lang="English" data-dir="ltr"></div>
          <div class="pb-lang-panel" data-lang="French" data-dir="ltr"></div>
        </body></html>
        """
        prepared = prepare_html_for_pdf(html, "French")
        self.assertIn('data-lang="French"', prepared)
        self.assertNotIn('data-lang="French" hidden', prepared)
        self.assertIn('data-lang="French"', prepared)
        self.assertIn('hidden=""', prepared)


class TestWriteSvgPng(unittest.TestCase):
    def test_write_svg_png_rasterizes_donut(self) -> None:
        svg = render_donut_svg({"value": 25, "target": 50, "value_label": "25"})
        output = ROOT / "tests" / "fixtures" / "donut-raster.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            write_svg_png(svg, output, width=64, height=64)
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 100)
        finally:
            output.unlink(missing_ok=True)

    def test_write_svg_png_rasterizes_line_chart(self) -> None:
        item = {
            "values": [10.0, 20.0, None, 30.0, 40.0],
            "value_labels": ["10", "20", "", "30", "40"],
            "annual_target": 35.0,
            "annual_target_label": "35",
        }
        svg = render_line_chart_svg(
            item,
            481,
            chart_id="asset-line",
            show_value_labels=True,
            show_target_labels=True,
            target_label="Target",
        )
        self.assertNotIn('font-family=""Open Sans"', svg)
        output = ROOT / "tests" / "fixtures" / "line-raster.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            write_svg_png(svg, output, width=481, height=110)
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 100)
        finally:
            output.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
