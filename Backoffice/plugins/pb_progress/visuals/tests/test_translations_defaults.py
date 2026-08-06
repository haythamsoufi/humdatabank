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
from pb_figures.translations import _bundle_cache_key, _load_bundle, clear_cache, load_section_order  # noqa: E402


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

            translations, section_order, parts_order = _load_bundle(_bundle_cache_key(path.resolve()))

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
        from pb_figures.translations import _parse_section_order_rows

        rows = [
            {"part": "sp", "section": "SP1", "order": 1},
            {"part": "sp", "section": "SP2", "order": 2},
            {"part": "ef", "section": "EF2", "order": 1},
            {"part": "ef", "section": "EF3", "order": 2},
        ]
        section_order, parts_order = _parse_section_order_rows(rows)
        self.assertEqual(parts_order, ("sp", "ef"))
        self.assertEqual(section_order["sp"], ["SP1", "SP2"])
        self.assertEqual(section_order["ef"], ["EF2", "EF3"])

    def test_load_bundle_uses_env_section_order(self) -> None:
        import os
        import json

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "SG Report.xlsx"
            _write_minimal_workbook(path)
            rows = [{"part": "sp", "section": "SP2", "order": 1}]
            os.environ["PB_REPORT_SECTION_ORDER"] = json.dumps(rows)
            try:
                clear_cache()
                _, section_order, _ = _load_bundle(_bundle_cache_key(path.resolve()))
                self.assertEqual(section_order, {"sp": ["SP2"]})
            finally:
                os.environ.pop("PB_REPORT_SECTION_ORDER", None)
                clear_cache()

    def test_load_bundle_uses_env_section_titles(self) -> None:
        import json
        import os

        from pb_figures.translations import section_title_for

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "SG Report.xlsx"
            _write_minimal_workbook(path)
            rows = [{"part": "sp", "section": "SP1", "order": 1}]
            titles = {"section.SP1": {"English": "Bank SP1", "French": "Banque SP1"}}
            os.environ["PB_REPORT_SECTION_ORDER"] = json.dumps(rows)
            os.environ["PB_REPORT_SECTION_TITLES"] = json.dumps(titles)
            try:
                clear_cache()
                self.assertEqual(section_title_for("SP1", "English", path), "Bank SP1")
                self.assertEqual(section_title_for("SP1", "French", path), "Banque SP1")
            finally:
                os.environ.pop("PB_REPORT_SECTION_ORDER", None)
                os.environ.pop("PB_REPORT_SECTION_TITLES", None)
                clear_cache()


if __name__ == "__main__":
    unittest.main()
