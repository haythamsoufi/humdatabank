"""
Integration tests for AIVectorStore.hybrid_search_per_document's batched (window-function)
implementation, verifying it returns the same per-document ranking as the original
one-query-per-document loop, against a real Postgres + pgvector database.

Context: hybrid_search_per_document previously issued 2 queries (vector + keyword) PER
document_id in scope, which meant up to ~500 sequential DB round-trips for a full_coverage
document search across ~250 documents (PUBLIC_DOC_FULL_COVERAGE_MAX_DOCS). This is a
classic N+1 pattern. The batched implementation replaces the loop with 2 total queries
(one per search strategy) using ROW_NUMBER() OVER (PARTITION BY document_id ...).
"""
from unittest.mock import patch

import pytest

from app.models import AIDocument
from app.models.embeddings import AIDocumentChunk, AIEmbedding
from app.models.enums import AIDocumentProcessingStatusValue


def _make_vector(seed: float, dims: int = 1536) -> list[float]:
    """Deterministic pseudo-embedding: mostly zeros with one distinguishing component,
    so cosine similarity/ordering between documents is fully predictable in tests."""
    vec = [0.01] * dims
    vec[0] = seed
    return vec


@pytest.mark.unit
class TestHybridSearchPerDocumentBatching:
    @pytest.fixture
    def store(self, app):
        with app.app_context():
            from unittest.mock import MagicMock, patch

            with patch("app.services.ai.documents.vector_store.AIEmbeddingService") as mock_emb:
                mock_service = MagicMock()
                mock_service.model = "test-model"
                mock_service.dimensions = 1536
                mock_emb.return_value = mock_service

                from app.services.ai.documents.vector_store import AIVectorStore

                return AIVectorStore()

    def _seed_document(self, db_session, *, title, chunks_content, seeds, is_public=True):
        """Create one AIDocument with N chunks, each with its own embedding vector."""
        doc = AIDocument(
            title=title,
            filename=f"{title.lower().replace(' ', '_')}.pdf",
            file_type="pdf",
            is_public=is_public,
            searchable=True,
            processing_status=AIDocumentProcessingStatusValue.completed.value,
        )
        db_session.add(doc)
        db_session.flush()

        chunk_ids = []
        for idx, (content, seed) in enumerate(zip(chunks_content, seeds)):
            chunk = AIDocumentChunk(
                document_id=doc.id,
                content=content,
                content_length=len(content),
                chunk_index=idx,
                chunk_type="semantic",
            )
            db_session.add(chunk)
            db_session.flush()

            embedding = AIEmbedding(
                document_id=doc.id,
                chunk_id=chunk.id,
                embedding=_make_vector(seed),
                model="test-model",
                dimensions=1536,
            )
            db_session.add(embedding)
            chunk_ids.append(chunk.id)

        db_session.commit()
        db_session.refresh(doc)
        return doc, chunk_ids

    def test_batched_matches_looped_per_document_ranking(self, app, db_session, store):
        """The batched window-function query must return the same top-N chunks per
        document (by similarity) as the original one-query-per-document loop."""
        with app.app_context():
            doc_a, chunks_a = self._seed_document(
                db_session,
                title="Kenya Annual Report 2024",
                chunks_content=[
                    "Kenya volunteers increased significantly this year.",
                    "Kenya staff numbers remained stable.",
                    "Kenya budget allocation details for programmes.",
                ],
                seeds=[0.95, 0.5, 0.1],
            )
            doc_b, chunks_b = self._seed_document(
                db_session,
                title="Nepal Unified Plan 2026",
                chunks_content=[
                    "Nepal migration and displacement overview.",
                    "Nepal volunteers and staff overview.",
                ],
                seeds=[0.4, 0.9],
            )

            doc_ids = [doc_a.id, doc_b.id]
            query_embedding = _make_vector(1.0)

            with patch.object(store, "_get_cached_embedding", return_value=(query_embedding, 0.0)):
                batched = store.hybrid_search_per_document(
                    "volunteers",
                    doc_ids,
                    chunks_per_doc=1,
                    user_id=None,
                    user_role="public",
                )
                looped = store._hybrid_search_per_document_looped(
                    "volunteers",
                    doc_ids,
                    chunks_per_doc=1,
                    keyword_weight=0.3,
                    vector_weight=0.7,
                    filters=None,
                    user_id=None,
                    user_role="public",
                    query_embedding=query_embedding,
                )

            assert len(batched) == 2
            assert len(looped) == 2

            batched_by_doc = {int(r["document_id"]): r for r in batched}
            looped_by_doc = {int(r["document_id"]): r for r in looped}

            assert set(batched_by_doc.keys()) == {doc_a.id, doc_b.id}
            assert set(looped_by_doc.keys()) == {doc_a.id, doc_b.id}

            # Highest-similarity chunk per document must match between batched and looped.
            for doc_id in doc_ids:
                assert batched_by_doc[doc_id]["chunk_id"] == looped_by_doc[doc_id]["chunk_id"], (
                    f"doc {doc_id}: batched picked chunk {batched_by_doc[doc_id]['chunk_id']} "
                    f"but looped picked {looped_by_doc[doc_id]['chunk_id']}"
                )

            # Doc A's top chunk (by construction) is the one with seed 0.95 (index 0).
            assert batched_by_doc[doc_a.id]["chunk_id"] == chunks_a[0]
            # Doc B's top chunk (by construction) is the one with seed 0.9 (index 1).
            assert batched_by_doc[doc_b.id]["chunk_id"] == chunks_b[1]

    def test_batched_respects_chunks_per_doc_limit(self, app, db_session, store):
        with app.app_context():
            doc, chunk_ids = self._seed_document(
                db_session,
                title="Chad Annual Report 2024",
                chunks_content=[f"Chad content chunk {i}." for i in range(5)],
                seeds=[0.9, 0.8, 0.7, 0.6, 0.5],
            )
            query_embedding = _make_vector(1.0)

            with patch.object(store, "_get_cached_embedding", return_value=(query_embedding, 0.0)):
                results = store.hybrid_search_per_document(
                    "content",
                    [doc.id],
                    chunks_per_doc=2,
                    user_id=None,
                    user_role="public",
                )

            assert len(results) == 2
            returned_chunk_ids = {r["chunk_id"] for r in results}
            # The two highest-similarity chunks (seeds 0.9, 0.8) must be the ones returned.
            assert returned_chunk_ids == {chunk_ids[0], chunk_ids[1]}

    def test_batched_excludes_non_public_documents(self, app, db_session, store):
        with app.app_context():
            public_doc, public_chunks = self._seed_document(
                db_session,
                title="Public Doc",
                chunks_content=["Public volunteers content."],
                seeds=[0.9],
                is_public=True,
            )
            private_doc, private_chunks = self._seed_document(
                db_session,
                title="Private Doc",
                chunks_content=["Private volunteers content."],
                seeds=[0.95],
                is_public=False,
            )
            query_embedding = _make_vector(1.0)

            with patch.object(store, "_get_cached_embedding", return_value=(query_embedding, 0.0)):
                results = store.hybrid_search_per_document(
                    "volunteers",
                    [public_doc.id, private_doc.id],
                    chunks_per_doc=1,
                    user_id=None,
                    user_role="public",
                )

            result_doc_ids = {int(r["document_id"]) for r in results}
            assert result_doc_ids == {public_doc.id}

    def test_batched_returns_empty_for_no_documents(self, app, store):
        with app.app_context():
            assert store.hybrid_search_per_document("volunteers", [], chunks_per_doc=5) == []
