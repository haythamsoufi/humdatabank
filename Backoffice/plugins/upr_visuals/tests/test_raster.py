"""Unit tests for UPR visual PNG crop helpers."""

from __future__ import annotations

import pytest

from plugins.upr_visuals.raster import _page_size, ink_bounds


@pytest.mark.unit
def test_pdf_canvas_is_taller_than_catalog_but_png_crops_to_ink():
    width, height = _page_size("strategic_priorities")
    assert width == 1100
    assert height >= 1400 * 2
    combined_w, combined_h = _page_size("combined")
    assert combined_w == 1100
    assert combined_h >= 8000


@pytest.mark.unit
def test_ink_bounds_trims_bottom_whitespace():
    width, height, n = 4, 6, 3
    samples = bytearray([255] * (width * height * n))
    # Dark pixel near the top-left; rest of canvas is white.
    samples[1 * width * n + 1 * n] = 10
    samples[1 * width * n + 1 * n + 1] = 10
    samples[1 * width * n + 1 * n + 2] = 10
    bounds = ink_bounds(bytes(samples), width, height, n)
    assert bounds == (1, 1, 1, 1)


@pytest.mark.unit
def test_ink_bounds_empty_white_image():
    samples = bytes([255] * (3 * 3 * 3))
    assert ink_bounds(samples, 3, 3, 3) is None


@pytest.mark.unit
def test_trim_pixmap_drops_white_margin():
    import fitz

    from plugins.upr_visuals.raster import _trim_pixmap

    width, height = 20, 30
    samples = bytearray([255] * (width * height * 3))
    index = (4 * width + 3) * 3
    samples[index : index + 3] = b"\x00\x00\x00"
    pixmap = fitz.Pixmap(fitz.csRGB, width, height, bytes(samples), 0)
    trimmed = _trim_pixmap(pixmap, pad=2)
    assert trimmed.width == 5
    assert trimmed.height == 5
