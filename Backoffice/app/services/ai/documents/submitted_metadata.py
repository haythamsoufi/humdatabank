"""Map SubmittedDocument provenance into AIDocument metadata (FDRS and other system imports)."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, Optional

# Form / FDRS document_type labels → canonical AIDocument.document_category values.
_DOCUMENT_TYPE_LABEL_TO_CATEGORY: Dict[str, str] = {
    "annual report": "report",
    "strategic plan": "strategic_plan",
    "audited financial statement": "report",
    "unaudited financial statement": "report",
    "country plan": "country_plan",
    "country report": "country_report",
    "work plan": "work_plan",
    "situation report": "sitrep",
    "assessment": "assessment",
    "policy": "policy",
    "guideline": "guideline",
    "training": "training",
}

_FDRS_SOURCE_ORGANIZATION = "FDRS"
_PERIOD_YEAR_RE = re.compile(r"\b(19[89]\d|20[012]\d)\b")


def is_fdrs_submitted_document(submitted_doc) -> bool:
    return bool(getattr(submitted_doc, "fdrs_import_key", None))


def submitted_document_type_label(submitted_doc) -> str:
    return (
        (getattr(submitted_doc, "document_label", None) or "")
        or (getattr(submitted_doc, "document_type", None) or "")
    ).strip()


def map_document_type_label_to_category(label: str) -> Optional[str]:
    """Map a human document type label to a DOCUMENT_CATEGORIES value."""
    key = (label or "").strip().lower()
    if not key:
        return None
    if key in _DOCUMENT_TYPE_LABEL_TO_CATEGORY:
        return _DOCUMENT_TYPE_LABEL_TO_CATEGORY[key]
    for pattern, category in _DOCUMENT_TYPE_LABEL_TO_CATEGORY.items():
        if pattern in key:
            return category
    return None


def parse_submitted_document_period_date(period: Optional[str]) -> Optional[date]:
    """Best-effort reporting year from SubmittedDocument.period (e.g. '2024' or '2021-2024')."""
    if not period:
        return None
    matches = _PERIOD_YEAR_RE.findall(str(period))
    if not matches:
        return None
    try:
        year = int(matches[-1])
        return date(year, 12, 31)
    except (TypeError, ValueError):
        return None


def build_ai_title_from_submitted_document(submitted_doc) -> str:
    """Human-readable title from structured submission metadata (prefer over raw filename)."""
    doc_type = submitted_document_type_label(submitted_doc)
    country_name = ""
    try:
        country = getattr(submitted_doc, "document_country", None)
        if country and getattr(country, "name", None):
            country_name = country.name.strip()
        elif getattr(submitted_doc, "standalone_linked_display", None):
            country_name = str(submitted_doc.standalone_linked_display).strip()
    except Exception:
        country_name = ""

    period = (getattr(submitted_doc, "period", None) or "").strip()
    filename = (getattr(submitted_doc, "filename", None) or "").strip()

    parts = []
    if doc_type:
        parts.append(doc_type)
    if country_name:
        parts.append(country_name)
    if period and period not in parts:
        if parts:
            return f"{parts[0]} - {parts[1]} ({period})" if len(parts) > 1 else f"{parts[0]} ({period})"
        return period
    if parts:
        return " - ".join(parts)
    return filename or "Document"


def build_submitted_document_metadata_hints(submitted_doc) -> Dict[str, Any]:
    """
    Structured metadata hints for AI import from a SubmittedDocument row.

    FDRS rows (``fdrs_import_key`` set) always use source_organization ``FDRS`` and
    map ``document_type`` to ``document_category``. Other system documents get category
    / language / date hints when available.
    """
    hints: Dict[str, Any] = {}
    if not submitted_doc:
        return hints

    doc_type_label = submitted_document_type_label(submitted_doc)
    category = map_document_type_label_to_category(doc_type_label)
    if category:
        hints["document_category"] = category

    if is_fdrs_submitted_document(submitted_doc):
        hints["source_organization"] = _FDRS_SOURCE_ORGANIZATION

    lang = (getattr(submitted_doc, "language", None) or "").strip().lower()
    if lang:
        hints["document_language"] = lang.split("_")[0].split("-")[0]

    period_date = parse_submitted_document_period_date(getattr(submitted_doc, "period", None))
    if period_date:
        hints["document_date"] = period_date

    title = build_ai_title_from_submitted_document(submitted_doc)
    if title:
        hints["title"] = title

    extra: Dict[str, Any] = {}
    if doc_type_label:
        extra["document_type_label"] = doc_type_label
    if is_fdrs_submitted_document(submitted_doc):
        extra["source_system"] = _FDRS_SOURCE_ORGANIZATION
        period = (getattr(submitted_doc, "period", None) or "").strip()
        if period:
            extra["reporting_period"] = period
    if extra:
        hints["extra_metadata"] = extra

    return hints


def merge_submitted_metadata_hints(
    submitted_doc,
    enriched: Dict[str, Any],
) -> Dict[str, Any]:
    """Overlay structured submission hints onto heuristic enrichment (hints win)."""
    out = dict(enriched or {})
    hints = build_submitted_document_metadata_hints(submitted_doc)
    if not hints:
        return out

    for key in ("document_category", "source_organization", "document_language", "document_date", "title"):
        if hints.get(key) is not None:
            out[key] = hints[key]

    extra = dict(out.get("extra_metadata") or {})
    extra.update(hints.get("extra_metadata") or {})
    if extra:
        out["extra_metadata"] = extra

    return out


def apply_enriched_metadata_to_ai_doc(ai_doc, enriched_meta: Dict[str, Any]) -> None:
    """Persist enrichment (+ merged submission hints) onto an AIDocument."""
    if not ai_doc or not enriched_meta:
        return
    if enriched_meta.get("title"):
        ai_doc.title = enriched_meta["title"]
    if enriched_meta.get("document_date") is not None:
        ai_doc.document_date = enriched_meta.get("document_date")
    if enriched_meta.get("document_language"):
        ai_doc.document_language = enriched_meta["document_language"]
    if enriched_meta.get("document_category"):
        ai_doc.document_category = enriched_meta["document_category"]
    if enriched_meta.get("quality_score") is not None:
        ai_doc.quality_score = enriched_meta["quality_score"]
    if enriched_meta.get("source_organization"):
        ai_doc.source_organization = enriched_meta["source_organization"]
    if enriched_meta.get("extra_metadata"):
        base_extra = dict(getattr(ai_doc, "extra_metadata", None) or {})
        base_extra.update(enriched_meta["extra_metadata"])
        ai_doc.extra_metadata = base_extra


def enrich_ai_document_metadata_from_content(
    ai_doc,
    *,
    filename: str,
    text: str,
    total_pages=None,
    pdf_metadata=None,
    has_tables: bool = False,
    table_extraction_success: bool = True,
    source_url=None,
) -> Dict[str, Any]:
    """Run heuristic enrichment, then overlay linked SubmittedDocument hints when present."""
    from app.services.ai.documents.metadata import enrich_document_metadata

    enriched = enrich_document_metadata(
        title=getattr(ai_doc, "title", None) or filename,
        filename=filename,
        text=text,
        total_pages=total_pages,
        pdf_metadata=pdf_metadata,
        has_tables=has_tables,
        table_extraction_success=table_extraction_success,
        source_url=source_url,
    )
    submitted_doc = getattr(ai_doc, "submitted_document", None)
    if submitted_doc is not None:
        enriched = merge_submitted_metadata_hints(submitted_doc, enriched)
    return enriched


def apply_submitted_document_metadata_to_ai_doc(ai_doc, submitted_doc) -> None:
    """Apply structured hints onto an AIDocument ORM instance (in-place)."""
    if not ai_doc or not submitted_doc:
        return

    hints = build_submitted_document_metadata_hints(submitted_doc)
    if hints.get("title"):
        ai_doc.title = hints["title"]
    if hints.get("document_category"):
        ai_doc.document_category = hints["document_category"]
    if hints.get("source_organization"):
        ai_doc.source_organization = hints["source_organization"]
    if hints.get("document_language"):
        ai_doc.document_language = hints["document_language"]
    if hints.get("document_date"):
        ai_doc.document_date = hints["document_date"]

    derived_country = None
    try:
        derived_country = getattr(submitted_doc, "document_country", None)
    except Exception:
        derived_country = None
    if derived_country and getattr(derived_country, "id", None):
        ai_doc.country_id = int(derived_country.id)
        ai_doc.country_name = getattr(derived_country, "name", None)
    else:
        ai_doc.country_id = None
        ai_doc.country_name = None

    extra = dict(getattr(ai_doc, "extra_metadata", None) or {})
    extra.update(hints.get("extra_metadata") or {})
    if extra:
        ai_doc.extra_metadata = extra
