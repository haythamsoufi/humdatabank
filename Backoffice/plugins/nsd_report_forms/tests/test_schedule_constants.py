"""Unit tests for NSD cycle helpers (no DB)."""

from app.services.projects.service import CYCLE_PERIOD_SEP, cycle_period_name, parse_cycle_slot
from plugins.nsd_report_forms.constants import (
    ENTITY_TYPE,
    FINAL_SLOT,
    all_quarter_slots,
    parse_quarter_slot,
    quarter_slot,
)
from plugins.nsd_report_forms.schedule import slot_for_schedule_row


def test_entity_type_constant():
    assert ENTITY_TYPE == "project"


def test_quarter_slots_catalogue():
    slots = all_quarter_slots(2)
    assert slots[0] == "Y1Q1"
    assert "Y2Q4" in slots
    assert FINAL_SLOT == "Final"
    assert len(slots) == 8


def test_parse_quarter_slot():
    assert parse_quarter_slot("Y1Q2") == (1, 2)
    assert parse_quarter_slot("Final") is None
    assert quarter_slot(2, 3) == "Y2Q3"


def test_slot_for_schedule_row():
    assert slot_for_schedule_row("CBF quarter", "Y1Q3") == ("CBF quarter", "Y1Q3")
    assert slot_for_schedule_row("CBF final report", "Y2Q4") == ("CBF final report", FINAL_SLOT)
    assert slot_for_schedule_row("CBF quarter", "bad") is None


def test_cycle_period_name():
    assert cycle_period_name("CBF-2025-014", "Y1Q2") == f"CBF-2025-014{CYCLE_PERIOD_SEP}Y1Q2"
    assert cycle_period_name("CBF-2025-014", "Final") == f"CBF-2025-014{CYCLE_PERIOD_SEP}Final"


def test_parse_cycle_slot():
    assert parse_cycle_slot(f"CBF-2025-014{CYCLE_PERIOD_SEP}Y1Q2") == "Y1Q2"
    assert parse_cycle_slot(f"CBF-2025-014{CYCLE_PERIOD_SEP}Final") == "Final"
    assert parse_cycle_slot("Y1Q2") == "Y1Q2"
    assert parse_cycle_slot("Final") == "Final"
    assert parse_cycle_slot("CBF-2025-014 Y1Q2") == "Y1Q2"
    assert parse_cycle_slot("CBF-2025-014 - Final") == "Final"
    assert parse_cycle_slot("") is None
