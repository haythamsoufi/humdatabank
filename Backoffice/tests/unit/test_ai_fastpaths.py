"""Unit tests for services.ai_fastpaths (P0 – currently 0% coverage)."""
import pytest
from unittest.mock import MagicMock


class TestAiFastpathsImport:
    """Verify the package re-exports the expected entry point."""

    def test_module_importable(self):
        import app.services.ai.chat.fastpaths as pkg
        assert pkg is not None

    def test_run_unified_plans_focus_fastpath_re_exported(self):
        from app.services.ai.chat.fastpaths import run_unified_plans_focus_fastpath
        assert callable(run_unified_plans_focus_fastpath)

    def test_all_list_contains_entrypoint(self):
        import app.services.ai.chat.fastpaths as pkg
        assert "run_unified_plans_focus_fastpath" in pkg.__all__

    def test_entrypoint_is_same_object_as_source(self):
        from app.services.ai.chat.fastpaths import run_unified_plans_focus_fastpath as exported
        from app.services.upr.focus_area_analysis import run_unified_plans_focus_fastpath as source
        assert exported is source


class TestRunUnifiedPlansFocusFastpath:
    """Tests for run_unified_plans_focus_fastpath (real function, mocked deps)."""

    _MATCHING_QUERY = (
        "review all unified plans for cash and cea — identify key gaps and patterns"
    )

    def _kwargs(self, registry=None):
        return {
            "tools_registry": registry or MagicMock(),
            "client": MagicMock(),
            "model": "test-model",
            "provider": "openai",
        }

    def test_returns_none_for_non_matching_query(self, app):
        from app.services.ai.chat.fastpaths import run_unified_plans_focus_fastpath

        with app.app_context():
            result = run_unified_plans_focus_fastpath(
                query="number of volunteers in Nepal",
                **self._kwargs(),
            )
        assert result is None

    def test_returns_none_when_required_tool_missing(self, app):
        from app.services.ai.chat.fastpaths import run_unified_plans_focus_fastpath

        registry = MagicMock()
        registry.get_tool_definitions_openai.return_value = [
            {"function": {"name": "other_tool"}},
        ]
        with app.app_context():
            result = run_unified_plans_focus_fastpath(
                query=self._MATCHING_QUERY,
                **self._kwargs(registry=registry),
            )
        assert result is None
        registry.execute_tool.assert_not_called()

    def test_executes_tool_and_returns_answer_on_success(self, app):
        from app.services.ai.chat.fastpaths import run_unified_plans_focus_fastpath

        registry = MagicMock()
        registry.get_tool_definitions_openai.return_value = [
            {"function": {"name": "analyze_unified_plans_focus_areas"}},
        ]
        registry.execute_tool.return_value = {
            "success": True,
            "result": {
                "plans": [{"country": "Nepal"}],
                "countries_grouped": [],
                "most_recent_plan_per_country": [],
                "counts_by_area": {"cash": 1},
                "plans_analyzed": 1,
                "total_plans": 1,
            },
        }
        with app.app_context():
            result = run_unified_plans_focus_fastpath(
                query=self._MATCHING_QUERY,
                **self._kwargs(registry=registry),
            )
        assert result is not None
        assert isinstance(result, dict)
        registry.execute_tool.assert_called_once()
