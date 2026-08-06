"""Tests for localized HTML report header metadata."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.report_meta import format_report_date, report_header_meta  # noqa: E402


class ReportHeaderMetaTests(unittest.TestCase):
    @patch("pb_figures.report_meta.report_titles")
    @patch("pb_figures.report_meta.report_author")
    @patch("pb_figures.report_meta.report_author_label")
    @patch("pb_figures.report_meta.report_published_label")
    def test_report_header_meta_builds_all_languages(
        self,
        mock_published_label,
        mock_author_label,
        mock_author,
        mock_titles,
    ) -> None:
        mock_titles.return_value = {
            "English": "Plan & Budget Report — Figures",
            "French": "Rapport du Conseil de direction — Figures",
        }
        mock_author.side_effect = lambda lang, _path=None: "IFRC — FDS Team"
        mock_author_label.side_effect = lambda lang, _path=None: {
            "English": "Author",
            "French": "Auteur",
        }.get(lang, "Author")
        mock_published_label.side_effect = lambda lang, _path=None: {
            "English": "Published",
            "French": "Publié",
        }.get(lang, "Published")

        meta = report_header_meta(
            ("English", "French", "Arabic"),
            published_on=date(2026, 8, 6),
        )

        self.assertEqual(meta["French"]["title"], "Rapport du Conseil de direction — Figures")
        self.assertEqual(meta["French"]["authorLabel"], "Auteur")
        self.assertEqual(meta["French"]["publishedLabel"], "Publié")
        self.assertEqual(meta["French"]["date"], "6 août 2026")
        self.assertEqual(meta["French"]["contentsLabel"], "Sommaire")
        self.assertEqual(meta["Arabic"]["contentsLabel"], "المحتويات")
        self.assertIn("tocExpandLabel", meta["English"])
        self.assertIn("tocCollapseLabel", meta["English"])

    def test_format_report_date_spanish(self) -> None:
        self.assertEqual(
            format_report_date("Spanish", date(2026, 8, 6)),
            "6 de agosto de 2026",
        )


if __name__ == "__main__":
    unittest.main()
