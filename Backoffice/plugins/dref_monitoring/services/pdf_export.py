"""PDF of the same block list as the Word file.

Visuals follow the IFRC type and colour used for print reports: Montserrat
headings, Open Sans body, red title, navy chapters. WeasyPrint embeds the
faces shipped with the app. A missing WeasyPrint install raises PdfUnavailable
so the route can answer 503.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

_FONTS = Path(__file__).resolve().parents[3] / "app" / "static" / "fonts"

_CSS = """
@font-face {
  font-family: "Montserrat";
  src: url("montserrat-latin.woff2") format("woff2");
  font-weight: 700;
  font-style: normal;
}
@font-face {
  font-family: "Open Sans";
  src: url("OpenSans-Regular.ttf") format("truetype");
  font-weight: 400;
  font-style: normal;
}
@font-face {
  font-family: "Open Sans";
  src: url("OpenSans-Bold.ttf") format("truetype");
  font-weight: 700;
  font-style: normal;
}
@font-face {
  font-family: "Open Sans";
  src: url("OpenSans-Italic.ttf") format("truetype");
  font-weight: 400;
  font-style: italic;
}
@font-face {
  font-family: "Open Sans";
  src: url("OpenSans-BoldItalic.ttf") format("truetype");
  font-weight: 700;
  font-style: italic;
}
@page {
  size: A4;
  margin: 18mm 16mm 22mm 16mm;
  @top-left {
    content: element(running-head);
  }
  @bottom-left {
    content: element(running-foot);
    vertical-align: top;
    padding-top: 4mm;
    width: 100%;
  }
}
.run-foot {
  position: running(running-foot);
  font-family: "Open Sans", sans-serif;
  font-size: 9pt;
  color: #011e41;
  white-space: nowrap;
}
.run-foot .pg::before {
  content: counter(page);
  font-size: 11pt;
  font-weight: 700;
  margin-right: 8pt;
}
.run-foot .dot { color: #ef3340; font-weight: 700; }
.run-foot .name { font-weight: 700; }
.cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  column-gap: 12mm;
  margin: 0 0 4pt;
}
.cards p {
  margin: 0 0 10pt;
  line-height: 1.4;
  break-inside: avoid;
}
.cards a { color: inherit; text-decoration: underline; }
html, body {
  margin: 0;
  padding: 0;
  color: #000;
  font-family: "Open Sans", sans-serif;
  font-size: 10.5pt;
  line-height: 1.35;
}
.run-head {
  position: running(running-head);
  font-family: "Open Sans", sans-serif;
  font-size: 8pt;
  color: #011e41;
  border-bottom: 1.5pt solid #ef3340;
  padding-bottom: 3pt;
}
h1.title {
  font-family: "Montserrat", "Open Sans", sans-serif;
  font-weight: 700;
  font-size: 22pt;
  line-height: 1.15;
  color: #ef3340;
  margin: 0 0 2pt;
}
p.subtitle {
  font-family: "Montserrat", "Open Sans", sans-serif;
  font-weight: 700;
  font-size: 14pt;
  color: #011e41;
  margin: 0 0 10pt;
}
h1.chapter {
  font-family: "Montserrat", "Open Sans", sans-serif;
  font-weight: 700;
  font-size: 16pt;
  line-height: 1.2;
  color: #011e41;
  margin: 16pt 0 4pt;
  page-break-after: avoid;
}
h2 {
  font-family: "Montserrat", "Open Sans", sans-serif;
  font-weight: 700;
  font-size: 13pt;
  color: #1b365d;
  margin: 12pt 0 4pt;
  page-break-after: avoid;
}
h3 {
  font-family: "Open Sans", sans-serif;
  font-weight: 700;
  font-size: 11pt;
  color: #000;
  margin: 8pt 0 3pt;
  page-break-after: avoid;
}
p { margin: 0 0 8pt; }
p.note {
  font-size: 9pt;
  font-style: italic;
  color: #58595b;
  margin: 2pt 0 8pt;
}
ul, ol { margin: 0 0 8pt 14pt; padding: 0; }
li { margin: 0 0 2pt; }
table {
  width: 100%;
  border-collapse: collapse;
  margin: 0 0 8pt;
  page-break-inside: avoid;
  font-size: 9pt;
}
th {
  background: #011e41;
  color: #fff;
  font-weight: 700;
  text-align: left;
  padding: 4pt 6pt;
}
td {
  border-bottom: 0.4pt solid #d5d6d8;
  padding: 3pt 6pt;
  vertical-align: top;
}
tr:nth-child(even) td { background: #f7f8fa; }
table.kv th, table.kv td { background: transparent; color: #000; font-weight: 400; }
table.kv td:first-child {
  width: 42%;
  color: #58595b;
  font-weight: 700;
  background: #f4f5f7;
}
"""


class PdfUnavailable(RuntimeError):
    """WeasyPrint is not installed in this environment."""


def render_pdf(blocks: list, header: str, language: str = "en") -> bytes:
    try:
        from weasyprint import CSS, HTML
        from weasyprint.text.fonts import FontConfiguration
    except ImportError as exc:
        raise PdfUnavailable("WeasyPrint is not available.") from exc

    from plugins.dref_monitoring.i18n import override_locale

    font_config = FontConfiguration()
    base = _FONTS.resolve().as_uri() + "/"
    with override_locale(language):
        stylesheet = CSS(string=_stylesheet(language), font_config=font_config, base_url=base)
        document = HTML(string=_html(blocks, header, language), base_url=base)
        return document.write_pdf(stylesheets=[stylesheet], font_config=font_config)


def _stylesheet(language: str) -> str:
    css = _CSS
    if language == "ar":
        css = css.replace("@bottom-left {", "@bottom-right {")
    if language != "ar":
        return css
    return css + """
@font-face {
  font-family: "Tajawal";
  src: url("Tajawal-Regular.ttf") format("truetype");
  font-weight: 400;
  font-style: normal;
}
@font-face {
  font-family: "Tajawal";
  src: url("Tajawal-Bold.ttf") format("truetype");
  font-weight: 700;
  font-style: normal;
}
html[lang="ar"], html[lang="ar"] body, html[lang="ar"] h1, html[lang="ar"] h2, html[lang="ar"] h3,
html[lang="ar"] p, html[lang="ar"] li, html[lang="ar"] td, html[lang="ar"] th {
  font-family: "Tajawal", "Open Sans", sans-serif;
}
"""


def _html(blocks: list, header: str, language: str = "en") -> str:
    direction = "rtl" if language == "ar" else "ltr"
    parts = [
        f'<!DOCTYPE html><html lang="{escape(language)}" dir="{direction}"><head><meta charset="utf-8"></head><body>',
        f"<div class=\"run-head\">{escape(header)}</div>",
        _footer_html(blocks),
    ]
    for block in blocks:
        parts.append(_block_html(block))
    parts.append("</body></html>")
    return "".join(parts)


def _footer_html(blocks: list) -> str:
    """The page number, the report type and the operation name, set in the bottom margin of every page."""
    from plugins.dref_monitoring.services.docx_export import footer_parts

    title, subtitle = footer_parts(blocks)
    parts = ['<div class="run-foot"><span class="pg"></span>']
    if title:
        parts.append(f"<span class=\"title\">{escape(title)}</span>")
    if subtitle:
        parts.append(f"<span class=\"dot\"> \u2022 </span>" if title else "")
        parts.append(f"<span class=\"name\">{escape(subtitle)}</span>")
    parts.append("</div>")
    return "".join(parts)


def _block_html(block) -> str:
    kind = block.kind
    if kind == "title":
        return f"<h1 class=\"title\">{escape(block.text)}</h1>"
    if kind == "subtitle":
        return f"<p class=\"subtitle\">{escape(block.text)}</p>"
    if kind == "heading":
        level = block.level if block.level in {1, 2, 3} else 2
        css = " class=\"chapter\"" if level == 1 else ""
        return f"<h{level}{css}>{escape(block.text)}</h{level}>"
    if kind == "note":
        return f"<p class=\"note\">{escape(block.text)}</p>"
    if kind == "kv":
        return _table_html((), block.rows, kv=True)
    if kind == "table":
        return _table_html(block.headers, block.rows, kv=False)
    if kind == "bullets":
        items = "".join(f"<li>{escape(row[0] if row else '')}</li>" for row in block.rows)
        return f"<ul>{items}</ul>"
    if getattr(block, "is_grid", False):
        from plugins.dref_monitoring.services.narrative_format import Node

        cards = [Node("p", runs=tuple(runs)) for runs in block.cards]
        return f"<div class=\"cards\">{_rich_html(cards)}</div>"
    if getattr(block, "html", ""):
        # The stored text is already reduced to paragraphs, lists and bold, italic and underline.
        return _rich_html(block.nodes) or "<p>&nbsp;</p>"
    text = escape(block.text or "") or "&nbsp;"
    return f"<p>{text}</p>"


def _rich_html(nodes) -> str:
    from plugins.dref_monitoring.services.narrative_format import nodes_to_html

    return nodes_to_html(list(nodes))


def _table_html(headers, rows, *, kv: bool) -> str:
    css = " class=\"kv\"" if kv else ""
    head = ""
    if headers:
        head = "<thead><tr>" + "".join(f"<th>{escape(cell)}</th>" for cell in headers) + "</tr></thead>"
    body = []
    for row in rows:
        cells = "".join(f"<td>{escape(cell)}</td>" for cell in row)
        body.append(f"<tr>{cells}</tr>")
    return f"<table{css}>{head}<tbody>{''.join(body)}</tbody></table>"
