"""Tests for value formatting in calculations.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gb_figures.calculations import format_value  # noqa: E402


class FormatValueTests(unittest.TestCase):
    def test_whole_millions_drop_trailing_decimal(self) -> None:
        self.assertEqual(format_value(46_000_000, None), "46M")
        self.assertEqual(format_value(45_999_999.999, None), "46M")

    def test_fractional_millions_keep_one_decimal(self) -> None:
        self.assertEqual(format_value(12_300_000, None), "12.3M")
        self.assertEqual(format_value(6_200_000, None), "6.2M")


if __name__ == "__main__":
    unittest.main()
