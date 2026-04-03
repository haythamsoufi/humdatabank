"""
AI Rerank Service

Optional two-stage retrieval: after hybrid search, rerank candidates with a
cross-encoder or API (e.g. Cohere) for better precision when searching 200+ documents.
Enable with AI_RERANK_ENABLED=true. Configure AI_RERANK_PROVIDER and API keys.
"""

import logging
from typing import List, Dict, Any

from flask import current_app

logger = logging.getLogger(__name__)


def rerank_chunks(
    query_text: str,
    chunks: List[Dict[str, Any]],
    top_k: int,
) -> List[Dict[str, Any]]:
    """
    Rerank document chunks by relevance to the query.
    Returns the same chunks in new order (and optionally trimmed to top_k).
    If reranking is disabled or fails, returns chunks unchanged.
    """
    if not chunks or not (query_text or "").strip():
        return chunks

    provider = (current_app.config.get("AI_RERANK_PROVIDER") or "cohere").strip().lower()
    rerank_top_k = int(current_app.config.get("AI_RERANK_TOP_K", 20))

    if provider == "cohere":
        return _rerank_cohere(query_text, chunks, top_k=min(rerank_top_k, top_k * 2))
    if provider == "local":
        return _rerank_local(query_text, chunks, top_k=min(rerank_top_k, top_k * 2))

    logger.debug("Rerank provider %s not implemented, using original order", provider)
    return chunks


def _rerank_cohere(
    query_text: str,
    chunks: List[Dict[str, Any]],
    top_k: int,
) -> List[Dict[str, Any]]:
    """Rerank using Cohere Rerank API. Requires COHERE_API_KEY."""
    api_key = current_app.config.get("COHERE_API_KEY")
    if not api_key:
        logger.debug("COHERE_API_KEY not set, skipping rerank")
        return chunks

    try:
        import cohere
        model = current_app.config.get("AI_RERANK_COHERE_MODEL", "rerank-v3.5")
        documents = [c.get("content") or "" for c in chunks]
        if not any(documents):
            return chunks
        # Prefer ClientV2 (Cohere v2 API); fall back to Client for older SDKs
        try:
            client = cohere.ClientV2(api_key=api_key)
        except AttributeError:
            client = cohere.Client(api_key=api_key)
        response = client.rerank(
            model=model,
            query=query_text,
            documents=documents,
            top_n=min(top_k, len(chunks)),
        )
        # Cohere returns results in reranked order with index into original list
        order = [r.index for r in response.results]
        return [chunks[i] for i in order if 0 <= i < len(chunks)]
    except ImportError:
        logger.warning("cohere package not installed. pip install cohere to enable reranking.")
        return chunks
    except Exception as e:
        logger.warning("Cohere rerank failed: %s", e)
        return chunks


def _rerank_local(
    query_text: str,
    chunks: List[Dict[str, Any]],
    top_k: int,
) -> List[Dict[str, Any]]:
    """Rerank using a local cross-encoder (e.g. sentence-transformers)."""
    try:
        from sentence_transformers import CrossEncoder
        model_name = current_app.config.get("AI_RERANK_LOCAL_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
        model = CrossEncoder(model_name)
        documents = [c.get("content") or "" for c in chunks]
        if not any(documents):
            return chunks
        pairs = [(query_text, d) for d in documents]
        scores = model.predict(pairs)
        indexed = list(zip(scores, range(len(chunks))))
        indexed.sort(key=lambda x: x[0], reverse=True)
        return [chunks[i] for _, i in indexed[:top_k]]
    except ImportError:
        logger.warning("sentence-transformers not installed. pip install sentence-transformers for local rerank.")
        return chunks
    except Exception as e:
        logger.warning("Local rerank failed: %s", e)
        return chunks
