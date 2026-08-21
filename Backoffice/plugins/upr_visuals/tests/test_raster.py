"""Unit tests for UPR visual PNG crop helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.upr_visuals.raster import (
    MAX_PNG_EDGE,
    PNG_EXPORT_SCALE,
    _css_for_print,
    _font_css,
    _page_size,
    _pdf_page_css,
    _png_render_scale,
    _rewrite_export_images,
    _stitch_pixmaps,
    _wrap,
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
def test_pdf_canvas_is_a4_landscape_for_single_chips():
    from plugins.upr_visuals.catalog import A4_PAGE_HEIGHT_PX, A4_PAGE_WIDTH_PX

    width, height = _page_size("strategic_priorities")
    assert width == A4_PAGE_WIDTH_PX
    assert height == A4_PAGE_HEIGHT_PX
    css = _pdf_page_css("strategic_priorities")
    assert "A4 landscape" in css
    assert "portrait" not in css
    assert "margin: 6mm" in css


@pytest.mark.unit
def test_combined_pdf_is_portrait_and_keeps_sections_together():
    from plugins.upr_visuals.catalog import A4_PORTRAIT_HEIGHT_PX, A4_PORTRAIT_WIDTH_PX

    width, height = _page_size("combined")
    assert width == A4_PORTRAIT_WIDTH_PX
    assert height == A4_PORTRAIT_HEIGHT_PX
    assert width < height
    css = _pdf_page_css("combined")
    assert "A4 portrait" in css
    assert "margin: 10mm 0" in css
    assert "margin: 0mm 0mm 18mm" in css
    assert "page-break-inside: avoid" in css
    assert "upr-combined-section--finance" in css
    assert "upr-combined-section--indicators" in css
    assert "upr-combined-section--page-start" in css
    assert "upr-bar-group" in css
    assert "upr-fin-cover" in css
    assert "table-layout: fixed" in css
    assert ".upr-reach-row" in css
    assert "element(cover-footer)" in css
    assert "@page :first" in css
    assert "position: running(cover-footer)" in css
    wrapped = _wrap('<div class="upr-combined-section">x</div>', dashboard_id="combined")
    assert "page-break-inside: avoid" in wrapped


@pytest.mark.unit
def test_combined_finance_scales_as_a_unit():
    css = (Path(__file__).resolve().parents[1] / "static" / "css" / "upr-visuals.css").read_text(
        encoding="utf-8"
    )
    assert ".upr-combined-section--finance .upr-block--finance" not in css
    assert ".upr-combined-section--finance .upr-fin-net td" not in css
    assert ".upr-combined-section--finance .upr-fin-hero" not in css
    wrapped = _wrap('<div class="upr-combined-section--finance">x</div>', dashboard_id="combined")
    assert ".upr-combined-section--finance .upr-block--finance { font-size: 0.78rem; }" in wrapped
    assert ".upr-combined-section--finance .upr-block--finance { font-size: 0.78rem; }" not in _wrap(
        "<div>x</div>", dashboard_id="financial"
    )


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


class _FakeRect:
    def __init__(self, width: float, height: float):
        self.width = width
        self.height = height


class _FakePage:
    def __init__(self, width: float, height: float):
        self.rect = _FakeRect(width, height)


@pytest.mark.unit
def test_png_render_scale_keeps_single_page_at_export_scale():
    doc = [_FakePage(842, 595)]
    assert _png_render_scale(doc, scale=8.0) == 8.0


@pytest.mark.unit
def test_png_render_scale_caps_stitched_combined_height():
    pages = 6
    page_h = 842.0
    doc = [_FakePage(595, page_h) for _ in range(pages)]
    scale = _png_render_scale(doc, scale=8.0)
    assert scale < 8.0
    assert pages * page_h * scale <= MAX_PNG_EDGE
    assert MAX_PNG_EDGE == 16384


@pytest.mark.unit
def test_resolve_export_image_src_maps_plugin_static():
    src = resolve_export_image_src("/upr-visuals/static/icons/eo-emergency.png")
    assert src.startswith("file:")
    assert src.endswith("eo-emergency.png")
    assert resolve_export_image_src("data:image/png;base64,abc") == "data:image/png;base64,abc"
    remote = "https://example.test/icon.png"
    assert resolve_export_image_src(remote) == remote
    logo = resolve_export_image_src("/static/IFRC_logo_square.svg")
    assert logo.startswith("file:")
    assert logo.lower().endswith("ifrc_logo_square.svg")


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
