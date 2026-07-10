"""Tests for dynamic indicator layout rules in layouts.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.layouts import (  # noqa: E402
    TEMPORARILY_HIDDEN,
    build_section_layout,
    mapping_indicator_rows,
    show_ns_breakdown,
    visible_donut_rows,
    visible_indicator_ids,
)


def _sample_mapping() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Strategic Priority / Enabling Function": [
                "SP1", "SP1", "SP1", "SP4", "SP4", "SP4",
            ],
            "ID": ["612", "615", "616", "629", "630", "631"],
            "Type": [
                "Cumulative", "Distinct", "Distinct",
                "Cumulative", "Distinct", "Distinct",
            ],
            "Unit": [None, "NSs", "NSs", None, None, None],
        }
    )


class DynamicLayoutTests(unittest.TestCase):
    def test_mapping_indicator_rows_preserve_excel_order(self) -> None:
        rows = mapping_indicator_rows(_sample_mapping(), "SP1")
        self.assertEqual(rows["ID"].tolist(), ["612", "615", "616"])

    def test_sp_layout_splits_line_and_donut_indicators(self) -> None:
        layout = build_section_layout("SP1", _sample_mapping())
        self.assertEqual(layout["cumulative_ids"], ["612", "615", "616"])
        self.assertEqual(layout["donut_pairs"], [])

        sp4 = build_section_layout("SP4", _sample_mapping())
        self.assertEqual(sp4["cumulative_ids"], ["629", "630", "631"])
        self.assertEqual(sp4["donut_pairs"], [])

    def test_sp_layout_chunks_three_donuts_into_two_rows(self) -> None:
        mapping = pd.DataFrame(
            {
                "Strategic Priority / Enabling Function": ["SP4"] * 4,
                "ID": ["629", "630", "631", "632"],
                "Type": ["Cumulative", "Distinct", "Distinct", "Distinct"],
                "Unit": [None, None, None, None],
            }
        )
        layout = build_section_layout("SP4", mapping)
        self.assertEqual(layout["cumulative_ids"], ["629", "630", "631", "632"])
        self.assertEqual(layout["donut_pairs"], [])

    def test_distinct_ns_indicators_hide_breakdown_rows(self) -> None:
        self.assertFalse(show_ns_breakdown("Distinct", "NSs"))
        self.assertTrue(show_ns_breakdown("Cumulative", None))
        self.assertTrue(show_ns_breakdown("Distinct", "Platforms"))


class LayoutVisibilityTests(unittest.TestCase):
    def test_visible_indicator_ids_respects_hidden_set(self) -> None:
        original = TEMPORARILY_HIDDEN.copy()
        try:
            TEMPORARILY_HIDDEN["SP2"] = frozenset({"Katya01"})
            ids = ["618", "Katya01", "622"]
            self.assertEqual(visible_indicator_ids("SP2", ids), ["618", "622"])
        finally:
            TEMPORARILY_HIDDEN.clear()
            TEMPORARILY_HIDDEN.update(original)

    def test_visible_donut_rows_filters_by_id(self) -> None:
        rows = [{"id": "618"}, {"id": "Katya01"}, {"id": "622"}]
        self.assertEqual(len(visible_donut_rows("SP2", rows)), 3)


if __name__ == "__main__":
    unittest.main()
