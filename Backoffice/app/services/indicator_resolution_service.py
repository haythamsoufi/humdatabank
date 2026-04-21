"""
Indicator Resolution Service: map user phrase to Indicator Bank via vector search and optional LLM.

- Vector: embed Indicator Bank (name + definition + unit); embed user query; return top-k by cosine similarity.
- LLM (optional): given user query + top-k indicators, LLM picks the single best match.

Config: AI_INDICATOR_RESOLUTION_METHOD (vector | vector_then_llm | keyword),
        AI_INDICATOR_LLM_DISAMBIGUATE, AI_INDICATOR_TOP_K.
"""

import json
import logging
from typing import List, Optional, Tuple, Any

from flask import current_app
from sqlalchemy import text
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import IndicatorBank, IndicatorBankEmbedding
from app.services.ai_embedding_service import AIEmbeddingService
from app.services.ai_embedding_service import EmbeddingError

logger = logging.getLogger(__name__)


def _text_for_indicator(ind: IndicatorBank) -> str:
    """Build searchable text for one indicator (name + definition + unit)."""
    parts = [ind.name or ""]
    if getattr(ind, "definition", None) and str(ind.definition).strip():
        parts.append(str(ind.definition).strip())
    if getattr(ind, "unit", None) and str(ind.unit).strip():
        parts.append(f"Unit: {ind.unit}".strip())
    return " ".join(parts).strip() or ind.name or ""


class IndicatorResolutionService:
    """Semantic and optional LLM-based indicator resolution."""

    def __init__(self):
        self._embedding_service: Optional[AIEmbeddingService] = None

    @property
    def embedding_service(self) -> AIEmbeddingService:
        if self._embedding_service is None:
            self._embedding_service = AIEmbeddingService()
        return self._embedding_service

    def resolve(
        self,
        query: str,
        top_k: int = 10,
        *,
        exclude_archived: bool = True,
    ) -> List[Tuple[IndicatorBank, float]]:
        """
        Resolve user phrase to top-k indicators by vector similarity.
        Returns list of (IndicatorBank, similarity_score). Empty if no embeddings exist.
        """
        query = (query or "").strip()
        if not query:
            return []

        try:
            query_embedding, _ = self.embedding_service.generate_embedding(query)
        except EmbeddingError as e:
            logger.warning("Indicator resolution embedding failed: %s", e)
            return []

        return self._search_similar(query_embedding, top_k=top_k, exclude_archived=exclude_archived)

    def _search_similar(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        exclude_archived: bool = True,
    ) -> List[Tuple[IndicatorBank, float]]:
        """Vector similarity search over indicator_bank_embeddings. Returns (IndicatorBank, score)."""
        try:
            q = (
                db.session.query(
                    IndicatorBank,
                    (1 - IndicatorBankEmbedding.embedding.cosine_distance(query_embedding)).label("similarity"),
                )
                .join(IndicatorBankEmbedding, IndicatorBankEmbedding.indicator_bank_id == IndicatorBank.id)
            )
            if exclude_archived:
                q = q.filter(IndicatorBank.archived == False)  # noqa: E712
            q = q.order_by(text("similarity DESC")).limit(top_k)
            rows = q.all()
            return [(ind, float(sim)) for ind, sim in rows]
        except Exception as e:
            logger.warning("Indicator vector search failed: %s", e, exc_info=True)
            try:
                db.session.rollback()
            except Exception as rb_err:
                logger.debug("Indicator vector search rollback failed: %s", rb_err)
            return []

    def resolve_with_llm(
        self,
        user_query: str,
        top_k_indicators: List[Tuple[IndicatorBank, float]],
    ) -> Optional[IndicatorBank]:
        """
        Given user query and top-k (indicator, score), ask LLM to pick the single best indicator.
        Returns None if LLM says none or call fails.
        """
        if not top_k_indicators or not (user_query or "").strip():
            return None

        list_text = "\n".join(
            f"- id={ind.id}: {ind.name}" + (f" (definition: {(ind.definition or '')[:200]}...)" if getattr(ind, "definition", None) else "")
            for ind, _ in top_k_indicators[:15]
        )
        system = (
            "You are a precise assistant. The user asked a question about data. Below is a list of indicators from our Indicator Bank (id and name). "
            "Choose the ONE indicator that best matches what the user is asking about. Reply with ONLY a JSON object: {\"indicator_id\": <number>} for the chosen indicator, "
            "or {\"indicator_id\": null} if none match. Use the first list item's id if multiple seem equally good. No other text."
        )
        user_msg = f"User question: {user_query}\n\nIndicators:\n{list_text}"

        try:
            from openai import OpenAI
            client = OpenAI(api_key=current_app.config.get("OPENAI_API_KEY"), timeout=int(current_app.config.get("AI_HTTP_TIMEOUT_SECONDS", 60)))
            model = current_app.config.get("OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
                temperature=0,
            )
            content = (resp.choices[0].message.content or "").strip()
            # Parse JSON (allow markdown code block)
            if "```" in content:
                content = content.split("```")[1].replace("json", "").strip()
            data = json.loads(content)
            id_val = data.get("indicator_id")
            if id_val is None:
                return None
            id_val = int(id_val)
            for ind, _ in top_k_indicators:
                if ind.id == id_val:
                    return ind
            return top_k_indicators[0][0] if top_k_indicators else None
        except Exception as e:
            logger.warning("Indicator LLM disambiguation failed: %s", e)
            return top_k_indicators[0][0] if top_k_indicators else None

    def sync_all(self, batch_size: int = 100) -> Tuple[int, float]:
        """
        (Re)build embeddings for all non-archived indicators. Returns (count_upserted, total_cost_usd).
        Safe to run multiple times (upserts by indicator_bank_id).
        """
        indicators = (
            IndicatorBank.query.filter(IndicatorBank.archived == False)  # noqa: E712
            .order_by(IndicatorBank.id)
            .all()
        )
        if not indicators:
            return 0, 0.0

        texts = [_text_for_indicator(ind) for ind in indicators]
        try:
            embeddings, total_cost = self.embedding_service.generate_embeddings_batch(texts, batch_size=batch_size)
        except EmbeddingError as e:
            logger.error("Indicator sync embeddings failed: %s", e)
            raise

        dims = len(embeddings[0]) if embeddings else 0
        model = self.embedding_service.model
        stored = 0
        for i, ind in enumerate(indicators):
            if i >= len(embeddings):
                break
            vec = embeddings[i]
            cost_per = total_cost / len(embeddings) if embeddings else 0
            existing = db.session.query(IndicatorBankEmbedding).filter_by(indicator_bank_id=ind.id).first()
            if existing:
                existing.embedding = vec
                existing.text_embedded = texts[i]
                existing.model = model
                existing.dimensions = dims
                existing.generation_cost_usd = cost_per
            else:
                db.session.add(
                    IndicatorBankEmbedding(
                        indicator_bank_id=ind.id,
                        embedding=vec,
                        text_embedded=texts[i],
                        model=model,
                        dimensions=dims,
                        generation_cost_usd=cost_per,
                    )
                )
            stored += 1
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error("Indicator sync commit failed: %s", e)
            raise
        logger.info("Indicator sync: %s embeddings stored, cost=%.4f USD", stored, total_cost)
        return stored, total_cost

    def has_embeddings(self) -> bool:
        """Return True if at least one indicator embedding exists."""
        try:
            return db.session.query(IndicatorBankEmbedding.id).limit(1).first() is not None
        except Exception as e:
            logger.debug("has_embeddings check failed: %s", e)
            return False


def get_indicator_candidates(
    indicator_identifier: Any,
    top_k: Optional[int] = None,
) -> List[Tuple[IndicatorBank, float]]:
    """
    Return top-k indicator candidates with their vector similarity scores.

    Returns list of (IndicatorBank, similarity_score) ordered by similarity
    (highest first).  Similarity is cosine similarity (0..1 typical range).
    - int or numeric str: return single (IndicatorBank, 1.0), or [] if not found.
    - str: when embeddings exist and method is vector/vector_then_llm, return
      scored pairs.  Otherwise return [] (caller falls back to keyword search).
    """
    if top_k is None:
        top_k = int(current_app.config.get("AI_INDICATOR_TOP_K", 10))
    if isinstance(indicator_identifier, int):
        ind = db.session.get(IndicatorBank, indicator_identifier)
        return [(ind, 1.0)] if ind else []
    if isinstance(indicator_identifier, str) and indicator_identifier.strip().isdigit():
        ind = db.session.get(IndicatorBank, int(indicator_identifier.strip()))
        return [(ind, 1.0)] if ind else []

    ident = (indicator_identifier or "").strip()
    if not ident:
        return []

    method = (current_app.config.get("AI_INDICATOR_RESOLUTION_METHOD") or "keyword").strip().lower()
    if method not in ("vector", "vector_then_llm"):
        logger.info("get_indicator_candidates: method=%r, skipping vector search for %r", method, ident)
        return []

    svc = IndicatorResolutionService()
    if not svc.has_embeddings():
        logger.warning("get_indicator_candidates: no indicator embeddings found, falling back to keyword for %r", ident)
        return []

    results = svc.resolve(ident, top_k=top_k)
    if results:
        logger.info(
            "get_indicator_candidates: vector search for %r returned %d results: %s",
            ident, len(results),
            [(ind.name, ind.id, round(sim, 4)) for ind, sim in results[:5]],
        )
    else:
        logger.info("get_indicator_candidates: vector search for %r returned 0 results", ident)
    return results


def resolve_indicator_identifier(
    indicator_identifier: Any,
    *,
    country_id: Optional[int] = None,
    user_query: Optional[str] = None,
) -> Optional[IndicatorBank]:
    """
    Resolve indicator_identifier (int or str) to a single IndicatorBank using configured method.
    - int or numeric str: direct lookup by id.
    - str: vector (and optional LLM) or keyword fallback; user_query used for LLM when provided.
    Returns None if not found.
    """
    if isinstance(indicator_identifier, int):
        return db.session.get(IndicatorBank, indicator_identifier)
    if isinstance(indicator_identifier, str) and indicator_identifier.strip().isdigit():
        return db.session.get(IndicatorBank, int(indicator_identifier.strip()))

    # String: use configured resolution method
    method = (current_app.config.get("AI_INDICATOR_RESOLUTION_METHOD") or "keyword").strip().lower()
    if method not in ("vector", "vector_then_llm"):
        return None  # Caller will use keyword path in data_retrieval_form

    svc = IndicatorResolutionService()
    if not svc.has_embeddings():
        return None

    top_k = int(current_app.config.get("AI_INDICATOR_TOP_K", 10))
    candidates = svc.resolve((indicator_identifier or "").strip(), top_k=top_k)
    if not candidates:
        return None

    use_llm = (
        method == "vector_then_llm"
        and current_app.config.get("AI_INDICATOR_LLM_DISAMBIGUATE", True)
    )
    if use_llm and (user_query or indicator_identifier):
        chosen = svc.resolve_with_llm(user_query or str(indicator_identifier), candidates)
        return chosen
    return candidates[0][0] if candidates else None
