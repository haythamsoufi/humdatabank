"""
AI tool routing policy helpers.

These helpers keep source/tool-selection heuristics out of the executor so the
core loop stays focused on orchestration.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Tuple

from flask import g, has_request_context

logger = logging.getLogger(__name__)


_FORBID_DOCUMENTS_RE = re.compile(
    r"\b("
    r"databank\s+only|database\s+only|indicator\s+bank\s+only|structured\s+data\s+only|"
    r"not\s+documents|don't\s+look\s+into\s+documents|do\s+not\s+look\s+into\s+documents|"
    r"no\s+documents|documents?\s+off"
    r")\b",
    re.IGNORECASE,
)


def normalize_search_query(query: Any) -> str:
    """Normalize document-search queries for lightweight dedup checks."""
    q = str(query or "").strip().lower()
    if not q:
        return ""
    tokens = [t for t in re.findall(r"[a-z0-9]+", q) if t not in {"or", "and"}]
    return " ".join(tokens)


def are_search_queries_trivially_similar(a: str, b: str) -> bool:
    """
    Return True when two normalized queries are effectively the same intent.
    This catches exact duplicates and simple term reordering.
    """
    if not a or not b:
        return False
    if a == b:
        return True
    a_set = set(a.split())
    b_set = set(b.split())
    if not a_set or not b_set:
        return False
    # If one query is almost entirely contained in the other, treat as duplicate.
    overlap_ratio = len(a_set & b_set) / float(min(len(a_set), len(b_set)))
    return overlap_ratio >= 0.9


def is_redundant_document_search(
    *,
    tool_name: str,
    tool_args: Dict[str, Any],
    recent_search_signatures: List[Dict[str, Any]],
) -> Tuple[bool, str]:
    """Detect repeated search calls in the same run. Pagination is not redundant."""
    if tool_name not in ("search_documents", "search_documents_hybrid"):
        return False, ""
    normalized_query = normalize_search_query((tool_args or {}).get("query"))
    if not normalized_query:
        return False, ""
    return_all_countries = bool((tool_args or {}).get("return_all_countries", False))
    current_offset = int((tool_args or {}).get("offset", 0))
    for prev in reversed((recent_search_signatures or [])[-4:]):
        if bool(prev.get("return_all_countries", False)) != return_all_countries:
            continue
        prev_query = str(prev.get("query_norm") or "")
        if prev_query != normalized_query and not are_search_queries_trivially_similar(normalized_query, prev_query):
            continue
        prev_offset = int(prev.get("offset", 0))
        if current_offset != prev_offset:
            continue
        if prev_query == normalized_query:
            return True, "same normalized query"
        if are_search_queries_trivially_similar(normalized_query, prev_query):
            return True, "trivially similar query"
    return False, ""


def _extract_document_rows_and_meta(tool_result: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], int, int, int]:
    """Extract rows + pagination metadata from document-search tool output."""
    if not isinstance(tool_result, dict):
        return [], 0, 0, 0

    payload = tool_result.get("result")
    if isinstance(payload, dict):
        rows = payload.get("result")
        total_count = payload.get("total_count", 0)
        offset = payload.get("offset", 0)
        limit = payload.get("limit", 0)
    else:
        rows = tool_result.get("result")
        total_count = tool_result.get("total_count", 0)
        offset = tool_result.get("offset", 0)
        limit = tool_result.get("limit", 0)

    if not isinstance(rows, list):
        rows = []

    try:
        total_count = int(total_count or 0)
    except Exception as e:
        logger.debug("_extract_document_rows_and_meta: total_count parse failed: %s", e)
        total_count = 0
    try:
        offset = int(offset or 0)
    except Exception as e:
        logger.debug("_extract_document_rows_and_meta: offset parse failed: %s", e)
        offset = 0
    try:
        limit = int(limit or 0)
    except Exception as e:
        logger.debug("_extract_document_rows_and_meta: limit parse failed: %s", e)
        limit = 0

    return rows, total_count, offset, limit


def extract_document_search_batch_summary(tool_result: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize a search_documents batch for pagination guardrails."""
    rows, total_count, offset, limit = _extract_document_rows_and_meta(tool_result)
    max_score = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        score = row.get("combined_score")
        try:
            score_v = float(score)
        except Exception as e:
            logger.debug("extract_document_search_batch_summary: score parse failed: %s", e)
            continue
        if max_score is None or score_v > max_score:
            max_score = score_v

    return {
        "total_count": total_count,
        "offset": offset,
        "limit": limit,
        "returned_count": len(rows),
        "max_combined_score": max_score,
    }


def should_skip_search_pagination(
    *,
    tool_name: str,
    tool_args: Dict[str, Any],
    recent_search_signatures: List[Dict[str, Any]],
    full_table_requested: bool = False,
    max_batches_for_general: int = 4,
    low_score_threshold: float = 0.42,
    max_consecutive_low_score_batches: int = 2,
) -> Tuple[bool, str]:
    """
    Decide whether to skip another paginated search_documents call for same query.

    We keep exhaustive pagination for explicit full-table asks; otherwise stop when
    retrieval quality has clearly degraded or generic batch caps are reached.
    """
    if tool_name not in ("search_documents", "search_documents_hybrid"):
        return False, ""
    if full_table_requested:
        return False, ""
    if not bool((tool_args or {}).get("return_all_countries", False)):
        return False, ""

    try:
        current_offset = int((tool_args or {}).get("offset", 0))
    except Exception as e:
        logger.debug("should_skip_search_pagination: current_offset parse failed: %s", e)
        current_offset = 0
    if current_offset <= 0:
        return False, ""

    normalized_query = normalize_search_query((tool_args or {}).get("query"))
    if not normalized_query:
        return False, ""

    same_query_calls: List[Dict[str, Any]] = []
    for prev in recent_search_signatures or []:
        if not isinstance(prev, dict):
            continue
        if not bool(prev.get("return_all_countries", False)):
            continue
        prev_query = str(prev.get("query_norm") or "")
        if prev_query == normalized_query or are_search_queries_trivially_similar(prev_query, normalized_query):
            same_query_calls.append(prev)

    if not same_query_calls:
        return False, ""

    last = same_query_calls[-1]
    try:
        last_total_count = int(last.get("total_count", 0) or 0)
    except Exception as e:
        logger.debug("should_skip_search_pagination: last_total_count parse failed: %s", e)
        last_total_count = 0
    if last_total_count > 0 and current_offset >= last_total_count:
        return True, "offset already reached total_count"

    if len(same_query_calls) >= max(1, int(max_batches_for_general)):
        return True, "pagination batch cap reached"

    # Stop when the last consecutive pages are weak and we're already a few pages in.
    threshold = float(low_score_threshold)
    required_low_batches = max(1, int(max_consecutive_low_score_batches))
    consecutive_low = 0
    for prev in reversed(same_query_calls):
        score = prev.get("max_combined_score")
        try:
            score_v = float(score)
        except Exception as e:
            logger.debug("should_skip_search_pagination: score parse failed: %s", e)
            break
        if score_v < threshold:
            consecutive_low += 1
        else:
            break
    if len(same_query_calls) >= 3 and consecutive_low >= required_low_batches:
        return True, "consecutive low-relevance batches"

    return False, ""


def user_forbids_documents(query: str) -> bool:
    if not query or not isinstance(query, str):
        return False
    return bool(_FORBID_DOCUMENTS_RE.search(query))


def docs_sources_enabled() -> bool:
    """
    Respect UI source toggles: if both system_documents and upr_documents are
    disabled, do not force document search. If sources config is missing,
    default to True for back-compat.
    """
    if not has_request_context():
        return True
    try:
        cfg = getattr(g, "ai_sources_cfg", None)
    except Exception as e:
        logger.debug("docs_sources_enabled: get ai_sources_cfg failed: %s", e)
        cfg = None
    if not isinstance(cfg, dict):
        return True
    try:
        include_system = bool(cfg.get("system_documents", False))
        include_upr = bool(cfg.get("upr_documents", False))
        return bool(include_system or include_upr)
    except Exception as e:
        logger.debug("_cfg_requests_document_search failed: %s", e)
        return True


def is_value_question(query: str) -> bool:
    """
    True if the query is asking for a factual value (number, count, figure) that
    should be answered using get_indicator_value and/or search_documents.
    """
    if not query or not isinstance(query, str):
        return False
    q = query.strip().lower()
    if len(q) < 10:
        return False
    value_phrases = (
        "number of",
        "how many",
        "how much",
        "total number",
        "count of",
        "branches",
        "volunteers",
        "staff",
        "offices",
        "members",
        "personnel",
        "people reached",
        "beneficiaries",
        "figure for",
        "value for",
        "latest",
        "current",
        "recorded value",
        "indicator value",
        "what is the",
        "get me the",
        "find the",
        "retrieve the",
    )
    if any(p in q for p in value_phrases):
        return True
    if " in " in q and ("?" in q or "what" in q or "how" in q):
        return True
    if " for " in q and ("?" in q or "what" in q or "how" in q):
        return True
    return False


def is_smalltalk(query: str) -> bool:
    if not query or not isinstance(query, str):
        return True
    q = query.strip().lower()
    if not q:
        return True
    if len(q) <= 8:
        return True
    smalltalk = (
        "hi",
        "hello",
        "hey",
        "thanks",
        "thank you",
        "thx",
        "ok",
        "okay",
        "cool",
        "great",
        "nice",
        "good morning",
        "good afternoon",
        "good evening",
    )
    return any(q == s or q.startswith(s + " ") for s in smalltalk)


def docs_only_sources_enabled() -> bool:
    """
    True when the request explicitly disabled databank/structured tools but
    still allows documents.
    """
    if not has_request_context():
        return False
    try:
        sc = getattr(g, "ai_sources_cfg", None)
    except Exception as e:
        logger.debug("docs_only_sources_enabled: get ai_sources_cfg failed: %s", e)
        sc = None
    if not isinstance(sc, dict):
        return False
    historical = bool(sc.get("historical", False))
    system_docs = bool(sc.get("system_documents", False))
    upr_docs = bool(sc.get("upr_documents", False))
    return (not historical) and (system_docs or upr_docs)


def should_force_docs_tool_first_turn(query: str) -> bool:
    """
    Best-effort heuristic: when sources are documents-only, force at least one
    tool call for substantive queries.
    """
    if is_smalltalk(query):
        return False
    q = str(query or "").strip()
    if len(q) < 12:
        return False
    ql = q.lower()
    if any(p in ql for p in ("which source", "use sources", "toggle", "checkbox", "settings")):
        return False
    return True
