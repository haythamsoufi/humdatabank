"""
AI Vector Store Service

Manages storage and retrieval of document embeddings using pgvector.
Provides efficient similarity search and hybrid search capabilities.
"""

import hashlib
import json
import logging
import re
from datetime import date
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy import text, func, inspect as sa_inspect
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError
from flask import current_app

from app.extensions import db
from app.models import AIDocument, AIDocumentChunk, AIEmbedding, Country
from app.models.embeddings import ai_document_countries
from app.services.ai_embedding_service import AIEmbeddingService, EmbeddingCache
from app.utils.sql_utils import safe_ilike_pattern

logger = logging.getLogger(__name__)


class VectorStoreError(Exception):
    """Raised when vector store operations fail."""
    pass


class AIVectorStore:
    """
    Service for managing document embeddings in pgvector.

    Features:
    - Store and retrieve embeddings
    - Cosine similarity search
    - Hybrid search (vector + keyword)
    - Filtered search by metadata
    - Permission-aware search
    """

    def __init__(self):
        """Initialize the vector store."""
        self.embedding_service = AIEmbeddingService()
        # Per-instance cache: avoids redundant embedding API calls for repeated queries within a session.
        self._query_cache = EmbeddingCache(max_size=500)

    def _get_cached_embedding(self, text: str) -> Tuple[List[float], float]:
        """Return embedding for text, using the per-instance cache to avoid redundant API calls."""
        cache_key = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        cached = self._query_cache.get(cache_key)
        if cached is not None:
            logger.debug("Embedding cache hit for query (key=%s)", cache_key[:12])
            return cached
        embedding, cost = self.embedding_service.generate_embedding(text)
        self._query_cache.set(cache_key, embedding, cost)
        return embedding, cost

    def clear_embedding_cache(self) -> None:
        """Clear the per-instance embedding cache (e.g. after model change or admin action)."""
        self._query_cache.clear()
        logger.info("AIVectorStore: embedding cache cleared")

    # Temporal signals that indicate the user wants the most recent information
    _TEMPORAL_SIGNALS_RE = re.compile(
        r"\b(latest|recent|current|newest|new|now|today|this year|last year|"
        r"most recent|up to date|updated|2024|2025|2026)\b",
        re.IGNORECASE,
    )

    @staticmethod
    def _has_temporal_signal(query: str) -> bool:
        """Return True if the query contains recency signals."""
        return bool(AIVectorStore._TEMPORAL_SIGNALS_RE.search(query or ""))

    @staticmethod
    def _apply_temporal_boost(
        results: List[Dict[str, Any]],
        boost_factor: float = 0.05,
    ) -> List[Dict[str, Any]]:
        """
        Boost combined_score for results from more recent documents.
        Documents with a known document_date get a small recency bonus;
        documents without a date are not penalised.
        """
        today = date.today()
        for r in results:
            doc_date_raw = r.get("document_date")
            if not doc_date_raw:
                continue
            try:
                if isinstance(doc_date_raw, str):
                    doc_date = date.fromisoformat(doc_date_raw[:10])
                else:
                    doc_date = doc_date_raw
                # Days since the doc was published (0 = today, larger = older)
                age_days = max(0, (today - doc_date).days)
                # Recency bonus decays over ~5 years (1825 days)
                recency_bonus = boost_factor * max(0.0, 1.0 - age_days / 1825.0)
                r["combined_score"] = r.get("combined_score", 0.0) + recency_bonus
            except Exception as e:
                logger.debug("Temporal boost: could not parse date for result: %s", e)
        return results

    @staticmethod
    def _country_id_filter(country_id: int):
        """
        Build a filter condition that matches documents related to a country_id.

        Matches documents where:
        - Legacy country_id matches, OR
        - Country is in the M2M ai_document_countries table, OR
        - Document has geographic_scope = 'global' (applies to all countries)
        """
        return db.or_(
            AIDocument.country_id == country_id,
            AIDocument.id.in_(
                db.select(ai_document_countries.c.ai_document_id).where(
                    ai_document_countries.c.country_id == country_id
                )
            ),
            AIDocument.geographic_scope == 'global',
        )

    @staticmethod
    def _country_name_filter(country_name: str):
        """
        Build a filter condition that matches documents by country name.

        Matches via legacy fields, M2M relationship, or global scope.
        Uses safe_ilike_pattern to prevent SQL injection via user-supplied filters.
        """
        cn = (country_name or "").strip()
        if not cn:
            return AIDocument.geographic_scope == 'global'
        exact_pat = safe_ilike_pattern(cn, prefix=False, suffix=False)
        contains_pat = safe_ilike_pattern(cn)
        return db.or_(
            AIDocument.country_name.ilike(exact_pat),
            AIDocument.country_name.ilike(contains_pat),
            AIDocument.country.has(Country.name.ilike(exact_pat)),
            AIDocument.country.has(Country.name.ilike(contains_pat)),
            AIDocument.countries.any(Country.name.ilike(exact_pat)),
            AIDocument.countries.any(Country.name.ilike(contains_pat)),
            AIDocument.geographic_scope == 'global',
        )

    @staticmethod
    def _format_chunk_result(
        chunk: AIDocumentChunk,
        document: AIDocument,
        *,
        similarity_score: Optional[float] = None,
        keyword_score: Optional[float] = None,
        embedding: Optional[AIEmbedding] = None,
    ) -> Dict[str, Any]:
        """Build a single result dict from chunk + document. Reduces duplication across search methods."""
        try:
            doc_country_name = (
                (document.country.name if getattr(document, "country", None) else None)
                or getattr(document, "country_name", None)
            )
        except Exception as e:
            logger.debug("_format_chunk_result: doc_country_name failed: %s", e)
            doc_country_name = getattr(document, "country_name", None)
        try:
            doc_country_iso3 = getattr(getattr(document, "country", None), "iso3", None)
        except Exception as e:
            logger.debug("_format_chunk_result: doc_country_iso3 failed: %s", e)
            doc_country_iso3 = None

        # Build multi-country list (include region so callers can filter by platform's country map)
        try:
            doc_countries = [
                {
                    "id": c.id,
                    "name": c.name,
                    "iso3": getattr(c, "iso3", None),
                    "region": getattr(c, "region", None),
                }
                for c in (document.countries or [])
            ]
        except Exception as e:
            logger.debug("_format_chunk_result: doc_countries failed: %s", e)
            doc_countries = []

        # Serialize document_date safely
        raw_doc_date = getattr(document, "document_date", None)
        doc_date_str = raw_doc_date.isoformat() if raw_doc_date else None

        out: Dict[str, Any] = {
            "chunk_id": chunk.id,
            "document_id": document.id,
            "document_title": document.title,
            "document_filename": document.filename,
            "document_type": document.file_type,
            "document_country_id": getattr(document, "country_id", None),
            "document_country_name": doc_country_name,
            "document_country_iso3": doc_country_iso3,
            "document_geographic_scope": getattr(document, "geographic_scope", None),
            "document_countries": doc_countries,
            "is_system_document": getattr(document, "submitted_document_id", None) is not None,
            "is_api_import": getattr(document, "source_url", None) is not None,
            "chunk_index": chunk.chunk_index,
            "page_number": chunk.page_number,
            "section_title": chunk.section_title,
            "content": chunk.content,
            "token_count": chunk.token_count,
            # Enriched provenance metadata
            "document_date": doc_date_str,
            "document_language": getattr(document, "document_language", None),
            "document_category": getattr(document, "document_category", None),
            "source_organization": getattr(document, "source_organization", None),
            "quality_score": getattr(document, "quality_score", None),
            # Chunk semantic metadata
            "semantic_type": getattr(chunk, "semantic_type", None),
            "heading_hierarchy": getattr(chunk, "heading_hierarchy", None),
        }
        if similarity_score is not None:
            out["similarity_score"] = float(similarity_score)
        if keyword_score is not None:
            out["keyword_score"] = float(keyword_score)
        if embedding is not None:
            out["metadata"] = {
                **(chunk.extra_metadata or {}),
                "embedding_model": embedding.model,
            }
        return out

    @staticmethod
    def _apply_document_permission_filters(query, user_id: Optional[int], user_role: Optional[str]):
        """
        Apply document visibility filters (is_public, user_id, allowed_roles).
        Use for any query that joins AIDocument. Returns the modified query.
        """
        if user_role in ("admin", "system_manager"):
            return query
        if user_id:
            query = query.filter(
                db.or_(
                    AIDocument.is_public == True,
                    AIDocument.user_id == user_id,
                )
            )
        else:
            query = query.filter(AIDocument.is_public == True)
        role = (user_role or "public").strip().lower()
        role_json = json.dumps([role])
        query = query.filter(
            db.or_(
                AIDocument.is_public == True,
                AIDocument.allowed_roles.is_(None),
                text("(ai_documents.allowed_roles::jsonb @> CAST(:role_json AS jsonb))").bindparams(role_json=role_json),
            )
        )
        return query

    def store_document_embeddings(
        self,
        document_id: int,
        chunks_with_embeddings: List[Tuple[AIDocumentChunk, List[float], float]]
    ) -> int:
        """
        Store embeddings for document chunks.

        Args:
            document_id: ID of the parent document
            chunks_with_embeddings: List of (chunk, embedding_vector, cost) tuples

        Returns:
            Number of embeddings stored

        Raises:
            VectorStoreError: If storage fails
        """
        try:
            stored_count = 0
            total_cost = 0.0

            # IMPORTANT: chunks may be committed/expired or even concurrently deleted/recreated
            # (e.g. duplicate import workers). Never rely on attribute refresh of ORM instances
            # here; extract identity safely and verify rows still exist for this document.
            chunk_id_to_payload: Dict[int, Tuple[List[float], float]] = {}
            for c, vec, cost in chunks_with_embeddings:
                cid: Optional[int] = None
                try:
                    ident = sa_inspect(c).identity
                    if ident and len(ident) > 0 and ident[0] is not None:
                        cid = int(ident[0])
                except Exception as e:
                    logger.debug("store_embeddings: chunk identity inspect failed: %s", e)
                    cid = None
                if cid is None:
                    # Fallback (best-effort); avoid crashing on ObjectDeletedError
                    try:
                        raw = getattr(c, "id", None)
                        cid = int(raw) if raw is not None else None
                    except Exception as e:
                        logger.debug("store_embeddings: chunk id fallback failed: %s", e)
                        cid = None
                if cid is None:
                    continue
                chunk_id_to_payload[cid] = (vec, cost)

            chunk_ids = list(chunk_id_to_payload.keys())
            existing_by_chunk_id: Dict[int, AIEmbedding] = {}
            if chunk_ids:
                for e in AIEmbedding.query.filter(AIEmbedding.chunk_id.in_(chunk_ids)).all():
                    existing_by_chunk_id[int(e.chunk_id)] = e

            # Only store embeddings for chunks that still exist (and belong to this document).
            # This prevents FK errors and makes concurrent processing degrade safely.
            existing_chunk_ids: set[int] = set()
            if chunk_ids:
                rows = (
                    db.session.query(AIDocumentChunk.id)
                    .filter(AIDocumentChunk.document_id == document_id)
                    .filter(AIDocumentChunk.id.in_(chunk_ids))
                    .all()
                )
                existing_chunk_ids = {int(r[0]) for r in rows if r and r[0] is not None}

            for chunk_id, (embedding_vector, cost) in chunk_id_to_payload.items():
                if chunk_id not in existing_chunk_ids:
                    logger.warning(
                        "Skipping embedding storage for missing chunk_id=%s document_id=%s (likely concurrent reprocess/delete)",
                        chunk_id,
                        document_id,
                    )
                    continue
                # Safety: ensure vectors match configured dimensions (prevents DB corruption)
                self.embedding_service._validate_dimensions(embedding_vector)  # type: ignore[attr-defined]

                existing = existing_by_chunk_id.get(int(chunk_id))

                if existing:
                    existing.embedding = embedding_vector
                    existing.model = self.embedding_service.model
                    existing.dimensions = len(embedding_vector)
                    existing.generation_cost_usd = cost
                else:
                    # Handle race where another worker inserts the same chunk_id embedding.
                    try:
                        with db.session.begin_nested():
                            emb = AIEmbedding(
                                document_id=document_id,
                                chunk_id=chunk_id,
                                embedding=embedding_vector,
                                model=self.embedding_service.model,
                                dimensions=len(embedding_vector),
                                generation_cost_usd=cost,
                            )
                            db.session.add(emb)
                            db.session.flush()
                            existing_by_chunk_id[int(chunk_id)] = emb
                    except IntegrityError:
                        # Could be a unique-race (another worker inserted) OR a FK race
                        # (chunk deleted after our existence check). Distinguish by re-checking chunk.
                        still_exists = (
                            db.session.query(AIDocumentChunk.id)
                            .filter(AIDocumentChunk.document_id == document_id)
                            .filter(AIDocumentChunk.id == chunk_id)
                            .scalar()
                        )
                        if not still_exists:
                            logger.warning(
                                "Skipping embedding insert for chunk_id=%s document_id=%s (chunk disappeared during insert)",
                                chunk_id,
                                document_id,
                            )
                            continue

                        # Another worker likely inserted; fetch and update.
                        emb = AIEmbedding.query.filter_by(chunk_id=chunk_id).one_or_none()
                        if emb:
                            emb.embedding = embedding_vector
                            emb.model = self.embedding_service.model
                            emb.dimensions = len(embedding_vector)
                            emb.generation_cost_usd = cost
                            existing_by_chunk_id[int(chunk_id)] = emb
                        else:
                            # If it still doesn't exist, re-raise to surface unexpected constraints.
                            raise

                stored_count += 1
                total_cost += cost

            db.session.commit()

            # Keep document total_embeddings in sync for stats and document library
            doc = db.session.get(AIDocument, document_id)
            if doc is not None:
                actual_count = (
                    db.session.query(func.count(AIEmbedding.id))
                    .filter(AIEmbedding.document_id == document_id)
                    .scalar()
                )
                doc.total_embeddings = int(actual_count or 0)
                db.session.commit()

            logger.info(f"Stored {stored_count} embeddings for document {document_id}, cost: ${total_cost:.4f}")
            return stored_count

        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to store embeddings: {e}", exc_info=True)
            raise VectorStoreError(f"Failed to store embeddings: {e}")

    def search_similar(
        self,
        query_text: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        user_role: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar document chunks using vector similarity.

        Args:
            query_text: Text to search for
            top_k: Number of results to return
            filters: Optional filters (document_id, file_type, etc.)
            user_id: User ID for permission filtering
            user_role: User role for permission filtering

        Returns:
            List of matching chunks with similarity scores and metadata

        Raises:
            VectorStoreError: If search fails
        """
        try:
            query_embedding, _ = self._get_cached_embedding(query_text)
            formatted_results = self._search_similar_with_embedding(
                query_embedding=query_embedding,
                query_text=query_text,
                top_k=top_k,
                filters=filters,
                user_id=user_id,
                user_role=user_role,
            )
            sample = [
                {
                    "document_id": r["document_id"],
                    "title": r["document_title"],
                    "filename": r["document_filename"],
                    "page_number": r["page_number"],
                    "score": r["similarity_score"],
                }
                for r in formatted_results[: min(5, len(formatted_results))]
            ]
            logger.info(
                "Vector search results: count=%s sample=%s",
                len(formatted_results),
                sample,
            )
            return formatted_results

        except Exception as e:
            logger.error(f"Vector search failed: {e}", exc_info=True)
            try:
                db.session.rollback()
            except Exception as rb_err:
                logger.debug("Vector search: rollback after error failed: %s", rb_err)
            raise VectorStoreError(f"Vector search failed: {e}")

    def _search_similar_with_embedding(
        self,
        query_embedding: List[float],
        query_text: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        user_role: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Vector search using a pre-computed embedding (avoids redundant API calls).
        Same logic as search_similar but skips embedding generation.
        """
        try:
            query_preview = (query_text[:200] + '...') if len(query_text) > 200 else query_text
            logger.info(
                "Vector search start: top_k=%s filters=%s user_id=%s role=%s query=%s",
                top_k,
                filters,
                user_id,
                user_role,
                query_preview
            )

            # Build base query with similarity search (using provided embedding)
            similarity_query = db.session.query(
                AIEmbedding,
                AIDocumentChunk,
                AIDocument,
                (1 - AIEmbedding.embedding.cosine_distance(query_embedding)).label('similarity')
            ).join(
                AIDocumentChunk, AIEmbedding.chunk_id == AIDocumentChunk.id
            ).join(
                AIDocument, AIEmbedding.document_id == AIDocument.id
            ).filter(
                AIDocument.searchable == True,
                AIDocument.processing_status == 'completed'
            )
            try:
                similarity_query = similarity_query.options(joinedload(AIDocument.country))
            except Exception as e:
                logger.debug("_search_similar_with_embedding: joinedload country failed: %s", e)

            similarity_query = self._apply_document_permission_filters(
                similarity_query, user_id, user_role
            )

            # Apply custom filters
            if filters:
                if "country_id" in filters and filters.get("country_id"):
                    similarity_query = similarity_query.filter(self._country_id_filter(int(filters["country_id"])))
                if "document_id" in filters:
                    similarity_query = similarity_query.filter(AIDocument.id == filters["document_id"])
                if "file_type" in filters:
                    similarity_query = similarity_query.filter(AIDocument.file_type == filters["file_type"])
                if "user_id" in filters:
                    similarity_query = similarity_query.filter(AIDocument.user_id == filters["user_id"])
                # Source filters (optional):
                # - is_api_import: True => documents imported from external API (AIDocument.source_url IS NOT NULL)
                # - is_system_document: True => documents uploaded via the system (AIDocument.submitted_document_id IS NOT NULL)
                if "is_api_import" in filters:
                    if filters.get("is_api_import") is True:
                        similarity_query = similarity_query.filter(AIDocument.source_url.isnot(None))
                    elif filters.get("is_api_import") is False:
                        similarity_query = similarity_query.filter(AIDocument.source_url.is_(None))
                if "is_system_document" in filters:
                    if filters.get("is_system_document") is True:
                        similarity_query = similarity_query.filter(AIDocument.submitted_document_id.isnot(None))
                    elif filters.get("is_system_document") is False:
                        similarity_query = similarity_query.filter(AIDocument.submitted_document_id.is_(None))
                if "workflow_role" in filters and (filters.get("workflow_role") or "").strip():
                    role_val = str(filters["workflow_role"]).strip()
                    role_json = json.dumps([role_val])
                    similarity_query = similarity_query.filter(
                        text("(ai_documents.extra_metadata->'roles')::jsonb @> CAST(:workflow_role_json AS jsonb)").bindparams(workflow_role_json=role_json)
                    )
                if "country_name" in filters and (filters.get("country_name") or "").strip():
                    similarity_query = similarity_query.filter(self._country_name_filter(filters["country_name"]))
                # Optional date_range filter: {"min": date, "max": date} or (min_date, max_date)
                if "date_range" in filters and filters.get("date_range"):
                    dr = filters["date_range"]
                    min_d, max_d = None, None
                    if isinstance(dr, (list, tuple)) and len(dr) >= 2:
                        min_d, max_d = dr[0], dr[1]
                    elif isinstance(dr, dict):
                        min_d, max_d = dr.get("min"), dr.get("max")
                    if min_d is not None:
                        d = min_d if isinstance(min_d, date) else date.fromisoformat(str(min_d)[:10])
                        similarity_query = similarity_query.filter(AIDocument.document_date >= d)
                    if max_d is not None:
                        d = max_d if isinstance(max_d, date) else date.fromisoformat(str(max_d)[:10])
                        similarity_query = similarity_query.filter(AIDocument.document_date <= d)

            # Order by similarity and limit (text() for label consistency with search_similar)
            results = similarity_query.order_by(text("similarity DESC")).limit(top_k).all()

            # Format results
            formatted_results = [
                self._format_chunk_result(chunk, document, similarity_score=float(similarity), embedding=embedding)
                for embedding, chunk, document, similarity in results
            ]

            sample = [
                {"document_id": r["document_id"], "title": r["document_title"], "filename": r["document_filename"], "page_number": r["page_number"], "score": r["similarity_score"]}
                for r in formatted_results[:5]
            ]
            logger.info("Vector search results: count=%s sample=%s", len(formatted_results), sample)
            return formatted_results

        except Exception as e:
            logger.error(f"Vector search with embedding failed: {e}", exc_info=True)
            try:
                db.session.rollback()
            except Exception as rb_err:
                logger.debug("Vector search with embedding: rollback failed: %s", rb_err)
            raise VectorStoreError(f"Vector search with embedding failed: {e}")

    def _get_system_document_results_with_embedding(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fast system document search using pre-computed embedding.
        Only searches documents uploaded via forms/document management.
        """
        try:
            # Respect caller intent: if they explicitly request API-imported docs or explicitly exclude
            # system docs, do not return system documents.
            if filters:
                if filters.get("is_api_import") is True:
                    return []
                if filters.get("is_system_document") is False:
                    return []

            # Build query specifically for system documents
            similarity_query = db.session.query(
                AIEmbedding,
                AIDocumentChunk,
                AIDocument,
                (1 - AIEmbedding.embedding.cosine_distance(query_embedding)).label('similarity')
            ).join(
                AIDocumentChunk, AIEmbedding.chunk_id == AIDocumentChunk.id
            ).join(
                AIDocument, AIEmbedding.document_id == AIDocument.id
            ).filter(
                AIDocument.searchable == True,
                AIDocument.processing_status == 'completed',
                AIDocument.submitted_document_id.isnot(None),  # ONLY system documents
            )

            # Apply country filter if provided
            if filters and filters.get("country_id"):
                similarity_query = similarity_query.filter(self._country_id_filter(int(filters["country_id"])))
            # Apply date_range filter if provided
            if filters and filters.get("date_range"):
                dr = filters["date_range"]
                min_d, max_d = None, None
                if isinstance(dr, (list, tuple)) and len(dr) >= 2:
                    min_d, max_d = dr[0], dr[1]
                elif isinstance(dr, dict):
                    min_d, max_d = dr.get("min"), dr.get("max")
                if min_d is not None:
                    d = min_d if isinstance(min_d, date) else date.fromisoformat(str(min_d)[:10])
                    similarity_query = similarity_query.filter(AIDocument.document_date >= d)
                if max_d is not None:
                    d = max_d if isinstance(max_d, date) else date.fromisoformat(str(max_d)[:10])
                    similarity_query = similarity_query.filter(AIDocument.document_date <= d)

            # Order by similarity and limit (text() for label consistency)
            results = similarity_query.order_by(text("similarity DESC")).limit(top_k).all()

            if not results:
                return []

            # Format results
            formatted_results = [
                self._format_chunk_result(chunk, document, similarity_score=float(similarity), embedding=embedding)
                for embedding, chunk, document, similarity in results
            ]
            for r in formatted_results:
                r["is_system_document"] = True
                r["is_api_import"] = False

            if formatted_results:
                logger.info("System document search: found %d chunks", len(formatted_results))

            return formatted_results

        except Exception as e:
            logger.error("System document search failed: %s", e, exc_info=True)
            try:
                db.session.rollback()
            except Exception as rb_err:
                logger.debug("System document search: rollback failed: %s", rb_err)
            raise VectorStoreError(f"System document search failed: {e}")

    def hybrid_search(
        self,
        query_text: str,
        top_k: int = 5,
        keyword_weight: float = 0.3,
        vector_weight: float = 0.7,
        vector_query_text: Optional[str] = None,
        keyword_query_text: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        user_role: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search combining vector similarity and keyword matching.

        Args:
            query_text: Original user query text (used for logging/backwards compatibility).
            top_k: Number of results to return
            keyword_weight: Weight for keyword score (0-1)
            vector_weight: Weight for vector similarity score (0-1)
            vector_query_text: Optional. If provided, use this text for embedding-based retrieval (semantic search).
                Useful when the original query contains boolean syntax, excessive quoting, or other patterns that
                degrade embedding quality.
            keyword_query_text: Optional. If provided, use this text for keyword/FTS retrieval.
                Useful when you want to preserve boolean / quoted phrase syntax for lexical matching.
            filters: Optional filters
            user_id: User ID for permission filtering
            user_role: User role for permission filtering

        Returns:
            List of matching chunks with combined scores
        """
        # Backwards-compatible defaults: if specialized query strings are not provided,
        # use the original query_text for both semantic and keyword retrieval.
        vq = (vector_query_text or "").strip() or (query_text or "").strip()
        kq = (keyword_query_text or "").strip() or (query_text or "").strip()

        # Generate embedding once (cache-aware) and reuse for all vector searches in this call.
        query_embedding, _ = self._get_cached_embedding(vq)

        # Get vector search results (using pre-computed embedding)
        vector_results = self._search_similar_with_embedding(
            query_embedding=query_embedding,
            query_text=vq,
            top_k=top_k * 2,  # Reduced from 3x to 2x for speed
            filters=filters,
            user_id=user_id,
            user_role=user_role
        )

        # Get keyword search results (no embedding needed)
        keyword_results = self._keyword_search(
            query_text=kq,
            top_k=top_k * 2,  # Reduced from 3x to 2x for speed
            filters=filters,
            user_id=user_id,
            user_role=user_role
        )

        # PRIORITY: Ensure system documents (uploaded via forms) are always included
        # Uses same embedding - no extra API call needed
        system_doc_results = self._get_system_document_results_with_embedding(
            query_embedding=query_embedding,
            top_k=top_k,
            filters=filters,
        )

        # Merge system document results into vector results (they'll get priority boost in combine)
        existing_chunk_ids = {r['chunk_id'] for r in vector_results}
        for sdr in system_doc_results:
            if sdr['chunk_id'] not in existing_chunk_ids:
                vector_results.append(sdr)
                existing_chunk_ids.add(sdr['chunk_id'])

        # Combine and re-rank results
        combined_results = self._combine_search_results(
            vector_results=vector_results,
            keyword_results=keyword_results,
            vector_weight=vector_weight,
            keyword_weight=keyword_weight
        )

        # Diversity: cap chunks per document so results span more documents (important for 200+ docs).
        max_per_doc = int(current_app.config.get('AI_DOCUMENT_DIVERSITY_MAX_CHUNKS_PER_DOC', 0))
        if max_per_doc > 0:
            combined_results = self._apply_diversity_cap(combined_results, max_per_doc=max_per_doc)

        # Temporal boost: when query signals recency preference, boost results from recent documents.
        if self._has_temporal_signal(query_text):
            boost = float(current_app.config.get('AI_TEMPORAL_BOOST_FACTOR', 0.05))
            combined_results = self._apply_temporal_boost(combined_results, boost_factor=boost)
            # Re-sort after boosting
            combined_results.sort(key=lambda r: r.get("combined_score", 0.0), reverse=True)

        # Optional reranking (cross-encoder or API) for higher precision.
        if current_app.config.get('AI_RERANK_ENABLED'):
            # Prefer the semantic query for reranking so boolean-heavy syntax does not confuse the reranker.
            combined_results = self._rerank_results(vq, combined_results, top_k)

        # Return top_k results
        return combined_results[:top_k]

    def keyword_search(
        self,
        query_text: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        user_role: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Public wrapper for keyword-based search.
        Kept as a thin shim around the internal implementation to avoid external callers
        reaching into private methods.
        """
        return self._keyword_search(
            query_text=query_text,
            top_k=top_k,
            filters=filters,
            user_id=user_id,
            user_role=user_role,
        )

    def _keyword_search(
        self,
        query_text: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        user_role: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Perform keyword-based search using PostgreSQL full-text search."""
        try:
            keywords = query_text.lower().split()

            # Prefer Postgres full-text search (no schema changes required).
            # Note: performance improves further with a GIN index on to_tsvector(content).
            ts_query = func.websearch_to_tsquery('simple', query_text)
            ts_vector = func.to_tsvector('simple', AIDocumentChunk.content)
            rank = func.ts_rank_cd(ts_vector, ts_query)

            query = (
                db.session.query(AIDocumentChunk, AIDocument, rank.label("rank"))
                .join(AIDocument, AIDocumentChunk.document_id == AIDocument.id)
                .filter(
                    AIDocument.searchable == True,
                    AIDocument.processing_status == 'completed',
                    ts_vector.op('@@')(ts_query),
                )
            )
            try:
                query = query.options(joinedload(AIDocument.country))
            except Exception as e:
                logger.debug("keyword search: joinedload country failed: %s", e)

            query = self._apply_document_permission_filters(query, user_id, user_role)

            # Apply additional filters
            if filters:
                if 'document_id' in filters:
                    query = query.filter(AIDocument.id == filters['document_id'])
                if 'file_type' in filters:
                    query = query.filter(AIDocument.file_type == filters['file_type'])
                if 'country_id' in filters and filters.get('country_id'):
                    query = query.filter(self._country_id_filter(int(filters['country_id'])))
                # Source filters (optional):
                # - is_api_import: True => documents imported from external API (AIDocument.source_url IS NOT NULL)
                # - is_system_document: True => documents uploaded via the system (AIDocument.submitted_document_id IS NOT NULL)
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
                if 'country_name' in filters and (filters.get('country_name') or '').strip():
                    query = query.filter(self._country_name_filter(filters['country_name']))
                if "date_range" in filters and filters.get("date_range"):
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

            results = query.order_by(text("rank DESC")).limit(top_k).all()

            # Normalize rank to ~[0..1] for combination with vector similarity
            max_rank = 0.0
            for _, _, rnk in results:
                try:
                    max_rank = max(max_rank, float(rnk or 0.0))
                except Exception as e:
                    logger.debug("keyword search: max_rank normalization failed: %s", e)
                    continue

            formatted_results = []
            for chunk, document, rnk in results:
                try:
                    keyword_score = float(rnk or 0.0) / max_rank if max_rank > 0 else 0.0
                except Exception as e:
                    logger.debug("keyword search: keyword_score failed: %s", e)
                    keyword_score = 0.0
                formatted_results.append(
                    self._format_chunk_result(chunk, document, keyword_score=keyword_score)
                )

            return formatted_results

        except Exception as e:
            # Fallback to conservative ILIKE matching if FTS isn't available (older Postgres/config).
            logger.warning(f"Keyword search failed, falling back to ILIKE: {e}")
            try:
                keywords = query_text.lower().split()
                query = (
                    db.session.query(AIDocumentChunk, AIDocument)
                    .join(AIDocument, AIDocumentChunk.document_id == AIDocument.id)
                    .filter(AIDocument.searchable == True, AIDocument.processing_status == 'completed')
                )
                try:
                    query = query.options(joinedload(AIDocument.country))
                except Exception as e:
                    logger.debug("keyword search ILIKE fallback: joinedload failed: %s", e)

                query = self._apply_document_permission_filters(query, user_id, user_role)

                if filters:
                    if 'document_id' in filters:
                        query = query.filter(AIDocument.id == filters['document_id'])
                    if 'file_type' in filters:
                        query = query.filter(AIDocument.file_type == filters['file_type'])
                    if 'country_id' in filters and filters.get('country_id'):
                        query = query.filter(self._country_id_filter(int(filters['country_id'])))
                    if 'country_name' in filters and (filters.get('country_name') or '').strip():
                        query = query.filter(self._country_name_filter(filters['country_name']))

                keyword_conditions = []
                for keyword in keywords:
                    if len(keyword) > 2:
                        keyword_conditions.append(AIDocumentChunk.content.ilike(safe_ilike_pattern(keyword)))
                if keyword_conditions:
                    query = query.filter(db.or_(*keyword_conditions))

                results = query.limit(top_k).all()
                formatted_results = []
                for chunk, document in results:
                    content_lower = chunk.content.lower()
                    keyword_score = (
                        sum(1 for kw in keywords if kw in content_lower) / len(keywords)
                        if keywords
                        else 0.0
                    )
                    formatted_results.append(
                        self._format_chunk_result(chunk, document, keyword_score=float(keyword_score))
                    )
                return formatted_results
            except Exception as fallback_err:
                logger.warning("Keyword search ILIKE fallback also failed: %s", fallback_err)
                return []

    def _get_system_document_results(
        self,
        query_text: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        user_role: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve chunks specifically from system-uploaded documents (via forms/document management).

        This ensures documents uploaded by countries through the system are always considered,
        even if cross-lingual search (e.g., English query vs Portuguese content) ranks them lower.
        """
        try:
            # Respect caller intent: if they explicitly request API-imported docs or explicitly exclude
            # system docs, do not return system documents.
            if filters:
                if filters.get("is_api_import") is True:
                    return []
                if filters.get("is_system_document") is False:
                    return []

            # Generate embedding for query (cache-aware)
            query_embedding, _ = self._get_cached_embedding(query_text)

            # Build query specifically for system documents (submitted_document_id IS NOT NULL)
            similarity_query = db.session.query(
                AIEmbedding,
                AIDocumentChunk,
                AIDocument,
                (1 - AIEmbedding.embedding.cosine_distance(query_embedding)).label('similarity')
            ).join(
                AIDocumentChunk, AIEmbedding.chunk_id == AIDocumentChunk.id
            ).join(
                AIDocument, AIEmbedding.document_id == AIDocument.id
            ).filter(
                AIDocument.searchable == True,
                AIDocument.processing_status == 'completed',
                AIDocument.submitted_document_id.isnot(None),  # ONLY system documents
            )

            # Apply country filter if provided (multi-country aware)
            if filters and filters.get("country_id"):
                similarity_query = similarity_query.filter(self._country_id_filter(int(filters["country_id"])))

            # Order by similarity and limit
            results = similarity_query.order_by(text("similarity DESC")).limit(top_k * 2).all()

            if not results:
                return []

            # Format results
            formatted_results = [
                self._format_chunk_result(chunk, document, similarity_score=float(similarity), embedding=embedding)
                for embedding, chunk, document, similarity in results
            ]
            for r in formatted_results:
                r["is_system_document"] = True
                r["is_api_import"] = False

            if formatted_results:
                logger.info(
                    "System document search: found %d chunks from system-uploaded documents",
                    len(formatted_results)
                )

            return formatted_results

        except Exception as e:
            logger.error("System document search failed: %s", e, exc_info=True)
            try:
                db.session.rollback()
            except Exception as rb_err:
                logger.debug("System document search: rollback failed: %s", rb_err)
            raise VectorStoreError(f"System document search failed: {e}")

    def _combine_search_results(
        self,
        vector_results: List[Dict[str, Any]],
        keyword_results: List[Dict[str, Any]],
        vector_weight: float,
        keyword_weight: float,
        system_document_boost: float = 0.25,  # Boost for system-uploaded documents (high to overcome cross-lingual penalty)
    ) -> List[Dict[str, Any]]:
        """
        Combine vector and keyword results with weighted scoring.

        System-uploaded documents (via forms/document management) get a boost
        over API-imported documents (IFRC API/UPR) to prioritize country-submitted data.
        """
        # Create a map of chunk_id to results
        combined = {}

        # Add vector results
        for result in vector_results:
            chunk_id = result['chunk_id']
            combined[chunk_id] = result.copy()
            combined[chunk_id]['vector_score'] = result.get('similarity_score', 0.0)
            combined[chunk_id]['keyword_score'] = 0.0

        # Add/update with keyword results
        for result in keyword_results:
            chunk_id = result['chunk_id']
            if chunk_id in combined:
                combined[chunk_id]['keyword_score'] = result.get('keyword_score', 0.0)
                # Preserve source tracking from keyword results if not already set
                if 'is_system_document' not in combined[chunk_id]:
                    combined[chunk_id]['is_system_document'] = result.get('is_system_document', False)
                    combined[chunk_id]['is_api_import'] = result.get('is_api_import', False)
            else:
                combined[chunk_id] = result.copy()
                combined[chunk_id]['vector_score'] = 0.0
                combined[chunk_id]['keyword_score'] = result.get('keyword_score', 0.0)

        # Calculate combined scores with source priority boost
        for chunk_id, result in combined.items():
            vector_score = result.get('vector_score', 0.0)
            keyword_score = result.get('keyword_score', 0.0)
            base_score = (vector_score * vector_weight) + (keyword_score * keyword_weight)

            # Apply source priority boost
            # System documents (uploaded via forms/document management) get priority
            source_boost = 0.0
            if result.get('is_system_document', False):
                source_boost = system_document_boost
            elif result.get('is_api_import', False):
                source_boost = 0.0  # No boost for API imports

            # Strong keyword match boost: exact factual matches (e.g. "10,000 volunteers")
            # should not be outranked by many vector-similar chunks. Prevents queries like
            # "countries with 10,000 volunteers" from losing the right chunk after merge.
            keyword_match_boost = 0.0
            if keyword_score >= 0.9:
                keyword_match_boost = 0.2

            result['combined_score'] = base_score + source_boost + keyword_match_boost
            result['source_boost'] = source_boost

        # Sort by combined score
        sorted_results = sorted(combined.values(), key=lambda x: x['combined_score'], reverse=True)

        return sorted_results

    @staticmethod
    def _apply_diversity_cap(
        results: List[Dict[str, Any]],
        max_per_doc: int,
    ) -> List[Dict[str, Any]]:
        """
        Limit the number of chunks per document so results span more documents.
        Preserves order (by combined_score); keeps the top max_per_doc chunks per document_id.
        """
        if max_per_doc <= 0 or not results:
            return results
        doc_count: Dict[int, int] = {}
        out: List[Dict[str, Any]] = []
        for r in results:
            doc_id = r.get('document_id')
            if doc_id is None:
                out.append(r)
                continue
            try:
                doc_id = int(doc_id)
            except (TypeError, ValueError):
                out.append(r)
                continue
            n = doc_count.get(doc_id, 0)
            if n < max_per_doc:
                doc_count[doc_id] = n + 1
                out.append(r)
        return out

    def _rerank_results(
        self,
        query_text: str,
        results: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """Optionally rerank results via cross-encoder or API. Returns reordered list (length unchanged)."""
        try:
            from app.services.ai_rerank_service import rerank_chunks
            return rerank_chunks(
                query_text=query_text,
                chunks=results,
                top_k=top_k,
            )
        except Exception as e:
            logger.warning("Rerank failed, using original order: %s", e)
            return results

    def delete_document_embeddings(self, document_id: int) -> int:
        """
        Delete all embeddings for a document.

        Args:
            document_id: ID of the document

        Returns:
            Number of embeddings deleted
        """
        try:
            count = AIEmbedding.query.filter_by(document_id=document_id).delete()
            doc = db.session.get(AIDocument, document_id)
            if doc is not None:
                doc.total_embeddings = 0
            db.session.commit()
            logger.info(f"Deleted {count} embeddings for document {document_id}")
            return count
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to delete embeddings: {e}")
            raise VectorStoreError(f"Failed to delete embeddings: {e}")

    def get_document_statistics(self, document_id: int) -> Dict[str, Any]:
        """Get statistics about a document's embeddings."""
        try:
            doc = AIDocument.query.get(document_id)
            if not doc:
                return {}

            embedding_count = AIEmbedding.query.filter_by(document_id=document_id).count()

            return {
                'document_id': document_id,
                'title': doc.title,
                'total_chunks': doc.total_chunks,
                'total_embeddings': embedding_count,
                'embedding_model': doc.embedding_model,
                'embedding_dimensions': doc.embedding_dimensions,
            }
        except Exception as e:
            logger.error(f"Failed to get document statistics: {e}")
            return {}

    def reindex_document(self, document_id: int) -> bool:
        """
        Reindex a document (regenerate all embeddings).

        Useful when changing embedding models or fixing issues.
        """
        try:
            # Delete existing embeddings
            self.delete_document_embeddings(document_id)

            # Get all chunks
            chunks = AIDocumentChunk.query.filter_by(document_id=document_id).all()

            if not chunks:
                logger.warning(f"No chunks found for document {document_id}")
                return False

            # Generate new embeddings
            texts = [chunk.content for chunk in chunks]
            embeddings, total_cost = self.embedding_service.generate_embeddings_batch(texts)

            # Store new embeddings
            chunks_with_embeddings = [(chunks[i], embeddings[i], total_cost / len(embeddings)) for i in range(len(chunks))]
            self.store_document_embeddings(document_id, chunks_with_embeddings)

            logger.info(f"Reindexed document {document_id} with {len(embeddings)} embeddings")
            return True

        except Exception as e:
            logger.error(f"Failed to reindex document: {e}")
            return False
