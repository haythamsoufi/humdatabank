"""Render the HTML report to a combined PDF via WeasyPrint."""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

_PDF_HIDE_SELECTORS = (
    "#pb-report-toolbar",
    ".pb-report-toolbar",
    ".pb-report-tools",
    ".pb-language-selector",
    "#quarto-sidebar",
    "#quarto-margin-sidebar",
    "nav#TOC",
    "nav#toc",
)

PDF_EXPORT_CSS = """
.report-figure .pb-dashboard .dash-title { display: none !important; }
.report-section { page-break-before: auto !important; break-before: auto !important; }
.report-part + .report-part .report-part-title {
  page-break-before: always !important;
  break-before: page !important;
}
.report-figure { page-break-inside: auto !important; break-inside: auto !important; }
.pb-dashboard .indicator-row,
.pb-dashboard .donut-row,
.pb-dashboard .donut-pair {
  page-break-inside: avoid !important;
  break-inside: avoid !important;
}
.pb-dashboard .section-tail {
  page-break-inside: auto !important;
  break-inside: auto !important;
}
.pb-dashboard .footnote {
  page-break-before: avoid !important;
  break-before: avoid !important;
}
.report-section-title {
  page-break-after: avoid !important;
  break-after: avoid !important;
}
.pb-lang-panel:not([hidden]) .report-figure:last-child,
.pb-lang-panel:not([hidden]) .report-section:last-child,
.pb-lang-panel:not([hidden]) .report-part:last-child {
  margin-bottom: 0 !important;
}
.pb-lang-panel:not([hidden]) .pb-dashboard {
  padding-bottom: 0 !important;
}
main, #quarto-document-content, .page-layout-full {
  padding-bottom: 0 !important;
  margin-bottom: 0 !important;
}
/* Dashboard is authored at full A4 width (8.27in) but @page margins narrow the
   printable area — fit charts/tables to the content box and preserve aspect ratio. */
body.pb-pdf-export .pb-dashboard {
  max-width: 100% !important;
  width: 100% !important;
  padding-left: 0 !important;
  padding-right: 0 !important;
  box-sizing: border-box !important;
}
body.pb-pdf-export .pb-dashboard .line-chart-inner {
  width: 100% !important;
  max-width: 100% !important;
  height: auto !important;
  min-height: 0 !important;
  aspect-ratio: 481 / 110;
  overflow: visible !important;
}
body.pb-pdf-export .pb-dashboard .line-chart-inner > svg,
body.pb-pdf-export .pb-dashboard .line-chart-inner > .line-chart-img {
  width: 100% !important;
  max-width: none !important;
  height: auto !important;
  max-height: none !important;
  aspect-ratio: 481 / 110;
  object-fit: contain;
}
body.pb-pdf-export .pb-dashboard div.year-data-grid,
body.pb-pdf-export .pb-dashboard table.year-data-grid {
  width: 100% !important;
  max-width: 100% !important;
}
body.pb-pdf-export .pb-dashboard .line-chart-wrap {
  overflow: visible !important;
}
"""

PDF_PAGE_CSS = """
@page {
  size: A4;
  margin: 15mm 12mm;
}
"""


def html_file_uri(path: Path) -> str:
    """Return a file:// URI for local HTML assets."""
    return path.resolve().as_uri()


def _append_class(element, class_name: str) -> None:
    classes = element.get("class") or []
    if isinstance(classes, str):
        classes = classes.split()
    if class_name not in classes:
        classes.append(class_name)
    element["class"] = classes


def _restructure_section_tails(soup: BeautifulSoup) -> None:
    for dashboard in soup.select(".pb-dashboard"):
        footnote = None
        for child in dashboard.children:
            if getattr(child, "name", None) == "div" and "footnote" in (child.get("class") or []):
                footnote = child
                break
        if footnote is None or footnote.find_parent(class_="section-tail"):
            continue
        last_block = footnote.find_previous_sibling()
        if last_block is None or "dash-title" in (last_block.get("class") or []):
            continue
        tail = soup.new_tag("div", attrs={"class": "section-tail"})
        last_block.insert_before(tail)
        tail.append(last_block.extract())
        tail.append(footnote.extract())


def prepare_html_for_pdf(html_content: str, language: str) -> str:
    """Apply the same DOM/CSS changes as the legacy Playwright PDF export script."""
    soup = BeautifulSoup(html_content, "lxml")

    active_panel = None
    for panel in soup.select(".pb-lang-panel"):
        if panel.get("data-lang") == language:
            panel.attrs.pop("hidden", None)
            active_panel = panel
        else:
            panel["hidden"] = ""

    is_rtl = active_panel is not None and active_panel.get("data-dir") == "rtl"
    html_el = soup.find("html")
    if html_el is not None:
        html_el["dir"] = "rtl" if is_rtl else "ltr"
        if is_rtl:
            _append_class(html_el, "pb-report-arabic")
        else:
            classes = html_el.get("class") or []
            if isinstance(classes, str):
                classes = classes.split()
            html_el["class"] = [name for name in classes if name != "pb-report-arabic"]

    body = soup.find("body")
    if body is not None:
        _append_class(body, "pb-pdf-export")

    for selector in _PDF_HIDE_SELECTORS:
        for element in soup.select(selector):
            element.decompose()

    _restructure_section_tails(soup)

    head = soup.find("head")
    if head is None:
        head = soup.new_tag("head")
        if html_el is not None:
            html_el.insert(0, head)
    style = soup.new_tag("style")
    style.string = PDF_EXPORT_CSS
    head.append(style)

    return str(soup)


def render_report_pdf(
    html_path: Path,
    output_path: Path,
    *,
    language: str,
    browser=None,
) -> Path:
    """Export one language panel from the built HTML report as a combined PDF."""
    del browser  # kept for caller compatibility during migration

    html_path = Path(html_path)
    output_path = Path(output_path)
    if not html_path.is_file():
        raise FileNotFoundError(f"HTML report not found: {html_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from weasyprint import CSS, HTML
    except ImportError as exc:
        raise RuntimeError(
            "WeasyPrint is not installed. It is required for P&B report PDF export."
        ) from exc

    prepared = prepare_html_for_pdf(html_path.read_text(encoding="utf-8"), language)
    HTML(
        string=prepared,
        base_url=f"{html_path.parent.resolve().as_posix()}/",
    ).write_pdf(
        str(output_path),
        stylesheets=[CSS(string=PDF_PAGE_CSS)],
        optimize_images=True,
    )
    return output_path
