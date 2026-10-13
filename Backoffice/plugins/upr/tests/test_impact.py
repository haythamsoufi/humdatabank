"""Unit tests for the UPR Analysis aggregator (no database needed)."""

from __future__ import annotations

from plugins.upr.impact import aggregate_impact, round_sort_key


def _master(**kw):
    row = {
        "ISO3": "AAA",
        "Country": "Aland",
        "Round": "AR25",
        "Year": 2025,
        "Section": None,
        "SectionB": None,
        "Entity": "HNS",
        "NS": "Aland RC",
        "Source": "Country Data",
        "Area": "Total",
        "Attribute": "Total",
        "Indicator": None,
        "indicatorId": None,
        "ValueNum": None,
        "Region": "Africa",
    }
    row.update(kw)
    return row


def _sub(**kw):
    row = {"Round": "AR25", "ISO3": "AAA", "Region": "Africa", "status": "approved", "fds_validated": "Validated"}
    row.update(kw)
    return row


def test_round_sort_key_orders_plan_midyear_annual_within_year():
    codes = ["AR25", "P25", "MYR25", "P24"]
    assert sorted(codes, key=round_sort_key) == ["P24", "P25", "MYR25", "AR25"]


def test_coverage_splits_plan_vs_report_by_year():
    subs = [
        _sub(Round="AR24", ISO3="AAA", status="approved"),
        _sub(Round="AR24", ISO3="BBB", status="submitted", fds_validated=None),
        _sub(Round="AR25", ISO3="AAA", status="approved"),
        _sub(Round="AR25", ISO3="BBB", status="approved"),
        _sub(Round="AR25", ISO3="CCC", status="assigned", fds_validated=None),
        _sub(Round="P25", ISO3="AAA", status="approved"),
    ]
    out = aggregate_impact([], subs)
    by_year = {r["year"]: r for r in out["coverage"]["by_year"]}
    assert by_year[2024]["report_countries"] == 2
    assert by_year[2024]["report_submitted"] == 2
    assert by_year[2024]["report_validated"] == 1
    assert by_year[2025]["report_countries"] == 3
    assert by_year[2025]["report_submitted"] == 2  # CCC is only assigned
    assert by_year[2025]["report_validated"] == 2
    assert by_year[2025]["plan_submitted"] == 1


def test_funding_prefers_total_over_breakdown_no_double_count():
    rows = [
        # One country, one entity: a stored Total plus its SP breakdown.
        _master(Round="P25", Section="Funding", Indicator="Funding Requirement", Entity="HNS", Attribute="Total", ValueNum=1000),
        _master(Round="P25", Section="Funding", Indicator="Funding Requirement", Entity="HNS", Attribute="SP Breakdown", Area="SP1", ValueNum=600),
        _master(Round="P25", Section="Funding", Indicator="Funding Requirement", Entity="HNS", Attribute="SP Breakdown", Area="SP2", ValueNum=400),
        # Second entity contributes its own total.
        _master(Round="P25", Section="Funding", Indicator="Funding Requirement", Entity="IFRC Secretariat", Attribute="Total", ValueNum=500),
    ]
    out = aggregate_impact(rows, [])
    req = {r["year"]: r["value"] for r in out["funding"]["plan_requirement"]}
    assert req[2025] == 1500  # 1000 + 500, breakdown ignored because Total present


def test_funding_delivery_follows_financial_overview_network_mix():
    rows = [
        # Country plan: the three streams behind the Country requirement bar.
        _master(Round="P25", Section="Funding", Indicator="Funding Requirement", Source="Country Data", Entity="HNS", Attribute="Total", ValueNum=1000),
        _master(Round="P25", Section="Funding", Indicator="Funding Requirement", Source="Country Data", Entity="IFRC Secretariat", Attribute="Total", ValueNum=400),
        _master(Round="P25", Section="Funding", Indicator="Funding Requirement", Source="Country Data", Entity="PNS", Attribute="Total", ValueNum=100),
        # Host strategic-priority totals stay off the network delivery lines.
        _master(Round="AR25", Section="Funding", Indicator="Funding", Source="Country Data", Entity="HNS", Attribute="SP Breakdown", Area="SP1", ValueNum=80),
        _master(Round="AR25", Section="Funding", Indicator="Expenditure", Source="Country Data", Entity="HNS", Attribute="SP Breakdown", Area="SP1", ValueNum=60),
        # Other sources on the country report, plus PNS self-reports. Transfers are not expenditure.
        _master(Round="AR25", Section="Funding", Indicator="Funding", Source="Country Data", Entity="Other sources", Attribute="Funding Source", ValueNum=15),
        _master(Round="AR25", Section="Funding", Indicator="Funding", Source="PNS Data", Entity="PNS", Attribute="Total", ValueNum=500),
        _master(Round="AR25", Section="Funding", Indicator="Expenditure", Source="PNS Data", Entity="PNS", Attribute="Total", ValueNum=700),
        _master(Round="AR25", Section="Funding", Indicator="Transferred", Source="PNS Data", Entity="PNS", Attribute="Total", ValueNum=50),
    ]
    out = aggregate_impact(rows, [])
    req = {r["year"]: r["value"] for r in out["funding"]["plan_requirement"]}
    fund = {r["year"]: r["value"] for r in out["funding"]["report_funding"]}
    exp = {r["year"]: r["value"] for r in out["funding"]["report_expenditure"]}
    assert req[2025] == 1500
    assert fund[2025] == 515  # PNS self-report + other sources; not the host SP total
    assert exp[2025] == 700
    plan_countries = {c["iso3"]: c for c in out["funding"]["plan_requirement"][0]["countries"]}
    assert plan_countries["AAA"]["country"] == "Aland"
    assert plan_countries["AAA"]["value"] == 1500
    fund_countries = {c["iso3"]: c for c in out["funding"]["report_funding"][0]["countries"]}
    assert fund_countries["AAA"]["value"] == 515


def test_ifrc_snapshot_is_added_onto_network_delivery(monkeypatch):
    from plugins.upr.impact import _add_ifrc_network_actuals

    monkeypatch.setattr(
        "plugins.upr.financial.ifrc_secretariat_actuals_by_country",
        lambda round_code, *, iso3s=None: (
            [{"iso3": "AFG", "country": "Afghanistan", "funding": 10.0, "expenditure": 4.0}]
            if round_code == "AR25" and iso3s == {"AFG"}
            else []
        ),
    )
    funding = {
        "report_funding": [{"year": 2025, "round": "AR25", "value": 500, "countries": [{"iso3": "CHE", "country": "Switzerland", "value": 500}]}],
        "report_expenditure": [{"year": 2025, "round": "AR25", "value": 700}],
    }
    _add_ifrc_network_actuals(funding, {"AFG"})
    assert funding["report_funding"][0]["value"] == 510
    assert funding["report_expenditure"][0]["value"] == 704
    by_iso = {c["iso3"]: c["value"] for c in funding["report_funding"][0]["countries"]}
    assert by_iso["AFG"] == 10
    assert by_iso["CHE"] == 500


def test_report_funding_and_expenditure_split_by_indicator():
    rows = [
        _master(Round="AR25", Section="Funding", Indicator="Funding", Source="PNS Data", Entity="PNS", Attribute="Total", ValueNum=800),
        _master(Round="AR25", Section="Funding", Indicator="Expenditure", Source="PNS Data", Entity="PNS", Attribute="Total", ValueNum=600),
    ]
    out = aggregate_impact(rows, [])
    fund = {r["year"]: r["value"] for r in out["funding"]["report_funding"]}
    exp = {r["year"]: r["value"] for r in out["funding"]["report_expenditure"]}
    assert fund[2025] == 800
    assert exp[2025] == 600


def test_reporting_prefers_annual_else_midyear_per_year():
    # 2025 has both a mid-year and an annual report -> annual wins.
    # 2026 has only a mid-year report -> it is used and flagged as a fall-back.
    rows = [
        _master(Round="MYR25", Section="Funding", Indicator="Funding", Source="PNS Data", Entity="PNS", Attribute="Total", ValueNum=300),
        _master(Round="AR25", Section="Funding", Indicator="Funding", Source="PNS Data", Entity="PNS", Attribute="Total", ValueNum=500),
        _master(Round="MYR26", Section="Funding", Indicator="Funding", Source="PNS Data", Entity="PNS", Attribute="Total", ValueNum=250),
    ]
    out = aggregate_impact(rows, [])
    fund = {r["year"]: r["value"] for r in out["funding"]["report_funding"]}
    assert fund[2025] == 500  # AR25 beats MYR25
    assert fund[2026] == 250  # only MYR26 available
    assert 2026 in out["midyear_fallback_years"]
    assert 2025 not in out["midyear_fallback_years"]
    # One figure per year — no separate MYR/AR positions on the axis.
    assert out["years"] == [2025, 2026]


def test_reach_sums_area_leaves():
    rows = [
        _master(Round="P25", Section="Reach", Indicator="People to be reached", Area="SP1", ValueNum=100),
        _master(Round="P25", Section="Reach", Indicator="People to be reached", Area="SP2", ValueNum=250),
    ]
    out = aggregate_impact(rows, [])
    reach = {r["year"]: r["value"] for r in out["reach"]["by_year"]}
    assert reach[2025] == 350


def test_partners_distinct_ns_and_pns_funding():
    rows = [
        _master(Round="AR25", Section="Support", Entity="PNS", NS="Danish RC", ValueNum=1),
        _master(Round="AR25", Section="Support", Entity="PNS", NS="Danish RC", ValueNum=1),
        _master(Round="AR25", Section="Support", Entity="PNS", NS="Spanish RC", ValueNum=1),
        _master(Round="AR25", Section="Funding", Source="PNS Data", Indicator="Funding", Entity="PNS", ValueNum=5000),
        _master(Round="AR25", Section="Funding", Source="PNS Data", Indicator="Funding", Entity="PNS", ValueNum=3000),
    ]
    out = aggregate_impact(rows, [])
    partners = {r["year"]: r for r in out["partners"]["by_year"]}
    assert partners[2025]["partners"] == 2
    assert partners[2025]["funding"] == 8000


def test_capacity_maps_indicators_to_keys():
    rows = [
        _master(Round="AR25", Section="NS Data", Indicator="Number of people volunteering", ValueNum=1000),
        _master(Round="AR25", Section="NS Data", Indicator="Number of paid staff", ValueNum=50),
        _master(Round="AR25", Section="NS Data", Indicator="Number of National Society branches", ValueNum=30),
        _master(Round="AR25", Section="NS Data", Indicator="Number of National Society Local Units", ValueNum=200),
    ]
    out = aggregate_impact(rows, [])
    cap = out["capacity"]
    assert {r["year"]: r["value"] for r in cap["volunteers"]}[2025] == 1000
    assert {r["year"]: r["value"] for r in cap["staff"]}[2025] == 50
    assert {r["year"]: r["value"] for r in cap["branches"]}[2025] == 30
    assert {r["year"]: r["value"] for r in cap["local_units"]}[2025] == 200


def test_in_progress_year_excluded_from_headline_and_flagged():
    # P27 is open (few submissions); headline should anchor on the last settled plan year.
    subs = [
        _sub(Round="P25", ISO3="AAA", status="approved"),
        _sub(Round="P25", ISO3="BBB", status="approved"),
        _sub(Round="P26", ISO3="AAA", status="approved"),
        _sub(Round="P26", ISO3="BBB", status="approved"),
        _sub(Round="P27", ISO3="AAA", status="submitted", fds_validated=None),
        _sub(Round="P27", ISO3="BBB", status="assigned", fds_validated=None),
        _sub(Round="P27", ISO3="CCC", status="assigned", fds_validated=None),
        _sub(Round="P27", ISO3="DDD", status="assigned", fds_validated=None),
    ]
    rows = [
        _master(Round="P25", Section="Reach", Indicator="People to be reached", Area="SP1", ValueNum=100),
        _master(Round="P26", Section="Reach", Indicator="People to be reached", Area="SP1", ValueNum=200),
        _master(Round="P27", Section="Reach", Indicator="People to be reached", Area="SP1", ValueNum=10),
    ]
    out = aggregate_impact(rows, subs)
    assert "P27" in out["in_progress"]
    assert 2027 in out["in_progress_years"]
    assert 2026 not in out["in_progress_years"]
    reach = out["headline"]["reach"]
    assert reach["latest_year"] == 2026       # open 2027 skipped
    assert reach["previous_year"] == 2025
    assert reach["change_pct"] == 100.0


def test_headline_compares_consecutive_years():
    subs = [
        _sub(Round="AR24", ISO3="AAA", status="approved"),
        _sub(Round="AR24", ISO3="BBB", status="approved"),
        _sub(Round="AR25", ISO3="AAA", status="approved"),
        _sub(Round="AR25", ISO3="BBB", status="approved"),
        _sub(Round="AR25", ISO3="CCC", status="approved"),
    ]
    out = aggregate_impact([], subs)
    cov = out["headline"]["coverage"]
    assert cov["latest"] == 3
    assert cov["latest_year"] == 2025
    assert cov["previous"] == 2
    assert cov["change_pct"] == 50.0
