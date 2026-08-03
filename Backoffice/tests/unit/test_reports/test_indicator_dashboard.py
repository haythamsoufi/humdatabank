"""Tests for indicator dashboard aggregation and helpers."""

from __future__ import annotations

import pytest

from app.services.reports.indicator_dashboard_helpers import (
    NS_TABLE_NS_UNIT,
    NS_TABLE_STANDARD,
    dashboard_table_rows,
    ns_table_mode,
)

pytestmark = pytest.mark.unit


def test_ns_table_mode_distinct_ns():
    assert ns_table_mode("Distinct", "NSs") == "implementing_count"


def test_ns_table_mode_cumulative_ns_unit():
    assert ns_table_mode("Cumulative", "NS") == NS_TABLE_NS_UNIT


def test_ns_table_mode_standard():
    assert ns_table_mode("Cumulative", "People") == NS_TABLE_STANDARD


def test_dashboard_table_rows_standard():
    assert dashboard_table_rows(ns_table_mode=NS_TABLE_STANDARD) == (True, True)


def test_dashboard_table_rows_ns_unit_hides_implementing():
    assert dashboard_table_rows(ns_table_mode=NS_TABLE_NS_UNIT) == (True, False)
