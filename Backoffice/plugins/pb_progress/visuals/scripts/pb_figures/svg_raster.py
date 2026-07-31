"""Rasterize SVG strings to PNG without a browser."""

from __future__ import annotations

from pathlib import Path


def _normalize_svg(svg: str) -> str:
    document = svg.strip()
    if 'xmlns="http://www.w3.org/2000/svg"' not in document:
        document = document.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
    return document


def _write_svg_png_cairosvg(
    svg: str,
    output_path: Path,
    *,
    width: int,
    height: int,
    scale: float,
) -> None:
    import cairosvg

    cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        write_to=str(output_path),
        output_width=max(1, int(width * scale)),
        output_height=max(1, int(height * scale)),
    )


def _write_svg_png_pymupdf(
    svg: str,
    output_path: Path,
    *,
    width: int,
    height: int,
    scale: float,
) -> None:
    import fitz

    target_width = max(1, int(width * scale))
    target_height = max(1, int(height * scale))
    doc = fitz.open(stream=svg.encode("utf-8"), filetype="svg")
    try:
        page = doc[0]
        rect = page.rect
        if rect.width <= 0 or rect.height <= 0:
            matrix = fitz.Matrix(scale, scale)
        else:
            matrix = fitz.Matrix(
                target_width / rect.width,
                target_height / rect.height,
            )
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        pixmap.save(str(output_path))
    finally:
        doc.close()


def write_svg_png(
    svg: str,
    output_path: Path,
    *,
    width: int,
    height: int,
    scale: float = 2.0,
) -> Path:
    """Write an SVG document to PNG, preferring CairoSVG with PyMuPDF fallback."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = _normalize_svg(svg)
    raster_errors: list[str] = []

    try:
        _write_svg_png_cairosvg(
            document,
            output_path,
            width=width,
            height=height,
            scale=scale,
        )
        return output_path
    except ImportError as exc:
        raster_errors.append(f"CairoSVG unavailable: {exc}")
    except OSError as exc:
        raster_errors.append(f"CairoSVG native libraries unavailable: {exc}")

    try:
        _write_svg_png_pymupdf(
            document,
            output_path,
            width=width,
            height=height,
            scale=scale,
        )
        return output_path
    except ImportError as exc:
        raster_errors.append(f"PyMuPDF unavailable: {exc}")
    except OSError as exc:
        raster_errors.append(f"PyMuPDF rasterization failed: {exc}")
    except Exception as exc:
        raster_errors.append(f"PyMuPDF rasterization failed: {exc}")

    detail = " ".join(raster_errors) or "unknown rasterization error"
    raise RuntimeError(
        "Could not rasterize SVG to PNG. Install Cairo for CairoSVG or PyMuPDF as fallback. "
        f"Details: {detail}"
    )
