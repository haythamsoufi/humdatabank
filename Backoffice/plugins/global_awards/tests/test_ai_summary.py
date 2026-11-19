"""AI summaries for the presentation and A4 report. The model is faked; nothing leaves the process."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from plugins.global_awards.ai import summary as ai

pytestmark = pytest.mark.unit


def _analysis():
    return {
        "ready": True,
        "meta": {"award_label": "Sep 2026 – Sep 2027", "goal": "Reach people", "region": "", "cycle": ""},
        "kpis": [{"label": "Countries", "value": "2", "meta": "MARC country projects"}],
        "cycles": [{"slot": "Y1Q1", "kind": "quarter", "country_due": "2026-12-01", "pending": 1,
                    "progress": 0, "submitted": 1, "approved": 0, "total": 2}],
        "sections": [{"key": "goal", "name": "Goal", "statement": "", "indicators": 2, "with_data": 1}],
        "indicators": [
            {"code": "1", "label": "People reached", "section": "Goal", "unit": "people",
             "countries": 2, "target": 1000.0, "actual": 400.0, "countries_reported": 1},
            {"code": "2", "label": "Volunteers", "section": "Goal", "unit": "",
             "countries": 2, "target": None, "actual": None, "countries_reported": 0},
        ],
        "countries": [
            {"country": "Kenya", "region": "Africa", "latest_slot": "Y1Q1", "latest_status": "submitted",
             "in_scope": 2, "reported": 1, "cycles_submitted": 1, "cycles_total": 1},
            {"country": "Chad", "region": "Africa", "latest_slot": "Y1Q1", "latest_status": "pending",
             "in_scope": 2, "reported": 0, "cycles_submitted": 0, "cycles_total": 1},
        ],
    }


def _client(content: str):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    client.calls = calls
    return client


def test_payload_only_holds_requested_sections():
    payload = ai.build_payload(_analysis(), ["countries"])
    assert list(payload) == ["countries"]
    assert payload["countries"]["countries_total"] == 2
    assert payload["countries"]["latest_report_status_counts"] == {"submitted": 1, "pending": 1}


def test_payload_puts_lines_with_data_first_and_caps_rows():
    analysis = _analysis()
    analysis["indicators"] = [
        {"code": str(n), "label": f"Line {n}", "section": "Goal", "unit": "", "countries": 1,
         "target": None, "actual": None, "countries_reported": 0}
        for n in range(ai.MAX_INDICATORS + 10)
    ] + [{"code": "x", "label": "Has data", "section": "Goal", "unit": "", "countries": 1,
          "target": 5.0, "actual": 2.0, "countries_reported": 1}]
    block = ai.build_payload(analysis, ["logframe"])["logframe"]
    assert block["indicators_total"] == ai.MAX_INDICATORS + 11
    assert len(block["indicators"]) == ai.MAX_INDICATORS
    assert block["indicators"][0]["indicator"] == "Has data"


def test_parse_response_clips_and_drops_unknown_sections():
    raw = json.dumps({"sections": {
        "overview": {"headline": "H" * 500, "summary": "Two countries.", "findings": ["- a", "b", "c", "d", "e", "f"],
                     "attention": "one gap", "next_steps": []},
        "other": {"summary": "ignored"},
        "logframe": {"summary": "", "findings": []},
    }})
    result = ai.parse_response(raw, ["overview", "logframe"])
    assert list(result) == ["overview"]
    row = result["overview"]
    assert len(row["headline"]) <= ai.MAX_HEADLINE
    assert row["findings"] == ["a", "b", "c", "d"]
    assert row["attention"] == ["one gap"]


def test_parse_response_accepts_fenced_and_unwrapped_json():
    raw = '```json\n{"overview": {"summary": "Fine.", "findings": ["x"]}}\n```'
    assert ai.parse_response(raw, ["overview"])["overview"]["summary"] == "Fine."
    assert ai.parse_response("not json", ["overview"]) == {}


def test_generate_sends_data_and_instruction_once_for_all_sections():
    client = _client(json.dumps({"sections": {
        "overview": {"headline": "On track", "summary": "One of two reported.", "findings": ["1 of 2"]},
        "countries": {"headline": "Chad late", "summary": "Chad has not started.", "findings": ["Chad pending"]},
    }}))
    result = ai.generate_summaries(
        _analysis(), ["overview", "countries"], language="fr", client=client, model="gpt-4o-mini"
    )
    assert set(result) == {"overview", "countries"}
    assert len(client.calls) == 1
    user_message = client.calls[0]["messages"][1]["content"]
    assert "'fr'" in user_message and "Kenya" in user_message and "People reached" not in user_message


def test_generate_makes_no_call_without_sections():
    client = _client("{}")
    with pytest.raises(ai.SummaryUnavailable):
        ai.generate_summaries(_analysis(), [], client=client, model="gpt-4o-mini")
    assert client.calls == []


def test_generate_reports_provider_failure_and_empty_output():
    def boom(**_kwargs):
        raise RuntimeError("secret detail")

    failing = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=boom)))
    with pytest.raises(ai.SummaryUnavailable) as error:
        ai.generate_summaries(_analysis(), ["overview"], client=failing, model="gpt-4o-mini")
    assert "secret detail" not in str(error.value)

    with pytest.raises(ai.SummaryUnavailable):
        ai.generate_summaries(_analysis(), ["overview"], client=_client("{}"), model="gpt-4o-mini")
