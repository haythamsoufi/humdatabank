"""Tests for localized missing-value labels."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.calculations import not_applicable, not_available  # noqa: E402
from pb_figures.translations import _translation_cell, clear_cache  # noqa: E402


class TranslationCellTests(unittest.TestCase):
    def test_na_string_is_preserved(self) -> None:
        self.assertEqual(_translation_cell("n/a"), "n/a")

    def test_nan_value_is_ignored(self) -> None:
        self.assertIsNone(_translation_cell(float("nan")))


class MissingValueLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        clear_cache()

    def test_not_available_english(self) -> None:
        self.assertEqual(not_available("English"), "Not available yet")

    def test_not_available_arabic(self) -> None:
        self.assertEqual(not_available("Arabic"), "غير متوفر بعد")

    def test_not_applicable_english(self) -> None:
        self.assertEqual(not_applicable("English"), "n/a")

    def test_not_applicable_french(self) -> None:
        self.assertNotEqual(not_applicable("French").lower(), "nan")


if __name__ == "__main__":
    unittest.main()
