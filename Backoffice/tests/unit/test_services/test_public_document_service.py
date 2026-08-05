import datetime

import pytest

from app.models import AIDocument
from app.models.enums import AIDocumentProcessingStatusValue
from app.services.public_document_service import (
    PUBLIC_DOC_FULL_COVERAGE_CONTENT_CHARS,
    PUBLIC_DOC_MAX_CONTENT_CHARS,
    _build_search_filters,
    _extract_year,
    _should_prioritize_latest_per_country,
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
            "content": "Migration programmes.",
            "combined_score": 0.82,
        }
        slim = slim_public_document_chunk(row, max_content_chars=500)
        assert slim["source_url"] == "https://idrl.ifrc.org/Document/Download/12345"
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
            from app.services import public_document_service as svc

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
            from app.services import public_document_service as svc

            original = svc.AIVectorStore
            svc.AIVectorStore = FakeStore
            try:
                out = search_public_documents("syria unified plan 2026")
            finally:
                svc.AIVectorStore = original

        assert out["count"] == 0
        assert out["chunks"] == []
        assert out["visibility"] == "public_only"

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
            from app.services import public_document_service as svc

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
            from app.services import public_document_service as svc

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
