"""Tests for UPR visuals data helpers that do not need a live database."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from plugins.upr_visuals.data import (
    _apply_support_funding,
    _extend_support_with_funding,
    _funding_column_bucket,
    _funding_entity,
    _matrix_cells,
    _scalar_number,
    _split_appeal_label,
    _split_cell_key,
    _spef_icon_alias,
    _sum_funding_by_bucket,
    _sum_funding_rows,
    _support_from_cells,
    build_report_network_entities,
    max_people_by_area,
    pns_funding_from_plan_cells,
    sum_t23_host_cells,
    support_total_from_rows,
    t22_host_funding_by_pns,
    t23_host_funding_by_pns,
)


@pytest.mark.unit
def test_spef_icon_alias_maps_reach_codes_to_catalog():
    assert _spef_icon_alias("CC1") == "CC"
    assert _spef_icon_alias("EFs") == "EF1"
    assert _spef_icon_alias("SP1") == "SP1"


@pytest.mark.unit
def test_split_appeal_label():
    name, code = _split_appeal_label("Nigeria - Floods (MDRNG041)")
    assert name == "Nigeria - Floods"
    assert code == "MDRNG041"


@pytest.mark.unit
def test_funding_entity_aliases():
    assert _funding_entity("IFRC Secretariat") == "IFRC Secretariat"
    assert _funding_entity("PNSs") == "PNS"
    assert _funding_entity("HNS other sources") == "Other sources"
    assert _funding_entity("HNS") == "HNS"


@pytest.mark.unit
def test_matrix_cells_from_values_envelope():
    entry = SimpleNamespace(
        get_display_disagg_data=lambda: {"mode": "matrix", "values": {"HNS_SP1": 100, "_meta": 1}}
    )
    cells = _matrix_cells(entry)
    assert cells == {"HNS_SP1": 100}


@pytest.mark.unit
def test_scalar_number_prefers_display_value():
    entry = SimpleNamespace(
        data_not_available=False,
        not_applicable=False,
        get_display_value=lambda: "1,250",
        numeric_value=None,
    )
    assert _scalar_number(entry) == 1250.0


@pytest.mark.unit
def test_sum_funding_rows_groups_pns_numeric_keys():
    cells = {
        "HNS_SP1": 10,
        "IFRC Secretariat_SP1": 20,
        "42_SP1": 30,
        "HNS_Total": 999,
    }
    grouped = _sum_funding_rows(cells)
    assert grouped["HNS"] == 10
    assert grouped["IFRC Secretariat"] == 20
    assert grouped["PNS"] == 30


@pytest.mark.unit
def test_sum_funding_rows_falls_back_to_total_column():
    grouped = _sum_funding_rows({"HNS_Total": 50, "IFRC Secretariat_row_total": 70})
    assert grouped["HNS"] == 50
    assert grouped["IFRC Secretariat"] == 70


@pytest.mark.unit
def test_split_cell_key_keeps_supported_column():
    assert _split_cell_key("7_SP1 Supported") == ("7", "SP1 Supported")
    assert _split_cell_key("2026_SP1") == ("2026", "SP1")
    assert _split_cell_key("IFRC Secretariat_SP1") == ("IFRC Secretariat", "SP1")
    assert _split_cell_key(
        "Resilience - Climate and environment_Funding (CHF)"
    ) == ("Resilience - Climate and environment", "Funding (CHF)")


@pytest.mark.unit
def test_support_from_cells_ticks(monkeypatch):
    monkeypatch.setattr("plugins.upr_visuals.data._ns_names", lambda ids: {7: "The Netherlands Red Cross"})
    rows = _support_from_cells({"7_SP1": 1, "7_EFs": 1}, planned=True)
    assert len(rows) == 1
    assert rows[0]["name"] == "Netherlands Red Cross"
    assert rows[0]["areas"]["SP1"] is True
    assert rows[0]["areas"]["SP2"] is False
    assert rows[0]["areas"]["EFs"] is True


@pytest.mark.unit
def test_support_from_cells_reporting_supported_columns(monkeypatch):
    monkeypatch.setattr("plugins.upr_visuals.data._ns_names", lambda ids: {7: "The Netherlands Red Cross"})
    rows = _support_from_cells(
        {"7_SP1 Supported": 1, "7_SP2 Planned": 1, "7_EFs Supported": 1},
        planned=False,
    )
    assert len(rows) == 1
    assert rows[0]["areas"]["SP1"] is True
    assert rows[0]["areas"]["SP2"] is False
    assert rows[0]["areas"]["EFs"] is True


@pytest.mark.unit
def test_support_from_cells_reads_total_funding_column(monkeypatch):
    monkeypatch.setattr("plugins.upr_visuals.data._ns_names", lambda ids: {7: "The Netherlands Red Cross"})
    rows = _support_from_cells(
        {"7_SP1 Supported": 1, "7_Total": 1_200_000},
        planned=False,
    )
    assert rows[0]["funding"] == 1_200_000
    assert rows[0]["funding_display"] == "1.2M"


@pytest.mark.unit
def test_pns_funding_from_plan_cells_sums_sp_rows():
    amounts = pns_funding_from_plan_cells(
        {"7_SP1": 100_000, "7_SP2": 50_000, "HNS_SP1": 9, "7_Total": 999}
    )
    assert amounts[7] == 150_000


@pytest.mark.unit
def test_t23_host_funding_by_pns():
    entry = SimpleNamespace(
        assignment_entity_status_id=10,
        get_display_disagg_data=lambda: {
            "mode": "matrix",
            "values": {"49_Total Funding": 780_000, "49_Total Expenditure": 10},
        },
    )
    amounts = t23_host_funding_by_pns([entry], 49, {10: 7})
    assert amounts[7] == 780_000


@pytest.mark.unit
def test_t22_host_funding_by_pns_prefers_total():
    entry = SimpleNamespace(
        assignment_entity_status_id=10,
        get_display_disagg_data=lambda: {
            "mode": "matrix",
            "values": {"1_SP2": 100_000, "1_Total": 1_700_000},
        },
    )
    amounts = t22_host_funding_by_pns([entry], 1, {10: 49})
    assert amounts[49] == 1_700_000


@pytest.mark.unit
def test_extend_support_with_funding_adds_amount_only_rows(monkeypatch):
    monkeypatch.setattr("plugins.upr_visuals.data._ns_names", lambda ids: {12: "Austrian Red Cross"})
    amounts = {49: 1_700_000, 12: 650_000}
    rows = _apply_support_funding(
        [
            {
                "ns_id": 49,
                "name": "Danish Red Cross",
                "funding": None,
                "funding_display": "",
                "areas": {"SP2": True},
            }
        ],
        amounts,
    )
    rows = _extend_support_with_funding(rows, amounts)
    names = {row["name"]: row for row in rows}
    assert names["Danish Red Cross"]["funding_display"] == "1.7M"
    assert names["Austrian Red Cross"]["funding_display"] == "650,000"
    assert support_total_from_rows(rows)["value"] == 2_350_000


@pytest.mark.unit
def test_funding_column_bucket():
    assert _funding_column_bucket("SP1") == "longer_term"
    assert _funding_column_bucket("EFs") == "longer_term"
    assert _funding_column_bucket("EA1") == "emergency"
    assert _funding_column_bucket("Total") == "row_total"


@pytest.mark.unit
def test_sum_funding_by_bucket_splits_longer_term_and_emergency():
    cells = {
        "HNS_SP1": 10,
        "HNS_EA1": 40,
        "IFRC Secretariat_SP2": 20,
        "42_EFs": 5,
        "42_EA2": 15,
        "HNS_Total": 999,
    }
    grouped = _sum_funding_by_bucket(cells)
    assert grouped["HNS"]["longer_term"] == 10
    assert grouped["HNS"]["emergency"] == 40
    assert grouped["HNS"]["overall"] == 50
    assert grouped["IFRC Secretariat"]["longer_term"] == 20
    assert grouped["PNS"]["longer_term"] == 5
    assert grouped["PNS"]["emergency"] == 15
    assert grouped["PNS"]["overall"] == 20


@pytest.mark.unit
def test_sum_t23_host_cells_filters_by_host_ns():
    host = SimpleNamespace(
        get_display_disagg_data=lambda: {
            "49_Total Funding": 100,
            "49_Total Expenditure": 80,
            "12_Total Funding": 999,
        }
    )
    other = SimpleNamespace(
        get_display_disagg_data=lambda: {"12_Total Funding": 50, "49_Total Transferred to HNS": 10}
    )
    totals = sum_t23_host_cells([host, other], 49)
    assert totals["funding"] == 100
    assert totals["expenditure"] == 80
    assert totals["transferred"] == 10
    assert totals["assignments"] == 2


@pytest.mark.unit
def test_build_report_network_entities_combines_plan_and_pns():
    plan = {
        "HNS": {"overall": 100, "longer_term": 80, "emergency": 20},
        "IFRC Secretariat": {"overall": 200, "longer_term": 150, "emergency": 50},
        "PNS": {"overall": 300, "longer_term": 300, "emergency": 0},
    }
    rows = build_report_network_entities(
        plan,
        pns_funding=90,
        pns_expenditure=70,
        other_funding=10,
    )
    by_entity = {row["entity"]: row for row in rows}
    assert "Country" in by_entity
    assert "IFRC Secretariat" in by_entity
    assert "PNS" in by_entity
    assert "Other sources" in by_entity
    country_req = by_entity["Country"]["buckets"][0]["metrics"][0]
    assert country_req["key"] == "funding_requirement"
    assert country_req["value"] == 600
    ifrc_buckets = {b["key"]: b for b in by_entity["IFRC Secretariat"]["buckets"]}
    assert "longer_term" in ifrc_buckets
    assert "emergency" in ifrc_buckets
    assert ifrc_buckets["longer_term"]["metrics"][0]["value"] == 150
    assert ifrc_buckets["emergency"]["metrics"][0]["value"] == 50
    ifrc_funding = next(m for m in ifrc_buckets["longer_term"]["metrics"] if m["key"] == "funding")
    assert ifrc_funding["display"] == "Not reported"
    pns_metrics = {m["key"]: m for m in by_entity["PNS"]["buckets"][0]["metrics"]}
    assert pns_metrics["funding"]["value"] == 90
    assert pns_metrics["expenditure"]["value"] == 70
    other_metrics = {m["key"]: m for m in by_entity["Other sources"]["buckets"][0]["metrics"]}
    assert other_metrics["funding_requirement"]["value"] == 100
    assert other_metrics["funding"]["value"] == 10
    assert "expenditure" not in other_metrics


@pytest.mark.unit
def test_ifrc_secretariat_always_splits_longer_term_and_emergency():
    rows = build_report_network_entities(
        {
            "HNS": {"overall": 20, "longer_term": 20, "emergency": 0},
            "IFRC Secretariat": {"overall": 25, "longer_term": 25, "emergency": 0},
            "PNS": {"overall": 15, "longer_term": 15, "emergency": 0},
        }
    )
    ifrc = next(row for row in rows if row["entity"] == "IFRC Secretariat")
    keys = [bucket["key"] for bucket in ifrc["buckets"]]
    assert keys == ["longer_term", "emergency"]
    assert ifrc["buckets"][0]["label"] == "Longer-term"
    assert ifrc["buckets"][1]["label"] == "Emergency Operations"
    req = next(m for m in ifrc["buckets"][0]["metrics"] if m["key"] == "funding_requirement")
    eo_req = next(m for m in ifrc["buckets"][1]["metrics"] if m["key"] == "funding_requirement")
    assert req["value"] == 25
    assert eo_req["display"] == "Not reported"


@pytest.mark.unit
def test_max_people_by_area_keeps_highest_per_sp_and_cross_cutting():
    best = max_people_by_area(
        [
            ("SP1", 100),
            ("SP1", 2500),
            ("SP1", 800),
            ("CC1", 400),
            ("CC1", 1200),
            ("SP2", 50),
            ("EO", 9000),
            ("EF1", 99),
        ]
    )
    assert best["SP1"] == 2500
    assert best["CC1"] == 1200
    assert best["SP2"] == 50
    assert best["EO"] == 9000
    assert "EF1" not in best


@pytest.mark.unit
def test_visual_export_filename():
    from plugins.upr_visuals.service import visual_export_filename

    name = visual_export_filename(
        {"iso3": "AFG", "round_code": "P25", "period_name": "2025"},
        "financial",
        "pdf",
    )
    assert name == "AFG_P25_financial.pdf"
    assert visual_export_filename({}, "combined", "png") == "UNK_round_combined.png"
