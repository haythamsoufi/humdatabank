"""Compact public document search for Custom GPT and other external integrations."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from flask import current_app

from app.models import AIDocument
from app.models.enums import AIDocumentProcessingStatusValue
from app.services.ai.documents.country_detection import detect_country_id_and_name
from app.services.ai.documents.vector_store import AIVectorStore, VectorStoreError
from app.services.upr.query_detection import query_prefers_upr_documents

PUBLIC_DOC_DEFAULT_TOP_K = 8
PUBLIC_DOC_MAX_TOP_K = 12
PUBLIC_DOC_DEFAULT_MIN_SCORE = 0.25
PUBLIC_DOC_MAX_CONTENT_CHARS = 1200

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

    notes = [
        "Only documents marked public in the AI Knowledge Base are searchable.",
        "Use the returned chunk content to answer; cite document_title and page_number.",
        "For numeric indicator trends, prefer GET /api/v1/public/global-trend.",
    ]
    if query_prefers_upr_documents(raw_query):
        notes.append("Query matched Unified Plan / UPR document scope.")
    if year:
        notes.append(f"Applied document year filter: {year}.")

    return {
        "query": raw_query,
        "search_mode": mode,
        "visibility": "public_only",
        "filters_applied": filters or {},
        "min_score": min_score,
        "count": len(slimmed),
        "chunks": slimmed,
        "notes": notes,
    }
