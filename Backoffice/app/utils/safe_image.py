"""Bounded image / PDF-render helpers (decompression-bomb and OCR resource limits).

Untrusted images and PDFs must be opened through :func:`open_image_safe` and
rendered through :func:`clamp_render_scale` / :func:`clamp_dpi` so a small
upload cannot allocate gigabytes of pixels. OCR calls go through
:func:`ocr_image_to_string`, which enforces a wall-clock timeout on tesseract.
"""

from __future__ import annotations

import io
import warnings
from typing import Any, BinaryIO, Tuple, Union

MAX_IMAGE_PIXELS = 50_000_000
MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_RENDER_PIXELS = 36_000_000
MAX_RENDER_DPI = 300
OCR_TIMEOUT_SECONDS = 60
OCR_MAX_PIXELS = 25_000_000


class UnsafeImageError(ValueError):
    """Image is malformed or exceeds the pixel/byte budget. Message is user-safe."""


def configure_pillow_limits(max_pixels: int = MAX_IMAGE_PIXELS) -> None:
    """Set Pillow's global bomb threshold and make its warning fatal."""
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = max_pixels
    warnings.simplefilter("error", Image.DecompressionBombWarning)


def open_image_safe(
    source: Union[bytes, bytearray, BinaryIO],
    *,
    max_pixels: int = MAX_IMAGE_PIXELS,
    max_bytes: int = MAX_IMAGE_BYTES,
) -> Any:
    """Open ``source`` (bytes or binary stream) and reject oversized or bomb-like images.

    The pixel count is checked from the header before any pixel data is decoded.
    Returns a lazily-loaded ``PIL.Image.Image``; callers should use it as a context manager.
    """
    from PIL import Image

    configure_pillow_limits(max_pixels)
    if isinstance(source, (bytes, bytearray)):
        if len(source) > max_bytes:
            raise UnsafeImageError("The image file is too large.")
        stream: BinaryIO = io.BytesIO(bytes(source))
    else:
        stream = source
    try:
        img = Image.open(stream)
    except Image.DecompressionBombError as exc:
        raise UnsafeImageError("The image dimensions are too large.") from exc
    except Image.DecompressionBombWarning as exc:
        raise UnsafeImageError("The image dimensions are too large.") from exc
    except Exception as exc:
        raise UnsafeImageError("File is not a valid image") from exc
    width, height = img.size
    if width <= 0 or height <= 0 or width * height > max_pixels:
        img.close()
        raise UnsafeImageError("The image dimensions are too large.")
    return img


def clamp_dpi(page_width_pt: float, page_height_pt: float, dpi: int, *, max_pixels: int = MAX_RENDER_PIXELS) -> int:
    """Return ``dpi`` reduced (never raised above MAX_RENDER_DPI) so the render stays within ``max_pixels``."""
    dpi = max(1, min(int(dpi), MAX_RENDER_DPI))
    width = max(float(page_width_pt), 1.0)
    height = max(float(page_height_pt), 1.0)
    pixels = (width * dpi / 72.0) * (height * dpi / 72.0)
    if pixels <= max_pixels:
        return dpi
    scaled = int(dpi * (max_pixels / pixels) ** 0.5)
    return max(1, scaled)


def clamp_render_scale(
    page_width_pt: float, page_height_pt: float, scale: float, *, max_pixels: int = MAX_RENDER_PIXELS
) -> float:
    """Return a zoom factor (1.0 == 72 dpi) reduced so the rendered page fits ``max_pixels``."""
    dpi = clamp_dpi(page_width_pt, page_height_pt, int(round(max(scale, 0.01) * 72)), max_pixels=max_pixels)
    return dpi / 72.0


def render_page_size(page: Any) -> Tuple[float, float]:
    rect = page.rect
    return float(rect.width or 1.0), float(rect.height or 1.0)


def ocr_image_to_string(image: Any, *, timeout: int = OCR_TIMEOUT_SECONDS, max_pixels: int = OCR_MAX_PIXELS, **kwargs: Any) -> str:
    """Run tesseract with a timeout, downscaling first when ``image`` exceeds ``max_pixels``."""
    import pytesseract
    from PIL import Image

    width, height = image.size
    if width * height > max_pixels:
        ratio = (max_pixels / float(width * height)) ** 0.5
        image = image.resize((max(1, int(width * ratio)), max(1, int(height * ratio))), Image.Resampling.LANCZOS)
    return pytesseract.image_to_string(image, timeout=timeout, **kwargs)
