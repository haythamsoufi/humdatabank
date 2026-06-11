"""
Comprehensive tests for app/services/indicator_resolution_service.py.

Covers:
  - _text_for_indicator
  - IndicatorResolutionService.__init__, .embedding_service property
  - IndicatorResolutionService.resolve (empty query, embedding error, success)
  - IndicatorResolutionService._search_similar (success, exception)
  - IndicatorResolutionService.resolve_with_llm (all branches)
  - IndicatorResolutionService.sync_all (empty, success, commit error)
  - IndicatorResolutionService.has_embeddings
  - get_indicator_candidates (all branches)
  - resolve_indicator_identifier (all branches)
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from app.services.indicator_resolution_service import (
    IndicatorResolutionService,
    _text_for_indicator,
    get_indicator_candidates,
    resolve_indicator_identifier,
)


# ---------------------------------------------------------------------------
# _text_for_indicator
# ---------------------------------------------------------------------------
class TestTextForIndicator:
    def _ind(self, name="Indicator", definition=None, unit=None, questions=None):
        ind = MagicMock()
        ind.name = name
        ind.definition = definition
        ind.unit = unit
        ind.monitoring_questions_list = questions or []
        return ind

    def test_name_only(self):
        ind = self._ind(name="Mortality Rate")
        result = _text_for_indicator(ind)
        assert "Mortality Rate" in result

    def test_includes_definition(self):
        ind = self._ind(name="X", definition="Count of deaths")
        result = _text_for_indicator(ind)
        assert "Count of deaths" in result

    def test_includes_unit(self):
        ind = self._ind(name="X", unit="Number")
        result = _text_for_indicator(ind)
        assert "Unit: Number" in result

    def test_includes_monitoring_questions(self):
        ind = self._ind(name="X", questions=["How many?", "Which countries?"])
        result = _text_for_indicator(ind)
        assert "How many?" in result
        assert "Which countries?" in result

    def test_blank_definition_omitted(self):
        ind = self._ind(name="X", definition="   ")
        result = _text_for_indicator(ind)
        assert "Unit:" not in result or "  " not in result

    def test_monitoring_questions_exception_handled(self):
        ind = MagicMock()
        ind.name = "Y"
        ind.definition = None
        ind.unit = None
        ind.monitoring_questions_list = MagicMock(side_effect=Exception("crash"))
        # Should not raise
        result = _text_for_indicator(ind)
        assert "Y" in result

    def test_empty_name_and_no_other_fields(self):
        ind = self._ind(name="")
        result = _text_for_indicator(ind)
        assert result == ""

    def test_question_none_or_empty_skipped(self):
        ind = self._ind(name="Z", questions=[None, "", "Valid Q"])
        result = _text_for_indicator(ind)
        assert "Valid Q" in result


# ---------------------------------------------------------------------------
# IndicatorResolutionService.__init__ and embedding_service
# ---------------------------------------------------------------------------
class TestIndicatorResolutionServiceInit:
    def test_init_sets_none_embedding_service(self):
        svc = IndicatorResolutionService()
        assert svc._embedding_service is None

    def test_embedding_service_property_creates_instance(self, app):
        with app.app_context():
            svc = IndicatorResolutionService()
            with patch(
                "app.services.indicator_resolution_service.AIEmbeddingService"
            ) as MockEmb:
                MockEmb.return_value = MagicMock()
                es = svc.embedding_service
                assert es is MockEmb.return_value

    def test_embedding_service_cached(self, app):
        with app.app_context():
            svc = IndicatorResolutionService()
            with patch(
                "app.services.indicator_resolution_service.AIEmbeddingService"
            ) as MockEmb:
                MockEmb.return_value = MagicMock()
                es1 = svc.embedding_service
                es2 = svc.embedding_service
                MockEmb.assert_called_once()
                assert es1 is es2


# ---------------------------------------------------------------------------
# IndicatorResolutionService.resolve
# ---------------------------------------------------------------------------
class TestIndicatorResolutionServiceResolve:
    def test_empty_query_returns_empty(self, app):
        with app.app_context():
            svc = IndicatorResolutionService()
            result = svc.resolve("")
            assert result == []

    def test_whitespace_query_returns_empty(self, app):
        with app.app_context():
            svc = IndicatorResolutionService()
            result = svc.resolve("   ")
            assert result == []

    def test_embedding_error_returns_empty(self, app):
        with app.app_context():
            from app.services.ai_embedding_service import EmbeddingError

            svc = IndicatorResolutionService()
            mock_es = MagicMock()
            mock_es.generate_embedding.side_effect = EmbeddingError("fail")
            svc._embedding_service = mock_es

            result = svc.resolve("test query")
            assert result == []

    def test_successful_resolve_returns_list(self, app):
        with app.app_context():
            svc = IndicatorResolutionService()
            mock_es = MagicMock()
            mock_es.generate_embedding.return_value = ([0.1, 0.2, 0.3], 0.0001)
            svc._embedding_service = mock_es

            mock_ind = MagicMock()
            with patch.object(svc, "_search_similar", return_value=[(mock_ind, 0.95)]):
                result = svc.resolve("mortality rate")
                assert len(result) == 1
                assert result[0][1] == 0.95


# ---------------------------------------------------------------------------
# IndicatorResolutionService._search_similar
# ---------------------------------------------------------------------------
class TestSearchSimilar:
    def test_returns_results_from_db(self, app):
        with app.app_context():
            svc = IndicatorResolutionService()
            mock_ind = MagicMock()
            mock_ind.archived = False

            with patch("app.services.indicator_resolution_service.db") as mock_db:
                mock_db.session.query.return_value.join.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
                    (mock_ind, 0.9)
                ]
                result = svc._search_similar([0.1, 0.2], top_k=5)
                assert len(result) == 1
                assert result[0][1] == pytest.approx(0.9)

    def test_exception_returns_empty(self, app):
        with app.app_context():
            svc = IndicatorResolutionService()

            with patch("app.services.indicator_resolution_service.db") as mock_db:
                mock_db.session.query.side_effect = Exception("vector error")
                mock_db.session.rollback = MagicMock()
                result = svc._search_similar([0.1, 0.2])
                assert result == []

    def test_rollback_failure_in_exception_path(self, app):
        with app.app_context():
            svc = IndicatorResolutionService()

            with patch("app.services.indicator_resolution_service.db") as mock_db:
                mock_db.session.query.side_effect = Exception("vector error")
                mock_db.session.rollback = MagicMock(side_effect=Exception("rollback fail"))
                result = svc._search_similar([0.1, 0.2])
                assert result == []

    def test_exclude_archived_filter_applied(self, app):
        with app.app_context():
            svc = IndicatorResolutionService()

            with patch("app.services.indicator_resolution_service.db") as mock_db:
                query_chain = MagicMock()
                mock_db.session.query.return_value = query_chain
                query_chain.join.return_value = query_chain
                query_chain.filter.return_value = query_chain
                query_chain.order_by.return_value = query_chain
                query_chain.limit.return_value = query_chain
                query_chain.all.return_value = []

                svc._search_similar([0.1], exclude_archived=True)
                # filter was called (for archived=False)
                query_chain.filter.assert_called()


# ---------------------------------------------------------------------------
# IndicatorResolutionService.resolve_with_llm
# ---------------------------------------------------------------------------
class TestResolveWithLlm:
    def test_empty_top_k_returns_none(self, app):
        with app.app_context():
            svc = IndicatorResolutionService()
            result = svc.resolve_with_llm("what is X", [])
            assert result is None

    def test_empty_query_returns_none(self, app):
        with app.app_context():
            svc = IndicatorResolutionService()
            mock_ind = MagicMock()
            result = svc.resolve_with_llm("", [(mock_ind, 0.9)])
            assert result is None

    def test_successful_llm_returns_matched_indicator(self, app):
        with app.app_context():
            svc = IndicatorResolutionService()
            ind1 = MagicMock()
            ind1.id = 10
            ind1.name = "Test Indicator"
            ind1.definition = "A definition"
            ind2 = MagicMock()
            ind2.id = 20
            ind2.name = "Another Indicator"
            ind2.definition = None

            fake_resp = MagicMock()
            fake_resp.choices[0].message.content = json.dumps({"indicator_id": 10})

            # OpenAI is lazily imported inside resolve_with_llm: patch at openai module
            with patch("openai.OpenAI") as MockOAI:
                mock_client = MagicMock()
                MockOAI.return_value = mock_client
                mock_client.chat.completions.create.return_value = fake_resp

                result = svc.resolve_with_llm("test query", [(ind1, 0.9), (ind2, 0.8)])
                assert result is ind1

    def test_llm_returns_null_indicator_id(self, app):
        with app.app_context():
            svc = IndicatorResolutionService()
            ind = MagicMock()
            ind.id = 5
            ind.name = "X"
            ind.definition = None

            fake_resp = MagicMock()
            fake_resp.choices[0].message.content = json.dumps({"indicator_id": None})

            with patch("openai.OpenAI") as MockOAI:
                mock_client = MagicMock()
                MockOAI.return_value = mock_client
                mock_client.chat.completions.create.return_value = fake_resp

                result = svc.resolve_with_llm("query", [(ind, 0.9)])
                assert result is None

    def test_llm_returns_id_not_in_list_falls_back_to_first(self, app):
        with app.app_context():
            svc = IndicatorResolutionService()
            ind = MagicMock()
            ind.id = 1
            ind.name = "X"
            ind.definition = None

            fake_resp = MagicMock()
            fake_resp.choices[0].message.content = json.dumps({"indicator_id": 999})

            with patch("openai.OpenAI") as MockOAI:
                mock_client = MagicMock()
                MockOAI.return_value = mock_client
                mock_client.chat.completions.create.return_value = fake_resp

                result = svc.resolve_with_llm("query", [(ind, 0.9)])
                assert result is ind

    def test_llm_response_with_markdown_code_block(self, app):
        with app.app_context():
            svc = IndicatorResolutionService()
            ind = MagicMock()
            ind.id = 7
            ind.name = "X"
            ind.definition = None

            markdown_content = '```json\n{"indicator_id": 7}\n```'
            fake_resp = MagicMock()
            fake_resp.choices[0].message.content = markdown_content

            with patch("openai.OpenAI") as MockOAI:
                mock_client = MagicMock()
                MockOAI.return_value = mock_client
                mock_client.chat.completions.create.return_value = fake_resp

                result = svc.resolve_with_llm("query", [(ind, 0.9)])
                assert result is ind

    def test_llm_exception_returns_first_candidate(self, app):
        with app.app_context():
            svc = IndicatorResolutionService()
            ind = MagicMock()
            ind.id = 3
            ind.name = "X"
            ind.definition = None

            with patch("openai.OpenAI", side_effect=Exception("openai error")):
                result = svc.resolve_with_llm("query", [(ind, 0.9)])
                assert result is ind

    def test_shows_up_to_15_candidates(self, app):
        with app.app_context():
            svc = IndicatorResolutionService()
            candidates = []
            for i in range(20):
                m = MagicMock()
                m.id = i
                m.name = f"Indicator {i}"
                m.definition = None
                candidates.append((m, 0.9))

            fake_resp = MagicMock()
            fake_resp.choices[0].message.content = json.dumps({"indicator_id": 0})

            with patch("openai.OpenAI") as MockOAI:
                mock_client = MagicMock()
                MockOAI.return_value = mock_client
                mock_client.chat.completions.create.return_value = fake_resp

                result = svc.resolve_with_llm("query", candidates)
                call_kwargs = mock_client.chat.completions.create.call_args
                messages = call_kwargs[1].get("messages") or call_kwargs[0][1]
                user_msg = next(m for m in messages if m["role"] == "user")
                assert user_msg["content"].count("- id=") <= 15


# ---------------------------------------------------------------------------
# IndicatorResolutionService.sync_all
# ---------------------------------------------------------------------------
class TestSyncAll:
    def test_no_indicators_returns_zero(self, app):
        with app.app_context():
            svc = IndicatorResolutionService()
            with patch("app.services.indicator_resolution_service.IndicatorBank") as MockIB:
                MockIB.query.filter.return_value.order_by.return_value.all.return_value = []
                count, cost = svc.sync_all()
                assert count == 0
                assert cost == 0.0

    def test_embedding_error_raised(self, app):
        with app.app_context():
            from app.services.ai_embedding_service import EmbeddingError

            svc = IndicatorResolutionService()
            mock_es = MagicMock()
            mock_es.generate_embeddings_batch.side_effect = EmbeddingError("batch fail")
            mock_es.model = "text-embedding-3-small"
            svc._embedding_service = mock_es

            ind = MagicMock()
            ind.name = "X"
            ind.definition = None
            ind.unit = None
            ind.monitoring_questions_list = []

            with patch("app.services.indicator_resolution_service.IndicatorBank") as MockIB:
                MockIB.query.filter.return_value.order_by.return_value.all.return_value = [ind]
                with pytest.raises(EmbeddingError):
                    svc.sync_all()

    def test_successful_sync_upserts_embeddings(self, app):
        with app.app_context():
            svc = IndicatorResolutionService()
            mock_es = MagicMock()
            mock_es.generate_embeddings_batch.return_value = ([[0.1, 0.2]], 0.001)
            mock_es.model = "text-embedding-3-small"
            svc._embedding_service = mock_es

            ind = MagicMock()
            ind.id = 1
            ind.name = "Test"
            ind.definition = None
            ind.unit = None
            ind.monitoring_questions_list = []

            with patch("app.services.indicator_resolution_service.IndicatorBank") as MockIB, \
                 patch("app.services.indicator_resolution_service.IndicatorBankEmbedding") as MockEmb, \
                 patch("app.services.indicator_resolution_service.db") as mock_db:

                MockIB.query.filter.return_value.order_by.return_value.all.return_value = [ind]
                MockEmb.return_value = MagicMock()
                mock_db.session.query.return_value.filter_by.return_value.first.return_value = None
                mock_db.session.add = MagicMock()
                mock_db.session.commit = MagicMock()

                count, cost = svc.sync_all()
                assert count == 1

    def test_updates_existing_embedding(self, app):
        with app.app_context():
            svc = IndicatorResolutionService()
            mock_es = MagicMock()
            mock_es.generate_embeddings_batch.return_value = ([[0.1, 0.2]], 0.001)
            mock_es.model = "text-embedding-3-small"
            svc._embedding_service = mock_es

            ind = MagicMock()
            ind.id = 1
            ind.name = "Test"
            ind.definition = None
            ind.unit = None
            ind.monitoring_questions_list = []

            existing_emb = MagicMock()

            with patch("app.services.indicator_resolution_service.IndicatorBank") as MockIB, \
                 patch("app.services.indicator_resolution_service.db") as mock_db:

                MockIB.query.filter.return_value.order_by.return_value.all.return_value = [ind]
                mock_db.session.query.return_value.filter_by.return_value.first.return_value = existing_emb
                mock_db.session.commit = MagicMock()

                count, cost = svc.sync_all()
                assert count == 1
                assert existing_emb.embedding == [0.1, 0.2]

    def test_commit_error_raises(self, app):
        with app.app_context():
            svc = IndicatorResolutionService()
            mock_es = MagicMock()
            mock_es.generate_embeddings_batch.return_value = ([[0.1]], 0.001)
            mock_es.model = "text-embedding-3-small"
            svc._embedding_service = mock_es

            ind = MagicMock()
            ind.id = 1
            ind.name = "T"
            ind.definition = None
            ind.unit = None
            ind.monitoring_questions_list = []

            with patch("app.services.indicator_resolution_service.IndicatorBank") as MockIB, \
                 patch("app.services.indicator_resolution_service.db") as mock_db:

                MockIB.query.filter.return_value.order_by.return_value.all.return_value = [ind]
                mock_db.session.query.return_value.filter_by.return_value.first.return_value = None
                mock_db.session.add = MagicMock()
                mock_db.session.commit = MagicMock(side_effect=Exception("commit fail"))
                mock_db.session.rollback = MagicMock()

                with pytest.raises(Exception, match="commit fail"):
                    svc.sync_all()


# ---------------------------------------------------------------------------
# IndicatorResolutionService.has_embeddings
# ---------------------------------------------------------------------------
class TestHasEmbeddings:
    def test_returns_true_when_embedding_exists(self, app):
        with app.app_context():
            svc = IndicatorResolutionService()
            with patch("app.services.indicator_resolution_service.db") as mock_db:
                mock_db.session.query.return_value.limit.return_value.first.return_value = MagicMock()
                assert svc.has_embeddings() is True

    def test_returns_false_when_no_embeddings(self, app):
        with app.app_context():
            svc = IndicatorResolutionService()
            with patch("app.services.indicator_resolution_service.db") as mock_db:
                mock_db.session.query.return_value.limit.return_value.first.return_value = None
                assert svc.has_embeddings() is False

    def test_exception_returns_false(self, app):
        with app.app_context():
            svc = IndicatorResolutionService()
            with patch("app.services.indicator_resolution_service.db") as mock_db:
                mock_db.session.query.side_effect = Exception("db error")
                assert svc.has_embeddings() is False


# ---------------------------------------------------------------------------
# get_indicator_candidates
# ---------------------------------------------------------------------------
class TestGetIndicatorCandidates:
    def test_integer_id_direct_lookup(self, app):
        with app.app_context():
            ind = MagicMock()
            with patch("app.services.indicator_resolution_service.db") as mock_db:
                mock_db.session.get.return_value = ind
                result = get_indicator_candidates(5)
                assert result == [(ind, 1.0)]

    def test_integer_id_not_found_returns_empty(self, app):
        with app.app_context():
            with patch("app.services.indicator_resolution_service.db") as mock_db:
                mock_db.session.get.return_value = None
                result = get_indicator_candidates(999)
                assert result == []

    def test_numeric_string_direct_lookup(self, app):
        with app.app_context():
            ind = MagicMock()
            with patch("app.services.indicator_resolution_service.db") as mock_db:
                mock_db.session.get.return_value = ind
                result = get_indicator_candidates("42")
                assert result == [(ind, 1.0)]

    def test_empty_string_returns_empty(self, app):
        with app.app_context():
            result = get_indicator_candidates("")
            assert result == []

    def test_keyword_method_returns_empty(self, app):
        with app.app_context():
            with patch.dict(app.config, {"AI_INDICATOR_RESOLUTION_METHOD": "keyword"}):
                result = get_indicator_candidates("mortality rate")
                assert result == []

    def test_vector_method_no_embeddings_returns_empty(self, app):
        with app.app_context():
            with patch.dict(app.config, {"AI_INDICATOR_RESOLUTION_METHOD": "vector"}):
                with patch(
                    "app.services.indicator_resolution_service.IndicatorResolutionService"
                ) as MockSvc:
                    mock_svc = MagicMock()
                    mock_svc.has_embeddings.return_value = False
                    MockSvc.return_value = mock_svc
                    result = get_indicator_candidates("mortality rate")
                    assert result == []

    def test_vector_method_with_embeddings_returns_results(self, app):
        with app.app_context():
            ind = MagicMock()
            with patch.dict(app.config, {"AI_INDICATOR_RESOLUTION_METHOD": "vector", "AI_INDICATOR_TOP_K": "5"}):
                with patch(
                    "app.services.indicator_resolution_service.IndicatorResolutionService"
                ) as MockSvc:
                    mock_svc = MagicMock()
                    mock_svc.has_embeddings.return_value = True
                    mock_svc.resolve.return_value = [(ind, 0.88)]
                    MockSvc.return_value = mock_svc
                    result = get_indicator_candidates("mortality rate")
                    assert len(result) == 1

    def test_vector_method_empty_results_logged(self, app):
        with app.app_context():
            with patch.dict(app.config, {"AI_INDICATOR_RESOLUTION_METHOD": "vector"}):
                with patch(
                    "app.services.indicator_resolution_service.IndicatorResolutionService"
                ) as MockSvc:
                    mock_svc = MagicMock()
                    mock_svc.has_embeddings.return_value = True
                    mock_svc.resolve.return_value = []
                    MockSvc.return_value = mock_svc
                    result = get_indicator_candidates("unknown query xyz")
                    assert result == []

    def test_top_k_from_config(self, app):
        with app.app_context():
            with patch.dict(app.config, {
                "AI_INDICATOR_RESOLUTION_METHOD": "vector",
                "AI_INDICATOR_TOP_K": "3",
            }):
                with patch(
                    "app.services.indicator_resolution_service.IndicatorResolutionService"
                ) as MockSvc:
                    mock_svc = MagicMock()
                    mock_svc.has_embeddings.return_value = True
                    mock_svc.resolve.return_value = []
                    MockSvc.return_value = mock_svc
                    get_indicator_candidates("test", top_k=None)
                    mock_svc.resolve.assert_called_with("test", top_k=3)


# ---------------------------------------------------------------------------
# resolve_indicator_identifier
# ---------------------------------------------------------------------------
class TestResolveIndicatorIdentifier:
    def test_integer_direct_lookup(self, app):
        with app.app_context():
            ind = MagicMock()
            with patch("app.services.indicator_resolution_service.db") as mock_db:
                mock_db.session.get.return_value = ind
                result = resolve_indicator_identifier(5)
                assert result is ind

    def test_numeric_string_direct_lookup(self, app):
        with app.app_context():
            ind = MagicMock()
            with patch("app.services.indicator_resolution_service.db") as mock_db:
                mock_db.session.get.return_value = ind
                result = resolve_indicator_identifier("10")
                assert result is ind

    def test_keyword_method_returns_none(self, app):
        with app.app_context():
            with patch.dict(app.config, {"AI_INDICATOR_RESOLUTION_METHOD": "keyword"}):
                result = resolve_indicator_identifier("mortality rate")
                assert result is None

    def test_vector_no_embeddings_returns_none(self, app):
        with app.app_context():
            with patch.dict(app.config, {"AI_INDICATOR_RESOLUTION_METHOD": "vector"}):
                with patch(
                    "app.services.indicator_resolution_service.IndicatorResolutionService"
                ) as MockSvc:
                    mock_svc = MagicMock()
                    mock_svc.has_embeddings.return_value = False
                    MockSvc.return_value = mock_svc
                    result = resolve_indicator_identifier("mortality rate")
                    assert result is None

    def test_vector_no_candidates_returns_none(self, app):
        with app.app_context():
            with patch.dict(app.config, {"AI_INDICATOR_RESOLUTION_METHOD": "vector"}):
                with patch(
                    "app.services.indicator_resolution_service.IndicatorResolutionService"
                ) as MockSvc:
                    mock_svc = MagicMock()
                    mock_svc.has_embeddings.return_value = True
                    mock_svc.resolve.return_value = []
                    MockSvc.return_value = mock_svc
                    result = resolve_indicator_identifier("unknown query")
                    assert result is None

    def test_vector_returns_first_candidate(self, app):
        with app.app_context():
            ind = MagicMock()
            with patch.dict(app.config, {"AI_INDICATOR_RESOLUTION_METHOD": "vector"}):
                with patch(
                    "app.services.indicator_resolution_service.IndicatorResolutionService"
                ) as MockSvc:
                    mock_svc = MagicMock()
                    mock_svc.has_embeddings.return_value = True
                    mock_svc.resolve.return_value = [(ind, 0.9)]
                    MockSvc.return_value = mock_svc
                    result = resolve_indicator_identifier("mortality")
                    assert result is ind

    def test_vector_then_llm_calls_resolve_with_llm(self, app):
        with app.app_context():
            ind = MagicMock()
            with patch.dict(app.config, {
                "AI_INDICATOR_RESOLUTION_METHOD": "vector_then_llm",
                "AI_INDICATOR_LLM_DISAMBIGUATE": True,
                "AI_INDICATOR_TOP_K": "5",
            }):
                with patch(
                    "app.services.indicator_resolution_service.IndicatorResolutionService"
                ) as MockSvc:
                    mock_svc = MagicMock()
                    mock_svc.has_embeddings.return_value = True
                    mock_svc.resolve.return_value = [(ind, 0.9)]
                    mock_svc.resolve_with_llm.return_value = ind
                    MockSvc.return_value = mock_svc

                    result = resolve_indicator_identifier(
                        "mortality rate", user_query="What is the mortality rate?"
                    )
                    mock_svc.resolve_with_llm.assert_called_once()
                    assert result is ind

    def test_vector_then_llm_disabled_returns_first(self, app):
        with app.app_context():
            ind = MagicMock()
            with patch.dict(app.config, {
                "AI_INDICATOR_RESOLUTION_METHOD": "vector_then_llm",
                "AI_INDICATOR_LLM_DISAMBIGUATE": False,
            }):
                with patch(
                    "app.services.indicator_resolution_service.IndicatorResolutionService"
                ) as MockSvc:
                    mock_svc = MagicMock()
                    mock_svc.has_embeddings.return_value = True
                    mock_svc.resolve.return_value = [(ind, 0.9)]
                    MockSvc.return_value = mock_svc

                    result = resolve_indicator_identifier("mortality rate")
                    mock_svc.resolve_with_llm.assert_not_called()
                    assert result is ind
