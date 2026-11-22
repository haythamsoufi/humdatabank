"""The narrative model may only cite sources we listed, and the page keeps our links."""

from __future__ import annotations

import json

import pytest

from plugins.dref_monitoring.services.prompts import system_prompt, user_prompt
from plugins.dref_monitoring.services.sources import (
    accept_chapter_sources,
    resolve_sources,
    safe_href,
    source_claims,
    stamp_catalog,
)


@pytest.mark.unit
def test_the_prompt_asks_for_a_sources_array_and_hides_links():
    prompt = system_prompt("operational_update", "en")
    assert "source_catalog" in prompt
    assert '"used_for"' in prompt
    assert "Never invent an id" in prompt
    payload = {
        "appeal_code": "MDRZZ001",
        "context": {
            "emergency": {"event_id": 6560, "event_name": "Zedland Floods", "event_start": "2026-04-01"},
            "databank_documents": [
                {
                    "title": "Flash Update 3",
                    "organization": "OCHA",
                    "date": "2026-04-26",
                    "page": 3,
                    "document_id": 12,
                    "source_url": "https://example.org/flash",
                    "excerpt": "Homes were damaged.",
                }
            ],
            "field_reports": [{"id": 15, "number": 8, "title": "Zedland Flood", "report_date": "2026-05-03"}],
        },
    }
    text = user_prompt(payload)
    assert "https://example.org/flash" not in text
    assert "_source_links" not in text
    assert "doc-12" in text and "fr-15" in text
    sent = json.loads(text)
    assert all("url" not in item for item in sent["source_catalog"])
    assert sent["context"]["databank_documents"][0]["ref"] == "doc-12"
    assert "source_url" not in sent["context"]["databank_documents"][0]


@pytest.mark.unit
def test_only_catalog_ids_become_links_and_model_urls_are_ignored():
    payload = {
        "context": {
            "approved_application": {"event_scope": "Flooding in Herat."},
            "databank_documents": [
                {
                    "title": "Flash Update 3",
                    "document_id": 4,
                    "has_file": True,
                    "page": 2,
                    "excerpt": "River levels fell.",
                }
            ],
        }
    }
    catalog = stamp_catalog(payload, 36)
    reply = json.dumps(
        {
            "what_happened": "The river rose.",
            "needs": "",
            "sources": [
                {"id": "operation", "chapter": "what_happened", "used_for": "The appeal code is on the operation."},
                {
                    "id": "doc-4",
                    "chapter": "what_happened",
                    "used_for": "River levels fell.",
                    "url": "javascript:alert(1)",
                    "title": "Invented title",
                },
                {"id": "doc-999", "chapter": "what_happened", "used_for": "Not in the catalog."},
                {"id": "operation", "chapter": "needs", "used_for": "This chapter is empty."},
                {"id": "approved-application", "chapter": "not_a_chapter", "used_for": "No."},
            ],
        }
    )
    rows = resolve_sources(source_claims(reply), catalog, {"what_happened"})
    assert [row["id"] for row in rows] == ["operation", "doc-4"]
    operation, document = rows
    assert operation["url"] == "/dref-monitoring/operations/36"
    assert operation["title"] == "Operation record"
    assert document["url"] == "/api/ai/documents/4/download"
    assert document["title"] == "Flash Update 3"
    assert document["locator"] == "p. 2"
    assert document["used_for"] == "River levels fell."
    assert safe_href("javascript:alert(1)") == ""
    assert safe_href("https://go.ifrc.org/emergencies/6560/details").startswith("https://")


@pytest.mark.unit
def test_a_saved_source_keeps_only_a_link_we_would_render():
    rows = accept_chapter_sources(
        [
            {
                "id": "doc-4",
                "kind": "document",
                "title": "Flash Update 3",
                "url": "javascript:alert(1)",
                "used_for": "River levels fell.",
            },
            {"id": "not an id", "kind": "document", "title": "Nope", "used_for": "x"},
        ],
        "what_happened",
    )
    assert len(rows) == 1
    assert rows[0]["url"] == ""
    assert rows[0]["chapter"] == "what_happened"
    assert accept_chapter_sources(rows, "not_a_chapter") == []
    assert safe_href("/assignment/88") == "/assignment/88"
    assert safe_href("/assignment/88/edit") == ""


@pytest.mark.unit
def test_a_period_links_to_its_assignment_and_the_open_draft_is_not_a_previous_report():
    prompt = system_prompt("operational_update", "en")
    assert "never the draft being written" in prompt
    assert "Do not pack several facts into one sentence" in prompt
    payload = {
        "draft_id": 13,
        "appeal_code": "MDRBD041",
        "total_approved_chf": "494,769",
        "start_date": "2026-09-14",
        "end_date": "2027-03-31",
        "people_targeted": "300,000",
        "monitoring_reports": [
            {
                "id": "mon-4",
                "title": "14 September 2026 to 31 October 2026",
                "date": "2026-10-31",
                "locator": "231 people reached · 32 activities (1 ongoing, 31 planned)",
                "url": "/assignment/88",
                "status": "submitted",
            },
            {"id": "mon-5", "title": "Earlier period", "url": "/assignment/88/edit"},
        ],
        "context": {
            "previous_report": {
                "draft_id": 13,
                "kind": "operational_update",
                "status": "draft",
                "written_on": "2026-11-20",
                "chapters": {"what_happened": "This is the draft being edited."},
            }
        },
    }
    catalog = stamp_catalog(payload, 8)
    by_id = {row["id"]: row for row in catalog}
    assert "previous-report" not in by_id
    assert "previous_report" not in payload["context"]
    assert "draft_id" not in payload
    assert by_id["operation"]["url"] == "/dref-monitoring/operations/8"
    assert by_id["operation"]["title"] == "MDRBD041 operation record"
    assert "CHF 494,769" in by_id["operation"]["locator"]
    assert "300,000 people targeted" in by_id["operation"]["locator"]
    assert by_id["mon-4"]["url"] == "/assignment/88"
    assert by_id["mon-4"]["locator"].startswith("231 people reached")
    assert by_id["mon-5"]["url"] == ""
    assert "url" not in payload["monitoring_reports"][0]
    text = user_prompt(
        {
            "appeal_code": "MDRBD041",
            "monitoring_reports": [
                {
                    "id": "mon-4",
                    "title": "14 September 2026 to 31 October 2026",
                    "locator": "231 people reached",
                    "url": "/assignment/88",
                }
            ],
        }
    )
    assert "/assignment/88" not in text
    assert "mon-4" in text
