"""Tests for turn digest, tool-failure disclosure, verifier number filtering, series notes."""

from app.services.ai.agent.executor import (
    _doc_search_failed_without_success,
    _ensure_tool_failure_disclosed,
)
from app.services.ai.data.form_retrieval import _timeseries_data_quality_notes
from app.services.ai.quality.answer_verifier import _extract_checkable_numbers
from app.services.ai.runtime.turn_digest import build_turn_digest

FAILED_SEARCH = {
    "action": "search_documents",
    "action_input": {"country_identifier": "Syria", "query": "volunteers Syria"},
    "observation": {"success": False, "error": "Tool execution failed.", "error_type": "VectorStoreError"},
}
OK_SEARCH = {
    "action": "search_documents",
    "action_input": {"query": "volunteers"},
    "observation": {
        "success": True,
        "result": {"success": True, "result": [{"document_title": "Annual Report 2024", "page_number": 9}]},
    },
}
TIMESERIES = {
    "action": "get_indicator_timeseries",
    "action_input": {"country_identifier": "Syria", "indicator_name": "Volunteers"},
    "observation": {
        "success": True,
        "result": {
            "country_display_name": "Syrian Arab Republic",
            "indicator": {"display_name": "Number of people volunteering."},
            "series": [
                {"period_name": "2016", "value": 7673, "data_status": "saved"},
                {"period_name": "2017", "value": 9248, "data_status": "saved"},
            ],
        },
    },
}


def test_failed_search_detected_and_disclosed():
    steps = [FAILED_SEARCH, FAILED_SEARCH]
    assert _doc_search_failed_without_success(steps)
    out = _ensure_tool_failure_disclosed("Plausible reasons: recruitment drives.", steps)
    assert out.startswith("**Note:** I couldn't search the uploaded documents")
    assert "Plausible reasons" in out


def test_no_disclosure_when_answer_already_admits_failure_or_search_ok():
    steps = [FAILED_SEARCH]
    ans = "I couldn't search the documents just now, so this is general reasoning."
    assert _ensure_tool_failure_disclosed(ans, steps) == ans
    assert not _doc_search_failed_without_success([FAILED_SEARCH, OK_SEARCH])
    assert _ensure_tool_failure_disclosed("x", [OK_SEARCH]) == "x"
    assert _ensure_tool_failure_disclosed("x", []) == "x"


def test_digest_marks_failures_and_keeps_values():
    d = build_turn_digest([FAILED_SEARCH, TIMESERIES, {"action": "finish", "observation": "done"}])
    assert "search_documents" in d and "FAILED" in d and "VectorStoreError" in d
    assert "2016=7673 (saved)" in d and "2017=9248" in d
    assert "finish" not in d.replace("FAILED", "")
    assert build_turn_digest([{"action": "finish"}]) == ""


def test_digest_lists_retrieved_documents():
    d = build_turn_digest([OK_SEARCH])
    assert "Annual Report 2024 p.9" in d


def test_verifier_ignores_urls_years_pages_codes():
    answer = (
        "1. [Annual Report - Syrian Arab Republic (2023) - page 2]( /api/ai/documents/711/download)\n"
        "2. UPL_SYRIA_2023 (UPL-2023-MAASY002) - page 17\n"
        "Volunteers rose to 14,098 in 2026 and 75% of branches."
    )
    nums = _extract_checkable_numbers(answer)
    assert "14,098" in nums and "75%" in nums
    assert not any(n in ("711", "711/", "2023", "2024", "2", "17") for n in nums)


def test_series_quality_notes():
    series = [
        {"year": 2023, "period_name": "2023", "value": 9788.0, "data_status": "saved"},
        {"year": 2024, "period_name": "Jan-Jun 2024", "value": 9788.0, "data_status": "saved"},
        {"year": 2025, "period_name": "2025", "value": 12878.0, "data_status": "saved"},
    ]
    notes = " ".join(_timeseries_data_quality_notes(series))
    assert "carried forward" in notes
    assert "Jan-Jun 2024" in notes and "not a plain calendar year" in notes
    assert "saved/draft" in notes
    assert "+32%" in notes
