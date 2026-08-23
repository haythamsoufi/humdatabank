"""WeasyPrint narrative pages that match the IDML Word styles, merged after visuals."""

from __future__ import annotations

from html import escape
from pathlib import Path

from plugins.upr_visuals.errors import UprVisualsError
from plugins.upr_visuals.idml.constants import _STYLE_RUNS
from plugins.upr_visuals.idml.narrative_style import folio_label, folio_text
from plugins.upr_visuals.raster import _PLUGIN_FONTS_DIR

_APP_FONTS_DIR = Path(__file__).resolve().parents[3] / "app" / "static" / "fonts"


def _run_html(run: dict, *, style_name: str) -> str:
    from plugins.upr_visuals.idml.word_reader import safe_export_href

    text = escape(str(run.get("text") or ""))
    if not text:
        return ""
    href = safe_export_href(run.get("href"))
    base = _STYLE_RUNS.get(style_name) or _STYLE_RUNS["Body"]
    bold = bool(run.get("bold")) and style_name != "AdditionalHead"
    if style_name == "ContactName":
        bold = True
    cls = "upr-nar-run"
    if bold or base["style"] == "Bold":
        cls += " is-bold"
    if href:
        return f'<a class="{cls} is-link" href="{escape(href, quote=True)}">{text}</a>'
    return f'<span class="{cls}">{text}</span>'


def _para_html(para: dict) -> str:
    if para.get("kind") == "table":
        return _table_html(para.get("rows") or [])
    style_name = para.get("style") or "Body"
    runs = para.get("runs") or [{"text": para.get("text") or "", "href": "", "bold": False}]
    inner = "".join(_run_html(run, style_name=style_name) for run in runs) or "&nbsp;"
    if style_name == "SourceItem" and not inner.startswith("•"):
        inner = f"• {inner}"
    return f'<p class="upr-nar-p upr-nar-p--{style_name}">{inner}</p>'


def _cell_html(paras: list[dict], *, label: bool) -> str:
    if not paras:
        return "&nbsp;"
    parts: list[str] = []
    for para in paras:
        runs = para.get("runs") or [{"text": para.get("text") or "", "href": "", "bold": False}]
        bits: list[str] = []
        for run in runs:
            text = escape(str(run.get("text") or ""))
            if not text:
                continue
            href = (run.get("href") or "").strip()
            if href and not label:
                bits.append(f'<a class="upr-nar-run is-link" href="{escape(href, quote=True)}">{text}</a>')
            else:
                bits.append(text)
        parts.append("".join(bits) or "&nbsp;")
    return "<br/>".join(parts)


def _table_html(rows: list[list[list[dict]]]) -> str:
    if not rows:
        return ""
    body: list[str] = []
    two = max((len(row) for row in rows), default=0) == 2
    for row in rows:
        cells = list(row)
        if two and len(cells) < 2:
            cells.append([])
        if two:
            body.append(
                "<tr>"
                f"<th>{_cell_html(cells[0], label=True)}</th>"
                f"<td>{_cell_html(cells[1], label=False)}</td>"
                "</tr>"
            )
        else:
            body.append("<tr>" + "".join(f"<td>{_cell_html(cell, label=False)}</td>" for cell in cells) + "</tr>")
    return f'<div class="upr-nar-table-wrap"><table class="upr-nar-table">{"".join(body)}</table></div>'


def _narrative_css() -> str:
    from plugins.upr_visuals.i18n import current_export_language, rtl_css, uses_arabic_font
    from plugins.upr_visuals.typography import (
        ARABIC_NUMBER_STACK,
        LATIN_NUMBER_STACK,
        print_typography_css,
    )

    lang = current_export_language()
    heading_stack = ARABIC_NUMBER_STACK if uses_arabic_font(lang) else LATIN_NUMBER_STACK
    return f"""
{print_typography_css(lang)}
{rtl_css(lang)}
@page {{
  size: A4;
  margin: 32pt 34pt 40pt 34pt;
}}
html, body {{
  margin: 0;
  padding: 0;
  color: #000;
  font-size: 10pt;
  line-height: 13.5pt;
}}
.upr-nar-p {{ margin: 0 0 8.5pt; }}
.upr-nar-p--QHeading {{
  font-family: {heading_stack}; font-weight: 700; font-size: 20pt;
  line-height: 24pt; color: #ef3340; margin: 4pt 0 12pt;
}}
.upr-nar-p--SectionHead {{
  font-family: {heading_stack}; font-weight: 700; font-size: 15pt;
  line-height: 18pt; color: #011e41; margin: 16pt 0 6pt;
}}
.upr-nar-p--TopicHead {{
  font-family: {heading_stack}; font-weight: 700; font-size: 14pt;
  line-height: 17pt; color: #1b365d; margin: 12pt 0 6pt;
}}
.upr-nar-p--BandHead {{
  font-family: {heading_stack}; font-weight: 700; font-size: 16pt;
  line-height: 20pt; color: #1b365d; margin: 14pt 0 10pt;
  border-bottom: 2pt solid #1b365d; padding-bottom: 3pt;
}}
.upr-nar-p--Subhead {{
  font-weight: 700; font-size: 10pt; line-height: 13.5pt; margin: 10pt 0 6pt;
}}
.upr-nar-p--Body {{ text-align: justify; }}
.upr-nar-p--Blank {{ margin: 0 0 4pt; line-height: 12pt; min-height: 12pt; }}
.upr-nar-p--AdditionalHead {{
  font-family: {heading_stack}; font-weight: 700; font-size: 9.5pt;
  line-height: 12pt; margin: 8pt 0 10pt;
}}
.upr-nar-p--SourceItem {{ font-size: 9.5pt; line-height: 13pt; margin: 0 0 6pt; }}
.upr-nar-p--ContactHead {{
  font-weight: 700; font-size: 10pt; line-height: 13pt; color: #ef3340; margin: 16pt 0 10pt;
}}
.upr-nar-p--ContactName {{ font-weight: 700; font-size: 9.5pt; line-height: 13pt; margin: 10pt 0 1pt; }}
.upr-nar-p--ContactDetail {{ font-size: 9.5pt; line-height: 13pt; margin: 0 0 1pt; }}
.upr-nar-run.is-bold {{ font-weight: 700; }}
.upr-nar-run.is-link {{ color: #ef3340; text-decoration: underline; }}
.upr-nar-table-wrap {{
  break-inside: avoid;
  page-break-inside: avoid;
}}
.upr-nar-table {{
  width: 100%;
  border-collapse: collapse;
  margin: 0 0 12pt;
  font-size: 9pt;
  break-inside: avoid;
  page-break-inside: avoid;
}}
.upr-nar-table tr {{
  break-inside: avoid;
  page-break-inside: avoid;
}}
.upr-nar-table th, .upr-nar-table td {{
  border: 0.4pt solid #000;
  padding: 4pt 6pt;
  vertical-align: middle;
}}
.upr-nar-table th {{
  width: 36%;
  background: #011e41;
  color: #fff;
  font-weight: 700;
  text-align: start;
}}
.upr-nar-table td {{ background: #f1f1f1; }}
"""


def render_narrative_pdf_bytes(styled: list[dict], *, folio: str = "", full_fonts: bool = False) -> bytes:
    from plugins.upr_visuals.i18n import (
        arabic_font_class,
        current_export_language,
        rtl_document_attrs,
        uses_arabic_font,
    )
    from plugins.upr_visuals.raster import write_weasyprint_pdf
    from plugins.upr_visuals.typography import print_typography_css

    _ = folio
    lang = current_export_language()
    attrs = rtl_document_attrs(lang)
    font_class = arabic_font_class(lang)
    class_attr = f" class='{font_class}'" if font_class else ""
    body = "".join(_para_html(para) for para in styled)
    # Inline faces on the document (same as dashboard ``_wrap``) so WeasyPrint
    # registers Tajawal even if a caller forgets FontConfiguration on CSS().
    html = (
        f"<!DOCTYPE html><html lang='{attrs['lang']}' dir='{attrs['dir']}'{class_attr}>"
        f"<head><meta charset='utf-8'><style>{print_typography_css(lang)}</style></head>"
        f"<body>{body}</body></html>"
    )
    try:
        return write_weasyprint_pdf(
            html,
            stylesheets=[_narrative_css()],
            full_fonts=full_fonts or uses_arabic_font(lang),
        )
    except RuntimeError as exc:
        raise UprVisualsError(str(exc)) from exc


def _montserrat_regular() -> Path | None:
    for path in (
        _PLUGIN_FONTS_DIR / "Montserrat-Regular.ttf",
        _APP_FONTS_DIR / "Montserrat-Regular.ttf",
    ):
        if path.is_file():
            return path
    return None


def _folio_has_rtl(text: str) -> bool:
    return any("\u0590" <= char <= "\u08ff" or "\ufb1d" <= char <= "\ufefc" for char in text)


def _folio_has_arabic(text: str) -> bool:
    return any("\u0600" <= char <= "\u06ff" or "\ufb50" <= char <= "\ufefc" for char in text)


def _folio_font_path(*, rtl: bool, arabic: bool = False) -> Path | None:
    """Montserrat for Latin; Tajawal for Arabic script; system RTL fonts otherwise."""
    import os

    candidates: list[Path] = []
    if rtl:
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        if arabic:
            candidates.extend(
                [
                    _PLUGIN_FONTS_DIR / "Tajawal-Regular.ttf",
                    _APP_FONTS_DIR / "Tajawal-Regular.ttf",
                    Path("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"),
                    Path("/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"),
                ]
            )
        candidates.extend(
            [
                windir / "Fonts" / "arial.ttf",
                windir / "Fonts" / "arialuni.ttf",
                windir / "Fonts" / "tahoma.ttf",
                windir / "Fonts" / "segoeui.ttf",
                Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            ]
        )
    candidates.extend(
        [
            _PLUGIN_FONTS_DIR / "Montserrat-Regular.ttf",
            _APP_FONTS_DIR / "Montserrat-Regular.ttf",
        ]
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


def apply_report_folios(out, *, folio: str = "") -> None:
    """Stamp ``{label}    /    {n}`` from page 2 onward. Page 1 is the cover."""
    import fitz

    label = folio or folio_label({})
    rtl = _folio_has_rtl(label)
    font_path = _folio_font_path(rtl=rtl, arabic=_folio_has_arabic(label))
    folio_rect = fitz.Rect(34.0, 803.7, 563.9, 817.7)
    archive = fitz.Archive(str(font_path.parent)) if rtl and font_path is not None else None
    css = ""
    if archive is not None and font_path is not None:
        css = (
            f"@font-face {{ font-family: FolioFont; src: url({font_path.name}); }}"
            "div { font-family: FolioFont, sans-serif; font-size: 8pt; text-align: center; "
            "direction: rtl; color: #000; }"
        )
    for index in range(1, out.page_count):
        page = out[index]
        text = folio_text(label, index + 1)
        if archive is not None:
            page.insert_htmlbox(folio_rect, f"<div>{escape(text)}</div>", css=css, archive=archive)
            continue
        if font_path is not None:
            page.insert_font(fontname="mont", fontfile=str(font_path))
            fontname = "mont"
        else:
            fontname = "helv"
        page.insert_textbox(
            folio_rect,
            text,
            fontname=fontname,
            fontsize=8,
            color=(0, 0, 0),
            align=getattr(fitz, "TEXT_ALIGN_CENTER", 1),
        )


def merge_report_pdfs(visuals_pdf: bytes, narrative_pdf: bytes, *, folio: str = "") -> bytes:
    import fitz

    label = folio or folio_label({})
    out = fitz.open(stream=visuals_pdf, filetype="pdf")
    try:
        extra = fitz.open(stream=narrative_pdf, filetype="pdf")
        try:
            out.insert_pdf(extra)
        finally:
            extra.close()
        apply_report_folios(out, folio=label)
        return out.tobytes()
    finally:
        out.close()
