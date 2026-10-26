"""Tests for figure style theme resolution."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.config import resolve_excel  # noqa: E402
from pb_figures.data import build_model  # noqa: E402
from pb_figures.payload import build_payload  # noqa: E402
from pb_figures.styles import (  # noqa: E402
    DEFAULT_STYLE,
    ENV_VAR,
    resolve_style,
    style_payload,
)


class StyleResolutionTests(unittest.TestCase):
    def test_resolve_style_defaults_to_classic(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop(ENV_VAR, None)
            style = resolve_style()
        self.assertEqual(style["name"], DEFAULT_STYLE)
        self.assertFalse(style["line_chart_effects"]["area_fill"])

    def test_resolve_style_explicit_name(self) -> None:
        style = resolve_style("modern")
        self.assertEqual(style["name"], "modern")
        self.assertTrue(style["line_chart_effects"]["area_fill"])
        self.assertFalse(style["line_chart_effects"]["marker_ring"])
        self.assertEqual(style["marker_radius"], 2.25)
        self.assertEqual(style["line_stroke_width"], 2.75)

    def test_resolve_style_env_override(self) -> None:
        with patch.dict(os.environ, {ENV_VAR: "professional"}):
            style = resolve_style()
        self.assertEqual(style["name"], "professional")
        self.assertFalse(style["line_chart_effects"]["marker_ring"])
        self.assertTrue(style["line_chart_effects"]["area_fill"])
        self.assertEqual(style["line_stroke_width"], 2.0)
        self.assertEqual(style["marker_radius"], 3.0)

    def test_resolve_style_invalid_name_raises(self) -> None:
        with self.assertRaises(ValueError):
            resolve_style("retro")

    def test_style_payload_includes_theme_fields(self) -> None:
        with patch.dict(os.environ, {ENV_VAR: "modern"}):
            payload = style_payload()
        self.assertEqual(payload["style"], "modern")
        self.assertIn("colors", payload)
        self.assertIn("line_chart_effects", payload)
        self.assertIn("line_stroke_width", payload)
        self.assertIn("marker_radius", payload)
        self.assertEqual(payload["colors"]["value"], "#c22526")
        self.assertEqual(payload["colors"]["target"], "#f28e2b")
        self.assertEqual(payload["marker_radius"], 2.25)


class PayloadStyleIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        excel = ROOT / "SG Report.xlsx"
        cls.excel_available = excel.exists()
        cls.excel_path = excel

    def test_sp_payload_includes_modern_style(self) -> None:
        if not self.excel_available:
            self.skipTest("SG Report.xlsx not present in workspace")
        with patch.dict(os.environ, {ENV_VAR: "modern"}):
            model = build_model(resolve_excel(self.excel_path))
            payload = build_payload(model, "SP1", "English")
        self.assertEqual(payload["style"], "modern")
        self.assertTrue(payload["line_chart_effects"]["area_fill"])
        self.assertTrue(payload["line_chart_effects"]["line_shadow"])

    def test_ef_payload_includes_professional_style(self) -> None:
        if not self.excel_available:
            self.skipTest("SG Report.xlsx not present in workspace")
        with patch.dict(os.environ, {ENV_VAR: "professional"}):
            model = build_model(resolve_excel(self.excel_path))
            payload = build_payload(model, "EF1", "English")
        self.assertEqual(payload["style"], "professional")
        self.assertFalse(payload["line_chart_effects"]["marker_ring"])
        self.assertEqual(payload["line_stroke_width"], 2.0)
        self.assertEqual(payload["marker_radius"], 3.0)


if __name__ == "__main__":
    unittest.main()
