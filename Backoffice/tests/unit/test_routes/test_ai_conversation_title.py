"""Tests for app.routes.ai._build_initial_conversation_title.

The form-builder AI panel appends extracted document/image text to the
outgoing message behind a "--- Imported questionnaire text from "<file>" ---"
or "--- Pasted form image "<file>" ---" marker (see
_appendAttachmentBlockToMessage in form-builder-ai.js) so the LLM can see the
attachment contents. That block must never leak into the conversation title,
which used to be built by naively truncating the first 80 characters of the
raw message.
"""

import pytest

from app.routes.ai import _build_initial_conversation_title

pytestmark = [pytest.mark.unit]


class TestBuildInitialConversationTitle:
    def test_empty_message_returns_new_chat(self):
        assert _build_initial_conversation_title("") == "New chat"
        assert _build_initial_conversation_title(None) == "New chat"
        assert _build_initial_conversation_title("   ") == "New chat"

    def test_short_message_returned_verbatim(self):
        assert _build_initial_conversation_title("Add a WASH section") == "Add a WASH section"

    def test_long_message_truncated_to_80_chars(self):
        text = "x" * 100
        title = _build_initial_conversation_title(text)
        assert title == ("x" * 80) + "…"

    def test_strips_imported_questionnaire_text_marker(self):
        message = (
            'Build a form template from this attached questionnaire.\n\n'
            '--- Imported questionnaire text from "NSD investment monitoring.pdf" ---\n'
            'Detected section headings:\n- Project Information\n\n'
            '[Page 1]\nNSD investment monitoring\nReporting period: 17/03/2025'
        )
        title = _build_initial_conversation_title(message)
        assert title == "Build a form template from this attached questionnaire."
        assert "Imported questionnaire" not in title
        assert "NSD investment monitoring.pdf" not in title

    def test_strips_pasted_form_image_marker(self):
        message = (
            'Build a form template from this pasted image.\n\n'
            '--- Pasted form image "screenshot.png" ---\n'
            'OCR text goes here...'
        )
        title = _build_initial_conversation_title(message)
        assert title == "Build a form template from this pasted image."

    def test_strips_marker_even_when_prefix_alone_exceeds_80_chars(self):
        # Regression: previously the naive 80-char truncation could land mid-marker,
        # e.g. 'Build a form template…--- Imported questionna…'. Confirm a long-ish
        # prefix is still truncated cleanly on its own terms, without any marker text.
        prefix = "Build a form template from this attached questionnaire and use the same field order. "
        message = prefix + '\n\n--- Imported questionnaire text from "doc.pdf" ---\ncontent'
        title = _build_initial_conversation_title(message)
        assert "---" not in title
        assert "Imported questionnaire" not in title
        assert title.startswith("Build a form template")

    def test_unrelated_triple_dash_text_is_not_stripped(self):
        # Only the specific form-builder attachment labels trigger stripping —
        # a generic "---" divider in a normal user message is left alone.
        message = "Here is my plan:\n\n--- this is just a divider ---\nDetails follow."
        assert _build_initial_conversation_title(message) == message
