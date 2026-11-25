"""An Emergency Appeal with no approved plan is drafted from its operational strategy."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from plugins.emergency_operations_monitoring.models import DrefIndicator, DrefOperation
from plugins.emergency_operations_monitoring.services import go_sync
from plugins.emergency_operations_monitoring.services.go_parse import narrative_signature
from plugins.emergency_operations_monitoring.services.ops_strategy import (
    document_text,
    draft_pending_strategies,
    draft_plan_from_strategy,
    interventions_from_model,
    sector_key,
    select_strategy,
)
from plugins.emergency_operations_monitoring.services.plans import (
    activities_for,
    go_source_notices,
    groups_for,
    indicators_for_group,
    latest_baseline,
    latest_plan,
)
from plugins.emergency_operations_monitoring.tests.test_emergency_appeals import _appeal, _feed
from tests.factories import create_test_country

STRATEGY_URL = "https://go-api.ifrc.org/api/DownloadFile/96486/MDRZZ018OS"
TEXT = "Health services for 8000 people through mobile clinics. " * 20


def _documents(doc_id=34116):
    return {
        "results": [
            {
                "id": 34107,
                "type": "Emergency Appeal",
                "document_url": "https://go-api.ifrc.org/api/DownloadFile/1/MDRZZ018EA",
                "created_at": "2026-08-12T00:00:00Z",
                "name": "Appeal",
            },
            {
                "id": 1,
                "type": "Operational strategy",
                "document_url": "https://go-api.ifrc.org/api/DownloadFile/1/old",
                "created_at": "2026-01-01T00:00:00Z",
                "name": "Old strategy",
            },
            {
                "id": doc_id,
                "type": "Operational strategy",
                "document_url": STRATEGY_URL,
                "created_at": "2026-08-22T00:00:00Z",
                "name": "Zedland (MDRZZ018)",
                "description": "MDRZZ018OS",
            },
            {
                "id": 9,
                "type": "Operational strategy",
                "document_url": "http://go-api.ifrc.org/not-https",
                "created_at": "2026-09-01T00:00:00Z",
                "name": "Insecure",
            },
        ]
    }


def _http(doc_id=34116, fail=False):
    base = _feed([_appeal()])

    def http_get(url, params):
        if "appeal_document" in str(url):
            if fail:
                raise RuntimeError("documents down")
            assert params["appeal"] == 7831
            return _documents(doc_id)
        return base(url, params)

    return http_get


def _reply(_messages):
    return json.dumps(
        {
            "interventions": [
                {
                    "sector": "Health",
                    "budget": "CHF 1,200,000",
                    "people_targeted": 8000,
                    "indicators": [{"title": "People reached with health services", "target": "8,000"}],
                    "activities": ["Run mobile clinics", ""],
                },
                {"key": "wash", "indicators": [], "activities": []},
            ]
        }
    )


def _read(_data):
    return TEXT


def _fetch(url):
    assert url == STRATEGY_URL
    return b"%PDF-1.4"


@pytest.fixture
def seeded(db_session):
    import plugins.emergency_operations_monitoring.models  # noqa: F401

    return create_test_country(db_session, name="Zedland", iso3="ZZZ", region="Test")


# --- the document and the extraction, no database ----------------------------------------------


@pytest.mark.unit
def test_the_newest_operational_strategy_is_chosen_and_other_documents_are_not():
    chosen = select_strategy(_documents()["results"])
    assert chosen["id"] == 34116
    assert chosen["url"] == STRATEGY_URL
    assert chosen["name"] == "Zedland (MDRZZ018)"
    assert select_strategy([{"type": "Operations Update", "document_url": STRATEGY_URL, "id": 3}]) is None
    assert select_strategy(None) is None


@pytest.mark.unit
def test_a_strategy_reply_becomes_sectors_indicators_and_activities():
    rows = interventions_from_model(_reply(None))
    assert rows == [
        {
            "key": "health",
            "label": "Health",
            "budget": 1200000,
            "people_targeted": 8000,
            "indicators": [{"title": "People reached with health services", "target": 8000}],
            "activities": ["Run mobile clinics"],
        }
    ]
    assert sector_key("WASH") == "water_sanitation_and_hygiene"
    assert interventions_from_model("not json") == []


@pytest.mark.unit
def test_a_strategy_id_changes_the_saved_signature_and_a_name_does_not():
    plain = {"narrative": {"event_description": "Quake"}, "narrative_version": 2}
    strategy = {
        "id": "34116",
        "created_at": "2026-08-22T00:00:00Z",
        "url": STRATEGY_URL,
        "name": "One name",
    }
    first = narrative_signature({**plain, "operational_strategy": strategy})
    assert first != narrative_signature(plain)
    renamed = {**strategy, "name": "Another name"}
    assert narrative_signature({**plain, "operational_strategy": renamed}) == first
    replaced = {**strategy, "id": 99999}
    assert narrative_signature({**plain, "operational_strategy": replaced}) != first


@pytest.mark.unit
def test_pdf_text_is_read_and_other_bytes_are_not():
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Mobile clinics in health")
    assert "Mobile clinics in health" in document_text(document.tobytes())
    document.close()
    assert document_text(b"this is not a strategy") == ""


# --- sync and the drafted plan ------------------------------------------------------------------


@pytest.mark.db
def test_a_sync_stores_the_operational_strategy_and_keeps_a_plan_extracted_from_it(seeded):
    go_sync.sync_from_go(_http())
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ018").one()
    baseline = latest_baseline(operation.id)
    strategy = baseline.application["operational_strategy"]
    assert strategy["id"] == 34116
    assert strategy["url"] == STRATEGY_URL
    assert "operational strategy" in go_source_notices(baseline)[0].lower()
    assert [group.key for group in groups_for(latest_plan(operation.id).id)] == ["operation"]

    result = draft_plan_from_strategy(operation, fetch=_fetch, read_text=_read, complete=_reply, force=True)
    assert result["ok"] is True and result["sectors"] == 1
    plan = latest_plan(operation.id)
    assert plan.source == "strategy"
    groups = {group.key: group for group in groups_for(plan.id)}
    assert set(groups) == {"health"}
    assert groups["health"].budget_chf == Decimal("1200000.00")
    assert groups["health"].people_targeted == 8000
    assert [row.title for row in indicators_for_group(groups["health"].id)] == ["People reached with health services"]
    assert indicators_for_group(groups["health"].id)[0].target == Decimal("8000.00")
    assert [row.title for row in activities_for(groups["health"].id)] == ["Run mobile clinics"]
    stored = latest_baseline(operation.id).application
    assert stored["source"] == "operational_strategy"
    assert stored["operational_strategy"]["extracted_document_id"] == 34116
    assert "drafted from the operational strategy" in go_source_notices(latest_baseline(operation.id))[0]

    go_sync.sync_from_go(_http())
    kept = latest_baseline(operation.id).application
    assert kept["interventions"][0]["key"] == "health"
    assert kept["operational_strategy"]["extracted_document_id"] == 34116
    assert latest_plan(operation.id).source == "strategy"
    assert [group.key for group in groups_for(latest_plan(operation.id).id)] == ["health"]


@pytest.mark.db
def test_a_replaced_strategy_document_drops_the_extracted_plan(seeded):
    go_sync.sync_from_go(_http())
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ018").one()
    draft_plan_from_strategy(operation, fetch=_fetch, read_text=_read, complete=_reply, force=True)

    go_sync.sync_from_go(_http(doc_id=99999))
    stored = latest_baseline(operation.id).application
    assert stored["operational_strategy"]["id"] == 99999
    assert stored.get("interventions") in (None, [])
    assert latest_plan(operation.id).source == "strategy"
    assert [group.key for group in groups_for(latest_plan(operation.id).id)] == ["health"]


@pytest.mark.db
def test_a_confirmed_plan_and_an_edited_plan_are_not_replaced(seeded):
    from plugins.emergency_operations_monitoring.access import Actor
    from plugins.emergency_operations_monitoring.services.plans import validate_plan
    from tests.factories import create_test_user

    go_sync.sync_from_go(_http())
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ018").one()
    user = create_test_user(db.session, email="strategy-validator@example.com")
    actor = Actor(user.id, True, frozenset(), frozenset(), {})
    assert validate_plan(operation, actor, date(2026, 11, 25)) is None

    refused = draft_plan_from_strategy(operation, fetch=_fetch, read_text=_read, complete=_reply, force=True)
    assert refused["ok"] is False
    assert latest_plan(operation.id).status == "validated"

    edited = DrefOperation.query.filter_by(appeal_code="MDRZZ018").one()
    plan = latest_plan(edited.id)
    plan.status = "draft"
    plan.source = "excel"
    db.session.commit()
    refused = draft_plan_from_strategy(edited, fetch=_fetch, read_text=_read, complete=_reply, force=True)
    assert refused["ok"] is False
    assert [group.key for group in groups_for(latest_plan(edited.id).id)] == ["operation"]


@pytest.mark.db
def test_the_sync_drafts_an_untouched_plan_and_leaves_one_the_team_has_changed(seeded):
    go_sync.sync_from_go(_http())
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ018").one()
    indicator = DrefIndicator(
        group_id=groups_for(latest_plan(operation.id).id)[0].id,
        title="Left on purpose",
        kind="outcome",
        enabled=False,
    )
    db.session.add(indicator)
    db.session.commit()

    assert (
        draft_pending_strategies(fetch=_fetch, read_text=_read, complete=_reply) == 0
    )
    assert [group.key for group in groups_for(latest_plan(operation.id).id)] == ["operation"]

    indicator.enabled = True
    db.session.commit()
    # The extra indicator means the plan no longer matches the generated shape, so it is still left.
    assert draft_pending_strategies(fetch=_fetch, read_text=_read, complete=_reply) == 0

    db.session.delete(indicator)
    db.session.commit()
    assert draft_pending_strategies(fetch=_fetch, read_text=_read, complete=_reply) == 1
    assert [group.key for group in groups_for(latest_plan(operation.id).id)] == ["health"]


@pytest.mark.db
def test_drafting_is_refused_when_ai_is_off_and_a_missing_document_does_not_stop_the_sync(seeded):
    go_sync.sync_from_go(_http(fail=True))
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ018").one()
    application = latest_baseline(operation.id).application or {}
    assert application.get("operational_strategy") is None
    refused = draft_plan_from_strategy(operation, force=True)
    assert refused["ok"] is False
    assert "operational strategy" in refused["error"].lower()


@pytest.mark.db
def test_the_plan_page_links_the_strategy_and_drafts_it(seeded, app, logged_in_sm_client, monkeypatch):
    from app.plugins.lifecycle_store import save_active_plugin_ids

    from plugins.emergency_operations_monitoring.services import ops_strategy

    previous = set(app.plugin_manager.active_plugins)
    save_active_plugin_ids(sorted(previous | {"emergency_operations_monitoring"}))
    app.plugin_manager.sync_activation_state()
    go_sync.sync_from_go(_http())
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ018").one()
    monkeypatch.setattr(ops_strategy, "fetch_bytes", _fetch)
    monkeypatch.setattr(ops_strategy, "document_text", _read)
    monkeypatch.setattr(ops_strategy, "default_complete", _reply)
    monkeypatch.setattr(ops_strategy, "_ai_on", lambda: True)
    try:
        page = logged_in_sm_client.get(f"/emergency-operations/operations/{operation.id}?tab=plan")
        assert page.status_code == 200
        body = page.get_data(as_text=True)
        assert STRATEGY_URL in body
        assert "Draft plan from the operational strategy" in body
        posted = logged_in_sm_client.post(
            f"/emergency-operations/operations/{operation.id}/plan/strategy",
            data={"tab": "plan"},
            follow_redirects=True,
        )
        assert posted.status_code == 200
        assert "People reached with health services" in posted.get_data(as_text=True)
        assert latest_plan(operation.id).source == "strategy"
    finally:
        app.plugin_manager.active_plugins = previous
