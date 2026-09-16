"""Unit tests for pure module-level text helpers in app/services/ai/chat/engine.py.

These small helpers previously had zero direct test coverage; AIChatEngine.run()
itself is a large orchestration method (agent routing, RAG, streaming, OpenAI
calls) that isn't practical to unit test directly, but the text-transform
helpers it delegates to are pure functions and are covered here in isolation.
"""
import pytest

from app.services.ai.chat.engine import (
    _scrub_message_for_llm,
    _strip_form_builder_boilerplate,
    _strip_markdown_sources_section,
)

pytestmark = [pytest.mark.unit]


class TestScrubMessageForLlm:
    """Covers the PII-scrub vs. form-builder faithful-import conflict.

    Generic chat messages still get PII-redacted before reaching a third-party
    LLM. Form-builder assistant messages skip that redaction because users
    routinely paste verbatim questionnaire text (e.g. sample contact fields)
    that must be faithfully reproduced in the generated template; DLP already
    gates genuinely sensitive pastes upstream in the route layer.
    """

    def test_redacts_email_for_regular_chat(self, app):
        with app.app_context():
            result = _scrub_message_for_llm(
                "Contact me at jane@example.com", form_builder_assistant=False
            )
        assert "jane@example.com" not in result
        assert "[REDACTED_EMAIL]" in result

    def test_redacts_phone_for_regular_chat(self, app):
        with app.app_context():
            result = _scrub_message_for_llm(
                "Call +1 555 123 4567 for support", form_builder_assistant=False
            )
        assert "555 123 4567" not in result
        assert "[REDACTED_PHONE]" in result

    def test_skips_redaction_for_form_builder_assistant(self, app):
        pasted = "Contact field example: jane@example.com, phone +1 555 123 4567"
        with app.app_context():
            result = _scrub_message_for_llm(pasted, form_builder_assistant=True)
        assert result == pasted

    def test_strips_surrounding_whitespace(self, app):
        with app.app_context():
            assert _scrub_message_for_llm("  hello  ", form_builder_assistant=True) == "hello"
            assert _scrub_message_for_llm("  hello  ", form_builder_assistant=False) == "hello"

    def test_handles_none_and_empty_message(self, app):
        with app.app_context():
            assert _scrub_message_for_llm(None, form_builder_assistant=False) == ""
            assert _scrub_message_for_llm(None, form_builder_assistant=True) == ""
            assert _scrub_message_for_llm("", form_builder_assistant=True) == ""


class TestStripMarkdownSourcesSection:
    def test_removes_trailing_sources_block(self):
        text = "Some answer text.\n\n## Sources\n- Doc A, p.1\n- Doc B, p.2"
        assert _strip_markdown_sources_section(text) == "Some answer text."

    def test_no_sources_block_returns_unchanged(self):
        text = "Some answer text with no sources heading."
        assert _strip_markdown_sources_section(text) == text

    def test_empty_and_none_text_returned_as_is(self):
        assert _strip_markdown_sources_section("") == ""
        assert _strip_markdown_sources_section(None) is None


class TestStripFormBuilderBoilerplate:
    def test_removes_no_warnings_lines_regardless_of_edit_mode(self):
        text = "Created the template.\nWarnings: none.\nDone."
        result = _strip_form_builder_boilerplate(text, edit_mode=False)
        assert "warnings" not in result.lower()
        assert "Created the template." in result
        assert "Done." in result

    def test_edit_mode_removes_review_and_deploy_boilerplate(self):
        text = (
            "Updated the section.\n"
            "All changes are applied to the draft.\n"
            "Please review the draft and deploy when ready.\n"
            "[Open the draft in the form builder](/admin/templates/edit/5)\n"
        )
        result = _strip_form_builder_boilerplate(text, edit_mode=True)
        assert result == "Updated the section."

    def test_non_edit_mode_keeps_review_deploy_text(self):
        """The review/deploy boilerplate only applies to edit-mode answers —
        e.g. a freshly created (non-draft-edit) template answer keeps it."""
        text = "Created it.\nPlease review the draft and deploy when ready."
        result = _strip_form_builder_boilerplate(text, edit_mode=False)
        assert "Please review the draft and deploy when ready." in result

    def test_collapses_resulting_blank_lines(self):
        text = "Line one.\nWarnings: none.\nNo warnings were produced.\nLine two."
        result = _strip_form_builder_boilerplate(text, edit_mode=False)
        assert "\n\n\n" not in result
        assert result == "Line one.\n\nLine two."

    def test_empty_text_returned_as_is(self):
        assert _strip_form_builder_boilerplate("", edit_mode=True) == ""
