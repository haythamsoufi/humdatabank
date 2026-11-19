"""Bounds and reporting cadence. No database."""

from datetime import date
from decimal import Decimal

import pytest

from plugins.dref_monitoring.services.bounds import (
    dates_outside_operation,
    exceeds_group_budget,
    people_over_cap,
)
from plugins.dref_monitoring.services.go_parse import is_imminent, parse_stage
from plugins.dref_monitoring.services.periods import build_periods, default_frequency, escalation_level

pytestmark = pytest.mark.unit


def test_group_budget_blocks_the_activity_that_breaks_the_sector_cap():
    pairs = [(1, Decimal("40")), (2, Decimal("50"))]
    assert exceeds_group_budget(Decimal("100"), pairs, 2, Decimal("70")) is True
    assert exceeds_group_budget(Decimal("100"), pairs, 2, Decimal("60")) is False
    assert exceeds_group_budget(None, pairs, 2, Decimal("999")) is False


def test_dates_and_people_use_the_approved_operation():
    assert dates_outside_operation(date(2026, 1, 1), date(2026, 6, 30), date(2026, 1, 1), date(2026, 7, 1))
    assert not dates_outside_operation(date(2026, 1, 1), date(2026, 6, 30), date(2026, 1, 2), date(2026, 6, 30))
    assert people_over_cap(100, 101)
    assert not people_over_cap(100, 100)
    assert not people_over_cap(None, 500)


def test_imminent_operations_report_every_two_weeks():
    assert default_frequency("i-DREF", 2, date(2026, 1, 1), date(2026, 2, 15)) == "biweekly"
    assert default_frequency("DREF", 6, date(2026, 1, 1), date(2026, 7, 1)) == "monthly"
    periods = build_periods(date(2026, 1, 1), date(2026, 1, 20), "biweekly")
    assert periods[0][0] == 1
    assert periods[-1][2] == date(2026, 1, 20)
    assert len(periods) == 2


def test_escalation_steps_up_as_the_report_stays_open():
    due = date(2026, 5, 10)
    settings = {
        "reminder_days_before": 3,
        "escalation_validate_days": 3,
        "escalation_review_days": 7,
        "escalation_portfolio_days": 14,
    }
    assert escalation_level(date(2026, 5, 1), due, False, settings) is None
    assert escalation_level(date(2026, 5, 8), due, False, settings) == "reminder"
    assert escalation_level(date(2026, 5, 14), due, False, settings) == "validate"
    assert escalation_level(date(2026, 5, 20), due, False, settings) == "review"
    assert escalation_level(date(2026, 5, 30), due, False, settings) == "portfolio"
    assert escalation_level(date(2026, 5, 30), due, True, settings) is None


def test_dref3_row_keeps_active_sectors_and_drops_empty_ones():
    parsed = parse_stage(
        {
            "id": "Dref-1",
            "appeal_code": "mdrzz001",
            "appeal_type": "DREF",
            "pillar": "Response",
            "country_iso3": "zzz",
            "sector_health": True,
            "sector_health_budget": "1500.5",
            "sector_health_people_targeted": 40,
            "sector_education": False,
            "is_latest_stage": True,
            "total_approved": 10000,
            "start_date_of_operation": "2026-01-01",
            "end_date_of_operation": "2026-06-30",
        }
    )
    assert parsed["appeal_code"] == "MDRZZ001"
    assert parsed["country_iso3"] == "ZZZ"
    assert [item["key"] for item in parsed["sectors"]] == ["health"]
    assert is_imminent("i-DREF", "Response")
    assert not is_imminent("DREF", "Response")


def test_draft_template_does_not_print_missing_numbers_as_none():
    from plugins.dref_monitoring.services.drafts import render_template_body

    body = render_template_body(
        {
            "appeal_code": "MDRZZ001",
            "expenditure_note": "Indicative.",
            "sectors": [
                {
                    "label": "Health",
                    "budget_chf": None,
                    "people_targeted": None,
                    "activities": [
                        {
                            "title": "Deliver Health",
                            "status": "planned",
                            "people_reached": None,
                            "expenditure_chf": None,
                            "indicators": [{"title": "People reached", "target": None, "actual": None}],
                        }
                    ],
                }
            ],
        },
        "final_report",
    )
    assert "None" not in body
    assert "not reported" in body


def test_future_open_period_shows_upcoming():
    from types import SimpleNamespace

    from plugins.dref_monitoring.services.reporting import reporting_period_badge

    today = date(2026, 11, 19)
    future = SimpleNamespace(status="open", start_date=date(2027, 4, 1))
    current = SimpleNamespace(status="open", start_date=date(2026, 11, 1))
    draft = SimpleNamespace(status="draft")
    filed = SimpleNamespace(status="submitted")
    assert reporting_period_badge(future, None, today) == "upcoming"
    assert reporting_period_badge(future, draft, today) == "upcoming"
    assert reporting_period_badge(future, filed, today) == "submitted"
    assert reporting_period_badge(current, None, today) == "open"
    assert reporting_period_badge(current, draft, today) == "draft"
    assert reporting_period_badge(SimpleNamespace(status="overdue", start_date=date(2026, 8, 1)), None, today) == "overdue"
