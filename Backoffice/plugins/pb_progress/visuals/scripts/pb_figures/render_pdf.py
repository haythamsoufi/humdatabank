"""Render the HTML report to a combined PDF via Playwright."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Browser

PDF_PREPARE_JS = """
(lang) => {
  document.querySelectorAll(".pb-lang-panel").forEach((panel) => {
    if (panel.dataset.lang === lang) {
      panel.removeAttribute("hidden");
    } else {
      panel.setAttribute("hidden", "");
    }
  });

  const activePanel = document.querySelector(`.pb-lang-panel[data-lang="${lang}"]`);
  const isRtl = activePanel && activePanel.dataset.dir === "rtl";
  document.documentElement.classList.toggle("pb-report-arabic", Boolean(isRtl));
  document.documentElement.setAttribute("dir", isRtl ? "rtl" : "ltr");
  document.body.classList.add("pb-pdf-export");

  [
    "#pb-report-toolbar",
    ".pb-report-toolbar",
    ".pb-report-tools",
    ".pb-language-selector",
    "#pb-scroll-headers",
    "#quarto-sidebar",
    "#quarto-margin-sidebar",
    "nav#TOC",
    "nav#toc",
  ].forEach((selector) => {
    document.querySelectorAll(selector).forEach((el) => {
      el.style.display = "none";
    });
  });

  document.querySelectorAll(".pb-dashboard").forEach((dashboard) => {
    const footnote = dashboard.querySelector(":scope > .footnote");
    if (!footnote || footnote.closest(".section-tail")) return;
    const lastBlock = footnote.previousElementSibling;
    if (!lastBlock || lastBlock.classList.contains("dash-title")) return;
    const tail = document.createElement("div");
    tail.className = "section-tail";
    dashboard.insertBefore(tail, lastBlock);
    tail.appendChild(lastBlock);
    tail.appendChild(footnote);
  });

  const pdfStyle = document.createElement("style");
  pdfStyle.textContent = `
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
    /* Trailing figure/dashboard margins can spill onto an extra blank page. */
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
  `;
  document.head.appendChild(pdfStyle);
}
"""


def html_file_uri(path: Path) -> str:
    """Return a file:// URI suitable for Playwright on all platforms."""
    return path.resolve().as_uri()


def render_report_pdf(
    html_path: Path,
    output_path: Path,
    *,
    language: str,
    browser: Browser,
) -> Path:
    """Export one language panel from the built HTML report as a combined PDF."""
    html_path = Path(html_path)
    output_path = Path(output_path)
    if not html_path.is_file():
        raise FileNotFoundError(f"HTML report not found: {html_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    page = browser.new_page(viewport={"width": 1280, "height": 900})
    try:
        page.goto(html_file_uri(html_path), wait_until="load")
        page.evaluate("async () => { await document.fonts.ready; }")
        page.evaluate(PDF_PREPARE_JS, language)
        page.emulate_media(media="print")
        page.pdf(
            path=str(output_path),
            format="A4",
            print_background=True,
            prefer_css_page_size=True,
            margin={"top": "15mm", "bottom": "15mm", "left": "12mm", "right": "12mm"},
        )
    finally:
        page.close()
    return output_path
