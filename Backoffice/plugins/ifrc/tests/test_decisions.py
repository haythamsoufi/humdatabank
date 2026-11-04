"""Decision Support rules, metrics and permission filtering. SYNTHETIC fixtures only: not real National Society data."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from plugins.ifrc.decisions import config, rules
from plugins.ifrc.decisions.access import DENIED, AccessContext
from plugins.ifrc.decisions.facts import Filters, build_decision_data
from plugins.ifrc.decisions.metrics import (
    METRIC_REGISTRY,
    NOT_APPLICABLE,
    NOT_REPORTED,
    REPORTED,
    UNAVAILABLE,
    Observation,
    aggregate,
    meets_quality,
    validation_state_for,
)

TODAY = date(2026, 11, 4)
NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
ADMIN = AccessContext(user_id=1, access_level="admin", allowed_iso3=None, can_view=True, can_manage=True)


def _fact(iso3, name, round_code, year, amount, sid, *, entity="HNS", attribute="Total", label="Applicable"):
    return {
        "Round": round_code, "ISO3": iso3, "Country": name, "NS": f"{name} NS", "Region": "Testregion",
        "Section": "Funding", "Source": "Country Data", "Entity": entity, "Attribute": attribute,
        "SP/EF": None, "Applicable/Data not available": label, "Indicator": "Funding",
        "ValueNum": amount, "Year": year, "submission_id": sid,
    }


def _sub(iso3, name, round_code, sid, status="approved", submitted="2026-10-01T10:00:00", due="2026-09-30T00:00:00"):
    return {
        "Round": round_code, "Country": name, "Region": "Testregion", "NS": f"{name} NS", "ISO3": iso3,
        "status": status, "submitted_at": submitted, "due_date": due, "submission_id": sid,
    }


def _extract(facts, plan_subs, report_subs=()):
    return {
        "plan_facts": list(facts),
        "plan_submissions": list(plan_subs),
        "report_submissions": list(report_subs),
        "built_at": "2026-11-04T09:00:00+00:00",
    }


def _run(extract, access=ADMIN, filters=None, decision_id="DEC-002", rule_overrides=None):
    filters = filters or Filters()
    decision = config.default_decisions()[decision_id]
    rule_map = config.default_rules()
    for rule_id, changes in (rule_overrides or {}).items():
        rule_map[rule_id].update(changes)
    data = build_decision_data(extract, access, filters, today=TODAY)

    def baseline(round_code):
        base = build_decision_data(extract, access, replace(filters, round=round_code, year=None), today=TODAY)
        return base if base.obs("funding_requirement") else None

    flags, outcomes = rules.evaluate_decision(decision, rule_map, data, filters, baseline, now=NOW)
    return data, flags, outcomes


def _two_round_extract(current=10_000_000, baseline=17_200_000):
    return _extract(
        [
            _fact("AAA", "Alpha", "P27", 2027, current, 1),
            _fact("AAA", "Alpha", "P26", 2026, baseline, 2),
            _fact("BBB", "Beta", "P27", 2027, 1_000_000, 3),
            _fact("BBB", "Beta", "P26", 2026, 1_050_000, 4),
        ],
        [
            _sub("AAA", "Alpha", "P27", 1), _sub("AAA", "Alpha", "P26", 2),
            _sub("BBB", "Beta", "P27", 3), _sub("BBB", "Beta", "P26", 4),
        ],
    )


def _by_rule(flags, rule_id):
    return [f for f in flags if f["rule_id"] == rule_id]


# --- states -----------------------------------------------------------------

def _obs(state, value=None, iso3="AAA"):
    return Observation(
        metric_id="funding_requirement", entity_id=iso3, entity_name=iso3, region="R", round="P27", year=2027,
        state=state, value=value, validation_state="validated", submission_id=1, status="approved",
    )


def test_zero_is_a_value_and_other_states_are_not_zero():
    zero = aggregate([_obs(REPORTED, 0.0)])[0]
    assert zero["state"] == REPORTED and zero["value"] == 0.0
    assert aggregate([_obs(UNAVAILABLE)])[0]["value"] is None
    assert aggregate([_obs(UNAVAILABLE)])[0]["state"] == UNAVAILABLE
    assert aggregate([_obs(NOT_APPLICABLE)])[0]["state"] == NOT_APPLICABLE
    mixed = aggregate([_obs(REPORTED, 5.0), _obs(UNAVAILABLE)])[0]
    assert mixed["value"] == 5.0 and mixed["n_unavailable"] == 1


def test_validation_state_mapping_and_quality_gate():
    assert validation_state_for("approved") == "validated"
    assert validation_state_for("sent_for_review") == "provisional"
    assert validation_state_for("in_progress") == "draft"
    assert meets_quality("provisional", "reviewable")
    assert not meets_quality("draft", "reviewable")
    assert not meets_quality("provisional", "validated")


# --- RULE-YOY-CHANGE --------------------------------------------------------

def test_yoy_flag_carries_trigger_values_threshold_and_evidence():
    _data, flags, _out = _run(_two_round_extract())
    yoy = _by_rule(flags, "RULE-YOY-CHANGE")
    assert [f["entity_id"] for f in yoy] == ["AAA"]  # Beta moved 4.8%, below 30
    flag = yoy[0]
    assert flag["trigger_values"]["percent_change"] == pytest.approx(-41.86, abs=0.01)
    assert flag["trigger_values"]["current"] == 10_000_000
    assert flag["trigger_values"]["baseline"] == 17_200_000
    assert flag["threshold"] == {"operator": "absolute_percent_change_gte", "value": 30, "provisional": True}
    assert flag["rule_version"] == 1 and flag["validation_state"] == "validated"
    assert flag["baseline_period"].startswith("P26")
    assert len(flag["evidence_ids"]) == 2 and all(e.startswith("EVID-") for e in flag["evidence_ids"])
    assert flag["finding_source"] == "deterministic_rule"
    assert "41.9" in flag["message"] and "P26" in flag["message"]


def test_threshold_change_changes_result_without_code_change():
    _d, flags, _o = _run(_two_round_extract(), rule_overrides={"RULE-YOY-CHANGE": {"condition": {"operator": "absolute_percent_change_gte", "value": 50}}})
    assert not _by_rule(flags, "RULE-YOY-CHANGE")


def test_missing_baseline_is_not_evaluable_not_a_flag():
    extract = _extract([_fact("AAA", "Alpha", "P27", 2027, 5, 1)], [_sub("AAA", "Alpha", "P27", 1)])
    _d, flags, outcomes = _run(extract)
    assert not _by_rule(flags, "RULE-YOY-CHANGE")
    yoy = next(o for o in outcomes if o.rule_id == "RULE-YOY-CHANGE")
    assert yoy.not_evaluable and yoy.status == "ok"


def test_zero_baseline_is_not_evaluable():
    extract = _two_round_extract(baseline=0)
    # 0 is not emitted by the extract; an explicit zero row must not produce a percentage.
    extract["plan_facts"] = [f for f in extract["plan_facts"] if not (f["ISO3"] == "AAA" and f["Round"] == "P26")]
    extract["plan_facts"].append(_fact("AAA", "Alpha", "P26", 2026, 0, 2))
    _d, flags, outcomes = _run(extract)
    assert not [f for f in _by_rule(flags, "RULE-YOY-CHANGE") if f["entity_id"] == "AAA"]


def test_draft_submissions_do_not_drive_flags():
    extract = _two_round_extract()
    extract["plan_submissions"][0]["status"] = "in_progress"
    _d, flags, _o = _run(extract)
    assert not _by_rule(flags, "RULE-YOY-CHANGE")


def test_paused_rule_does_not_run():
    _d, flags, outcomes = _run(_two_round_extract(), rule_overrides={"RULE-YOY-CHANGE": {"enabled": False}})
    assert not _by_rule(flags, "RULE-YOY-CHANGE")
    assert all(o.rule_id != "RULE-YOY-CHANGE" for o in outcomes)


def test_flag_keys_are_stable_across_runs():
    _d, first, _o = _run(_two_round_extract())
    _d, second, _o = _run(_two_round_extract())
    assert [f["id"] for f in first] == [f["id"] for f in second]
    assert [f["trigger_values"] for f in first] == [f["trigger_values"] for f in second]


# --- other rules ------------------------------------------------------------

def test_missing_target_flags_funding_without_people_but_not_when_not_applicable():
    extract = _two_round_extract()
    _d, flags, _o = _run(extract)
    assert {f["entity_id"] for f in _by_rule(flags, "RULE-MISSING-TARGET")} == {"AAA", "BBB"}

    na_row = {
        "Round": "P27", "ISO3": "AAA", "Country": "Alpha", "Region": "Testregion", "Section": "Reach",
        "Indicator": "People to be reached", "Attribute": "Total", "ValueNum": None, "Year": 2027,
        "Applicable/Data not available": "Not Applicable", "submission_id": 1,
    }
    extract["plan_facts"].append(na_row)
    _d, flags, _o = _run(extract)
    assert {f["entity_id"] for f in _by_rule(flags, "RULE-MISSING-TARGET")} == {"BBB"}


def test_concentration_needs_enough_countries():
    _d, flags, outcomes = _run(_two_round_extract())
    assert not _by_rule(flags, "RULE-CONCENTRATION")
    assert next(o for o in outcomes if o.rule_id == "RULE-CONCENTRATION").not_evaluable

    facts, subs = [], []
    for i, amount in enumerate([9_000_000, 1_000_000, 1_000_000, 1_000_000, 1_000_000], start=1):
        iso = f"C{i:02d}"[:3]
        facts.append(_fact(iso, f"C{i}", "P27", 2027, amount, i))
        subs.append(_sub(iso, f"C{i}", "P27", i))
    _d, flags, _o = _run(_extract(facts, subs))
    flagged = _by_rule(flags, "RULE-CONCENTRATION")
    assert [f["entity_id"] for f in flagged] == ["C01"]
    assert flagged[0]["trigger_values"]["share_pct"] == pytest.approx(9 / 13 * 100, abs=0.01)


def test_unvalidated_requirement_is_information_only():
    extract = _two_round_extract()
    extract["plan_submissions"][2]["status"] = "submitted"
    _d, flags, _o = _run(extract)
    pending = _by_rule(flags, "RULE-UNVALIDATED-REQUIREMENT")
    assert [f["entity_id"] for f in pending] == ["BBB"]
    assert pending[0]["severity"] == "information" and pending[0]["validation_state"] == "provisional"


def test_stalled_and_overdue_workflow_rules():
    extract = _extract(
        [],
        [
            _sub("AAA", "Alpha", "P27", 1, status="submitted", submitted="2026-10-01T00:00:00"),  # 34 days
            _sub("BBB", "Beta", "P27", 2, status="sent_for_review", submitted="2026-11-01T00:00:00"),  # 3 days
            _sub("CCC", "Gamma", "P27", 3, status="in_progress", due="2026-10-20T00:00:00"),  # 15 days overdue
            _sub("DDD", "Delta", "P27", 4, status="pending", due="2026-12-01T00:00:00"),  # not due
        ],
    )
    _d, flags, _o = _run(extract, decision_id="DEC-004")
    assert [f["entity_id"] for f in _by_rule(flags, "RULE-STALLED-REVIEW")] == ["AAA"]
    overdue = _by_rule(flags, "RULE-OVERDUE-SUBMISSION")
    assert [f["entity_id"] for f in overdue] == ["CCC"]
    assert overdue[0]["trigger_values"]["days"] == 15 and overdue[0]["severity"] == "important"


def test_workflow_rule_without_dates_is_skipped_not_flagged():
    extract = _extract([], [_sub("AAA", "Alpha", "P27", 1, status="submitted", submitted=None)])
    _d, flags, _o = _run(extract, decision_id="DEC-004")
    assert not _by_rule(flags, "RULE-STALLED-REVIEW")


def test_data_unavailable_rule_counts_applicable_indicators_only():
    unavailable = {
        "Round": "P27", "ISO3": "AAA", "Country": "Alpha", "Region": "Testregion", "Section": "Core indicators",
        "Indicator": "Volunteers", "Attribute": "Total", "ValueNum": None, "Year": 2027,
        "Applicable/Data not available": "Applicable- data not available", "submission_id": 1,
    }
    not_applicable = dict(unavailable, ISO3="BBB", submission_id=2, **{"Applicable/Data not available": "Not Applicable"})
    extract = _extract([unavailable, not_applicable], [_sub("AAA", "Alpha", "P27", 1), _sub("BBB", "Beta", "P27", 2)])
    _d, flags, _o = _run(extract, decision_id="DEC-004")
    assert [f["entity_id"] for f in _by_rule(flags, "RULE-DATA-UNAVAILABLE")] == ["AAA"]


def test_low_coverage_is_a_scope_flag_with_counts():
    subs = [_sub(f"C{i:02d}"[:3], f"C{i}", "P27", i, status="approved" if i <= 2 else "pending") for i in range(1, 6)]
    _d, flags, _o = _run(_extract([], subs), decision_id="DEC-004")
    cov = _by_rule(flags, "RULE-LOW-COVERAGE")
    assert len(cov) == 1 and cov[0]["entity_type"] == "scope"
    assert cov[0]["trigger_values"] == {"submitted": 2, "expected": 5, "coverage_pct": 40.0}


def test_failing_rule_is_isolated():
    decision = config.default_decisions()["DEC-002"]
    rule_map = config.default_rules()
    rule_map["RULE-CONCENTRATION"]["condition"] = {"operator": "no_such_operator", "value": 1}
    data = build_decision_data(_two_round_extract(), ADMIN, Filters(), today=TODAY)
    flags, outcomes = rules.evaluate_decision(decision, rule_map, data, Filters(), lambda r: None, now=NOW)
    broken = next(o for o in outcomes if o.rule_id == "RULE-CONCENTRATION")
    assert broken.status == "error"
    assert any(o.status == "ok" for o in outcomes)


# --- permissions: filter before calculation ----------------------------------

def test_restricted_user_totals_exclude_other_countries():
    extract = _two_round_extract()
    restricted = AccessContext(user_id=2, access_level="user", allowed_iso3=frozenset({"BBB"}), can_view=True)
    data = build_decision_data(extract, restricted, Filters(round="P27"), today=TODAY)
    total = aggregate(data.obs("funding_requirement"))[0]["value"]
    assert total == 1_000_000  # Alpha's 10M is not in the sum
    assert {o.entity_id for o in data.obs("funding_requirement")} == {"BBB"}
    assert {s.iso3 for s in data.submissions} == {"BBB"}


def test_restricted_user_gets_no_flags_evidence_or_coverage_for_other_countries():
    extract = _two_round_extract()
    restricted = AccessContext(user_id=2, access_level="user", allowed_iso3=frozenset({"BBB"}), can_view=True)
    data, flags, _o = _run(extract, access=restricted)
    assert {f["entity_id"] for f in flags} <= {"BBB"}
    assert not any(f["entity_id"] == "AAA" for f in flags)
    hidden_ids = {o.evidence_id for o in _run(extract)[0].obs("funding_requirement") if o.entity_id == "AAA"}
    assert hidden_ids and not hidden_ids & {e for f in flags for e in f["evidence_ids"]}
    assert not hidden_ids & {o.evidence_id for o in data.obs("funding_requirement")}


def test_no_scope_and_denied_contexts_see_nothing():
    for access in (DENIED, AccessContext(user_id=3, access_level="user", allowed_iso3=frozenset(), can_view=True)):
        data = build_decision_data(_two_round_extract(), access, Filters(), today=TODAY)
        assert data.submissions == [] and data.obs("funding_requirement") == []


def test_user_without_view_permission_reads_no_rows():
    no_view = AccessContext(user_id=4, access_level="user", allowed_iso3=None, can_view=False)
    assert build_decision_data(_two_round_extract(), no_view, Filters(), today=TODAY).submissions == []


def test_decision_visibility_follows_status_and_role():
    decision = config.default_decisions()["DEC-002"]
    user = AccessContext(user_id=5, access_level="user", allowed_iso3=None, can_view=True)
    assert user.can_see_decision(decision)
    assert not DENIED.can_see_decision(decision)
    assert not user.can_see_decision({**decision, "status": "paused"})
    assert not user.can_see_decision({**decision, "visibility": "admin"})
    assert ADMIN.can_see_decision({**decision, "visibility": "admin"})
    assert not user.can_see_decision({**decision, "allowed_roles": ["admin"]})


# --- filters, config, funding mapping ---------------------------------------

def test_filters_reject_bad_input():
    with pytest.raises(ValueError):
        Filters.from_args({"country": "TURKEY"})
    with pytest.raises(ValueError):
        Filters.from_args({"round": "27"})
    with pytest.raises(ValueError):
        Filters.from_args({"validation_state": "approved"})
    parsed = Filters.from_args({"country": "tur", "round": "p27", "lang": "xx"})
    assert (parsed.country, parsed.round, parsed.lang) == ("TUR", "P27", "en")


def test_filter_by_country_and_round_narrows_everything():
    data = build_decision_data(_two_round_extract(), ADMIN, Filters(country="AAA", round="P27"), today=TODAY)
    assert {s.round for s in data.submissions} == {"P27"} and {s.iso3 for s in data.submissions} == {"AAA"}


def test_funding_prefers_priority_columns_over_total_and_does_not_double_count():
    facts = [
        _fact("AAA", "Alpha", "P27", 2027, 999, 1, attribute="Total"),
        _fact("AAA", "Alpha", "P27", 2027, 300, 1, attribute="Longer-term"),
        _fact("AAA", "Alpha", "P27", 2027, 200, 1, attribute="Emergency Operations"),
    ]
    data = build_decision_data(_extract(facts, [_sub("AAA", "Alpha", "P27", 1)]), ADMIN, Filters(), today=TODAY)
    assert aggregate(data.obs("funding_requirement"))[0]["value"] == 500
    assert sum(o.value for o in data.obs("funding_requirement_by_priority")) == 500


def test_non_network_entities_and_confirmed_funding_are_excluded():
    facts = [
        _fact("AAA", "Alpha", "P27", 2027, 100, 1, entity="HNS"),
        _fact("AAA", "Alpha", "P27", 2027, 777, 1, entity="Other sources"),
        dict(_fact("AAA", "Alpha", "P27", 2027, 555, 1, entity="PNS"), Indicator="Confirmed Funding"),
    ]
    data = build_decision_data(_extract(facts, [_sub("AAA", "Alpha", "P27", 1)]), ADMIN, Filters(), today=TODAY)
    assert aggregate(data.obs("funding_requirement"))[0]["value"] == 100


def test_validation_filter_keeps_only_matching_state():
    extract = _two_round_extract()
    extract["plan_submissions"][2]["status"] = "submitted"
    data = build_decision_data(extract, ADMIN, Filters(round="P27", validation_state="validated"), today=TODAY)
    assert {o.entity_id for o in data.obs("funding_requirement")} == {"AAA"}


def test_rule_payload_validation_rejects_unsafe_values():
    rule = config.default_rules()["RULE-YOY-CHANGE"]
    known = set(METRIC_REGISTRY)
    assert config.validate_rule_payload(rule, known_metrics=known) == []
    bad = {**rule, "condition": {"operator": "drop_table", "value": -1}, "severity": "catastrophic"}
    errors = config.validate_rule_payload(bad, known_metrics=known)
    assert len(errors) >= 3
    assert config.validate_rule_payload({**rule, "condition": {"operator": "stalled_days_gte", "value": True}}, known_metrics=known)


def test_every_default_rule_and_decision_is_valid_and_translated():
    known = set(METRIC_REGISTRY)
    rule_map = config.default_rules()
    for rule in rule_map.values():
        assert config.validate_rule_payload(rule, known_metrics=known) == [], rule["id"]
        assert rule["provisional"] is True
    for decision in config.default_decisions().values():
        assert config.validate_decision_payload(decision, known_metrics=known, known_rules=set(rule_map)) == []
        assert set(decision["title"]) == set(config.LANGUAGES)
        assert decision["question"]["ar"]


def test_message_template_is_plain_substitution_and_translations_fall_back():
    assert config.render_template("{{a}} x {{missing}} y {{ b }}", {"a": 1, "b": "z"}) == "1 x  y z"
    assert config.render_template("{{ a.__class__ }}", {"a": 1}) == "{{ a.__class__ }}"
    assert config.tr({"en": "Hello", "fr": "Bonjour"}, "fr") == "Bonjour"
    assert config.tr({"en": "Hello"}, "ar") == "Hello"


def test_french_flag_message():
    _d, flags, _o = _run(_two_round_extract(), filters=Filters(lang="fr"))
    yoy = _by_rule(flags, "RULE-YOY-CHANGE")[0]
    assert "besoin de financement" in yoy["message"]


def test_metric_registry_defines_every_decision_metric():
    for decision in config.default_decisions().values():
        for metric_id in decision["metric_ids"]:
            assert metric_id in METRIC_REGISTRY
    assert METRIC_REGISTRY["people_targeted"].provisional_mapping
    for definition in METRIC_REGISTRY.values():
        assert definition.state_semantics and definition.definition


def test_ai_tool_specs_match_implementations():
    from plugins.ifrc.decisions.ai_tools import DECISION_TOOL_NAMES, DECISION_TOOL_SPECS, TOOL_FUNCTIONS

    assert set(TOOL_FUNCTIONS) == set(DECISION_TOOL_NAMES)
    for spec in DECISION_TOOL_SPECS:
        params = spec["function"]["parameters"]
        assert params["type"] == "object"
        assert set(params["required"]) <= set(params["properties"])
