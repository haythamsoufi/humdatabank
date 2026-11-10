"""Unit tests for UPR template 22 staff-presence helpers."""

from __future__ import annotations

from unittest.mock import patch

from plugins.upr.analysis.staff_presence import (
    StaffPresenceLink,
    build_staff_presence,
    clear_staff_presence_cache,
    host_staff_totals,
)


def test_host_staff_totals_sums_numeric_host_rows():
    cells = {
        "mode": "matrix",
        "values": {
            "80_intl_delegates_hns": 3,
            "80_intl_delegates_ifrc": 1,
            "91_national_staff_hns_hns": 5,
            "HNS_intl_delegates_hns": 9,
            "80_ignored_zero": 0,
        },
    }
    # _iter_matrix_numbers expects a flat cells dict from _matrix_cells.
    flat = {
        "80_intl_delegates_hns": 3,
        "80_intl_delegates_ifrc": 1,
        "91_national_staff_hns_hns": 5,
        "HNS_intl_delegates_hns": 9,
        "80_ignored_zero": 0,
    }
    assert host_staff_totals(flat) == {80: 4.0, 91: 5.0}
    assert host_staff_totals(cells.get("values", {})) == {80: 4.0, 91: 5.0}


def test_build_staff_presence_pns_lists_host_countries():
    links = (
        StaffPresenceLink(
            year=2026,
            pns_iso3="NOR",
            pns_name="Norwegian Red Cross",
            host_iso3="SYR",
            host_name="Syria",
            staff=4,
        ),
        StaffPresenceLink(
            year=2026,
            pns_iso3="NOR",
            pns_name="Norwegian Red Cross",
            host_iso3="UKR",
            host_name="Ukraine",
            staff=2,
        ),
        StaffPresenceLink(
            year=2025,
            pns_iso3="NOR",
            pns_name="Norwegian Red Cross",
            host_iso3="SYR",
            host_name="Syria",
            staff=1,
        ),
        StaffPresenceLink(
            year=2026,
            pns_iso3="DNK",
            pns_name="Danish Red Cross",
            host_iso3="SYR",
            host_name="Syria",
            staff=7,
        ),
    )
    clear_staff_presence_cache()
    with patch(
        "plugins.upr.analysis.staff_presence.staff_presence_links",
        return_value=links,
    ):
        payload = build_staff_presence(iso3="NOR", is_pns=True, preferred_year=2026)

    assert payload["year"] == 2026
    assert payload["count"] == 2
    assert payload["staff_total"] == 6
    assert [row["iso3"] for row in payload["entries"]] == ["SYR", "UKR"]
    assert payload["entries"][0]["staff"] == 4


def test_build_staff_presence_host_lists_pns():
    links = (
        StaffPresenceLink(
            year=2026,
            pns_iso3="NOR",
            pns_name="Norwegian Red Cross",
            host_iso3="SYR",
            host_name="Syria",
            staff=4,
        ),
        StaffPresenceLink(
            year=2026,
            pns_iso3="DNK",
            pns_name="Danish Red Cross",
            host_iso3="SYR",
            host_name="Syria",
            staff=7,
        ),
        StaffPresenceLink(
            year=2026,
            pns_iso3="NOR",
            pns_name="Norwegian Red Cross",
            host_iso3="UKR",
            host_name="Ukraine",
            staff=2,
        ),
    )
    with patch(
        "plugins.upr.analysis.staff_presence.staff_presence_links",
        return_value=links,
    ):
        payload = build_staff_presence(iso3="syr", is_pns=False, preferred_year=2026)

    assert payload["count"] == 2
    assert payload["staff_total"] == 11
    assert payload["entries"][0]["iso3"] == "DNK"
    assert payload["entries"][0]["name"] == "Danish Red Cross"
    assert payload["entries"][1]["iso3"] == "NOR"


def test_build_staff_presence_falls_back_to_latest_year():
    links = (
        StaffPresenceLink(
            year=2025,
            pns_iso3="NOR",
            pns_name="Norwegian Red Cross",
            host_iso3="SYR",
            host_name="Syria",
            staff=3,
        ),
    )
    with patch(
        "plugins.upr.analysis.staff_presence.staff_presence_links",
        return_value=links,
    ):
        payload = build_staff_presence(iso3="NOR", is_pns=True, preferred_year=2026)

    assert payload["year"] == 2025
    assert payload["count"] == 1
