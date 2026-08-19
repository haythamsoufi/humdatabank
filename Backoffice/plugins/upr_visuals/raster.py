"""Rasterize UPR dashboard HTML to PDF/PNG via WeasyPrint + PyMuPDF."""

from __future__ import annotations

import io
from pathlib import Path

from plugins.upr_visuals.catalog import DASHBOARD_BY_ID

_PLUGIN_DIR = Path(__file__).resolve().parent
_CSS_PATH = _PLUGIN_DIR / "static" / "css" / "upr-visuals.css"
_APP_FONTS_DIR = Path(__file__).resolve().parents[2] / "app" / "static" / "fonts"
_PLUGIN_FONTS_DIR = _PLUGIN_DIR / "fonts"


def _first_font(*paths: Path) -> Path | None:
    for path in paths:
        if path.is_file():
            return path
    return None


def _font_face(family: str, path: Path | None, weight: int) -> str | None:
    if path is None:
        return None
    posix = path.as_posix()
    return (
        f"@font-face {{ font-family: '{family}'; src: url('file:///{posix}'); "
        f"font-weight: {weight}; font-style: normal; }}"
    )


def _font_css() -> str:
    faces = [
        _font_face("Open Sans", _first_font(_APP_FONTS_DIR / "OpenSans-Regular.ttf"), 400),
        _font_face("Open Sans", _first_font(_APP_FONTS_DIR / "OpenSans-Bold.ttf"), 700),
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


def _page_size(dashboard_id: str) -> tuple[int, int]:
    """PDF canvas size. PNG output is cropped to ink, so this is headroom only."""
    spec = DASHBOARD_BY_ID[dashboard_id]
    width = spec.width
    if dashboard_id == "combined":
        return width, max(spec.height * 5, 8000)
    return width, max(spec.height * 2, spec.height + 400)


def _wrap(dashboard_html: str, width: int) -> str:
    css = _CSS_PATH.read_text(encoding="utf-8") if _CSS_PATH.is_file() else ""
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<style>"
        f"{_font_css()}\n{css}\n"
        "html, body { margin: 0; padding: 0; background: #fff; }"
        f".upr-dashboard {{ width: {width}px; max-width: {width}px; }}"
        "</style></head><body>"
        f"{dashboard_html}</body></html>"
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


def _trim_pixmap(pixmap, *, pad: int = 16):
    import fitz

    bounds = ink_bounds(pixmap.samples, pixmap.width, pixmap.height, pixmap.n)
    if bounds is None:
        return pixmap
    x0, y0, x1, y1 = bounds
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(pixmap.width - 1, x1 + pad)
    y1 = min(pixmap.height - 1, y1 + pad)
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


def render_pdf_bytes(dashboard_html: str, *, dashboard_id: str) -> bytes:
    try:
        from weasyprint import CSS, HTML
    except ImportError as exc:
        raise RuntimeError("WeasyPrint is required for UPR visual export.") from exc

    width, page_height = _page_size(dashboard_id)
    pad = 16
    document_html = _wrap(dashboard_html, width)
    page_css = CSS(
        string=(
            f"@page {{ size: {width + pad * 2}px {page_height + pad * 2}px; margin: {pad}px; }}\n"
            "html, body { margin: 0; padding: 0; background: #fff; }"
        )
    )
    pdf_buffer = io.BytesIO()
    HTML(string=document_html, base_url=f"{_PLUGIN_DIR.resolve().as_posix()}/").write_pdf(
        pdf_buffer, stylesheets=[page_css], optimize_images=True
    )
    return pdf_buffer.getvalue()


def render_png(
    dashboard_html: str,
    output_path: Path,
    *,
    dashboard_id: str,
    scale: float = 2.0,
) -> Path:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF (fitz) is required for UPR visual PNG export.") from exc

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(stream=render_pdf_bytes(dashboard_html, dashboard_id=dashboard_id), filetype="pdf")
    try:
        page = doc[0]
        clip = _content_rect(page)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False, clip=clip)
        pixmap = _trim_pixmap(pixmap)
        pixmap.save(str(output_path))
    finally:
        doc.close()
    return output_path
