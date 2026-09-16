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

    def test_first_turn_forces_create_when_no_template_and_permitted(self, app_ctx):
        """Form-builder panel, no template open yet, user can create -> force create_form_template."""
        from unittest.mock import patch
        from app.services.ai.policies.agent_routing import AgentRoutingPolicy

        with patch(
            "app.services.ai.tools._utils.resolve_form_builder_context",
            return_value={"enabled": True, "template_id": None},
        ), patch(
            "app.services.ai.tools.registry._form_template_allowed_tools",
            return_value={"create_form_template"},
        ):
            choice = AgentRoutingPolicy.first_turn_tool_choice(query="Build me an intake form")

        assert choice == {"type": "function", "function": {"name": "create_form_template"}}

    def test_first_turn_falls_back_to_auto_when_create_not_permitted(self, app_ctx):
        """Regression: a view/edit-only user opening the panel with no template selected must
        not get a tool_choice naming create_form_template, since registry.py's RBAC-filtered
        tools array for that turn won't include it either -> OpenAI would 400 on a tool_choice
        naming a function absent from tools."""
        from unittest.mock import patch
        from app.services.ai.policies.agent_routing import AgentRoutingPolicy

        with patch(
            "app.services.ai.tools._utils.resolve_form_builder_context",
            return_value={"enabled": True, "template_id": None},
        ), patch(
            "app.services.ai.tools.registry._form_template_allowed_tools",
            return_value={"get_form_template_full_structure"},
        ):
            choice = AgentRoutingPolicy.first_turn_tool_choice(query="Build me an intake form")

        assert choice == "auto"

    def test_first_turn_required_when_template_open(self, app_ctx):
        """Form-builder panel with a template already open forces some tool call (not a
        specific one), so RBAC-filtered tool lists never risk naming an unlisted function."""
        from unittest.mock import patch
        from app.services.ai.policies.agent_routing import AgentRoutingPolicy

        with patch(
            "app.services.ai.tools._utils.resolve_form_builder_context",
            return_value={"enabled": True, "template_id": 12},
        ):
            choice = AgentRoutingPolicy.first_turn_tool_choice(query="Add a phone number field")

        assert choice == "required"

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
