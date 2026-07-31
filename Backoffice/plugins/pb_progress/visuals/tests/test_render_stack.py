"""Tests for pure-Python P&B render stack helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.donut_chart import render_donut_svg  # noqa: E402
from pb_figures.render_pdf import prepare_html_for_pdf  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
