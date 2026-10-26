"""Tests for bundled Tajawal font injection."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.font_faces import inject_chart_fonts, inject_open_sans_fonts, inject_tajawal_fonts, open_sans_face_css, tajawal_face_css  # noqa: E402


class FontFaceTests(unittest.TestCase):
    def test_css_includes_both_weights(self) -> None:
        css = tajawal_face_css()
        self.assertIn("font-weight: 400", css)
        self.assertIn("font-weight: 700", css)
        self.assertIn("data:font/ttf;base64,", css)

    def test_inject_replaces_placeholder(self) -> None:
        html = "<style>__TAJAWAL_FONT_CSS__</style>"
        result = inject_tajawal_fonts(html)
        self.assertNotIn("__TAJAWAL_FONT_CSS__", result)
        self.assertIn("@font-face", result)

    def test_open_sans_css_includes_both_weights(self) -> None:
        css = open_sans_face_css()
        self.assertIn("font-weight: 400", css)
        self.assertIn("font-weight: 700", css)
        self.assertIn('"Open Sans"', css)

    def test_inject_chart_fonts_replaces_both_placeholders(self) -> None:
        html = "<style>__TAJAWAL_FONT_CSS__\n__OPEN_SANS_FONT_CSS__</style>"
        result = inject_chart_fonts(html)
        self.assertNotIn("__TAJAWAL_FONT_CSS__", result)
        self.assertNotIn("__OPEN_SANS_FONT_CSS__", result)
        self.assertIn('"Tajawal"', result)
        self.assertIn('"Open Sans"', result)


if __name__ == "__main__":
    unittest.main()
