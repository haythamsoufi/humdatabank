"""Unit tests for app/services/ai/runtime/tool_observation.py.

Focus: create/edit/translate_form_template/discard_template_draft results carry a full
before/after serialization of the *entire* template under undo_structure/redo_structure
(see FormTemplateAIService.apply_edits et al.) purely so the SSE client can offer
Undo/Redo. Before this fix, compact_tool_observation_for_llm() had no tool-specific
handling for these tools, so the raw, uncompacted snapshots (doubled — one before, one
after) were resent to OpenAI as the tool's "observation" on every turn, for every
form-builder write, growing the conversation with data the LLM never uses. This module
otherwise had zero direct test coverage.
"""

import json

import pytest

from app.services.ai.runtime.tool_observation import (
    compact_tool_observation_for_llm,
    strip_form_builder_snapshots_for_trace,
)

pytestmark = [pytest.mark.unit]


def _make_full_structure(item_count: int = 40) -> dict:
    """A template structure large enough to matter, shaped like
    FormTemplateAIService.get_full_structure()'s return value."""
    return {
        "template_id": 42,
        "version_id": 7,
        "version_number": 3,
        "version_status": "draft",
        "name": "Intake form",
        "sections": [
            {
                "id": 1,
                "name": "Section A",
                "items": [
                    {
                        "id": i,
                        "label": f"Question {i}",
                        "label_translations": {"fr": f"Question {i} FR", "es": f"Question {i} ES"},
                        "type": "text",
                    }
                    for i in range(item_count)
                ],
            }
        ],
    }


class TestFormTemplateWriteToolCompaction:
    def test_strips_undo_redo_snapshots_for_create_form_template(self, app):
        with app.app_context():
            tool_result = {
                "success": True,
                "result": {
                    "template_id": 42,
                    "version_id": 7,
                    "name": "Intake form",
                    "edit_url": "/admin/forms/42/edit?version=7",
                    "changes": ["created template", "added 3 sections"],
                    "warnings": [],
                    "undo_structure": _make_full_structure(),
                    "redo_structure": _make_full_structure(),
                },
            }
            observation = compact_tool_observation_for_llm(
                tool_name="create_form_template", tool_result=tool_result
            )

        parsed = json.loads(observation)
        assert parsed["result"]["template_id"] == 42
        assert parsed["result"]["edit_url"] == "/admin/forms/42/edit?version=7"
        assert parsed["result"]["changes"] == ["created template", "added 3 sections"]
        # Snapshots replaced with a short marker, not the full nested structure.
        assert "Question 0" not in observation
        assert "Question 39" not in observation
        assert isinstance(parsed["result"]["undo_structure"], str)
        assert isinstance(parsed["result"]["redo_structure"], str)
        assert "omitted" in parsed["result"]["undo_structure"]

    @pytest.mark.parametrize(
        "tool_name",
        ["create_form_template", "edit_form_template", "translate_form_template", "discard_template_draft"],
    )
    def test_strips_snapshots_for_every_write_tool(self, app, tool_name):
        with app.app_context():
            tool_result = {
                "success": True,
                "result": {
                    "template_id": 1,
                    "undo_structure": _make_full_structure(),
                    "redo_structure": _make_full_structure(),
                },
            }
            observation = compact_tool_observation_for_llm(tool_name=tool_name, tool_result=tool_result)
        assert "Question 0" not in observation

    def test_does_not_mutate_original_tool_result(self, app):
        """Regression: the compacted copy must never alias the original dict — that
        original object is what extract_form_builder_result_from_steps() and the SSE
        form_builder_result payload read directly from `steps[i]['observation']`
        (see executor.py), so mutating it in place would silently break Undo/Redo for
        the *current* request even though this function only touches the LLM-bound copy.
        """
        full_before = _make_full_structure()
        full_after = _make_full_structure()
        tool_result = {
            "success": True,
            "result": {
                "template_id": 1,
                "undo_structure": full_before,
                "redo_structure": full_after,
            },
        }
        with app.app_context():
            compact_tool_observation_for_llm(tool_name="edit_form_template", tool_result=tool_result)

        # Original dict passed in (and its nested snapshot objects) must be untouched.
        assert tool_result["result"]["undo_structure"] is full_before
        assert tool_result["result"]["redo_structure"] is full_after
        assert full_before["sections"][0]["items"][0]["label"] == "Question 0"

    def test_missing_snapshots_falls_through_unaffected(self, app):
        """A write-tool error result with no undo_structure/redo_structure keys at all
        (e.g. validation failed before any snapshot was taken) must still round-trip via
        the generic path rather than erroring."""
        with app.app_context():
            tool_result = {"success": False, "error": "Template not found."}
            observation = compact_tool_observation_for_llm(
                tool_name="edit_form_template", tool_result=tool_result
            )
        parsed = json.loads(observation)
        assert parsed["success"] is False
        assert parsed["error"] == "Template not found."

    def test_other_tools_are_not_affected(self, app):
        """Sanity: a non-form-template tool with fields that happen to be named
        undo_structure/redo_structure (unlikely, but the branch is name-gated) is not
        touched by this form-template-specific path."""
        with app.app_context():
            tool_result = {"success": True, "result": {"undo_structure": "keep me"}}
            observation = compact_tool_observation_for_llm(
                tool_name="get_indicator_value", tool_result=tool_result
            )
        parsed = json.loads(observation)
        assert parsed["result"]["undo_structure"] == "keep me"

    def test_still_over_limit_after_stripping_falls_back_to_generic_compaction(self, app):
        """When changes/warnings lists are themselves huge, stripping the two snapshot
        keys may not be enough — must fall through to the generic compaction instead of
        returning an oversized string."""
        with app.app_context():
            tool_result = {
                "success": True,
                "result": {
                    "template_id": 1,
                    "undo_structure": _make_full_structure(),
                    "redo_structure": _make_full_structure(),
                    "changes": [f"change #{i} with some descriptive text padding" for i in range(3000)],
                },
            }
            observation = compact_tool_observation_for_llm(
                tool_name="edit_form_template", tool_result=tool_result, max_chars=2000
            )
        # Original (snapshots + 3000 verbose change lines) would be well over 100k chars;
        # confirm real compaction happened without pinning the exact re-escaped byte count.
        assert len(observation) < 10000
        # Must still be valid JSON (generic fallback never emits a broken/partial document).
        json.loads(observation)


class TestStripFormBuilderSnapshotsForTrace:
    """Covers the AIReasoningTrace.steps persistence path (separate sink from the
    LLM-observation compaction above — see strip_form_builder_snapshots_for_trace's
    docstring for why the trace table needs its own, independent trim)."""

    def _make_step(self, action: str = "edit_form_template") -> dict:
        return {
            "step": 1,
            "action": action,
            "action_input": {"template_id": 1},
            "observation": {
                "success": True,
                "result": {
                    "template_id": 1,
                    "edit_url": "/x",
                    "undo_structure": _make_full_structure(),
                    "redo_structure": _make_full_structure(),
                },
            },
            "timestamp": "2024-01-01T00:00:00",
        }

    def test_strips_snapshots_from_matching_step(self):
        steps = [self._make_step()]
        trimmed = strip_form_builder_snapshots_for_trace(steps)
        obs_result = trimmed[0]["observation"]["result"]
        assert obs_result["edit_url"] == "/x"  # non-snapshot fields preserved
        assert "omitted" in obs_result["undo_structure"]
        assert "omitted" in obs_result["redo_structure"]

    def test_does_not_mutate_input(self):
        """The original list/dicts (shared with result['steps'] and
        form_builder_result) must never be touched — only a parallel copy is built."""
        steps = [self._make_step()]
        original_undo = steps[0]["observation"]["result"]["undo_structure"]
        strip_form_builder_snapshots_for_trace(steps)
        assert steps[0]["observation"]["result"]["undo_structure"] is original_undo
        assert steps[0]["observation"]["result"]["undo_structure"]["sections"][0]["items"][0]["label"] == "Question 0"

    def test_non_form_builder_steps_untouched_and_not_copied(self):
        """Fast path: a run with no form-template write step returns the *same* list
        object (no-op), not just an equal one — avoids needless copying for the common
        case (databank/document queries)."""
        steps = [
            {"step": 1, "action": "get_indicator_value", "observation": {"success": True, "result": {}}},
            {"step": 2, "action": "finish", "observation": None},
        ]
        assert strip_form_builder_snapshots_for_trace(steps) is steps

    def test_mixed_steps_only_form_builder_step_is_copied(self):
        other_step = {"step": 1, "action": "get_indicator_value", "observation": {"success": True, "result": {}}}
        fb_step = self._make_step()
        trimmed = strip_form_builder_snapshots_for_trace([other_step, fb_step])
        assert trimmed[0] is other_step  # untouched steps are passed through by reference
        assert trimmed[1] is not fb_step  # the matching step got a new wrapper dict
        assert "omitted" in trimmed[1]["observation"]["result"]["undo_structure"]

    def test_non_list_input_returned_unchanged(self):
        assert strip_form_builder_snapshots_for_trace(None) is None
        assert strip_form_builder_snapshots_for_trace("not a list") == "not a list"

    def test_step_without_snapshots_untouched(self):
        """A failed write (e.g. validation error before any snapshot was taken) has no
        undo_structure/redo_structure keys — must pass through as-is."""
        steps = [
            {
                "step": 1,
                "action": "edit_form_template",
                "observation": {"success": False, "error": "not found"},
            }
        ]
        assert strip_form_builder_snapshots_for_trace(steps) == steps
