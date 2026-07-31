"""Tests for translation/section-order fallbacks when Excel metadata sheets are missing."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.defaults import DEFAULT_PARTS_ORDER, DEFAULT_SECTION_ORDER  # noqa: E402
from pb_figures.report_meta import report_parts  # noqa: E402
from pb_figures.translations import _load_bundle, clear_cache, load_section_order  # noqa: E402


def _write_minimal_workbook(path: Path) -> None:
    mapping = pd.DataFrame(
        {
            "Strategic Priority / Enabling Function": ["SP1"],
            "ID": ["1"],
            "English": ["Indicator one"],
            "SP EN": ["Priority 1"],
            "Type": ["Cumulative"],
            "Unit": ["People"],
        }
    )
    final = pd.DataFrame(
        {
            "Index": [1],
            "Strategic Priority / Enabling Function": ["SP1"],
            "ID": ["1"],
            "Source": ["Manual"],
            "Year": ["2027"],
            "Value": [100],
            "Implementing": [10],
            "Count": [5],
        }
    )
    total_reported = pd.DataFrame({"Source": ["Manual"], "Year": ["2027"], "TotalReported": [10]})
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        empty = pd.DataFrame()
        empty.to_excel(writer, sheet_name="Mapping", index=False, startrow=3)
        mapping.to_excel(writer, sheet_name="Mapping", index=False, startrow=3)
        final.to_excel(writer, sheet_name="Final", index=False)
        total_reported.to_excel(writer, sheet_name="TotalReported", index=False)


class TranslationDefaultsTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_cache()

    def tearDown(self) -> None:
        clear_cache()

    def test_load_bundle_uses_defaults_when_metadata_sheets_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "SG Report.xlsx"
            _write_minimal_workbook(path)

            translations, section_order, parts_order = _load_bundle(str(path.resolve()))

            self.assertIn("report.title", translations)
            self.assertEqual(section_order, DEFAULT_SECTION_ORDER)
            self.assertEqual(parts_order, DEFAULT_PARTS_ORDER)

    def test_report_parts_work_without_metadata_sheets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "SG Report.xlsx"
            _write_minimal_workbook(path)

            with mock.patch("pb_figures.report_meta.resolve_excel", return_value=path):
                parts = report_parts()

            self.assertEqual([part["id"] for part in parts], list(DEFAULT_PARTS_ORDER))

    def test_load_section_order_falls_back_without_sheet(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "SG Report.xlsx"
            _write_minimal_workbook(path)

            order = load_section_order(path)
            self.assertEqual(order, DEFAULT_SECTION_ORDER)

    def test_parts_order_prefers_sp_before_ef_when_legacy_per_part_orders(self) -> None:
        from pb_figures.translations import _parse_section_order_sheet

        order_df = pd.DataFrame(
            [
                {"part": "sp", "section": "SP1", "order": 1},
                {"part": "sp", "section": "SP2", "order": 2},
                {"part": "ef", "section": "EF2", "order": 1},
                {"part": "ef", "section": "EF3", "order": 2},
            ]
        )
        section_order, parts_order = _parse_section_order_sheet(order_df)
        self.assertEqual(parts_order, ("sp", "ef"))
        self.assertEqual(section_order["sp"], ["SP1", "SP2"])
        self.assertEqual(section_order["ef"], ["EF2", "EF3"])


if __name__ == "__main__":
    unittest.main()
