"""Single source of truth for UPR visuals fonts (screen + WeasyPrint + IDML names).

Rules:
- Latin copy is Open Sans; Arabic-script copy is Tajawal (``.upr-arabic-font``).
- KPI / amount digits stay Montserrat, with Tajawal as the Arabic fallback.
- Hebrew is RTL but stays on the Latin stack — do not key fonts off ``dir=rtl``.
- Set ``font-family`` on roots and inherit. Do not blast ``p, h3, td``.
- WeasyPrint running footers lose ``html.upr-arabic-font`` ancestry; the footer
  carries ``.upr-arabic-font`` itself, and ``@page`` margin boxes get the stack.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Callable

_PLUGIN_DIR = Path(__file__).resolve().parent
_APP_STATIC_DIR = _PLUGIN_DIR.parents[1] / "app" / "static"
_APP_FONTS_DIR = _APP_STATIC_DIR / "fonts"
_PLUGIN_FONTS_DIR = _PLUGIN_DIR / "fonts"
_PB_FONTS_DIR = _PLUGIN_DIR.parents[0] / "pb_progress" / "visuals" / "report" / "fonts"
_CSS_PATH = _PLUGIN_DIR / "static" / "css" / "upr-visuals.css"

LATIN_FAMILY = "Open Sans"
ARABIC_FAMILY = "Tajawal"
NUMBER_FAMILY = "Montserrat"

LATIN_BODY_STACK = f'"{LATIN_FAMILY}", "Segoe UI", sans-serif'
ARABIC_BODY_STACK = f'"{ARABIC_FAMILY}", "Arial", "Segoe UI", sans-serif'
LATIN_NUMBER_STACK = f'"{NUMBER_FAMILY}", "{LATIN_FAMILY}", sans-serif'
ARABIC_NUMBER_STACK = f'"{NUMBER_FAMILY}", "{ARABIC_FAMILY}", sans-serif'

# Numeric / KPI faces. Country titles are *not* here — Arabic names inherit Tajawal.
NUMBER_SELECTORS = (
    ".upr-kpi__value",
    ".upr-fin-kpi__value",
    ".upr-reach-value",
    ".upr-reach-headline",
    ".upr-bar-value",
    ".upr-bar-yes.upr-num",
    ".upr-num",
    ".upr-support-total",
    ".upr-plan-fund__source-value",
    ".upr-plan-fund__projected-value",
    ".upr-detail-fund__amt",
    ".upr-support-fill--on",
    ".upr-doc-footer__appeal strong",
)

_FONT_CUTS: tuple[tuple[str, str, int], ...] = (
    (LATIN_FAMILY, "OpenSans-Regular.ttf", 400),
    (LATIN_FAMILY, "OpenSans-Bold.ttf", 700),
    (ARABIC_FAMILY, "Tajawal-Regular.ttf", 400),
    (ARABIC_FAMILY, "Tajawal-Bold.ttf", 700),
    (NUMBER_FAMILY, "Montserrat-Regular.ttf", 400),
    (NUMBER_FAMILY, "Montserrat-Bold.ttf", 700),
)

# File hashes + these modules: any print/font/HTML change busts export reuse.
_STYLE_SOURCE_FILES = (
    _CSS_PATH,
    _PLUGIN_DIR / "typography.py",
    _PLUGIN_DIR / "raster.py",
    _PLUGIN_DIR / "i18n.py",
    _PLUGIN_DIR / "render.py",
    _PLUGIN_DIR / "idml" / "narrative_pdf.py",
)


def _first_font(*paths: Path) -> Path | None:
    for path in paths:
        if path.is_file():
            return path
    return None


def resolve_font_file(filename: str) -> Path | None:
    return _first_font(
        _PLUGIN_FONTS_DIR / filename,
        _APP_FONTS_DIR / filename,
        _PB_FONTS_DIR / filename,
    )


def iter_resolved_fonts() -> list[tuple[str, Path, int]]:
    found: list[tuple[str, Path, int]] = []
    for family, filename, weight in _FONT_CUTS:
        path = resolve_font_file(filename)
        if path is not None:
            found.append((family, path, weight))
    return found


def _font_face(family: str, src: str, weight: int, *, style: str = "normal") -> str:
    return (
        f"@font-face {{ font-family: '{family}'; "
        f"src: url('{src}') format('truetype'); "
        f"font-weight: {weight}; font-style: {style}; font-display: swap; }}"
    )


def _faces_for_cut(family: str, src: str, weight: int) -> list[str]:
    """Normal + italic. Missing italic TTFs reuse roman so engines do not fall to Times."""
    return [
        _font_face(family, src, weight),
        _font_face(family, src, weight, style="italic"),
    ]


def font_face_css(src_for: Callable[[Path], str | None]) -> str:
    faces: list[str] = []
    for family, path, weight in iter_resolved_fonts():
        src = src_for(path)
        if src:
            faces.extend(_faces_for_cut(family, src, weight))
    return "\n".join(faces)


def file_font_src(path: Path) -> str:
    """file:// URI for WeasyPrint (it often fails on huge data:font URIs)."""
    return path.resolve().as_uri()


@lru_cache(maxsize=1)
def export_font_face_css() -> str:
    return font_face_css(file_font_src)


def _http_font_src(path: Path) -> str | None:
    """Browser URL when the TTF is under a web-served root; skip plugin/fonts."""
    try:
        resolved = path.resolve()
    except OSError:
        return None
    name = resolved.name
    if _APP_FONTS_DIR.resolve() in (resolved, resolved.parent) or _APP_FONTS_DIR.resolve() in resolved.parents:
        try:
            from flask import has_request_context, url_for

            if has_request_context():
                return url_for("static", filename=f"fonts/{name}")
        except Exception:
            pass
        return f"/static/fonts/{name}"
    plugin_static = (_PLUGIN_DIR / "static").resolve()
    if plugin_static == resolved or plugin_static in resolved.parents:
        rel = resolved.relative_to(plugin_static).as_posix()
        try:
            from flask import has_request_context, url_for

            if has_request_context():
                return url_for("upr_visuals.static_file", filename=rel)
        except Exception:
            pass
        return f"/upr-visuals/static/{rel}"
    return None


def browser_font_face_css() -> str:
    return font_face_css(_http_font_src)


def _prefixed_selectors(prefix: str, selectors: tuple[str, ...]) -> str:
    return ",\n".join(f"{prefix} {sel}" if not sel.startswith(prefix) else sel for sel in selectors)


def typography_css() -> str:
    """Inherit Tajawal under ``.upr-arabic-font``; restore Montserrat on numbers."""
    numbers = _prefixed_selectors(".upr-arabic-font", NUMBER_SELECTORS)
    return f"""
.upr-arabic-font,
.upr-arabic-font * {{
  font-family: {ARABIC_BODY_STACK};
}}
{numbers} {{
  font-family: {ARABIC_NUMBER_STACK};
}}
"""


def document_root_font_css(lang: str | None = None) -> str:
    """Default on ``html, body`` only — children inherit. No element allow-list."""
    from plugins.upr_visuals.i18n import uses_arabic_font

    family = ARABIC_BODY_STACK if uses_arabic_font(lang) else LATIN_BODY_STACK
    return f"html, body {{ font-family: {family}; }}"


def paged_margin_font_css(lang: str | None = None) -> str:
    """WeasyPrint margin boxes (running cover footer) do not inherit ``html`` fonts."""
    from plugins.upr_visuals.i18n import uses_arabic_font

    if not uses_arabic_font(lang):
        return ""
    return f"""
@page {{
  font-family: {ARABIC_BODY_STACK};
}}
@page :first {{
  @bottom-center {{
    font-family: {ARABIC_BODY_STACK};
  }}
}}
"""


def print_typography_css(lang: str | None = None) -> str:
    """Faces + inherit rules + root + paged margin stack for one export language."""
    return "\n".join(
        part
        for part in (
            export_font_face_css(),
            typography_css(),
            document_root_font_css(lang),
            paged_margin_font_css(lang),
        )
        if part
    )


def browser_stylesheet() -> str:
    return f"{browser_font_face_css()}\n{typography_css()}"


def idml_applied_font(*, arabic_font: bool, heading: bool = False) -> str:
    if arabic_font:
        return ARABIC_FAMILY
    return NUMBER_FAMILY if heading else LATIN_FAMILY


def _file_digest(path: Path) -> bytes:
    if not path.is_file():
        return b""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.digest()


@lru_cache(maxsize=1)
def export_style_token() -> str:
    """Content hash of print CSS, typography, HTML, and bundled font files."""
    digest = hashlib.sha256()
    for path in _STYLE_SOURCE_FILES:
        digest.update(path.as_posix().encode())
        digest.update(_file_digest(path))
    for family, path, weight in iter_resolved_fonts():
        digest.update(family.encode())
        digest.update(str(weight).encode())
        digest.update(_file_digest(path))
    digest.update(typography_css().encode())
    digest.update(document_root_font_css("ar").encode())
    digest.update(document_root_font_css("en").encode())
    digest.update(paged_margin_font_css("ar").encode())
    return digest.hexdigest()[:20]
