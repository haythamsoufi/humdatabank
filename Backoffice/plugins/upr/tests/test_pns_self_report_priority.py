"""A PNS that self-reported (submitted T22) overrides the host's T24 entry, even when blank."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from plugins.upr.catalog import PLAN_ITEM_FALLBACKS
from plugins.upr.financial import _plan_financial
from plugins.upr.pns_funding import (
    PnsPlanOverride,
    overrides_for_year,
    strip_pns_rows,
    t22_funding_cells_by_year,
    t22_host_funding_by_pns,
)
from plugins.upr.support import _plan_support

HOST_COUNTRY = 1
Y0_ITEM = SimpleNamespace(id=PLAN_ITEM_FALLBACKS["funding_y0"], label="Funding Requirement", order=0)
Y1_ITEM = SimpleNamespace(id=PLAN_ITEM_FALLBACKS["funding_y1"], label="Funding Requirement +1", order=1)
ITEMS = [Y0_ITEM, Y1_ITEM]


def _entry(values: dict):
    return SimpleNamespace(
        get_display_disagg_data=lambda: {"mode": "matrix", "values": values},
        disagg_data={"values": values},
    )


def _plan_entries(year0: dict, year1: dict | None = None) -> dict:
    out = {Y0_ITEM.id: _entry(year0)}
    if year1 is not None:
        out[Y1_ITEM.id] = _entry(year1)
    return out


# --- reading T22 item 1303 (columns saved resolved per assignment: SP1_2026, SP1_2027, ...) ---


@pytest.mark.unit
def test_t22_cells_by_year_reads_each_year_group():
    by_year = t22_funding_cells_by_year(
        {
            "1_SP1_2026": 100,
            "1_SP2_2026": 50,
            "1_EFs_2026": 10,
            "1_confirmedfn_2026": 7,  # confirmed funding is not a requirement
            "1_SP1_2027": 300,
            "1_fr_tot_2028": 999,  # only a fallback when no SP/EF cells
            "2_SP1_2026": 5_000,  # another host country
        },
        HOST_COUNTRY,
        2026,
    )
    assert by_year[2026] == PnsPlanOverride(total=160, areas={"SP1": 100, "SP2": 50, "EFs": 10})
    assert by_year[2027].total == 300
    assert by_year[2028] == PnsPlanOverride(total=999, areas={})


@pytest.mark.unit
def test_t22_cells_by_year_resolves_legacy_modified_cells():
    by_year = t22_funding_cells_by_year(
        {
            "1_SP1_2026": {"original": 98_818, "modified": "", "isModified": True},
            "1_SP2_2026": {"original": 10, "modified": "25", "isModified": True},
        },
        HOST_COUNTRY,
        2026,
    )
    # modified "" is a blanked lookup (counts as zero); modified "25" wins over original
    assert by_year[2026].areas == {"SP2": 25}


@pytest.mark.unit
def test_t22_cells_by_year_legacy_plain_columns_belong_to_first_year():
    by_year = t22_funding_cells_by_year({"1_SP2": 100_000, "1_Total": 1_700_000}, HOST_COUNTRY, 2026)
    assert by_year == {2026: PnsPlanOverride(total=1_700_000, areas={"SP2": 100_000})}


@pytest.mark.unit
def test_t22_cells_by_year_blank_row_is_empty():
    assert t22_funding_cells_by_year({"2_SP1_2026": 999}, HOST_COUNTRY, 2026) == {}


@pytest.mark.unit
def test_overrides_for_year_defaults_missing_year_to_zero():
    overrides = {7: {2026: PnsPlanOverride(total=5, areas={"SP1": 5})}}
    assert overrides_for_year(overrides, 2026)[7].total == 5
    assert overrides_for_year(overrides, 2027)[7] == PnsPlanOverride()


@pytest.mark.unit
def test_t22_host_funding_by_pns_uses_year_columns():
    entry = _entry({"1_SP1_2026": 100, "1_SP2_2026": 50, "1_SP1_2027": 999})
    assert t22_host_funding_by_pns([entry], 1, {10: 49}, 2026) == {}  # entry has no AES mapping yet
    entry.assignment_entity_status_id = 10
    assert t22_host_funding_by_pns([entry], 1, {10: 49}, 2026) == {49: 150}
    assert t22_host_funding_by_pns([entry], 1, {10: 49}, 2027) == {49: 999}


@pytest.mark.unit
def test_strip_pns_rows_keeps_hns_ifrc_and_other_ns():
    cells = {"HNS_SP1": 1, "IFRC Secretariat_SP1": 2, "7_SP1": 3, "12_SP1": 4}
    assert strip_pns_rows(cells, frozenset({7})) == {
        "HNS_SP1": 1,
        "IFRC Secretariat_SP1": 2,
        "12_SP1": 4,
    }


# --- applying the override to the plan visuals ---


def _overrides():
    return {
        7: {
            2026: PnsPlanOverride(total=2_000_000, areas={"SP1": 2_000_000}),
            2027: PnsPlanOverride(total=800_000, areas={"SP2": 800_000}),
        },
        12: {},  # submitted, left Afghanistan blank in every year
    }


@pytest.mark.unit
def test_plan_financial_pns_self_report_replaces_country_figure_per_year(monkeypatch):
    monkeypatch.setattr("plugins.upr.financial.load_t22_pns_overrides", lambda *_a, **_k: _overrides())
    by_item = _plan_entries(
        {
            "HNS_SP1": 1_000_000,
            "7_SP1": 5_000_000,  # country said 5M, PNS self-reported 2M
            "12_SP1": 3_000_000,  # country said 3M, PNS left blank -> 0
            "20_SP1": 400_000,  # PNS 20 has not self-reported -> country figure stays
        },
        {"7_SP2": 9_000_000, "12_SP2": 1_000_000, "20_SP2": 100_000},
    )
    result = _plan_financial(ITEMS, by_item, "2026", country_id=HOST_COUNTRY)
    y0, y1 = result["years"][0], result["years"][1]
    assert y0["pns"] == 2_400_000
    assert y0["hns"] == 1_000_000
    assert result["area_years"][0]["by_entity"]["PNS"]["SP1"] == 2_400_000
    # year +1: PNS 7 -> 0.8M (T22), PNS 12 -> 0 (blank), PNS 20 -> 0.1M (country)
    assert y1["pns"] == 900_000
    assert result["cover_sources"][-1]["value"] == 2_400_000  # first-year cover figure


@pytest.mark.unit
def test_plan_financial_without_overrides_uses_country_figures(monkeypatch):
    monkeypatch.setattr("plugins.upr.financial.load_t22_pns_overrides", lambda *_a, **_k: {})
    result = _plan_financial(ITEMS, _plan_entries({"7_SP1": 5_000_000}), "2026", country_id=HOST_COUNTRY)
    assert result["years"][0]["pns"] == 5_000_000


@pytest.mark.unit
def test_plan_support_pns_self_report_takes_priority(monkeypatch):
    monkeypatch.setattr("plugins.upr.support.load_t22_pns_overrides", lambda *_a, **_k: _overrides())
    monkeypatch.setattr("plugins.upr.support._load_t22_funding_by_pns", lambda *_a, **_k: {})
    monkeypatch.setattr(
        "plugins.upr.support._ns_names",
        lambda ids: {7: "British Red Cross", 12: "Austrian Red Cross", 20: "Danish Red Cross"},
    )
    by_item = _plan_entries(
        {"7_SP1": 5_000_000, "12_SP1": 3_000_000, "20_SP1": 400_000},
        {"7_SP2": 9_000_000},
    )
    rows = _plan_support(ITEMS, by_item, period_name="2026", country_id=HOST_COUNTRY)
    british = {row["year"]: row for row in rows if row["ns_id"] == 7}
    assert british[2026]["funding"] == 2_000_000
    assert british[2026]["area_amounts"]["SP1"] == 2_000_000
    assert british[2027]["funding"] == 800_000
    assert british[2027]["area_amounts"]["SP2"] == 800_000
    assert not any(row["ns_id"] == 12 for row in rows)  # blank self-report, no ticks -> nothing
    danish = [row for row in rows if row["ns_id"] == 20]
    assert danish and danish[0]["funding"] == 400_000
