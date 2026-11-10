"""Tests for structured AI chat sources parsing / synthesis."""

from app.utils.ai_sources_parser import (
    merge_structured_sources,
    parse_labeled_sources,
    render_sources_body_html,
    synthesize_timeseries_source,
)


def test_parse_labeled_sources_title_and_detail():
    answer = """
Some answer text.

## Sources

- title: IFRC Network Databank (indicator: "Number of people volunteering.")
  detail: years 2016–Jan-Jun 2026. Note: all 11 points are saved/draft (not submitted).
- title: Syria UPR 2026
  page: 14
  url: /api/ai/documents/12/download
  detail: "Volunteers reached 14,098."
"""
    items = parse_labeled_sources(answer)
    assert len(items) == 2
    assert items[0]["title"].startswith("IFRC Network Databank")
    assert items[0]["detail"].startswith("years 2016")
    assert items[0]["kind"] in {"other", "databank"}
    assert items[1]["title"] == "Syria UPR 2026"
    assert items[1]["page"] == 14
    assert items[1]["url"] == "/api/ai/documents/12/download"
    assert items[1]["detail"] == "Volunteers reached 14,098."
    assert items[1]["kind"] == "document"


def test_synthesize_timeseries_source_builds_title_detail():
    payload = {
        "success": True,
        "result": {
            "indicator_display_name": "Number of people volunteering.",
            "series": [
                {"x": 2016, "y": 100, "data_status": "saved"},
                {"x": 2024, "y": 200, "data_status": "saved"},
            ],
            "data_quality_notes": ["Large jump between 2023 and 2024."],
        },
    }
    item = synthesize_timeseries_source(payload, org_name="IFRC Network Databank")
    assert item is not None
    assert item["title"] == 'IFRC Network Databank (indicator: "Number of people volunteering.")'
    assert "years 2016–2024" in (item["detail"] or "")
    assert "saved/draft" in (item["detail"] or "").lower()
    assert item["kind"] == "databank"


def test_merge_prefers_tool_synth_over_prose():
    answer = """
Caveat sentence.

## Sources

- title: Should be superseded if same title from tools
  detail: wrong detail
"""
    steps = [
        {
            "action": "get_indicator_timeseries",
            "observation": {
                "success": True,
                "result": {
                    "indicator_display_name": "Number of people volunteering.",
                    "series": [
                        {"x": 2016, "y": 1, "data_status": "saved"},
                        {"x": 2026, "y": 2, "data_status": "saved"},
                    ],
                },
            },
        }
    ]
    items = merge_structured_sources(
        answer=answer,
        steps=steps,
        org_name="IFRC Network Databank",
    )
    assert items
    titles = [i["title"] for i in items]
    assert any("Number of people volunteering" in t for t in titles)
    databank = next(i for i in items if "volunteering" in i["title"])
    assert "years 2016–2026" in (databank["detail"] or "")


def test_render_sources_body_html_has_data_attrs():
    html = render_sources_body_html(
        [
            {
                "title": 'IFRC Network Databank (indicator: "Volunteers")',
                "detail": "years 2016–2024. Note: draft.",
                "kind": "databank",
            }
        ]
    )
    assert "data-source-title=" in html
    assert "data-source-detail=" in html
    assert "data-source-kind=" in html
    assert "chat-response-sources-list" in html


def test_plain_sources_sentence_is_structured():
    """A zero-hit search often writes one sentence under ## Sources, not labeled fields."""
    answer = """
I searched uploaded document titles for "emergency" in Syria.
Result: 0 documents found.

## Sources

Uploaded document titles for Syria contained no "emergency" match.
"""
    items = merge_structured_sources(answer=answer)
    assert len(items) == 1
    assert items[0]["title"].startswith("Uploaded document titles for Syria")
    assert items[0]["kind"] == "other"


def test_numbered_source_lines_are_structured():
    answer = """
## Sources

1. Syria Unified Plan 2024
2. Contingency plan
"""
    items = merge_structured_sources(answer=answer)
    assert [i["title"] for i in items] == ["Syria Unified Plan 2024", "Contingency plan"]


def test_format_sources_html_is_structured_chip_data_only():
    from app.services.ai.providers.formatting import format_ai_response_for_html

    html = format_ai_response_for_html(
        'No emergency documents matched.\n\n## Sources\n\n'
        'Uploaded document titles for Syria contained no "emergency" match.\n'
    )
    assert "data-source-title=" in html
    assert "Uploaded document titles for Syria" in html
    assert "<details" not in html.lower()
    assert "<summary" not in html.lower()


def test_legacy_prose_bullet_still_usable():
    answer = """
## Sources

- IFRC Network Databank (indicator: 'Number of people volunteering.') — years 2011-2024.
"""
    items = merge_structured_sources(answer=answer)
    assert len(items) >= 1
    assert "IFRC Network Databank" in items[0]["title"]
