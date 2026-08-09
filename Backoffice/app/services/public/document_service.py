"""Compact public document search for Custom GPT and other external integrations."""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any, Dict, List, Optional

from flask import current_app
from sqlalchemy import text
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import AIDocument, AIDocumentChunk
from app.models.enums import AIDocumentProcessingStatusValue
from app.services.ai.documents.country_detection import detect_country_id_and_name
from app.services.ai.documents.vector_store import AIVectorStore, VectorStoreError
from app.services.upr.query_detection import (
    query_prefers_upr_documents,
    query_requests_multi_year_documents,
)

PUBLIC_DOC_DEFAULT_TOP_K = 8
PUBLIC_DOC_MAX_TOP_K = 12
PUBLIC_DOC_DEFAULT_MIN_SCORE = 0.25
PUBLIC_DOC_MAX_CONTENT_CHARS = 1200
PUBLIC_DOC_FULL_COVERAGE_MAX_DOCS = 250
PUBLIC_DOC_FULL_COVERAGE_CONTENT_CHARS = 800
PUBLIC_DOC_FULL_COVERAGE_CHUNKS_PER_DOC = 20
PUBLIC_DOC_ACTION_MAX_RESPONSE_CHARS = 95_000
PUBLIC_DOC_FULL_COVERAGE_DEFAULT_PER_PAGE = 80
# When a country filter narrows scope to this many documents or fewer, search per
# document (batched) instead of one global vector query. The global path uses
# _country_id_filter's geographic_scope='global' OR, which prevents pgvector from
# using the HNSW index efficiently and has timed out at the 18s statement_timeout
# on production for single-country MCP/report requests.
PUBLIC_DOC_SCOPED_SEARCH_MAX_DOCS = 80
# Minimum boost-free (vector/keyword) relevance a chunk must have, even if a source_boost
# (see _passes_relevance_floor) would otherwise let it clear min_score on its own.
PUBLIC_DOC_MIN_RAW_RELEVANCE = 0.05
# Multi-country ("all" or a large country_ids list) search batches documents into groups of
# this size and issues one batched per-document query per group server-side, instead of
# erroring past PUBLIC_DOC_FULL_COVERAGE_MAX_DOCS and pushing batching onto the caller.
PUBLIC_DOC_MULTI_COUNTRY_BATCH_SIZE = PUBLIC_DOC_FULL_COVERAGE_MAX_DOCS
# Hard ceiling on number of batches (documents-in-scope / batch_size) for one call, so a
# pathologically large scope still fails fast instead of issuing dozens of sequential queries.
PUBLIC_DOC_MULTI_COUNTRY_MAX_BATCHES = 20
# Chunk-context tool (databank_get_chunk_context): caps before/after so a caller can't
# use it to walk an entire document one window at a time.
PUBLIC_DOC_CHUNK_CONTEXT_MAX_BEFORE_AFTER = 5
PUBLIC_DOC_CHUNK_CONTEXT_MAX_CONTENT_CHARS = 3000

logger = logging.getLogger(__name__)


class PublicDocumentSearchUnavailable(Exception):
    """Transient embedding/DB failure during public document search (retry-worthy)."""


class PublicDocumentScopeTooLarge(ValueError):
    """Too many documents in scope for the requested search mode."""


_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def _dedupe_rows_by_chunk_id(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Final safety net: keep the highest-scoring row per chunk_id."""
    best_by_chunk: Dict[Any, Dict[str, Any]] = {}
    for row in rows:
        chunk_id = row.get("chunk_id")
        if chunk_id is None:
            continue
        existing = best_by_chunk.get(chunk_id)
        if existing is None or _chunk_score(row) > _chunk_score(existing):
            best_by_chunk[chunk_id] = row
    if not best_by_chunk:
        return rows
    seen: set[Any] = set()
    deduped: List[Dict[str, Any]] = []
    for row in rows:
        chunk_id = row.get("chunk_id")
        if chunk_id is None:
            deduped.append(row)
            continue
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        deduped.append(best_by_chunk[chunk_id])
    return deduped


def _phrase_words(phrase: str | None) -> List[str]:
    return [w for w in re.split(r"\s+", (phrase or "").strip()) if w]


def _literal_phrase_pattern(phrase: str) -> "re.Pattern[str] | None":
    """
    Compile a case-insensitive, whitespace-tolerant regex requiring *phrase*'s words to
    appear literally and adjacently (in order), independent of the Postgres tsvector/
    tsquery lexeme match used as a fast pre-filter in ``AIVectorStore._apply_require_phrase_filter``.

    ``phraseto_tsquery`` matches on lexeme *positions*, and Postgres's default parser can
    assign a hyphenated compound word (e.g. "post-employment") both a combined lexeme and
    decomposed-part lexemes — a theoretical edge case where an unrelated compound word could
    satisfy a positional adjacency check. This regex is a literal-text backstop so
    ``require_phrase`` never returns a chunk a human wouldn't recognize as containing the
    phrase, regardless of tokenizer edge cases.
    """
    words = _phrase_words(phrase)
    if not words:
        return None
    pattern = r"\b" + r"\s+".join(re.escape(w) for w in words) + r"\b"
    return re.compile(pattern, re.IGNORECASE)


def _content_contains_literal_phrase(content: str | None, phrase: str) -> bool:
    """True if *content* literally contains *phrase* (case-insensitive, whitespace-tolerant)."""
    regex = _literal_phrase_pattern(phrase)
    if regex is None:
        return True
    if not content:
        return False
    return regex.search(content) is not None


def _filter_rows_by_literal_phrase(
    rows: List[Dict[str, Any]], phrase: str
) -> tuple[List[Dict[str, Any]], int]:
    """
    Defense-in-depth for ``require_phrase``: drop any row whose content does not literally
    contain the phrase even though it passed the DB-side FTS filter. Returns
    ``(kept_rows, dropped_count)`` so callers can surface a transparency note.
    """
    regex = _literal_phrase_pattern(phrase)
    if regex is None:
        return rows, 0
    kept: List[Dict[str, Any]] = []
    dropped = 0
    for row in rows:
        content = row.get("content")
        if content and regex.search(content):
            kept.append(row)
        else:
            dropped += 1
    if dropped:
        logger.warning(
            "require_phrase %r: dropped %d chunk(s) that passed the FTS phrase filter "
            "but failed the literal-text check (chunk_ids=%s)",
            phrase,
            dropped,
            [r.get("chunk_id") for r in rows if r not in kept][:20],
        )
    return kept, dropped


def _snippet_around_phrase(content: str | None, phrase: str, max_chars: int) -> str:
    """
    Truncate *content* to *max_chars*, centered on the first literal occurrence of
    *phrase* instead of the head of the chunk.

    When a chunk only qualified because of ``require_phrase``, a plain head-truncation
    can cut the preview before the very text that justified the match, making the hit
    look unverifiable (or, worse, look like a false positive) to the caller. Centering the
    window on the match keeps the justifying text visible.
    """
    raw = (content or "").strip()
    if len(raw) <= max_chars:
        return raw
    regex = _literal_phrase_pattern(phrase)
    match = regex.search(raw) if regex else None
    if not match:
        return _truncate(raw, max_chars)

    start_idx, end_idx = match.span()
    context_budget = max(0, max_chars - (end_idx - start_idx))
    before = context_budget // 2
    window_start = max(0, start_idx - before)
    window_end = min(len(raw), window_start + max_chars)
    if window_end - window_start < max_chars:
        window_start = max(0, window_end - max_chars)

    snippet = raw[window_start:window_end].strip()
    prefix = "…" if window_start > 0 else ""
    suffix = "…" if window_end < len(raw) else ""
    return f"{prefix}{snippet}{suffix}"


def _parse_country_ids_param(country_ids: str | None) -> tuple[List[int] | None, bool]:
    """
    Parse country_ids query param.

    Returns (ids, is_all). ``is_all`` is True when the caller requested every country.
    """
    raw = (country_ids or "").strip()
    if not raw:
        return None, False
    if raw.lower() == "all":
        return None, True
    parsed: List[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            parsed.append(int(part))
        except ValueError as exc:
            raise ValueError(f"Invalid country_ids entry: {part!r}") from exc
    if not parsed:
        raise ValueError("country_ids must be a comma-separated list of ids or 'all'")
    return sorted(set(parsed)), False


def _group_slim_chunks_by_country(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group slim chunks by primary country name for multi-country fan-out responses."""
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for chunk in chunks:
        countries = chunk.get("countries") or []
        label = countries[0] if countries else "Unknown"
        grouped.setdefault(label, []).append(chunk)
    out: List[Dict[str, Any]] = []
    for country_name in sorted(grouped.keys(), key=str.lower):
        country_chunks = grouped[country_name]
        country_chunks.sort(key=lambda c: c.get("score") or 0.0, reverse=True)
        out.append(
            {
                "country": country_name,
                "count": len(country_chunks),
                "chunks": country_chunks,
            }
        )
    return out


def _truncate(text: str | None, max_chars: int) -> str:
    raw = (text or "").strip()
    if len(raw) <= max_chars:
        return raw
    return raw[: max_chars - 1].rstrip() + "…"


def _chunk_score(row: Dict[str, Any]) -> float:
    for key in ("combined_score", "similarity_score", "keyword_score"):
        val = row.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return 0.0


def _passes_relevance_floor(row: Dict[str, Any], min_score: float) -> bool:
    """
    Return True when *row* clears ``min_score`` on genuine text relevance, not only
    on a non-relevance ranking boost.

    ``combined_score`` (see ``AIVectorStore._combine_search_results``) can include a
    fixed ``source_boost`` (e.g. +0.25 for system-uploaded documents) that has nothing
    to do with how well the chunk matches the query. A chunk with ~zero vector/keyword
    similarity can still clear a low ``min_score`` on that boost alone, which is exactly
    the kind of near-irrelevant hit this filter should be dropping. Require the
    boost-free portion of the score to also clear a small floor.
    """
    score = _chunk_score(row)
    if score < min_score:
        return False
    source_boost = row.get("source_boost")
    if not source_boost:
        return True
    try:
        raw_relevance = score - float(source_boost)
    except (TypeError, ValueError):
        return True
    return raw_relevance >= PUBLIC_DOC_MIN_RAW_RELEVANCE


def _document_source_url(document: AIDocument | Dict[str, Any] | None) -> str | None:
    if document is None:
        return None
    if isinstance(document, dict):
        raw = document.get("source_url")
    else:
        raw = getattr(document, "source_url", None)
    url = (raw or "").strip()
    return url or None


def _ai_document_has_local_file(document: AIDocument) -> bool:
    from app.routes.ai_documents.helpers import _ai_doc_source_ready

    return bool(getattr(document, "storage_path", None) and _ai_doc_source_ready(document))


def _public_document_link_fields(
    document_id: int | None,
    *,
    source_url: str | None = None,
    has_local_file: bool = False,
) -> Dict[str, str | None]:
    """Build shareable links: external source_url and/or Databank-hosted download."""
    download_url = None
    if document_id and has_local_file:
        try:
            from flask import url_for

            download_url = url_for(
                "api.public_download_ai_document",
                document_id=int(document_id),
                _external=True,
            )
        except RuntimeError:
            download_url = None
    document_url = source_url or download_url
    return {
        "source_url": source_url,
        "download_url": download_url,
        "document_url": document_url,
    }


def _load_public_ai_document(document_id: int) -> AIDocument:
    completed = AIDocumentProcessingStatusValue.completed.value
    doc = AIDocument.query.filter(
        AIDocument.id == int(document_id),
        AIDocument.is_public.is_(True),
        AIDocument.searchable.is_(True),
        AIDocument.processing_status == completed,
    ).first()
    if not doc:
        raise ValueError("Document not found or not public")
    return doc


def _document_scope_entry(document: AIDocument, *, check_local_file: bool = True) -> Dict[str, Any]:
    doc_id = int(document.id)
    source_url = _document_source_url(document)
    entry = {
        "document_id": doc_id,
        "document_title": document.title,
        "countries": _document_country_names(document),
    }
    # Skip the local-file/blob existence check (a storage round-trip — a network call on
    # Azure Blob) when an external source_url is already available, or when the caller
    # passes check_local_file=False because a resolved download link isn't needed (e.g. a
    # document with no matching chunk in full-coverage search — see without_hits below).
    has_local_file = False if (source_url or not check_local_file) else _ai_document_has_local_file(document)
    entry.update(
        _public_document_link_fields(
            doc_id,
            source_url=source_url,
            has_local_file=has_local_file,
        )
    )
    return entry


def slim_public_document_chunk(
    row: Dict[str, Any],
    *,
    max_content_chars: int,
    require_phrase: str | None = None,
) -> Dict[str, Any]:
    """Project a vector-store hit to a compact shape for Custom GPT Actions."""
    countries = row.get("document_countries") or []
    country_names = [c.get("name") for c in countries if isinstance(c, dict) and c.get("name")]
    if not country_names and row.get("document_country_name"):
        country_names = [row["document_country_name"]]

    doc_id = row.get("document_id")
    source_url = _document_source_url(row)
    links = _public_document_link_fields(
        int(doc_id) if doc_id is not None else None,
        source_url=source_url,
        has_local_file=bool(row.get("has_local_file")),
    )

    phrase = (require_phrase or "").strip()
    content = (
        _snippet_around_phrase(row.get("content"), phrase, max_content_chars)
        if phrase
        else _truncate(row.get("content"), max_content_chars)
    )

    return {
        "chunk_id": row.get("chunk_id"),
        "document_id": doc_id,
        "document_title": row.get("document_title"),
        "document_filename": row.get("document_filename"),
        "document_date": row.get("document_date"),
        "document_category": row.get("document_category"),
        "document_language": row.get("document_language"),
        "countries": country_names,
        "page_number": row.get("page_number"),
        "section_title": row.get("section_title"),
        "content": content,
        "score": round(_chunk_score(row), 4),
        "source_organization": row.get("source_organization"),
        **links,
    }


def _resolve_country_filter(
    query: str,
    *,
    country_name: str | None,
    country_id: int | None,
) -> Dict[str, Any]:
    filters: Dict[str, Any] = {}
    if country_id:
        filters["country_id"] = int(country_id)
        return filters
    if country_name:
        filters["country_name"] = country_name.strip()
        return filters

    detected_id, detected_name = detect_country_id_and_name(
        filename=None,
        title=None,
        text=query,
        max_text_chars=500,
    )
    if detected_id:
        filters["country_id"] = int(detected_id)
    elif detected_name:
        filters["country_name"] = detected_name
    return filters


def _build_search_filters(
    query: str,
    *,
    country_name: str | None = None,
    country_id: int | None = None,
    country_ids: List[int] | None = None,
    country_ids_all: bool = False,
    file_type: str | None = None,
    year: int | None = None,
    require_phrase: str | None = None,
) -> Dict[str, Any] | None:
    filters: Dict[str, Any] = {}
    if country_ids:
        filters["country_ids"] = country_ids
    elif not country_ids_all:
        filters.update(_resolve_country_filter(query, country_name=country_name, country_id=country_id))

    if file_type:
        filters["file_type"] = file_type.strip().lower()

    if query_prefers_upr_documents(query):
        filters["is_api_import"] = True
        filters["is_system_document"] = False

    if year:
        filters["date_range"] = {"min": f"{year}-01-01", "max": f"{year}-12-31"}

    phrase = (require_phrase or "").strip()
    if phrase:
        filters["require_phrase"] = phrase

    return filters or None


def _extract_year(query: str) -> int | None:
    matches = _YEAR_RE.findall(query or "")
    if not matches:
        return None
    try:
        return int(matches[-1])
    except (TypeError, ValueError):
        return None


def _public_searchable_document_ids(document_ids: set[int]) -> set[int]:
    """Return document IDs that are publicly searchable (is_public + completed + searchable)."""
    if not document_ids:
        return set()
    completed = AIDocumentProcessingStatusValue.completed.value
    rows = (
        AIDocument.query.filter(
            AIDocument.id.in_(document_ids),
            AIDocument.is_public.is_(True),
            AIDocument.searchable.is_(True),
            AIDocument.processing_status == completed,
        )
        .with_entities(AIDocument.id)
        .all()
    )
    return {int(row[0]) for row in rows}


def _document_country_names(document: AIDocument) -> List[str]:
    names: List[str] = []
    try:
        for country in document.countries or []:
            if country and country.name:
                names.append(country.name)
    except Exception:
        pass
    if not names and document.country_name:
        names.append(document.country_name.strip())
    elif document.country and document.country.name and document.country.name not in names:
        names.append(document.country.name)
    return names


def _apply_scope_filters_to_query(query, filters: Dict[str, Any] | None):
    """Apply the same document-level filters used by vector search."""
    if not filters:
        return query

    if filters.get("country_ids"):
        query = query.filter(AIVectorStore._country_ids_filter(list(filters["country_ids"])))
    elif filters.get("country_id"):
        query = query.filter(AIVectorStore._country_id_filter(int(filters["country_id"])))
    if filters.get("country_name"):
        query = query.filter(AIVectorStore._country_name_filter(filters["country_name"]))
    if filters.get("file_type"):
        query = query.filter(AIDocument.file_type == filters["file_type"])
    if filters.get("user_id"):
        query = query.filter(AIDocument.user_id == filters["user_id"])
    if "is_api_import" in filters:
        if filters.get("is_api_import") is True:
            query = query.filter(AIDocument.source_url.isnot(None))
        elif filters.get("is_api_import") is False:
            query = query.filter(AIDocument.source_url.is_(None))
    if "is_system_document" in filters:
        if filters.get("is_system_document") is True:
            query = query.filter(AIDocument.submitted_document_id.isnot(None))
        elif filters.get("is_system_document") is False:
            query = query.filter(AIDocument.submitted_document_id.is_(None))
    if filters.get("workflow_role"):
        role_val = str(filters["workflow_role"]).strip()
        role_json = json.dumps([role_val])
        query = query.filter(
            text("(ai_documents.extra_metadata->'roles')::jsonb @> CAST(:workflow_role_json AS jsonb)").bindparams(
                workflow_role_json=role_json
            )
        )
    if filters.get("date_range"):
        dr = filters["date_range"]
        min_d, max_d = None, None
        if isinstance(dr, (list, tuple)) and len(dr) >= 2:
            min_d, max_d = dr[0], dr[1]
        elif isinstance(dr, dict):
            min_d, max_d = dr.get("min"), dr.get("max")
        if min_d is not None:
            d = min_d if isinstance(min_d, date) else date.fromisoformat(str(min_d)[:10])
            query = query.filter(AIDocument.document_date >= d)
        if max_d is not None:
            d = max_d if isinstance(max_d, date) else date.fromisoformat(str(max_d)[:10])
            query = query.filter(AIDocument.document_date <= d)
    return query


def _document_year(document: AIDocument) -> int:
    if document.document_date:
        return int(document.document_date.year)
    for source in (document.title, document.filename):
        years = _YEAR_RE.findall(source or "")
        if years:
            return max(int(y) for y in years)
    if document.processed_at:
        return int(document.processed_at.year)
    if document.created_at:
        return int(document.created_at.year)
    return 0


def _document_type_key(document: AIDocument, query: str) -> str:
    title = (document.title or "").lower()
    filename = (document.filename or "").lower()
    category = (document.document_category or "").lower()
    extra = document.extra_metadata if isinstance(document.extra_metadata, dict) else {}
    label = str(extra.get("document_type_label") or "").lower()
    combined = f"{title} {filename} {label} {category}"

    if re.search(r"\bmid[-\s]?year|\bmyr\b", combined, re.IGNORECASE):
        return "midyear_report"
    if re.search(r"\bannual\s+report|\bar\b", combined, re.IGNORECASE):
        return "annual_report"
    if re.search(r"\bunified\s+plan|\bupl\b|\bupr\b", combined, re.IGNORECASE):
        return "unified_plan"
    if query_prefers_upr_documents(query):
        return "unified_plan"
    if category:
        return category
    return "other"


def _document_recency_key(document: AIDocument) -> tuple:
    doc_date = document.document_date or date.min
    processed = document.processed_at or document.created_at
    processed_ord = processed.date() if processed else date.min
    return (_document_year(document), doc_date, processed_ord, int(document.id))


def _should_prioritize_latest_per_country(
    query: str,
    filters: Dict[str, Any] | None,
    *,
    latest_per_country: bool | None,
) -> bool:
    if latest_per_country is not None:
        return bool(latest_per_country)
    if query_requests_multi_year_documents(query):
        return False
    return True


def prioritize_latest_documents_per_country(
    documents: List[AIDocument],
    query: str,
    *,
    enabled: bool,
) -> tuple[List[AIDocument], Dict[str, Any]]:
    """Keep the newest document per (country, document-type) group for snapshot queries."""
    if not enabled or len(documents) <= 1:
        return documents, {"latest_per_country_applied": False}

    groups: Dict[tuple[str, str], List[AIDocument]] = {}
    for doc in documents:
        type_key = _document_type_key(doc, query)
        country_keys = [name.strip().lower() for name in _document_country_names(doc)] or ["__unknown__"]
        for country_key in country_keys:
            groups.setdefault((country_key, type_key), []).append(doc)

    selected_ids: set[int] = set()
    superseded: List[Dict[str, Any]] = []
    for (_country_key, type_key), docs in groups.items():
        unique_docs = {int(doc.id): doc for doc in docs}
        docs = list(unique_docs.values())
        if len(docs) == 1:
            selected_ids.add(int(docs[0].id))
            continue
        best = max(docs, key=_document_recency_key)
        selected_ids.add(int(best.id))
        for doc in docs:
            if int(doc.id) == int(best.id):
                continue
            superseded.append(
                {
                    "document_id": int(doc.id),
                    "document_title": doc.title,
                    "countries": _document_country_names(doc),
                    "document_type": type_key,
                    "document_year": _document_year(doc),
                    "source_url": _document_source_url(doc),
                    "superseded_by_document_id": int(best.id),
                    "superseded_by_title": best.title,
                }
            )

    selected = [doc for doc in documents if int(doc.id) in selected_ids]
    selected.sort(key=lambda doc: (doc.title or "").lower())
    return selected, {
        "latest_per_country_applied": True,
        "documents_before_dedupe": len(documents),
        "documents_after_dedupe": len(selected),
        "superseded_documents": sorted(
            superseded,
            key=lambda item: ((item.get("countries") or [""])[0], item.get("document_year") or 0),
        ),
    }


def list_public_documents_in_scope(filters: Dict[str, Any] | None) -> List[AIDocument]:
    """List public, searchable, completed documents matching scope filters."""
    completed = AIDocumentProcessingStatusValue.completed.value
    query = AIDocument.query.filter(
        AIDocument.is_public.is_(True),
        AIDocument.searchable.is_(True),
        AIDocument.processing_status == completed,
    )
    # Eager-load the singular `country` relation (default lazy='select'): without this,
    # _document_country_names()/_document_scope_entry() trigger one extra SELECT per
    # document that lacks a legacy country_name (N+1 across up to PUBLIC_DOC_CATALOG_MAX_DOCS
    # documents). `countries` (M2M) is already lazy='selectin' on the model and batches fine.
    query = query.options(joinedload(AIDocument.country))
    query = _apply_scope_filters_to_query(query, filters)
    return query.order_by(AIDocument.title).all()


DOCUMENT_TYPE_CHOICES = ("annual_report", "unified_plan", "midyear_report", "other")
PUBLIC_DOC_CATALOG_MAX_DOCS = 2000


def _catalog_scope_filters(
    *,
    country_id: Optional[int] = None,
    country_name: Optional[str] = None,
    file_type: Optional[str] = None,
) -> Dict[str, Any] | None:
    filters: Dict[str, Any] = {}
    if country_id:
        filters["country_id"] = int(country_id)
    elif country_name:
        filters["country_name"] = country_name.strip()
    if file_type:
        filters["file_type"] = file_type.strip().lower()
    return filters or None


def _catalog_document_entry(
    document: AIDocument,
    *,
    type_key: str,
    year: int,
    include_links: bool = True,
) -> Dict[str, Any]:
    doc_id = int(document.id)
    entry: Dict[str, Any] = {
        "document_id": doc_id,
        "document_title": document.title,
        "document_type": type_key,
        "year": year or None,
        "countries": _document_country_names(document),
    }
    if include_links:
        source_url = _document_source_url(document)
        has_local_file = False
        if not source_url:
            has_local_file = _ai_document_has_local_file(document)
        entry.update(
            _public_document_link_fields(
                doc_id,
                source_url=source_url,
                has_local_file=has_local_file,
            )
        )
    return entry


def catalog_public_documents(
    *,
    document_type: str = "",
    year: Optional[int] = None,
    country_id: Optional[int] = None,
    country_name: Optional[str] = None,
    file_type: str = "",
    include_documents: bool = True,
) -> Dict[str, Any]:
    """
    Inventory public documents by type / year / country — counts, not semantic search.

    Answers questions like "how many countries submitted an annual report (FDRS) or a
    Unified Plan (UPR) for 2024, or across all years?" directly from document metadata,
    without running vector search. Scope is identical to :func:`search_public_documents`:
    only documents with ``is_public=True``, ``searchable=True`` and
    ``processing_status=completed`` are counted (see :func:`list_public_documents_in_scope`).
    Use :func:`search_public_documents` instead for narrative Q&A over document content.
    """
    normalized_type = (document_type or "").strip().lower()
    if normalized_type in ("", "all"):
        normalized_type = ""
    elif normalized_type not in DOCUMENT_TYPE_CHOICES:
        raise ValueError(
            f"Unknown document_type {document_type!r}. "
            f"Use one of: {', '.join(DOCUMENT_TYPE_CHOICES)}, or omit for all types."
        )

    filters = _catalog_scope_filters(country_id=country_id, country_name=country_name, file_type=file_type)
    documents = list_public_documents_in_scope(filters)

    if len(documents) > PUBLIC_DOC_CATALOG_MAX_DOCS:
        raise ValueError(
            f"Too many public documents in scope ({len(documents)}). "
            "Narrow with country_id, country_name, or document_type."
        )

    entries: List[Dict[str, Any]] = []
    for doc in documents:
        type_key = _document_type_key(doc, "")
        if normalized_type and type_key != normalized_type:
            continue
        doc_year = _document_year(doc)
        if year and doc_year != int(year):
            continue
        entries.append(
            _catalog_document_entry(
                doc,
                type_key=type_key,
                year=doc_year,
                include_links=include_documents,
            )
        )

    by_type: Dict[str, int] = {}
    by_year_buckets: Dict[int, Dict[str, Any]] = {}
    by_country_buckets: Dict[str, Dict[str, Any]] = {}
    all_country_names: set[str] = set()

    for entry in entries:
        by_type[entry["document_type"]] = by_type.get(entry["document_type"], 0) + 1

        entry_year = entry["year"] or 0
        year_bucket = by_year_buckets.setdefault(
            entry_year, {"year": entry["year"], "document_count": 0, "_countries": set()}
        )
        year_bucket["document_count"] += 1

        countries = entry["countries"] or ["Unknown / regional"]
        for country in countries:
            year_bucket["_countries"].add(country)
            all_country_names.add(country)
            country_bucket = by_country_buckets.setdefault(country, {"country": country, "documents": []})
            country_bucket["documents"].append(entry)

    by_year = [
        {
            "year": bucket["year"],
            "document_count": bucket["document_count"],
            "countries_count": len(bucket["_countries"]),
        }
        for bucket in by_year_buckets.values()
    ]
    by_year.sort(key=lambda bucket: (bucket["year"] is not None, bucket["year"] or 0), reverse=True)

    by_country = sorted(by_country_buckets.values(), key=lambda bucket: bucket["country"].lower())

    notes = [
        "Counts only documents marked public in the AI Knowledge Base "
        "(is_public=True, searchable=True, processing_status=completed).",
        "document_type is inferred from title/filename/category — use searchPublicDocuments "
        "to verify ambiguous cases from the document text itself.",
        "A country is counted once per year it has a matching public document, even if it "
        "also appears in other years (see by_year for the yearly breakdown).",
    ]
    if not include_documents:
        for bucket in by_country:
            bucket["documents"] = []
        notes.append("include_documents=false: per-document listings omitted; counts are still complete.")

    payload: Dict[str, Any] = {
        "filters_applied": {
            "document_type": normalized_type or "all",
            "year": year,
            "country_id": country_id,
            "country_name": country_name,
            "file_type": file_type or None,
        },
        "visibility": "public_only",
        "total_documents": len(entries),
        "countries_count": len(all_country_names),
        "by_type": by_type,
        "by_year": by_year,
        "by_country": by_country,
        "notes": notes,
    }

    # Trim per-country document listings (not the counts) if the response would exceed the
    # Custom GPT Actions response-size limit — mirrors the full_coverage trimming above.
    trimmed = False
    while include_documents and any(b["documents"] for b in by_country) and _estimate_json_chars(payload) > PUBLIC_DOC_ACTION_MAX_RESPONSE_CHARS:
        trimmed = True
        for bucket in by_country:
            if bucket["documents"]:
                bucket["documents"] = bucket["documents"][:-1]

    if trimmed:
        payload["notes"] = notes + [
            "Document listings truncated to fit the response size limit; counts above remain accurate."
        ]

    return payload


def filter_rows_to_public_documents(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Defense-in-depth: drop any chunk whose parent document is not public/searchable.

    Vector search already applies permission filters; this re-validates before responding
    to unauthenticated Custom GPT callers.
    """
    doc_ids = {
        int(row["document_id"])
        for row in rows
        if row.get("document_id") is not None
    }
    allowed = _public_searchable_document_ids(doc_ids)
    return [
        row
        for row in rows
        if row.get("document_id") is not None and int(row["document_id"]) in allowed
    ]


def _estimate_json_chars(payload: Dict[str, Any]) -> int:
    return len(json.dumps(payload, ensure_ascii=False, default=str))


def _paginate_full_coverage_hits(
    hits: List[Dict[str, Any]],
    *,
    page: int,
    per_page: int,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    total = len(hits)
    per_page = max(1, int(per_page))
    page = max(1, int(page))
    total_pages = max(1, (total + per_page - 1) // per_page) if total else 1
    if page > total_pages:
        page = total_pages
    start = (page - 1) * per_page
    page_hits = hits[start : start + per_page]
    return page_hits, {
        "total_matching_chunks": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "has_more_pages": page < total_pages,
    }


def _search_public_documents_full_coverage(
    vector_store: AIVectorStore,
    raw_query: str,
    *,
    filters: Dict[str, Any] | None,
    min_score: float,
    mode: str,
    max_content_chars: int,
    page: int = 1,
    per_page: int = PUBLIC_DOC_FULL_COVERAGE_DEFAULT_PER_PAGE,
    latest_per_country: bool | None = None,
    require_phrase: str | None = None,
) -> Dict[str, Any]:
    documents = list_public_documents_in_scope(filters)
    prioritize_latest = _should_prioritize_latest_per_country(
        raw_query,
        filters,
        latest_per_country=latest_per_country,
    )
    documents, latest_meta = prioritize_latest_documents_per_country(
        documents,
        raw_query,
        enabled=prioritize_latest,
    )
    max_docs = PUBLIC_DOC_MULTI_COUNTRY_BATCH_SIZE * PUBLIC_DOC_MULTI_COUNTRY_MAX_BATCHES
    if len(documents) > max_docs:
        raise PublicDocumentScopeTooLarge(
            f"Too many documents in scope ({len(documents)}), even with server-side batching "
            f"(max {max_docs}). Narrow filters (year, country, file_type)."
        )

    doc_ids = [int(doc.id) for doc in documents]
    # Defer _document_scope_entry() (which may HEAD-check blob/local storage per document)
    # until after hits are known: most documents in scope typically DO have a hit, so
    # building the full entry (with link resolution) for every document up front wastes
    # a storage check for every document that ends up discarded below.
    documents_by_id = {int(doc.id): doc for doc in documents}

    try:
        # Auto-batches into groups of PUBLIC_DOC_MULTI_COUNTRY_BATCH_SIZE documents when scope
        # exceeds one batch (e.g. an unscoped or country_ids="all" full-coverage sweep of the
        # whole public corpus), instead of erroring and pushing batching onto the caller.
        rows, batch_count = _batched_per_document_search_rows(
            vector_store,
            raw_query,
            doc_ids,
            filters=filters,
            chunks_per_doc=PUBLIC_DOC_FULL_COVERAGE_CHUNKS_PER_DOC,
            mode=mode,
            batch_size=PUBLIC_DOC_MULTI_COUNTRY_BATCH_SIZE,
        )
    except VectorStoreError as exc:
        current_app.logger.error("Public document full-coverage search failed: %s", exc)
        raise PublicDocumentSearchUnavailable("Document search is temporarily unavailable") from exc

    rows = filter_rows_to_public_documents(rows)
    rows = _dedupe_rows_by_chunk_id(rows)
    phrase = (require_phrase or "").strip()
    phrase_dropped = 0
    if phrase:
        rows, phrase_dropped = _filter_rows_by_literal_phrase(rows, phrase)
    hits: List[Dict[str, Any]] = []
    docs_with_hits: set[int] = set()

    for row in rows:
        doc_id = row.get("document_id")
        if doc_id is None or not _passes_relevance_floor(row, min_score):
            continue
        doc_id = int(doc_id)
        hits.append(
            slim_public_document_chunk(
                row, max_content_chars=max_content_chars, require_phrase=phrase
            )
        )
        docs_with_hits.add(doc_id)

    # check_local_file=False: these documents have no matching chunk (nothing to cite), so
    # skip the per-document blob/local-file existence check — free source_url is still kept.
    without_hits = [
        _document_scope_entry(doc, check_local_file=False)
        for doc_id, doc in documents_by_id.items()
        if doc_id not in docs_with_hits
    ]
    hits.sort(key=lambda chunk: chunk.get("score") or 0.0, reverse=True)
    without_hits.sort(key=lambda item: (item.get("document_title") or "").lower())

    page_hits, pagination = _paginate_full_coverage_hits(hits, page=page, per_page=per_page)

    coverage: Dict[str, Any] = {
        "documents_in_scope": len(documents),
        "documents_with_hits": len(docs_with_hits),
        "documents_without_hits": len(without_hits),
        "without_hits": without_hits,
        "latest_per_country": latest_meta,
        **pagination,
    }
    if phrase_dropped:
        coverage["phrase_filter_dropped_non_literal_matches"] = phrase_dropped
    coverage["auto_batched_queries"] = batch_count
    if batch_count > 1:
        coverage["note_auto_batched"] = (
            f"Scope exceeded one batch ({PUBLIC_DOC_MULTI_COUNTRY_BATCH_SIZE} documents); "
            f"searched across {batch_count} sequential server-side queries."
        )

    # Shrink page size if the JSON would exceed Custom GPT Actions limit (~100k chars).
    while page_hits and _estimate_json_chars({"chunks": page_hits, "coverage": coverage}) > PUBLIC_DOC_ACTION_MAX_RESPONSE_CHARS:
        if len(page_hits) == 1:
            slim = dict(page_hits[0])
            content = slim.get("content") or ""
            if len(content) > 200:
                slim["content"] = _truncate(content, max(200, len(content) // 2))
                page_hits = [slim]
                coverage["content_truncated_for_limit"] = True
                break
            break
        page_hits = page_hits[:-1]
        coverage["chunks_trimmed_for_limit"] = True
        coverage["per_page"] = len(page_hits)

    return {
        "chunks": page_hits,
        "count": len(page_hits),
        "coverage_mode": "full",
        "coverage": coverage,
    }


def _should_use_country_scoped_search(filters: Dict[str, Any] | None) -> bool:
    if not filters:
        return False
    if filters.get("country_ids"):
        return len(filters["country_ids"]) == 1
    return bool(filters.get("country_id") or filters.get("country_name"))


def _should_use_multi_country_scoped_search(
    filters: Dict[str, Any] | None,
    *,
    country_ids_all: bool,
) -> bool:
    if country_ids_all:
        return True
    country_ids = (filters or {}).get("country_ids") or []
    return len(country_ids) > 1


def _batched_per_document_search_rows(
    vector_store: AIVectorStore,
    raw_query: str,
    doc_ids: List[int],
    *,
    filters: Dict[str, Any] | None,
    chunks_per_doc: int,
    mode: str,
    batch_size: int = PUBLIC_DOC_MULTI_COUNTRY_BATCH_SIZE,
) -> tuple[List[Dict[str, Any]], int]:
    """
    Run one batched per-document search per ``batch_size`` group of ``doc_ids`` (sequential
    DB round trips server-side), instead of a single query over an unbounded document list.

    Each document appears in exactly one batch, so concatenating results across batches is
    safe — no cross-batch overlap or re-ranking is needed (final ranking/top_k happens later
    in :func:`search_public_documents`). Returns ``(rows, batch_count)``.
    """
    batches = [doc_ids[i : i + batch_size] for i in range(0, len(doc_ids), batch_size)]
    all_rows: List[Dict[str, Any]] = []
    for batch_doc_ids in batches:
        if mode == "vector":
            batch_rows = vector_store.search_similar_per_document(
                raw_query,
                batch_doc_ids,
                chunks_per_doc=chunks_per_doc,
                filters=filters,
                user_id=None,
                user_role="public",
            )
        else:
            batch_rows = vector_store.hybrid_search_per_document(
                raw_query,
                batch_doc_ids,
                chunks_per_doc=chunks_per_doc,
                filters=filters,
                user_id=None,
                user_role="public",
            )
        all_rows.extend(batch_rows)
    return all_rows, len(batches)


def _try_multi_country_scoped_search_rows(
    vector_store: AIVectorStore,
    raw_query: str,
    *,
    filters: Dict[str, Any] | None,
    top_k: int,
    mode: str,
    country_ids_all: bool,
) -> tuple[List[Dict[str, Any]], int]:
    """
    Batched per-document search across multiple countries.

    Auto-batches into groups of ``PUBLIC_DOC_MULTI_COUNTRY_BATCH_SIZE`` documents (one
    server-side query pair per group) when the scope is large — e.g. ``country_ids="all"``
    across the whole public corpus — instead of erroring and pushing the batching onto the
    caller. Returns ``(rows, batch_count)``.
    """
    documents = list_public_documents_in_scope(filters)
    if not documents:
        return [], 0

    doc_ids = [int(doc.id) for doc in documents]
    max_docs = PUBLIC_DOC_MULTI_COUNTRY_BATCH_SIZE * PUBLIC_DOC_MULTI_COUNTRY_MAX_BATCHES
    if len(doc_ids) > max_docs:
        scope_hint = "all public countries" if country_ids_all else "requested countries"
        raise PublicDocumentScopeTooLarge(
            f"Too many documents in scope ({len(doc_ids)}) for {scope_hint}, even with batching "
            f"(max {max_docs}). Narrow filters (year, file_type) to reduce scope."
        )

    chunks_per_doc = max(top_k, 8)
    return _batched_per_document_search_rows(
        vector_store,
        raw_query,
        doc_ids,
        filters=filters,
        chunks_per_doc=chunks_per_doc,
        mode=mode,
        batch_size=PUBLIC_DOC_MULTI_COUNTRY_BATCH_SIZE,
    )


def _try_country_scoped_search_rows(
    vector_store: AIVectorStore,
    raw_query: str,
    *,
    filters: Dict[str, Any] | None,
    top_k: int,
    mode: str,
) -> List[Dict[str, Any]] | None:
    """Search within country-scoped documents only; None => fall back to global search."""
    if not _should_use_country_scoped_search(filters):
        return None

    documents = list_public_documents_in_scope(filters)
    if not documents:
        return []
    if len(documents) > PUBLIC_DOC_SCOPED_SEARCH_MAX_DOCS:
        return None

    doc_ids = [int(doc.id) for doc in documents]
    chunks_per_doc = max(top_k, 8)
    if mode == "vector":
        return vector_store.search_similar_per_document(
            raw_query,
            doc_ids,
            chunks_per_doc=chunks_per_doc,
            filters=filters,
            user_id=None,
            user_role="public",
        )

    return vector_store.hybrid_search_per_document(
        raw_query,
        doc_ids,
        chunks_per_doc=chunks_per_doc,
        filters=filters,
        user_id=None,
        user_role="public",
    )


def search_public_documents(
    query: str,
    *,
    top_k: int = PUBLIC_DOC_DEFAULT_TOP_K,
    min_score: float = PUBLIC_DOC_DEFAULT_MIN_SCORE,
    country_name: str | None = None,
    country_id: int | None = None,
    country_ids: str | None = None,
    file_type: str | None = None,
    search_mode: str = "hybrid",
    max_content_chars: int = PUBLIC_DOC_MAX_CONTENT_CHARS,
    full_coverage: bool = False,
    page: int = 1,
    per_page: int = PUBLIC_DOC_FULL_COVERAGE_DEFAULT_PER_PAGE,
    latest_per_country: bool | None = None,
    require_phrase: str | None = None,
) -> Dict[str, Any]:
    """
    Search public AI document chunks (is_public=True only).

    Returns slim chunk payloads suitable for Custom GPT synthesis.
    """
    raw_query = (query or "").strip()
    if not raw_query:
        raise ValueError("query is required")

    top_k = max(1, min(int(top_k), PUBLIC_DOC_MAX_TOP_K))
    min_score = max(0.0, min(float(min_score), 1.0))
    mode = (search_mode or "hybrid").strip().lower()
    if mode not in {"hybrid", "vector"}:
        mode = "hybrid"

    year = _extract_year(raw_query)
    phrase = (require_phrase or "").strip()
    parsed_country_ids, country_ids_all = _parse_country_ids_param(country_ids)
    if parsed_country_ids and len(parsed_country_ids) == 1 and country_id is None:
        country_id = parsed_country_ids[0]
        parsed_country_ids = None

    filters = _build_search_filters(
        raw_query,
        country_name=country_name,
        country_id=country_id,
        country_ids=parsed_country_ids,
        country_ids_all=country_ids_all,
        file_type=file_type,
        year=year,
        require_phrase=phrase,
    )

    vector_store = AIVectorStore()
    multi_country = _should_use_multi_country_scoped_search(filters, country_ids_all=country_ids_all)
    phrase_dropped = 0
    batch_count = 0

    if full_coverage:
        coverage_payload = _search_public_documents_full_coverage(
            vector_store,
            raw_query,
            filters=filters,
            min_score=min_score,
            mode=mode,
            max_content_chars=min(max_content_chars, PUBLIC_DOC_FULL_COVERAGE_CONTENT_CHARS),
            page=page,
            per_page=per_page,
            latest_per_country=latest_per_country,
            require_phrase=phrase,
        )
        slimmed = coverage_payload["chunks"]
        coverage_block = coverage_payload["coverage"]
        coverage_mode = coverage_payload["coverage_mode"]
        phrase_dropped = coverage_block.get("phrase_filter_dropped_non_literal_matches", 0)
        batch_count = coverage_block.get("auto_batched_queries", 0)
    else:
        try:
            if multi_country:
                rows, batch_count = _try_multi_country_scoped_search_rows(
                    vector_store,
                    raw_query,
                    filters=filters,
                    top_k=top_k,
                    mode=mode,
                    country_ids_all=country_ids_all,
                )
            else:
                rows = _try_country_scoped_search_rows(
                    vector_store,
                    raw_query,
                    filters=filters,
                    top_k=top_k,
                    mode=mode,
                )
            if rows is None:
                if mode == "vector":
                    rows = vector_store.search_similar(
                        query_text=raw_query,
                        top_k=top_k * 2,
                        filters=filters,
                        user_id=None,
                        user_role="public",
                    )
                else:
                    rows = vector_store.hybrid_search(
                        query_text=raw_query,
                        top_k=top_k * 2,
                        filters=filters,
                        user_id=None,
                        user_role="public",
                    )
        except VectorStoreError as exc:
            current_app.logger.error("Public document search failed: %s", exc)
            raise PublicDocumentSearchUnavailable("Document search is temporarily unavailable") from exc

        rows = filter_rows_to_public_documents(rows)
        rows = _dedupe_rows_by_chunk_id(rows)
        if phrase:
            rows, phrase_dropped = _filter_rows_by_literal_phrase(rows, phrase)
        filtered = [row for row in rows if _passes_relevance_floor(row, min_score)]
        # Country-scoped rows come back concatenated per document (each document's own
        # chunks already ranked, but not interleaved across documents — see
        # hybrid_search_per_document), so re-sort globally before truncating to top_k.
        # This is a no-op for the already-sorted global (non-scoped) path.
        filtered.sort(key=_chunk_score, reverse=True)
        slimmed = [
            slim_public_document_chunk(
                row, max_content_chars=max_content_chars, require_phrase=phrase
            )
            for row in filtered[:top_k]
        ]
        coverage_block = None
        coverage_mode = "top_k"

    notes = [
        "Only documents marked public in the AI Knowledge Base are searchable.",
        "Use the returned chunk content to answer; cite document_title and page_number.",
        "For numeric indicator trends, prefer GET /api/v1/public/global-trend.",
    ]
    if full_coverage:
        notes.append(
            "Full coverage: searched every public document in scope; returns all chunks with "
            f"score>={min_score}. Paginate with page/per_page if coverage.has_more_pages. "
            f"Custom GPT Actions cap responses at ~{PUBLIC_DOC_ACTION_MAX_RESPONSE_CHARS} chars."
        )
        if query_requests_multi_year_documents(raw_query):
            notes.append("Multi-year query: all matching years kept (latest-per-country dedupe skipped).")
        elif latest_per_country is not False:
            notes.append(
                "Snapshot query: kept the newest document per country and document type "
                "(e.g. 2026 Unified Plan over 2024/2025). See coverage.latest_per_country."
            )
    if query_prefers_upr_documents(raw_query):
        notes.append("Query matched Unified Plan / UPR document scope.")
    if year:
        notes.append(f"Applied document year filter: {year}.")
    if phrase:
        notes.append(f"Hard phrase filter applied: chunks must contain {phrase!r}.")
        if phrase_dropped:
            notes.append(
                f"Dropped {phrase_dropped} chunk(s) that matched the phrase filter's search "
                "index but not the literal phrase text (literal-text safety check)."
            )
    if multi_country:
        notes.append(
            "Multi-country search: results include by_country grouping from one batched query."
        )
    if batch_count > 1:
        notes.append(
            f"Scope was auto-batched into {batch_count} sequential server-side queries "
            f"(documents-in-scope exceeded {PUBLIC_DOC_MULTI_COUNTRY_BATCH_SIZE}); "
            "results are combined as if from a single call."
        )

    payload: Dict[str, Any] = {
        "query": raw_query,
        "search_mode": mode,
        "coverage_mode": coverage_mode,
        "visibility": "public_only",
        "filters_applied": filters or {},
        "min_score": min_score,
        "count": len(slimmed),
        "chunks": slimmed,
        "notes": notes,
    }
    if coverage_block is not None:
        payload["coverage"] = coverage_block
    if multi_country and slimmed:
        payload["by_country"] = _group_slim_chunks_by_country(slimmed)
    return payload


def get_public_document_metadata(document_id: int) -> Dict[str, Any]:
    """Return public metadata for a single AI document (including shareable links)."""
    doc = _load_public_ai_document(document_id)
    doc_date = doc.document_date.isoformat() if doc.document_date else None
    source_url = _document_source_url(doc)
    payload = {
        "document_id": int(doc.id),
        "document_title": doc.title,
        "document_filename": doc.filename,
        "document_date": doc_date,
        "document_category": doc.document_category,
        "countries": _document_country_names(doc),
        "visibility": "public_only",
        "has_local_file": _ai_document_has_local_file(doc),
    }
    payload.update(
        _public_document_link_fields(
            int(doc.id),
            source_url=source_url,
            has_local_file=bool(payload["has_local_file"]),
        )
    )
    return payload


def get_public_document_chunk_context(
    chunk_id: int,
    *,
    before: int = 1,
    after: int = 1,
) -> Dict[str, Any]:
    """
    Return the requested chunk plus its immediate neighbors (by ``chunk_index``) from the
    same document, so a caller can verify or expand an ambiguous/truncated search hit
    without re-running a broad search over the whole document.

    Only chunks belonging to a public, searchable, completed document are returned —
    same visibility rule as :func:`search_public_documents`.
    """
    before = max(0, min(int(before), PUBLIC_DOC_CHUNK_CONTEXT_MAX_BEFORE_AFTER))
    after = max(0, min(int(after), PUBLIC_DOC_CHUNK_CONTEXT_MAX_BEFORE_AFTER))

    completed = AIDocumentProcessingStatusValue.completed.value
    target = (
        db.session.query(AIDocumentChunk, AIDocument)
        .join(AIDocument, AIDocumentChunk.document_id == AIDocument.id)
        .filter(
            AIDocumentChunk.id == int(chunk_id),
            AIDocument.is_public.is_(True),
            AIDocument.searchable.is_(True),
            AIDocument.processing_status == completed,
        )
        .options(joinedload(AIDocument.country))
        .first()
    )
    if not target:
        raise ValueError("Chunk not found, or its document is not public")

    target_chunk, document = target
    doc_id = int(document.id)
    min_index = target_chunk.chunk_index - before
    max_index = target_chunk.chunk_index + after

    siblings = (
        AIDocumentChunk.query.filter(
            AIDocumentChunk.document_id == doc_id,
            AIDocumentChunk.chunk_index >= min_index,
            AIDocumentChunk.chunk_index <= max_index,
        )
        .order_by(AIDocumentChunk.chunk_index)
        .all()
    )

    chunks = [
        {
            "chunk_id": int(c.id),
            "chunk_index": c.chunk_index,
            "page_number": c.page_number,
            "section_title": c.section_title,
            "content": _truncate(c.content, PUBLIC_DOC_CHUNK_CONTEXT_MAX_CONTENT_CHARS),
            "is_requested_chunk": int(c.id) == int(target_chunk.id),
        }
        for c in siblings
    ]

    source_url = _document_source_url(document)
    links = _public_document_link_fields(
        doc_id,
        source_url=source_url,
        has_local_file=_ai_document_has_local_file(document) if not source_url else False,
    )

    return {
        "document_id": doc_id,
        "document_title": document.title,
        "countries": _document_country_names(document),
        "requested_chunk_id": int(target_chunk.id),
        "requested_chunk_index": target_chunk.chunk_index,
        "before": before,
        "after": after,
        "count": len(chunks),
        "chunks": chunks,
        "notes": [
            "chunks are ordered by chunk_index (document reading order); "
            "is_requested_chunk marks the chunk originally returned by search.",
            "Neighboring chunk_index values may be non-contiguous if some chunks were "
            "filtered at ingestion; missing indices simply have no chunk.",
        ],
    }


def stream_public_ai_document_download(document_id: int):
    """Stream or redirect a public AI document file (no login required)."""
    import os

    from flask import redirect, send_file

    from app.routes.ai_documents.helpers import _ai_doc_source_ready, _validate_ifrc_fetch_url
    from app.services.platform.storage_service import StorageService

    doc = _load_public_ai_document(document_id)
    source_url = _document_source_url(doc)
    if source_url:
        ok, _reason = _validate_ifrc_fetch_url(source_url)
        if ok:
            return redirect(source_url, code=302)

    if not doc.storage_path or not _ai_doc_source_ready(doc):
        raise ValueError("Document file not available")

    storage = StorageService()
    if getattr(doc, "submitted_document_id", None):
        storage_path = doc.storage_path.strip()
        category_rel = storage.category_rel_for_submitted_storage_path(storage_path)
        if category_rel is None:
            if storage_path and os.path.exists(storage_path):
                return send_file(
                    storage_path,
                    as_attachment=True,
                    download_name=doc.filename,
                    mimetype="application/octet-stream",
                )
            raise ValueError("Document file not available")
        category, rel = category_rel
        return storage.stream_response(
            category,
            rel,
            filename=doc.filename,
            mimetype="application/octet-stream",
            as_attachment=True,
        )

    if os.path.isabs(doc.storage_path):
        return send_file(
            doc.storage_path,
            as_attachment=True,
            download_name=doc.filename,
            mimetype="application/octet-stream",
        )
    return storage.stream_response(
        storage.AI_DOCUMENTS,
        doc.storage_path,
        filename=doc.filename,
        mimetype="application/octet-stream",
        as_attachment=True,
    )
