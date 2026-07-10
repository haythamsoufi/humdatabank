"""Tests for dynamic footnote totals from TotalReported."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.calculations import footnote_for_key  # noqa: E402
from pb_figures.data import reporting_source_totals  # noqa: E402


class TestReportingSourceTotals(unittest.TestCase):
    def test_reads_upr_and_fdrs_counts_for_year(self) -> None:
        totals = reporting_source_totals(
            Path(__file__).resolve().parents[1] / "SG Report.xlsx",
            year="2025",
        )
        self.assertEqual(totals["year"], "2025")
        self.assertEqual(totals["upr_ns"], 143)
        self.assertEqual(totals["fdrs_ns"], 84)

    def test_footnote_substitutes_placeholders(self) -> None:
        os.environ["PB_REPORT_EXCEL"] = str(
            Path(__file__).resolve().parents[1] / "SG Report.xlsx"
        )
        os.environ["PB_REPORT_YEAR"] = "2025"
        try:
            text = footnote_for_key("default", "English")
        finally:
            os.environ.pop("PB_REPORT_EXCEL", None)
            os.environ.pop("PB_REPORT_YEAR", None)

        self.assertIn("143", text)
        self.assertIn("84", text)
        self.assertIn("2025", text)
        self.assertNotIn("113", text)
        self.assertNotIn("{upr_ns}", text)


if __name__ == "__main__":
    unittest.main()
