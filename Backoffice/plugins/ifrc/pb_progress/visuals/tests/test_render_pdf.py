"""Tests for combined PDF export helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.languages import pdf_filename  # noqa: E402
from pb_figures.render_pdf import html_file_uri  # noqa: E402


class PdfFilenameTests(unittest.TestCase):
    def test_pdf_filename_uses_language_slug(self) -> None:
        self.assertEqual(pdf_filename("English"), "pb-report-english.pdf")
        self.assertEqual(pdf_filename("Arabic"), "pb-report-arabic.pdf")


class HtmlFileUriTests(unittest.TestCase):
    def test_html_file_uri_uses_file_scheme(self) -> None:
        uri = html_file_uri(Path("report/output/pb-report.html"))
        self.assertTrue(uri.startswith("file:///"))
        self.assertIn("pb-report.html", uri)


if __name__ == "__main__":
    unittest.main()
