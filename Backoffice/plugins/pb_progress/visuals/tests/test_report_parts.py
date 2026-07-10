"""Tests for dynamic report part ordering."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.report_meta import report_parts  # noqa: E402


class ReportPartsTests(unittest.TestCase):
    @patch("pb_figures.report_meta.load_section_order")
    @patch("pb_figures.report_meta.load_parts_order")
    @patch("pb_figures.report_meta.resolve_excel")
    @patch("pb_figures.report_meta.part_title")
    def test_report_parts_follow_section_order_sheet(
        self,
        mock_part_title,
        _mock_resolve_excel,
        mock_parts_order,
        mock_section_order,
    ) -> None:
        mock_parts_order.return_value = ("cc", "sp", "ef")
        mock_section_order.return_value = {
            "cc": ["CC1", "CC2"],
            "sp": ["SP1"],
            "ef": ["EF1"],
        }
        mock_part_title.side_effect = lambda part_id, lang, _path: f"{part_id}-{lang}"

        parts = report_parts()

        self.assertEqual([part["id"] for part in parts], ["cc", "sp", "ef"])
        self.assertEqual(parts[0]["sections"], ["CC1", "CC2"])
        self.assertEqual(parts[0]["title"]["English"], "cc-English")

    @patch("pb_figures.report_meta.load_section_order")
    @patch("pb_figures.report_meta.load_parts_order")
    @patch("pb_figures.report_meta.resolve_excel")
    @patch("pb_figures.report_meta.part_title")
    def test_empty_parts_are_skipped(
        self,
        _mock_part_title,
        _mock_resolve_excel,
        mock_parts_order,
        mock_section_order,
    ) -> None:
        mock_parts_order.return_value = ("cc", "sp")
        mock_section_order.return_value = {"sp": ["SP1"]}

        parts = report_parts()

        self.assertEqual([part["id"] for part in parts], ["sp"])


if __name__ == "__main__":
    unittest.main()
