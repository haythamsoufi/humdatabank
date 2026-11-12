"""Tests for reporting_period_label_parser."""

from datetime import date

import pytest

from app.utils.indicators.reporting_period_label_parser import (
    parse_period_label,
    parse_structured_period_label,
)

pytestmark = pytest.mark.unit


class TestParsePeriodLabel:
    def test_annual_single_year(self):
        assert parse_period_label("2024") == (
            "annual",
            date(2024, 1, 1),
            date(2024, 12, 31),
        )

    def test_custom_year_span(self):
        assert parse_period_label("2023-2024") == (
            "custom",
            date(2023, 1, 1),
            date(2024, 12, 31),
        )

    def test_quarterly_label(self):
        assert parse_period_label("Q1 2024") == (
            "quarterly",
            date(2024, 1, 1),
            date(2024, 3, 31),
        )

    def test_month_range_same_year(self):
        assert parse_period_label("Jan-Jun 2026") == (
            "monthly",
            date(2026, 1, 1),
            date(2026, 6, 30),
        )

    def test_single_month(self):
        assert parse_period_label("Mar 2026") == (
            "monthly",
            date(2026, 3, 1),
            date(2026, 3, 31),
        )
        assert parse_period_label("Feb 2024") == (
            "monthly",
            date(2024, 2, 1),
            date(2024, 2, 29),
        )

    def test_unparseable_labels(self):
        assert parse_period_label("Self-Reported") is None
        assert parse_period_label("") is None


class TestParseStructuredPeriodLabel:
    def test_picker_labels(self):
        assert parse_structured_period_label("2027") == (
            "annual",
            date(2027, 1, 1),
            date(2027, 12, 31),
        )
        assert parse_structured_period_label("2024-2025") == (
            "custom",
            date(2024, 1, 1),
            date(2025, 12, 31),
        )
        assert parse_structured_period_label("Jan-Jun 2023") == (
            "monthly",
            date(2023, 1, 1),
            date(2023, 6, 30),
        )
        assert parse_structured_period_label("Jan 2024-Mar 2025") == (
            "monthly",
            date(2024, 1, 1),
            date(2025, 3, 31),
        )
        assert parse_structured_period_label("Mar 2026") == (
            "monthly",
            date(2026, 3, 1),
            date(2026, 3, 31),
        )

    def test_rejects_text_that_only_contains_a_year(self):
        assert parse_structured_period_label("TestPeriod2024") is None
        assert parse_structured_period_label("Self-Reported") is None
        assert parse_structured_period_label("Q1 2024") is None
