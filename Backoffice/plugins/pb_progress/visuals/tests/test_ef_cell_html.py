"""Tests for EF dashboard line-chart rendering."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.render_embed import _append_section_tail, _render_sp_html  # noqa: E402
from pb_figures.calculations import table_row_labels  # noqa: E402


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
            "section": "SP4",
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
            "donut_pairs": [[{
                "label": "Donut A",
                "value": 44,
                "value_label": "44",
                "target": None,
                "target_label": "",
            }]],
            "donuts": [],
            "footnote": "Footnote text",
        }
        refs = {"pair_0_0_donut": "pair_0_0_donut.png"}
        html = _render_sp_html(payload, refs)
        self.assertIn('<div class="indicator-row">', html)
        self.assertIn('<div class="section-tail"><div class="donut-pair">', html)
        self.assertIn("Footnote text", html)
        self.assertLess(html.index('<div class="indicator-row">'), html.index('<div class="section-tail">'))

    def test_year_only_footer_omits_ns_breakdown_rows(self) -> None:
        payload = {
            "section": "SP1",
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

    def test_ef_section_renders_line_charts(self) -> None:
        payload = {
            "section": "EF1",
            "title": "EF 1",
            "headers": {"target": "Target"},
            "table_labels": {"year": "Year", "reporting": "Reporting", "implementing": "Implementing"},
            "cumulative": [
                {
                    "label": "Indicator A",
                    "years": ["2023", "2024"],
                    "values": [14.0, 14.0],
                    "value_labels": ["14", "14"],
                    "reporting": ["107", "106"],
                    "implementing": ["14", "14"],
                    "show_ns_breakdown": True,
                },
                {
                    "label": "Indicator B",
                    "years": ["2023"],
                    "values": [50.0],
                    "value_labels": ["50"],
                    "reporting": ["107"],
                    "implementing": ["50"],
                    "show_ns_breakdown": True,
                },
            ],
            "donuts": [],
            "footnote": "EF footnote",
        }
        html = _render_sp_html(payload, {})
        self.assertNotIn("ef-table", html)
        self.assertEqual(html.count('<div class="indicator-row">'), 2)
        self.assertEqual(html.count('<svg class="line-chart-svg"'), 2)
        self.assertIn("50", html)
        self.assertNotIn("50/ 107", html)
        self.assertIn("Reporting", html)
        self.assertIn("Implementing", html)
        self.assertNotIn('class="x-axis-footer year-only"', html)

    def test_distinct_ns_table_shows_reporting_row_only(self) -> None:
        labels = table_row_labels("English")
        payload = {
            "section": "SP1",
            "title": "SP1",
            "headers": {"target": "Target"},
            "table_labels": labels,
            "cumulative": [{
                "label": "Number of National Societies implementing nature-based solutions",
                "years": ["2024", "2025"],
                "values": [40.0, 45.0],
                "value_labels": ["40", "45"],
                "reporting": ["40", "45"],
                "implementing": ["40", "45"],
                "ns_table_mode": "implementing_count",
                "show_ns_breakdown": True,
            }],
            "donuts": [],
            "footnote": "Footnote text",
        }
        html = _render_sp_html(payload, {})
        self.assertIn(labels["reporting"], html)
        self.assertNotIn(labels["implementing"], html)
        self.assertIn(">40<", html)
        self.assertIn(">45<", html)


if __name__ == "__main__":
    unittest.main()
