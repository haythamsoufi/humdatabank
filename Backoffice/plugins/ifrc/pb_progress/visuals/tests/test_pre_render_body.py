"""Tests for _body.qmd generation edge cases."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pre_render import _render_language_panel  # noqa: E402


class PreRenderBodyTests(unittest.TestCase):
    @patch("pre_render.report_parts")
    @patch("pre_render.section_titles")
    def test_skips_sections_without_mapping_indicators(
        self,
        mock_section_titles,
        mock_report_parts,
    ) -> None:
        mock_report_parts.return_value = [
            {
                "id": "cc",
                "title": {"English": "Cross-cutting"},
                "sections": ["CC1"],
            }
        ]
        mock_section_titles.return_value = {"CC1": "Cross-cutting"}
        mapping = pd.DataFrame(
            {
                "Strategic Priority / Enabling Function": ["SP1"],
                "ID": ["618"],
                "Type": ["Cumulative"],
                "English": ["Example"],
            }
        )
        model = pd.DataFrame({"section": ["SP1"], "ID": ["618"], "Value": [1.0]})

        html_lines = _render_language_panel(
            "English",
            model,
            Path("SG Report.xlsx"),
            mapping,
            visible=True,
        )
        body = "\n".join(html_lines)

        self.assertIn("Cross-cutting", body)
        self.assertNotIn("report-figure", body)
        self.assertNotIn("pb-dashboard", body)

    @patch("pre_render.build_section_embed")
    @patch("pre_render.report_parts")
    @patch("pre_render.section_titles")
    def test_cross_cutting_omits_section_subheading(
        self,
        mock_section_titles,
        mock_report_parts,
        mock_build_section_embed,
    ) -> None:
        mock_report_parts.return_value = [
            {
                "id": "cc",
                "title": {"English": "Cross-cutting"},
                "sections": ["CC1"],
            }
        ]
        mock_section_titles.return_value = {"CC1": "Cross-cutting indicators"}
        mock_build_section_embed.return_value = '<div class="pb-dashboard">charts</div>'
        mapping = pd.DataFrame(
            {
                "Strategic Priority / Enabling Function": ["CC1"],
                "ID": ["618"],
                "Type": ["Cumulative"],
                "English": ["Example"],
            }
        )
        model = pd.DataFrame({"section": ["CC1"], "ID": ["618"], "Value": [1.0]})

        html_lines = _render_language_panel(
            "English",
            model,
            Path("SG Report.xlsx"),
            mapping,
            visible=True,
        )
        body = "\n".join(html_lines)

        self.assertIn('class="report-part-title"', body)
        self.assertIn("Cross-cutting", body)
        self.assertNotIn("report-section-title", body)
        self.assertNotIn("section-cc1", body)
        self.assertIn("pb-dashboard", body)


class PreRenderHeaderTests(unittest.TestCase):
    @patch("pre_render.build_section_embed")
    @patch("pre_render.report_parts")
    @patch("pre_render.section_titles")
    @patch("pre_render.report_header_meta")
    def test_generate_body_includes_header_i18n_payload(
        self,
        mock_report_header_meta,
        mock_section_titles,
        mock_report_parts,
        _mock_build_section_embed,
    ) -> None:
        from pre_render import _generate_body

        mock_report_header_meta.return_value = {
            "English": {
                "title": "English title",
                "author": "IFRC",
                "authorLabel": "Author",
                "publishedLabel": "Published",
                "date": "6 August 2026",
            },
        }
        mock_report_parts.return_value = []
        mock_section_titles.return_value = {}
        mapping = pd.DataFrame(
            {
                "Strategic Priority / Enabling Function": ["SP1"],
                "ID": ["618"],
                "Type": ["Cumulative"],
                "English": ["Example"],
            }
        )
        model = pd.DataFrame({"section": ["SP1"], "ID": ["618"], "Value": [1.0]})
        output = Path("_body_test.qmd")

        try:
            _generate_body(output, model, ("English",), Path("SG Report.xlsx"), mapping)
            body = output.read_text(encoding="utf-8")
        finally:
            output.unlink(missing_ok=True)

        self.assertIn('id="pb-report-header-i18n"', body)
        self.assertIn("English title", body)


if __name__ == "__main__":
    unittest.main()
