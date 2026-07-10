"""Bundled Tajawal font faces for offline Arabic typography."""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

FONTS_DIR = Path(__file__).resolve().parents[2] / "report" / "fonts"
_FONT_FILES = {
    400: FONTS_DIR / "Tajawal-Regular.ttf",
    700: FONTS_DIR / "Tajawal-Bold.ttf",
}
_PLACEHOLDER = "__TAJAWAL_FONT_CSS__"


@lru_cache(maxsize=1)
def tajawal_face_css(*, inline: bool = True) -> str:
    """Return @font-face rules for Tajawal (400 and 700).

    When inline=True (default), embeds TTF data for Playwright set_content().
    When inline=False, uses relative file URLs for on-disk HTML templates.
    """
    blocks: list[str] = []
    for weight, path in _FONT_FILES.items():
        if inline:
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            src = f"url(data:font/ttf;base64,{encoded}) format('truetype')"
        else:
            src = f"url('{path.as_posix()}') format('truetype')"
        blocks.append(
            "@font-face {\n"
            '  font-family: "Tajawal";\n'
            "  font-style: normal;\n"
            f"  font-weight: {weight};\n"
            "  font-display: swap;\n"
            f"  src: {src};\n"
            "}"
        )
    return "\n".join(blocks)


def inject_tajawal_fonts(html: str) -> str:
    """Replace the Tajawal placeholder in HTML templates."""
    if _PLACEHOLDER not in html:
        return html
    return html.replace(_PLACEHOLDER, tajawal_face_css(inline=True))
