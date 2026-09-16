"""Unit tests for AIChatIntegration._process_with_agent (app/services/ai/chat/integration.py).

Focus: form_builder_result must survive every result-status branch (success, timeout
with/without a partial answer, generic failure with a partial answer). This module had
zero direct test coverage before.

Regression covered here: extract_form_builder_result_from_steps() (in ai/tools/_utils.py)
scans `steps` for the latest *successful* write regardless of the run's overall status —
so a create/edit that committed on an earlier iteration before a later timeout must not be
silently dropped by _process_with_agent's metadata-building branches. One such branch
("timeout, no partial answer") previously omitted the field entirely.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.ai.chat.integration import AIChatIntegration


@pytest.fixture
def integration(app):
    """AIChatIntegration with a mocked agent (skips real executor construction)."""
    with app.app_context():
        app.config["AI_AGENT_ENABLED"] = True
        svc = AIChatIntegration()
        svc.agent = MagicMock()
        svc.agent.model = "gpt-5"
        svc.agent.provider = "openai"
        yield svc


FB_RESULT = {
    "action": "edit_form_template",
    "template_id": 42,
    "version_id": 7,
    "edit_url": "/admin/forms/42/edit?version=7",
    "undo_structure": {"sections": []},
    "redo_structure": {"sections": []},
}


class TestProcessWithAgentFormBuilderResult:
    def test_success_forwards_form_builder_result(self, integration, app):
        integration.agent.execute.return_value = {
            "success": True,
            "answer": "Added the phone number field.",
            "steps": [{"action": "edit_form_template", "observation": {"success": True}}],
            "status": "completed",
            "form_builder_result": FB_RESULT,
        }
        with app.app_context():
            _text, _model, _calls, metadata = integration._process_with_agent(
                message="add a phone field",
                conversation_history=None,
                user_context={},
                language="en",
            )
        assert metadata["form_builder_result"] == FB_RESULT

    def test_timeout_with_partial_answer_forwards_form_builder_result(self, integration, app):
        """Timeout after a write already committed: partial answer describes what
        happened, and the UI still needs edit_url/undo_structure to reflect it."""
        integration.agent.execute.return_value = {
            "success": False,
            "status": "timeout",
            "answer": "I added the phone number field, but ran out of time for the rest.",
            "steps": [{"action": "edit_form_template", "observation": {"success": True}}],
            "form_builder_result": FB_RESULT,
        }
        with app.app_context():
            text, _model, _calls, metadata = integration._process_with_agent(
                message="add a phone field and three other things",
                conversation_history=None,
                user_context={},
                language="en",
            )
        assert text
        assert metadata["status"] == "timeout_partial"
        assert metadata["form_builder_result"] == FB_RESULT

    def test_timeout_without_partial_answer_still_forwards_form_builder_result(
        self, integration, app
    ):
        """Regression: even when there's no usable partial-answer text at all, a write
        that committed before the timeout must still surface edit_url/undo_structure to
        the client instead of a bare 'took too long' message with no trace of the edit."""
        integration.agent.execute.return_value = {
            "success": False,
            "status": "timeout",
            "answer": "",
            "steps": [{"action": "create_form_template", "observation": {"success": True}}],
            "form_builder_result": FB_RESULT,
        }
        with app.app_context():
            text, _model, _calls, metadata = integration._process_with_agent(
                message="build me an intake form",
                conversation_history=None,
                user_context={},
                language="en",
            )
        assert text  # generic timeout message
        assert metadata["status"] == "timeout"
        assert metadata["form_builder_result"] == FB_RESULT

    def test_generic_failure_with_partial_answer_forwards_form_builder_result(
        self, integration, app
    ):
        integration.agent.execute.return_value = {
            "success": False,
            "status": "max_tools_exceeded",
            "error": "Max tool calls exceeded (25)",
            "answer": "I created the template but hit the tool-call limit.",
            "steps": [{"action": "create_form_template", "observation": {"success": True}}],
            "form_builder_result": FB_RESULT,
        }
        with app.app_context():
            text, _model, _calls, metadata = integration._process_with_agent(
                message="build me a huge intake form",
                conversation_history=None,
                user_context={},
                language="en",
            )
        assert text
        assert metadata["status"] == "max_tools_exceeded"
        assert metadata["form_builder_result"] == FB_RESULT

    def test_cancelled_with_partial_answer_forwards_form_builder_result(self, integration, app):
        integration.agent.execute.return_value = {
            "success": False,
            "status": "cancelled",
            "answer": "I created the template before you cancelled.",
            "steps": [{"action": "create_form_template", "observation": {"success": True}}],
            "form_builder_result": FB_RESULT,
        }
        with app.app_context():
            text, _model, _calls, metadata = integration._process_with_agent(
                message="build me an intake form",
                conversation_history=None,
                user_context={},
                language="en",
            )
        assert text == "I created the template before you cancelled."
        assert metadata["status"] == "cancelled"
        assert metadata["form_builder_result"] == FB_RESULT

    def test_cancelled_without_partial_answer_still_forwards_form_builder_result(
        self, integration, app
    ):
        integration.agent.execute.return_value = {
            "success": False,
            "status": "cancelled",
            "answer": "",
            "steps": [{"action": "create_form_template", "observation": {"success": True}}],
            "form_builder_result": FB_RESULT,
        }
        with app.app_context():
            text, _model, _calls, metadata = integration._process_with_agent(
                message="build me an intake form",
                conversation_history=None,
                user_context={},
                language="en",
            )
        assert text  # generic "cancelled" message, never empty
        assert metadata["status"] == "cancelled"
        assert metadata["form_builder_result"] == FB_RESULT

    def test_cancelled_without_partial_answer_does_not_fall_back_to_direct_llm(
        self, integration, app
    ):
        """Regression: the generic (non-timeout, non-cancelled) `else` branch falls back
        to a full direct-LLM call when there's no partial answer and status != 'llm_error'.
        'cancelled' must be handled in its own branch *before* that fallback — otherwise a
        user-initiated stop would silently trigger another expensive round-trip the user
        never asked for."""
        integration.agent.execute.return_value = {
            "success": False,
            "status": "cancelled",
            "answer": "",
            "steps": [],
        }
        with app.app_context():
            with patch.object(integration, "_process_with_direct_llm") as mock_direct_llm:
                integration._process_with_agent(
                    message="build me an intake form",
                    conversation_history=None,
                    user_context={},
                    language="en",
                )
            mock_direct_llm.assert_not_called()

    def test_success_without_form_builder_result_omits_it_cleanly(self, integration, app):
        """Sanity counterpart: a plain databank query has no form_builder_result and
        must not fabricate one."""
        integration.agent.execute.return_value = {
            "success": True,
            "answer": "Kenya has 1500 volunteers.",
            "steps": [{"action": "get_indicator_value", "observation": {"success": True}}],
            "status": "completed",
        }
        with app.app_context():
            _text, _model, _calls, metadata = integration._process_with_agent(
                message="How many volunteers in Kenya?",
                conversation_history=None,
                user_context={},
                language="en",
            )
        assert metadata.get("form_builder_result") is None
