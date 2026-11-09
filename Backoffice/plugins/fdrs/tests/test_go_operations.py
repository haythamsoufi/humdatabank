"""Parser tests for IFRC GO active operations. No network."""

from plugins.fdrs.services.go_operations import (
    build_operations_payload,
    go_region_id,
    operation_query_params,
    operations_by_country,
    parse_active_appeals,
    parse_aggregated,
)


def test_country_totals_use_iso3_not_the_ignored_list_filter():
    aggregated, appeals = operation_query_params(iso3="ago")
    assert aggregated == {"iso3": "AGO"}
    assert appeals == {"country__iso3": "AGO"}
    assert operation_query_params(region_id=0) == ({"region": 0}, {"region": 0})


def test_go_region_id_matches_databank_region_names():
    assert go_region_id("Africa") == 0
    assert go_region_id("Americas") == 1
    assert go_region_id("Asia Pacific") == 2
    assert go_region_id("Europe and Central Asia") == 3
    assert go_region_id("Middle East and North Africa") == 4
    assert go_region_id("Other") is None


def test_parse_aggregated_prefers_dref_included_funding():
    summary = parse_aggregated({
        "active_drefs": 2,
        "active_appeals": 0,
        "target_population": 76075,
        "amount_requested": None,
        "amount_requested_dref_included": 1096512,
        "amount_funded": None,
        "amount_funded_dref_included": 548256,
    })
    assert summary["active_drefs"] == 2
    assert summary["people_targeted"] == 76075
    assert summary["amount_requested"] == 1096512
    assert summary["amount_funded"] == 548256


def test_active_appeals_drop_closed_rows_and_rank_countries():
    appeals = [
        {
            "name": "Closed flood",
            "status": 1,
            "status_display": "Closed",
            "atype_display": "DREF",
            "num_beneficiaries": 999,
            "country": {"name": "Kenya", "iso3": "KEN"},
        },
        {
            "name": "Burkina Faso - Floods",
            "code": "MDRBF024",
            "status": 0,
            "status_display": "Active",
            "atype_display": "DREF",
            "dtype": {"name": "Flood"},
            "num_beneficiaries": 26075,
            "amount_requested": 100,
            "amount_funded": 40,
            "start_date": "2026-03-16T00:00:00Z",
            "country": {"name": "Burkina Faso", "iso3": "BFA"},
        },
        {
            "name": "Kenya drought",
            "status": 0,
            "atype_display": "Emergency Appeal",
            "num_beneficiaries": 5000,
            "country": {"name": "Kenya", "iso3": "KEN"},
        },
    ]
    active = parse_active_appeals(appeals)
    assert [row["name"] for row in active] == ["Burkina Faso - Floods", "Kenya drought"]
    assert active[0]["disaster_type"] == "Flood"
    assert active[0]["start_date"] == "2026-03-16"
    angola_only = parse_active_appeals(appeals, iso3="AGO")
    assert angola_only == []

    countries = operations_by_country(active)
    assert countries[0]["iso3"] == "BFA"
    assert countries[0]["people_targeted"] == 26075
    assert countries[1]["operations"] == 1

    payload = build_operations_payload(
        {"active_drefs": 1, "active_appeals": 1, "target_population": 31075},
        appeals,
        operation_limit=1,
        include_countries=True,
    )
    assert len(payload["operations"]) == 1
    assert payload["operations"][0]["name"] == "Burkina Faso - Floods"
    assert payload["by_country"][0]["iso3"] == "BFA"
