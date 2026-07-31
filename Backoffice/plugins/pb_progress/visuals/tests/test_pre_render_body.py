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


if __name__ == "__main__":
    unittest.main()
