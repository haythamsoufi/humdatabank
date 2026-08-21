"""Rasterize UPR dashboard HTML to PDF/PNG via WeasyPrint + PyMuPDF."""

from __future__ import annotations

import io
import re
from functools import lru_cache
from pathlib import Path

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
_IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc=["\'])([^"\']+)(["\'])', re.IGNORECASE)
_PLUGIN_STATIC_URL = "/upr-visuals/static/"

_PLUGIN_DIR = Path(__file__).resolve().parent
_CSS_PATH = _PLUGIN_DIR / "static" / "css" / "upr-visuals.css"
_APP_STATIC_DIR = Path(__file__).resolve().parents[2] / "app" / "static"
_APP_FONTS_DIR = _APP_STATIC_DIR / "fonts"
_PLUGIN_FONTS_DIR = _PLUGIN_DIR / "fonts"
_APP_STATIC_URL = "/static/"


def _first_font(*paths: Path) -> Path | None:
    for path in paths:
        if path.is_file():
            return path
    return None


def _font_face(family: str, path: Path | None, weight: int) -> str | None:
    if path is None or not path.is_file():
        return None
    # file:// — WeasyPrint 69 often fails to parse huge unquoted data:font URIs.
    uri = path.resolve().as_uri()
    return (
        f"@font-face {{ font-family: '{family}'; "
        f"src: url('{uri}') format('truetype'); "
        f"font-weight: {weight}; font-style: normal; }}"
    )


@lru_cache(maxsize=1)
def _font_css() -> str:
    open_sans_dirs = (
        _APP_FONTS_DIR,
        _PLUGIN_DIR.parents[0] / "pb_progress" / "visuals" / "report" / "fonts",
    )
    faces = [
        _font_face("Open Sans", _first_font(*(folder / "OpenSans-Regular.ttf" for folder in open_sans_dirs)), 400),
        _font_face("Open Sans", _first_font(*(folder / "OpenSans-Bold.ttf" for folder in open_sans_dirs)), 700),
        _font_face(
            "Montserrat",
            _first_font(
                _PLUGIN_FONTS_DIR / "Montserrat-Regular.ttf",
                _APP_FONTS_DIR / "Montserrat-Regular.ttf",
            ),
            400,
        ),
        _font_face(
            "Montserrat",
            _first_font(
                _PLUGIN_FONTS_DIR / "Montserrat-Bold.ttf",
                _APP_FONTS_DIR / "Montserrat-Bold.ttf",
            ),
            700,
        ),
    ]
    return "\n".join(face for face in faces if face)


def _css_for_print(css: str) -> str:
    """Drop @media blocks. WeasyPrint rejects query-only media, and PNG export is desktop-width."""
    out: list[str] = []
    i = 0
    while True:
        start = css.find("@media", i)
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
    return "".join(out)


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
    keep_together = ""
    if portrait:
        keep_together = (
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
            ".upr-combined-section--finance {"
            " break-inside: avoid; page-break-inside: avoid; }"
            ".upr-combined-section--finance .upr-block--finance { font-size: 0.78rem; }"
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
            ".upr-combined-section > .upr-block--reach{"
            " margin-left:-8mm; margin-right:-8mm; width:calc(100% + 16mm); max-width:none;"
            " padding:1.15rem 8mm 1.35rem; }"
            ".upr-reach-icon,.upr-reach-icon--img{ width:3.35rem; height:3.35rem; }"
            ".upr-reach-icon--img img{ width:2.05rem; height:2.05rem; }"
            ".upr-fin-hero,.upr-fin-grid{ width:100%; max-width:100%; }"
            ".upr-fin-grid{ table-layout:fixed; border-collapse:collapse; }"
            ".upr-fin-grid--with-sources .upr-fin-col-overview-plot{ width:22%; }"
            ".upr-fin-grid .upr-bar-label{ white-space:nowrap; }"
            ".upr-bar-track{ display:flex; flex-wrap:nowrap; align-items:center; width:100%; white-space:nowrap; }"
        )
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
        f"{keep_together}"
    )


def resolve_export_image_src(src: str) -> str:
    """Map Flask/plugin image URLs to file:// so WeasyPrint can read them."""
    raw = (src or "").strip()
    if not raw or raw.startswith(("data:", "file:")):
        return raw
    plugin_root = _PLUGIN_DIR.resolve()
    app_static = _APP_STATIC_DIR.resolve()
    candidates: list[Path] = []
    path_only = raw.split("?", 1)[0]
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
    return raw


def _rewrite_export_images(html: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        return f"{match.group(1)}{resolve_export_image_src(match.group(2))}{match.group(3)}"

    return _IMG_SRC_RE.sub(_replace, html)


def _wrap(dashboard_html: str, width: int | None = None, *, dashboard_id: str = "") -> str:
    css = _CSS_PATH.read_text(encoding="utf-8") if _CSS_PATH.is_file() else ""
    keep_together = ""
    if _is_portrait_export(dashboard_id):
        keep_together = (
            ".upr-combined-section:not(.upr-combined-section--finance):not(.upr-combined-section--indicators),"
            " .upr-combined-section:not(.upr-combined-section--finance):not(.upr-combined-section--indicators) > .upr-block,"
            " .upr-combined-section:not(.upr-combined-section--finance):not(.upr-combined-section--indicators) table,"
            " .upr-combined-section:not(.upr-combined-section--finance):not(.upr-combined-section--indicators) .upr-bars {"
            " break-inside: avoid; page-break-inside: avoid; }"
            ".upr-combined-section--indicators,"
            " .upr-combined-section--indicators > .upr-block {"
            " break-inside: auto; page-break-inside: auto; }"
            ".upr-combined-section--indicators .upr-bar-group {"
            " break-inside: avoid; page-break-inside: avoid; }"
            ".upr-fin-cover,.upr-fin-hero,.upr-fin-grid,"
            ".upr-combined-section--finance {"
            " break-inside: avoid; page-break-inside: avoid; }"
        )
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<style>"
        f"{_font_css()}\n{_css_for_print(css)}\n"
        "html, body { margin: 0; padding: 0; background: #fff; }"
        ".upr-dashboard { width: 100%; max-width: none; }"
        ".upr-vis-page { width: auto; max-width: none; min-height: 0; "
        "padding: 0; margin: 0; box-shadow: none; }"
        f"{keep_together}"
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
    covers_page = area.width >= page_rect.width * 0.85 and area.height >= page_rect.height * 0.45
    if not covers_page:
        return False
    fill = drawing.get("fill")
    if not fill:
        return area.width >= page_rect.width * 0.95 and area.height >= page_rect.height * 0.95
    try:
        rgb = fill[:3]
    except (TypeError, IndexError):
        return False
    return all(float(channel) >= 0.98 for channel in rgb)


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
    clip.x0 = max(page.rect.x0, clip.x0 - 12)
    clip.y0 = max(page.rect.y0, clip.y0 - 12)
    clip.x1 = min(page.rect.x1, clip.x1 + 12)
    clip.y1 = min(page.rect.y1, clip.y1 + 12)
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
    buf = memoryview(samples)
    stride = width * n

    def row_used(y: int) -> bool:
        row = buf[y * stride : (y + 1) * stride]
        for i in range(0, len(row), n):
            if row[i] < threshold or row[i + 1] < threshold or row[i + 2] < threshold:
                return True
        return False

    y0 = next((y for y in range(height) if row_used(y)), None)
    if y0 is None:
        return None
    y1 = next(y for y in range(height - 1, y0 - 1, -1) if row_used(y))

    def col_used(x: int) -> bool:
        for y in range(y0, y1 + 1):
            i = (y * width + x) * n
            if buf[i] < threshold or buf[i + 1] < threshold or buf[i + 2] < threshold:
                return True
        return False

    x0 = next(x for x in range(width) if col_used(x))
    x1 = next(x for x in range(width - 1, x0 - 1, -1) if col_used(x))
    return x0, y0, x1, y1


def _trim_pixmap(pixmap, *, pad: int = 16, keep_width: bool = False):
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


def render_pdf_bytes(dashboard_html: str, *, dashboard_id: str, zoom: float = 1.0) -> bytes:
    try:
        from weasyprint import CSS, HTML
    except ImportError as exc:
        raise RuntimeError("WeasyPrint is required for UPR visual export.") from exc

    _page_size(dashboard_id)
    document_html = _wrap(dashboard_html, dashboard_id=dashboard_id)
    page_css = CSS(string=_pdf_page_css(dashboard_id))
    pdf_buffer = io.BytesIO()
    HTML(string=document_html, base_url=_PLUGIN_DIR.resolve().as_uri() + "/").write_pdf(
        pdf_buffer,
        stylesheets=[page_css],
        optimize_images=False,
        full_fonts=True,
        hinting=True,
        zoom=zoom,
    )
    return pdf_buffer.getvalue()


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
    pdf_bytes = render_pdf_bytes(dashboard_html, dashboard_id=dashboard_id, zoom=scale)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        pixmaps = [page.get_pixmap(alpha=False) for page in doc]
        pixmap = pixmaps[0] if len(pixmaps) == 1 else _stitch_pixmaps(pixmaps)
        pixmap = _trim_pixmap(pixmap, keep_width=True)
        pixmap.save(str(output_path))
    finally:
        doc.close()
    return output_path
