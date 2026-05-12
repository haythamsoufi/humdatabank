"""
ai_tools._query_utils
─────────────────────
Query-level heuristics used during document search tool execution:

- ``infer_country_identifier_from_query`` – extract a country name/ISO3 code
  from a free-text query so the retrieval layer can apply a country filter.
- ``query_prefers_upr_documents``         – detect whether a query clearly
  targets Unified Plan / UPR documents.
- ``rewrite_document_search_query``       – split a query into a semantic
  (embedding) variant and a keyword (FTS) variant, expanding IFRC terminology
  along the way.
"""

import logging
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# UPR / Unified Plan detection – moved to app.services.upr.query_detection
# ---------------------------------------------------------------------------
from app.services.upr.query_detection import query_prefers_upr_documents  # noqa: F401


# ---------------------------------------------------------------------------
# Country inference
# ---------------------------------------------------------------------------


def infer_country_identifier_from_query(query: str) -> Optional[str]:
    """
    Best-effort extraction of a country name or ISO-3 code from a free-text
    query so the retrieval layer can apply a country filter automatically.

    Why: LLMs don't always pass explicit filters even when the user query
    contains a country name (e.g. "show me data for Syria").
    """
    q = (query or "").strip()
    if not q:
        return None

    # ISO-3 token (e.g. "SYR")
    m = re.search(r"\b([A-Z]{3})\b", q)
    if m:
        return m.group(1).strip()

    # Common preposition pattern: "in Syria", "for Afghanistan", etc.
    m2 = re.search(
        r"\b(?:in|for|of|about)\s+([A-Za-z][A-Za-z\-\s']{2,60})\b",
        q,
        flags=re.IGNORECASE,
    )
    if m2:
        cand = (m2.group(1) or "").strip()
        cand = re.split(
            r"\b(?:during|in|on|at|for|from|to)\b|\b\d{4}\b", cand, maxsplit=1
        )[0].strip()
        cand = cand.strip(" ,.;:()[]{}\"'")
        if cand:
            return cand

    # Fallback: scan known country names (exact substring, conservative)
    q_lower = q.lower()
    try:
        from app.extensions import db
        from app.models import Country

        for (name,) in db.session.query(Country.name).filter(Country.name.isnot(None)).all():
            if name and name.lower() in q_lower:
                return str(name).strip()
    except Exception as exc:
        logger.debug("infer_country_identifier_from_query: country scan failed: %s", exc)

    return None


# ---------------------------------------------------------------------------
# Query rewriting
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset(
    {
        "the", "a", "an", "of", "in", "on", "for", "to", "and", "or", "not",
        "their", "its", "into", "with", "by", "from", "as", "at",
    }
)


def rewrite_document_search_query(query: str) -> Dict[str, str]:
    """
    Split a document search query into a *semantic* (embedding) variant and a
    *keyword* (FTS) variant, expanding IFRC-specific terminology along the way.

    Returns
    -------
    dict with keys:
        ``vector_query``  – natural-language form suitable for embedding models.
        ``keyword_query`` – form suitable for Postgres ``websearch_to_tsquery``.
    """
    raw = (query or "").strip()
    if not raw:
        return {"vector_query": "", "keyword_query": ""}

    keyword_query = re.sub(r"\s+", " ", raw).strip()

    # Terminology expansion (IFRC glossary + Indicator Bank aliases)
    exp_terms: List[str] = []
    try:
        from app.services.ifrc_terminology_service import get_query_expansion_terms

        exp_terms = get_query_expansion_terms(raw, max_terms=10)
    except Exception as exc:
        logger.debug("rewrite_document_search_query: expansion failed: %s", exc)

    has_query_syntax = bool(
        re.search(
            r'(\bOR\b|\bAND\b|\bNOT\b)|[(){}]|\s"\S|\S"\s|\"',
            raw,
            flags=re.IGNORECASE,
        )
    )
    if not has_query_syntax:
        return {"vector_query": keyword_query, "keyword_query": keyword_query}

    phrases = [
        p.strip()
        for p in re.findall(r'"([^"]{2,200})"', raw)
        if (p or "").strip()
    ]

    cleaned = raw
    cleaned = re.sub(r"\b(OR|AND|NOT)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'["(){}\[\]]', " ", cleaned)
    cleaned = re.sub(r"[^A-Za-z0-9\s\-'/]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    words: List[str] = [
        w.strip()
        for w in re.split(r"\s+", cleaned)
        if w.lower().strip() and w.lower().strip() not in _STOP_WORDS and (
            len(w.lower().strip()) >= 3 or w.strip().isdigit()
        )
    ]

    seen: set = set()
    parts: List[str] = []
    for p in phrases:
        key = p.lower()
        if key not in seen:
            seen.add(key)
            parts.append(p)
    phrase_blob = " " + " ".join(phrases).lower() + " " if phrases else ""
    for w in words:
        key = w.lower()
        if key in seen:
            continue
        if phrase_blob and f" {key} " in phrase_blob:
            continue
        seen.add(key)
        parts.append(w)
        if len(parts) >= 14:
            break

    vector_query = " ".join(parts).strip() or keyword_query
    if exp_terms:
        vector_extra = " ".join(exp_terms[:6]).strip()
        if vector_extra:
            vector_query = f"{vector_query} {vector_extra}".strip()
        keyword_extra: List[str] = []
        for t in exp_terms[:8]:
            tt = str(t or "").strip()
            if not tt:
                continue
            keyword_extra.append(f'"{tt}"' if " " in tt else tt)
        if keyword_extra:
            keyword_query = f"{keyword_query} {' '.join(keyword_extra)}".strip()

    return {"vector_query": vector_query, "keyword_query": keyword_query}


# ---------------------------------------------------------------------------
# Country filter resolution
# ---------------------------------------------------------------------------


def resolve_country_search_filters(country_hint, filters):
    """
    Resolve a country hint string to ``country_id`` / ``country_name`` entries
    in *filters*.  Modifies *filters* in-place.
    """
    if not country_hint:
        return
    try:
        from app.services.data_retrieval_service import resolve_country
        country = resolve_country(country_hint)
        if country and getattr(country, "id", None):
            filters["country_id"] = int(country.id)
            if getattr(country, "name", None):
                filters["country_name"] = str(country.name).strip()
        else:
            filters["country_name"] = str(country_hint).strip()
    except Exception as exc:
        logger.debug("resolve_country_search_filters failed: %s", exc)
        try:
            filters["country_name"] = str(country_hint).strip()
        except Exception as exc2:
            logger.debug("resolve_country_search_filters fallback failed: %s", exc2)
