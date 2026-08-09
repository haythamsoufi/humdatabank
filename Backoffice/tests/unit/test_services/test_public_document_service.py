import datetime
from typing import Any

import pytest

from app.models import AIDocument
from app.models.enums import AIDocumentProcessingStatusValue
from app.services.public.document_service import (
    PUBLIC_DOC_FULL_COVERAGE_CONTENT_CHARS,
    PUBLIC_DOC_MAX_CONTENT_CHARS,
    _build_search_filters,
    _document_type_key,
    _extract_year,
    _public_document_link_fields,
    _should_prioritize_latest_per_country,
    catalog_public_documents,
    filter_rows_to_public_documents,
    list_public_documents_in_scope,
    prioritize_latest_documents_per_country,
    search_public_documents,
    slim_public_document_chunk,
)
from app.services.upr.query_detection import query_requests_multi_year_documents


class TestPublicDocumentHelpers:
    def test_extract_year_from_query(self):
        assert _extract_year("Syria unified plan 2026 focus areas") == 2026
        assert _extract_year("no year here") is None

    def test_build_search_filters_upr_scope(self):
        filters = _build_search_filters("Syria unified plan 2026", year=2026)
        assert filters is not None
        assert filters.get("is_api_import") is True
        assert filters.get("is_system_document") is False
        assert filters.get("date_range") == {"min": "2026-01-01", "max": "2026-12-31"}

    def test_slim_public_document_chunk_truncates_content(self):
        row = {
            "chunk_id": 1,
            "document_id": 9,
            "document_title": "Syria Unified Plan 2026",
            "document_filename": "syria_upl_2026.pdf",
            "document_date": "2026-01-01",
            "document_category": "Unified Plan",
            "document_language": "en",
            "document_country_name": "Syria",
            "document_countries": [{"id": 1, "name": "Syria", "iso3": "SYR"}],
            "page_number": 4,
            "section_title": "Focus areas",
            "content": "x" * (PUBLIC_DOC_MAX_CONTENT_CHARS + 50),
            "combined_score": 0.82,
            "source_organization": "IFRC",
        }
        slim = slim_public_document_chunk(row, max_content_chars=100)
        assert slim["document_title"] == "Syria Unified Plan 2026"
        assert slim["countries"] == ["Syria"]
        assert slim["score"] == 0.82
        assert len(slim["content"]) <= 101
        assert slim["content"].endswith("…")

    def test_slim_public_document_chunk_includes_source_url(self):
        row = {
            "chunk_id": 1,
            "document_id": 9,
            "document_title": "Syria Unified Plan 2026",
            "source_url": "https://idrl.ifrc.org/Document/Download/12345",
            "has_local_file": True,
            "content": "Migration programmes.",
            "combined_score": 0.82,
        }
        slim = slim_public_document_chunk(row, max_content_chars=500)
        assert slim["source_url"] == "https://idrl.ifrc.org/Document/Download/12345"
        assert slim["document_url"] == "https://idrl.ifrc.org/Document/Download/12345"

    def test_public_document_link_fields_prefers_local_download_when_no_source(self):
        links = _public_document_link_fields(42, source_url=None, has_local_file=True)
        assert links["source_url"] is None
        assert links["download_url"] is None or links["download_url"].endswith("/public/documents/42/download")
        assert links["document_url"] == links["download_url"]

    def test_query_requests_multi_year_documents(self):
        assert query_requests_multi_year_documents("Syria migration activities over years") is True
        assert query_requests_multi_year_documents("compare Syria 2024 and 2026 plans") is True
        assert query_requests_multi_year_documents("migration in 2026 unified plans") is False

    def test_should_prioritize_latest_for_snapshot_not_multi_year(self):
        assert _should_prioritize_latest_per_country(
            "migration unified plan 2026",
            {"date_range": {"min": "2026-01-01", "max": "2026-12-31"}},
            latest_per_country=None,
        ) is True
        assert not _should_prioritize_latest_per_country(
            "syria migration over years",
            {"country_name": "Syria"},
            latest_per_country=None,
        )
        assert not _should_prioritize_latest_per_country(
            "migration unified plan",
            None,
            latest_per_country=False,
        )

    def test_prioritize_latest_documents_per_country_keeps_newest_plan(self):
        docs = [
            AIDocument(
                id=1,
                title="Syria Unified Plan 2024",
                filename="syria_2024.pdf",
                file_type="pdf",
                country_name="Syria",
                document_date=datetime.date(2024, 1, 1),
            ),
            AIDocument(
                id=2,
                title="Syria Unified Plan 2026",
                filename="syria_2026.pdf",
                file_type="pdf",
                country_name="Syria",
                document_date=datetime.date(2026, 1, 1),
            ),
            AIDocument(
                id=3,
                title="Kenya Unified Plan 2026",
                filename="kenya_2026.pdf",
                file_type="pdf",
                country_name="Kenya",
                document_date=datetime.date(2026, 1, 1),
            ),
        ]
        selected, meta = prioritize_latest_documents_per_country(
            docs,
            "migration unified plan",
            enabled=True,
        )
        assert meta["latest_per_country_applied"] is True
        assert {doc.id for doc in selected} == {2, 3}
        assert len(meta["superseded_documents"]) == 1
        assert meta["superseded_documents"][0]["document_id"] == 1

    def test_prioritize_latest_skipped_for_multi_year_query(self):
        docs = [
            AIDocument(
                id=1,
                title="Syria Unified Plan 2024",
                filename="syria_2024.pdf",
                file_type="pdf",
                country_name="Syria",
                document_date=datetime.date(2024, 1, 1),
            ),
            AIDocument(
                id=2,
                title="Syria Unified Plan 2026",
                filename="syria_2026.pdf",
                file_type="pdf",
                country_name="Syria",
                document_date=datetime.date(2026, 1, 1),
            ),
        ]
        assert not _should_prioritize_latest_per_country(
            "syria migration activities over years",
            {"country_name": "Syria"},
            latest_per_country=None,
        )
        selected, meta = prioritize_latest_documents_per_country(
            docs,
            "syria migration activities over years",
            enabled=False,
        )
        assert meta["latest_per_country_applied"] is False
        assert len(selected) == 2


@pytest.mark.unit
class TestFilterRowsToPublicDocuments:
    def _create_doc(self, db_session, *, is_public: bool):
        doc = AIDocument(
            title="Test doc",
            filename="test.pdf",
            file_type="pdf",
            is_public=is_public,
            searchable=True,
            processing_status=AIDocumentProcessingStatusValue.completed.value,
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)
        return doc

    def test_keeps_only_public_completed_searchable_documents(self, app, db_session):
        public_doc = self._create_doc(db_session, is_public=True)
        private_doc = self._create_doc(db_session, is_public=False)

        rows = [
            {"document_id": public_doc.id, "chunk_id": 1, "content": "public chunk"},
            {"document_id": private_doc.id, "chunk_id": 2, "content": "private chunk"},
        ]

        with app.app_context():
            filtered = filter_rows_to_public_documents(rows)

        assert len(filtered) == 1
        assert filtered[0]["document_id"] == public_doc.id

    def test_excludes_non_searchable_or_pending_documents(self, app, db_session):
        pending = AIDocument(
            title="Pending",
            filename="pending.pdf",
            file_type="pdf",
            is_public=True,
            searchable=True,
            processing_status=AIDocumentProcessingStatusValue.pending.value,
        )
        not_searchable = AIDocument(
            title="Hidden",
            filename="hidden.pdf",
            file_type="pdf",
            is_public=True,
            searchable=False,
            processing_status=AIDocumentProcessingStatusValue.completed.value,
        )
        db_session.add_all([pending, not_searchable])
        db_session.commit()

        rows = [
            {"document_id": pending.id, "chunk_id": 1, "content": "pending"},
            {"document_id": not_searchable.id, "chunk_id": 2, "content": "hidden"},
        ]

        with app.app_context():
            filtered = filter_rows_to_public_documents(rows)

        assert filtered == []


@pytest.mark.unit
class TestGetPublicDocumentChunkContext:
    """
    Regression coverage for outstanding item #2: databank_get_chunk_context — fetch chunks
    immediately before/after a search result by chunk_index, to verify/expand a truncated or
    ambiguous match without re-searching the whole document.
    """

    def _seed_document(self, db_session, *, is_public: bool = True, num_chunks: int = 5):
        from app.models.embeddings import AIDocumentChunk

        doc = AIDocument(
            title="Test doc with chunks",
            filename="test_chunks.pdf",
            file_type="pdf",
            is_public=is_public,
            searchable=True,
            processing_status=AIDocumentProcessingStatusValue.completed.value,
        )
        db_session.add(doc)
        db_session.commit()

        chunks = []
        for idx in range(num_chunks):
            chunk = AIDocumentChunk(
                document_id=doc.id,
                content=f"Chunk {idx} content.",
                content_length=20,
                chunk_index=idx,
                page_number=idx // 2 + 1,
                chunk_type="semantic",
            )
            db_session.add(chunk)
            chunks.append(chunk)
        db_session.commit()
        for chunk in chunks:
            db_session.refresh(chunk)
        return doc, chunks

    def test_returns_requested_chunk_with_neighbors_in_order(self, app, db_session):
        from app.services.public.document_service import get_public_document_chunk_context

        _doc, chunks = self._seed_document(db_session, num_chunks=5)
        middle = chunks[2]

        with app.app_context():
            out = get_public_document_chunk_context(middle.id, before=1, after=1)

        returned_ids = [c["chunk_id"] for c in out["chunks"]]
        assert returned_ids == [chunks[1].id, chunks[2].id, chunks[3].id]
        flags = {c["chunk_id"]: c["is_requested_chunk"] for c in out["chunks"]}
        assert flags[chunks[2].id] is True
        assert flags[chunks[1].id] is False
        assert flags[chunks[3].id] is False
        assert out["requested_chunk_id"] == middle.id

    def test_clamps_to_available_chunks_at_document_start(self, app, db_session):
        from app.services.public.document_service import get_public_document_chunk_context

        _doc, chunks = self._seed_document(db_session, num_chunks=5)
        first = chunks[0]

        with app.app_context():
            out = get_public_document_chunk_context(first.id, before=3, after=1)

        # No chunk_index -3..-1 exists; only 0 and 1 should come back, not an error.
        returned_ids = [c["chunk_id"] for c in out["chunks"]]
        assert returned_ids == [chunks[0].id, chunks[1].id]

    def test_clamps_before_after_to_max(self, app, db_session):
        from app.services.public.document_service import (
            PUBLIC_DOC_CHUNK_CONTEXT_MAX_BEFORE_AFTER,
            get_public_document_chunk_context,
        )

        _doc, chunks = self._seed_document(db_session, num_chunks=5)

        with app.app_context():
            out = get_public_document_chunk_context(chunks[2].id, before=999, after=999)

        assert out["before"] == PUBLIC_DOC_CHUNK_CONTEXT_MAX_BEFORE_AFTER
        assert out["after"] == PUBLIC_DOC_CHUNK_CONTEXT_MAX_BEFORE_AFTER

    def test_raises_for_non_public_document(self, app, db_session):
        from app.services.public.document_service import get_public_document_chunk_context

        _doc, chunks = self._seed_document(db_session, is_public=False, num_chunks=3)

        with app.app_context():
            with pytest.raises(ValueError, match="not public"):
                get_public_document_chunk_context(chunks[0].id)

    def test_raises_for_unknown_chunk_id(self, app, db_session):
        from app.services.public.document_service import get_public_document_chunk_context

        with app.app_context():
            with pytest.raises(ValueError):
                get_public_document_chunk_context(999_999_999)


@pytest.mark.unit
class TestSearchPublicDocuments:
    def test_requires_query(self, app):
        with app.app_context():
            with pytest.raises(ValueError, match="query is required"):
                search_public_documents("")

    def test_returns_slim_chunks(self, app, db_session):
        with app.app_context():
            public_doc = AIDocument(
                title="Syria Unified Plan 2026",
                filename="syria.pdf",
                file_type="pdf",
                is_public=True,
                searchable=True,
                processing_status=AIDocumentProcessingStatusValue.completed.value,
            )
            db_session.add(public_doc)
            db_session.commit()
            db_session.refresh(public_doc)

        sample_rows = [
            {
                "chunk_id": 10,
                "document_id": public_doc.id,
                "document_title": "Syria Unified Plan 2026",
                "document_filename": "syria.pdf",
                "document_country_name": "Syria",
                "document_countries": [],
                "page_number": 2,
                "section_title": "Strategic focus",
                "content": "Health, WASH, and shelter are priority focus areas.",
                "combined_score": 0.91,
            },
            {
                "chunk_id": 11,
                "document_id": public_doc.id,
                "document_title": "Syria Unified Plan 2026",
                "document_filename": "syria.pdf",
                "document_country_name": "Syria",
                "document_countries": [],
                "page_number": 3,
                "section_title": "Operations",
                "content": "Low relevance chunk.",
                "combined_score": 0.1,
            },
        ]

        class FakeStore:
            def hybrid_search(self, **kwargs):
                assert kwargs["user_id"] is None
                assert kwargs["user_role"] == "public"
                return sample_rows

        with app.app_context():
            from app.services.public import document_service as svc

            original = svc.AIVectorStore
            svc.AIVectorStore = FakeStore
            try:
                out = search_public_documents(
                    "summarize focus areas in syria unified plan 2026",
                    top_k=5,
                    min_score=0.25,
                )
            finally:
                svc.AIVectorStore = original

        assert out["count"] == 1
        assert out["visibility"] == "public_only"
        assert out["chunks"][0]["section_title"] == "Strategic focus"
        assert "Unified Plan" in " ".join(out["notes"])

    def test_search_drops_private_document_chunks(self, app, db_session):
        with app.app_context():
            private_doc = AIDocument(
                title="Private Syria Plan",
                filename="private.pdf",
                file_type="pdf",
                is_public=False,
                searchable=True,
                processing_status=AIDocumentProcessingStatusValue.completed.value,
            )
            db_session.add(private_doc)
            db_session.commit()
            db_session.refresh(private_doc)

        leaked_rows = [
            {
                "chunk_id": 99,
                "document_id": private_doc.id,
                "document_title": "Private Syria Plan",
                "content": "Secret focus areas.",
                "combined_score": 0.99,
            }
        ]

        class FakeStore:
            def hybrid_search(self, **kwargs):
                return leaked_rows

        with app.app_context():
            from app.services.public import document_service as svc

            original = svc.AIVectorStore
            svc.AIVectorStore = FakeStore
            try:
                out = search_public_documents("syria unified plan 2026")
            finally:
                svc.AIVectorStore = original

        assert out["count"] == 0
        assert out["chunks"] == []
        assert out["visibility"] == "public_only"

    def test_country_filter_uses_scoped_per_document_search(self, app):
        from unittest.mock import MagicMock, patch

        public_doc = MagicMock()
        public_doc.id = 16701

        sample_rows = [
            {
                "chunk_id": 10,
                "document_id": 16701,
                "document_title": "Syria Unified Plan 2026",
                "content": "Health, WASH, and shelter are priority focus areas.",
                "combined_score": 0.91,
            }
        ]
        calls: dict[str, Any] = {"hybrid_search": 0, "hybrid_search_per_document": 0}

        class FakeStore:
            def hybrid_search(self, **kwargs):
                calls["hybrid_search"] += 1
                return []

            def hybrid_search_per_document(self, query_text, document_ids, **kwargs):
                calls["hybrid_search_per_document"] += 1
                assert document_ids == [16701]
                assert kwargs["user_role"] == "public"
                return sample_rows

        with app.app_context():
            from app.services.public import document_service as svc

            original = svc.AIVectorStore
            svc.AIVectorStore = FakeStore
            try:
                with patch.object(svc, "list_public_documents_in_scope", return_value=[public_doc]):
                    with patch.object(svc, "filter_rows_to_public_documents", side_effect=lambda rows: rows):
                        out = search_public_documents(
                            "Syrian Arab Republic unified plan focus areas",
                            country_id=167,
                            top_k=5,
                            min_score=0.25,
                        )
            finally:
                svc.AIVectorStore = original

        assert calls["hybrid_search"] == 0
        assert calls["hybrid_search_per_document"] == 1
        assert out["count"] == 1
        assert out["chunks"][0]["content"].startswith("Health")

    def test_country_scoped_search_returns_globally_top_scored_chunks(self, app):
        """
        Regression guard: hybrid_search_per_document returns chunks grouped/concatenated
        per document (each group already sorted by score internally), NOT globally sorted
        by score across documents. search_public_documents must re-sort before slicing to
        top_k, otherwise it would silently return low-score chunks from a low-document-id
        doc while dropping a much higher-scoring chunk from another in-scope document.
        """
        from unittest.mock import MagicMock, patch

        doc_low_id = MagicMock()
        doc_low_id.id = 101
        doc_high_id = MagicMock()
        doc_high_id.id = 205

        # Concatenated in document_id order (as hybrid_search_per_document produces),
        # NOT in score order: the best chunk (0.95) is second because doc 205 > doc 101.
        per_document_rows = [
            {
                "chunk_id": 1,
                "document_id": 101,
                "document_title": "Low-relevance doc",
                "content": "Only marginally related content.",
                "combined_score": 0.30,
            },
            {
                "chunk_id": 2,
                "document_id": 205,
                "document_title": "Highly relevant doc",
                "content": "Exact answer to the query.",
                "combined_score": 0.95,
            },
        ]

        class FakeStore:
            def hybrid_search(self, **kwargs):
                return []

            def hybrid_search_per_document(self, query_text, document_ids, **kwargs):
                assert document_ids == [101, 205]
                return per_document_rows

        with app.app_context():
            from app.services.public import document_service as svc

            original = svc.AIVectorStore
            svc.AIVectorStore = FakeStore
            try:
                with patch.object(
                    svc, "list_public_documents_in_scope", return_value=[doc_low_id, doc_high_id]
                ):
                    with patch.object(svc, "filter_rows_to_public_documents", side_effect=lambda rows: rows):
                        out = search_public_documents(
                            "test query",
                            country_id=167,
                            top_k=1,
                            min_score=0.25,
                        )
            finally:
                svc.AIVectorStore = original

        assert out["count"] == 1
        assert out["chunks"][0]["document_id"] == 205
        assert out["chunks"][0]["score"] == 0.95

    def test_min_score_rejects_chunk_relying_only_on_source_boost(self, app):
        """
        A system-uploaded document gets a +0.25 source_boost in combined_score
        (AIVectorStore._combine_search_results), independent of actual text relevance.
        A chunk with ~zero vector/keyword similarity must not pass the public min_score
        filter purely on that boost — otherwise near-irrelevant system-doc chunks leak
        into results whenever min_score is at or below the boost size (the default
        min_score=0.25 equals the boost exactly).
        """
        boost_only_row = {
            "chunk_id": 1,
            "document_id": 501,
            "document_title": "Unrelated system upload",
            "content": "Completely unrelated content that barely matched a stray keyword.",
            "vector_score": 0.0,
            "keyword_score": 0.02,
            "source_boost": 0.25,
            "combined_score": 0.0 * 0.7 + 0.02 * 0.3 + 0.25,  # 0.256 — clears min_score=0.25
        }
        genuine_row = {
            "chunk_id": 2,
            "document_id": 502,
            "document_title": "Genuinely relevant doc",
            "content": "This directly answers the query.",
            "vector_score": 0.6,
            "keyword_score": 0.5,
            "source_boost": 0.0,
            "combined_score": 0.6 * 0.7 + 0.5 * 0.3,  # 0.57
        }

        class FakeStore:
            def hybrid_search(self, **kwargs):
                return [boost_only_row, genuine_row]

        with app.app_context():
            from unittest.mock import patch

            from app.services.public import document_service as svc

            original = svc.AIVectorStore
            svc.AIVectorStore = FakeStore
            try:
                with patch.object(svc, "filter_rows_to_public_documents", side_effect=lambda rows: rows):
                    out = search_public_documents("unrelated query", top_k=5, min_score=0.25)
            finally:
                svc.AIVectorStore = original

        returned_doc_ids = {c["document_id"] for c in out["chunks"]}
        assert 502 in returned_doc_ids
        assert 501 not in returned_doc_ids

    def test_api_route_returns_chunks(self, client, app):
        payload = {
            "query": "summarize focus areas in syria unified plan 2026",
            "search_mode": "hybrid",
            "filters_applied": {"is_api_import": True},
            "min_score": 0.25,
            "count": 1,
            "chunks": [
                {
                    "chunk_id": 10,
                    "document_title": "Syria Unified Plan 2026",
                    "content": "Health and WASH focus areas.",
                    "score": 0.9,
                }
            ],
            "notes": [],
        }

        with app.app_context():
            from unittest.mock import patch

            with patch(
                "app.routes.api.public_integrations.search_public_documents",
                return_value=payload,
            ):
                resp = client.get(
                    "/api/v1/public/documents/search"
                    "?query=summarize+focus+areas+in+syria+unified+plan+2026"
                )

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["count"] == 1
        assert body["chunks"][0]["document_title"] == "Syria Unified Plan 2026"
        assert resp.headers.get("X-Public-Data-Access") == "true"

    def test_api_route_requires_query(self, client):
        resp = client.get("/api/v1/public/documents/search")
        assert resp.status_code == 400

    def test_full_coverage_returns_coverage_block(self, app, db_session):
        with app.app_context():
            doc_a = AIDocument(
                title="Kenya Unified Plan 2026",
                filename="kenya.pdf",
                file_type="pdf",
                is_public=True,
                searchable=True,
                processing_status=AIDocumentProcessingStatusValue.completed.value,
                country_name="Kenya",
                source_url="https://example.org/upl/kenya",
                document_date=datetime.date(2026, 1, 1),
            )
            doc_b = AIDocument(
                title="Nepal Unified Plan 2026",
                filename="nepal.pdf",
                file_type="pdf",
                is_public=True,
                searchable=True,
                processing_status=AIDocumentProcessingStatusValue.completed.value,
                country_name="Nepal",
                source_url="https://example.org/upl/nepal",
                document_date=datetime.date(2026, 1, 1),
            )
            db_session.add_all([doc_a, doc_b])
            db_session.commit()
            db_session.refresh(doc_a)
            db_session.refresh(doc_b)

        per_doc_rows = {
            doc_a.id: {
                "chunk_id": 1,
                "document_id": doc_a.id,
                "document_title": "Kenya Unified Plan 2026",
                "document_country_name": "Kenya",
                "page_number": 2,
                "content": "Migration and displacement programmes.",
                "combined_score": 0.88,
            },
            doc_b.id: {
                "chunk_id": 2,
                "document_id": doc_b.id,
                "document_title": "Nepal Unified Plan 2026",
                "document_country_name": "Nepal",
                "page_number": 1,
                "content": "Health and WASH only.",
                "combined_score": 0.05,
            },
        }

        class FakeStore:
            def hybrid_search_per_document(self, query_text, document_ids, **kwargs):
                return [per_doc_rows[doc_id] for doc_id in document_ids if doc_id in per_doc_rows]

        with app.app_context():
            from app.services.public import document_service as svc

            original = svc.AIVectorStore
            svc.AIVectorStore = FakeStore
            try:
                out = search_public_documents(
                    "migration unified plan 2026",
                    full_coverage=True,
                    min_score=0.25,
                )
            finally:
                svc.AIVectorStore = original

        assert out["coverage_mode"] == "full"
        assert out["coverage"]["documents_in_scope"] == 2
        assert out["coverage"]["documents_with_hits"] == 1
        assert out["coverage"]["documents_without_hits"] == 1
        assert out["coverage"]["total_matching_chunks"] == 1
        assert out["chunks"][0]["document_title"] == "Kenya Unified Plan 2026"
        assert len(out["chunks"][0]["content"]) <= PUBLIC_DOC_FULL_COVERAGE_CONTENT_CHARS + 1
        assert out["coverage"]["without_hits"][0]["document_title"] == "Nepal Unified Plan 2026"

    def test_full_coverage_without_hits_checks_local_file_per_document(self, app, db_session):
        """
        Regression guard: for every in-scope document that has NO matching chunk
        (without_hits), _document_scope_entry() must NOT call
        _ai_document_has_local_file() (a storage existence check — a network round-trip
        on Azure Blob) since that link is never used for uncited documents.
        """
        from unittest.mock import patch

        with app.app_context():
            # Distinct country_name per doc: prioritize_latest_documents_per_country
            # groups by (country, document_type) and would otherwise collapse same-country
            # docs down to the newest one, undercounting without_hits for this repro.
            countries = ["Kenya", "Nepal", "Peru"]
            docs = [
                AIDocument(
                    title=f"No-hit doc {i}",
                    filename=f"nohit_{i}.pdf",
                    file_type="pdf",
                    is_public=True,
                    searchable=True,
                    processing_status=AIDocumentProcessingStatusValue.completed.value,
                    country_name=countries[i],
                    document_date=datetime.date(2026, 1, 1),
                    storage_path=f"nohit_{i}.pdf",
                )
                for i in range(3)
            ]
            db_session.add_all(docs)
            db_session.commit()
            for d in docs:
                db_session.refresh(d)

        class FakeStore:
            def hybrid_search_per_document(self, query_text, document_ids, **kwargs):
                return []  # no hits for any in-scope document

        with app.app_context():
            from app.services.public import document_service as svc

            original = svc.AIVectorStore
            svc.AIVectorStore = FakeStore
            try:
                with patch.object(
                    svc, "_ai_document_has_local_file", return_value=True
                ) as mock_has_local:
                    out = svc.search_public_documents(
                        "migration",
                        full_coverage=True,
                        min_score=0.25,
                    )
            finally:
                svc.AIVectorStore = original

        assert out["coverage"]["documents_without_hits"] == 3
        # without_hits documents are never cited, so resolving a download link for them
        # (a storage/blob existence check — a network round-trip on Azure Blob) is wasted
        # work. Must not be called at all for these entries.
        mock_has_local.assert_not_called()

    def test_full_coverage_returns_all_relevant_chunks_per_document(self, app, db_session):
        with app.app_context():
            doc = AIDocument(
                title="Kenya Unified Plan 2026",
                filename="kenya.pdf",
                file_type="pdf",
                is_public=True,
                searchable=True,
                processing_status=AIDocumentProcessingStatusValue.completed.value,
                country_name="Kenya",
                source_url="https://example.org/upl/kenya",
                document_date=datetime.date(2026, 1, 1),
            )
            db_session.add(doc)
            db_session.commit()
            db_session.refresh(doc)

        class FakeStore:
            def hybrid_search_per_document(self, query_text, document_ids, **kwargs):
                assert document_ids == [doc.id]
                return [
                    {
                        "chunk_id": 1,
                        "document_id": doc.id,
                        "document_title": "Kenya Unified Plan 2026",
                        "page_number": 2,
                        "content": "Migration programmes in border areas.",
                        "combined_score": 0.9,
                    },
                    {
                        "chunk_id": 2,
                        "document_id": doc.id,
                        "document_title": "Kenya Unified Plan 2026",
                        "page_number": 8,
                        "content": "Return and reintegration for migrants.",
                        "combined_score": 0.7,
                    },
                    {
                        "chunk_id": 3,
                        "document_id": doc.id,
                        "document_title": "Kenya Unified Plan 2026",
                        "page_number": 12,
                        "content": "Unrelated health section.",
                        "combined_score": 0.1,
                    },
                ]

        with app.app_context():
            from app.services.public import document_service as svc

            original = svc.AIVectorStore
            svc.AIVectorStore = FakeStore
            try:
                out = search_public_documents(
                    "migration unified plan 2026",
                    full_coverage=True,
                    min_score=0.25,
                )
            finally:
                svc.AIVectorStore = original

        assert out["coverage"]["documents_with_hits"] == 1
        assert out["coverage"]["total_matching_chunks"] == 2
        assert len(out["chunks"]) == 2
        pages = sorted(chunk["page_number"] for chunk in out["chunks"])
        assert pages == [2, 8]

    def test_list_public_documents_in_scope_respects_upr_filters(self, app, db_session):
        with app.app_context():
            in_scope = AIDocument(
                title="Syria Unified Plan 2026",
                filename="syria.pdf",
                file_type="pdf",
                is_public=True,
                searchable=True,
                processing_status=AIDocumentProcessingStatusValue.completed.value,
                source_url="https://example.org/upl/syria",
                document_date=datetime.date(2026, 3, 1),
            )
            private = AIDocument(
                title="Hidden Plan 2026",
                filename="hidden.pdf",
                file_type="pdf",
                is_public=False,
                searchable=True,
                processing_status=AIDocumentProcessingStatusValue.completed.value,
                source_url="https://example.org/upl/hidden",
                document_date=datetime.date(2026, 3, 1),
            )
            db_session.add_all([in_scope, private])
            db_session.commit()

            filters = _build_search_filters("syria unified plan 2026", year=2026)
            docs = list_public_documents_in_scope(filters)

        assert len(docs) == 1
        assert docs[0].title == "Syria Unified Plan 2026"

    def test_api_route_accepts_full_coverage(self, client, app):
        payload = {
            "query": "migration unified plan 2026",
            "coverage_mode": "full",
            "coverage": {"documents_in_scope": 2, "documents_with_hits": 1, "documents_without_hits": 1},
            "count": 1,
            "chunks": [{"document_title": "Kenya Unified Plan 2026", "content": "Migration.", "score": 0.9}],
            "notes": [],
        }

        with app.app_context():
            from unittest.mock import patch

            with patch(
                "app.routes.api.public_integrations.search_public_documents",
                return_value=payload,
            ) as mocked:
                resp = client.get(
                    "/api/v1/public/documents/search"
                    "?query=migration+unified+plan+2026&full_coverage=true"
                )
                assert mocked.call_args.kwargs["full_coverage"] is True

        assert resp.status_code == 200
        assert resp.get_json()["coverage_mode"] == "full"


@pytest.mark.unit
class TestCatalogPublicDocuments:
    def _doc(
        self,
        db_session,
        *,
        title,
        filename,
        is_public=True,
        searchable=True,
        status=None,
        country_name=None,
        document_date=None,
        storage_path=None,
        source_url=None,
    ):
        doc = AIDocument(
            title=title,
            filename=filename,
            file_type="pdf",
            is_public=is_public,
            searchable=searchable,
            processing_status=status or AIDocumentProcessingStatusValue.completed.value,
            country_name=country_name,
            document_date=document_date,
            storage_path=storage_path,
            source_url=source_url,
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)
        return doc

    def test_rejects_unknown_document_type(self, app):
        with app.app_context():
            with pytest.raises(ValueError, match="Unknown document_type"):
                catalog_public_documents(document_type="not_a_real_type")

    def test_excludes_private_non_searchable_and_pending_documents(self, app, db_session):
        """Security: only is_public + searchable + completed documents may be counted —
        same visibility scope as search_public_documents, verified independently here."""
        with app.app_context():
            self._doc(
                db_session,
                title="Kenya Annual Report 2024",
                filename="kenya_ar_2024.pdf",
                country_name="Kenya",
                document_date=datetime.date(2024, 3, 1),
            )
            self._doc(
                db_session,
                title="Nepal Annual Report 2024",
                filename="nepal_ar_2024.pdf",
                is_public=False,
                country_name="Nepal",
                document_date=datetime.date(2024, 3, 1),
            )
            self._doc(
                db_session,
                title="Chad Annual Report 2024",
                filename="chad_ar_2024.pdf",
                searchable=False,
                country_name="Chad",
                document_date=datetime.date(2024, 3, 1),
            )
            self._doc(
                db_session,
                title="Peru Annual Report 2024",
                filename="peru_ar_2024.pdf",
                status=AIDocumentProcessingStatusValue.pending.value,
                country_name="Peru",
                document_date=datetime.date(2024, 3, 1),
            )

            out = catalog_public_documents(document_type="annual_report")

        assert out["total_documents"] == 1
        assert out["countries_count"] == 1
        assert out["visibility"] == "public_only"
        assert [c["country"] for c in out["by_country"]] == ["Kenya"]

    def test_filters_by_year_and_omitting_year_gives_breakdown(self, app, db_session):
        with app.app_context():
            self._doc(
                db_session,
                title="Kenya Annual Report 2023",
                filename="kenya_ar_2023.pdf",
                country_name="Kenya",
                document_date=datetime.date(2023, 3, 1),
            )
            self._doc(
                db_session,
                title="Kenya Annual Report 2024",
                filename="kenya_ar_2024.pdf",
                country_name="Kenya",
                document_date=datetime.date(2024, 3, 1),
            )

            scoped = catalog_public_documents(document_type="annual_report", year=2024)
            all_years = catalog_public_documents(document_type="annual_report")

        assert scoped["total_documents"] == 1
        assert scoped["by_year"] == [{"year": 2024, "document_count": 1, "countries_count": 1}]

        assert all_years["total_documents"] == 2
        # Newest year first.
        assert [b["year"] for b in all_years["by_year"]] == [2024, 2023]

    def test_all_types_when_document_type_omitted(self, app, db_session):
        with app.app_context():
            self._doc(
                db_session,
                title="Kenya Annual Report 2024",
                filename="kenya_ar_2024.pdf",
                country_name="Kenya",
                document_date=datetime.date(2024, 1, 1),
            )
            self._doc(
                db_session,
                title="Nepal Unified Plan 2026",
                filename="nepal_upl_2026.pdf",
                country_name="Nepal",
                document_date=datetime.date(2026, 1, 1),
            )

            out = catalog_public_documents()

        assert out["total_documents"] == 2
        assert out["by_type"] == {"annual_report": 1, "unified_plan": 1}

    def test_country_name_filter_scopes_results(self, app, db_session):
        with app.app_context():
            self._doc(
                db_session,
                title="Kenya Annual Report 2024",
                filename="kenya_ar_2024.pdf",
                country_name="Kenya",
                document_date=datetime.date(2024, 1, 1),
            )
            self._doc(
                db_session,
                title="Nepal Annual Report 2024",
                filename="nepal_ar_2024.pdf",
                country_name="Nepal",
                document_date=datetime.date(2024, 1, 1),
            )

            out = catalog_public_documents(document_type="annual_report", country_name="Kenya")

        assert out["total_documents"] == 1
        assert out["by_country"][0]["country"] == "Kenya"

    def test_include_documents_false_keeps_counts_but_drops_listing(self, app, db_session):
        with app.app_context():
            self._doc(
                db_session,
                title="Kenya Annual Report 2024",
                filename="kenya_ar_2024.pdf",
                country_name="Kenya",
                document_date=datetime.date(2024, 1, 1),
            )

            out = catalog_public_documents(document_type="annual_report", include_documents=False)

        assert out["total_documents"] == 1
        assert out["by_country"][0]["documents"] == []
        assert any("include_documents=false" in note for note in out["notes"])

    def test_include_documents_false_skips_blob_existence_checks(self, app, db_session):
        """Counts-only catalog must not HEAD-check Azure/local storage per document."""
        from unittest.mock import patch

        with app.app_context():
            self._doc(
                db_session,
                title="Kenya Annual Report 2024",
                filename="kenya_ar_2024.pdf",
                country_name="Kenya",
                document_date=datetime.date(2024, 1, 1),
                storage_path="kenya_ar_2024.pdf",
            )

            with patch(
                "app.services.public.document_service._ai_document_has_local_file",
                side_effect=AssertionError("blob check should not run when include_documents=false"),
            ) as mock_has_local:
                out = catalog_public_documents(document_type="annual_report", include_documents=False)

        mock_has_local.assert_not_called()
        assert out["total_documents"] == 1

    def test_include_documents_true_skips_blob_check_when_source_url_present(self, app, db_session):
        from unittest.mock import patch

        with app.app_context():
            self._doc(
                db_session,
                title="Kenya Annual Report 2024",
                filename="kenya_ar_2024.pdf",
                country_name="Kenya",
                document_date=datetime.date(2024, 1, 1),
                storage_path="kenya_ar_2024.pdf",
                source_url="https://example.org/kenya-ar-2024.pdf",
            )

            with patch(
                "app.services.public.document_service._ai_document_has_local_file",
                side_effect=AssertionError("blob check not needed when source_url is set"),
            ) as mock_has_local:
                out = catalog_public_documents(document_type="annual_report", include_documents=True)

        mock_has_local.assert_not_called()
        assert out["by_country"][0]["documents"][0]["document_url"] == "https://example.org/kenya-ar-2024.pdf"

    def test_document_type_key_detects_annual_report_and_unified_plan(self, app, db_session):
        with app.app_context():
            ar = self._doc(db_session, title="Kenya Annual Report 2024", filename="kenya_ar.pdf")
            upl = self._doc(db_session, title="Syria Unified Plan 2026", filename="syria_upl.pdf")
            other = self._doc(db_session, title="Random Briefing Note", filename="brief.pdf")

        assert _document_type_key(ar, "") == "annual_report"
        assert _document_type_key(upl, "") == "unified_plan"
        assert _document_type_key(other, "") == "other"


class TestPublicDocumentSearchFixes:
    def test_dedupe_rows_by_chunk_id_keeps_highest_score(self):
        from app.services.public.document_service import _dedupe_rows_by_chunk_id

        rows = [
            {"chunk_id": 1, "combined_score": 0.4, "content": "a"},
            {"chunk_id": 1, "combined_score": 0.9, "content": "b"},
            {"chunk_id": 2, "combined_score": 0.5, "content": "c"},
        ]
        out = _dedupe_rows_by_chunk_id(rows)
        assert len(out) == 2
        assert out[0]["combined_score"] == 0.9
        assert out[1]["chunk_id"] == 2

    def test_build_search_filters_require_phrase(self):
        filters = _build_search_filters("postal partnerships", require_phrase="post office")
        assert filters is not None
        assert filters["require_phrase"] == "post office"

    def test_parse_country_ids_all_and_list(self):
        from app.services.public.document_service import _parse_country_ids_param

        assert _parse_country_ids_param("all") == (None, True)
        assert _parse_country_ids_param("153,167,153") == ([153, 167], False)

    def test_api_route_service_unavailable_returns_503(self, client, app):
        from unittest.mock import patch

        from app.services.public.document_service import PublicDocumentSearchUnavailable

        with app.app_context():
            with patch(
                "app.routes.api.public_integrations.search_public_documents",
                side_effect=PublicDocumentSearchUnavailable("Document search is temporarily unavailable"),
            ):
                resp = client.get("/api/v1/public/documents/search?query=postal")

        assert resp.status_code == 503
        body = resp.get_json()
        assert body["error_type"] == "service_unavailable"

    def test_api_route_scope_too_large_returns_400_with_error_type(self, client, app):
        from unittest.mock import patch

        from app.services.public.document_service import PublicDocumentScopeTooLarge

        with app.app_context():
            with patch(
                "app.routes.api.public_integrations.search_public_documents",
                side_effect=PublicDocumentScopeTooLarge("Too many documents in scope (448)."),
            ):
                resp = client.get("/api/v1/public/documents/search?query=postal&full_coverage=true")

        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error_type"] == "scope_too_large"

    def test_api_route_chunk_context_returns_payload(self, client, app):
        from unittest.mock import patch

        payload = {
            "document_id": 244,
            "document_title": "Lithuania Annual Report 2025",
            "requested_chunk_id": 17842,
            "requested_chunk_index": 40,
            "before": 1,
            "after": 1,
            "count": 2,
            "chunks": [
                {"chunk_id": 17841, "chunk_index": 39, "is_requested_chunk": False},
                {"chunk_id": 17842, "chunk_index": 40, "is_requested_chunk": True},
            ],
            "notes": [],
        }
        with app.app_context():
            with patch(
                "app.routes.api.public_integrations.get_public_document_chunk_context",
                return_value=payload,
            ) as mock_context:
                resp = client.get(
                    "/api/v1/public/documents/chunks/17842/context?before=1&after=1"
                )

        assert resp.status_code == 200
        assert resp.get_json()["requested_chunk_id"] == 17842
        mock_context.assert_called_once_with(17842, before=1, after=1)

    def test_api_route_chunk_context_returns_404_for_unknown_chunk(self, client, app):
        from unittest.mock import patch

        with app.app_context():
            with patch(
                "app.routes.api.public_integrations.get_public_document_chunk_context",
                side_effect=ValueError("Chunk not found, or its document is not public"),
            ):
                resp = client.get("/api/v1/public/documents/chunks/999999999/context")

        assert resp.status_code == 404

    def test_multi_country_search_adds_by_country(self, app):
        from unittest.mock import patch

        from app.services.public import document_service as svc

        rows = [
            {
                "chunk_id": 1,
                "document_id": 10,
                "document_title": "Doc A",
                "document_country_name": "Kenya",
                "document_countries": [{"name": "Kenya"}],
                "content": "Kenya postal content with enough relevance here.",
                "combined_score": 0.8,
            },
            {
                "chunk_id": 2,
                "document_id": 11,
                "document_title": "Doc B",
                "document_country_name": "Syria",
                "document_countries": [{"name": "Syria"}],
                "content": "Syria postal content with enough relevance here.",
                "combined_score": 0.7,
            },
        ]

        class FakeStore:
            def hybrid_search_per_document(self, *args, **kwargs):
                return rows

        class FakeDoc:
            def __init__(self, doc_id: int):
                self.id = doc_id

        original = svc.AIVectorStore
        svc.AIVectorStore = FakeStore
        try:
            with app.app_context():
                with patch.object(
                    svc,
                    "list_public_documents_in_scope",
                    return_value=[FakeDoc(10), FakeDoc(11)],
                ):
                    with patch.object(svc, "filter_rows_to_public_documents", side_effect=lambda r: r):
                        out = search_public_documents(
                            "postal partnerships",
                            country_ids="1,2",
                            top_k=8,
                            min_score=0.25,
                        )
        finally:
            svc.AIVectorStore = original

        assert "by_country" in out
        assert len(out["by_country"]) == 2
        country_names = {entry["country"] for entry in out["by_country"]}
        assert country_names == {"Kenya", "Syria"}


class TestAutoBatchingForLargeScope:
    """
    Regression coverage for outstanding item #1: country_ids="all" (or any scope larger
    than one batch) must auto-batch server-side instead of raising
    PublicDocumentScopeTooLarge("Too many documents in scope (865)") and pushing the
    batching logic (guessing sequential numeric id ranges) onto the caller.
    """

    def test_batched_per_document_search_rows_splits_into_groups(self):
        from app.services.public.document_service import _batched_per_document_search_rows

        calls = []

        class FakeStore:
            def hybrid_search_per_document(self, raw_query, doc_ids, **kwargs):
                calls.append(list(doc_ids))
                return [{"chunk_id": doc_id, "document_id": doc_id} for doc_id in doc_ids]

        rows, batch_count = _batched_per_document_search_rows(
            FakeStore(),
            "query",
            [1, 2, 3, 4, 5],
            filters=None,
            chunks_per_doc=8,
            mode="hybrid",
            batch_size=2,
        )

        assert batch_count == 3
        assert calls == [[1, 2], [3, 4], [5]]
        assert {row["chunk_id"] for row in rows} == {1, 2, 3, 4, 5}

    def test_batched_per_document_search_rows_uses_vector_only_in_vector_mode(self):
        from app.services.public.document_service import _batched_per_document_search_rows

        vector_calls = []
        hybrid_calls = []

        class FakeStore:
            def search_similar_per_document(self, raw_query, doc_ids, **kwargs):
                vector_calls.append(list(doc_ids))
                return []

            def hybrid_search_per_document(self, raw_query, doc_ids, **kwargs):
                hybrid_calls.append(list(doc_ids))
                return []

        _batched_per_document_search_rows(
            FakeStore(), "query", [1, 2, 3], filters=None, chunks_per_doc=8, mode="vector", batch_size=2
        )

        assert vector_calls == [[1, 2], [3]]
        assert hybrid_calls == []

    def test_try_multi_country_scoped_search_rows_batches_instead_of_raising(self, app):
        from unittest.mock import patch

        from app.services.public import document_service as svc

        class FakeDoc:
            def __init__(self, doc_id):
                self.id = doc_id

        # 5 fake documents, batch size patched to 2 => 3 batches instead of one big query.
        docs = [FakeDoc(i) for i in range(1, 6)]
        calls = []

        class FakeStore:
            def hybrid_search_per_document(self, raw_query, doc_ids, **kwargs):
                calls.append(list(doc_ids))
                return [
                    {"chunk_id": doc_id, "document_id": doc_id, "content": "x"}
                    for doc_id in doc_ids
                ]

        with app.app_context():
            with patch.object(svc, "PUBLIC_DOC_MULTI_COUNTRY_BATCH_SIZE", 2):
                with patch.object(svc, "list_public_documents_in_scope", return_value=docs):
                    rows, batch_count = svc._try_multi_country_scoped_search_rows(
                        FakeStore(),
                        "query",
                        filters=None,
                        top_k=8,
                        mode="hybrid",
                        country_ids_all=True,
                    )

        assert batch_count == 3
        assert len(calls) == 3
        assert len(rows) == 5

    def test_try_multi_country_scoped_search_rows_still_errors_past_absolute_ceiling(self, app):
        from unittest.mock import patch

        from app.services.public.document_service import PublicDocumentScopeTooLarge
        from app.services.public import document_service as svc

        class FakeDoc:
            def __init__(self, doc_id):
                self.id = doc_id

        class FakeStore:
            def hybrid_search_per_document(self, *args, **kwargs):
                raise AssertionError("should not reach the DB query past the scope ceiling")

        # 7 fake documents but batch_size=2 and max_batches=2 => absolute ceiling is 4 docs.
        docs = [FakeDoc(i) for i in range(1, 8)]

        with app.app_context():
            with patch.object(svc, "PUBLIC_DOC_MULTI_COUNTRY_BATCH_SIZE", 2):
                with patch.object(svc, "PUBLIC_DOC_MULTI_COUNTRY_MAX_BATCHES", 2):
                    with patch.object(svc, "list_public_documents_in_scope", return_value=docs):
                        with pytest.raises(PublicDocumentScopeTooLarge):
                            svc._try_multi_country_scoped_search_rows(
                                FakeStore(),
                                "query",
                                filters=None,
                                top_k=8,
                                mode="hybrid",
                                country_ids_all=True,
                            )

    def test_search_public_documents_country_ids_all_auto_batches_end_to_end(self, app):
        from unittest.mock import patch

        from app.services.public import document_service as svc

        class FakeDoc:
            def __init__(self, doc_id):
                self.id = doc_id

        docs = [FakeDoc(i) for i in range(1, 6)]  # 5 docs, batch size patched to 2 => 3 batches

        class FakeStore:
            def hybrid_search_per_document(self, raw_query, doc_ids, **kwargs):
                return [
                    {
                        "chunk_id": doc_id,
                        "document_id": doc_id,
                        "document_title": f"Doc {doc_id}",
                        "document_country_name": f"Country {doc_id}",
                        "document_countries": [{"name": f"Country {doc_id}"}],
                        "content": "Post Office partnership content with enough relevance.",
                        "combined_score": 0.5,
                    }
                    for doc_id in doc_ids
                ]

        original = svc.AIVectorStore
        svc.AIVectorStore = FakeStore
        try:
            with app.app_context():
                with patch.object(svc, "PUBLIC_DOC_MULTI_COUNTRY_BATCH_SIZE", 2):
                    with patch.object(svc, "list_public_documents_in_scope", return_value=docs):
                        with patch.object(svc, "filter_rows_to_public_documents", side_effect=lambda r: r):
                            out = svc.search_public_documents(
                                "Post Office partnership",
                                country_ids="all",
                                top_k=8,
                                min_score=0.05,
                            )
        finally:
            svc.AIVectorStore = original

        assert out["count"] == 5
        assert any("auto-batched into 3" in note for note in out["notes"])
        assert "by_country" in out

    def test_duplicate_chunk_id_across_batches_still_deduped(self, app):
        """
        Regression coverage for the Round 1 "duplicate chunk_id within a single response"
        bug, specifically in combination with auto-batching: if the same chunk_id were ever
        returned by more than one batch (e.g. a future bug in how documents are partitioned),
        the final dedupe pass must still collapse it to one row, keeping the highest score.
        """
        from unittest.mock import patch

        from app.services.public import document_service as svc

        class FakeDoc:
            def __init__(self, doc_id):
                self.id = doc_id

        docs = [FakeDoc(i) for i in range(1, 5)]  # 4 docs, batch size patched to 2 => 2 batches

        class FakeStore:
            def hybrid_search_per_document(self, raw_query, doc_ids, **kwargs):
                # Simulate chunk_id=999 leaking into both batches with different scores.
                return [
                    {
                        "chunk_id": 999,
                        "document_id": doc_ids[0],
                        "document_title": "Duplicate-prone doc",
                        "content": "Post Office partnership content with enough relevance.",
                        "combined_score": 0.3 + 0.1 * doc_ids[0],
                    }
                ]

        original = svc.AIVectorStore
        svc.AIVectorStore = FakeStore
        try:
            with app.app_context():
                with patch.object(svc, "PUBLIC_DOC_MULTI_COUNTRY_BATCH_SIZE", 2):
                    with patch.object(svc, "list_public_documents_in_scope", return_value=docs):
                        with patch.object(svc, "filter_rows_to_public_documents", side_effect=lambda r: r):
                            out = svc.search_public_documents(
                                "Post Office partnership",
                                country_ids="all",
                                top_k=8,
                                min_score=0.05,
                            )
        finally:
            svc.AIVectorStore = original

        chunk_ids = [c["chunk_id"] for c in out["chunks"]]
        assert chunk_ids.count(999) == 1
        assert out["count"] == 1


class TestRequirePhraseLiteralSafetyNet:
    """
    Regression coverage for the Round-2 bug report: require_phrase="Post Office" false-matched
    a Lithuania annual report chunk (document_id=244, chunk_id=17842) whose text never contains
    the literal phrase — the closest text nearby was an unrelated "Post-employment benefits"
    line. These tests use a synthetic chunk built from that same shape (a hyphenated compound
    word near, but not forming, the required phrase) to prove it can never leak through
    require_phrase again, regardless of how the DB-side FTS pre-filter behaves.
    """

    LITHUANIA_LIKE_CONTENT = (
        "Note 24. Employee benefits. Post-employment benefit obligations are measured "
        "using the projected unit credit method. The office of financial reporting "
        "reviewed the discount rate assumptions used for post-employment benefits "
        "during the reporting period covering the annual report."
    )

    def test_content_contains_literal_phrase_rejects_hyphenated_compound(self):
        from app.services.public.document_service import _content_contains_literal_phrase

        assert not _content_contains_literal_phrase(self.LITHUANIA_LIKE_CONTENT, "Post Office")

    def test_content_contains_literal_phrase_accepts_genuine_match(self):
        from app.services.public.document_service import _content_contains_literal_phrase

        genuine = "The Red Cross ran blood drives with the Seychelles Post Office in 2025."
        assert _content_contains_literal_phrase(genuine, "Post Office")

    def test_content_contains_literal_phrase_is_whitespace_tolerant(self):
        from app.services.public.document_service import _content_contains_literal_phrase

        assert _content_contains_literal_phrase("...the Post   Office box...", "Post Office")
        assert _content_contains_literal_phrase("...the Post\nOffice box...", "Post Office")

    def test_filter_rows_by_literal_phrase_drops_false_positive_and_counts_it(self):
        from app.services.public.document_service import _filter_rows_by_literal_phrase

        false_positive_row = {
            "chunk_id": 17842,
            "document_id": 244,
            "content": self.LITHUANIA_LIKE_CONTENT,
        }
        genuine_row = {
            "chunk_id": 999,
            "document_id": 501,
            "content": "Blood drives with the Seychelles Post Office partnership continued.",
        }

        kept, dropped = _filter_rows_by_literal_phrase(
            [false_positive_row, genuine_row], "Post Office"
        )

        kept_ids = {row["chunk_id"] for row in kept}
        assert kept_ids == {999}
        assert dropped == 1

    def test_search_public_documents_never_returns_hyphenated_false_positive(self, app):
        """End-to-end: even if the fake vector store returns the false-positive row (simulating
        any DB-layer FTS edge case), search_public_documents must not surface it when
        require_phrase is set."""
        from unittest.mock import patch

        from app.services.public import document_service as svc

        false_positive_row = {
            "chunk_id": 17842,
            "document_id": 244,
            "document_title": "Lithuania Annual Report 2025",
            "content": self.LITHUANIA_LIKE_CONTENT,
            "combined_score": 0.3857,
        }
        genuine_row = {
            "chunk_id": 555,
            "document_id": 153,
            "document_title": "Seychelles Annual Report 2025",
            "content": (
                "The Red Cross Society of Seychelles ran blood drives in partnership with the "
                "Seychelles Post Office, collecting donations at branch locations nationwide."
            ),
            "combined_score": 0.92,
        }

        class FakeStore:
            def hybrid_search_per_document(self, *args, **kwargs):
                return [false_positive_row, genuine_row]

            def hybrid_search(self, **kwargs):
                return [false_positive_row, genuine_row]

        original = svc.AIVectorStore
        svc.AIVectorStore = FakeStore
        try:
            with app.app_context():
                with patch.object(svc, "list_public_documents_in_scope", return_value=[]):
                    with patch.object(svc, "filter_rows_to_public_documents", side_effect=lambda r: r):
                        out = svc.search_public_documents(
                            "Post Office partnership",
                            require_phrase="Post Office",
                            top_k=8,
                            min_score=0.05,
                        )
        finally:
            svc.AIVectorStore = original

        returned_chunk_ids = {c["chunk_id"] for c in out["chunks"]}
        assert 17842 not in returned_chunk_ids
        assert 555 in returned_chunk_ids
        assert any("Dropped 1 chunk" in note for note in out["notes"])

    def test_snippet_around_phrase_centers_on_match_instead_of_head(self):
        from app.services.public.document_service import _snippet_around_phrase

        long_prefix = "Background paragraph text. " * 20
        content = f"{long_prefix}The Seychelles Post Office partnership began in 2025. " + (
            "Trailing filler text. " * 20
        )
        snippet = _snippet_around_phrase(content, "Post Office", max_chars=80)

        assert "Post Office" in snippet
        assert len(snippet) <= 82  # small allowance for ellipsis chars

    def test_slim_public_document_chunk_uses_phrase_centered_snippet(self):
        long_prefix = "Background paragraph text. " * 20
        content = f"{long_prefix}The Seychelles Post Office partnership began in 2025."
        row = {
            "chunk_id": 1,
            "document_id": 153,
            "content": content,
            "combined_score": 0.9,
        }

        slim = slim_public_document_chunk(row, max_content_chars=60, require_phrase="Post Office")
        assert "Post Office" in slim["content"]

