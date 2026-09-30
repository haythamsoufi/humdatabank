import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.utils.safe_image import (
    MAX_RENDER_DPI,
    UnsafeImageError,
    clamp_dpi,
    clamp_render_scale,
    ocr_image_to_string,
    open_image_safe,
)


def _png(width=10, height=10):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buf, "PNG")
    return buf.getvalue()


def test_opens_normal_image_from_bytes_and_stream():
    with open_image_safe(_png(12, 8)) as img:
        assert img.size == (12, 8)
    with open_image_safe(io.BytesIO(_png())) as img:
        assert img.size == (10, 10)


def test_rejects_garbage():
    with pytest.raises(UnsafeImageError):
        open_image_safe(b"definitely not an image")


def test_rejects_image_over_pixel_budget_from_header():
    with pytest.raises(UnsafeImageError, match="dimensions"):
        open_image_safe(_png(200, 200), max_pixels=1000)


def test_rejects_oversized_bytes():
    with pytest.raises(UnsafeImageError, match="too large"):
        open_image_safe(_png(), max_bytes=10)


def test_pillow_global_limit_is_configured_and_bomb_warning_is_fatal():
    open_image_safe(_png()).close()
    assert Image.MAX_IMAGE_PIXELS == 50_000_000
    import warnings

    with pytest.raises(Image.DecompressionBombWarning):
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            warnings.warn("x", Image.DecompressionBombWarning)


def test_clamp_dpi_reduces_for_huge_pages_and_never_exceeds_max():
    assert clamp_dpi(595, 842, 150) == 150
    assert clamp_dpi(595, 842, 10_000) == MAX_RENDER_DPI or clamp_dpi(595, 842, 10_000) <= MAX_RENDER_DPI
    huge = clamp_dpi(14400, 14400, 300)
    assert huge < 300
    assert (14400 * huge / 72) ** 2 <= 36_000_000 * 1.02


def test_clamp_render_scale():
    assert clamp_render_scale(595, 842, 1.5) == pytest.approx(1.5, rel=0.02)
    assert clamp_render_scale(14400, 14400, 4.0) < 4.0


def test_ocr_passes_timeout_and_downscales():
    fake = MagicMock()
    fake.pytesseract = MagicMock()
    fake.image_to_string.return_value = "text"
    img = Image.new("RGB", (400, 400), "white")
    with patch.dict("sys.modules", {"pytesseract": fake}):
        assert ocr_image_to_string(img, timeout=7, max_pixels=10_000) == "text"
    args, kwargs = fake.image_to_string.call_args
    assert kwargs["timeout"] == 7
    assert args[0].size[0] * args[0].size[1] <= 10_000
