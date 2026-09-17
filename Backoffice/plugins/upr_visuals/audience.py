"""Classify attached UPR narratives as internal-only or public-facing.

Internal drafts (GO mid-year PDFs, files stamped Internal) are not prepared
for publication. Public files are editor-ready Design packages (IFRC network
annual report / country plan, Appeal code). Internal signals win; if neither
side is conclusive the safer default is internal.
"""

from __future__ import annotations

import re
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

INTERNAL_COVER_BANNER = "INTERNAL — not for public use"
# Extra cover-header height in PDF points when the yellow banner is present.
INTERNAL_COVER_BANNER_H = 22.0

_INTERNAL_VALUES = frozenset({"internal", "internal_only", "internal-only", "not_public", "not-public"})
_PUBLIC_VALUES = frozenset({"public", "external", "public_facing", "public-facing"})
_AUTO_VALUES = frozenset({"", "auto", "detect", "default"})

_INTERNAL_FILENAME = re.compile(
    r"(?:^|[\s_\-.])internal(?:[\s_\-.]|$)|not[\s_\-]*for[\s_\-]*public",
    re.I,
)
_PUBLIC_FILENAME = re.compile(r"(?:^|[\s_\-])design(?:[\s_\-.]|$)", re.I)
_INTERNAL_LINE = re.compile(r"(?im)^\s*internal(?:\s+use\s+only)?\s*$")
_INTERNAL_PHRASE = re.compile(
    r"(?i)(?:internal\s+use\s+only|not\s+for\s+(?:public|external)(?:\s+use|\s+distribution)?)"
)
_PUBLIC_PHRASE = re.compile(
    r"(?i)ifrc\s+network\s+(?:annual\s+report|country\s+plan)|appeal\s+code\s*:"
)


def parse_narrative_audience(value: str | None) -> str | None:
    """Return ``internal`` / ``public``, or ``None`` when the caller wants auto-detect."""
    raw = str(value or "").strip().lower().replace(" ", "_")
    if raw in _AUTO_VALUES:
        return None
    if raw in _INTERNAL_VALUES:
        return "internal"
    if raw in _PUBLIC_VALUES:
        return "public"
    return None


def is_internal_narrative(meta: dict[str, Any] | None) -> bool:
    return str((meta or {}).get("narrative_audience") or "").strip().lower() == "internal"


def apply_narrative_audience(payload: dict[str, Any] | None, audience: str | None) -> dict[str, Any]:
    payload = dict(payload or {})
    meta = dict(payload.get("meta") or {})
    meta["narrative_audience"] = "internal" if str(audience or "").strip().lower() == "internal" else "public"
    payload["meta"] = meta
    return payload


def resolve_narrative_audience(
    requested: str | None = None,
    *,
    filename: str = "",
    data: bytes | None = None,
    blocks: list | None = None,
) -> str:
    parsed = parse_narrative_audience(requested)
    if parsed:
        return parsed
    return detect_narrative_audience(filename=filename, data=data or b"", blocks=blocks)


def detect_narrative_audience(
    *,
    filename: str = "",
    data: bytes | None = None,
    blocks: list | None = None,
) -> str:
    name = Path(filename or "").name
    internal_name = bool(_INTERNAL_FILENAME.search(name))
    public_name = bool(_PUBLIC_FILENAME.search(name))
    preview = _preview_text(filename=name, data=data or b"", blocks=blocks)
    internal_text = bool(_INTERNAL_LINE.search(preview) or _INTERNAL_PHRASE.search(preview))
    public_text = bool(_PUBLIC_PHRASE.search(preview))
    if internal_name or internal_text:
        return "internal"
    if public_name or public_text:
        return "public"
    return "internal"


def _preview_text(*, filename: str, data: bytes, blocks: list | None) -> str:
    parts = [filename]
    if blocks:
        for row in blocks[:50]:
            if isinstance(row, dict):
                parts.append(str(row.get("text") or ""))
            else:
                parts.append(str(row))
        return "\n".join(parts)
    if not data:
        return "\n".join(parts)
    if data.startswith(b"%PDF"):
        parts.append(_pdf_preview(data))
    elif data.startswith(b"PK"):
        parts.append(_docx_preview(data))
    return "\n".join(parts)


def _pdf_preview(data: bytes) -> str:
    try:
        import fitz

        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return ""
    try:
        chunks: list[str] = []
        for index in range(min(2, doc.page_count)):
            chunks.append(doc.load_page(index).get_text("text") or "")
        return "\n".join(chunks)
    except Exception:
        return ""
    finally:
        doc.close()


def _docx_preview(data: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            if "word/document.xml" not in zf.namelist():
                return ""
            xml = zf.read("word/document.xml")[:120000]
    except Exception:
        return ""
    try:
        text = xml.decode("utf-8", "ignore")
    except Exception:
        return ""
    return re.sub(r"<[^>]+>", " ", text)
