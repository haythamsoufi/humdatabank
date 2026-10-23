"""Legacy ``GET /api/embeddedcontent`` from Admin → Embed Content.

The data.ifrc.org client injects ``EmbedCode`` as HTML. That string is the same
iframe the admin Copy button builds. One title and one description are copied
into every language field, because Embed Content is not translated.

``type=UNIFIED-PLANNING``, ``type=OVERVIEW-INTERNATIONAL``, and
``type=GLOBAL-INITIATIVES`` are the active rows whose page slot is Unified
Planning, International Overview, or Global Initiatives, in sort order.
Category is ignored, so an Analysis embed stays off those pages until the slot
is set. OCAC and BOCA are not in this table.
"""

from __future__ import annotations

import re
from html import escape
from typing import Any
from urllib.parse import urljoin

from flask import has_request_context, request

from app.models import EmbedContent

# Legacy ``type`` values the FDRS dashboard pages send.
EMBED_TYPE_TO_PAGE_SLOT = {
    "UNIFIED-PLANNING": "unified_planning",
    "OVERVIEW-INTERNATIONAL": "overview_international",
    "GLOBAL-INITIATIVES": "global_initiatives",
}

_TABLEAU_EMBEDDED = re.compile(r"[:?&]embed\s*=\s*y", re.IGNORECASE)


def serves_embed_type(embed_type: str) -> bool:
    key = (embed_type or "").strip().upper()
    return key in EMBED_TYPE_TO_PAGE_SLOT


def legacy_embeds(embed_type: str) -> list[dict[str, Any]]:
    """Rows for one FDRS page, in the shape ``embeddedcontent`` already parses."""
    key = (embed_type or "").strip().upper()
    rows = (
        EmbedContent.query.filter_by(is_active=True, page_slot=EMBED_TYPE_TO_PAGE_SLOT[key])
        .order_by(EmbedContent.sort_order, EmbedContent.id)
        .all()
    )
    return [_legacy_row(row) for row in rows]


def _legacy_row(row: EmbedContent) -> dict[str, Any]:
    title = row.title or ""
    text = row.description or ""
    return {
        "Id": row.id,
        "TitleEn": title,
        "TitleEs": title,
        "TitleFr": title,
        "TitleAr": title,
        "TextEn": text,
        "TextEs": text,
        "TextFr": text,
        "TextAr": text,
        "Order": row.sort_order or 0,
        "EmbedCode": iframe_tag(_absolute_url(row.embed_url), title, row.embed_type),
    }


def iframe_tag(url: str, title: str, embed_type: str | None) -> str:
    """The admin Copy iframe tag: full width, 640px tall, no border."""
    src = _tableau_src(url) if (embed_type or "").strip().lower() == "tableau" else (url or "").strip()
    label = escape(title or "Embed", quote=True)
    return (
        f'<iframe title="{label}" src="{escape(src, quote=True)}" '
        'style="width:100%;height:640px;border:0;"></iframe>'
    )


def _tableau_src(url: str) -> str:
    src = (url or "").strip()
    if not src or _TABLEAU_EMBEDDED.search(src):
        return src
    joiner = "&" if "?" in src else "?"
    return f"{src}{joiner}:embed=y&:showVizHome=no"


def _absolute_url(url: str | None) -> str:
    raw = (url or "").strip()
    if raw.startswith("/") and has_request_context():
        return urljoin(request.host_url, raw.lstrip("/"))
    return raw
