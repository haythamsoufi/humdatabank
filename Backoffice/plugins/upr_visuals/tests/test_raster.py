"""Unit tests for UPR visual PNG crop helpers."""

from __future__ import annotations

import pytest

from plugins.upr_visuals.raster import (
    PNG_EXPORT_SCALE,
    _css_for_print,
    _font_css,
    _page_size,
    _rewrite_export_images,
    _stitch_pixmaps,
    ink_bounds,
    resolve_export_image_src,
)


@pytest.mark.unit
def test_export_fonts_are_inlined():
    css = _font_css()
    assert "file:" in css
    assert "Open Sans" in css
    assert "OpenSans-Regular" in css
    assert PNG_EXPORT_SCALE >= 8


@pytest.mark.unit
def test_export_open_sans_files_are_real_ttf():
    from pathlib import Path

    from plugins.upr_visuals.raster import _APP_FONTS_DIR

    for name in ("OpenSans-Regular.ttf", "OpenSans-Bold.ttf"):
        path = Path(_APP_FONTS_DIR) / name
        header = path.read_bytes()[:4]
        assert header in {b"\x00\x01\x00\x00", b"OTTO"}, f"{name} is not a TTF/OTF (got {header!r})"


@pytest.mark.unit
def test_print_css_drops_media_queries():
    css = (
        ".upr-bar { display: flex; }\n"
        "@media screen and (max-width: 720px) {\n"
        "  .upr-bar { display: block; }\n"
        "}\n"
        ".upr-dot { width: 1rem; }\n"
    )
    printed = _css_for_print(css)
    assert ".upr-bar { display: flex; }" in printed
    assert ".upr-dot { width: 1rem; }" in printed
    assert "@media" not in printed
    assert "display: block" not in printed


@pytest.mark.unit
def test_pdf_canvas_is_a4_landscape():
    from plugins.upr_visuals.catalog import A4_PAGE_HEIGHT_PX, A4_PAGE_WIDTH_PX

    width, height = _page_size("strategic_priorities")
    assert width == A4_PAGE_WIDTH_PX
    assert height == A4_PAGE_HEIGHT_PX
    combined_w, combined_h = _page_size("combined")
    assert combined_w == A4_PAGE_WIDTH_PX
    assert combined_h == A4_PAGE_HEIGHT_PX


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
def test_stitch_pixmaps_stacks_pages():
    import fitz

    top = fitz.Pixmap(fitz.csRGB, 4, 2, bytes([10] * (4 * 2 * 3)), 0)
    bottom = fitz.Pixmap(fitz.csRGB, 4, 3, bytes([40] * (4 * 3 * 3)), 0)
    stacked = _stitch_pixmaps([top, bottom])
    assert stacked.width == 4
    assert stacked.height == 5
    assert stacked.samples[0] == 10
    assert stacked.samples[-1] == 40


@pytest.mark.unit
def test_resolve_export_image_src_maps_plugin_static():
    src = resolve_export_image_src("/upr-visuals/static/icons/eo-emergency.png")
    assert src.startswith("file:")
    assert src.endswith("eo-emergency.png")
    assert resolve_export_image_src("data:image/png;base64,abc") == "data:image/png;base64,abc"
    remote = "https://example.test/icon.png"
    assert resolve_export_image_src(remote) == remote


@pytest.mark.unit
def test_rewrite_export_images_rewrites_plugin_src():
    html = '<img src="/upr-visuals/static/icons/eo-emergency.png" alt="">'
    rewritten = _rewrite_export_images(html)
    assert "file:" in rewritten
    assert "eo-emergency.png" in rewritten


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
    full_width = _trim_pixmap(pixmap, pad=2, keep_width=True)
    assert full_width.width == width
    assert full_width.height == 5
