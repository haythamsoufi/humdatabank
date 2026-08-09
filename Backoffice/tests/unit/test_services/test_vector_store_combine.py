"""Unit tests for AIVectorStore._combine_search_results scoring."""

from __future__ import annotations

from unittest.mock import patch

import pytest


class TestCombineSearchResultsKeywordBoost:
    def test_short_chunk_with_high_keyword_score_does_not_get_boost(self, app):
        from app.services.ai.documents.vector_store import AIVectorStore

        short_header = {
            "chunk_id": "a",
            "similarity_score": 0.0,
            "keyword_score": 1.0,
            "token_count": 3,
            "content": "PARTNERSHIPS",
            "is_system_document": False,
        }
        substantive = {
            "chunk_id": "b",
            "similarity_score": 0.55,
            "keyword_score": 0.6,
            "token_count": 120,
            "content": "The national society operates postal service partnerships with ...",
            "is_system_document": False,
        }

        with app.app_context():
            with patch.dict(app.config, {"AI_MIN_TOKENS_FOR_KEYWORD_BOOST": 22}):
                store = AIVectorStore()
                combined = store._combine_search_results(
                    vector_results=[short_header, substantive],
                    keyword_results=[short_header, substantive],
                    vector_weight=0.7,
                    keyword_weight=0.3,
                )

        by_id = {row["chunk_id"]: row for row in combined}
        assert by_id["a"]["combined_score"] == pytest.approx(0.3)
        assert by_id["b"]["combined_score"] == pytest.approx(0.55 * 0.7 + 0.6 * 0.3)

    def test_substantive_high_keyword_match_gets_boost(self, app):
        from app.services.ai.documents.vector_store import AIVectorStore

        exact_match = {
            "chunk_id": "c",
            "similarity_score": 0.4,
            "keyword_score": 0.95,
            "token_count": 80,
            "content": "Countries reporting more than 10,000 volunteers in 2024 include ...",
            "is_system_document": False,
        }

        with app.app_context():
            with patch.dict(app.config, {"AI_MIN_TOKENS_FOR_KEYWORD_BOOST": 22}):
                store = AIVectorStore()
                combined = store._combine_search_results(
                    vector_results=[exact_match],
                    keyword_results=[exact_match],
                    vector_weight=0.7,
                    keyword_weight=0.3,
                )

        assert combined[0]["combined_score"] == pytest.approx(0.4 * 0.7 + 0.95 * 0.3 + 0.2)

    def test_tiny_system_document_does_not_get_source_boost(self, app):
        from app.services.ai.documents.vector_store import AIVectorStore

        tiny_system = {
            "chunk_id": "d",
            "similarity_score": 0.1,
            "keyword_score": 0.1,
            "token_count": 5,
            "content": "Contact postal address",
            "is_system_document": True,
        }

        with app.app_context():
            with patch.dict(app.config, {"AI_MIN_TOKENS_FOR_KEYWORD_BOOST": 22}):
                store = AIVectorStore()
                combined = store._combine_search_results(
                    vector_results=[tiny_system],
                    keyword_results=[tiny_system],
                    vector_weight=0.7,
                    keyword_weight=0.3,
                    system_document_boost=0.25,
                )

        assert combined[0]["source_boost"] == 0.0
        assert combined[0]["combined_score"] == pytest.approx(0.1 * 0.7 + 0.1 * 0.3)
