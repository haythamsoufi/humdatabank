"""Rasterize UPR dashboard HTML to PDF/PNG via WeasyPrint + PyMuPDF."""

from __future__ import annotations

import gc
import io
import json
import logging
import mimetypes
import os
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname, urlopen

from plugins.upr_visuals.catalog import (
    A4_COMBINED_FOLLOWING_MARGIN_MM,
    A4_COMBINED_MARGIN_MM,
    A4_MARGIN_MM,
    A4_PAGE_HEIGHT_PX,
    A4_PAGE_WIDTH_PX,
    A4_PORTRAIT_HEIGHT_PX,
    A4_PORTRAIT_WIDTH_PX,
    DASHBOARD_BY_ID,
)

# WeasyPrint zoom (PDF units per CSS px), then pixmap 1:1. ~8× A4 (~576 dpi)
# so text and icons stay sharp when the PNG is zoomed. Do not use
# get_pixmap(matrix=N) — that only upscales a 72 dpi bake.
PNG_EXPORT_SCALE = 8.0
# Combined All visuals stacks A4 pages into one strip. Paint/GDI+ allows
# 32,767 px; WinUI Snipping Tool and Photos use Direct3D textures (16,384).
MAX_PNG_EDGE = 16384
_IMG_SRC_RE = re.compile(
    r'((?:<img\b[^>]*?\bsrc=|<image\b[^>]*?\b(?:xlink:)?href=)["\'])([^"\']+)(["\'])',
    re.IGNORECASE,
)
_PLUGIN_STATIC_URL = "/upr-visuals/static/"
_NS_LOGO_API_PREFIX = "/api/v1/uploads/ns/"

_PLUGIN_DIR = Path(__file__).resolve().parent
_BACKOFFICE_ROOT = _PLUGIN_DIR.parents[1]
_CSS_PATH = _PLUGIN_DIR / "static" / "css" / "upr-visuals.css"
_APP_STATIC_DIR = Path(__file__).resolve().parents[2] / "app" / "static"
_APP_FONTS_DIR = _APP_STATIC_DIR / "fonts"
_PLUGIN_FONTS_DIR = _PLUGIN_DIR / "fonts"
_APP_STATIC_URL = "/static/"
# HTTPS origins trusted for export image inlining (NS logos and KPI icons from the
# public FDRS GitHub repo).  Only these prefixes are fetched; all other https:// URLs
# remain unchanged and will be blocked by _restricted_url_fetcher as before.
_TRUSTED_REMOTE_PREFIXES = ("https://raw.githubusercontent.com/FDRS-ifrc/",)

logger = logging.getLogger(__name__)


def _first_font(*paths: Path) -> Path | None:
    for path in paths:
        if path.is_file():
            return path
    return None


def _font_face(family: str, path: Path | None, weight: int, *, style: str = "normal") -> str | None:
    if path is None or not path.is_file():
        return None
    # file:// — WeasyPrint 69 often fails to parse huge unquoted data:font URIs.
    uri = path.resolve().as_uri()
    return (
        f"@font-face {{ font-family: '{family}'; "
        f"src: url('{uri}') format('truetype'); "
        f"font-weight: {weight}; font-style: {style}; }}"
    )


def _font_faces(family: str, path: Path | None, weight: int) -> list[str]:
    """Normal + italic faces. Missing italic TTFs reuse roman so WeasyPrint does not fall to Times."""
    faces = [_font_face(family, path, weight), _font_face(family, path, weight, style="italic")]
    return [face for face in faces if face]


_EXPORT_BODY_FONT_CSS = (
    'html, body, table, th, td, p, h1, h2, h3, h4, li {'
    ' font-family: "Open Sans", "Segoe UI", sans-serif; }'
)


@lru_cache(maxsize=1)
def _font_css() -> str:
    open_sans_dirs = (
        _APP_FONTS_DIR,
        _PLUGIN_DIR.parents[0] / "pb_progress" / "visuals" / "report" / "fonts",
    )
    faces: list[str] = []
    faces.extend(
        _font_faces("Open Sans", _first_font(*(folder / "OpenSans-Regular.ttf" for folder in open_sans_dirs)), 400)
    )
    faces.extend(
        _font_faces("Open Sans", _first_font(*(folder / "OpenSans-Bold.ttf" for folder in open_sans_dirs)), 700)
    )
    tajawal_regular = _first_font(
        _PLUGIN_FONTS_DIR / "Tajawal-Regular.ttf",
        _APP_FONTS_DIR / "Tajawal-Regular.ttf",
        *(folder / "Tajawal-Regular.ttf" for folder in open_sans_dirs),
    )
    tajawal_bold = _first_font(
        _PLUGIN_FONTS_DIR / "Tajawal-Bold.ttf",
        _APP_FONTS_DIR / "Tajawal-Bold.ttf",
        *(folder / "Tajawal-Bold.ttf" for folder in open_sans_dirs),
    )
    faces.extend(_font_faces("Tajawal", tajawal_regular, 400))
    faces.extend(_font_faces("Tajawal", tajawal_bold, 700))
    faces.extend(
        _font_faces(
            "Montserrat",
            _first_font(
                _PLUGIN_FONTS_DIR / "Montserrat-Regular.ttf",
                _APP_FONTS_DIR / "Montserrat-Regular.ttf",
            ),
            400,
        )
    )
    faces.extend(
        _font_faces(
            "Montserrat",
            _first_font(
                _PLUGIN_FONTS_DIR / "Montserrat-Bold.ttf",
                _APP_FONTS_DIR / "Montserrat-Bold.ttf",
            ),
            700,
        )
    )
    return "\n".join(faces)


_PRINT_DROP_AT = ("@media", "@keyframes", "@-webkit-keyframes")
_BACKDROP_MIN_COVERAGE_W = 0.85
_BACKDROP_MIN_COVERAGE_H = 0.45
_BACKDROP_NEAR_FULL_W = 0.95
_BACKDROP_NEAR_FULL_H = 0.95
_BACKDROP_WHITE_CHANNEL = 0.98
_CONTENT_CLIP_PAD_PX = 12
_TRIM_PIXMAP_PAD_PX = 16
_PORTRAIT_KEEP_TOGETHER_CSS = (
    ".upr-combined-section:not(.upr-combined-section--finance):not(.upr-combined-section--indicators),"
    ".upr-combined-section:not(.upr-combined-section--finance):not(.upr-combined-section--indicators) > .upr-block,"
    ".upr-combined-section:not(.upr-combined-section--finance):not(.upr-combined-section--indicators) table,"
    ".upr-combined-section:not(.upr-combined-section--finance):not(.upr-combined-section--indicators) .upr-bars {"
    " break-inside: avoid; page-break-inside: avoid; }"
    ".upr-doc-header {"
    " break-inside: avoid; page-break-inside: avoid;"
    " break-after: avoid; page-break-after: avoid;"
    " margin: 0; width: 100%; }"
    ".upr-dashboard--combined { display: block; }"
    ".upr-doc-footer {"
    " position: running(cover-footer); margin: 0; padding: 0; }"
    ".upr-fin-cover,.upr-fin-hero,.upr-fin-grid,"
    ".upr-combined-section--finance,"
    ".upr-combined-section--plan-fund,.upr-block--plan-fund,"
    ".upr-combined-section--network-funding {"
    " break-inside: avoid; page-break-inside: avoid; }"
    ".upr-combined-section--indicators,"
    ".upr-combined-section--indicators > .upr-block {"
    " break-inside: auto; page-break-inside: auto; }"
    ".upr-combined-section--indicators .upr-block__title {"
    " break-after: avoid; page-break-after: avoid; }"
    ".upr-combined-section--indicators .upr-bar-group,"
    ".upr-combined-section--indicators .upr-bar-row {"
    " break-inside: avoid; page-break-inside: avoid; }"
    ".upr-combined-section--page-start {"
    " break-before: page; page-break-before: always; }"
    ".upr-support-table { width: 100%; max-width: 100%; table-layout: fixed; }"
    ".upr-support-table .upr-ns { white-space: normal; overflow-wrap: anywhere; }"
    ".upr-support-th--plan span { writing-mode: horizontal-tb; transform: none; }"
    ".upr-reach-row{ width:100%; max-width:100%; table-layout:fixed; border-collapse:collapse; }"
    ".upr-combined-body{ padding-left:0; padding-right:0; }"
    ".upr-combined-section{ padding-left:8mm; padding-right:8mm; box-sizing:border-box; }"
    ".upr-combined-section--reach{ padding-left:0; padding-right:0; }"
    ".upr-combined-section > .upr-block--reach{"
    " margin-left:0; margin-right:0; width:100%; max-width:none;"
    " padding:1.15rem 8mm 1.35rem; }"
    ".upr-reach-icon,.upr-reach-icon--img,.upr-reach-icon svg{ width:56px; height:56px; }"
    ".upr-fin-hero,.upr-fin-grid{ width:100%; max-width:100%; }"
    ".upr-fin-grid{ table-layout:fixed; border-collapse:collapse; }"
    ".upr-fin-grid--with-sources .upr-fin-col-overview-plot{ width:22%; }"
    ".upr-fin-grid .upr-bar-label{ white-space:normal; overflow-wrap:anywhere; overflow:hidden; }"
    ".upr-fin-col-source-plot{ min-width:6em; }"
    ".upr-bar-track{ display:flex; flex-wrap:nowrap; align-items:center; width:100%; white-space:nowrap; }"
    ".upr-combined-section--finance .upr-block--finance { font-size: 0.78rem; }"
)


def _rtl_print_css(lang: str | None = None) -> str:
    """WeasyPrint-safe RTL overrides.

    Financial tables stay ``direction: ltr`` + ``table-layout: fixed``.
    WeasyPrint reverses RTL table columns and then paints rowspan/Arabic
    into neighbouring cells. Hero and network rows emit plot-first in HTML
    so labels sit on the right; tracks pack to the right and values use
    ``order: -1`` so the number sits to the left of the bar. Unreported
    values are right-aligned in the plot so they sit next to those labels.

    Indicator ``.upr-bars`` tables are RTL so labels sit on the right;
    tracks stay LTR and pack to the right so bars grow toward those labels.
    Values use ``order: -1`` so the number sits to the left of the bar.

    Reach icons cannot use CSS ``border-radius`` + ``overflow: hidden`` —
    WeasyPrint clips those rings into crescents. Rings are SVG; cells stay visible.
    """
    from plugins.upr_visuals.i18n import is_rtl

    if not is_rtl(lang):
        return ""
    return """
html[dir="rtl"] .upr-fin-grid,
html[dir="rtl"] .upr-fin-net {
  direction: ltr;
  table-layout: fixed;
}
html[dir="rtl"] .upr-bars {
  direction: rtl;
  table-layout: fixed;
}
html[dir="rtl"] .upr-reach-row,
html[dir="rtl"] .upr-support-table,
html[dir="rtl"] .upr-source-table,
html[dir="rtl"] .upr-year-table {
  direction: ltr;
  table-layout: fixed;
}
html[dir="rtl"] .upr-num,
html[dir="rtl"] .upr-bar-value,
html[dir="rtl"] .upr-support-total {
  direction: ltr;
  unicode-bidi: isolate;
}
html[dir="rtl"] .upr-amt {
  display: inline-flex;
  flex-direction: row;
  flex-wrap: nowrap;
  align-items: baseline;
  gap: 0.25em;
  direction: ltr;
  unicode-bidi: isolate;
}
html[dir="rtl"] .upr-support-table tbody .upr-num {
  text-align: right;
  overflow: hidden;
}
html[dir="rtl"] .upr-support-table tbody td.upr-num .upr-amt {
  display: flex;
  width: 100%;
  justify-content: flex-end;
}
html[dir="rtl"] .upr-support-table td.upr-support-total {
  text-align: right;
  overflow: visible;
}
html[dir="rtl"] .upr-support-total .upr-amt {
  display: flex;
  width: 100%;
  justify-content: flex-end;
}
html[dir="rtl"] .upr-support-col-ns { width: 22%; }
html[dir="rtl"] .upr-support-col-num { width: 16%; }
html[dir="rtl"] .upr-support-col-dot { width: 9%; }
html[dir="rtl"] .upr-fin-col-overview-label { width: 16%; }
html[dir="rtl"] .upr-fin-col-overview-plot { width: 28%; }
html[dir="rtl"] .upr-fin-grid--with-sources .upr-fin-col-overview-plot { width: 28%; }
html[dir="rtl"] .upr-fin-col-source-label { width: 28%; }
html[dir="rtl"] .upr-fin-col-source-plot { width: 28%; }
html[dir="rtl"] .upr-fin-grid--half .upr-fin-col-overview-label,
html[dir="rtl"] .upr-fin-grid--half .upr-fin-col-source-label { width: 50%; }
html[dir="rtl"] .upr-fin-grid--half .upr-fin-col-overview-plot,
html[dir="rtl"] .upr-fin-grid--half .upr-fin-col-source-plot { width: 50%; }
html[dir="rtl"] .upr-fin-grid--half td.upr-bar-label,
html[dir="rtl"] .upr-fin-hero .upr-bar-row .upr-bar-label {
  padding-inline-start: 0.5em;
  padding-inline-end: 0;
}
html[dir="rtl"] .upr-fin-grid--half td.upr-bar-plot,
html[dir="rtl"] .upr-fin-hero .upr-bar-row .upr-bar-plot {
  padding-inline-end: 0.5em;
  padding-inline-start: 0;
  text-align: right;
}
html[dir="rtl"] .upr-fin-grid--half .upr-bar-yes,
html[dir="rtl"] .upr-fin-grid--half .upr-not-reported,
html[dir="rtl"] .upr-fin-net .upr-bar-yes,
html[dir="rtl"] .upr-fin-net .upr-not-reported,
html[dir="rtl"] .upr-bars .upr-bar-yes {
  display: block;
  text-align: right;
}
html[dir="rtl"] .upr-fin-net-col-entity { width: 22%; }
html[dir="rtl"] .upr-fin-net-col-bucket { width: 16%; }
html[dir="rtl"] .upr-fin-net-col-metric { width: 16%; }
html[dir="rtl"] .upr-fin-net-col-plot { width: 46%; }
html[dir="rtl"] .upr-fin-grid .upr-bar-label,
html[dir="rtl"] .upr-fin-hero .upr-bar-label,
html[dir="rtl"] .upr-bars .upr-bar-label,
html[dir="rtl"] .upr-fin-net__entity,
html[dir="rtl"] .upr-fin-net__bucket {
  white-space: normal;
  overflow: hidden;
  overflow-wrap: break-word;
  word-break: break-word;
  max-width: none;
  min-width: 0;
}
html[dir="rtl"] .upr-bar-plot,
html[dir="rtl"] .upr-fin-net__plot {
  overflow: hidden;
}
html[dir="rtl"] .upr-bar-plot .upr-bar-yes,
html[dir="rtl"] .upr-fin-net__plot .upr-bar-yes {
  white-space: nowrap;
}
html[dir="rtl"] .upr-bar-track {
  direction: ltr;
}
html[dir="rtl"] .upr-bars .upr-bar-track,
html[dir="rtl"] .upr-fin-net .upr-bar-track {
  justify-content: flex-end;
}
html[dir="rtl"] .upr-bars .upr-bar-value,
html[dir="rtl"] .upr-fin-net .upr-bar-value {
  order: -1;
}
html[dir="rtl"] .upr-fin-grid .upr-bar-track {
  justify-content: flex-end;
}
html[dir="rtl"] .upr-fin-grid .upr-bar-value {
  order: -1;
}
html[dir="rtl"] .upr-doc-header__titles,
html[dir="rtl"] .upr-doc-header__subtitle,
html[dir="rtl"] .upr-doc-header__country,
html[dir="rtl"] .upr-fin-grid th,
html[dir="rtl"] .upr-fin-grid td.upr-bar-label,
html[dir="rtl"] .upr-fin-net__entity,
html[dir="rtl"] .upr-fin-net__bucket,
html[dir="rtl"] .upr-fin-net__metric {
  text-align: right;
}
html[dir="rtl"] .upr-bars .upr-bar-label,
html[dir="rtl"] .upr-block--bars .upr-bar-label,
html[dir="rtl"] .upr-block--emergency .upr-bar-label {
  text-align: left;
}
html[dir="rtl"] .upr-block__title,
html[dir="rtl"] .upr-block__title--center,
html[dir="rtl"] .upr-block__subtitle--center,
html[dir="rtl"] .upr-fin-unit,
html[dir="rtl"] .upr-fin-ns {
  text-align: center;
}
html[dir="rtl"] .upr-block--support .upr-block__title,
html[dir="rtl"] .upr-block--support .upr-kpi,
html[dir="rtl"] .upr-block--support .upr-kpi__label,
html[dir="rtl"] .upr-block--support .upr-kpi__value {
  text-align: center;
}
html[dir="rtl"] .upr-block--support .upr-kpi {
  display: flex;
  flex-direction: column;
  align-items: center;
}
html[dir="rtl"] .upr-block--support .upr-kpi__icon,
html[dir="rtl"] .upr-block--support .upr-kpi__icon--img {
  display: block;
  margin-left: auto;
  margin-right: auto;
}
html[dir="rtl"] .upr-block--support .upr-kpi__value {
  direction: ltr;
  unicode-bidi: isolate;
}
html[dir="rtl"] .upr-reach-row {
  direction: ltr;
}
html[dir="rtl"] .upr-reach-label,
html[dir="rtl"] .upr-reach-icon-wrap,
html[dir="rtl"] .upr-reach-value,
html[dir="rtl"] .upr-reach-band--icons td {
  text-align: center;
  overflow: visible;
}
html[dir="rtl"] .upr-reach-icon-wrap {
  min-height: 4.25rem;
  padding: 0.35rem 0.15rem 0.2rem;
}
html[dir="rtl"] .upr-reach-icon,
html[dir="rtl"] .upr-reach-icon--img,
html[dir="rtl"] .upr-reach-icon svg {
  overflow: visible;
  display: block;
  width: 56px;
  height: 56px;
  margin-left: auto;
  margin-right: auto;
  border: none;
  border-radius: 0;
  background: transparent;
}
html[dir="rtl"] .upr-fin-hero-split {
  direction: rtl;
}
html[dir="rtl"] .upr-fin-hero-split .upr-fin-grid {
  direction: ltr;
}
html[dir="rtl"] .upr-reach-divider {
  width: 2px;
  min-width: 2px;
  max-width: 2px;
  padding: 0;
  border: none;
  background: #011e41;
}
html[dir="rtl"] .upr-reach-band--labels .upr-reach-divider {
  background: transparent;
  border: none;
}
"""


def _css_for_print(css: str) -> str:
    """Drop screen-only at-rules. WeasyPrint rejects @media and @keyframes."""
    out: list[str] = []
    i = 0
    length = len(css)
    while i < length:
        start = -1
        for name in _PRINT_DROP_AT:
            pos = css.find(name, i)
            if pos >= 0 and (start < 0 or pos < start):
                start = pos
        if start < 0:
            out.append(css[i:])
            break
        out.append(css[i:start])
        brace = css.find("{", start)
        if brace < 0:
            break
        depth = 0
        j = brace
        while j < len(css):
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1
        i = j
    return _strip_print_unsupported(_drop_unused_print_rules("".join(out)))


_PRINT_DROP_SELECTOR_MARKERS = (
    "::-webkit-",
    "::-moz-",
    ".upr-visuals-embed",
    ".upr-visuals-lang",
    ".upr-visuals-download",
    ".upr-visuals-narrative",
    "#upr-visuals-narrative",
)
_PRINT_DROP_DECL_RE = re.compile(
    r"(?i)([;{])\s*(?:box-shadow|overflow-x|-webkit-overflow-scrolling|scrollbar-width)\s*:[^;}]*"
)


def _is_print_chrome_selector(selector: str) -> bool:
    return any(marker in selector for marker in _PRINT_DROP_SELECTOR_MARKERS)


def _drop_unused_print_rules(css: str) -> str:
    """Drop UI-only selectors. Keep siblings in the same rule (e.g. ``.upr-dashboard``)."""
    out: list[str] = []
    i = 0
    while i < len(css):
        brace = css.find("{", i)
        if brace < 0:
            out.append(css[i:])
            break
        raw_selector = css[i:brace]
        depth = 0
        j = brace
        while j < len(css):
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1
        parts = raw_selector.split(",")
        kept = [part for part in parts if part.strip() and not _is_print_chrome_selector(part)]
        if not kept:
            i = j
            continue
        if len(kept) != len(parts):
            lead_len = len(raw_selector) - len(raw_selector.lstrip())
            rebuilt = ",".join(kept)
            if lead_len and not rebuilt[:1].isspace():
                rebuilt = raw_selector[:lead_len] + rebuilt.lstrip()
            out.append(rebuilt + css[brace:j])
        else:
            out.append(css[i:j])
        i = j
    return "".join(out)
_WEASYPRINT_IGNORED_RE = re.compile(r"^Ignored `.+` at \d+:\d+, .+$")
_OWN_CHILD_LINE_RE = re.compile(r"^(?:DEBUG|INFO|WARNING|ERROR) |^UPR (?:PNG|export) ")


def _strip_print_unsupported(css: str) -> str:
    """Drop declarations WeasyPrint warns about and does not paint."""
    return _PRINT_DROP_DECL_RE.sub(r"\1", css)


def summarize_child_log(text: str) -> str:
    """Keep unexpected child output; drop WeasyPrint CSS noise and our own progress lines."""
    keep: list[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _WEASYPRINT_IGNORED_RE.match(stripped):
            continue
        if _OWN_CHILD_LINE_RE.match(stripped):
            continue
        keep.append(line)
    return "\n".join(keep).strip()


@lru_cache(maxsize=1)
def _print_css() -> str:
    css = _CSS_PATH.read_text(encoding="utf-8") if _CSS_PATH.is_file() else ""
    return _css_for_print(css)


def _is_portrait_export(dashboard_id: str) -> bool:
    return dashboard_id == "combined"


def _page_size(dashboard_id: str) -> tuple[int, int]:
    """A4 CSS-pixel canvas. Combined (All visuals) is portrait; other chips stay landscape."""
    DASHBOARD_BY_ID[dashboard_id]
    if _is_portrait_export(dashboard_id):
        return A4_PORTRAIT_WIDTH_PX, A4_PORTRAIT_HEIGHT_PX
    return A4_PAGE_WIDTH_PX, A4_PAGE_HEIGHT_PX


def _pdf_page_css(dashboard_id: str) -> str:
    portrait = _is_portrait_export(dashboard_id)
    orientation = "portrait" if portrait else "landscape"
    margin = A4_COMBINED_MARGIN_MM if portrait else A4_MARGIN_MM
    from plugins.upr_visuals.i18n import current_export_language

    keep_together = _PORTRAIT_KEEP_TOGETHER_CSS if portrait else ""
    rtl_print = _rtl_print_css(current_export_language())
    if portrait:
        page = (
            f"@page {{ size: A4 portrait; margin: {A4_COMBINED_FOLLOWING_MARGIN_MM}mm 0; }}\n"
            "@page :first {\n"
            f"  margin: {A4_COMBINED_MARGIN_MM}mm {A4_COMBINED_MARGIN_MM}mm 18mm;\n"
            "  @bottom-center {\n"
            "    content: element(cover-footer);\n"
            "    width: 100%;\n"
            "    vertical-align: bottom;\n"
            "    padding: 0 8mm 5mm;\n"
            "  }\n"
            "}\n"
        )
    else:
        page = f"@page {{ size: A4 {orientation}; margin: {margin}mm; }}\n"
    return (
        page
        + "html, body { margin: 0; padding: 0; background: #fff; }\n"
        + f"{_EXPORT_BODY_FONT_CSS}\n"
        f"{keep_together}"
        f"{rtl_print}"
    )


def _is_allowed_local_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    plugin_root = _PLUGIN_DIR.resolve()
    app_static = _APP_STATIC_DIR.resolve()
    return resolved == plugin_root or plugin_root in resolved.parents or resolved == app_static or app_static in resolved.parents


def _ns_logo_data_uri(filename: str) -> str:
    name = os.path.basename((filename or "").replace("\\", "/")).strip()
    if not name or name in {".", ".."}:
        return ""
    try:
        from app.services.platform import storage_service as storage

        data = storage.download(storage.SYSTEM, f"ns/{name}")
    except Exception:
        logger.debug("UPR visuals: could not load NS logo %s for export", name, exc_info=True)
        return ""
    if not data:
        return ""
    mime = mimetypes.guess_type(name)[0] or "image/png"
    import base64

    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _fetch_remote_as_data_uri(url: str) -> str:
    """Download a remote image from a trusted origin and return a data URI.

    Only called for URLs that match _TRUSTED_REMOTE_PREFIXES, so no untrusted
    network egress happens during export.
    """
    import base64

    parsed = urlparse(url)
    name = Path(unquote(parsed.path)).name or "image.png"
    try:
        with urlopen(url, timeout=10) as resp:
            data = resp.read()
    except Exception:
        logger.debug("UPR visuals: could not fetch remote image %s for export", url, exc_info=True)
        return ""
    if not data:
        return ""
    mime = mimetypes.guess_type(name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def resolve_export_image_src(src: str) -> str:
    """Map Flask/plugin image URLs to file:// or data: so WeasyPrint can read them."""
    raw = (src or "").strip()
    if not raw or raw.startswith(("data:", "file:")):
        return raw
    plugin_root = _PLUGIN_DIR.resolve()
    app_static = _APP_STATIC_DIR.resolve()
    candidates: list[Path] = []
    path_only = raw.split("?", 1)[0]
    if path_only.startswith(_NS_LOGO_API_PREFIX):
        return _ns_logo_data_uri(path_only[len(_NS_LOGO_API_PREFIX) :]) or ""
    if path_only.startswith(_PLUGIN_STATIC_URL):
        candidates.append(_PLUGIN_DIR / "static" / path_only[len(_PLUGIN_STATIC_URL) :])
    elif path_only.startswith(_APP_STATIC_URL):
        candidates.append(_APP_STATIC_DIR / path_only[len(_APP_STATIC_URL) :])
    elif path_only.startswith("static/"):
        candidates.append(_PLUGIN_DIR / path_only)
        candidates.append(_APP_STATIC_DIR / path_only[len("static/") :])
    elif not path_only.startswith(("http://", "https://", "/")):
        candidates.append(_PLUGIN_DIR / path_only)
        candidates.append(_PLUGIN_DIR / "static" / path_only)
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        in_plugin = resolved == plugin_root or plugin_root in resolved.parents
        in_app_static = resolved == app_static or app_static in resolved.parents
        if resolved.is_file() and (in_plugin or in_app_static):
            return resolved.as_uri()
    # Inline images from known trusted remote origins so they survive
    # _restricted_url_fetcher (which blocks all http/https).
    if any(raw.startswith(p) for p in _TRUSTED_REMOTE_PREFIXES):
        return _fetch_remote_as_data_uri(raw) or raw
    return raw


def _restricted_url_fetcher(url, timeout=10, ssl_context=None):
    """Allow only data: and local files under the plugin / app static trees."""
    from weasyprint.urls import default_url_fetcher

    raw = (url or "").strip()
    if raw.startswith("data:"):
        return default_url_fetcher(url, timeout=timeout, ssl_context=ssl_context)
    parsed = urlparse(raw)
    if parsed.scheme != "file":
        raise ValueError(f"Blocked export URL scheme: {parsed.scheme or 'unknown'}")
    local = Path(url2pathname(unquote(parsed.path)))
    if not _is_allowed_local_path(local):
        raise ValueError("Blocked export file URL outside allowed static roots")
    return default_url_fetcher(url, timeout=timeout, ssl_context=ssl_context)


def _rewrite_export_images(html: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        return f"{match.group(1)}{resolve_export_image_src(match.group(2))}{match.group(3)}"

    return _IMG_SRC_RE.sub(_replace, html)


def _wrap(
    dashboard_html: str,
    width: int | None = None,
    *,
    dashboard_id: str = "",
    title: str = "",
) -> str:
    from html import escape

    from plugins.upr_visuals.i18n import current_export_language, rtl_css, rtl_document_attrs

    keep_together = _PORTRAIT_KEEP_TOGETHER_CSS if _is_portrait_export(dashboard_id) else ""
    lang = current_export_language()
    attrs = rtl_document_attrs(lang)
    title_html = f"<title>{escape((title or '').strip())}</title>" if (title or "").strip() else ""
    return (
        f"<!DOCTYPE html><html lang='{attrs['lang']}' dir='{attrs['dir']}'><head><meta charset='utf-8'>"
        f"{title_html}"
        "<style>"
        f"{_font_css()}\n{_print_css()}\n{rtl_css(lang)}\n"
        "html, body { margin: 0; padding: 0; background: #fff; }"
        f"{_EXPORT_BODY_FONT_CSS}"
        ".upr-dashboard { width: 100%; max-width: none; }"
        ".upr-vis-page { width: auto; max-width: none; min-height: 0; "
        "padding: 0; margin: 0; }"
        f"{keep_together}"
        f"{_rtl_print_css(lang)}"
        "</style></head><body>"
        f"{_rewrite_export_images(dashboard_html)}</body></html>"
    )


def _is_page_backdrop(drawing, page_rect) -> bool:
    """Skip full-page white fills so crop is not stuck to the catalog canvas."""
    rect = drawing.get("rect")
    if not rect:
        return True
    import fitz

    area = fitz.Rect(rect)
    covers_page = (
        area.width >= page_rect.width * _BACKDROP_MIN_COVERAGE_W
        and area.height >= page_rect.height * _BACKDROP_MIN_COVERAGE_H
    )
    if not covers_page:
        return False
    fill = drawing.get("fill")
    if not fill:
        return (
            area.width >= page_rect.width * _BACKDROP_NEAR_FULL_W
            and area.height >= page_rect.height * _BACKDROP_NEAR_FULL_H
        )
    try:
        rgb = fill[:3]
    except (TypeError, IndexError):
        return False
    return all(float(channel) >= _BACKDROP_WHITE_CHANNEL for channel in rgb)


def _content_rect(page):
    import fitz

    clip = fitz.Rect()
    for block in page.get_text("blocks"):
        clip |= fitz.Rect(block[:4])
    for info in page.get_image_info():
        clip |= fitz.Rect(info["bbox"])
    try:
        drawings = page.get_drawings()
    except Exception:
        drawings = []
    for drawing in drawings:
        rect = drawing.get("rect")
        if not rect or _is_page_backdrop(drawing, page.rect):
            continue
        clip |= fitz.Rect(rect)
    if clip.is_empty:
        return page.rect
    clip.x0 = max(page.rect.x0, clip.x0 - _CONTENT_CLIP_PAD_PX)
    clip.y0 = max(page.rect.y0, clip.y0 - _CONTENT_CLIP_PAD_PX)
    clip.x1 = min(page.rect.x1, clip.x1 + _CONTENT_CLIP_PAD_PX)
    clip.y1 = min(page.rect.y1, clip.y1 + _CONTENT_CLIP_PAD_PX)
    return clip


def ink_bounds(
    samples: bytes | memoryview,
    width: int,
    height: int,
    n: int,
    *,
    threshold: int = 248,
) -> tuple[int, int, int, int] | None:
    """Inclusive pixel bbox of non-white content. Used to trim PNG whitespace."""
    if width <= 0 or height <= 0 or n < 3:
        return None
    import numpy as np

    arr = np.frombuffer(samples, dtype=np.uint8).reshape(height, width, n)
    used = (arr[:, :, :3] < threshold).any(axis=2)
    rows = np.flatnonzero(used.any(axis=1))
    if rows.size == 0:
        return None
    cols = np.flatnonzero(used.any(axis=0))
    return int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1])


def _trim_pixmap(pixmap, *, pad: int = _TRIM_PIXMAP_PAD_PX, keep_width: bool = False):
    import fitz

    bounds = ink_bounds(pixmap.samples, pixmap.width, pixmap.height, pixmap.n)
    if bounds is None:
        return pixmap
    x0, y0, x1, y1 = bounds
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(pixmap.width - 1, x1 + pad)
    y1 = min(pixmap.height - 1, y1 + pad)
    if keep_width:
        x0 = 0
        x1 = pixmap.width - 1
    if x0 == 0 and y0 == 0 and x1 == pixmap.width - 1 and y1 == pixmap.height - 1:
        return pixmap
    width = x1 - x0 + 1
    height = y1 - y0 + 1
    n = pixmap.n
    stride = pixmap.width * n
    src = pixmap.samples
    cropped = b"".join(
        src[y * stride + x0 * n : y * stride + (x1 + 1) * n] for y in range(y0, y1 + 1)
    )
    alpha = 1 if pixmap.alpha else 0
    return fitz.Pixmap(pixmap.colorspace, width, height, cropped, alpha)


def _stitch_pixmaps(pixmaps: list) -> object:
    """Stack A4 pages top-to-bottom so one PNG still holds a multi-page visual."""
    import fitz

    width = max(pixmap.width for pixmap in pixmaps)
    height = sum(pixmap.height for pixmap in pixmaps)
    channels = pixmaps[0].n
    canvas = bytearray([255] * (width * height * channels))
    top = 0
    for pixmap in pixmaps:
        src_stride = pixmap.width * channels
        dest_stride = width * channels
        source = pixmap.samples
        for row in range(pixmap.height):
            start = row * src_stride
            dest = (top + row) * dest_stride
            canvas[dest : dest + src_stride] = source[start : start + src_stride]
        top += pixmap.height
    return fitz.Pixmap(pixmaps[0].colorspace, width, height, bytes(canvas), 0)


def render_pdf_bytes(
    dashboard_html: str,
    *,
    dashboard_id: str,
    zoom: float = 1.0,
    title: str = "",
    full_fonts: bool = False,
) -> bytes:
    try:
        from weasyprint import CSS, HTML
    except ImportError as exc:
        raise RuntimeError("WeasyPrint is required for UPR visual export.") from exc

    _page_size(dashboard_id)
    document_html = _wrap(dashboard_html, dashboard_id=dashboard_id, title=title)
    page_css = CSS(string=_pdf_page_css(dashboard_id))
    pdf_buffer = io.BytesIO()
    HTML(
        string=document_html,
        base_url=_PLUGIN_DIR.resolve().as_uri() + "/",
        url_fetcher=_restricted_url_fetcher,
    ).write_pdf(
        pdf_buffer,
        stylesheets=[page_css],
        optimize_images=False,
        full_fonts=full_fonts,
        hinting=True,
        zoom=zoom,
    )
    return pdf_buffer.getvalue()


def _png_render_scale(doc, *, scale: float) -> float:
    """Fit a stitched multi-page PNG under Direct3D's 16,384 px texture limit."""
    width = max((float(page.rect.width) for page in doc), default=1.0)
    height = sum(float(page.rect.height) for page in doc) or 1.0
    return max(0.25, min(float(scale), MAX_PNG_EDGE / height, MAX_PNG_EDGE / width))


def render_png(
    dashboard_html: str,
    output_path: Path,
    *,
    dashboard_id: str,
    scale: float = PNG_EXPORT_SCALE,
) -> Path:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF (fitz) is required for UPR visual PNG export.") from exc

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Combined / multi-page: rasterize from a 1× PDF, then scale the pixmap so
    # the stacked strip stays under MAX_PNG_EDGE (Snipping Tool / D3D 16,384).
    bake_zoom = 1.0 if _is_portrait_export(dashboard_id) else scale
    pdf_bytes = render_pdf_bytes(dashboard_html, dashboard_id=dashboard_id, zoom=bake_zoom)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pixmap = None
    try:
        if bake_zoom == 1.0:
            render_scale = _png_render_scale(doc, scale=scale)
            matrix = fitz.Matrix(render_scale, render_scale)
        else:
            render_scale = bake_zoom
            matrix = None
        logger.info(
            "UPR PNG %s: %s page(s), scale=%.2f",
            dashboard_id,
            doc.page_count,
            render_scale,
        )
        for page in doc:
            page_pix = (
                page.get_pixmap(matrix=matrix, alpha=False)
                if matrix is not None
                else page.get_pixmap(alpha=False)
            )
            if doc.page_count > 1:
                page_pix = _trim_pixmap(page_pix, keep_width=True)
            if pixmap is None:
                pixmap = page_pix
            else:
                pixmap = _stitch_pixmaps([pixmap, page_pix])
        if pixmap is None:
            raise RuntimeError(f"PNG render produced no pages for {dashboard_id}")
        pixmap = _trim_pixmap(pixmap, keep_width=True)
        pixmap.save(str(output_path))
    except MemoryError as exc:
        logger.exception("UPR PNG out of memory for %s", dashboard_id)
        raise RuntimeError(f"PNG render ran out of memory for {dashboard_id}") from exc
    finally:
        pixmap = None
        doc.close()
        gc.collect()
    return output_path


def render_png_job_file(job_path: str | Path) -> None:
    """Child-process entry: read a JSON job file and write the PNG."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("weasyprint").setLevel(logging.ERROR)
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    html = Path(job["html_path"]).read_text(encoding="utf-8")
    render_png(
        html,
        Path(job["output_path"]),
        dashboard_id=str(job["dashboard_id"]),
        scale=float(job.get("scale") or PNG_EXPORT_SCALE),
    )


def render_png_isolated(
    dashboard_html: str,
    output_path: Path,
    *,
    dashboard_id: str,
    scale: float = PNG_EXPORT_SCALE,
    timeout: float = 120.0,
) -> Path:
    """Rasterize in a child process so a Cairo/PyMuPDF abort cannot kill Flask."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    job_path = output_path.with_suffix(output_path.suffix + ".job.json")
    html_path = output_path.with_suffix(output_path.suffix + ".html")
    html_path.write_text(dashboard_html, encoding="utf-8")
    job_path.write_text(
        json.dumps(
            {
                "html_path": str(html_path),
                "output_path": str(output_path),
                "dashboard_id": dashboard_id,
                "scale": scale,
            }
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    pythonpath = os.pathsep.join(
        path for path in (str(_BACKOFFICE_ROOT), env.get("PYTHONPATH", "")) if path
    )
    env["PYTHONPATH"] = pythonpath
    cmd = [
        sys.executable,
        "-c",
        "from plugins.upr_visuals.raster import render_png_job_file; "
        "render_png_job_file(__import__('sys').argv[1])",
        str(job_path),
    ]
    logger.info("UPR PNG start %s", dashboard_id)
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(_BACKOFFICE_ROOT),
            env=env,
            timeout=timeout,
            capture_output=True,
            text=True,
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        logger.error("UPR PNG timed out after %.0fs: %s", timeout, dashboard_id)
        raise TimeoutError(f"PNG render timed out for {dashboard_id}") from exc
    finally:
        for path in (job_path, html_path):
            try:
                path.unlink()
            except OSError:
                pass
    child_log = ((completed.stderr or "") + (completed.stdout or "")).strip()
    useful = summarize_child_log(child_log)
    if useful:
        logger.warning("UPR PNG %s child:\n%s", dashboard_id, useful[-4000:])
    if completed.returncode:
        logger.error(
            "UPR PNG renderer crashed for %s (exit %s)",
            dashboard_id,
            completed.returncode,
        )
        raise RuntimeError(
            useful or child_log or f"PNG renderer crashed (exit {completed.returncode})"
        )
    if not output_path.is_file() or output_path.stat().st_size <= 0:
        raise RuntimeError(f"PNG renderer produced no file for {dashboard_id}")
    logger.info("UPR PNG done %s (%s bytes)", dashboard_id, output_path.stat().st_size)
    return output_path
