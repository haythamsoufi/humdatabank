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
# 1989–2099. 2030+ is required for strategic-plan periods such as 2025-2030.
_PERIOD_YEAR_RE = re.compile(r"\b(19[89]\d|20\d{2})\b")
_PERIOD_RANGE_RE = re.compile(
    r"(19[89]\d|20\d{2})\s*[-–—]\s*(19[89]\d|20\d{2})"
)


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
    from app.services.ai.documents.emergency_catalogue import classify_operation_category

    operation = classify_operation_category(key, "")
    if operation:
        return operation
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
    from app.services.ai.documents.emergency_catalogue import category_from_stored_ifrc_type

    ifrc_category = category_from_stored_ifrc_type(ai_doc)
    if ifrc_category:
        enriched["document_category"] = ifrc_category
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

    extra = _metadata_dict(ai_doc)
    extra.update(hints.get("extra_metadata") or {})
    ai_doc.extra_metadata = extra
    refresh_catalog_display(ai_doc)


def _as_text(value) -> str:
    """Return a stripped string. Non-strings (including mocks) become empty."""
    if not isinstance(value, str):
        return ""
    return value.strip()


def _metadata_dict(ai_doc) -> Dict[str, Any]:
    raw = getattr(ai_doc, "extra_metadata", None)
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def years_covered_by_period(period: Optional[str]) -> list[int]:
    """Years a catalog period covers. ``2025-2030`` expands; a single year stays one year."""
    text = _as_text(period)
    if not text:
        return []
    range_match = _PERIOD_RANGE_RE.fullmatch(text)
    if range_match:
        start, end = int(range_match.group(1)), int(range_match.group(2))
        if start > end:
            start, end = end, start
        if end - start <= 40:
            return list(range(start, end + 1))
    return [int(year) for year in _PERIOD_YEAR_RE.findall(text)]


def format_year_span(years: list[int]) -> str:
    """``2023-2025`` when the years are contiguous, otherwise ``2020, 2024``."""
    unique = sorted({int(year) for year in years})
    if not unique:
        return ""
    if len(unique) == 1:
        return str(unique[0])
    if unique[-1] - unique[0] + 1 == len(unique):
        return f"{unique[0]}-{unique[-1]}"
    return ", ".join(str(year) for year in unique)


def _catalog_entries(ai_doc) -> list[Dict[str, Any]]:
    raw = _metadata_dict(ai_doc).get("catalog_entries") or []
    if not isinstance(raw, list):
        return []
    return [dict(entry) for entry in raw if isinstance(entry, dict)]


def _entry_key(entry: Dict[str, Any]) -> Optional[tuple]:
    kind = _as_text(entry.get("kind")) or "submitted"
    if kind == "guidance":
        gid = entry.get("guidance_document_id")
        try:
            return ("guidance", int(gid)) if gid is not None else None
        except (TypeError, ValueError):
            return None
    sid = entry.get("submitted_document_id")
    try:
        return ("submitted", int(sid)) if sid is not None else None
    except (TypeError, ValueError):
        return None


def _period_from_title(title: str) -> str:
    match = re.search(r"\(([^)]+)\)\s*$", title or "")
    if not match:
        return ""
    inner = match.group(1).strip()
    return inner if _PERIOD_YEAR_RE.search(inner) else ""


def _type_from_title(title: str) -> str:
    body = re.sub(r"\s*\([^)]*\)\s*$", "", title or "").strip()
    if " - " not in body:
        return ""
    return body.split(" - ", 1)[0].strip()


def _entry_from_ai_document(ai_doc) -> list[Dict[str, Any]]:
    """Catalog rows implied by an AIDocument that has not stored ``catalog_entries`` yet."""
    if ai_doc is None:
        return []
    extra = _metadata_dict(ai_doc)
    title = _as_text(getattr(ai_doc, "title", None))
    entries: list[Dict[str, Any]] = []
    sid = getattr(ai_doc, "submitted_document_id", None)
    try:
        sid_int = int(sid) if sid is not None else None
    except (TypeError, ValueError):
        sid_int = None
    if sid_int:
        period = _as_text(extra.get("reporting_period")) or _period_from_title(title)
        doc_type = _as_text(extra.get("document_type_label")) or _type_from_title(title)
        entries.append(
            {
                "kind": "submitted",
                "submitted_document_id": sid_int,
                "period": period or None,
                "document_type": doc_type or None,
                "title": title or None,
                "filename": _as_text(getattr(ai_doc, "filename", None)) or None,
                "source_url": _as_text(getattr(ai_doc, "source_url", None)) or None,
                "document_category": _as_text(getattr(ai_doc, "document_category", None)) or None,
            }
        )
    gid = getattr(ai_doc, "guidance_document_id", None)
    try:
        gid_int = int(gid) if gid is not None else None
    except (TypeError, ValueError):
        gid_int = None
    if gid_int:
        entries.append(
            {
                "kind": "guidance",
                "guidance_document_id": gid_int,
                "title": _as_text(getattr(ai_doc, "title", None)) or None,
                "filename": _as_text(getattr(ai_doc, "filename", None)) or None,
            }
        )
    return entries


def _append_catalog_entry(entries: list[Dict[str, Any]], entry: Dict[str, Any]) -> bool:
    key = _entry_key(entry)
    if key is None:
        return False
    for existing in entries:
        if _entry_key(existing) == key:
            for field, value in entry.items():
                if value and not existing.get(field):
                    existing[field] = value
            return False
    entries.append(entry)
    return True


def _ensure_self_catalog_entries(ai_doc) -> list[Dict[str, Any]]:
    entries = _catalog_entries(ai_doc)
    if entries:
        return entries
    entries = []
    for entry in _entry_from_ai_document(ai_doc):
        _append_catalog_entry(entries, entry)
    return entries


def catalog_entry_from_submitted(submitted_doc) -> Optional[Dict[str, Any]]:
    if submitted_doc is None or getattr(submitted_doc, "id", None) is None:
        return None
    try:
        sid = int(submitted_doc.id)
    except (TypeError, ValueError):
        return None
    doc_type = submitted_document_type_label(submitted_doc)
    doc_type = doc_type if isinstance(doc_type, str) else ""
    period = _as_text(getattr(submitted_doc, "period", None))
    filename = _as_text(getattr(submitted_doc, "filename", None))
    title = ""
    try:
        built = build_ai_title_from_submitted_document(submitted_doc)
        title = built if isinstance(built, str) else ""
    except Exception:
        title = filename
    return {
        "kind": "submitted",
        "submitted_document_id": sid,
        "period": period or None,
        "document_type": doc_type.strip() or None,
        "title": title or None,
        "filename": filename or None,
        "source_url": _as_text(getattr(submitted_doc, "source_url", None)) or None,
        "document_category": map_document_type_label_to_category(doc_type) if doc_type else None,
    }


def refresh_catalog_display(ai_doc) -> None:
    """
    When one file was filed under several years or document types, show that on the title.

    A single catalog row keeps the title already stored. Two or more years become
    ``2023-2025`` when contiguous. Two document types are joined (``Annual Report / Strategic Plan``).
    """
    if ai_doc is None:
        return
    entries = [e for e in _catalog_entries(ai_doc) if (_as_text(e.get("kind")) or "submitted") == "submitted"]
    if len(entries) < 2:
        return

    years: list[int] = []
    periods: list[str] = []
    types: list[str] = []
    categories: list[str] = []
    for entry in entries:
        period = _as_text(entry.get("period"))
        if period and period not in periods:
            periods.append(period)
        years.extend(years_covered_by_period(period))
        doc_type = _as_text(entry.get("document_type"))
        if doc_type and doc_type not in types:
            types.append(doc_type)
        category = _as_text(entry.get("document_category"))
        if category and category not in categories:
            categories.append(category)

    span = format_year_span(years)
    country = _as_text(getattr(ai_doc, "country_name", None))
    fallback = _as_text(getattr(ai_doc, "title", None))
    if types and country and span:
        title = f"{' / '.join(types)} - {country} ({span})"
    elif types and country:
        title = f"{' / '.join(types)} - {country}"
    elif types and span:
        title = f"{' / '.join(types)} ({span})"
    elif span and fallback:
        body = re.sub(r"\s*\([^)]*\)\s*$", "", fallback).strip()
        title = f"{body} ({span})" if body else span
    else:
        title = fallback
    if title:
        ai_doc.title = title

    extra = _metadata_dict(ai_doc)
    if years:
        extra["coverage_years"] = sorted(set(years))
        latest = max(years)
        try:
            ai_doc.document_date = date(latest, 12, 31)
        except (TypeError, ValueError):
            pass
    if periods:
        extra["reporting_periods"] = periods
        extra["reporting_period"] = span or periods[0]
    if categories:
        extra["document_categories"] = categories
    ai_doc.extra_metadata = extra


def _remember_source_url(ai_doc, source_url: str) -> None:
    url = _as_text(source_url)
    if not url:
        return
    current = _as_text(getattr(ai_doc, "source_url", None))
    if not current:
        ai_doc.source_url = url
        return
    if current == url:
        return
    extra = _metadata_dict(ai_doc)
    alt_urls = list(extra.get("alt_source_urls") or [])
    if url not in alt_urls:
        alt_urls.append(url)
    extra["alt_source_urls"] = alt_urls
    ai_doc.extra_metadata = extra


def _store_catalog_entries(ai_doc, entries: list[Dict[str, Any]]) -> None:
    extra = _metadata_dict(ai_doc)
    extra["catalog_entries"] = entries
    ai_doc.extra_metadata = extra


def record_submitted_catalog_entry(ai_doc, submitted_doc) -> bool:
    """
    Remember a submitted-document catalog row on an existing AIDocument.

    Used when the file bytes are already embedded for another year, document type,
    or filename. Does not change which submitted document the row is primarily linked to.
    """
    entry = catalog_entry_from_submitted(submitted_doc)
    if ai_doc is None or entry is None:
        return False
    entries = _ensure_self_catalog_entries(ai_doc)
    added = _append_catalog_entry(entries, entry)
    _store_catalog_entries(ai_doc, entries)
    _remember_source_url(ai_doc, entry.get("source_url") or "")
    refresh_catalog_display(ai_doc)
    return added


def record_guidance_catalog_entry(ai_doc, guidance) -> bool:
    """Remember a guidance file that has the same bytes as an existing AIDocument."""
    if ai_doc is None or guidance is None or getattr(guidance, "id", None) is None:
        return False
    try:
        gid = int(guidance.id)
    except (TypeError, ValueError):
        return False
    entry = {
        "kind": "guidance",
        "guidance_document_id": gid,
        "title": _as_text(getattr(guidance, "title", None)) or _as_text(getattr(guidance, "filename", None)) or None,
        "filename": _as_text(getattr(guidance, "filename", None)) or None,
        "owner_key": _as_text(getattr(guidance, "owner_key", None)) or None,
    }
    entries = _ensure_self_catalog_entries(ai_doc)
    added = _append_catalog_entry(entries, entry)
    _store_catalog_entries(ai_doc, entries)
    refresh_catalog_display(ai_doc)
    return added


def absorb_catalog_from_ai_document(keeper, loser) -> None:
    """Copy catalog rows off a duplicate AIDocument before it is deleted."""
    if keeper is None or loser is None:
        return
    entries = _ensure_self_catalog_entries(keeper)
    for entry in _catalog_entries(loser):
        _append_catalog_entry(entries, entry)
    for entry in _entry_from_ai_document(loser):
        _append_catalog_entry(entries, entry)
    _store_catalog_entries(keeper, entries)
    loser_url = _as_text(getattr(loser, "source_url", None))
    if loser_url:
        _remember_source_url(keeper, loser_url)
    refresh_catalog_display(keeper)
