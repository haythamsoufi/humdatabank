"""Unit tests for UPR visual PNG crop helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import plugins.upr_visuals.raster as _raster_mod
from plugins.upr_visuals.raster import (
    MAX_PNG_EDGE,
    PNG_EXPORT_SCALE,
    _css_for_print,
    summarize_child_log,
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
    assert "font-style: italic" in css
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
def test_print_css_drops_keyframes():
    css = (
        ".upr-dot { width: 1rem; }\n"
        "@keyframes upr-vis-narrative-slide {\n"
        "  0% { left: -38%; }\n"
        "  100% { left: 100%; }\n"
        "}\n"
        ".upr-bar { display: flex; }\n"
    )
    printed = _css_for_print(css)
    assert ".upr-dot { width: 1rem; }" in printed
    assert ".upr-bar { display: flex; }" in printed
    assert "@keyframes" not in printed
    assert "upr-vis-narrative-slide" not in printed


@pytest.mark.unit
def test_print_css_drops_weasyprint_unsupported_decls():
    css = (
        ".upr-vis-page { background: #fff; box-shadow: 0 0 0 1px #ccc; }\n"
        ".upr-visual-report__body { overflow-x: hidden; min-width: 0; }\n"
    )
    printed = _css_for_print(css)
    assert "box-shadow" not in printed
    assert "overflow-x" not in printed
    assert "background: #fff" in printed
    assert "min-width: 0" in printed


@pytest.mark.unit
def test_rtl_print_css_keeps_fixed_columns_and_hidden_labels():
    from plugins.upr_visuals.raster import _rtl_print_css

    css = _rtl_print_css("ar")
    assert "table-layout: fixed" in css
    assert "table-layout: auto" not in css
    assert "overflow: hidden" in css
    assert "direction: ltr" in css
    assert "upr-fin-grid--half .upr-fin-col-source-label { width: 50%; }" in css
    assert "justify-content: flex-end" in css
    assert ".upr-bars .upr-bar-value" in css
    assert ".upr-fin-net .upr-bar-value" in css
    assert ".upr-fin-grid .upr-bar-value" in css
    assert "order: -1" in css
    assert "upr-support-table" in css
    assert "html[dir=\"rtl\"] .upr-block--support .upr-kpi__label" in css
    assert "html[dir=\"rtl\"] .upr-block--support .upr-kpi__value" in css
    assert "html[dir=\"rtl\"] .upr-block__title" in css
    assert "html[dir=\"rtl\"] .upr-block__title--center" in css
    assert "html[dir=\"rtl\"] .upr-fin-net .upr-not-reported" in css
    assert "html[dir=\"rtl\"] .upr-bars .upr-bar-yes" in css
    assert "html[dir=\"rtl\"] .upr-amt" in css
    assert "html[dir=\"rtl\"] .upr-support-table td.upr-support-total" in css
    assert "html[dir=\"rtl\"] .upr-support-table tbody td.upr-num .upr-amt" in css
    total_amt = css.split('html[dir="rtl"] .upr-support-total .upr-amt', 1)[1].split("}", 1)[0]
    assert "justify-content: flex-end" in total_amt
    assert "overflow: visible" in css.split(
        'html[dir="rtl"] .upr-support-table td.upr-support-total {', 1
    )[1].split("}", 1)[0]
    assert "unicode-bidi: isolate" in css
    assert "upr-support-col-num { width: 16%; }" in css
    title_center = css.split('html[dir="rtl"] .upr-block__title,', 1)[1].split("}", 1)[0]
    assert "text-align: center" in title_center
    label_right = css.split('html[dir="rtl"] .upr-fin-grid td.upr-bar-label,', 1)[1].split("}", 1)[0]
    assert "text-align: right" in label_right
    metric_left = css.split('html[dir="rtl"] .upr-fin-net__metric {', 1)[1].split("}", 1)[0]
    assert "text-align: left" in metric_left
    bars_label = css.split('html[dir="rtl"] .upr-block--bars .upr-bar-label,', 1)[1].split("}", 1)[0]
    assert "text-align: left" in bars_label
    not_reported = css.split("html[dir=\"rtl\"] .upr-fin-net .upr-not-reported", 1)[1].split("}", 1)[0]
    assert "text-align: right" in not_reported
    assert "align-items: center" in css
    assert "html[dir=\"rtl\"] .upr-combined-section > .upr-block--reach" not in css
    assert not _rtl_print_css("en")


@pytest.mark.unit
def test_print_css_drops_webkit_scrollbar_and_embed_chrome():
    from plugins.upr_visuals.raster import _print_css

    printed = _print_css()
    assert "::-webkit-scrollbar" not in printed
    assert ".upr-visuals-embed__tabs" not in printed
    assert ".upr-vis-skel" not in printed
    assert ".upr-dashboard" in printed
    assert 'font-family: "Open Sans", "Segoe UI", sans-serif' in printed


@pytest.mark.unit
def test_print_css_keeps_dashboard_font_when_grouped_with_embed_chrome():
    css = (
        ".upr-visual-report,\n"
        ".upr-dashboard,\n"
        ".upr-visuals-embed__toolbar,\n"
        ".upr-visuals-embed__tab {\n"
        '  font-family: "Open Sans", sans-serif;\n'
        "}\n"
        ".upr-visuals-embed__tabs { display: flex; }\n"
    )
    printed = _css_for_print(css)
    assert 'font-family: "Open Sans"' in printed
    assert ".upr-dashboard" in printed
    assert ".upr-visual-report" in printed
    assert ".upr-visuals-embed__toolbar" not in printed
    assert ".upr-visuals-embed__tab" not in printed
    assert ".upr-visuals-embed__tabs" not in printed


@pytest.mark.unit
def test_wrap_sets_document_open_sans():
    html = _wrap('<div class="upr-dashboard">x</div>', dashboard_id="combined")
    assert "html, body { font-family: \"Open Sans\", \"Segoe UI\", sans-serif; }" in html
    assert "html, body, table, th, td, p, h1, h2, h3, h4, li" not in html
    page = _pdf_page_css("combined")
    assert "html, body { font-family: \"Open Sans\", \"Segoe UI\", sans-serif; }" in page


@pytest.mark.unit
def test_arabic_export_uses_tajawal_body_font(monkeypatch):
    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: "ar")
    from plugins.upr_visuals.raster import _document_body_font_css, _pdf_page_css, _wrap

    assert "Tajawal" in _document_body_font_css("ar")
    assert "p, h1" not in _document_body_font_css("ar")
    html = _wrap('<div class="upr-dashboard">x</div>', dashboard_id="combined")
    assert 'font-family: "Tajawal", "Arial", "Segoe UI", sans-serif' in html
    assert ".upr-arabic-font *" in html
    assert "@bottom-center" in html
    page = _pdf_page_css("combined")
    assert "Tajawal" in page
    assert ".upr-arabic-font *" in page


@pytest.mark.unit
def test_summarize_child_log_drops_weasyprint_noise():
    raw = (
        "Ignored `box-shadow: none` at 1670:188, unknown property.\n"
        "INFO plugins.upr_visuals.raster: UPR PNG done reach (56204 bytes)\n"
        "UPR PNG done reach (56204 bytes)\n"
        "OSError: broken pipe\n"
    )
    assert summarize_child_log(raw) == "OSError: broken pipe"
    assert summarize_child_log("Ignored `overflow-x: hidden` at 260:3, unknown property.") == ""


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
    assert ".upr-combined-section--reach{ padding-left:0; padding-right:0; }" in css
    assert ".upr-combined-section > .upr-block--reach{" in css
    assert "margin-left:-8mm" not in css
    assert "element(cover-footer)" in css
    assert "@page :first" in css
    assert "position: running(cover-footer)" in css
    wrapped = _wrap('<div class="upr-combined-section">x</div>', dashboard_id="combined")
    assert "page-break-inside: avoid" in wrapped
    assert "@keyframes" not in wrapped


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


@pytest.mark.unit
def test_stitch_pixmaps_pads_narrower_page():
    import fitz

    top = fitz.Pixmap(fitz.csRGB, 4, 1, bytes([10] * (4 * 1 * 3)), 0)
    bottom = fitz.Pixmap(fitz.csRGB, 2, 1, bytes([40] * (2 * 1 * 3)), 0)
    stacked = _stitch_pixmaps([top, bottom])
    assert stacked.width == 4
    assert stacked.height == 2
    row = stacked.samples[4 * 3 :]
    assert bytes(row[:6]) == bytes([40] * 6)
    assert bytes(row[6:]) == bytes([255] * 6)


@pytest.mark.unit
def test_render_png_from_pdf_writes_png(tmp_path):
    import fitz

    from plugins.upr_visuals.raster import render_png_from_pdf

    doc = fitz.open()
    page = doc.new_page(width=80, height=60)
    page.draw_rect(page.rect, color=(1, 0, 0), fill=(1, 0, 0))
    pdf_bytes = doc.tobytes()
    doc.close()
    out = tmp_path / "out.png"
    render_png_from_pdf(pdf_bytes, out, dashboard_id="combined", scale=2.0)
    assert out.is_file()
    assert out.stat().st_size > 0
    pix = fitz.Pixmap(str(out))
    assert pix.width > 0
    assert pix.height > 0


@pytest.mark.unit
def test_render_png_job_file_uses_pdf_path(tmp_path, monkeypatch):
    pdf_path = tmp_path / "in.pdf"
    pdf_path.write_bytes(b"%PDF")
    out = tmp_path / "out.png"
    job = tmp_path / "job.json"
    job.write_text(
        json.dumps(
            {
                "pdf_path": str(pdf_path),
                "output_path": str(out),
                "dashboard_id": "combined",
                "scale": 8.0,
            }
        ),
        encoding="utf-8",
    )

    def fake(pdf_bytes, path, dashboard_id="combined", scale=8.0):
        assert pdf_bytes == b"%PDF"
        assert dashboard_id == "combined"
        assert scale == 8.0
        Path(path).write_bytes(b"png")

    monkeypatch.setattr(_raster_mod, "render_png_from_pdf", fake)
    _raster_mod.render_png_job_file(job)
    assert out.read_bytes() == b"png"


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
def test_render_png_job_file_calls_render_png(tmp_path, monkeypatch):
    html_path = tmp_path / "in.html"
    html_path.write_text("<html/>", encoding="utf-8")
    out = tmp_path / "out.png"
    job = tmp_path / "job.json"
    job.write_text(
        json.dumps(
            {
                "html_path": str(html_path),
                "output_path": str(out),
                "dashboard_id": "combined",
                "scale": 8.0,
            }
        ),
        encoding="utf-8",
    )

    def fake(html, path, dashboard_id="combined", scale=8.0):
        Path(path).write_bytes(b"png")
        assert html == "<html/>"
        assert dashboard_id == "combined"
        assert scale == 8.0

    monkeypatch.setattr(_raster_mod, "render_png", fake)
    _raster_mod.render_png_job_file(job)
    assert out.read_bytes() == b"png"


@pytest.mark.unit
def test_render_png_isolated_raises_on_child_crash(tmp_path, monkeypatch):
    class Result:
        returncode = 3221225477
        stdout = ""
        stderr = ""

    captured = {}

    def fake_run(*_a, **kwargs):
        captured["env"] = kwargs.get("env") or {}
        return Result()

    monkeypatch.setattr(_raster_mod.subprocess, "run", fake_run)
    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: "ar")
    with pytest.raises(RuntimeError, match="crashed"):
        _raster_mod.render_png_isolated("<html/>", tmp_path / "x.png", dashboard_id="combined")
    assert captured["env"].get("UPR_VISUALS_LANG") == "ar"


@pytest.mark.unit
def test_render_png_isolated_raises_on_timeout(tmp_path, monkeypatch):
    def boom(*_a, **_k):
        raise _raster_mod.subprocess.TimeoutExpired(cmd="png", timeout=1)

    monkeypatch.setattr(_raster_mod.subprocess, "run", boom)
    with pytest.raises(TimeoutError, match="timed out"):
        _raster_mod.render_png_isolated(
            "<html/>", tmp_path / "x.png", dashboard_id="combined", timeout=1
        )


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


class _FakeHTTPResponse:
    def __init__(self, data: bytes):
        self._data = data

    def read(self, _n: int = -1) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


@pytest.mark.unit
def test_resolve_export_image_src_inlines_trusted_github(monkeypatch):
    """NS logo and KPI icon HTTPS URLs from the FDRS GitHub CDN are inlined as data URIs."""
    fake_png = b"\x89PNG\r\n\x1a\n"
    monkeypatch.setattr(_raster_mod, "urlopen", lambda url, timeout=10: _FakeHTTPResponse(fake_png))

    ns_logo = "https://raw.githubusercontent.com/FDRS-ifrc/general/main/ns_logos/AFG.png"
    result = resolve_export_image_src(ns_logo)
    assert result.startswith("data:image/png;base64,")

    kpi_icon = "https://raw.githubusercontent.com/FDRS-ifrc/general/main/ifrc_icons/IFRC-icons-colour_Unity.png"
    assert resolve_export_image_src(kpi_icon).startswith("data:image/png;base64,")

    # Untrusted HTTPS still passes through unchanged (blocked later by _restricted_url_fetcher)
    untrusted = "https://example.test/icon.png"
    assert resolve_export_image_src(untrusted) == untrusted

    from plugins.upr_visuals.raster import _restricted_url_fetcher

    with pytest.raises(ValueError, match="Blocked export URL"):
        _restricted_url_fetcher("https://fonts.googleapis.com/css2?family=Tajawal")


@pytest.mark.unit
def test_resolve_export_image_src_trusted_github_fetch_failure_falls_back(monkeypatch):
    """A network error fetching a trusted URL returns the original URL (logged, not raised)."""
    monkeypatch.setattr(_raster_mod, "urlopen", lambda url, timeout=10: (_ for _ in ()).throw(OSError("timeout")))
    ns_logo = "https://raw.githubusercontent.com/FDRS-ifrc/general/main/ns_logos/AFG.png"
    assert resolve_export_image_src(ns_logo) == ns_logo


@pytest.mark.unit
def test_resolve_export_image_src_inlines_ns_logo_api(monkeypatch):
    monkeypatch.setattr(
        "app.services.platform.storage_service.download",
        lambda category, rel: b"\x89PNG\r\n\x1a\n",
    )
    src = resolve_export_image_src("/api/v1/uploads/ns/uganda.png")
    assert src.startswith("data:image/png;base64,")
    assert resolve_export_image_src("/api/v1/uploads/ns/../secret.png") == src
    monkeypatch.setattr(
        "app.services.platform.storage_service.download",
        lambda category, rel: (_ for _ in ()).throw(FileNotFoundError("missing")),
    )
    assert resolve_export_image_src("/api/v1/uploads/ns/missing.png") == ""


@pytest.mark.unit
def test_rewrite_export_images_rewrites_plugin_src():
    html = '<img src="/upr-visuals/static/icons/eo-emergency.png" alt="">'
    rewritten = _rewrite_export_images(html)
    assert "file:" in rewritten
    assert "eo-emergency.png" in rewritten
    svg = '<svg><image href="/upr-visuals/static/icons/eo-emergency.png"/></svg>'
    rewritten_svg = _rewrite_export_images(svg)
    assert "file:" in rewritten_svg
    assert "eo-emergency.png" in rewritten_svg


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


@pytest.mark.unit
def test_render_pdf_bytes_subsets_fonts_by_default(monkeypatch):
    captured = {}

    class FakeCSS:
        def __init__(self, string=""):
            pass

    class FakeHTML:
        def __init__(self, **_kwargs):
            pass

        def write_pdf(self, buf, **kwargs):
            captured.update(kwargs)
            buf.write(b"%PDF-1.4")

    monkeypatch.setattr("weasyprint.CSS", FakeCSS)
    monkeypatch.setattr("weasyprint.HTML", FakeHTML)
    from plugins.upr_visuals.raster import render_pdf_bytes

    render_pdf_bytes("<div class='upr-dashboard'/>", dashboard_id="combined")
    assert captured.get("full_fonts") is False


@pytest.mark.unit
def test_render_pdf_bytes_can_embed_full_fonts(monkeypatch):
    captured = {}

    class FakeCSS:
        def __init__(self, string=""):
            pass

    class FakeHTML:
        def __init__(self, **_kwargs):
            pass

        def write_pdf(self, buf, **kwargs):
            captured.update(kwargs)
            buf.write(b"%PDF-1.4")

    monkeypatch.setattr("weasyprint.CSS", FakeCSS)
    monkeypatch.setattr("weasyprint.HTML", FakeHTML)
    from plugins.upr_visuals.raster import render_pdf_bytes

    render_pdf_bytes("<div/>", dashboard_id="combined", full_fonts=True)
    assert captured.get("full_fonts") is True


def _reach_preview_html(*, rtl: bool = False) -> str:
    direction = " dir='rtl' lang='ar'" if rtl else ""
    return (
        f"<div class='upr-dashboard upr-dashboard--combined'{direction}>"
        "<div class='upr-combined-body'>"
        "<div class='upr-combined-section upr-combined-section--before-reach'>"
        "<p>KPIs</p></div>"
        "<div class='upr-combined-section upr-combined-section--reach'>"
        "<section class='upr-block upr-block--reach'>"
        "<h2 class='upr-block__title'>PEOPLE REACHED</h2>"
        "</section></div></div></div>"
    )


def _widest_reach_band(pdf_bytes: bytes):
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc[0]
        bands = []
        for drawing in page.get_drawings():
            fill = drawing.get("fill")
            if not fill or len(fill) < 3:
                continue
            if any(channel < 0.9 or channel > 0.98 for channel in fill[:3]):
                continue
            rect = fitz.Rect(drawing["rect"])
            if rect.width > page.rect.width * 0.5:
                bands.append(rect)
        assert bands, "expected a People reached grey band"
        return page.rect, max(bands, key=lambda item: item.width)
    finally:
        doc.close()


@pytest.mark.unit
@pytest.mark.parametrize("lang", ["en", "ar"])
def test_combined_reach_band_bleeds_after_narrative_merge(monkeypatch, lang):
    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: lang)
    monkeypatch.setattr("plugins.upr_visuals.i18n.is_rtl", lambda lang_code=None: lang == "ar")
    from plugins.upr_visuals.idml.narrative_pdf import merge_report_pdfs
    from plugins.upr_visuals.raster import render_pdf_bytes

    pdf = render_pdf_bytes(_reach_preview_html(rtl=lang == "ar"), dashboard_id="combined")
    page_rect, band = _widest_reach_band(pdf)
    assert band.x0 <= 1.5
    assert page_rect.width - band.x1 <= 1.5

    merged = merge_report_pdfs(pdf, pdf)
    page_rect, band = _widest_reach_band(merged)
    assert band.x0 <= 1.5
    assert page_rect.width - band.x1 <= 1.5
