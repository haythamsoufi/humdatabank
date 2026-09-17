"""Unit tests for app.services.ai.runtime.step_ux.

Focus: step_display_message() must give the five form-builder assistant tools
(get_form_template_full_structure, create_form_template, edit_form_template,
translate_form_template, discard_template_draft) their own user-facing wording
instead of silently falling through to the generic "Checking data…" — that
fallback is meant for databank/document tools the agent doesn't recognize, and
reads oddly for a template create/edit action next to "Working on your form…"
(the executor's form-builder fast-path-skip step — see AgentExecutor.execute).
"""

from app.services.ai.runtime.step_ux import plan_step_message, step_display_message


class TestStepDisplayMessageFormBuilderTools:
    def test_get_form_template_full_structure(self):
        msg = step_display_message("get_form_template_full_structure", {"template_id": 12})
        assert msg == "Reading the form structure…"

    def test_create_form_template(self):
        msg = step_display_message("create_form_template", {"name": "New Form", "sections": []})
        assert msg == "Creating your form template…"

    def test_edit_form_template(self):
        msg = step_display_message("edit_form_template", {"template_id": 12, "operations": []})
        assert msg == "Applying your changes to the form…"

    def test_translate_form_template_lists_languages(self):
        msg = step_display_message(
            "translate_form_template", {"template_id": 12, "languages": ["fr", "es", "ar"]}
        )
        assert msg == "Translating the form into fr, es, ar…"

    def test_translate_form_template_without_languages_falls_back(self):
        msg = step_display_message("translate_form_template", {"template_id": 12})
        assert msg == "Translating the form…"

    def test_discard_template_draft(self):
        msg = step_display_message("discard_template_draft", {"template_id": 12})
        assert msg == "Discarding the draft…"

    def test_unknown_tool_still_falls_back_to_checking_data(self):
        """Regression guard: the new branches must not swallow the generic fallback
        used by every databank/document tool this module doesn't special-case."""
        assert step_display_message("some_unrecognized_tool", {}) == "Checking data…"


class TestPlanStepMessage:
    def test_none_plan_returns_full_agent_message(self):
        # This is the generic (non form-builder) "no fast-path plan" message — the
        # form-builder panel's own executor branch bypasses this function entirely
        # and emits "Working on your form…" directly (see AgentExecutor.execute).
        assert plan_step_message(None) == "This needs multiple steps — starting…"

    def test_plan_present_returns_fast_path_message(self):
        class _FakePlan:
            tool_name = "get_indicator_value"
            tool_args = {}

        assert plan_step_message(_FakePlan()) == "I know how to answer this — fetching data…"
