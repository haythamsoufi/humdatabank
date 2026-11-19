"""Core cycle phase: which reporting windows a presentation includes by default."""

import datetime as dt

from types import SimpleNamespace

from app.services.projects.service import (
    assignment_display_status,
    assignment_is_upcoming_cycle,
    cycle_phase,
    cycle_selected_by_default,
)

START = dt.date(2026, 12, 21)
END = dt.date(2027, 3, 20)


def test_cycle_before_start_is_upcoming():
    assert cycle_phase(START, END, dt.date(2026, 12, 20)) == "upcoming"


def test_cycle_inside_window_is_active_including_both_ends():
    assert cycle_phase(START, END, START) == "active"
    assert cycle_phase(START, END, dt.date(2027, 1, 15)) == "active"
    assert cycle_phase(START, END, END) == "active"


def test_cycle_after_end_is_passed():
    assert cycle_phase(START, END, dt.date(2027, 3, 21)) == "passed"


def test_cycle_without_dates_is_active_and_datetimes_are_accepted():
    assert cycle_phase(None, None, dt.date(2027, 1, 1)) == "active"
    assert cycle_phase(dt.datetime(2026, 1, 1, 9), dt.datetime(2026, 2, 1, 9), dt.date(2026, 3, 1)) == "passed"


def test_presentations_select_active_and_passed_only():
    assert cycle_selected_by_default("active") is True
    assert cycle_selected_by_default("passed") is True
    assert cycle_selected_by_default("upcoming") is False


def _cycle(start, end, status="pending", project_cycle=True):
    return SimpleNamespace(
        status=status,
        assigned_form=SimpleNamespace(
            is_project_cycle=project_cycle,
            period_start=start,
            period_end=end,
        ),
    )


def test_pending_project_cycle_before_its_window_displays_as_upcoming():
    aes = _cycle(dt.date(2099, 4, 1), dt.date(2099, 4, 30))
    assert assignment_is_upcoming_cycle(aes) is True
    assert assignment_display_status(aes) == "upcoming"


def test_pending_project_cycle_inside_its_window_stays_pending():
    aes = _cycle(dt.date(2000, 1, 1), dt.date(2099, 1, 1))
    assert assignment_is_upcoming_cycle(aes) is False
    assert assignment_display_status(aes) == "pending"


def test_started_work_on_a_future_cycle_keeps_its_workflow_status():
    aes = _cycle(dt.date(2099, 4, 1), dt.date(2099, 4, 30), status="in_progress")
    assert assignment_is_upcoming_cycle(aes) is False
    assert assignment_display_status(aes) == "in_progress"


def test_campaign_assignment_is_not_an_upcoming_cycle():
    aes = _cycle(dt.date(2099, 4, 1), dt.date(2099, 4, 30), project_cycle=False)
    assert assignment_is_upcoming_cycle(aes) is False
