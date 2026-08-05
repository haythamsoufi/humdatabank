"""Compact public document search for Custom GPT and other external integrations."""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Dict, List, Optional

from flask import current_app
from sqlalchemy import text

from app.models import AIDocument
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

_YEAR_RE = re.compile(r"\b(20\d{2})\b")


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


def _document_source_url(document: AIDocument | Dict[str, Any] | None) -> str | None:
    if document is None:
        return None
    if isinstance(document, dict):
        raw = document.get("source_url")
    else:
        raw = getattr(document, "source_url", None)
    url = (raw or "").strip()
    return url or None


def _document_scope_entry(document: AIDocument) -> Dict[str, Any]:
    return {
        "document_id": int(document.id),
        "document_title": document.title,
        "countries": _document_country_names(document),
        "source_url": _document_source_url(document),
    }


def slim_public_document_chunk(row: Dict[str, Any], *, max_content_chars: int) -> Dict[str, Any]:
    """Project a vector-store hit to a compact shape for Custom GPT Actions."""
    countries = row.get("document_countries") or []
    country_names = [c.get("name") for c in countries if isinstance(c, dict) and c.get("name")]
    if not country_names and row.get("document_country_name"):
        country_names = [row["document_country_name"]]

    return {
        "chunk_id": row.get("chunk_id"),
        "document_id": row.get("document_id"),
        "document_title": row.get("document_title"),
        "document_filename": row.get("document_filename"),
        "document_date": row.get("document_date"),
        "document_category": row.get("document_category"),
        "document_language": row.get("document_language"),
        "countries": country_names,
        "page_number": row.get("page_number"),
        "section_title": row.get("section_title"),
        "content": _truncate(row.get("content"), max_content_chars),
        "score": round(_chunk_score(row), 4),
        "source_organization": row.get("source_organization"),
        "source_url": _document_source_url(row),
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
    file_type: str | None = None,
    year: int | None = None,
) -> Dict[str, Any] | None:
    filters: Dict[str, Any] = {}
    filters.update(_resolve_country_filter(query, country_name=country_name, country_id=country_id))

    if file_type:
        filters["file_type"] = file_type.strip().lower()

    if query_prefers_upr_documents(query):
        filters["is_api_import"] = True
        filters["is_system_document"] = False

    if year:
        filters["date_range"] = {"min": f"{year}-01-01", "max": f"{year}-12-31"}

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

    if filters.get("country_id"):
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
    query = _apply_scope_filters_to_query(query, filters)
    return query.order_by(AIDocument.title).all()


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
    if len(documents) > PUBLIC_DOC_FULL_COVERAGE_MAX_DOCS:
        raise ValueError(
            f"Too many documents in scope ({len(documents)}). "
            f"Narrow filters (year, country) or use full_coverage=false."
        )

    doc_ids = [int(doc.id) for doc in documents]
    scope_without_hits = {
        int(doc.id): _document_scope_entry(doc)
        for doc in documents
    }

    try:
        if mode == "vector":
            rows: List[Dict[str, Any]] = []
            for doc_id in doc_ids:
                doc_filters = dict(filters or {})
                doc_filters["document_id"] = doc_id
                rows.extend(
                    vector_store.search_similar(
                        query_text=raw_query,
                        top_k=PUBLIC_DOC_FULL_COVERAGE_CHUNKS_PER_DOC,
                        filters=doc_filters,
                        user_id=None,
                        user_role="public",
                    )
                )
        else:
            rows = vector_store.hybrid_search_per_document(
                raw_query,
                doc_ids,
                chunks_per_doc=PUBLIC_DOC_FULL_COVERAGE_CHUNKS_PER_DOC,
                filters=filters,
                user_id=None,
                user_role="public",
            )
    except VectorStoreError as exc:
        current_app.logger.error("Public document full-coverage search failed: %s", exc)
        raise ValueError("Document search is temporarily unavailable") from exc

    rows = filter_rows_to_public_documents(rows)
    hits: List[Dict[str, Any]] = []
    docs_with_hits: set[int] = set()

    for row in rows:
        score = _chunk_score(row)
        doc_id = row.get("document_id")
        if doc_id is None or score < min_score:
            continue
        doc_id = int(doc_id)
        hits.append(slim_public_document_chunk(row, max_content_chars=max_content_chars))
        docs_with_hits.add(doc_id)
        scope_without_hits.pop(doc_id, None)

    without_hits = list(scope_without_hits.values())
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


def search_public_documents(
    query: str,
    *,
    top_k: int = PUBLIC_DOC_DEFAULT_TOP_K,
    min_score: float = PUBLIC_DOC_DEFAULT_MIN_SCORE,
    country_name: str | None = None,
    country_id: int | None = None,
    file_type: str | None = None,
    search_mode: str = "hybrid",
    max_content_chars: int = PUBLIC_DOC_MAX_CONTENT_CHARS,
    full_coverage: bool = False,
    page: int = 1,
    per_page: int = PUBLIC_DOC_FULL_COVERAGE_DEFAULT_PER_PAGE,
    latest_per_country: bool | None = None,
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
    filters = _build_search_filters(
        raw_query,
        country_name=country_name,
        country_id=country_id,
        file_type=file_type,
        year=year,
    )

    vector_store = AIVectorStore()

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
        )
        slimmed = coverage_payload["chunks"]
        coverage_block = coverage_payload["coverage"]
        coverage_mode = coverage_payload["coverage_mode"]
    else:
        try:
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
            raise ValueError("Document search is temporarily unavailable") from exc

        rows = filter_rows_to_public_documents(rows)
        filtered = [row for row in rows if _chunk_score(row) >= min_score]
        slimmed = [
            slim_public_document_chunk(row, max_content_chars=max_content_chars)
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
    return payload


def get_public_document_metadata(document_id: int) -> Dict[str, Any]:
    """Return public metadata for a single AI document (including source URL when available)."""
    completed = AIDocumentProcessingStatusValue.completed.value
    doc = AIDocument.query.filter(
        AIDocument.id == int(document_id),
        AIDocument.is_public.is_(True),
        AIDocument.searchable.is_(True),
        AIDocument.processing_status == completed,
    ).first()
    if not doc:
        raise ValueError("Document not found or not public")

    doc_date = doc.document_date.isoformat() if doc.document_date else None
    return {
        "document_id": int(doc.id),
        "document_title": doc.title,
        "document_filename": doc.filename,
        "document_date": doc_date,
        "document_category": doc.document_category,
        "countries": _document_country_names(doc),
        "source_url": _document_source_url(doc),
        "visibility": "public_only",
    }
