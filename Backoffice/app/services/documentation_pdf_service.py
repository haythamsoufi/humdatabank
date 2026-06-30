"""
Server-side PDF export for documentation pages (WeasyPrint).

Produces real, selectable PDF text with proper wrapping — unlike client-side
html2canvas screenshot exports.
"""

from __future__ import annotations

import io
import os
import re
import tempfile
from pathlib import Path
from typing import Callable, Dict, Optional
from urllib.parse import quote

from flask import Response, current_app, render_template, request, send_file
from flask_babel import _, force_locale, format_datetime
from werkzeug.exceptions import ServiceUnavailable

from app.services import documentation_service as docs
from app.services.documentation_service import _prettify_stem
from app.services.app_settings_service import _strip_visual_path_prefixes
from app.utils.branding_visual_assets import relative_path_under_branding
from app.utils.datetime_helpers import get_org_timezone, utcnow
from app.utils.organization_helpers import get_org_name

_PDF_HEADER_LOGO_STATIC = "IFRC_logo_square.svg"


_RTL_LANGS = frozenset({"ar", "fa", "he", "ur"})


def _current_language() -> str:
    from app.utils.form_localization import get_translation_key

    return (get_translation_key() or "en").split("-")[0].lower()


def _is_rtl(lang: str) -> bool:
    return lang in _RTL_LANGS


def _pdf_asset_url_builder(root: Path) -> Callable[[str], str]:
    def builder(rel_asset: str) -> str:
        candidate = (root / rel_asset).resolve()
        return candidate.as_uri()

    return builder


def pdf_filename(page_title: str, current_rel: str) -> str:
    """Build a safe, human-readable download filename for a documentation PDF."""
    base = (page_title or "").strip()
    if not base:
        rel_stem = Path(current_rel or "documentation").stem
        base = _prettify_stem(rel_stem) if rel_stem else "Documentation"
    if not base:
        base = "Documentation"

    # Drop characters that are invalid in common filesystems; keep spaces and casing.
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", base)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
    cleaned = cleaned[:120] or "Documentation"
    return f"{cleaned}.pdf"


def _attachment_disposition(download_name: str) -> str:
    """RFC 5987 attachment header — avoids ASCII fallbacks that strip non-Latin text."""
    return f"attachment; filename*=UTF-8''{quote(download_name, safe='')}"


def _resolve_logo_uri_for_pdf(logo_path: str) -> Optional[str]:
    """Resolve the organization logo to a local file URI for WeasyPrint."""
    norm = _strip_visual_path_prefixes(logo_path or "logo.svg") or "logo.svg"
    static_path = Path(current_app.root_path) / "static" / norm
    if static_path.is_file():
        return static_path.resolve().as_uri()

    branding_rel = relative_path_under_branding(norm)
    if not branding_rel:
        return None

    try:
        from app.services import storage_service as storage

        if not storage.exists(storage.SYSTEM, branding_rel):
            return None
        data = storage.download(storage.SYSTEM, branding_rel)
        ext = os.path.splitext(branding_rel)[1] or ".png"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        tmp.write(data)
        tmp.close()
        return Path(tmp.name).as_uri()
    except Exception as exc:
        current_app.logger.debug("PDF logo resolve failed: %s", exc)
        return None


def _resolve_pdf_header_logo_uri() -> Optional[str]:
    """Use the square platform logo in documentation PDF headers."""
    return _resolve_logo_uri_for_pdf(_PDF_HEADER_LOGO_STATIC)


def _build_pdf_branding_context(lang: str, page_title: str) -> Dict[str, object]:
    """Localized branding labels and assets for documentation PDF export."""
    logo_uri = _resolve_pdf_header_logo_uri()
    generated_at = utcnow().astimezone(get_org_timezone())

    with force_locale(lang):
        formatted_date = format_datetime(generated_at, format="medium")
        return {
            "org_name": get_org_name(locale=lang),
            "logo_uri": logo_uri,
            "page_title": page_title,
            "is_rtl": _is_rtl(lang),
            "lang": lang,
            "generated_on": _("Generated on %(date)s")
            % {"date": formatted_date},
            "page_label": _("Page"),
        }


def _pdf_css(branding: Dict[str, object]) -> str:
    is_rtl = bool(branding.get("is_rtl"))
    body_font = (
        '"Tajawal", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, Arial, sans-serif'
        if is_rtl
        else '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, Arial, sans-serif'
    )
    text_align_start = "right" if is_rtl else "left"
    text_align_end = "left" if is_rtl else "right"
    return f"""
    @page {{
        size: A4;
        margin: 34mm 14mm 24mm 14mm;
        @top-left {{
            content: element(doc-header);
            width: 100%;
            vertical-align: bottom;
        }}
        @bottom-center {{
            content: element(doc-footer);
            width: 100%;
            vertical-align: top;
        }}
    }}

    * {{
        box-sizing: border-box;
    }}

    body {{
        font-family: {body_font};
        color: #334155;
        font-size: 11pt;
        line-height: 1.65;
        margin: 0;
        word-wrap: break-word;
        overflow-wrap: anywhere;
    }}

    .pdf-running-header {{
        position: running(doc-header);
        width: 100%;
        padding-bottom: 8pt;
        margin-bottom: 4pt;
        border-bottom: 2pt solid #dc2626;
    }}

    .pdf-header-table {{
        width: 100%;
        border-collapse: collapse;
    }}

    .pdf-header-logo-cell {{
        width: 42pt;
        vertical-align: middle;
        padding-{text_align_start}: 0;
        padding-{text_align_end}: 10pt;
    }}

    .pdf-header-logo {{
        display: block;
        max-width: 38pt;
        max-height: 38pt;
        width: auto;
        height: auto;
    }}

    .pdf-header-brand-cell {{
        vertical-align: middle;
        text-align: {text_align_start};
    }}

    .pdf-header-org {{
        font-size: 11pt;
        font-weight: 700;
        color: #0f172a;
        line-height: 1.25;
    }}

    .pdf-header-title-cell {{
        width: 38%;
        vertical-align: middle;
        text-align: {text_align_end};
        font-size: 9pt;
        font-weight: 600;
        color: #475569;
        line-height: 1.35;
    }}

    .pdf-running-footer {{
        position: running(doc-footer);
        width: 100%;
        padding-top: 6pt;
        border-top: 1pt solid #e2e8f0;
    }}

    .pdf-footer-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 8pt;
        color: #94a3b8;
    }}

    .pdf-footer-center {{
        width: 72%;
        text-align: {text_align_start};
        vertical-align: top;
    }}

    .pdf-footer-page {{
        width: 28%;
        text-align: {text_align_end};
        vertical-align: top;
        white-space: nowrap;
        font-size: 8.5pt;
        color: #64748b;
        font-family: {body_font};
    }}

    .pdf-page-num::after {{
        content: counter(page);
    }}

    .pdf-body {{
        padding-top: 2pt;
    }}

    .doc-title {{
        font-size: 20pt;
        font-weight: 700;
        color: #0f172a;
        margin: 0 0 16pt;
        padding-bottom: 8pt;
        border-bottom: 2pt solid #e2e8f0;
        page-break-after: avoid;
        word-wrap: break-word;
        overflow-wrap: anywhere;
    }}

    .docs-prose {{
        max-width: none;
    }}

    .docs-prose h1, .docs-prose h2, .docs-prose h3, .docs-prose h4, .docs-prose h5, .docs-prose h6 {{
        color: #1e293b;
        font-weight: 600;
        page-break-after: avoid;
        word-wrap: break-word;
        overflow-wrap: anywhere;
    }}

    .docs-prose h1 {{
        font-size: 18pt;
        font-weight: 700;
        color: #0f172a;
        margin: 18pt 0 10pt;
        padding-bottom: 6pt;
        border-bottom: 2pt solid #e2e8f0;
    }}
    .docs-prose h2 {{
        font-size: 14pt;
        font-weight: 600;
        color: #1e293b;
        margin: 16pt 0 8pt;
        padding-{text_align_start}: 10pt;
        border-{text_align_start}: 3pt solid #6366f1;
    }}
    .docs-prose h3 {{
        font-size: 12pt;
        font-weight: 600;
        color: #334155;
        margin: 14pt 0 6pt;
        padding-{text_align_start}: 8pt;
        border-{text_align_start}: 3pt solid #8b5cf6;
    }}
    .docs-prose h4 {{
        font-size: 11pt;
        font-weight: 600;
        color: #475569;
        margin: 12pt 0 6pt;
    }}
    .docs-prose h5 {{
        font-size: 10.5pt;
        font-weight: 600;
        color: #64748b;
        margin: 10pt 0 5pt;
    }}
    .docs-prose h6 {{
        font-size: 10pt;
        font-weight: 600;
        color: #64748b;
        margin: 8pt 0 4pt;
    }}

    /* TOC wraps heading text in <a class="toclink"> — keep heading look, not hyperlink */
    .docs-prose h1 a,
    .docs-prose h2 a,
    .docs-prose h3 a,
    .docs-prose h4 a,
    .docs-prose h5 a,
    .docs-prose h6 a {{
        color: inherit;
        text-decoration: none;
        font-weight: inherit;
        font-size: inherit;
    }}

    /* Empty bookmark anchors inserted for cross-language fragment targets */
    .docs-prose h1 > a:not([href]),
    .docs-prose h2 > a:not([href]),
    .docs-prose h3 > a:not([href]),
    .docs-prose h4 > a:not([href]),
    .docs-prose h5 > a:not([href]),
    .docs-prose h6 > a:not([href]) {{
        display: none;
    }}

    .docs-prose p, .docs-prose li, .docs-prose dd, .docs-prose dt {{
        word-wrap: break-word;
        overflow-wrap: anywhere;
    }}

    .docs-prose p {{ margin: 0 0 10pt; }}
    .docs-prose ul, .docs-prose ol {{
        margin: 0 0 10pt;
        padding-{text_align_start}: 18pt;
    }}
    .docs-prose li {{ margin-bottom: 4pt; }}

    .docs-prose a {{
        color: #4338ca;
        text-decoration: underline;
        word-wrap: break-word;
        overflow-wrap: anywhere;
    }}

    .docs-prose code {{
        font-family: ui-monospace, Menlo, Consolas, monospace;
        font-size: 9.5pt;
        background: #f1f5f9;
        color: #7c3aed;
        padding: 1pt 3pt;
        border-radius: 2pt;
        word-wrap: break-word;
        overflow-wrap: anywhere;
        white-space: pre-wrap;
    }}

    .docs-prose pre, .docs-prose .highlight pre {{
        background: #0f172a;
        color: #e2e8f0;
        padding: 10pt 12pt;
        border-radius: 4pt;
        font-size: 9pt;
        line-height: 1.5;
        white-space: pre-wrap;
        word-wrap: break-word;
        overflow-wrap: anywhere;
        page-break-inside: avoid;
        margin: 0 0 12pt;
    }}

    .docs-prose pre code {{
        background: none;
        color: inherit;
        padding: 0;
        white-space: pre-wrap;
    }}

    .docs-prose blockquote {{
        border-{text_align_start}: 3pt solid #818cf8;
        margin: 12pt 0;
        padding: 8pt 12pt;
        background: #f8fafc;
        color: #475569;
        page-break-inside: avoid;
    }}

    .docs-prose table {{
        width: 100%;
        border-collapse: collapse;
        margin: 0 0 12pt;
        font-size: 9.5pt;
        table-layout: fixed;
        word-wrap: break-word;
    }}

    .docs-prose th, .docs-prose td {{
        border: 1pt solid #e2e8f0;
        padding: 6pt 8pt;
        vertical-align: top;
        word-wrap: break-word;
        overflow-wrap: anywhere;
    }}

    .docs-prose th {{
        background: #f8fafc;
        font-weight: 600;
        color: #334155;
    }}

    .docs-prose img {{
        max-width: 100%;
        height: auto;
        margin: 10pt 0;
        page-break-inside: avoid;
    }}

    .docs-prose hr {{
        border: none;
        border-top: 1pt solid #e2e8f0;
        margin: 16pt 0;
    }}

    .docs-prose .toc {{
        margin: 12pt 0;
        padding: 10pt 12pt;
        background: #f8fafc;
        border: 1pt solid #e2e8f0;
        page-break-inside: avoid;
    }}

    .docs-prose details, .docs-prose .mermaid {{
        margin: 12pt 0;
        padding: 10pt 12pt;
        border: 1pt solid #e2e8f0;
        background: #f8fafc;
        page-break-inside: avoid;
    }}

    html[dir="rtl"] body,
    html[dir="rtl"] .pdf-running-header,
    html[dir="rtl"] .pdf-running-footer,
    html[dir="rtl"] .doc-title,
    html[dir="rtl"] .docs-prose {{
        direction: rtl;
        text-align: right;
        font-family: {body_font};
    }}

    html[dir="rtl"] .docs-prose h1,
    html[dir="rtl"] .docs-prose h2,
    html[dir="rtl"] .docs-prose h3,
    html[dir="rtl"] .docs-prose h4,
    html[dir="rtl"] .docs-prose h5,
    html[dir="rtl"] .docs-prose h6,
    html[dir="rtl"] .docs-prose p,
    html[dir="rtl"] .docs-prose li,
    html[dir="rtl"] .docs-prose dt,
    html[dir="rtl"] .docs-prose dd,
    html[dir="rtl"] .docs-prose th,
    html[dir="rtl"] .docs-prose td {{
        text-align: right;
    }}

    html[dir="rtl"] .docs-prose dd {{
        margin-right: 1.5rem;
        margin-left: 0;
        padding-right: 0.75rem;
        padding-left: 0;
        border-right: 2pt solid #e2e8f0;
        border-left: none;
    }}

    html[dir="rtl"] .docs-prose pre,
    html[dir="rtl"] .docs-prose .highlight,
    html[dir="rtl"] .docs-prose pre code {{
        direction: ltr;
        text-align: left;
    }}

    html[dir="rtl"] .docs-prose :not(pre) > code,
    html[dir="rtl"] .docs-prose kbd,
    html[dir="rtl"] .docs-prose samp {{
        direction: ltr;
    }}
    """


def generate_doc_pdf_bytes(
    *,
    root: Path,
    file_path: Path,
    current_rel: str,
    page_title: str,
    doc_url_builder: Callable[[str], str],
    lang: Optional[str] = None,
) -> bytes:
    """Render a documentation page to PDF bytes."""
    lang = lang or _current_language()
    branding = _build_pdf_branding_context(lang, page_title)
    asset_builder = _pdf_asset_url_builder(root)

    content_html = docs.render_markdown_file(
        root=root,
        file_path=file_path,
        current_rel=current_rel,
        doc_url_builder=doc_url_builder,
        asset_url_builder=asset_builder,
    )

    html_content = render_template(
        "admin/docs/export_pdf.html",
        content_html=content_html,
        **branding,
    )

    try:
        from weasyprint import CSS, HTML  # type: ignore
    except Exception as exc:
        current_app.logger.error("WeasyPrint not available for docs PDF export: %s", exc, exc_info=True)
        raise ServiceUnavailable(_("PDF generation is not available on this deployment.")) from exc

    base_url = request.url_root if request else None
    pdf_buffer = io.BytesIO()
    HTML(string=html_content, base_url=base_url).write_pdf(
        pdf_buffer,
        stylesheets=[CSS(string=_pdf_css(branding))],
        optimize_images=True,
    )
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()


def send_doc_pdf(
    *,
    root: Path,
    doc_path: str,
    user,
    visible_top_level_dirs: set[str],
    doc_url_builder: Callable[[str], str],
    prefer_user_landing: bool = False,
) -> Response:
    """Resolve a doc, enforce access, and return a PDF download response."""
    file_path, current_rel = docs.resolve_doc_path(
        root, doc_path, user, prefer_user_landing=prefer_user_landing
    )
    docs.ensure_doc_page_access(
        user,
        current_rel,
        visible_top_level_dirs=visible_top_level_dirs,
    )
    page_title = docs.extract_page_title(file_path)
    pdf_bytes = generate_doc_pdf_bytes(
        root=root,
        file_path=file_path,
        current_rel=current_rel,
        page_title=page_title,
        doc_url_builder=doc_url_builder,
    )
    download_name = pdf_filename(page_title, current_rel)
    response = send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=download_name,
    )
    response.headers["Content-Disposition"] = _attachment_disposition(download_name)
    return response
