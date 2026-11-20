"""What the model is given: the written application, field reports, documents, and the prompt."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.extensions import db
from plugins.dref_monitoring.access import Actor
from plugins.dref_monitoring.constants import SECTION_KEYS
from plugins.dref_monitoring.models import DrefBaseline, DrefDraft, DrefOperation
from plugins.dref_monitoring.services.context import (
    databank_documents,
    field_report_summary,
    field_reports,
    load_context,
)
from plugins.dref_monitoring.services.drafts import build_payload, generate_draft, llm_messages
from plugins.dref_monitoring.services.go_application import (
    NARRATIVE_VERSION,
    application_from_emergency,
)
from plugins.dref_monitoring.services.go_sync import apply_rows, stamp_stored_applications
from plugins.dref_monitoring.services.parsing import plain_text
from plugins.dref_monitoring.services.prompts import chapter_keys
from tests.factories import create_test_country, create_test_user

pytestmark = pytest.mark.db

EMERGENCY = {
    "name": "Zedland: Floods, 2026",
    "summary": "<p>Heavy rain flooded the north.</p>",
    "ifrc_severity_level_display": "Orange",
    "disaster_start_date": "2026-03-28T00:00:00Z",
    "countries": [{"name": "Zedland", "society_name": "Zedland Red Crescent"}],
    "timeline_field_reports": [
        {"id": 11, "report_date": "2026-04-01T00:00:00Z"},
        {"id": 12, "report_date": "2026-04-05T00:00:00Z"},
        {"id": 13, "report_date": "2026-04-09T00:00:00Z"},
        {"id": 14, "report_date": "2026-04-12T00:00:00Z"},
        {"id": 15, "report_date": "2026-04-20T00:00:00Z"},
    ],
    "dref": {
        "event_description": "<p>Rivers burst their banks on 28 March.</p><p>Two bridges fell.</p>",
        "event_scope": "About 18,000 people are affected.",
        "disaster_type_details": {"name": "Flood"},
        "needs_identified": [
            {"title": "shelter_housing_and_settlements", "title_display": "Shelter", "description": "3,000 homes were damaged."}
        ],
        "people_assisted": "The operation targets 2,000 families.",
        "dref_contacts": [{"name": "Private Person", "email": "private@example.org"}],
        "planned_interventions": [
            {
                "title": "health",
                "budget": 8000,
                "person_targeted": 80,
                "description": "Open the clinic",
                "indicators": [{"title": "People reached", "target": 80}],
            }
        ],
        "operational_update_details": {
            "event_description": "Floods continued into April.",
            "summary_of_change": "The timeframe moves to 31 January.",
            "planned_interventions": [
                {
                    "title": "health",
                    "budget": 9000,
                    "person_targeted": 90,
                    "description": "Keep the clinic open",
                    "progress_towards_outcome": "Two clinics opened in Herat.",
                    "indicators": [{"title": "People reached", "target": 90}],
                }
            ],
        },
        "timeline_operational_updates": [
            {"operational_update_number": 1, "summary_of_change": "Scaled up.", "date_of_approval": "2026-05-01"}
        ],
    },
}

FIELD_REPORT = {
    "fr_num": 8,
    "report_date": "2026-05-03T09:53:19Z",
    "title": "Zedland Flood",
    "description": "<p class=\"MsoNormal\">Flash floods hit Herat &amp; Ghor.</p>",
    "num_dead": 16,
    "num_affected": 3570,
    "num_injured": 0,
    "actions_taken": [
        {
            "organization": "NTLS",
            "actions_details": [{"name": "First Aid"}, {"name": "Search & Rescue"}],
            "summary": "",
        }
    ],
    "contacts": [{"name": "Reporter", "email": "reporter@example.org", "phone": "+1"}],
    "user_details": {"username": "someone@ifrc.org", "email": "someone@ifrc.org"},
}


def test_html_becomes_plain_paragraphs_and_a_clip_ends_on_a_sentence():
    text = plain_text("<p>One &amp; two.</p><p>Three.</p>")
    assert text == "One & two.\n\nThree."
    assert plain_text("Line<br>break") == "Line\nbreak"
    long = "First sentence here. " * 40
    clipped = plain_text(long, 100)
    assert clipped.endswith(".")
    assert len(clipped) <= 100
    assert plain_text(None) == ""


def test_the_emergency_page_keeps_the_written_application_and_no_contacts():
    application = application_from_emergency(EMERGENCY, "Application", 4321)
    narrative = application["narrative"]
    assert application["narrative_version"] == NARRATIVE_VERSION
    assert narrative["event_description"] == "Rivers burst their banks on 28 March.\n\nTwo bridges fell."
    assert narrative["event_scope"] == "About 18,000 people are affected."
    assert narrative["needs"] == [{"sector": "Shelter", "text": "3,000 homes were damaged."}]
    assert narrative["who_targeted"].startswith("The operation targets")
    context = application["context"]
    assert context["national_society"] == "Zedland Red Crescent"
    assert context["event_id"] == 4321
    assert context["hazard"] == "Flood"
    # The three newest reports and the first one.
    assert context["field_report_ids"] == [11, 13, 14, 15]
    assert "private@example.org" not in json.dumps(application)


def test_an_update_stage_uses_the_update_text_and_its_sector_progress():
    narrative = application_from_emergency(EMERGENCY, "Operational update 1")["narrative"]
    assert narrative["event_description"] == "Floods continued into April."
    assert narrative["summary_of_change"] == "The timeframe moves to 31 January."
    assert narrative["sector_progress"][0]["progress"] == "Two clinics opened in Herat."
    assert narrative["update_history"][0]["summary_of_change"] == "Scaled up."


def test_a_stored_plan_without_the_written_text_is_read_again(db_session):
    import plugins.dref_monitoring.models  # noqa: F401

    create_test_country(db_session, name="Zedland", iso3="ZZZ", region="Test")
    old = {
        "source": "application",
        "interventions": [
            {
                "key": "health",
                "label": "Health",
                "budget": 1000,
                "people_targeted": 10,
                "indicators": [],
                "activities": ["Open the clinic"],
            }
        ],
    }
    new = {**old, "narrative": {"event_description": "x"}, "narrative_version": NARRATIVE_VERSION}
    for stage_id, application in (("old-stage", old), ("new-stage", new)):
        apply_rows(
            [
                {
                    "id": stage_id,
                    "appeal_code": f"MDR{stage_id[:3].upper()}01",
                    "appeal_type": "DREF",
                    "country_iso3": "ZZZ",
                    "total_approved": 1000,
                    "is_latest_stage": True,
                    "operation_status": "active",
                    "sector_health": True,
                    "sector_health_budget": 1000,
                    "application": application,
                }
            ]
        )
    rows = [{"id": "old-stage"}, {"id": "new-stage"}]
    assert stamp_stored_applications(rows) == 1
    assert "application" not in rows[0]
    assert rows[1]["application"]["narrative_version"] == NARRATIVE_VERSION


def test_a_field_report_keeps_what_was_written_and_drops_people():
    summary = field_report_summary(FIELD_REPORT)
    assert summary["description"] == "Flash floods hit Herat & Ghor."
    assert summary["figures"] == {"dead": 16, "affected": 3570}
    assert summary["actions_taken"] == [
        {"by": "National Society", "actions": ["First Aid", "Search & Rescue"], "summary": ""}
    ]
    dumped = json.dumps(summary)
    assert "example.org" not in dumped
    assert "someone@ifrc.org" not in dumped


def test_a_field_report_that_cannot_be_read_is_skipped():
    calls = []

    def http_get(url, params):
        calls.append(url)
        if url.endswith("/12/"):
            raise RuntimeError("timeout")
        return {**FIELD_REPORT, "fr_num": int(url.rstrip("/").rsplit("/", 1)[1])}

    found = field_reports([11, 12, 13], http_get)
    assert [item["number"] for item in found] == [11, 13]
    assert all("/field-report/" in url for url in calls)


def _operation(**overrides):
    base = {
        "id": 1,
        "appeal_code": "MDRZZ001",
        "country_id": 5,
        "country_name": "Zedland",
        "hazard": "Flood",
        "disaster_name": "Zedland Floods",
        "date_of_disaster": None,
        "start_date": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_documents_are_limited_to_the_event_and_clipped():
    from datetime import date

    seen = {}

    def search(query, filters, user_id, top_k):
        seen["filters"] = filters
        seen["user_id"] = user_id
        return [
            {"chunk_id": 1, "document_title": "Flash Update 3", "source_organization": "OCHA",
             "document_date": "2026-04-26", "content": "Homes were damaged. " * 100, "combined_score": 0.9},
            {"chunk_id": 2, "document_title": "Old report", "document_date": "2019-01-01",
             "content": "An older flood.", "combined_score": 0.95},
            {"chunk_id": 1, "document_title": "Flash Update 3", "content": "duplicate", "combined_score": 0.1},
        ]

    documents = databank_documents(_operation(date_of_disaster=date(2026, 3, 28)), 77, search)
    assert seen["filters"] == {"country_id": 5}
    assert seen["user_id"] == 77
    assert [item["title"] for item in documents] == ["Flash Update 3"]
    assert len(documents[0]["excerpt"]) <= 900
    assert documents[0]["organization"] == "OCHA"


def test_a_failing_document_search_leaves_the_rest(app):
    def search(*args):
        raise RuntimeError("vector store down")

    assert databank_documents(_operation(), None, search) == []


@pytest.fixture
def seeded(db_session):
    import plugins.dref_monitoring.models  # noqa: F401

    create_test_country(db_session, name="Zedland", iso3="ZZZ", region="Test")
    return create_test_user(db_session, email="dref-context@example.com")


def _synced_operation():
    application = application_from_emergency(EMERGENCY, "Application", 4321)
    apply_rows(
        [
            {
                "id": "ctx-1",
                "appeal_code": "MDRCTX01",
                "appeal_type": "DREF",
                "country": "Zedland",
                "country_iso3": "ZZZ",
                "disaster_definition": "Flood",
                "disaster_name": "Zedland Floods",
                "total_approved": 10000,
                "people_targeted": 100,
                "start_date_of_operation": "2026-01-01",
                "end_date_of_operation": "2026-06-30",
                "is_latest_stage": True,
                "operation_status": "active",
                "sector_health": True,
                "sector_health_budget": 8000,
                "sector_health_people_targeted": 80,
                "application": application,
            }
        ]
    )
    return DrefOperation.query.filter_by(appeal_code="MDRCTX01").one()


def test_load_context_joins_every_source(seeded):
    operation = _synced_operation()
    baseline = DrefBaseline.query.filter_by(operation_id=operation.id).one()
    assert baseline.application["narrative"]["event_scope"]
    actor = Actor(seeded.id, True, frozenset(), frozenset(), {})

    def http_get(url, params):
        return {**FIELD_REPORT, "fr_num": int(url.rstrip("/").rsplit("/", 1)[1])}

    def search(query, filters, user_id, top_k):
        return [{"chunk_id": 9, "document_title": "Situation report", "content": "River levels fell.",
                 "combined_score": 0.7}]

    context = load_context(operation, actor, http_get=http_get, search=search)
    assert context["approved_application"]["event_scope"] == "About 18,000 people are affected."
    assert context["emergency"]["national_society"] == "Zedland Red Crescent"
    assert "field_report_ids" not in context["emergency"]
    assert [item["number"] for item in context["field_reports"]] == [11, 13, 14, 15]
    assert context["databank_documents"][0]["title"] == "Situation report"
    assert "previous_report" not in context


def test_the_draft_stores_and_sends_the_background_and_survives_a_loader_failure(seeded):
    operation = _synced_operation()
    actor = Actor(seeded.id, True, frozenset(), frozenset(), {})
    seen = {}

    def complete(payload, kind):
        seen["payload"] = payload
        return json.dumps({"what_happened": "Rivers burst their banks."})

    result = generate_draft(
        operation,
        "operational_update",
        actor,
        complete=complete,
        model_name="gpt-test",
        context_loader=lambda op, who: {"approved_application": {"event_scope": "Scope."}},
    )
    assert result["ai_used"] is True
    assert seen["payload"]["context"]["approved_application"]["event_scope"] == "Scope."
    assert db.session.get(DrefDraft, result["draft_id"]).sections["context"]

    def broken(op, who):
        raise RuntimeError("GO is down")

    again = generate_draft(operation, "operational_update", actor, complete=complete, context_loader=broken)
    assert again["ok"] is True
    assert "context" not in seen["payload"]
    # A draft without a model never loads the background.
    plain = generate_draft(
        operation, "operational_update", actor,
        context_loader=lambda op, who: (_ for _ in ()).throw(AssertionError("loaded for nothing")),
    )
    assert plain["ok"] is True


def test_the_next_draft_sees_the_previous_validated_one(seeded):
    operation = _synced_operation()
    actor = Actor(seeded.id, True, frozenset(), frozenset(), {})
    first = generate_draft(
        operation, "operational_update", actor,
        complete=lambda payload, kind: json.dumps({"what_happened": "Water entered the clinic."}),
    )
    draft = db.session.get(DrefDraft, first["draft_id"])
    draft.status = "validated"
    db.session.commit()
    context = load_context(operation, actor, http_get=lambda *a: {}, search=lambda *a: [])
    assert context["previous_report"]["chapters"]["what_happened"] == "Water entered the clinic."
    assert context["previous_report"]["status"] == "validated"


def test_the_payload_carries_worked_out_progress(seeded):
    operation = _synced_operation()
    payload = build_payload(operation)
    assert payload["country_name"] == "Zedland"
    summary = payload["progress_summary"]
    assert summary["activities"] >= 1
    assert "do not add" in payload["people_reached_note"]
    assert summary["budget_used_percent"] is None


def test_the_prompt_asks_only_for_the_chapters_a_report_has():
    update = llm_messages({"language": "en"}, "operational_update", "en")[0]["content"]
    final = llm_messages({"language": "en"}, "final_report", "en")[0]["content"]
    assert '"summary_of_changes" (GO' in update and '"challenges" (GO' not in update
    assert '"challenges" (GO' in final and '"summary_of_changes" (GO' not in final
    assert set(chapter_keys("operational_update")) | set(chapter_keys("final_report")) == set(SECTION_KEYS)
    for key in chapter_keys("final_report"):
        assert f'"{key}"' in final
    assert "Never write filler" in update
    assert "indicative until" in final


def test_background_comes_before_the_tables_in_the_user_message():
    payload = {"sectors": [], "history": [], "context": {"emergency": {"hazard": "Flood"}}, "request": {}, "appeal_code": "X"}
    content = llm_messages(payload, "final_report", "fr")[1]["content"]
    assert content.index('"context"') < content.index('"sectors"')
    assert "French" in llm_messages(payload, "final_report", "fr")[0]["content"]


def test_a_model_can_be_chosen_on_the_settings_page(app):
    from flask import current_app

    from plugins.dref_monitoring.config_store import save_posted_settings
    from plugins.dref_monitoring.services.llm import DEFAULT_MODEL, configured_model

    previous = current_app.config.get("OPENAI_MODEL")
    try:
        current_app.config["OPENAI_MODEL"] = "gpt-base"
        save_posted_settings({"ai_model": "", "ai_final_report_model": ""})
        assert configured_model("final_report") == "gpt-base"
        save_posted_settings({"ai_model": "gpt-5", "ai_final_report_model": "gpt-5 <script>"})
        assert configured_model("operational_update") == "gpt-5"
        assert configured_model("final_report") == "gpt-5script"
        save_posted_settings({"ai_final_report_model": ""}, partial=True)
        assert configured_model("final_report") == "gpt-5"
        save_posted_settings({"ai_model": ""})
        current_app.config["OPENAI_MODEL"] = ""
        assert configured_model() == DEFAULT_MODEL
    finally:
        current_app.config["OPENAI_MODEL"] = previous
        save_posted_settings({"ai_model": "", "ai_final_report_model": ""})
