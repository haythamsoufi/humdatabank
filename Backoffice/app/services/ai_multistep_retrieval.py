"""
AI Multi-Step Retrieval Service

Decomposes complex queries into sub-queries, retrieves evidence for each,
then merges and deduplicates results. Improves recall for comparative and
multi-entity questions like "Compare X and Y across countries."

Integration:
    Called by ai_tools_registry when search_documents_hybrid detects a complex query
    (multi-entity, comparative, or explicitly decomposable).

Usage:
    from app.services.ai_multistep_retrieval import MultiStepRetriever
    retriever = MultiStepRetriever()
    chunks = retriever.retrieve(query, context={}, top_k=10)
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Query decomposition heuristics
# ---------------------------------------------------------------------------

_COMPARE_RE = re.compile(
    r"\b(compare|comparison|versus|vs\.?|difference between|similarities? between|"
    r"how does .+ differ from|how do .+ compare)\b",
    re.IGNORECASE,
)
_AND_ENTITY_RE = re.compile(
    r"\b(?:[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\s+and\s+(?:[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\b"
)
_BOTH_RE = re.compile(r"\b(both|each|all of the|every)\b", re.IGNORECASE)
_MULTI_QUESTION_RE = re.compile(r"\?\s+(?:and\s+)?(?:also\s+)?(?:what|how|when|where|who)", re.IGNORECASE)


def is_decomposable_query(query: str) -> bool:
    """
    Return True if the query likely benefits from decomposition into sub-queries.
    Heuristic: comparative phrases, multi-entity AND, both/each, or chained questions.
    """
    if _COMPARE_RE.search(query):
        return True
    if _AND_ENTITY_RE.search(query) and len(query) > 40:
        return True
    if _BOTH_RE.search(query) and len(query) > 30:
        return True
    if _MULTI_QUESTION_RE.search(query):
        return True
    return False


def decompose_query(query: str) -> List[str]:
    """
    Decompose a complex query into up to 3 focused sub-queries.

    Uses simple heuristics; the caller can optionally use the LLM version instead.
    """
    sub_queries: List[str] = []

    # Comparative: "Compare X and Y" → two separate queries
    compare_match = re.search(
        r"compare\s+(.+?)\s+and\s+(.+?)(?:\s+in|\s+for|\s+across|\s*$)",
        query, re.IGNORECASE
    )
    if compare_match:
        a, b = compare_match.group(1).strip(), compare_match.group(2).strip()
        context = query[compare_match.end():].strip()
        sub_queries.append(f"{a} {context}".strip())
        sub_queries.append(f"{b} {context}".strip())
        return sub_queries[:3]

    # "X and Y" entity pair
    and_match = _AND_ENTITY_RE.search(query)
    if and_match:
        full = and_match.group(0)
        parts = re.split(r"\s+and\s+", full, maxsplit=1, flags=re.IGNORECASE)
        rest = query.replace(full, "").strip()
        for p in parts[:2]:
            sub_queries.append(f"{p.strip()} {rest}".strip())
        return sub_queries[:3]

    # Chained questions: split on "? and" or "? also"
    parts = _MULTI_QUESTION_RE.split(query)
    if len(parts) > 1:
        for part in parts[:3]:
            part = part.strip().rstrip("?").strip()
            if len(part) > 10:
                sub_queries.append(part)
        return sub_queries

    # Fallback: return original as single sub-query
    return [query]


def llm_decompose_query(query: str, context: Dict[str, Any]) -> List[str]:
    """
    Use an LLM to decompose a complex query into focused sub-queries.
    Falls back to heuristic decomposition if LLM fails or is unavailable.
    Gated by AI_MULTISTEP_LLM_DECOMPOSE config (default True).
    """
    try:
        from flask import current_app
        if not current_app.config.get("AI_MULTISTEP_LLM_DECOMPOSE", True):
            return decompose_query(query)

        from openai import OpenAI
        api_key = current_app.config.get("OPENAI_API_KEY")
        if not api_key:
            return decompose_query(query)

        model = current_app.config.get("OPENAI_MODEL", "gpt-4o-mini")
        client = OpenAI(api_key=api_key)

        prompt = (
            "You are a query decomposer. Given a complex user question, split it into "
            "at most 3 focused sub-questions that together cover the original. "
            "Return ONLY a JSON array of strings. No explanation.\n\n"
            f"Question: {query}"
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.0,
        )
        content = resp.choices[0].message.content or ""
        import json
        arr = json.loads(content.strip())
        if isinstance(arr, list) and all(isinstance(s, str) for s in arr):
            sub_queries = [s.strip() for s in arr if s.strip()][:3]
            if sub_queries:
                return sub_queries
    except Exception as exc:
        logger.debug("LLM decomposition failed, using heuristic: %s", exc)

    return decompose_query(query)


# ---------------------------------------------------------------------------
# Multi-step retriever
# ---------------------------------------------------------------------------

class MultiStepRetriever:
    """
    Runs hybrid search for each sub-query and merges results with attribution.

    Each result chunk carries a 'sub_query' field indicating which sub-question
    it was retrieved for, enabling citation-level attribution.
    """

    def retrieve(
        self,
        query: str,
        *,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        user_role: Optional[str] = None,
        top_k: int = 10,
        use_llm_decompose: bool = True,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Decompose query and retrieve for each sub-query.

        Returns:
            (merged_chunks, sub_queries)
            - merged_chunks: deduplicated, scored list of chunk dicts
            - sub_queries: the sub-queries that were used
        """
        from flask import current_app

        if use_llm_decompose and is_decomposable_query(query):
            sub_queries = llm_decompose_query(query, context or {})
            logger.info("Multi-step retrieval: decomposed into %d sub-queries: %s", len(sub_queries), sub_queries)
        else:
            sub_queries = [query]

        from app.services.ai_vector_store import AIVectorStore
        store = AIVectorStore()

        seen_chunk_ids: set = set()
        merged: List[Dict[str, Any]] = []
        per_subquery_k = max(top_k, len(sub_queries) * (top_k // max(len(sub_queries), 1)))

        for sq in sub_queries:
            try:
                results = store.hybrid_search(
                    query_text=sq,
                    top_k=per_subquery_k,
                    filters=filters,
                    user_id=user_id,
                    user_role=user_role,
                )
                for chunk in results:
                    cid = chunk.get("chunk_id")
                    if cid not in seen_chunk_ids:
                        seen_chunk_ids.add(cid)
                        chunk["sub_query"] = sq
                        merged.append(chunk)
            except Exception as exc:
                logger.warning("Multi-step retrieval sub-query failed (%r): %s", sq[:60], exc)

        # Re-score merged list by combined_score (desc), then trim
        merged.sort(key=lambda r: r.get("combined_score", r.get("similarity_score", 0.0)), reverse=True)
        return merged[:top_k], sub_queries
