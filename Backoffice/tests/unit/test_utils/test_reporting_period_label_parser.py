"""Tests for reporting_period_label_parser (maintenance scripts only)."""

from datetime import date

import pytest

from app.utils.reporting_period_label_parser import parse_period_label

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

    def test_unparseable_labels(self):
        assert parse_period_label("Self-Reported") is None
        assert parse_period_label("") is None
