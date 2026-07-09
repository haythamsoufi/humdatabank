"""Tests for indicator visibility rules in layouts.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gb_figures.layouts import (  # noqa: E402
    EF_ID_ORDERS,
    NS_COUNT_INDICATOR_IDS,
    SP_LAYOUTS,
    TEMPORARILY_HIDDEN,
    show_ns_breakdown,
    visible_donut_rows,
    visible_indicator_ids,
)


class TableauIndicatorOrderTests(unittest.TestCase):
    """Manual ID sorts from Archive/tableau/GB figures.twb."""

    def test_ef2_order_matches_tableau(self) -> None:
        self.assertEqual(EF_ID_ORDERS["EF2"], ["642", "644", "643", "645"])

    def test_ef4_order_matches_tableau(self) -> None:
        self.assertEqual(
            EF_ID_ORDERS["EF4"],
            ["637", "636", "650", "648", "649", "706"],
        )

    def test_sp2_cumulative_order_matches_tableau(self) -> None:
        self.assertEqual(
            SP_LAYOUTS["SP2"]["cumulative_ids"],
            ["619", "618", "622", "DREF"],
        )


class LayoutVisibilityTests(unittest.TestCase):
    def test_sp2_hides_katya01(self) -> None:
        ids = ["618", "Katya01", "622"]
        self.assertEqual(visible_indicator_ids("SP2", ids), ["618", "622"])
        self.assertIn("Katya01", TEMPORARILY_HIDDEN["SP2"])

    def test_other_sections_unaffected(self) -> None:
        ids = ["Katya01", "618"]
        self.assertEqual(visible_indicator_ids("SP1", ids), ids)

    def test_visible_donut_rows_filters_by_id(self) -> None:
        rows = [{"id": "618"}, {"id": "Katya01"}, {"id": "622"}]
        self.assertEqual(
            len(visible_donut_rows("SP2", rows)),
            2,
        )

    def test_sp4_donuts_are_side_by_side_pair(self) -> None:
        layout = SP_LAYOUTS["SP4"]
        self.assertEqual(
            layout["donut_pair"],
            ["KPI_ReachM_IntegratedPlan", "630"],
        )

    def test_ns_count_indicators_hide_breakdown_rows(self) -> None:
        self.assertEqual(
            NS_COUNT_INDICATOR_IDS,
            frozenset({"615", "616", "638", "DREF"}),
        )
        self.assertFalse(show_ns_breakdown("615"))
        self.assertFalse(show_ns_breakdown("616"))
        self.assertFalse(show_ns_breakdown("638"))
        self.assertFalse(show_ns_breakdown("DREF"))
        self.assertTrue(show_ns_breakdown("612"))
        self.assertTrue(show_ns_breakdown("633"))


if __name__ == "__main__":
    unittest.main()
