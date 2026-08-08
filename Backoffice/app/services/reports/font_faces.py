"""Shared font faces for report builder and pb_progress exports."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from plugins.pb_progress.visuals.scripts.pb_figures.font_faces import (
    inject_chart_fonts,
    open_sans_face_css,
    tajawal_face_css,
)

FONTS_DIR = Path(__file__).resolve().parents[2] / "static" / "fonts"

__all__ = ["FONTS_DIR", "inject_chart_fonts", "open_sans_face_css", "tajawal_face_css"]
