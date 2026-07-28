"""Unit tests for services.ai_tools — pure utility functions (no database, no LLM).

Covers:
  - ToolExecutionError
  - json_sanitize
  - truncate_json_value
  - split_tool_kw_for_call
  - tool_wrapper decorator
  - apply_document_source_filters
  - resolve_source_config (outside request context)
  - rewrite_document_search_query
  - infer_country_identifier_from_query (ISO3 and preposition patterns)
"""
import json
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# ToolExecutionError
# ---------------------------------------------------------------------------

class TestToolExecutionError:
    def test_is_exception_subclass(self):
        from app.services.ai.tools import ToolExecutionError
        assert issubclass(ToolExecutionError, Exception)

    def test_message_preserved(self):
        from app.services.ai.tools import ToolExecutionError
        err = ToolExecutionError("tool failed: bad input")
        assert "bad input" in str(err)

    def test_can_be_raised_and_caught(self):
        from app.services.ai.tools import ToolExecutionError
        with pytest.raises(ToolExecutionError):
            raise ToolExecutionError("oops")


# ---------------------------------------------------------------------------
# json_sanitize
# ---------------------------------------------------------------------------

class TestJsonSanitize:
    def _fn(self, v):
        from app.services.ai.tools import json_sanitize
        return json_sanitize(v)

    def test_dict_roundtrip(self):
        assert self._fn({"a": 1}) == {"a": 1}

    def test_list_roundtrip(self):
        assert self._fn([1, 2, 3]) == [1, 2, 3]

    def test_string_roundtrip(self):
        assert self._fn("hello") == "hello"

    def test_none_roundtrip(self):
        assert self._fn(None) is None

    def test_non_serialisable_becomes_string(self):
        import datetime
        result = self._fn(datetime.date(2024, 1, 1))
        assert isinstance(result, str)

    def test_nested_non_serialisable(self):
        import datetime
        result = self._fn({"ts": datetime.datetime(2024, 6, 1)})
        assert isinstance(result["ts"], str)

    def test_empty_dict(self):
        assert self._fn({}) == {}


# ---------------------------------------------------------------------------
# truncate_json_value
# ---------------------------------------------------------------------------

class TestTruncateJsonValue:
    def _fn(self, value, max_chars=None):
        from app.services.ai.tools import truncate_json_value
        if max_chars is None:
            return truncate_json_value(value, max_chars=200_000)
        return truncate_json_value(value, max_chars=max_chars)

    def test_small_payload_returned_unchanged(self):
        data = {"key": "value"}
        assert self._fn(data) == data

    def test_oversized_payload_truncated(self, app):
        from app.services.ai.tools import truncate_json_value
        large = {"data": "x" * 10_000}
        with app.app_context():
            app.config["AI_TOOL_LOG_MAX_CHARS"] = 100
            result = truncate_json_value(large)
        assert isinstance(result, dict)
        assert result.get("truncated") is True
        assert "preview" in result
        assert "original_length" in result

    def test_exact_limit_not_truncated(self):
        small = "hi"
        result = self._fn(small, max_chars=10_000)
        assert result == "hi"

    def test_min_cap_enforced(self):
        # max_chars < 4000 should be clamped to 4000
        from app.services.ai.tools import truncate_json_value
        result = truncate_json_value({"x": "y"}, max_chars=1)
        # Should not error; payload is tiny so no truncation
        assert result == {"x": "y"}

    def test_list_payload_small(self):
        assert self._fn([1, 2, 3]) == [1, 2, 3]


# ---------------------------------------------------------------------------
# split_tool_kw_for_call
# ---------------------------------------------------------------------------

class TestSplitToolKwForCall:
    def _fn(self, func, kwargs):
        from app.services.ai.tools import split_tool_kw_for_call
        return split_tool_kw_for_call(func, kwargs)

    def test_callback_stripped_when_not_accepted(self):
        def my_tool(query: str): ...
        call_kw, log_kw = self._fn(my_tool, {"query": "q", "_progress_callback": lambda: None})
        assert "_progress_callback" not in call_kw
        assert "_progress_callback" not in log_kw

    def test_callback_kept_when_accepted_via_var_kwargs(self):
        def my_tool(query: str, **kwargs): ...
        cb = lambda: None
        call_kw, _ = self._fn(my_tool, {"query": "q", "_progress_callback": cb})
        assert "_progress_callback" in call_kw

    def test_callback_kept_when_explicit_param(self):
        def my_tool(query: str, _progress_callback=None): ...
        cb = lambda: None
        call_kw, _ = self._fn(my_tool, {"query": "q", "_progress_callback": cb})
        assert "_progress_callback" in call_kw

    def test_no_callback_in_input_unchanged(self):
        def my_tool(x: int): ...
        call_kw, log_kw = self._fn(my_tool, {"x": 5})
        assert call_kw == {"x": 5}

    def test_log_kwargs_never_include_callback(self):
        def my_tool(q: str, **kw): ...
        _, log_kw = self._fn(my_tool, {"q": "hi", "_progress_callback": lambda: None})
        assert "_progress_callback" not in log_kw


# ---------------------------------------------------------------------------
# tool_wrapper decorator
# ---------------------------------------------------------------------------

class TestToolWrapper:
    def test_wraps_return_value(self):
        from app.services.ai.tools import tool_wrapper
        @tool_wrapper
        def add(x, y):
            return x + y
        assert add(2, 3) == 5

    def test_non_tool_error_re_raised_as_tool_execution_error(self):
        from app.services.ai.tools import tool_wrapper, ToolExecutionError
        @tool_wrapper
        def failing():
            raise ValueError("oops")
        with pytest.raises(ToolExecutionError, match="oops"):
            failing()

    def test_tool_execution_error_passes_through(self):
        from app.services.ai.tools import tool_wrapper, ToolExecutionError
        @tool_wrapper
        def already_tool_error():
            raise ToolExecutionError("already wrapped")
        with pytest.raises(ToolExecutionError, match="already wrapped"):
            already_tool_error()

    def test_preserves_function_name(self):
        from app.services.ai.tools import tool_wrapper
        @tool_wrapper
        def my_named_tool(x): return x
        assert my_named_tool.__name__ == "my_named_tool"

    def test_callback_stripped_automatically(self):
        from app.services.ai.tools import tool_wrapper
        @tool_wrapper
        def strict_tool(x: int): return x * 2
        result = strict_tool(x=5, _progress_callback=lambda: None)
        assert result == 10


# ---------------------------------------------------------------------------
# apply_document_source_filters
# ---------------------------------------------------------------------------

class TestApplyDocumentSourceFilters:
    def _fn(self, filters, sources_cfg, query=None):
        from app.services.ai.tools import apply_document_source_filters
        return apply_document_source_filters(filters, sources_cfg, query=query)

    def test_system_only_sets_is_api_import_false(self):
        filters = {}
        result = self._fn(filters, {"system_documents": True, "upr_documents": False})
        assert result is True
        assert filters["is_api_import"] is False

    def test_upr_only_sets_is_api_import_true(self):
        filters = {}
        result = self._fn(filters, {"system_documents": False, "upr_documents": True})
        assert result is True
        assert filters["is_api_import"] is True

    def test_both_disabled_returns_false(self):
        filters = {}
        result = self._fn(filters, {"system_documents": False, "upr_documents": False})
        assert result is False

    def test_both_enabled_no_query_no_filter_set(self):
        filters = {}
        result = self._fn(filters, {"system_documents": True, "upr_documents": True})
        assert result is True
        assert "is_api_import" not in filters

    def test_both_enabled_upr_query_narrows_to_upr(self):
        filters = {}
        result = self._fn(
            filters,
            {"system_documents": True, "upr_documents": True},
            query="Show me the UPR plan for Nepal",
        )
        assert result is True
        assert filters.get("is_api_import") is True

    def test_non_dict_sources_cfg_returns_true(self):
        filters = {}
        result = self._fn(filters, None)
        assert result is True

    def test_empty_sources_cfg_both_disabled(self):
        filters = {}
        result = self._fn(filters, {})
        assert result is False


# ---------------------------------------------------------------------------
# resolve_source_config — outside request context
# ---------------------------------------------------------------------------

class TestResolveSourceConfig:
    def test_returns_none_outside_request_context(self):
        from app.services.ai.tools import resolve_source_config
        result = resolve_source_config()
        assert result is None


# ---------------------------------------------------------------------------
# rewrite_document_search_query
# ---------------------------------------------------------------------------

class TestRewriteDocumentSearchQuery:
    def _fn(self, query):
        from app.services.ai.tools import rewrite_document_search_query
        return rewrite_document_search_query(query)

    def test_empty_query_returns_empty_strings(self):
        result = self._fn("")
        assert result == {"vector_query": "", "keyword_query": ""}

    def test_simple_query_vector_equals_keyword(self):
        result = self._fn("number of volunteers")
        assert result["vector_query"] == result["keyword_query"]

    def test_returns_dict_with_required_keys(self):
        result = self._fn("annual report 2024")
        assert "vector_query" in result
        assert "keyword_query" in result

    def test_boolean_operators_stripped_from_vector(self):
        result = self._fn('"volunteers" OR "staff"')
        assert "OR" not in result["vector_query"]

    def test_quoted_phrase_kept_in_keyword(self):
        result = self._fn('"first aid" training')
        assert "first aid" in result["keyword_query"]

    def test_none_query_handled(self):
        result = self._fn(None)  # type: ignore[arg-type]
        assert result["vector_query"] == ""


# ---------------------------------------------------------------------------
# infer_country_identifier_from_query
# ---------------------------------------------------------------------------

class TestInferCountryIdentifierFromQuery:
    def _fn(self, query):
        from app.services.ai.tools import infer_country_identifier_from_query
        return infer_country_identifier_from_query(query)

    def test_empty_returns_none(self):
        assert self._fn("") is None

    def test_iso3_extracted(self):
        result = self._fn("Volunteers data for SYR 2023")
        assert result == "SYR"

    def test_preposition_in_extracts_country_name(self):
        result = self._fn("What are the KPIs in Afghanistan?")
        assert result is not None
        assert "Afghanistan" in result

    def test_preposition_for_extracts_country_name(self):
        result = self._fn("Show me data for Nepal")
        assert result is not None
        assert "Nepal" in result

    def test_no_country_returns_none(self):
        result = self._fn("general statistics on health programmes")
        assert result is None
