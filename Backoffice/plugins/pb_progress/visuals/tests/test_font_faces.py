"""Tests for bundled Tajawal font injection."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.font_faces import inject_tajawal_fonts, tajawal_face_css  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
