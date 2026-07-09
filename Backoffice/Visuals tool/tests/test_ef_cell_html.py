"""Tests for EF table value cell formatting."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gb_figures.render_embed import _append_section_tail, _format_ef_cell_html, _render_sp_html  # noqa: E402


class EfCellHtmlTests(unittest.TestCase):
    def test_value_cell_splits_main_and_suffix(self) -> None:
        html = _format_ef_cell_html({
            "text": "85%/ 113",
            "value": True,
            "main": "85%",
            "suffix": "/ 113",
        })
        self.assertIn('class="value-main">85%', html)
        self.assertIn('class="value-suffix">/ 113', html)

    def test_non_value_cell_is_plain_text(self) -> None:
        html = _format_ef_cell_html({"text": "N/A", "value": False})
        self.assertEqual(html, "N/A")
        self.assertNotIn("value-main", html)


class SectionTailTests(unittest.TestCase):
    def test_wraps_only_last_block_with_footnote(self) -> None:
        parts = [
            '<div class="dash-title">SP1</div>',
            '<div class="indicator-row">chart 1</div>',
            '<div class="indicator-row">chart 2</div>',
        ]
        _append_section_tail(parts, "Footnote text")
        html = "".join(parts)
        self.assertEqual(html.count('<div class="indicator-row">'), 2)
        self.assertIn('<div class="section-tail">', html)
        self.assertIn('<div class="indicator-row">chart 2</div>', html)
        self.assertIn('<div class="indicator-row">chart 1</div>', html)
        self.assertIn("Footnote text", html)

    def test_sp_footnote_wraps_only_last_block(self) -> None:
        payload = {
            "title": "SP4",
            "headers": {"target": "Target"},
            "table_labels": {"year": "Year", "reporting": "Reporting", "implementing": "Implementing"},
            "cumulative": [{
                "label": "Chart",
                "years": ["2024"],
                "values": [1.0],
                "value_labels": ["1"],
                "reporting": ["1"],
                "implementing": ["1"],
                "show_ns_breakdown": True,
            }],
            "donut_pair": [{
                "label": "Donut A",
                "value": 44,
                "value_label": "44",
                "target": None,
                "target_label": "",
            }],
            "donuts": [],
            "footnote": "Footnote text",
        }
        refs = {"pair_0_donut": "pair_0_donut.png"}
        html = _render_sp_html(payload, refs)
        self.assertIn('<div class="indicator-row">', html)
        self.assertIn('<div class="section-tail"><div class="donut-pair">', html)
        self.assertIn("Footnote text", html)
        self.assertLess(html.index('<div class="indicator-row">'), html.index('<div class="section-tail">'))

    def test_year_only_footer_omits_ns_breakdown_rows(self) -> None:
        payload = {
            "title": "SP1",
            "headers": {"target": "Target"},
            "table_labels": {"year": "Year", "reporting": "Reporting", "implementing": "Implementing"},
            "cumulative": [{
                "label": "NS count",
                "years": ["2024"],
                "values": [67.0],
                "value_labels": ["67"],
                "reporting": ["1"],
                "implementing": ["1"],
                "show_ns_breakdown": False,
            }],
            "donuts": [],
            "footnote": "Footnote text",
        }
        refs = {}
        html = _render_sp_html(payload, refs)
        self.assertIn('class="x-axis-footer year-only"', html)
        self.assertIn('<svg class="line-chart-svg"', html)
        self.assertNotIn("Reporting", html)
        self.assertNotIn("Implementing", html)


if __name__ == "__main__":
    unittest.main()
