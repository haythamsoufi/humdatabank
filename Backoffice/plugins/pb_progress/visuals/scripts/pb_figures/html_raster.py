"""Rasterize dashboard HTML to PNG via WeasyPrint + PyMuPDF."""

from __future__ import annotations

import io
from pathlib import Path

_DASHBOARD_CSS_PATH = Path(__file__).parent / "static" / "dashboard.css"


def _dashboard_css() -> str:
    return _DASHBOARD_CSS_PATH.read_text(encoding="utf-8")


def _wrap_dashboard_html(dashboard_html: str, *, language: str) -> str:
    del language
    from .font_faces import open_sans_face_css, tajawal_face_css

    font_css = f"{open_sans_face_css(inline=False)}\n{tajawal_face_css(inline=False)}"
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<style>{font_css}\n{_dashboard_css()}</style></head>"
        f"<body>{dashboard_html}</body></html>"
    )


def render_dashboard_png(
    dashboard_html: str,
    output_path: Path,
    *,
    width: int,
    height: int,
    scale: float = 2.0,
    base_url: Path | str,
    language: str = "English",
) -> Path:
    """Render embeddable dashboard HTML to a PNG file."""
    try:
        from weasyprint import CSS, HTML
    except ImportError as exc:
        raise RuntimeError(
            "WeasyPrint is not installed. It is required for P&B dashboard PNG export."
        ) from exc

    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF (fitz) is not installed.") from exc

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    document_html = _wrap_dashboard_html(dashboard_html, language=language)
    page_height = max(height, 200)
    page_css = CSS(
        string=(
            f"@page {{ size: {width}px {page_height}px; margin: 0; }}\n"
            "html, body { margin: 0; padding: 0; background: #fff; }"
        )
    )

    pdf_buffer = io.BytesIO()
    HTML(
        string=document_html,
        base_url=f"{Path(base_url).resolve().as_posix()}/",
    ).write_pdf(pdf_buffer, stylesheets=[page_css], optimize_images=True)

    doc = fitz.open(stream=pdf_buffer.getvalue(), filetype="pdf")
    try:
        page = doc[0]
        matrix = fitz.Matrix(scale, scale)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        pixmap.save(str(output_path))
    finally:
        doc.close()

    return output_path
