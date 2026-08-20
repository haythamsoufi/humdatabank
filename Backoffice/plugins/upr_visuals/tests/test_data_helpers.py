"""Tests for UPR visuals data helpers that do not need a live database."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from plugins.upr_visuals.data import (
    _apply_support_funding,
    _expand_plan_support_years,
    _extend_support_with_funding,
    _funding_column_bucket,
    _funding_entity,
    _matrix_cells,
    _ns_logo_src,
    _reach_rows,
    _report_indicator_rows,
    _scalar_number,
    _section_is_other_indicators,
    _section_is_overall_action,
    _split_appeal_label,
    _split_cell_key,
    _spef_icon_alias,
    _sum_funding_by_area,
    _sum_funding_by_bucket,
    _sum_funding_rows,
    _support_from_cells,
    _usable_ifrc_actual,
    build_report_network_entities,
    ifrc_secretariat_actuals_for_report,
    max_people_by_area,
    pns_funding_from_plan_cells,
    pns_area_funding_from_plan_cells,
    spef_icon_srcs,
    sum_t23_host_cells,
    support_total_from_rows,
    t22_host_funding_by_pns,
    t23_host_funding_by_pns,
)
from plugins.upr_visuals.catalog import SUPPORT_AREA_CODES


@pytest.mark.unit
def test_spef_icon_alias_maps_reach_codes_to_catalog():
    assert _spef_icon_alias("CC1") == "CC"
    assert _spef_icon_alias("EFs") == "EF1"
    assert _spef_icon_alias("SP1") == "SP1"


@pytest.mark.unit
def test_ns_logo_src_falls_back_to_github_iso3():
    assert _ns_logo_src(None, "BGD").endswith("/ns_logos/BGD.png")
    assert _ns_logo_src(None, "xx") == ""


@pytest.mark.unit
def test_spef_icon_srcs_uses_indicator_bank_url(monkeypatch):
    row = SimpleNamespace(id=3, code="SP1", icon_filename="SP1.png", is_active=True)
    monkeypatch.setattr(
        "plugins.upr_visuals.data._load_spef_catalog_rows",
        lambda: [row],
    )
    monkeypatch.setattr(
        "plugins.upr_visuals.data._spef_catalog_icon_url",
        lambda item: f"/api/v1/uploads/spef/{item.icon_filename}",
    )
    icons = spef_icon_srcs(inline=False)
    assert icons["SP1"] == "/api/v1/uploads/spef/SP1.png"


@pytest.mark.unit
def test_spef_icon_srcs_uses_plugin_eo_icon(monkeypatch):
    monkeypatch.setattr("plugins.upr_visuals.data._load_spef_catalog_rows", lambda: [])
    icons = spef_icon_srcs(inline=False)
    assert icons["EO"].endswith("icons/eo-emergency.png")


@pytest.mark.unit
def test_spef_icon_srcs_inlines_plugin_eo_icon(monkeypatch):
    monkeypatch.setattr("plugins.upr_visuals.data._load_spef_catalog_rows", lambda: [])
    icons = spef_icon_srcs(inline=True)
    assert icons["EO"].startswith("data:image/png;base64,")
    assert icons["SP1"].startswith("data:image/png;base64,")


@pytest.mark.unit
def test_spef_icon_srcs_inline_skips_http_catalog_url(monkeypatch):
    row = SimpleNamespace(id=3, code="SP1", icon_filename="", is_active=True)
    monkeypatch.setattr(
        "plugins.upr_visuals.data._load_spef_catalog_rows",
        lambda: [row],
    )
    monkeypatch.setattr(
        "plugins.upr_visuals.data._spef_catalog_icon_url",
        lambda item: "/indicator-bank/spef-lookups/3/icon",
    )
    icons = spef_icon_srcs(inline=True)
    assert not str(icons.get("SP1", "")).startswith("/indicator-bank")
    assert icons["SP1"].startswith("data:image/png;base64,")


@pytest.mark.unit
def test_reach_rows_use_catalog_icon(monkeypatch):
    monkeypatch.setattr(
        "plugins.upr_visuals.data.spef_icon_srcs",
        lambda: {"SP1": "/indicator-bank/spef-lookups/3/icon"},
    )
    rows = _reach_rows({"SP1": 1000})
    sp1 = next(row for row in rows if row["code"] == "SP1")
    assert sp1["icon_src"] == "/indicator-bank/spef-lookups/3/icon"
    assert sp1["display"] == "1,000"


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
def test_sum_funding_by_area_rolls_enabling_functions():
    grouped = _sum_funding_by_area(
        {
            "HNS_SP1": 10,
            "HNS_EF1": 4,
            "HNS_Enabling Functions": 6,
            "IFRC Secretariat_SP2": 20,
            "IFRC Secretariat_Total": 999,
            "42_SP1": 30,
        }
    )
    assert grouped["HNS"]["SP1"] == 10
    assert grouped["HNS"]["EFs"] == 10
    assert grouped["HNS"]["total"] == 20
    assert grouped["IFRC Secretariat"]["SP2"] == 20
    assert grouped["IFRC Secretariat"]["total"] == 20
    assert grouped["PNS"]["SP1"] == 30
    assert grouped["PNS"]["total"] == 30


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
def test_pns_area_funding_from_plan_cells_groups_by_ns():
    grouped = pns_area_funding_from_plan_cells(
        {"7_SP1": 100_000, "7_EF2": 20_000, "HNS_SP1": 9, "7_Total": 999, "12_SP2": 489_000}
    )
    assert grouped[7]["SP1"] == 100_000
    assert grouped[7]["EFs"] == 20_000
    assert grouped[12]["SP2"] == 489_000
    assert 7 in grouped
    assert "HNS" not in grouped


@pytest.mark.unit
def test_expand_plan_support_years_emits_year_rows(monkeypatch):
    monkeypatch.setattr("plugins.upr_visuals.data._ns_names", lambda ids: {12: "Austrian Red Cross"})
    ticks = [
        {
            "ns_id": 49,
            "name": "Danish Red Cross",
            "funding": None,
            "areas": {code: True for code in SUPPORT_AREA_CODES} | {"multilateral": False},
        },
        {
            "ns_id": 7,
            "name": "British Red Cross",
            "funding": None,
            "areas": {"SP1": True, "SP2": False, "SP3": False, "SP4": False, "SP5": False, "EFs": False},
        },
    ]
    rows = _expand_plan_support_years(
        ticks,
        year_totals={
            2026: {49: 5_200_000, 7: 1_000_000, 12: 489_000},
            2027: {7: 2_000_000},
            2028: {7: 2_600_000},
        },
        year_areas={
            2026: {12: {"SP2": 489_000}},
            2027: {},
            2028: {},
        },
        confirmed={12: 100_000},
        years=[2026, 2027, 2028],
    )
    by_name: dict[str, list] = {}
    for row in rows:
        by_name.setdefault(row["name"], []).append(row)
    assert [row["year"] for row in by_name["British Red Cross"]] == [2026, 2027, 2028]
    danish = by_name["Danish Red Cross"]
    assert len(danish) == 1
    assert danish[0]["year"] == 2026
    assert danish[0]["funding_display"] == "5.2M"
    assert all(danish[0]["area_amounts"].get(code) is None for code in SUPPORT_AREA_CODES)
    austrian = by_name["Austrian Red Cross"]
    assert len(austrian) == 1
    assert austrian[0]["area_amounts"]["SP2"] == 489_000
    assert austrian[0]["confirmed_display"] == "100,000"
    assert support_total_from_rows(rows)["value"] == 11_289_000


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
def test_ifrc_secretariat_actuals_only_for_myr26():
    assert ifrc_secretariat_actuals_for_report(period_name="2025", iso2="AF") is None
    assert ifrc_secretariat_actuals_for_report(period_name="Jan-Jun 2025", iso2="AF") is None
    afg = ifrc_secretariat_actuals_for_report(period_name="Jan-Jun 2026", iso2="AF")
    assert afg is not None
    assert afg["longer_term"]["funding"] == 10_621_043
    assert afg["longer_term"]["expenditure"] == 3_461_570
    assert afg["emergency"]["funding"] == 1_938_683
    assert afg["emergency"]["expenditure"] == 2_929_339
    by_iso3 = ifrc_secretariat_actuals_for_report(period_name="Jan-Jun 2026", iso3="AFG")
    assert by_iso3 == afg
    missing = ifrc_secretariat_actuals_for_report(period_name="Jan-Jun 2026", iso2="ZZ")
    assert missing is None
    # Albania emergency funding is negative and expenditure is < 1,000 CHF.
    assert ifrc_secretariat_actuals_for_report(period_name="Jan-Jun 2026", iso2="AL") is None


@pytest.mark.unit
def test_usable_ifrc_actual_drops_below_1000_and_negatives():
    assert _usable_ifrc_actual(999) is None
    assert _usable_ifrc_actual(999.99) is None
    assert _usable_ifrc_actual(-5_000) is None
    assert _usable_ifrc_actual(0) is None
    assert _usable_ifrc_actual(None) is None
    assert _usable_ifrc_actual(1_000) == 1_000
    assert _usable_ifrc_actual(1_000.4) == 1_000.4


@pytest.mark.unit
def test_build_report_network_entities_uses_ifrc_actuals():
    plan = {
        "HNS": {"overall": 100, "longer_term": 80, "emergency": 20},
        "IFRC Secretariat": {"overall": 200, "longer_term": 150, "emergency": 50},
        "PNS": {"overall": 300, "longer_term": 300, "emergency": 0},
    }
    rows = build_report_network_entities(
        plan,
        ifrc_actuals={
            "longer_term": {"funding": 10_621_043, "expenditure": 3_461_570},
            "emergency": {"funding": 1_938_683, "expenditure": 2_929_339},
        },
    )
    ifrc = next(row for row in rows if row["entity"] == "IFRC Secretariat")
    longer = {m["key"]: m for m in ifrc["buckets"][0]["metrics"]}
    emergency = {m["key"]: m for m in ifrc["buckets"][1]["metrics"]}
    assert longer["funding_requirement"]["value"] == 150
    assert longer["funding"]["value"] == 10_621_043
    assert longer["expenditure"]["value"] == 3_461_570
    assert emergency["funding"]["value"] == 1_938_683
    assert emergency["expenditure"]["value"] == 2_929_339


@pytest.mark.unit
def test_section_is_overall_action_walks_parent():
    parent = SimpleNamespace(name="Overall Action Indicators", parent_section=None)
    child = SimpleNamespace(name="Resilience - Climate and environment", parent_section=parent)
    key_data = SimpleNamespace(name="Key Data", parent_section=None)
    assert _section_is_overall_action(parent) is True
    assert _section_is_overall_action(child) is True
    assert _section_is_overall_action(key_data) is False
    assert _section_is_overall_action(None) is False


@pytest.mark.unit
def test_section_is_other_indicators():
    other = SimpleNamespace(name="Other Indicators", section_type="dynamic_indicators")
    emergency = SimpleNamespace(name="Emergency Appeal Indicators", section_type="dynamic_indicators")
    assert _section_is_other_indicators(other) is True
    assert _section_is_other_indicators(emergency) is False
    assert _section_is_other_indicators(None) is False


@pytest.mark.unit
def test_report_indicator_rows_uses_overall_action_and_other_only(monkeypatch):
    overall = SimpleNamespace(name="Overall Action Indicators", parent_section=None)
    climate = SimpleNamespace(name="Resilience - Climate and environment", parent_section=overall)
    key_data = SimpleNamespace(name="Key Data", parent_section=None)
    other = SimpleNamespace(name="Other Indicators", section_type="dynamic_indicators")
    emergency = SimpleNamespace(name="Emergency Appeal Indicators", section_type="dynamic_indicators")

    core_item = SimpleNamespace(
        id=1,
        label="Climate people",
        form_section=climate,
        indicator_bank=SimpleNamespace(name="People reached with climate activities", type="number", spef_area=SimpleNamespace(code="SP1"), area="SP1"),
    )
    kpi_item = SimpleNamespace(
        id=2,
        label="Volunteers",
        form_section=key_data,
        indicator_bank=SimpleNamespace(name="Number of people volunteering.", type="number", spef_area=SimpleNamespace(code="EF2"), area="EF2"),
    )
    by_item = {
        1: SimpleNamespace(data_not_available=False, not_applicable=False, get_display_value=lambda: "1000", numeric_value=1000),
        2: SimpleNamespace(data_not_available=False, not_applicable=False, get_display_value=lambda: "50", numeric_value=50),
    }
    other_dyn = SimpleNamespace(
        repeat_instance_number=None,
        section=other,
        custom_label=None,
        indicator_bank=SimpleNamespace(name="Number of people reached - Cash Transfer Programming.", type="number", spef_area=SimpleNamespace(code="SP2"), area="SP2"),
        data_not_available=False,
        not_applicable=False,
        get_display_value=lambda: "250",
        numeric_value=250,
    )
    ea_dyn = SimpleNamespace(
        repeat_instance_number=1,
        section=emergency,
        custom_label=None,
        indicator_bank=SimpleNamespace(name="Number of people reached with disaster risk reduction.", type="number", spef_area=SimpleNamespace(code="SP2"), area="SP2"),
        data_not_available=False,
        not_applicable=False,
        get_display_value=lambda: "9000",
        numeric_value=9000,
    )
    monkeypatch.setattr(
        "plugins.upr_visuals.data._load_dynamic_indicator_rows",
        lambda aes_id: [other_dyn, ea_dyn],
    )

    rows = _report_indicator_rows([core_item, kpi_item], by_item, ("SP1", "SP2", "EF2"), bars_only=True, aes_id=1642)
    labels = [row["label"] for row in rows]
    assert labels == [
        "People reached with climate activities",
        "Number of people reached - Cash Transfer Programming.",
    ]
    assert {row["code"] for row in rows} == {"SP1", "SP2"}


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
