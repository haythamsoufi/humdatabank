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
  margin: 18mm 16mm 16mm 16mm;
  @top-left {
    content: element(running-head);
  }
  @bottom-right {
    content: "Page " counter(page) " / " counter(pages);
    font-family: "Open Sans", sans-serif;
    font-size: 8pt;
    color: #011e41;
  }
}
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
ul { margin: 0 0 8pt 14pt; padding: 0; }
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


def render_pdf(blocks: list, header: str) -> bytes:
    try:
        from weasyprint import CSS, HTML
        from weasyprint.text.fonts import FontConfiguration
    except ImportError as exc:
        raise PdfUnavailable("WeasyPrint is not available.") from exc

    font_config = FontConfiguration()
    base = _FONTS.resolve().as_uri() + "/"
    stylesheet = CSS(string=_CSS, font_config=font_config, base_url=base)
    document = HTML(string=_html(blocks, header), base_url=base)
    return document.write_pdf(stylesheets=[stylesheet], font_config=font_config)


def _html(blocks: list, header: str) -> str:
    parts = [
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"></head><body>",
        f"<div class=\"run-head\">{escape(header)}</div>",
    ]
    for block in blocks:
        parts.append(_block_html(block))
    parts.append("</body></html>")
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
    text = escape(block.text or "") or "&nbsp;"
    return f"<p>{text}</p>"


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
