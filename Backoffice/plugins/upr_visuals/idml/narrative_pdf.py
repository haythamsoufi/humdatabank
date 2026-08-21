"""WeasyPrint narrative pages that match the IDML Word styles, merged after visuals."""

from __future__ import annotations

from html import escape
from pathlib import Path

from plugins.upr_visuals.idml.builder import _STYLE_RUNS, folio_label
from plugins.upr_visuals.raster import _PLUGIN_DIR, _PLUGIN_FONTS_DIR, _font_css

_APP_FONTS_DIR = Path(__file__).resolve().parents[3] / "app" / "static" / "fonts"


def _run_html(run: dict, *, style_name: str) -> str:
    text = escape(str(run.get("text") or ""))
    if not text:
        return ""
    href = (run.get("href") or "").strip()
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
    return f"""
{_font_css()}
@page {{
  size: A4;
  margin: 32pt 34pt 40pt 34pt;
}}
html, body {{
  margin: 0;
  padding: 0;
  color: #000;
  font-family: "Open Sans", "Segoe UI", sans-serif;
  font-size: 10pt;
  line-height: 13.5pt;
}}
.upr-nar-p {{ margin: 0 0 8.5pt; }}
.upr-nar-p--QHeading {{
  font-family: Montserrat, sans-serif; font-weight: 700; font-size: 20pt;
  line-height: 24pt; color: #ef3340; margin: 4pt 0 12pt;
}}
.upr-nar-p--SectionHead {{
  font-family: Montserrat, sans-serif; font-weight: 700; font-size: 15pt;
  line-height: 18pt; color: #011e41; margin: 16pt 0 6pt;
}}
.upr-nar-p--TopicHead {{
  font-family: Montserrat, sans-serif; font-weight: 700; font-size: 14pt;
  line-height: 17pt; color: #1b365d; margin: 12pt 0 6pt;
}}
.upr-nar-p--BandHead {{
  font-family: Montserrat, sans-serif; font-weight: 700; font-size: 16pt;
  line-height: 20pt; color: #1b365d; margin: 14pt 0 10pt;
  border-bottom: 2pt solid #1b365d; padding-bottom: 3pt;
}}
.upr-nar-p--Subhead {{
  font-weight: 700; font-size: 10pt; line-height: 13.5pt; margin: 10pt 0 6pt;
}}
.upr-nar-p--Body {{ text-align: justify; }}
.upr-nar-p--Blank {{ margin: 0 0 4pt; line-height: 12pt; min-height: 12pt; }}
.upr-nar-p--AdditionalHead {{
  font-family: Montserrat, sans-serif; font-weight: 700; font-size: 9.5pt;
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
  text-align: left;
}}
.upr-nar-table td {{ background: #f1f1f1; }}
"""


def render_narrative_pdf_bytes(styled: list[dict], *, folio: str = "") -> bytes:
    try:
        from weasyprint import CSS, HTML
    except ImportError as exc:
        raise RuntimeError("WeasyPrint is required for UPR visual export.") from exc

    _ = folio
    body = "".join(_para_html(para) for para in styled)
    html = (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'></head>"
        f"<body>{body}</body></html>"
    )
    from io import BytesIO

    buffer = BytesIO()
    HTML(string=html, base_url=_PLUGIN_DIR.resolve().as_uri() + "/").write_pdf(
        buffer,
        stylesheets=[CSS(string=_narrative_css())],
        optimize_images=False,
        full_fonts=True,
        hinting=True,
    )
    return buffer.getvalue()


def _montserrat_regular() -> Path | None:
    for path in (
        _PLUGIN_FONTS_DIR / "Montserrat-Regular.ttf",
        _APP_FONTS_DIR / "Montserrat-Regular.ttf",
    ):
        if path.is_file():
            return path
    return None


def merge_report_pdfs(visuals_pdf: bytes, narrative_pdf: bytes, *, folio: str = "") -> bytes:
    import fitz

    label = folio or folio_label({})
    out = fitz.open(stream=visuals_pdf, filetype="pdf")
    try:
        extra = fitz.open(stream=narrative_pdf, filetype="pdf")
        start = out.page_count
        try:
            out.insert_pdf(extra)
        finally:
            extra.close()
        font_path = _montserrat_regular()
        for index in range(start, out.page_count):
            page = out[index]
            if font_path is not None:
                page.insert_font(fontname="mont", fontfile=str(font_path))
                fontname = "mont"
            else:
                fontname = "helv"
            rect = fitz.Rect(34.0, 803.7, 563.9, 817.7)
            page.insert_textbox(
                rect,
                f"{label}    /    {index + 1}",
                fontname=fontname,
                fontsize=8,
                color=(0, 0, 0),
                align=getattr(fitz, "TEXT_ALIGN_CENTER", 1),
            )
        return out.tobytes()
    finally:
        out.close()
