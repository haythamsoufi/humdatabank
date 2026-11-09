"""Unit tests for chat debug helpers (no live LLM calls)."""

import json
from pathlib import Path

import pytest

from app.services.ai.runtime.chat_debug_runner import (
    html_to_text,
    load_scenario,
    summarize_trace_steps,
)


def test_html_to_text_strips_tags_and_entities():
    html = "<p>Syria&#39;s volunteers rose to <strong>14,098</strong>.</p>"
    assert html_to_text(html) == "Syria's volunteers rose to 14,098."


def test_load_scenario_shapes(tmp_path: Path):
    p1 = tmp_path / "list.json"
    p1.write_text(json.dumps(["a", "b"]), encoding="utf-8")
    assert load_scenario(str(p1)) == ["a", "b"]

    p2 = tmp_path / "obj.json"
    p2.write_text(json.dumps({"prompts": ["x", "y"]}), encoding="utf-8")
    assert load_scenario(str(p2)) == ["x", "y"]

    p3 = tmp_path / "turns.json"
    p3.write_text(json.dumps({"turns": [{"message": "m1"}, {"prompt": "m2"}]}), encoding="utf-8")
    assert load_scenario(str(p3)) == ["m1", "m2"]

    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        load_scenario(str(bad))


def test_summarize_trace_steps_marks_failures():
    steps = [
        {
            "action": "search_documents",
            "action_input": {"query": "volunteers"},
            "observation": {"success": False, "error": "Tool execution failed.", "error_type": "VectorStoreError"},
        },
        {"action": "finish", "observation": "done"},
    ]
    summary = summarize_trace_steps(steps)
    assert summary["tools_used"] == ["search_documents"]
    assert summary["failed_tools"][0]["error_type"] == "VectorStoreError"
    assert "FAILED" in summary["tool_digest"]


def test_bundled_syria_scenario_loads():
    root = Path(__file__).resolve().parents[3]  # Backoffice/
    path = root / "scripts" / "ai" / "scenarios" / "syria-volunteers.json"
    assert path.is_file()
    prompts = load_scenario(str(path))
    assert len(prompts) == 3
    assert "Syria" in prompts[0]
