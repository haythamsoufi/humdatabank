"""Unit tests for form-builder AI tool registration and context gating.

The form template tools must only appear in the OpenAI tool definitions when
the request carries the form-builder panel context (g.ai_form_builder_ctx)
AND the user holds the matching RBAC permissions.
"""

from unittest.mock import patch

import pytest
from flask import g

from app.services.ai_tools import registry as registry_module
from app.services.ai_tools.form_template_specs import (
    FORM_TEMPLATE_TOOL_NAMES,
    FORM_TEMPLATE_TOOL_SPECS,
    FORM_TEMPLATE_WRITE_TOOLS,
)
from app.services.ai_tools.registry import AIToolsRegistry, _form_template_allowed_tools


def _registry_instance():
    """AIToolsRegistry without running __init__ (avoids vector store setup)."""
    return object.__new__(AIToolsRegistry)


def _tool_names(tool_defs):
    return {td.get("function", {}).get("name") for td in tool_defs}


@pytest.mark.unit
class TestFormTemplateToolSpecs:
    def test_spec_names_match_registry_constants(self):
        spec_names = {td["function"]["name"] for td in FORM_TEMPLATE_TOOL_SPECS}
        assert spec_names == set(FORM_TEMPLATE_TOOL_NAMES)
        assert FORM_TEMPLATE_WRITE_TOOLS < FORM_TEMPLATE_TOOL_NAMES

    def test_specs_are_valid_openai_function_definitions(self):
        for td in FORM_TEMPLATE_TOOL_SPECS:
            assert td["type"] == "function"
            fn = td["function"]
            assert fn["name"]
            assert fn["description"]
            params = fn["parameters"]
            assert params["type"] == "object"
            assert isinstance(params.get("properties"), dict)

    def test_registry_has_a_method_for_every_tool(self):
        for name in FORM_TEMPLATE_TOOL_NAMES:
            assert callable(getattr(AIToolsRegistry, name, None)), (
                f"AIToolsRegistry is missing a tool method for '{name}'"
            )


@pytest.mark.unit
class TestFormTemplateToolGating:
    def test_no_context_means_no_tools(self, app):
        with app.test_request_context("/api/ai/v2/chat/stream"):
            # No g.ai_form_builder_ctx set at all.
            assert _form_template_allowed_tools() == set()

    def test_context_without_permissions_means_no_tools(self, app):
        with app.test_request_context("/api/ai/v2/chat/stream"):
            g.ai_form_builder_ctx = {"enabled": True, "template_id": 1}
            with patch.object(
                registry_module,
                "resolve_form_template_permissions",
                return_value={"view": False, "create": False, "edit": False},
            ):
                assert _form_template_allowed_tools() == set()

    def test_view_only_exposes_read_tool(self, app):
        with app.test_request_context("/api/ai/v2/chat/stream"):
            g.ai_form_builder_ctx = {"enabled": True, "template_id": 1}
            with patch.object(
                registry_module,
                "resolve_form_template_permissions",
                return_value={"view": True, "create": False, "edit": False},
            ):
                assert _form_template_allowed_tools() == {"get_form_template_full_structure"}

    def test_full_permissions_expose_all_tools(self, app):
        with app.test_request_context("/api/ai/v2/chat/stream"):
            g.ai_form_builder_ctx = {"enabled": True, "template_id": 1}
            with patch.object(
                registry_module,
                "resolve_form_template_permissions",
                return_value={"view": True, "create": True, "edit": True},
            ):
                assert _form_template_allowed_tools() == set(FORM_TEMPLATE_TOOL_NAMES)

    def test_disabled_context_means_no_tools(self, app):
        with app.test_request_context("/api/ai/v2/chat/stream"):
            g.ai_form_builder_ctx = {"enabled": False}
            with patch.object(
                registry_module,
                "resolve_form_template_permissions",
                return_value={"view": True, "create": True, "edit": True},
            ):
                assert _form_template_allowed_tools() == set()


@pytest.mark.unit
class TestToolDefinitionsExposure:
    def test_definitions_exclude_form_tools_without_context(self, app):
        with app.test_request_context("/api/ai/v2/chat/stream"):
            names = _tool_names(_registry_instance().get_tool_definitions_openai())
            assert names.isdisjoint(FORM_TEMPLATE_TOOL_NAMES)

    def test_definitions_include_form_tools_with_context_and_permissions(self, app):
        with app.test_request_context("/api/ai/v2/chat/stream"):
            g.ai_form_builder_ctx = {"enabled": True, "template_id": 1}
            with patch.object(
                registry_module,
                "resolve_form_template_permissions",
                return_value={"view": True, "create": True, "edit": True},
            ):
                names = _tool_names(_registry_instance().get_tool_definitions_openai())
            assert FORM_TEMPLATE_TOOL_NAMES <= names
            assert "search_indicator_bank" in names
            assert "compare_countries" not in names
            assert "get_workflow_guide" not in names

    def test_definitions_respect_partial_permissions(self, app):
        with app.test_request_context("/api/ai/v2/chat/stream"):
            g.ai_form_builder_ctx = {"enabled": True, "template_id": 1}
            with patch.object(
                registry_module,
                "resolve_form_template_permissions",
                return_value={"view": True, "create": False, "edit": False},
            ):
                names = _tool_names(_registry_instance().get_tool_definitions_openai())
            assert "get_form_template_full_structure" in names
            assert names.isdisjoint(FORM_TEMPLATE_WRITE_TOOLS)

    def test_search_indicator_bank_kept_when_form_builder_active_and_sources_disabled(self, app):
        """The agent must resolve indicator ids while building forms, even when the
        databank source is disabled in the panel."""
        with app.test_request_context("/api/ai/v2/chat/stream"):
            g.ai_form_builder_ctx = {"enabled": True, "template_id": 1}
            g.ai_sources_cfg = {"historical": False, "system_documents": False, "upr_documents": False}
            with patch.object(
                registry_module,
                "resolve_form_template_permissions",
                return_value={"view": True, "create": True, "edit": True},
            ):
                names = _tool_names(_registry_instance().get_tool_definitions_openai())
            assert "search_indicator_bank" in names
            assert "get_indicator_value" not in names
