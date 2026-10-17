"""Tests for the PNS support flow-map reducer (no database needed)."""

from __future__ import annotations

from plugins.upr.flow import _centroids, aggregate_flows


COUNTRIES = {
    "GBR": {"iso2": "GB", "name": "United Kingdom", "region": "Europe"},
    "FRA": {"iso2": "FR", "name": "France", "region": "Europe"},
    "KEN": {"iso2": "KE", "name": "Kenya", "region": "Africa"},
    "ETH": {"iso2": "ET", "name": "Ethiopia", "region": "Africa"},
}

DONORS = {
    "british red cross": "GBR",
    "french red cross": "FRA",
}


def _support_row(ns, iso3, rnd, section="Support"):
    return {"Section": section, "Entity": "PNS", "NS": ns, "ISO3": iso3, "Round": rnd}


def test_centroids_file_loads():
    cent = _centroids()
    assert cent.get("GB") and len(cent["GB"]) == 2
    assert cent.get("KE")


def test_aggregate_builds_edges_and_nodes():
    rows = [
        _support_row("British Red Cross", "KEN", "AR24"),
        _support_row("British Red Cross", "KEN", "AR25"),  # same edge, 2nd round
        _support_row("British Red Cross", "ETH", "AR25"),
        _support_row("French Red Cross", "KEN", "AR25", section="Activities"),
        # noise: not a PNS support row
        {"Section": "funding", "Entity": "PNS", "NS": "British Red Cross", "ISO3": "KEN", "Round": "AR25"},
    ]
    out = aggregate_flows(rows, countries=COUNTRIES, donor_iso3_by_name=DONORS, host_iso3s=None)

    assert out["has_data"] is True
    edges = {(e["from"], e["to"]): e for e in out["edges"]}
    assert set(edges) == {("GBR", "KEN"), ("GBR", "ETH"), ("FRA", "KEN")}
    # Plan and report of different years stay one link; the year filter splits them.
    assert edges[("GBR", "KEN")]["weight"] == 1
    assert edges[("GBR", "KEN")]["years"] == [2024, 2025]
    assert edges[("GBR", "KEN")]["rounds"] == ["AR24", "AR25"]
    assert edges[("GBR", "KEN")]["latest_round"] == "AR25"
    assert out["years"] == [2025, 2024]

    nodes = {n["iso3"]: n for n in out["nodes"]}
    assert nodes["GBR"]["role"] == "donor"
    assert nodes["KEN"]["role"] == "host"
    assert nodes["GBR"]["out_weight"] == 2  # one link each to KEN and ETH
    assert nodes["KEN"]["in_weight"] == 2   # one link each from GBR and FRA
    # Every node carries coordinates.
    assert all(isinstance(n["lat"], float) and isinstance(n["lng"], float) for n in out["nodes"])


def test_plan_and_report_in_one_year_are_one_link():
    rows = [
        _support_row("British Red Cross", "KEN", "P25"),
        _support_row("British Red Cross", "KEN", "MYR25"),
        _support_row("British Red Cross", "KEN", "AR25"),
    ]
    out = aggregate_flows(rows, countries=COUNTRIES, donor_iso3_by_name=DONORS, host_iso3s=None)
    assert len(out["edges"]) == 1
    edge = out["edges"][0]
    assert edge["weight"] == 1
    assert edge["years"] == [2025]
    assert edge["rounds"] == ["P25", "MYR25", "AR25"]
    assert out["years"] == [2025]


def test_funding_uses_one_report_per_year():
    rows = [
        {"Source": "PNS Data", "Indicator": "Funding", "Round": "MYR25", "ISO3": "KEN", "Country": "Kenya", "NS": "British Red Cross", "ValueNum": 10},
        {"Source": "PNS Data", "Indicator": "Funding", "Round": "AR25", "ISO3": "KEN", "Country": "Kenya", "NS": "British Red Cross", "ValueNum": 50},
        {"Source": "PNS Data", "Indicator": "Funding", "Round": "AR25", "ISO3": "ETH", "Country": "Ethiopia", "NS": "British Red Cross", "ValueNum": 20},
        {"Source": "PNS Data", "Indicator": "Funding", "Round": "AR25", "ISO3": "KEN", "Country": "Kenya", "NS": "French Red Cross", "ValueNum": 30},
        {"Source": "PNS Data", "Indicator": "Funding", "Round": "P25", "ISO3": "KEN", "NS": "British Red Cross", "ValueNum": 999},
        {"Source": "PNS Data", "Indicator": "Funding", "Round": "AR25", "ISO3": "GBR", "NS": "British Red Cross", "ValueNum": 5},
    ]
    out = aggregate_flows(rows, countries=COUNTRIES, donor_iso3_by_name=DONORS, host_iso3s=None)
    amounts = {(link["from"], link["to"]): link["value"] for link in out["funding"]}
    assert amounts == {("GBR", "KEN"): 50, ("GBR", "ETH"): 20, ("FRA", "KEN"): 30}
    assert out["funding"][0]["from_name"] in {"British Red Cross", "French Red Cross"}


def test_priority_chart_splits_requirement_and_expenditure():
    rows = [
        {"Source": "Country Data", "Indicator": "Funding Requirement", "Entity": "PNS", "Round": "P25", "ISO3": "KEN", "Area": "SP2", "ValueNum": 80},
        {"Source": "Country Data", "Indicator": "Funding Requirement", "Entity": "HNS", "Round": "P25", "ISO3": "KEN", "Area": "SP2", "ValueNum": 500},
        {"Source": "PNS Data", "Indicator": "Expenditure", "Round": "AR25", "ISO3": "KEN", "NS": "British Red Cross", "Area": "SP2", "ValueNum": 30},
        {"Source": "PNS Data", "Indicator": "Expenditure", "Round": "AR25", "ISO3": "KEN", "NS": "British Red Cross", "Area": "EF1", "ValueNum": 5},
        {"Source": "PNS Data", "Indicator": "Expenditure", "Round": "AR25", "ISO3": "KEN", "NS": "British Red Cross", "Area": "SP3", "ValueNum": 18},
        {"Source": "PNS Data", "Indicator": "Funding", "Round": "AR25", "ISO3": "KEN", "NS": "British Red Cross", "Area": "Total", "ValueNum": 40},
        # The host's own priority breakdown is not bilateral PNS expenditure.
        {"Source": "Country Data", "Indicator": "Expenditure", "Attribute": "SP Breakdown", "Entity": "HNS", "Round": "AR25", "ISO3": "KEN", "NS": "Kenya Red Cross Society", "Area": "SP3", "ValueNum": 12},
        {"Source": "Country Data", "Indicator": "Expenditure", "Attribute": "Total", "Entity": "HNS", "Round": "AR25", "ISO3": "KEN", "Area": "Total", "ValueNum": 900},
    ]
    donors = dict(DONORS)
    donors["kenya red cross society"] = "KEN"
    out = aggregate_flows(rows, countries=COUNTRIES, donor_iso3_by_name=donors, host_iso3s=None)
    def total(area, metric):
        return sum(row[metric] for row in out["figures"] if row["area"] == area)
    assert total("SP2", "requirement") == 80
    assert total("SP2", "expenditure") == 30
    assert total("SP3", "expenditure") == 18
    assert total("EFs", "expenditure") == 5
    assert total("", "expenditure") == 0
    totals = [row for row in out["figures"] if not row["area"]]
    assert sum(row["funding"] for row in totals) == 40


def test_region_filter_restricts_hosts_but_not_donors():
    rows = [
        _support_row("British Red Cross", "KEN", "AR25"),
        _support_row("British Red Cross", "FRA", "AR25"),  # host in Europe
    ]
    out = aggregate_flows(rows, countries=COUNTRIES, donor_iso3_by_name=DONORS, host_iso3s={"KEN", "ETH"})
    edges = {(e["from"], e["to"]) for e in out["edges"]}
    assert edges == {("GBR", "KEN")}  # FRA host filtered out, GBR donor kept


def test_self_support_and_unresolved_are_dropped():
    rows = [
        _support_row("British Red Cross", "GBR", "AR25"),      # self-support
        _support_row("Unknown Society", "KEN", "AR25"),         # cannot resolve donor
    ]
    out = aggregate_flows(rows, countries=COUNTRIES, donor_iso3_by_name=DONORS, host_iso3s=None)
    assert out["edges"] == []
    assert out["has_data"] is False
    assert "Unknown Society" in out["unresolved_donors"]


def test_midyear_expenditure_keeps_country_the_annual_report_omits():
    countries = dict(COUNTRIES)
    countries["CHE"] = {"iso2": "CH", "name": "Switzerland", "region": "Europe"}
    countries["AFG"] = {"iso2": "AF", "name": "Afghanistan", "region": "Asia"}
    donors = dict(DONORS)
    donors["swiss red cross"] = "CHE"
    rows = [
        {"Source": "PNS Data", "Indicator": "Expenditure", "Round": "AR26", "ISO3": "KEN", "NS": "Swiss Red Cross", "Area": "SP2", "ValueNum": 100},
        {"Source": "PNS Data", "Indicator": "Expenditure", "Round": "MYR26", "ISO3": "AFG", "NS": "Swiss Red Cross", "Area": "SP2", "ValueNum": 8618},
    ]
    out = aggregate_flows(rows, countries=countries, donor_iso3_by_name=donors, host_iso3s=None)
    assert {(edge["from"], edge["to"]) for edge in out["edges"]} == {("CHE", "KEN"), ("CHE", "AFG")}
    spent = sum(row["expenditure"] for row in out["figures"] if row["area"] == "SP2")
    assert spent == 8718


def test_coverage_point_uses_inform_class_and_funding_met():
    from plugins.upr.flow import _coverage_points, inform_class

    assert inform_class(7.8) == "very_high"
    assert inform_class(2.2) == "low"
    figures = [
        {"year": 2025, "from": "CHE", "to": "AFG", "area": "", "requirement": 10000, "funding": 5000, "expenditure": 0},
        {"year": 2025, "from": "CHE", "to": "AFG", "area": "SP2", "requirement": 10000, "funding": 0, "expenditure": 8618},
    ]
    points = _coverage_points(figures, {"AFG": {"name": "Afghanistan"}})
    assert len(points) == 1
    point = points[0]
    assert point["requirement"] == 10000
    assert point["funding"] == 5000
    assert point["met"] == 50
    assert point["inform_class"] == "very_high"
    assert point["name"] == "Afghanistan"


def test_pns_reporting_priority_columns_are_expenditure():
    from plugins.upr.upr_data import _pns_column_indicator

    assert _pns_column_indicator("SP1") == "Expenditure"
    assert _pns_column_indicator("EFs") == "Expenditure"
    assert _pns_column_indicator("SP3_2026") == "Expenditure"
    assert _pns_column_indicator("Total Expenditure") == "Expenditure"
    assert _pns_column_indicator("Total Funding") == "Funding"
    assert _pns_column_indicator("Comments") is None
