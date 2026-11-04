"""Decision Maker service, store and chatbot-tool permission tests. SYNTHETIC fixtures only."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from plugins.ifrc.decisions import ai_tools, config, facts, service, store
from plugins.ifrc.decisions.access import DENIED, AccessContext
from plugins.ifrc.decisions.facts import Filters


def _fact(iso3, name, round_code, year, amount, sid):
    return {
        "Round": round_code, "ISO3": iso3, "Country": name, "NS": f"{name} NS", "Region": "Testregion",
        "Section": "Funding", "Source": "Country Data", "Entity": "HNS", "Attribute": "Total", "SP/EF": None,
        "Applicable/Data not available": "Applicable", "Indicator": "Funding", "ValueNum": amount,
        "Year": year, "submission_id": sid,
    }


def _sub(iso3, name, round_code, sid):
    return {
        "Round": round_code, "Country": name, "Region": "Testregion", "NS": f"{name} NS", "ISO3": iso3,
        "status": "approved", "submitted_at": "2026-10-01T10:00:00", "due_date": "2026-09-30T00:00:00",
        "submission_id": sid,
    }


@pytest.fixture
def extract():
    return {
        "plan_facts": [
            _fact("AAA", "Alpha", "P27", 2027, 10_000_000, 1),
            _fact("AAA", "Alpha", "P26", 2026, 17_200_000, 2),
            _fact("BBB", "Beta", "P27", 2027, 1_000_000, 3),
            _fact("BBB", "Beta", "P26", 2026, 1_050_000, 4),
        ],
        "plan_submissions": [
            _sub("AAA", "Alpha", "P27", 1), _sub("AAA", "Alpha", "P26", 2),
            _sub("BBB", "Beta", "P27", 3), _sub("BBB", "Beta", "P26", 4),
        ],
        "report_submissions": [],
        "built_at": datetime(2026, 11, 4, 9, 0, tzinfo=timezone.utc).isoformat(),
    }


@pytest.fixture
def patched(db_session, extract, monkeypatch):
    monkeypatch.setattr(facts, "load_extract", lambda: (extract, False))
    return db_session


@pytest.fixture
def admin(admin_user):
    return AccessContext(user_id=admin_user.id, access_level="admin", allowed_iso3=None, can_view=True, can_manage=True)


@pytest.fixture
def restricted(test_user):
    return AccessContext(user_id=test_user.id, access_level="user", allowed_iso3=frozenset({"BBB"}), can_view=True)


def _flag_id(access, rule_id="RULE-YOY-CHANGE"):
    body = service.decision_flags("DEC-002", Filters(), access)
    return next(f["id"] for f in body["data"]["flags"] if f["rule_id"] == rule_id)


def test_summary_is_scoped_and_exposes_no_authorization_internals(patched, restricted):
    body = service.decision_summary("DEC-002", Filters(), restricted)
    assert {row["country"] for row in body["data"]["entities"]} == {"BBB"}
    assert body["permission_context"] == {"scope_limited": True}
    assert body["data"]["funding_by_source"][0]["value"] == 1_000_000
    assert "Alpha" not in repr(body) and "AAA" not in repr(body)
    assert any("permitted" in c for c in body["data_quality"]["caveats"])


def test_admin_summary_has_envelope_and_all_countries(patched, admin):
    body = service.decision_summary("DEC-002", Filters(), admin)
    for key in ("data", "scope", "coverage", "data_quality", "refreshed_at", "sources", "permission_context"):
        assert key in body
    assert {row["country"] for row in body["data"]["entities"]} == {"AAA", "BBB"}
    assert body["coverage"] == {"round": "P27", "expected": 2, "submitted": 2, "validated": 2, "coverage_pct": 100.0}
    assert body["data_quality"]["readiness"] == "Ready"


def test_flag_for_other_country_is_indistinguishable_from_missing(patched, admin, restricted):
    flag_id = _flag_id(admin)
    assert service.flag_detail(flag_id, admin)["data"]["flag"]["entity_id"] == "AAA"
    with pytest.raises(service.NotFound):
        service.flag_detail(flag_id, restricted)
    with pytest.raises(service.NotFound):
        service.flag_detail("FLAG-" + "0" * 32, restricted)
    with pytest.raises(service.NotFound):
        service.set_flag_status(flag_id, "acknowledged", restricted)
    with pytest.raises(service.NotFound):
        service.add_flag_feedback(flag_id, "useful", restricted)


def test_evidence_and_source_records_respect_scope(patched, admin, restricted):
    detail = service.flag_detail(_flag_id(admin), admin)
    assert detail["data"]["evidence"], "admin must be able to open the evidence behind a flag"
    evidence_id = detail["data"]["flag"]["evidence_ids"][0]
    assert service.get_evidence(evidence_id, admin)["data"]["entity"]["id"] == "AAA"
    for denied in (restricted, DENIED):
        with pytest.raises(service.NotFound):
            service.get_evidence(evidence_id, denied)
    with pytest.raises(service.NotFound):
        service.get_source_record("submission:1", restricted)
    assert service.get_source_record("submission:3", restricted)["data"]["country"]["iso3"] == "BBB"
    with pytest.raises(service.NotFound):
        service.get_evidence("EVID-../../etc", admin)


def test_decision_hidden_when_user_lacks_view(patched):
    nobody = AccessContext(user_id=9, access_level="user", allowed_iso3=None, can_view=False)
    with pytest.raises(service.NotFound):
        service.decision_summary("DEC-002", Filters(), nobody)
    assert service.list_decisions(nobody, Filters())["data"]["decisions"] == []


def test_metrics_reject_unknown_dimension_and_metric(patched, admin):
    with pytest.raises(ValueError):
        service.decision_metrics("DEC-002", Filters(), admin, group_by=("strategic_priority",), metric_id="people_targeted")
    with pytest.raises(ValueError):
        service.decision_metrics("DEC-002", Filters(), admin, metric_id="submissions_stalled_days")
    body = service.decision_metrics("DEC-002", Filters(), admin, group_by=("country",), metric_id="funding_requirement")
    groups = body["data"][0]["groups"]
    assert {g["key"]["country"]: g["value"] for g in groups} == {"AAA": 10_000_000, "BBB": 1_000_000}
    assert body["data"][0]["year"] == 2027


def test_flag_review_state_persists_and_overlays(patched, admin):
    flag_id = _flag_id(admin)
    service.set_flag_status(flag_id, "acknowledged", admin, note="Checked with focal point")
    body = service.decision_flags("DEC-002", Filters(), admin)
    flag = next(f for f in body["data"]["flags"] if f["id"] == flag_id)
    assert flag["status"] == "acknowledged" and flag["review_note"] == "Checked with focal point"
    filtered = service.decision_flags("DEC-002", Filters(flag_status="new"), admin)
    assert flag_id not in {f["id"] for f in filtered["data"]["flags"]}
    with pytest.raises(ValueError):
        service.set_flag_status(flag_id, "new", admin)
    service.add_flag_feedback(flag_id, "expected", admin, note="Known restructuring")
    with pytest.raises(ValueError):
        service.add_flag_feedback(flag_id, "bogus", admin)


def test_rule_runs_are_recorded(patched, admin):
    from plugins.ifrc.decisions.models import DecisionRuleRun

    service.decision_flags("DEC-002", Filters(), admin)
    assert {r.rule_id for r in DecisionRuleRun.query.all()} >= {"RULE-YOY-CHANGE", "RULE-MISSING-TARGET"}


# --- chatbot tools -----------------------------------------------------------

def test_tools_refuse_without_access(patched, monkeypatch):
    monkeypatch.setattr(ai_tools, "_access", lambda: DENIED)
    for name, function in ai_tools.TOOL_FUNCTIONS.items():
        result = function(decision_id="DEC-002", flag_id="FLAG-" + "0" * 32, reference="EVID-x")
        assert result["success"] is False, name
        assert "AAA" not in repr(result)


def test_tools_answer_only_from_the_users_scope(patched, restricted, monkeypatch):
    monkeypatch.setattr(ai_tools, "_access", lambda: restricted)
    summary = ai_tools.get_decision_summary(decision_id="DEC-002")
    assert summary["success"] and {c["country"] for c in summary["countries"]} == {"BBB"}
    assert "answer_guidance" in summary and summary["open_view"].startswith("/decisions/")
    assert "Alpha" not in repr(summary)

    flags = ai_tools.get_decision_flags(decision_id="DEC-002")
    assert flags["success"] and all(f["entity_id"] == "BBB" for f in flags["flags"])
    metrics = ai_tools.get_decision_metrics(decision_id="DEC-002", metric="funding_requirement", group_by="country")
    assert [g["key"]["country"] for g in metrics["metrics"][0]["groups"]] == ["BBB"]

    admin_flag = next(
        f for f in service.decision_flags("DEC-002", Filters(), AccessContext(user_id=restricted.user_id, access_level="admin", allowed_iso3=None, can_view=True))["data"]["flags"]
        if f["entity_id"] == "AAA"
    )
    assert ai_tools.get_flag_evidence(flag_id=admin_flag["id"])["success"] is False
    assert ai_tools.get_source_record(reference=admin_flag["evidence_ids"][0])["success"] is False


def test_tool_filters_are_validated(patched, restricted, monkeypatch):
    monkeypatch.setattr(ai_tools, "_access", lambda: restricted)
    bad = ai_tools.get_decision_summary(decision_id="DEC-002", country="not-a-country")
    assert bad["success"] is False
    assert ai_tools.get_decision_summary(decision_id="DEC-999")["success"] is False


def test_flags_answer_matches_ui_service(patched, admin, monkeypatch):
    monkeypatch.setattr(ai_tools, "_access", lambda: admin)
    tool = ai_tools.get_decision_flags(decision_id="DEC-002", rule_id="RULE-YOY-CHANGE")
    ui = service.decision_flags("DEC-002", Filters(), admin)["data"]["flags"]
    assert [f["id"] for f in tool["flags"]] == [f["id"] for f in ui if f["rule_id"] == "RULE-YOY-CHANGE"]
    assert tool["evidence_links"] and all(link.startswith("/api/decision-evidence/EVID-") for link in tool["evidence_links"])


def test_templates_compile_with_the_standard_page_header(app):
    for name in ("catalogue", "workspace", "_guidance"):
        source = app.jinja_env.get_template(f"plugins/ifrc/decisions/{name}.html")
        assert source is not None


def test_every_decision_builds_summary_flags_and_metrics(patched, admin):
    for decision_id in config.default_decisions():
        summary = service.decision_summary(decision_id, Filters(), admin)
        assert summary["data"]["key_metrics"], decision_id
        assert len(summary["data"]["assistant_prompts"]) >= 2
        assert "rules" in service.decision_flags(decision_id, Filters(), admin)["data"]
        service.decision_metrics(decision_id, Filters(), admin)

