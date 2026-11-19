"""Helpers and Data Explorer wiring for Global Awards analysis."""

from __future__ import annotations

import datetime as dt

import pytest

from plugins.global_awards.analysis.data import cycle_sort_key, marc_block, parse_number, status_bucket
from plugins.global_awards.constants import EXPLORE_PERMISSION, EXPLORE_ROLE, EXPLORE_TAB_ID
from plugins.global_awards.plugin import GlobalAwardsPlugin

pytestmark = pytest.mark.unit


def test_parse_number_accepts_logframe_targets():
    assert parse_number("100000") == 100000.0
    assert parse_number("1,250") == 1250.0
    assert parse_number(3) == 3.0
    assert parse_number("n/a") is None
    assert parse_number("") is None
    assert parse_number(None) is None


def test_status_bucket_groups_workflow():
    assert status_bucket("approved") == "approved"
    assert status_bucket("submitted") == "submitted"
    assert status_bucket("in_progress") == "progress"
    assert status_bucket("sent_for_review") == "progress"
    assert status_bucket("pending") == "pending"
    assert status_bucket("cancelled") == "cancelled"


def test_cycle_sort_key_orders_quarters_then_final():
    slots = ["Final", "Y1Q3", "Y1Q1", "Y1Q2"]
    assert [slot for slot in sorted(slots, key=cycle_sort_key)] == ["Y1Q1", "Y1Q2", "Y1Q3", "Final"]


def test_resolve_cycle_slots_prefers_the_explicit_selection():
    from plugins.global_awards.analysis.data import resolve_cycle_slots

    assert resolve_cycle_slots() is None
    assert resolve_cycle_slots("Y1Q2") == {"Y1Q2"}
    assert resolve_cycle_slots("Y1Q2", ["Y1Q1", " Final "]) == {"Y1Q1", "Final"}
    assert resolve_cycle_slots(None, []) == set()


def test_cycle_catalog_flags_active_and_passed_for_the_presentation():
    from plugins.global_awards.analysis.data import cycle_catalog

    rows = {row["slot"]: row for row in cycle_catalog(dt.date(2027, 1, 10))}
    assert rows["Y1Q1"]["phase"] == "passed" and rows["Y1Q1"]["present"] is True
    assert rows["Y1Q2"]["phase"] == "active" and rows["Y1Q2"]["present"] is True
    assert rows["Y1Q3"]["phase"] == "upcoming" and rows["Y1Q3"]["present"] is False
    assert rows["Final"]["phase"] == "active" and rows["Final"]["present"] is True

    before = {row["slot"]: row for row in cycle_catalog(dt.date(2026, 8, 1))}
    assert not any(row["present"] for row in before.values())


def test_marc_block_reads_config():
    assert marc_block({"marc": {"key": "goal:people", "code": "1"}})["code"] == "1"
    assert marc_block(None) == {}
    assert marc_block({"other": 1}) == {}


def test_plugin_registers_explorer_tab_and_roles():
    plugin = GlobalAwardsPlugin()
    tabs = plugin.get_data_explorer_tabs()
    assert len(tabs) == 1
    tab = tabs[0]
    assert tab.tab_id == EXPLORE_TAB_ID
    assert tab.permission == EXPLORE_PERMISSION
    assert tab.panel_template.endswith("explorer/tab_panel.html")

    permissions = {row.code for row in plugin.get_seed_permissions()}
    assert EXPLORE_PERMISSION in permissions

    roles = {row.code: row for row in plugin.get_seed_roles()}
    assert EXPLORE_ROLE in roles
    assert EXPLORE_PERMISSION in roles[EXPLORE_ROLE].permission_codes
    assert EXPLORE_PERMISSION in roles["admin_global_awards"].permission_codes


def test_award_window_matches_dhr_calendar():
    from plugins.global_awards.importer.schedule import AWARD_END, AWARD_START, official_cycles

    assert AWARD_START == dt.date(2026, 9, 17)
    assert AWARD_END == dt.date(2027, 9, 16)
    assert [cycle.slot for cycle in official_cycles()] == ["Y1Q1", "Y1Q2", "Y1Q3", "Final"]
