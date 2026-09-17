"""Unit tests for app.utils.ai_utils.sanitize_page_context.

Focused on the formBuilder.enabled handling: the sanitizer must treat
page_context as untrusted input, but must not silently override an explicit
enabled=False into True. Several downstream consumers (chat/engine.py,
policies/prompt_policy.py, planning/query_rewriter.py, agent/executor.py) all
gate RBAC-sensitive form-template tool exposure and prompt behavior on
formBuilder.get("enabled"), so a sanitizer that always forces True would
defeat a caller's explicit opt-out.
"""

from app.utils.ai_utils import is_form_builder_assistant_context, sanitize_page_context


class TestSanitizePageContextBasics:
    def test_non_dict_input_returns_empty_dict(self):
        assert sanitize_page_context(None) == {}
        assert sanitize_page_context("not a dict") == {}
        assert sanitize_page_context([1, 2, 3]) == {}

    def test_drops_current_url_to_avoid_leaking_tokens(self):
        out = sanitize_page_context(
            {"currentUrl": "https://example.org/x?token=SECRET", "currentPage": "/x"}
        )
        assert "currentUrl" not in out
        assert out["currentPage"] == "/x"

    def test_caps_long_strings(self):
        out = sanitize_page_context({"pageTitle": "x" * 500})
        assert len(out["pageTitle"]) == 201  # 200 chars + trailing ellipsis marker
        assert out["pageTitle"].endswith("…")

    def test_page_data_only_keeps_known_keys(self):
        out = sanitize_page_context(
            {
                "pageData": {
                    "pageType": "form_builder_edit",
                    "country": "Kenya",
                    "secretToken": "should-not-appear",
                }
            }
        )
        assert out["pageData"] == {"pageType": "form_builder_edit", "country": "Kenya"}


class TestSanitizePageContextFormBuilderEnabled:
    def test_missing_form_builder_key_omits_output(self):
        out = sanitize_page_context({"currentPage": "/forms"})
        assert "formBuilder" not in out

    def test_enabled_true_is_preserved(self):
        out = sanitize_page_context({"formBuilder": {"enabled": True, "template_id": 5}})
        assert out["formBuilder"] == {"enabled": True, "template_id": 5}

    def test_enabled_absent_defaults_true_matching_current_callers(self):
        # Every current caller (transport.js) always sends enabled explicitly, but the
        # shape should still behave sensibly if a future caller omits the key.
        out = sanitize_page_context({"formBuilder": {"template_id": 5}})
        assert out["formBuilder"]["enabled"] is True

    def test_explicit_enabled_false_is_not_overridden_to_true(self):
        """Regression: sanitize_page_context used to hardcode enabled=True whenever the
        formBuilder key was present, silently ignoring an explicit enabled=False from the
        caller. That would re-activate RBAC-sensitive form-template tool gating downstream
        even when the caller explicitly said the panel was not active."""
        out = sanitize_page_context({"formBuilder": {"enabled": False, "template_id": 5}})
        assert out["formBuilder"]["enabled"] is False

    def test_enabled_false_still_keeps_typed_ids(self):
        out = sanitize_page_context(
            {"formBuilder": {"enabled": False, "template_id": "7", "version_id": "3"}}
        )
        assert out["formBuilder"] == {"enabled": False, "template_id": 7, "version_id": 3}

    def test_non_numeric_ids_are_dropped_not_raised(self):
        out = sanitize_page_context(
            {"formBuilder": {"enabled": True, "template_id": "not-a-number"}}
        )
        assert out["formBuilder"] == {"enabled": True}

    def test_form_builder_non_dict_is_ignored(self):
        out = sanitize_page_context({"formBuilder": "enabled"})
        assert "formBuilder" not in out


class TestIsFormBuilderAssistantContext:
    """is_form_builder_assistant_context() is the single shared predicate every
    form-builder exemption (PII scrubbing in AIChatEngine, the DLP mask-and-send
    gate in evaluate_ai_message) agrees on — see its docstring."""

    def test_true_when_enabled(self):
        assert is_form_builder_assistant_context({"formBuilder": {"enabled": True}}) is True

    def test_false_when_key_absent(self):
        assert is_form_builder_assistant_context({"currentPage": "/forms"}) is False

    def test_false_when_explicitly_disabled(self):
        assert is_form_builder_assistant_context({"formBuilder": {"enabled": False}}) is False

    def test_false_for_non_dict_page_context(self):
        assert is_form_builder_assistant_context(None) is False
        assert is_form_builder_assistant_context("not a dict") is False

    def test_false_when_form_builder_value_is_not_a_dict(self):
        assert is_form_builder_assistant_context({"formBuilder": "enabled"}) is False

    def test_works_with_already_sanitized_page_context(self):
        """Accepts the exact shape sanitize_page_context() produces."""
        sanitized = sanitize_page_context({"formBuilder": {"enabled": True, "template_id": 5}})
        assert is_form_builder_assistant_context(sanitized) is True
