"""Core cycle phase: which reporting windows a presentation includes by default."""

import datetime as dt

from app.services.projects.service import cycle_phase, cycle_selected_by_default

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
