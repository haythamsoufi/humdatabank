"""Tests for dynamic indicator layout rules in layouts.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.layouts import (  # noqa: E402
    NS_TABLE_IMPLEMENTING_COUNT,
    NS_TABLE_NS_UNIT,
    TEMPORARILY_HIDDEN,
    build_section_layout,
    cumulative_table_rows,
    is_ns_unit,
    mapping_indicator_rows,
    normalize_section_code,
    ns_table_mode,
    section_has_indicators,
    show_ns_breakdown,
    visible_donut_rows,
    visible_indicator_ids,
)
from pb_figures.payload import build_sp_payload  # noqa: E402


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
    def test_normalize_section_code_maps_cross_cutting_to_cc1(self) -> None:
        self.assertEqual(normalize_section_code("Cross-cutting"), "CC1")
        self.assertEqual(normalize_section_code("CC1"), "CC1")
        self.assertEqual(normalize_section_code("SP1"), "SP1")

    def test_mapping_indicator_rows_accepts_cross_cutting_label(self) -> None:
        mapping = pd.DataFrame(
            {
                "Strategic Priority / Enabling Function": ["Cross-cutting", "SP1"],
                "ID": ["101", "618"],
                "Type": ["Cumulative", "Cumulative"],
            }
        )
        rows = mapping_indicator_rows(mapping, "CC1")
        self.assertEqual(rows["ID"].tolist(), ["101"])
        self.assertTrue(section_has_indicators(mapping, "CC1"))

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

    def test_distinct_ns_indicators_use_implementing_count_table(self) -> None:
        self.assertEqual(ns_table_mode("Distinct", "NS"), NS_TABLE_IMPLEMENTING_COUNT)
        self.assertTrue(show_ns_breakdown("Distinct", "NSs"))
        self.assertTrue(show_ns_breakdown("Cumulative", None))
        self.assertEqual(ns_table_mode("Distinct", "Platforms"), "standard")

    def test_cumulative_ns_indicators_hide_implementing_row(self) -> None:
        self.assertTrue(is_ns_unit("NSs"))
        self.assertTrue(is_ns_unit("NS"))
        self.assertEqual(ns_table_mode("Cumulative", "NS"), NS_TABLE_NS_UNIT)
        item = {"show_ns_breakdown": True, "ns_table_mode": NS_TABLE_NS_UNIT}
        self.assertEqual(cumulative_table_rows(item), (True, False))

    def test_distinct_ns_payload_uses_total_reported_in_reporting_row(self) -> None:
        mapping = pd.DataFrame(
            {
                "Strategic Priority / Enabling Function": ["SP1"],
                "ID": ["615"],
                "Type": ["Distinct"],
                "Unit": ["NSs"],
                "English": ["Number of National Societies implementing nature-based solutions"],
                "SP EN": ["Climate and environment"],
                "_mapping_order": [0],
            }
        )
        model = pd.DataFrame(
            {
                "section": ["SP1"] * 3,
                "ID": ["615"] * 3,
                "Year": ["2023", "2024", "2025"],
                "Value": [40.0, 45.0, 50.0],
                "Count": [40, 45, 50],
                "Implementing": [98, 102, 108],
                "TotalReported": [100, 105, 110],
                "Type": ["Distinct"] * 3,
                "Unit": ["NSs"] * 3,
                "English": ["Number of National Societies implementing nature-based solutions"] * 3,
                "SP EN": ["Climate and environment"] * 3,
                "_mapping_order": [0] * 3,
            }
        )
        payload = build_sp_payload(model, "SP1", mapping=mapping)
        item = payload["cumulative"][0]
        self.assertEqual(item.get("ns_table_mode"), NS_TABLE_IMPLEMENTING_COUNT)
        # Value already is the "implementing" count (40/45/50); the one visible row
        # shows the total NSs participating in this reporting round instead.
        self.assertEqual(item["reporting"], ["100", "105", "110"])
        self.assertEqual(item["implementing"], ["98", "102", "108"])
        self.assertNotEqual(item["reporting"], ["40", "45", "50"])


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
