"""Unit tests for narrative participation (no database or network needed)."""

from __future__ import annotations

import pytest
import requests

from plugins.upr import narrative
from plugins.upr.narrative import (
    INTERNAL_TYPE_PREFIX,
    PUBLIC_TYPE_PREFIX,
    aggregate_participation,
    is_country_appeal_number,
    parse_unified_documents,
    round_year,
)

ISO = {"AF": "AFG", "BT": "BTN", "CM": "CMR", "PG": "PNG", "CH": "CHE"}

COUNTRIES = {
    "AFG": {"name": "Afghanistan", "region": "Asia Pacific"},
    "BTN": {"name": "Bhutan", "region": "Asia Pacific"},
    "CMR": {"name": "Cameroon", "region": "Africa"},
    "PNG": {"name": "Papua New Guinea", "region": "Asia Pacific"},
}


def _item(**kw):
    row = {
        "AppealsTypeId": 1844,
        "AppealsName": "Afghanistan 2026 Unified Plan",
        "BaseDirectory": "https://go-api.ifrc.org/api/DownloadFile/",
        "BaseFileName": "1/AFG",
        "AppealOrigType": "AFG UPL 2026",
        "BaseAppealNumber": "UPL-2026-MAAAF002",
        "AppealsDate": "2026-01-01T00:00:00",
        "Hidden": False,
        "LocationCountryCode": "AF",
    }
    row.update(kw)
    return row


def _parse(items, mapping=INTERNAL_TYPE_PREFIX):
    return parse_unified_documents(items, type_prefix=mapping, iso2_to_iso3=ISO)


def test_round_year_uses_first_year_found_in_either_field():
    assert round_year("Plan 2025", "UPL-2026-MAAAF002") == 2025
    assert round_year("", "UPL-2026-MAAAF002") == 2026
    assert round_year(None, None) is None
    # ascending order wins, as in the Power Query
    assert round_year("2026 and 2024") == 2024


@pytest.mark.parametrize(
    "number, expected",
    [
        ("UPL-2026-MAAAF002", True),
        ("UPL_2023_MAACM002", True),
        ("UPL_2023_MAA50001", False),  # regional appeal: digits after the tag
        ("UPL-2025-MGRPG001", True),  # MGR fallback
        ("UPL-2025-XYZ", False),  # no tag at all
        (None, False),
    ],
)
def test_country_appeal_number_filter(number, expected):
    assert is_country_appeal_number(number) is expected


def test_parse_maps_type_to_round_family_and_year():
    docs = _parse(
        [
            _item(AppealsTypeId=1844),
            _item(AppealsTypeId=10008, LocationCountryCode="BT", BaseAppealNumber="UPL-2026-MAABT001"),
            _item(AppealsTypeId=10010, LocationCountryCode="CM", AppealOrigType="Cameroon UPL 2025 AR",
                  BaseAppealNumber="UPL-2025-MAACM002"),
        ]
    )
    assert {(d["iso3"], d["round"]) for d in docs} == {("AFG", "P26"), ("BTN", "MYR26"), ("CMR", "AR25")}


def test_parse_public_type_ids_use_the_public_mapping():
    docs = _parse([_item(AppealsTypeId=1851), _item(AppealsTypeId=1844, LocationCountryCode="BT")], PUBLIC_TYPE_PREFIX)
    assert [(d["iso3"], d["round"]) for d in docs] == [("AFG", "P26")]


def test_parse_drops_hidden_unknown_regional_and_switzerland():
    docs = _parse(
        [
            _item(Hidden=True),
            _item(AppealsTypeId=9999),
            _item(LocationCountryCode="CH", BaseAppealNumber="UPL-2026-MAACH001"),
            _item(LocationCountryCode=""),
            _item(LocationCountryCode="ZZ"),  # not in the country map
            _item(LocationCountryCode="PG", BaseAppealNumber="UPL_2026_MAA50001"),  # regional
            _item(AppealOrigType="no year", BaseAppealNumber="UPL-MAAAF002"),
            _item(LocationCountryCode="BT", BaseAppealNumber="UPL-2026-MAABT001"),
        ]
    )
    assert [(d["iso3"], d["round"]) for d in docs] == [("BTN", "P26")]


def test_parse_keeps_first_document_per_country_and_round():
    docs = _parse([_item(AppealsName="first"), _item(AppealsName="second")])
    assert [d["title"] for d in docs] == ["first"]


def test_parse_ignores_non_list_payload():
    assert _parse({"detail": "nope"}) == []


def _doc(iso3, code):
    return {"iso3": iso3, "round": code}


def _sub(iso3, code, status="approved"):
    return {"Round": code, "ISO3": iso3, "status": status}


def test_participation_is_union_of_data_and_internal_narrative():
    out = aggregate_participation(
        internal=[_doc("AFG", "P25"), _doc("BTN", "P25"), _doc("CMR", "P25")],
        public=[_doc("AFG", "P25")],
        submissions=[_sub("AFG", "P25"), _sub("PNG", "P25"), _sub("CMR", "P25", status="assigned")],
        countries=COUNTRIES,
    )
    p25 = next(r for r in out["tracks"]["P"] if r["round"] == "P25")
    assert p25["internal"] == 3
    assert p25["public"] == 1
    assert p25["data_submitted"] == 2  # CMR is only assigned
    assert p25["data_assigned"] == 3
    assert p25["any"] == 4  # AFG, BTN, CMR via narrative; PNG via data
    assert p25["both"] == 1
    assert p25["narrative_only"] == 2
    assert p25["data_only"] == 1
    assert p25["published"] == 1
    assert p25["unpublished"] == 2
    assert p25["publication_pct"] == pytest.approx(33.3)


def test_rounds_without_data_leave_the_data_split_blank():
    out = aggregate_participation(
        internal=[_doc("AFG", "P23")],
        public=[],
        submissions=[_sub("AFG", "P24")],
        countries=COUNTRIES,
    )
    p23 = next(r for r in out["tracks"]["P"] if r["round"] == "P23")
    assert p23["data_available"] is False
    assert p23["any"] == 1
    assert p23["both"] is None and p23["narrative_only"] is None and p23["data_only"] is None


def test_newest_sparse_round_is_in_progress_and_excluded_from_headline():
    internal = [_doc(iso, "P25") for iso in COUNTRIES] + [_doc("AFG", "P26")]
    out = aggregate_participation(internal=internal, public=[], submissions=[], countries=COUNTRIES)
    by_round = {r["round"]: r for r in out["tracks"]["P"]}
    assert by_round["P26"]["in_progress"] is True
    assert by_round["P25"]["in_progress"] is False
    assert out["in_progress"] == ["P26"]
    assert out["headline"]["P"]["any"]["latest_round"] == "P25"
    # no misleading 0% publication rate while documents are still arriving
    assert by_round["P26"]["publication_pct"] is None


def test_retention_counts_carried_new_and_lapsed():
    internal = (
        [_doc(i, "AR24") for i in ("AFG", "BTN", "CMR")]
        + [_doc(i, "AR25") for i in ("AFG", "BTN", "PNG")]
    )
    out = aggregate_participation(internal=internal, public=[], submissions=[], countries=COUNTRIES)
    ar25 = next(r for r in out["tracks"]["AR"] if r["round"] == "AR25")
    assert (ar25["retained"], ar25["new"], ar25["lapsed"]) == (2, 1, 1)
    lapsed = out["gaps"]["AR"]["lapsed"]
    assert [c["iso3"] for c in lapsed] == ["CMR"]


def test_first_round_of_a_track_is_a_baseline_without_churn():
    internal = [_doc(i, "P23") for i in ("AFG", "BTN")] + [_doc(i, "P24") for i in COUNTRIES]
    out = aggregate_participation(internal=internal, public=[], submissions=[], countries=COUNTRIES)
    p23, p24 = out["tracks"]["P"]
    assert p23["baseline"] == 2
    assert p23["retained"] is None
    assert {c["iso3"]: c["baseline"] for c in p23["countries"]} == {"AFG": 1, "BTN": 1}
    # P23 is only partly covered (2 of 4): P24 can say who carried on, but
    # cannot say who "joined" (countries P23 simply missed would look new).
    assert p24["baseline"] is None
    assert (p24["retained"], p24["lapsed"], p24["new"]) == (2, 0, None)
    assert all("new" not in c for c in p24["countries"])
    assert {c["iso3"] for c in p24["countries"] if c["retained"]} == {"AFG", "BTN"}


def test_overview_measures_consistency_and_plan_to_report_completion():
    countries = {**COUNTRIES, "ZZZ": {"name": "Zedland", "region": "Africa"}}
    everyone = list(COUNTRIES)
    internal = (
        [_doc(i, "P24") for i in everyone]
        + [_doc(i, "AR24") for i in everyone]
        + [_doc(i, "P25") for i in everyone]
        + [_doc(i, "AR25") for i in ("AFG", "BTN", "CMR")]  # PNG planned but did not report
        + [_doc("ZZZ", "P23")]  # only seen in a partly covered round
        + [_doc(i, "P23") for i in ("AFG",)]
    )
    out = aggregate_participation(internal=internal, public=[], submissions=[], countries=countries)
    ov = out["overview"]
    assert "P23" not in ov["settled_rounds"]  # 2 of 4 participants: partly covered
    assert ov["settled_rounds"] == ["P24", "AR24", "P25", "AR25"]
    always = {c["iso3"] for c in ov["gaps"]["always"]}
    assert always == {"AFG", "BTN", "CMR"}
    assert {c["iso3"] for c in ov["gaps"]["intermittent"]} == {"PNG"}
    assert {c["iso3"] for c in ov["gaps"]["never"]} == {"ZZZ"}
    assert {e["rounds"]: e["countries"] for e in ov["engagement"]} == {0: 1, 1: 0, 2: 0, 3: 1, 4: 3}
    cycle = ov["cycle"]
    assert (cycle["year"], cycle["plan"], cycle["report"], cycle["both"]) == (2025, 4, 3, 3)
    assert cycle["completion_pct"] == 75.0
    assert [c["iso3"] for c in cycle["planned_not_reported"]] == ["PNG"]


def test_overview_without_a_shared_plan_and_report_year_has_no_cycle():
    out = aggregate_participation(
        internal=[_doc("AFG", "P25")], public=[], submissions=[], countries=COUNTRIES
    )
    assert out["overview"]["cycle"] is None


def test_every_round_record_has_a_chronological_order():
    out = aggregate_participation(
        internal=[_doc("AFG", "AR25"), _doc("AFG", "P25"), _doc("AFG", "MYR25")],
        public=[],
        submissions=[],
        countries=COUNTRIES,
    )
    records = [r for series in out["tracks"].values() for r in series]
    assert [r["round"] for r in sorted(records, key=lambda r: r["order"])] == ["P25", "MYR25", "AR25"]


def test_region_filter_scopes_every_stage():
    out = aggregate_participation(
        internal=[_doc("AFG", "P25"), _doc("CMR", "P25")],
        public=[_doc("CMR", "P25")],
        submissions=[_sub("AFG", "P25"), _sub("CMR", "P25")],
        countries=COUNTRIES,
        region="africa",
    )
    p25 = out["tracks"]["P"][0]
    assert (p25["internal"], p25["public"], p25["data_submitted"], p25["any"]) == (1, 1, 1, 1)
    assert out["universe"] == 1
    assert [m["iso3"] for m in out["matrix"]] == ["CMR"]


def test_matrix_flags_each_stage_per_round():
    out = aggregate_participation(
        internal=[_doc("AFG", "P25")],
        public=[_doc("AFG", "P25")],
        submissions=[_sub("AFG", "P25"), _sub("AFG", "AR25", status="submitted")],
        countries=COUNTRIES,
    )
    row = out["matrix"][0]
    assert row["rounds"] == {"P25": "DNP", "AR25": "D"}
    assert row["rounds_active"] == 2


def test_gaps_list_countries_to_follow_up():
    out = aggregate_participation(
        internal=[_doc("AFG", "P25"), _doc("BTN", "P25")],
        public=[_doc("AFG", "P25")],
        submissions=[_sub("AFG", "P25"), _sub("CMR", "P25")],
        countries=COUNTRIES,
    )
    gaps = out["gaps"]["P"]
    assert gaps["round"] == "P25"
    assert [c["iso3"] for c in gaps["narrative_only"]] == ["BTN"]
    assert [c["iso3"] for c in gaps["data_only"]] == ["CMR"]
    assert [c["iso3"] for c in gaps["unpublished"]] == ["BTN"]


def test_empty_inputs_produce_an_empty_payload():
    out = aggregate_participation(internal=[], public=[], submissions=[], countries={})
    assert out["rounds"] == [] and out["universe"] == 0 and out["matrix"] == []
    assert out["tracks"] == {"P": [], "MYR": [], "AR": []}


def test_load_appeals_serves_stale_feed_when_refresh_fails(monkeypatch):
    narrative.reset_narrative_cache_for_tests()
    calls = {"n": 0}
    payload = [{"AppealsId": 1}]

    def fetch(url):
        calls["n"] += 1
        if calls["n"] > 1:
            raise narrative.NarrativeSourceUnavailable("upstream")
        return payload

    monkeypatch.setattr(narrative, "_fetch_appeals", fetch)
    monkeypatch.setattr(narrative, "_CACHE_TTL_SECONDS", 600)
    assert narrative.load_appeals("internal", "u") == payload
    assert narrative.load_appeals("internal", "u") == payload
    assert calls["n"] == 1

    monkeypatch.setattr(narrative, "_CACHE_TTL_SECONDS", 0)
    assert narrative.load_appeals("internal", "u") == payload  # stale fallback
    assert calls["n"] == 2

    narrative.reset_narrative_cache_for_tests()
    with pytest.raises(narrative.NarrativeSourceUnavailable):
        narrative.load_appeals("public", "u")


def test_fetch_maps_auth_failure(monkeypatch):
    from flask import Flask

    app = Flask(__name__)

    class Response:
        status_code = 401

        def raise_for_status(self):
            error = requests.HTTPError("401")
            error.response = self
            raise error

    app.config["IFRC_API_USER"] = "api-user"
    app.config["IFRC_API_PASSWORD"] = "secret"
    monkeypatch.setattr(narrative.requests, "get", lambda *a, **k: Response())
    with app.app_context():
        with pytest.raises(narrative.NarrativeSourceUnavailable) as caught:
            narrative._fetch_appeals("https://go-api.ifrc.org/Api/FedNetAppeals")
    assert caught.value.code == "auth"
