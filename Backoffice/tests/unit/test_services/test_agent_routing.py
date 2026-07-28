"""Unit tests for AgentRoutingPolicy — central AI routing contract."""

import pytest


@pytest.fixture
def app_ctx(app):
    with app.app_context():
        yield app


class TestAgentRoutingPolicy:
    def test_first_turn_auto_by_default(self, app_ctx):
        from app.services.ai.policies.agent_routing import AgentRoutingPolicy

        assert AgentRoutingPolicy.first_turn_tool_choice(query="How many volunteers in Syria?") == "auto"

    def test_fast_path_enabled_by_default(self, app_ctx):
        from app.services.ai.policies.agent_routing import AgentRoutingPolicy

        app_ctx.config.pop("AI_AGENT_FAST_PATH_ENABLED", None)
        assert AgentRoutingPolicy.fast_path_enabled() is True

    def test_fast_path_disabled_by_config(self, app_ctx):
        from app.services.ai.policies.agent_routing import AgentRoutingPolicy

        app_ctx.config["AI_AGENT_FAST_PATH_ENABLED"] = False
        assert AgentRoutingPolicy.fast_path_enabled() is False

    def test_decide_fast_path_plan_skips_when_disabled(self, app_ctx):
        from app.services.ai.policies.agent_routing import AgentRoutingPolicy

        app_ctx.config["AI_AGENT_FAST_PATH_ENABLED"] = False

        class _StubPlanner:
            def plan_simple(self, **kwargs):
                raise AssertionError("plan_simple must not run when fast path disabled")

        assert AgentRoutingPolicy.decide_fast_path_plan(
            query_planner=_StubPlanner(),
            query="How many volunteers?",
            tool_names={"get_indicator_value"},
        ) is None

    def test_turn_supplement_dashboard_page_context(self, app_ctx):
        from app.services.ai.policies.agent_routing import AgentRoutingPolicy

        supplement = AgentRoutingPolicy.turn_system_prompt_supplement(
            query="Why only one country?",
            conversation_history=[],
            user_context={"page_context": {"pageData": {"pageType": "user_dashboard"}}},
        )
        assert "dashboard" in supplement.lower()
        assert "country" in supplement.lower()

    def test_turn_supplement_databank_only_directive(self, app_ctx):
        from app.services.ai.policies.agent_routing import AgentRoutingPolicy

        supplement = AgentRoutingPolicy.turn_system_prompt_supplement(
            query="Use databank only, not documents",
            conversation_history=[],
            user_context={},
        )
        assert "databank" in supplement.lower()
        assert "do not search documents" in supplement.lower()

    def test_turn_supplement_full_table_request(self, app_ctx):
        from app.services.ai.policies.agent_routing import AgentRoutingPolicy

        supplement = AgentRoutingPolicy.turn_system_prompt_supplement(
            query="Give me a full table of all countries",
            conversation_history=[],
            user_context={},
        )
        assert "markdown table" in supplement.lower()

    def test_should_skip_payload_inference_form_builder_only(self, app_ctx):
        from app.services.ai.policies.agent_routing import AgentRoutingPolicy

        assert AgentRoutingPolicy.should_skip_payload_inference(form_builder_assistant=True) is True
        assert AgentRoutingPolicy.should_skip_payload_inference(form_builder_assistant=False) is False


class TestQueryPlannerExecutionMode:
    def test_validate_rejects_full_agent_mode(self, app_ctx):
        from app.services.ai.planning.query_planner import AIQueryPlanner

        plan = AIQueryPlanner._validate_simple_plan_dict(
            {
                "execution_mode": "full_agent",
                "is_simple": True,
                "tool_name": "search_documents",
                "tool_args": {"query": "volunteers"},
                "confidence": 0.99,
            },
            tool_names={"search_documents"},
        )
        assert plan is None

    def test_validate_accepts_fast_path_with_high_confidence(self, app_ctx):
        from app.services.ai.planning.query_planner import AIQueryPlanner

        app_ctx.config["AI_AGENT_FAST_PATH_MIN_CONFIDENCE"] = 0.85
        plan = AIQueryPlanner._validate_simple_plan_dict(
            {
                "execution_mode": "fast_path",
                "is_simple": True,
                "tool_name": "get_indicator_value",
                "tool_args": {
                    "country_identifier": "Syria",
                    "indicator_name": "volunteers",
                },
                "confidence": 0.9,
            },
            tool_names={"get_indicator_value"},
        )
        assert plan is not None
        assert plan.tool_name == "get_indicator_value"

    def test_validate_rejects_low_confidence_fast_path(self, app_ctx):
        from app.services.ai.planning.query_planner import AIQueryPlanner

        app_ctx.config["AI_AGENT_FAST_PATH_MIN_CONFIDENCE"] = 0.85
        plan = AIQueryPlanner._validate_simple_plan_dict(
            {
                "execution_mode": "fast_path",
                "is_simple": True,
                "tool_name": "get_indicator_value",
                "tool_args": {
                    "country_identifier": "Syria",
                    "indicator_name": "volunteers",
                },
                "confidence": 0.7,
            },
            tool_names={"get_indicator_value"},
        )
        assert plan is None
