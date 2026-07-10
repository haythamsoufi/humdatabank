"""Tests for indicators without Final data."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.calculations import not_available  # noqa: E402
from pb_figures.layouts import build_section_layout, indicator_has_values  # noqa: E402
from pb_figures.payload import build_sp_payload  # noqa: E402
from pb_figures.render_embed import build_dashboard_html  # noqa: E402
from pb_figures.render_html import _dashboard_height  # noqa: E402


def _mapping_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Strategic Priority / Enabling Function": ["SP2", "SP2", "SP2"],
            "ID": ["618", "1128", "1130"],
            "Type": ["Cumulative", "Cumulative", "Cumulative"],
            "Unit": [None, "Percentage", "Percentage"],
            "English": [
                "Existing indicator",
                "Percentage of assistance delivered using cash and vouchers",
                "New indicator without data",
            ],
            "SP EN": ["Response", "Response", "Response"],
            "_mapping_order": [0, 1, 2],
        }
    )


def _model_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "section": ["SP2", "SP2"],
            "ID": ["618", "618"],
            "Year": ["2024", "2025"],
            "Value": [12_000_000.0, 15_000_000.0],
            "Count": [100, 120],
            "Implementing": [90, 110],
            "Type": ["Cumulative", "Cumulative"],
            "Unit": [None, None],
            "English": ["Existing indicator", "Existing indicator"],
            "SP EN": ["Response", "Response"],
            "_mapping_order": [0, 0],
        }
    )


class UnavailableIndicatorTests(unittest.TestCase):
    def test_layout_keeps_mapping_only_indicators(self) -> None:
        mapping = _mapping_frame()
        layout = build_section_layout("SP2", mapping)
        self.assertEqual(layout["cumulative_ids"], ["618", "1128", "1130"])

    def test_indicator_has_values_detects_missing_final_rows(self) -> None:
        model = _model_frame()
        self.assertTrue(indicator_has_values(model, "SP2", "618"))
        self.assertFalse(indicator_has_values(model, "SP2", "1128"))
        self.assertFalse(indicator_has_values(model, "SP2", "1130"))

    def test_indicator_has_values_detects_placeholder_rows_without_chart_values(self) -> None:
        model = pd.DataFrame(
            {
                "section": ["SP2"] * 5,
                "ID": ["1128"] * 5,
                "Year": ["2021", "2022", "2023", "2024", "2025"],
                "Value": [None, None, None, None, None],
                "Count": [None, None, 107, 106, 143],
                "Implementing": [None, None, None, None, None],
            }
        )
        self.assertFalse(indicator_has_values(model, "SP2", "1128"))

    def test_payload_marks_placeholder_rows_unavailable(self) -> None:
        mapping = _mapping_frame()
        model = _model_frame()
        placeholder_rows = pd.DataFrame(
            {
                "section": ["SP2"] * 5,
                "ID": ["1128"] * 5,
                "Year": ["2021", "2022", "2023", "2024", "2025"],
                "Value": [None, None, None, None, 0],
                "Count": [None, None, 107, 106, 143],
                "Implementing": [None, None, None, None, None],
                "Type": ["Cumulative"] * 5,
                "Unit": ["Percentage"] * 5,
                "English": ["Percentage of assistance delivered using cash and vouchers"] * 5,
                "SP EN": ["Response"] * 5,
                "_mapping_order": [1] * 5,
            }
        )
        combined = pd.concat([model, placeholder_rows], ignore_index=True)
        payload = build_sp_payload(combined, "SP2", mapping=mapping)
        item = next(item for item in payload["cumulative"] if item["label"].startswith("Percentage"))
        self.assertTrue(item.get("unavailable"))
        self.assertEqual(item.get("years"), [])

    def test_payload_marks_unavailable_indicators(self) -> None:
        payload = build_sp_payload(_model_frame(), "SP2", mapping=_mapping_frame())
        self.assertEqual(len(payload["cumulative"]), 3)
        unavailable = [item for item in payload["cumulative"] if item.get("unavailable")]
        self.assertEqual(len(unavailable), 2)
        self.assertEqual(unavailable[0]["unavailable_label"], not_available("English"))
        self.assertIn("cash and vouchers", unavailable[0]["label"])

    def test_embed_html_renders_not_available_message(self) -> None:
        payload = build_sp_payload(_model_frame(), "SP2", mapping=_mapping_frame())
        html = build_dashboard_html(payload, {})
        self.assertEqual(html.count(not_available("English")), 2)
        self.assertIn('class="indicator-row indicator-unavailable"', html)
        self.assertNotIn("x-axis-footer", html.split("cash and vouchers")[1].split(not_available("English"))[0])

    def test_png_dashboard_template_matches_embed_for_unavailable(self) -> None:
        payload = build_sp_payload(_model_frame(), "SP2", mapping=_mapping_frame())
        template = (ROOT / "scripts" / "pb_figures" / "templates" / "dashboard.html").read_text(encoding="utf-8")
        unavailable = [item for item in payload["cumulative"] if item.get("unavailable")]
        self.assertEqual(len(unavailable), 2)
        self.assertIn("if (item.unavailable)", template)
        self.assertIn('class="indicator-row indicator-unavailable"', template)
        self.assertIn(".indicator-unavailable-message", template)
        height = _dashboard_height(payload)
        self.assertEqual(height, 130 + 155 + 96 + 96)

    def test_sp4_distinct_indicators_render_as_line_charts(self) -> None:
        mapping = pd.DataFrame(
            {
                "Strategic Priority / Enabling Function": ["SP4"] * 4,
                "ID": ["629", "630", "631", "632"],
                "Type": ["Cumulative", "Distinct", "Distinct", "Distinct"],
                "Unit": [None, None, None, None],
                "English": ["Line", "Donut A", "Donut B", "Donut C"],
                "SP EN": ["Migration"] * 4,
                "_mapping_order": [0, 1, 2, 3],
            }
        )
        model = pd.DataFrame(
            {
                "section": ["SP4"] * 12,
                "ID": ["629"] * 3 + ["630"] * 3 + ["631"] * 3 + ["632"] * 3,
                "Year": ["2023", "2024", "2025"] * 4,
                "Value": [1_000_000.0, 1_100_000.0, 1_200_000.0, 44.0, 50.0, 55.0, 194.0, 200.0, 210.0, 51.0, 60.0, 65.0],
                "Count": [100] * 12,
                "Implementing": [90] * 12,
                "Type": ["Cumulative", "Distinct", "Distinct", "Distinct"] * 3,
                "Unit": [None, None, None, None] * 3,
                "English": ["Line", "Donut A", "Donut B", "Donut C"] * 3,
                "SP EN": ["Migration"] * 12,
                "_mapping_order": [0, 1, 2, 3] * 3,
            }
        )
        payload = build_sp_payload(model, "SP4", mapping=mapping)
        self.assertEqual(len(payload["cumulative"]), 4)
        self.assertEqual(payload["donut_pairs"], [])
        html = build_dashboard_html(payload, {})
        self.assertEqual(html.count('<div class="indicator-row">'), 4)
        self.assertEqual(html.count('<svg class="line-chart-svg"'), 4)
        self.assertNotIn("donut-pair", html)
        self.assertNotIn("donut-img", html)
        mapping = pd.DataFrame(
            {
                "Strategic Priority / Enabling Function": ["SP5"],
                "ID": ["999"],
                "Type": ["Distinct"],
                "Unit": ["Percentage"],
                "English": ["National Society has a functioning community feedback mechanism"],
                "SP EN": ["Accountability"],
                "_mapping_order": [0],
            }
        )
        model = pd.DataFrame(
            {
                "section": ["SP5"] * 3,
                "ID": ["999"] * 3,
                "Year": ["2023", "2024", "2025"],
                "Value": [None, None, None],
                "Count": [100, 105, 110],
                "Type": ["Distinct"] * 3,
                "Unit": ["Percentage"] * 3,
                "English": ["National Society has a functioning community feedback mechanism"] * 3,
                "SP EN": ["Accountability"] * 3,
                "_mapping_order": [0] * 3,
            }
        )
        payload = build_sp_payload(model, "SP5", mapping=mapping)
        self.assertEqual(len(payload["donut_pairs"]), 1)
        self.assertEqual(len(payload["donut_pairs"][0]), 1)
        self.assertTrue(payload["donut_pairs"][0][0].get("unavailable"))
        html = build_dashboard_html(payload, {})
        self.assertIn('class="donut-pair-item indicator-unavailable"', html)
        self.assertIn(not_available("English"), html)
        self.assertNotIn("donut-img", html)
        self.assertNotIn("donut-visual", html)


if __name__ == "__main__":
    unittest.main()
