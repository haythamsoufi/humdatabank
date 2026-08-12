"""Tests for value formatting in calculations.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.calculations import (  # noqa: E402
    format_donut_value,
    format_value,
    is_percentage_unit,
    table_row_labels,
)


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

    def test_arabic_millions_use_rtl_word_order(self) -> None:
        self.assertEqual(format_value(219_300_000, None, "Arabic"), "219.3 مليونا")
        self.assertEqual(format_value(2_000_000, None, "Arabic"), "2 مليونان")

    def test_arabic_million_suffix_by_range(self) -> None:
        cases = [
            (1_000_000, "1 مليون"),
            (2_000_000, "2 مليونان"),
            (3_000_000, "3 ملايين"),
            (5_000_000, "5 ملايين"),
            (10_000_000, "10 ملايين"),
            (11_000_000, "11 مليونا"),
            (25_000_000, "25 مليونا"),
            (99_000_000, "99 مليونا"),
            (100_000_000, "100 مليون"),
            (184_000_000, "184 مليون"),
            (219_000_000, "219 مليون"),
            (1_500_000, "1.5 مليون"),
            (2_500_000, "2.5 مليونان"),
            (10_050_000, "10.1 ملايين"),
            (99_900_000, "99.9 مليونا"),
            (100_500_000, "100.5 مليونا"),
            (219_300_000, "219.3 مليونا"),
            (184_400_000, "184.4 مليونا"),
            (10_800_000, "10.8 ملايين"),
            (73_700_000, "73.7 مليونا"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(format_value(value, None, "Arabic"), expected)

    def test_arabic_donut_million_suffix_by_range(self) -> None:
        cases = [
            (1_000_000, "1\nمليون"),
            (2_000_000, "2\nمليونان"),
            (5_000_000, "5\nملايين"),
            (25_000_000, "25\nمليونا"),
            (100_000_000, "100\nمليون"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(format_donut_value(value, None, "Arabic"), expected)


class TableLabelTests(unittest.TestCase):
    def test_reporting_and_implementing_include_national_societies_prefix(self) -> None:
        labels = table_row_labels("English")
        self.assertTrue(labels["reporting"].startswith("National Societies "))
        self.assertTrue(labels["implementing"].startswith("National Societies "))
        self.assertIn("Reporting", labels["reporting"])
        self.assertIn("Implementing", labels["implementing"])


if __name__ == "__main__":
    unittest.main()
