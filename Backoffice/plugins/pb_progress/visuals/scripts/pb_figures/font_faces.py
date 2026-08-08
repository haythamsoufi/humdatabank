"""Bundled Tajawal and Open Sans font faces for offline chart typography."""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

FONTS_DIR = Path(__file__).resolve().parents[5] / "app" / "static" / "fonts"
_LEGACY_FONTS_DIR = Path(__file__).resolve().parents[2] / "report" / "fonts"
if not FONTS_DIR.exists():
    FONTS_DIR = _LEGACY_FONTS_DIR
_FONT_SPECS: dict[str, dict[int, Path]] = {
    "Tajawal": {
        400: FONTS_DIR / "Tajawal-Regular.ttf",
        700: FONTS_DIR / "Tajawal-Bold.ttf",
    },
    "Open Sans": {
        400: FONTS_DIR / "OpenSans-Regular.ttf",
        700: FONTS_DIR / "OpenSans-Bold.ttf",
    },
}
_TAJAWAL_PLACEHOLDER = "__TAJAWAL_FONT_CSS__"
_OPEN_SANS_PLACEHOLDER = "__OPEN_SANS_FONT_CSS__"


def _face_css(family: str, *, inline: bool = True) -> str:
    blocks: list[str] = []
    for weight, path in _FONT_SPECS[family].items():
        if inline:
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            src = f"url(data:font/ttf;base64,{encoded}) format('truetype')"
        else:
            src = f"url('{path.as_posix()}') format('truetype')"
        blocks.append(
            "@font-face {\n"
            f'  font-family: "{family}";\n'
            "  font-style: normal;\n"
            f"  font-weight: {weight};\n"
            "  font-display: swap;\n"
            f"  src: {src};\n"
            "}"
        )
    return "\n".join(blocks)


@lru_cache(maxsize=2)
def tajawal_face_css(*, inline: bool = True) -> str:
    """Return @font-face rules for Tajawal (400 and 700)."""
    return _face_css("Tajawal", inline=inline)


@lru_cache(maxsize=2)
def open_sans_face_css(*, inline: bool = True) -> str:
    """Return @font-face rules for Open Sans (400 and 700)."""
    return _face_css("Open Sans", inline=inline)


def inject_tajawal_fonts(html: str) -> str:
    """Replace the Tajawal placeholder in HTML templates."""
    if _TAJAWAL_PLACEHOLDER not in html:
        return html
    return html.replace(_TAJAWAL_PLACEHOLDER, tajawal_face_css(inline=True))


def inject_open_sans_fonts(html: str) -> str:
    """Replace the Open Sans placeholder in HTML templates."""
    if _OPEN_SANS_PLACEHOLDER not in html:
        return html
    return html.replace(_OPEN_SANS_PLACEHOLDER, open_sans_face_css(inline=True))


def inject_chart_fonts(html: str) -> str:
    """Inject bundled Tajawal and Open Sans faces for chart rasterization."""
    return inject_open_sans_fonts(inject_tajawal_fonts(html))
