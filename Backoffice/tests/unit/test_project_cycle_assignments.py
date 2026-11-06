"""Unit tests for per-project cycle assignment helpers."""

from app.models.enums import AssignmentScope
from app.services.assignments.access_service import campaign_only
from app.services.projects.service import (
    CYCLE_PERIOD_SEP,
    cycle_period_name,
    parse_cycle_slot,
)


def test_assignment_scope_values():
    assert AssignmentScope.campaign.value == "campaign"
    assert AssignmentScope.project_cycle.value == "project_cycle"


def test_cycle_period_name_truncates_long_reference():
    long_ref = "X" * 95
    name = cycle_period_name(long_ref, "Y1Q1")
    assert len(name) <= 100
    assert name.endswith(f"{CYCLE_PERIOD_SEP}Y1Q1")


def test_parse_cycle_slot_variants():
    assert parse_cycle_slot("Y3Q4") == "Y3Q4"
    assert parse_cycle_slot(f"REF{CYCLE_PERIOD_SEP}Y3Q4") == "Y3Q4"


def test_campaign_only_helper_exists():
    # Import smoke — full query filter covered in integration when DB is available
    assert callable(campaign_only)
