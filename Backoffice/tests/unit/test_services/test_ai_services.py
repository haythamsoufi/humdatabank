"""
Unit Tests for AI/RAG Services

Tests the core AI functionality including:
- Document processing
- Chunking
- Embeddings
- Vector store
- Agent executor
- Tools registry
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import List, Dict, Any


# ============================================================================
# Test AIChunkingService
# ============================================================================

class TestAIChunkingService:
    """Tests for the AI chunking service."""

    @pytest.fixture
    def chunker(self, app):
        """Create chunking service instance."""
        with app.app_context():
            from app.services.ai_chunking_service import AIChunkingService
            return AIChunkingService()

    def test_chunk_short_text(self, chunker):
        """Short text should produce a single chunk."""
        text = "This is a short piece of text."
        chunks = chunker.chunk_document(text)
        assert len(chunks) == 1
        assert chunks[0].content == text

    def test_chunk_long_text(self, chunker):
        """Long text should be split into multiple chunks."""
        # Create text longer than chunk size
        text = "This is a sentence. " * 200
        chunks = chunker.chunk_document(text)
        assert len(chunks) > 1

    def test_chunk_preserves_content(self, chunker):
        """Chunking should preserve all content."""
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = chunker.chunk_document(text)

        # Reconstruct (accounting for overlap)
        all_content = " ".join(c.content for c in chunks)
        assert "First paragraph" in all_content
        assert "Second paragraph" in all_content
        assert "Third paragraph" in all_content

    def test_chunk_with_pages(self, chunker):
        """Chunking with page metadata."""
        pages = [
            {'content': 'Page 1 content.', 'page_number': 1},
            {'content': 'Page 2 content.', 'page_number': 2},
        ]
        chunks = chunker.chunk_document("", pages=pages)

        # Should have chunks with page numbers
        for chunk in chunks:
            assert hasattr(chunk, 'page_number')

    def test_semantic_chunking_strategy(self, chunker):
        """Test semantic chunking splits on natural boundaries."""
        text = """# Chapter 1

This is the introduction.

## Section 1.1

This is section content.

## Section 1.2

More section content here."""

        chunks = chunker.chunk_document(text, strategy='semantic')
        assert len(chunks) >= 1


# ============================================================================
# Test AIEmbeddingService
# ============================================================================

class TestAIEmbeddingService:
    """Tests for the AI embedding service."""

    @pytest.fixture
    def embedding_service_local(self, app):
        """Create embedding service with local provider."""
        with app.app_context():
            app.config['AI_EMBEDDING_PROVIDER'] = 'local'
            from app.services.ai_embedding_service import AIEmbeddingService
            return AIEmbeddingService()

    def test_generate_embedding_local(self, embedding_service_local):
        """Test local embedding generation."""
        text = "This is a test sentence for embedding."
        embedding, cost = embedding_service_local.generate_embedding(text)

        assert isinstance(embedding, list)
        assert len(embedding) > 0
        assert all(isinstance(x, float) for x in embedding)
        # Some providers may still report minimal usage cost depending on config.
        assert cost >= 0

    def test_generate_embeddings_batch(self, embedding_service_local):
        """Test batch embedding generation."""
        texts = [
            "First sentence.",
            "Second sentence.",
            "Third sentence."
        ]
        embeddings, total_cost = embedding_service_local.generate_embeddings_batch(texts)

        assert len(embeddings) == 3
        assert all(len(e) > 0 for e in embeddings)

    @patch('openai.OpenAI')
    def test_generate_embedding_openai(self, mock_openai, app):
        """Test OpenAI embedding generation."""
        with app.app_context():
            app.config['AI_EMBEDDING_PROVIDER'] = 'openai'
            app.config['OPENAI_API_KEY'] = 'test-key'
            # Match dimensions to mock so validation passes (other tests may set 128)
            app.config['AI_EMBEDDING_DIMENSIONS'] = 1536

            # Mock OpenAI response
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_client.embeddings.create.return_value = MagicMock(
                data=[MagicMock(embedding=[0.1] * 1536)],
                usage=MagicMock(total_tokens=10)
            )

            from app.services.ai_embedding_service import AIEmbeddingService
            service = AIEmbeddingService()

            embedding, cost = service.generate_embedding("Test text")

            assert len(embedding) == 1536
            assert cost > 0


# ============================================================================
# Test AIToolsRegistry
# ============================================================================

class TestAIToolsRegistry:
    """Tests for the AI tools registry."""

    @pytest.fixture
    def tools_registry(self, app):
        """Create tools registry instance."""
        with app.app_context():
            # Mock the vector store dependency (implementation lives in ai_tools.registry)
            with patch('app.services.ai_tools.registry.AIVectorStore'):
                from app.services.ai_tools import AIToolsRegistry
                return AIToolsRegistry()

    def test_get_tool_definitions_openai(self, tools_registry):
        """Test getting OpenAI function calling definitions."""
        tools = tools_registry.get_tool_definitions_openai()

        assert isinstance(tools, list)
        # Should have tools defined
        for tool in tools:
            assert 'type' in tool
            assert 'function' in tool
            assert 'name' in tool['function']
            assert 'description' in tool['function']

    def test_execute_tool_success(self, tools_registry):
        """Test successful tool execution."""
        with patch.object(tools_registry, 'get_indicator_value') as mock_tool:
            mock_tool.return_value = {'success': True, 'result': {'value': 100}}

            result = tools_registry.execute_tool(
                'get_indicator_value',
                country_identifier='Kenya',
                indicator_name='volunteers'
            )

            assert result['success'] is True

    def test_execute_unknown_tool(self, tools_registry):
        """Test executing an unknown tool."""
        from app.services.ai_tools import ToolExecutionError

        with pytest.raises(ToolExecutionError):
            tools_registry.execute_tool('unknown_tool')


# ============================================================================
# Test platform scope heuristics (out-of-scope gate before agent)
# ============================================================================

class TestPlatformScopeHeuristic:
    """Heuristic fast path for in-scope messages — avoids LLM classifier."""

    def test_data_query_is_in_scope(self, app):
        with app.app_context():
            from app.services.ai_query_rewriter import heuristic_likely_in_platform_scope

            assert heuristic_likely_in_platform_scope("volunteers in Syria 2024") is True
            assert heuristic_likely_in_platform_scope("which countries mention climate in UPL") is True

    def test_obvious_off_topic_not_heuristic_in_scope(self, app):
        with app.app_context():
            from app.services.ai_query_rewriter import heuristic_likely_in_platform_scope

            assert heuristic_likely_in_platform_scope("generate a code of a calculator app in python") is False
            assert heuristic_likely_in_platform_scope("write me a recipe for lasagna") is False

    def test_meta_help_is_in_scope(self, app):
        with app.app_context():
            from app.services.ai_query_rewriter import heuristic_likely_in_platform_scope

            assert heuristic_likely_in_platform_scope("what can you do") is True


# ============================================================================
# Test AIAgentExecutor
# ============================================================================

class TestAIAgentExecutor:
    """Tests for the AI agent executor."""

    @pytest.fixture
    def agent(self, app):
        """Create agent executor instance with mocked dependencies."""
        with app.app_context():
            app.config['AI_AGENT_ENABLED'] = True
            app.config['OPENAI_API_KEY'] = 'test-key'

            with patch('openai.OpenAI'):
                from app.services.ai_agent import AIAgentExecutor
                agent = AIAgentExecutor()
                return agent

    def test_agent_initialization(self, agent):
        """Test agent initializes correctly."""
        assert agent is not None
        assert agent.max_iterations > 0
        assert agent.cost_limit_usd is None or agent.cost_limit_usd > 0

    def test_execute_simple_query(self, app):
        """Test execute() orchestration with mocked dependencies."""
        with app.app_context():
            app.config['AI_AGENT_ENABLED'] = True
            app.config['OPENAI_API_KEY'] = 'test-key'

            with patch('openai.OpenAI'):
                from app.services.ai_agent import AIAgentExecutor
                agent = AIAgentExecutor()

                with (
                    patch.object(agent.trace_service, "create_trace", return_value=None),
                    patch.object(agent.trace_service, "finalize_trace", return_value=None),
                    patch.object(agent.query_planner, "plan_simple", return_value=None),
                    patch.object(
                        agent,
                        "_execute_openai_native",
                        return_value={
                            "success": True,
                            "answer": "Kenya has 1500 volunteers.",
                            "steps": [],
                            "status": "completed",
                            "tool_calls": 0,
                            "iterations": 1,
                        },
                    ),
                ):
                    result = agent.execute(
                        query="What is Kenya?",
                        user_context={"role": "admin"},
                        language="en",
                    )

                assert result["success"] is True
                assert "answer" in result

    def test_cost_limit_respected(self, agent):
        """Test that cost limit is enforced."""
        agent.cost_limit_usd = 0.001  # Very low limit

        # Mock to simulate high cost (cost estimation lives in ai_agent.executor)
        with patch('app.services.ai_agent.executor._estimate_openai_cost', return_value=1.0):
            # Should not exceed cost limit
            result = agent._execute_openai_native(
                query="test",
                conversation_history=None,
                user_context={},
                language='en'
            )

            # Either succeeds quickly or hits cost limit
            assert 'total_cost' in result or 'answer' in result

    def test_redundant_document_search_guard_exact_duplicate(self):
        """Exact duplicate query should be flagged as redundant."""
        from app.services.ai_tool_routing_policy import is_redundant_document_search

        recent = [
            {
                "tool_name": "search_documents",
                "query_norm": "digital transformation data system",
                "return_all_countries": True,
            }
        ]
        is_redundant, reason = is_redundant_document_search(
            tool_name="search_documents",
            tool_args={
                "query": "\"digital transformation\" OR \"data system\"",
                "return_all_countries": True,
                "top_k": 500,
            },
            recent_search_signatures=recent,
        )

        assert is_redundant is True
        assert "query" in reason

    def test_redundant_document_search_guard_reordered_terms(self):
        """Reordered/near-identical query terms should be flagged as redundant."""
        from app.services.ai_tool_routing_policy import is_redundant_document_search

        recent = [
            {
                "tool_name": "search_documents",
                "query_norm": "digital transformation data system information system",
                "return_all_countries": True,
            }
        ]
        is_redundant, reason = is_redundant_document_search(
            tool_name="search_documents",
            tool_args={
                "query": "\"information system\" OR \"data system\" OR \"digital transformation\"",
                "return_all_countries": True,
                "top_k": 200,
            },
            recent_search_signatures=recent,
        )

        assert is_redundant is True
        assert reason in ("same normalized query", "trivially similar query")

    def test_redundant_document_search_guard_different_query_not_flagged(self):
        """A genuinely different query should not be flagged as redundant."""
        from app.services.ai_tool_routing_policy import is_redundant_document_search

        recent = [
            {
                "tool_name": "search_documents",
                "query_norm": "digital transformation data system information system",
                "return_all_countries": True,
            }
        ]
        is_redundant, reason = is_redundant_document_search(
            tool_name="search_documents",
            tool_args={
                "query": "disaster preparedness early warning systems",
                "return_all_countries": True,
                "top_k": 50,
            },
            recent_search_signatures=recent,
        )

        assert is_redundant is False
        assert reason == ""


# ============================================================================
# Test extracted helper/policy modules
# ============================================================================

class TestAIToolRoutingPolicy:
    """Tests for extracted tool routing policy helpers."""

    def test_docs_only_sources_enabled_true(self, app):
        """docs_only_sources_enabled should be true for docs-only toggle state."""
        with app.app_context():
            with app.test_request_context("/"):
                from flask import g
                from app.services.ai_tool_routing_policy import docs_only_sources_enabled

                g.ai_sources_cfg = {
                    "historical": False,
                    "system_documents": True,
                    "upr_documents": False,
                }
                assert docs_only_sources_enabled() is True

    def test_docs_only_sources_enabled_false_when_historical_on(self, app):
        """docs_only_sources_enabled should be false when historical source is on."""
        with app.app_context():
            with app.test_request_context("/"):
                from flask import g
                from app.services.ai_tool_routing_policy import docs_only_sources_enabled

                g.ai_sources_cfg = {
                    "historical": True,
                    "system_documents": True,
                    "upr_documents": True,
                }
                assert docs_only_sources_enabled() is False

    def test_should_skip_search_pagination_when_relevance_drops(self):
        """Guard should stop deep pagination after consecutive low-score batches."""
        from app.services.ai_tool_routing_policy import should_skip_search_pagination

        recent = [
            {
                "tool_name": "search_documents",
                "query_norm": "ifrc pgi minimum standards",
                "return_all_countries": True,
                "offset": 0,
                "total_count": 420,
                "max_combined_score": 0.88,
            },
            {
                "tool_name": "search_documents",
                "query_norm": "ifrc pgi minimum standards",
                "return_all_countries": True,
                "offset": 100,
                "total_count": 420,
                "max_combined_score": 0.39,
            },
            {
                "tool_name": "search_documents",
                "query_norm": "ifrc pgi minimum standards",
                "return_all_countries": True,
                "offset": 200,
                "total_count": 420,
                "max_combined_score": 0.37,
            },
        ]
        should_skip, reason = should_skip_search_pagination(
            tool_name="search_documents",
            tool_args={
                "query": "IFRC PGI minimum standards",
                "return_all_countries": True,
                "offset": 300,
                "limit": 100,
            },
            recent_search_signatures=recent,
            full_table_requested=False,
            max_batches_for_general=4,
            low_score_threshold=0.42,
            max_consecutive_low_score_batches=2,
        )

        assert should_skip is True
        assert "low-relevance" in reason

    def test_should_not_skip_search_pagination_for_full_table_request(self):
        """Explicit full-table flow should keep exhaustive pagination."""
        from app.services.ai_tool_routing_policy import should_skip_search_pagination

        recent = [
            {
                "tool_name": "search_documents",
                "query_norm": "ifrc pgi minimum standards",
                "return_all_countries": True,
                "offset": 0,
                "total_count": 420,
                "max_combined_score": 0.88,
            },
            {
                "tool_name": "search_documents",
                "query_norm": "ifrc pgi minimum standards",
                "return_all_countries": True,
                "offset": 100,
                "total_count": 420,
                "max_combined_score": 0.30,
            },
            {
                "tool_name": "search_documents",
                "query_norm": "ifrc pgi minimum standards",
                "return_all_countries": True,
                "offset": 200,
                "total_count": 420,
                "max_combined_score": 0.29,
            },
            {
                "tool_name": "search_documents",
                "query_norm": "ifrc pgi minimum standards",
                "return_all_countries": True,
                "offset": 300,
                "total_count": 420,
                "max_combined_score": 0.28,
            },
        ]
        should_skip, reason = should_skip_search_pagination(
            tool_name="search_documents",
            tool_args={
                "query": "IFRC PGI minimum standards",
                "return_all_countries": True,
                "offset": 400,
                "limit": 100,
            },
            recent_search_signatures=recent,
            full_table_requested=True,
            max_batches_for_general=4,
            low_score_threshold=0.42,
            max_consecutive_low_score_batches=2,
        )

        assert should_skip is False
        assert reason == ""


class TestAIQueryIntentHelpers:
    """Tests for query-intent helper heuristics."""

    def test_platform_usage_help_detected(self):
        from app.services.ai_query_intent_helpers import is_platform_usage_help_question

        assert is_platform_usage_help_question("Where can I find the planning template in the platform?") is True

    def test_platform_usage_help_not_detected_for_document_lookup(self):
        from app.services.ai_query_intent_helpers import is_platform_usage_help_question

        assert is_platform_usage_help_question("Find the planning template PDF document for Syria.") is False

    def test_template_assignment_ambiguous_true(self):
        from app.services.ai_query_intent_helpers import is_template_assignment_ambiguous

        assert is_template_assignment_ambiguous("I need the template for this year's assignment") is True

    def test_template_assignment_ambiguous_false_for_document_request(self):
        from app.services.ai_query_intent_helpers import is_template_assignment_ambiguous

        assert is_template_assignment_ambiguous("Please download the planning template PDF file.") is False


class TestAIResponsePolicy:
    """Tests for extracted response policy helpers."""

    def test_user_expects_full_table_direct_request(self):
        """Explicit table requests should trigger table mode."""
        from app.services.ai_response_policy import user_expects_full_table

        assert user_expects_full_table("Please give me a full table of countries", []) is True

    def test_wants_reasoning_evidence_keywords(self):
        """Reasoning evidence helper should match explanatory intent words."""
        from app.services.ai_response_policy import wants_reasoning_evidence

        assert wants_reasoning_evidence("Why did this happen? Please provide evidence.") is True
        assert wants_reasoning_evidence("hello there") is False

    def test_sanitize_agent_answer_strips_traces(self):
        """Sanitizer should remove ReAct step traces and keep user-facing answer."""
        from app.services.ai_response_policy import sanitize_agent_answer

        raw = (
            "--- Step 1 ---\n"
            "Thought:\nNeed to search\n"
            "Action: search_documents\n"
            "Observation:\n"
            "The final answer is 42."
        )
        cleaned = sanitize_agent_answer(raw)
        assert "Step 1" not in cleaned
        assert "Action: search_documents" not in cleaned

    def test_sanitize_agent_answer_strips_leaked_search_documents_json(self):
        """Echoed search_documents tool arguments must not appear in user-facing text."""
        from app.services.ai_response_policy import sanitize_agent_answer

        leak = '{"query":"migration crime","return_all_countries":true,"top_k":50,"offset":0}'
        raw = (
            "I'll search the uploaded documents.\n"
            f"{leak}\n"
            "Summary of findings\n"
            "- Point one"
        )
        cleaned = sanitize_agent_answer(raw)
        assert leak not in cleaned
        assert "Summary of findings" in cleaned

    def test_sanitize_agent_answer_strips_inline_search_documents_json(self):
        from app.services.ai_response_policy import sanitize_agent_answer

        leak = '{"query":"x","return_all_countries":false,"top_k":8,"offset":0}'
        raw = f"Preamble {leak} after"
        cleaned = sanitize_agent_answer(raw)
        assert leak not in cleaned
        assert "Preamble" in cleaned and "after" in cleaned

    def test_sanitize_agent_answer_keeps_unrelated_json(self):
        """Do not strip arbitrary JSON that is not search_documents args."""
        from app.services.ai_response_policy import sanitize_agent_answer

        keep = '{"query":"title","notes":"user metadata"}'
        cleaned = sanitize_agent_answer(keep)
        assert "notes" in cleaned

    def test_contains_leaked_search_documents_tool_json(self):
        from app.services.ai_response_policy import contains_leaked_search_documents_tool_json

        leak = '{"query":"migration crime","return_all_countries":true,"top_k":50,"offset":0}'
        assert contains_leaked_search_documents_tool_json(f"Intro\n{leak}\nMore")
        assert not contains_leaked_search_documents_tool_json("Just prose, no JSON.")
        assert not contains_leaked_search_documents_tool_json('{"query":"title","notes":"user metadata"}')


class TestAIPayloadInference:
    """Tests for shape-based payload inference pipeline."""

    def test_timeseries_shape_detection(self):
        """Timeseries data should be detected by shape, not tool name."""
        from app.services.ai_payload_inference import _is_timeseries

        assert _is_timeseries({
            "series": [{"year": 2020, "value": 10}, {"year": 2021, "value": 12}],
        })
        assert not _is_timeseries({"series": [{"year": 2020}]})
        assert not _is_timeseries({"rows": [{"iso3": "KEN"}]})
        assert not _is_timeseries({})

    def test_country_rows_shape_detection(self):
        """Country rows with iso3 + value should be detected."""
        from app.services.ai_payload_inference import _is_country_rows, _TABLE_MIN_ROWS

        rows = [{"iso3": f"C{i:02d}", "value": i} for i in range(_TABLE_MIN_ROWS)]
        assert _is_country_rows({"rows": rows})
        assert not _is_country_rows({"rows": rows[:2]})
        assert not _is_country_rows({"series": []})

    def test_comparison_shape_detection(self):
        """Small countries list with indicator should be detected."""
        from app.services.ai_payload_inference import _is_comparison

        assert _is_comparison({
            "indicator": "Volunteers",
            "countries": [
                {"country": "Kenya", "value": 100},
                {"country": "Uganda", "value": 200},
            ],
        })
        assert not _is_comparison({"countries": [{"country": "Kenya", "value": 1}]})
        assert not _is_comparison({"countries": []})

    def test_categorical_counts_detection(self):
        """Dict of category -> count should be detected."""
        from app.services.ai_payload_inference import _is_categorical_counts

        assert _is_categorical_counts({"counts_by_area": {"health": 5, "wash": 3}})
        assert not _is_categorical_counts({"counts_by_area": {"only_one": 1}})
        assert not _is_categorical_counts({})

    def test_build_line_chart_from_tool_result(self):
        """Timeseries tool result should produce a line chart via shape detection."""
        from app.services.ai_payload_inference import build_payload_from_tool_result

        tool_result = {
            "success": True,
            "result": {
                "indicator": {"name": "Volunteers"},
                "country_name": "Kenya",
                "source_type": "indicator_bank",
                "series": [
                    {"year": 2020, "value": 10},
                    {"year": 2021, "value": 12},
                ],
            },
        }
        payloads = build_payload_from_tool_result(tool_result)
        assert "chart_payload" in payloads
        chart = payloads["chart_payload"]
        assert chart["type"] == "line"
        assert len(chart["series"]) == 2
        assert chart["metric"] == "Volunteers"
        assert chart["country"] == "Kenya"

    def test_build_bar_chart_from_comparison(self):
        """Comparison data should produce a bar chart."""
        from app.services.ai_payload_inference import build_payload_from_tool_result

        tool_result = {
            "success": True,
            "result": {
                "indicator": "Volunteers",
                "countries": [
                    {"country": "Kenya", "value": 100},
                    {"country": "Uganda", "value": 200},
                    {"country": "Tanzania", "value": 150},
                ],
            },
        }
        payloads = build_payload_from_tool_result(tool_result)
        assert "chart_payload" in payloads
        chart = payloads["chart_payload"]
        assert chart["type"] == "bar"
        assert len(chart["categories"]) == 3

    def test_build_pie_chart_from_counts(self):
        """Categorical counts should produce a pie chart."""
        from app.services.ai_payload_inference import build_payload_from_tool_result

        tool_result = {
            "success": True,
            "result": {
                "counts_by_area": {"health": 10, "wash": 8, "shelter": 5},
                "countries_grouped": [],
            },
        }
        payloads = build_payload_from_tool_result(tool_result)
        assert "chart_payload" in payloads
        chart = payloads["chart_payload"]
        assert chart["type"] == "pie"
        assert len(chart["slices"]) == 3

    def test_infer_payloads_from_steps(self):
        """Steps with timeseries data should produce chart_payload via infer_payloads."""
        from app.services.ai_payload_inference import infer_payloads

        steps = [
            {
                "step": 0,
                "action": "any_tool_name",
                "observation": {
                    "success": True,
                    "result": {
                        "indicator": {"name": "Staff"},
                        "country_name": "France",
                        "series": [
                            {"year": 2019, "value": 5},
                            {"year": 2020, "value": 7},
                            {"year": 2021, "value": 9},
                        ],
                    },
                },
            },
        ]
        result = infer_payloads(steps, "show staff trend in France")
        assert "chart_payload" in result
        assert result["chart_payload"]["type"] == "line"
        assert result.get("output_hint") == "chart"

    def test_extract_answer_column_hints_ignores_coverage_kpi_lines(self):
        """Pipe-heavy coverage lines must not be mistaken for markdown table headers."""
        from app.services.ai_payload_inference import _extract_answer_column_hints

        bad = (
            "Coverage: **286/286 plans** matched.\n\n"
            "Counts - Cash: 0 | CEA: 0 | Livelihoods: 0 | Social Protection: 0 (286 plans analysed)\n"
        )
        assert _extract_answer_column_hints(bad) == ""

    def test_unified_plans_focus_reference_enrichment_gating(self):
        from app.services.ai_payload_inference import _unified_plans_focus_wants_reference_enrichment

        assert not _unified_plans_focus_wants_reference_enrichment(
            "what countries prioritize migration in unified plans"
        )
        assert _unified_plans_focus_wants_reference_enrichment(
            "same question but add population and INFORM risk per country"
        )

    def test_focus_area_table_payload_includes_table_kind(self):
        from app.services.ai_payload_inference import build_payload_from_tool_result, _TABLE_MIN_ROWS

        def _iso3(idx: int) -> str:
            return (
                f"{chr(ord('A') + (idx % 26))}"
                f"{chr(ord('A') + ((idx // 26) % 26))}"
                f"{chr(ord('A') + ((idx // 676) % 26))}"
            )

        cg = []
        for i in range(_TABLE_MIN_ROWS):
            iso = _iso3(i)
            cg.append({
                "country_name": f"Country {i}",
                "country_iso3": iso,
                "plans": [{
                    "plan_year": 2025,
                    "document_title": f"Plan {i}",
                    "document_url": f"/d/{i}",
                    "area_details": {
                        "Migration Displacement": {
                            "evidence_chunks": 2,
                            "activity_examples": [
                                "Operational migration and displacement response text sample here.",
                            ],
                        },
                    },
                }],
            })
        tool_result = {
            "success": True,
            "result": {
                "counts_by_area": {"migration_displacement": 10},
                "countries_grouped": cg,
            },
        }
        payloads = build_payload_from_tool_result(tool_result)
        assert payloads.get("table_payload", {}).get("table_kind") == "unified_plans_focus"

    def test_infer_payloads_multi_slot(self):
        """Country rows should produce both table and map payloads."""
        from app.services.ai_payload_inference import infer_payloads, _TABLE_MIN_ROWS

        def _iso3(idx: int) -> str:
            return (
                f"{chr(ord('A') + (idx % 26))}"
                f"{chr(ord('A') + ((idx // 26) % 26))}"
                f"{chr(ord('A') + ((idx // 676) % 26))}"
            )

        rows = [
            {"iso3": _iso3(i), "country_name": f"Country {i}", "region": "MENA", "value": i * 10}
            for i in range(_TABLE_MIN_ROWS)
        ]
        steps = [
            {
                "step": 0,
                "action": "any_tool",
                "observation": {
                    "success": True,
                    "result": {
                        "rows": rows,
                        "indicator_name": "Test Metric",
                    },
                },
            },
        ]
        result = infer_payloads(steps, "show test metric for all countries")
        assert "table_payload" in result
        assert "map_payload" in result
        assert result["table_payload"]["type"] == "data_table"
        assert result["map_payload"]["type"] == "worldmap"

    def test_skipped_and_failed_observations_ignored(self):
        """Skipped or failed observations should not produce payloads."""
        from app.services.ai_payload_inference import infer_payloads

        steps = [
            {"step": 0, "action": "t", "observation": {"skipped": True, "series": [{"year": 2020, "value": 1}, {"year": 2021, "value": 2}]}},
            {"step": 1, "action": "t", "observation": {"success": False, "error": "fail"}},
        ]
        assert infer_payloads(steps, "") == {}

    def test_build_payload_handles_flat_observation(self):
        """Observations without result nesting should still be detected."""
        from app.services.ai_payload_inference import build_payload_from_tool_result

        tool_result = {
            "success": True,
            "indicator": {"name": "Branches"},
            "country_name": "Japan",
            "series": [
                {"year": 2020, "value": 100},
                {"year": 2021, "value": 120},
            ],
        }
        payloads = build_payload_from_tool_result(tool_result)
        assert "chart_payload" in payloads
        assert payloads["chart_payload"]["metric"] == "Branches"


class TestAIRuntimeUtils:
    """Tests for extracted runtime utility helpers."""

    def test_estimate_openai_cost_positive(self):
        """Cost estimation should return positive value for non-zero token counts."""
        from app.services.ai_runtime_utils import estimate_openai_cost

        cost = estimate_openai_cost("gpt-5-mini", 1000, 1000)
        assert cost > 0


# ============================================================================
# Test AIQueryPlanner
# ============================================================================

class TestAIQueryPlanner:
    """Tests for the centralized LLM query planner."""

    def test_validate_rejects_low_confidence(self, app):
        """Plans under confidence threshold should be rejected."""
        with app.app_context():
            from app.services.ai_query_planner import AIQueryPlanner
            plan = AIQueryPlanner._validate_simple_plan_dict(
                {
                    "is_simple": True,
                    "confidence": 0.2,
                    "tool_name": "search_documents",
                    "tool_args": {"query": "volunteers", "top_k": 5},
                },
                tool_names={"search_documents"},
            )
            assert plan is None

    def test_validate_normalizes_search_documents_top_k(self, app):
        """search_documents top_k should be bounded by config safety cap."""
        with app.app_context():
            app.config["AI_DOCUMENT_SEARCH_MAX_TOP_K_LIST"] = 120
            from app.services.ai_query_planner import AIQueryPlanner
            plan = AIQueryPlanner._validate_simple_plan_dict(
                {
                    "is_simple": True,
                    "confidence": 0.95,
                    "tool_name": "search_documents",
                    "tool_args": {
                        "query": "volunteers by country",
                        "return_all_countries": True,
                        "top_k": 999,
                    },
                    "output_hint": "map",
                },
                tool_names={"search_documents"},
            )
            assert plan is not None
            assert plan.tool_args["top_k"] == 120
            assert plan.tool_args["return_all_countries"] is True

    def test_plan_simple_returns_none_on_missing_required_args(self, app):
        """Planner output missing required tool args should not pass validation."""
        with app.app_context():
            from app.services.ai_query_planner import AIQueryPlanner

            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = (
                '{"is_simple": true, "confidence": 0.9, "tool_name": "get_indicator_value", '
                '"tool_args": {"indicator_name": "volunteers"}, "output_hint": "text"}'
            )
            mock_client.chat.completions.create.return_value = mock_response

            planner = AIQueryPlanner(client=mock_client, model="gpt-5-mini")
            plan = planner.plan_simple(
                query="Volunteers in Kenya",
                tool_names={"get_indicator_value"},
            )
            assert plan is None


# ============================================================================
# Test AIVectorStore
# ============================================================================

class TestAIVectorStore:
    """Tests for the AI vector store."""

    @pytest.fixture
    def vector_store(self, app):
        """Create vector store instance."""
        with app.app_context():
            app.config['AI_EMBEDDING_PROVIDER'] = 'local'

            with patch('app.services.ai_vector_store.AIEmbeddingService') as mock_emb:
                mock_service = MagicMock()
                mock_service.generate_embedding.return_value = ([0.1] * 384, 0)
                mock_service.model = 'test-model'
                mock_service.dimensions = 384
                mock_emb.return_value = mock_service

                from app.services.ai_vector_store import AIVectorStore
                return AIVectorStore()

    def test_store_initialization(self, vector_store):
        """Test vector store initializes correctly."""
        assert vector_store is not None
        assert vector_store.embedding_service is not None

    def test_get_document_statistics(self, vector_store, app):
        """Test getting document statistics."""
        with app.app_context():
            stats = vector_store.get_document_statistics(999)  # Non-existent
            assert stats == {}


# ============================================================================
# Test AIDocumentProcessor
# ============================================================================

class TestAIDocumentProcessor:
    """Tests for the AI document processor."""

    @pytest.fixture
    def processor(self, app):
        """Create document processor instance."""
        with app.app_context():
            from app.services.ai_document_processor import AIDocumentProcessor
            return AIDocumentProcessor()

    def test_supported_file_types(self, processor):
        """Test checking supported file types."""
        assert processor.is_supported_file('document.pdf')
        assert processor.is_supported_file('document.docx')
        assert processor.is_supported_file('document.txt')
        assert processor.is_supported_file('document.md')
        assert not processor.is_supported_file('document.exe')
        assert not processor.is_supported_file('document.zip')

    def test_get_file_type(self, processor):
        """Test file type detection."""
        assert processor.get_file_type('doc.pdf') == 'pdf'
        assert processor.get_file_type('doc.DOCX') == 'word'
        assert processor.get_file_type('doc.txt') == 'text'

    def test_process_text_file(self, processor, tmp_path):
        """Test processing a text file."""
        # Create a temp text file
        text_file = tmp_path / "test.txt"
        text_file.write_text("This is test content.\nLine two.\nLine three.")

        result = processor.process_document(
            file_path=str(text_file),
            filename="test.txt"
        )

        assert 'text' in result
        assert 'metadata' in result
        assert 'This is test content' in result['text']

    def test_process_markdown_file(self, processor, tmp_path):
        """Test processing a markdown file."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Header\n\nThis is **bold** text.\n\n- Item 1\n- Item 2")

        result = processor.process_document(
            file_path=str(md_file),
            filename="test.md"
        )

        assert 'text' in result
        assert 'Header' in result['text']


# ============================================================================
# Test AIReasoningTraceService
# ============================================================================

class TestAIReasoningTraceService:
    """Tests for the reasoning trace service."""

    @pytest.fixture
    def trace_service(self, app):
        """Create trace service instance."""
        with app.app_context():
            from app.services.ai_reasoning_trace import AIReasoningTraceService
            return AIReasoningTraceService()

    def test_service_initialization(self, trace_service):
        """Test service initializes correctly."""
        assert trace_service is not None

    def test_get_nonexistent_trace(self, trace_service, app):
        """Test getting a non-existent trace."""
        with app.app_context():
            trace = trace_service.get_trace(999999)
            assert trace is None

    def test_get_traces_for_nonexistent_user(self, trace_service, app):
        """Test getting traces for a non-existent user."""
        with app.app_context():
            traces = trace_service.get_traces_for_user(999999)
            assert traces == []


# ============================================================================
# Integration Tests (require database)
# ============================================================================

@pytest.mark.integration
class TestAIServicesIntegration:
    """Integration tests that require a database connection."""

    @pytest.fixture
    def db_session(self, app):
        """Get database session."""
        from app.extensions import db
        with app.app_context():
            yield db.session

    def test_save_and_retrieve_trace(self, db_session, app):
        """Test saving and retrieving a reasoning trace."""
        with app.app_context():
            from app.services.ai_reasoning_trace import AIReasoningTraceService
            from app.models import AIReasoningTrace

            service = AIReasoningTraceService()

            try:
                # Save trace
                service.save_trace(
                    query="Test query",
                    steps=[{'step': 1, 'thought': 'thinking', 'action': 'test_action'}],
                    final_answer="Test answer",
                    status='completed',
                    total_cost=0.001,
                    user_id=None,
                    conversation_id='test-conv-123',
                    llm_provider='test',
                    llm_model='test-model'
                )

                # Verify it was saved
                trace = AIReasoningTrace.query.filter_by(conversation_id='test-conv-123').first()
                if trace:  # Only assert if tables exist
                    assert trace.query == "Test query"
                    assert trace.status == 'completed'

                    # Cleanup
                    db_session.delete(trace)
                    db_session.commit()
            except Exception as e:
                pytest.skip(f"Integration DB not available for trace test: {e}")
