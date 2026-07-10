"""Tests for value formatting in calculations.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.calculations import format_value, is_percentage_unit, table_row_labels  # noqa: E402


class FormatValueTests(unittest.TestCase):
    def test_whole_millions_drop_trailing_decimal(self) -> None:
        self.assertEqual(format_value(46_000_000, None), "46M")
        self.assertEqual(format_value(45_999_999.999, None), "46M")

    def test_fractional_millions_keep_one_decimal(self) -> None:
        self.assertEqual(format_value(12_300_000, None), "12.3M")
        self.assertEqual(format_value(6_200_000, None), "6.2M")

    def test_percentage_fraction(self) -> None:
        self.assertEqual(format_value(0.23, "Percentage"), "23%")
        self.assertTrue(is_percentage_unit("Percentage"))

    def test_percentage_whole_number(self) -> None:
        self.assertEqual(format_value(23, "Percentage"), "23%")
        self.assertEqual(format_value(25, "percent"), "25%")


class TableLabelTests(unittest.TestCase):
    def test_reporting_and_implementing_include_national_societies_prefix(self) -> None:
        labels = table_row_labels("English")
        self.assertTrue(labels["reporting"].startswith("National Societies "))
        self.assertTrue(labels["implementing"].startswith("National Societies "))
        self.assertIn("Reporting", labels["reporting"])
        self.assertIn("Implementing", labels["implementing"])


if __name__ == "__main__":
    unittest.main()
