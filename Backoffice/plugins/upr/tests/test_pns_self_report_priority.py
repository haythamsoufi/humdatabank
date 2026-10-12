"""A PNS that self-reported (submitted T22) overrides the host's T24 entry, even when blank."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from plugins.upr.catalog import PLAN_ITEM_FALLBACKS
from plugins.upr.financial import _plan_financial
from plugins.upr.pns_funding import (
    PnsPlanOverride,
    strip_pns_rows,
    t22_host_plan_override,
)
from plugins.upr.support import _plan_support

HOST_COUNTRY = 1
FUNDING_ITEM = SimpleNamespace(id=PLAN_ITEM_FALLBACKS["funding_y0"], label="Funding Requirement", order=0)


def _plan_entry(values: dict) -> dict:
    entry = SimpleNamespace(
        get_display_disagg_data=lambda: {"mode": "matrix", "values": values},
        disagg_data={"values": values},
    )
    return {FUNDING_ITEM.id: entry}


@pytest.mark.unit
def test_t22_host_plan_override_reads_host_row_only():
    override = t22_host_plan_override(
        {"1_SP1": 100, "1_SP2": 50, "1_Total": 400, "2_SP1": 999, "1_confirmedfn": 7},
        HOST_COUNTRY,
    )
    assert override.total == 400
    assert override.areas == {"SP1": 100, "SP2": 50}


@pytest.mark.unit
def test_t22_host_plan_override_total_falls_back_to_areas():
    assert t22_host_plan_override({"1_SP1": 100, "1_EFs": 20}, HOST_COUNTRY).total == 120


@pytest.mark.unit
def test_t22_host_plan_override_blank_row_is_zero():
    override = t22_host_plan_override({"2_SP1": 999}, HOST_COUNTRY)
    assert override == PnsPlanOverride(total=0.0, areas={})


@pytest.mark.unit
def test_strip_pns_rows_keeps_hns_ifrc_and_other_ns():
    cells = {"HNS_SP1": 1, "IFRC Secretariat_SP1": 2, "7_SP1": 3, "12_SP1": 4}
    assert strip_pns_rows(cells, frozenset({7})) == {
        "HNS_SP1": 1,
        "IFRC Secretariat_SP1": 2,
        "12_SP1": 4,
    }


@pytest.mark.unit
def test_plan_financial_pns_self_report_replaces_country_figure(monkeypatch):
    monkeypatch.setattr(
        "plugins.upr.financial.load_t22_pns_overrides",
        lambda *_a, **_k: {
            7: PnsPlanOverride(total=2_000_000, areas={"SP1": 2_000_000}),
            12: PnsPlanOverride(),  # submitted, left Afghanistan blank
        },
    )
    by_item = _plan_entry(
        {
            "HNS_SP1": 1_000_000,
            "7_SP1": 5_000_000,  # country said 5M, PNS self-reported 2M
            "12_SP1": 3_000_000,  # country said 3M, PNS left blank -> 0
            "20_SP1": 400_000,  # PNS 20 has not self-reported -> country figure stays
        }
    )
    result = _plan_financial([FUNDING_ITEM], by_item, "2026", country_id=HOST_COUNTRY)
    assert result["years"][0]["pns"] == 2_400_000
    assert result["years"][0]["hns"] == 1_000_000
    assert result["area_years"][0]["by_entity"]["PNS"]["SP1"] == 2_400_000


@pytest.mark.unit
def test_plan_financial_without_overrides_uses_country_figures(monkeypatch):
    monkeypatch.setattr("plugins.upr.financial.load_t22_pns_overrides", lambda *_a, **_k: {})
    by_item = _plan_entry({"7_SP1": 5_000_000})
    result = _plan_financial([FUNDING_ITEM], by_item, "2026", country_id=HOST_COUNTRY)
    assert result["years"][0]["pns"] == 5_000_000


@pytest.mark.unit
def test_plan_support_pns_self_report_takes_priority(monkeypatch):
    monkeypatch.setattr(
        "plugins.upr.support.load_t22_pns_overrides",
        lambda *_a, **_k: {
            7: PnsPlanOverride(total=2_000_000, areas={"SP1": 2_000_000}),
            12: PnsPlanOverride(),
        },
    )
    monkeypatch.setattr("plugins.upr.support._load_t22_funding_by_pns", lambda *_a, **_k: {})
    monkeypatch.setattr(
        "plugins.upr.support._ns_names",
        lambda ids: {7: "British Red Cross", 12: "Austrian Red Cross", 20: "Danish Red Cross"},
    )
    by_item = _plan_entry(
        {"7_SP1": 5_000_000, "12_SP1": 3_000_000, "20_SP1": 400_000}
    )
    rows = _plan_support([FUNDING_ITEM], by_item, period_name="2026", country_id=HOST_COUNTRY)
    by_id = {row["ns_id"]: row for row in rows}
    assert by_id[7]["funding"] == 2_000_000
    assert by_id[7]["area_amounts"]["SP1"] == 2_000_000
    assert 12 not in by_id  # blank self-report, no ticks -> no amount to show
    assert by_id[20]["funding"] == 400_000
