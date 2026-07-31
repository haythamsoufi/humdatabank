"""Rasterize SVG strings to PNG without a browser."""

from __future__ import annotations

from pathlib import Path


def write_svg_png(
    svg: str,
    output_path: Path,
    *,
    width: int,
    height: int,
    scale: float = 2.0,
) -> Path:
    """Write an SVG document to a PNG file via CairoSVG."""
    try:
        import cairosvg
    except ImportError as exc:
        raise RuntimeError(
            "cairosvg is not installed. Add cairosvg to requirements and ensure "
            "Cairo libraries are available in the container image."
        ) from exc

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    document = svg.strip()
    if 'xmlns="http://www.w3.org/2000/svg"' not in document:
        document = document.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)

    cairosvg.svg2png(
        bytestring=document.encode("utf-8"),
        write_to=str(output_path),
        output_width=max(1, int(width * scale)),
        output_height=max(1, int(height * scale)),
    )
    return output_path
