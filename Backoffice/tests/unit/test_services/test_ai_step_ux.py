"""Unit tests for app.services.ai.runtime.step_ux.

Focus: step_display_message() must give the five form-builder assistant tools
(get_form_template_full_structure, create_form_template, edit_form_template,
translate_form_template, discard_template_draft) their own user-facing wording
instead of silently falling through to the generic "Checking data…" — that
fallback is meant for databank/document tools the agent doesn't recognize, and
reads oddly for a template create/edit action next to "Working on your form…"
(the executor's form-builder fast-path-skip step — see AgentExecutor.execute).
"""

from app.services.ai.runtime.step_ux import (
    ASSISTANT_NARRATION_MARKER,
    clean_tool_narration,
    emit_tool_start_step,
    format_tool_result_summary,
    plan_step_message,
    step_display_message,
)


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
        assert plan_step_message(None) == "Deciding what to look up…"

    def test_plan_present_returns_fast_path_message(self):
        class _FakePlan:
            tool_name = "get_indicator_value"
            tool_args = {}

        assert plan_step_message(_FakePlan()) == "I know how to answer this — fetching data…"


class TestCleanToolNarration:
    def test_plain_sentence_is_kept(self):
        text = "I'll pull Syria's yearly volunteer counts to see the trend."
        assert clean_tool_narration(text) == text

    def test_empty_and_non_string(self):
        assert clean_tool_narration(None) == ""
        assert clean_tool_narration("   ") == ""

    def test_structured_output_is_rejected(self):
        assert clean_tool_narration('{"query": "volunteers"}') == ""
        assert clean_tool_narration("```json\n{}\n```") == ""

    def test_markdown_is_stripped_and_whitespace_collapsed(self):
        assert clean_tool_narration("**Checking**  the\n`Indicator Bank` now") == "Checking the Indicator Bank now"

    def test_long_text_is_truncated(self):
        out = clean_tool_narration("word " * 200)
        assert len(out) <= 241
        assert out.endswith("…")


class TestEmitToolStartStep:
    def _collector(self):
        calls = []

        def cb(message=None, detail=None):
            calls.append((message, detail))

        return calls, cb

    def test_thought_is_narration_then_action_is_progress_step(self):
        calls, cb = self._collector()
        args = {"country_identifier": "Syria", "indicator_name": "Volunteers"}
        opened = emit_tool_start_step(cb, "get_indicator_timeseries", args, thought="I'll pull the yearly volunteer counts.")
        assert opened is True
        assert calls == [
            ("I'll pull the yearly volunteer counts.", ASSISTANT_NARRATION_MARKER),
            ("Reading Volunteers over time for Syria…", None),
        ]

    def test_follow_up_tool_in_same_turn_is_detail_only(self):
        calls, cb = self._collector()
        opened = emit_tool_start_step(cb, "get_country_information", {"country_identifier": "Syria"}, thought_open=True)
        assert opened is True
        assert calls == [(None, "Looking up information for Syria…")]

    def test_without_thought_keeps_one_step_per_tool(self):
        calls, cb = self._collector()
        opened = emit_tool_start_step(cb, "get_country_information", {"country_identifier": "Syria"})
        assert opened is False
        assert calls[0][0] == "Looking up information for Syria…"


class TestTimeseriesResultSummary:
    def test_reports_year_range(self):
        result = {
            "success": True,
            "result": {"series": [{"year": 2019, "value": 1}, {"year": 2021, "value": 2}, {"year": 2023, "value": 3}]},
        }
        summary = format_tool_result_summary("get_indicator_timeseries", result)
        assert summary == "Found 3 yearly values (2019–2023) · reviewing…"

    def test_empty_series(self):
        result = {"success": True, "result": {"series": [], "count": 0}}
        assert format_tool_result_summary("get_indicator_timeseries", result) == "No data available for this selection."
