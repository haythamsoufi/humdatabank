"""Extended unit tests for api_usage_stats covering missing branches."""

from datetime import timedelta
from unittest.mock import patch

import pytest

from app.models.api_usage import APIUsage
from app.services.api_usage_stats import (
    _fill_daily_buckets,
    _fill_hourly_buckets,
    _fill_monthly_buckets,
    _group_counts_by_day,
    _group_counts_by_hour,
    _group_counts_by_month,
    bulk_endpoint_usage_stats,
    chart_stats_for_period,
    endpoint_path_prefix,
    subtract_months,
)
from app.utils.datetime_helpers import utcnow


# ---------------------------------------------------------------------------
# endpoint_path_prefix
# ---------------------------------------------------------------------------

def test_endpoint_path_prefix_no_variable():
    assert endpoint_path_prefix('/api/v1/data') == '/api/v1/data'


def test_endpoint_path_prefix_curly_brace():
    assert endpoint_path_prefix('/api/v1/data/{id}/sub') == '/api/v1/data/'


def test_endpoint_path_prefix_angle_bracket():
    assert endpoint_path_prefix('/x/<pk>') == '/x/'


# ---------------------------------------------------------------------------
# subtract_months
# ---------------------------------------------------------------------------

def test_subtract_months_same_year():
    dt = utcnow().replace(month=6, day=15)
    result = subtract_months(dt, 3)
    assert result.month == 3
    assert result.year == dt.year


def test_subtract_months_clamps_day():
    """Subtracting 1 month from March 31 should produce Feb 28/29."""
    dt = utcnow().replace(month=3, day=31)
    result = subtract_months(dt, 1)
    assert result.month == 2
    assert result.day in (28, 29)


def test_subtract_months_multi_year_boundary():
    dt = utcnow().replace(month=1, day=15)
    result = subtract_months(dt, 13)
    assert result.month == 12
    assert result.year == dt.year - 2


# ---------------------------------------------------------------------------
# _group_counts_by_hour / _group_counts_by_day / _group_counts_by_month
# ---------------------------------------------------------------------------

def test_group_counts_by_hour_empty():
    assert _group_counts_by_hour([]) == {}


def test_group_counts_by_hour_counts():
    now = utcnow()
    ts = [now, now, now.replace(hour=(now.hour + 1) % 24)]
    counts = _group_counts_by_hour(ts)
    assert sum(counts.values()) == 3


def test_group_counts_by_day_empty():
    assert _group_counts_by_day([]) == {}


def test_group_counts_by_day_counts():
    now = utcnow()
    ts = [now, now - timedelta(days=1), now - timedelta(days=1)]
    counts = _group_counts_by_day(ts)
    assert sum(counts.values()) == 3
    assert len(counts) == 2


def test_group_counts_by_month_empty():
    assert _group_counts_by_month([]) == {}


def test_group_counts_by_month_counts():
    now = utcnow()
    ts = [now, now, subtract_months(now, 1)]
    counts = _group_counts_by_month(ts)
    assert sum(counts.values()) == 3


# ---------------------------------------------------------------------------
# _fill_hourly_buckets
# ---------------------------------------------------------------------------

def test_fill_hourly_buckets_length():
    result = _fill_hourly_buckets({})
    assert len(result) == 24
    assert all(r['count'] == 0 for r in result)


def test_fill_hourly_buckets_with_data():
    now = utcnow()
    key = now.strftime('%H:00')
    result = _fill_hourly_buckets({key: 5})
    counts = {r['label']: r['count'] for r in result}
    assert counts[key] == 5


# ---------------------------------------------------------------------------
# _fill_daily_buckets
# ---------------------------------------------------------------------------

def test_fill_daily_buckets_length():
    result = _fill_daily_buckets({}, days=7)
    assert len(result) == 7
    assert all(r['count'] == 0 for r in result)


def test_fill_daily_buckets_with_data():
    now = utcnow()
    key = now.strftime('%Y-%m-%d')
    result = _fill_daily_buckets({key: 3}, days=30)
    counts = {r['label']: r['count'] for r in result}
    assert counts[key] == 3


# ---------------------------------------------------------------------------
# _fill_monthly_buckets
# ---------------------------------------------------------------------------

def test_fill_monthly_buckets_length():
    result = _fill_monthly_buckets({}, months=12)
    assert len(result) == 12
    assert all(r['count'] == 0 for r in result)


def test_fill_monthly_buckets_with_data():
    now = utcnow()
    key = now.strftime('%Y-%m')
    result = _fill_monthly_buckets({key: 7}, months=12)
    counts = {r['label']: r['count'] for r in result}
    assert counts[key] == 7


# ---------------------------------------------------------------------------
# bulk_endpoint_usage_stats – empty / zero-total branches
# ---------------------------------------------------------------------------

def test_bulk_endpoint_usage_stats_empty_prefixes(app, db_session):
    result = bulk_endpoint_usage_stats([])
    assert result == {}


def test_bulk_endpoint_usage_stats_no_matching_data(app, db_session):
    result = bulk_endpoint_usage_stats(['/api/v1/nonexistent'])
    assert result['/api/v1/nonexistent']['total_requests'] == 0
    assert result['/api/v1/nonexistent']['success_rate'] == 100.0


def test_bulk_endpoint_usage_stats_deduplicates_prefixes(app, db_session):
    """Duplicate prefixes in the input should appear only once in the result."""
    result = bulk_endpoint_usage_stats(['/api/v1/x', '/api/v1/x'])
    assert list(result.keys()) == ['/api/v1/x']


# ---------------------------------------------------------------------------
# chart_stats_for_period – all branches
# ---------------------------------------------------------------------------

def test_chart_stats_for_period_daily(app, db_session):
    now = utcnow()
    db_session.add(
        APIUsage(
            api_endpoint='/api/v1/data',
            ip_address='10.0.0.1',
            method='GET',
            status_code=200,
            response_time=1.0,
            timestamp=now - timedelta(hours=1),
        )
    )
    db_session.commit()

    from app.models.api_usage import APIUsage as UsageModel
    base_query = UsageModel.query.filter(UsageModel.api_endpoint.like('/api/%'))
    stats = chart_stats_for_period(base_query, 'daily')
    assert len(stats) == 24
    assert sum(r['count'] for r in stats) >= 1


def test_chart_stats_for_period_weekly(app, db_session):
    now = utcnow()
    db_session.add(
        APIUsage(
            api_endpoint='/api/v1/data',
            ip_address='10.0.0.2',
            method='POST',
            status_code=201,
            response_time=2.0,
            timestamp=now - timedelta(days=3),
        )
    )
    db_session.commit()

    from app.models.api_usage import APIUsage as UsageModel
    base_query = UsageModel.query.filter(UsageModel.api_endpoint.like('/api/%'))
    stats = chart_stats_for_period(base_query, 'weekly')
    assert len(stats) == 7
    assert sum(r['count'] for r in stats) >= 1


def test_chart_stats_for_period_monthly(app, db_session):
    from app.models.api_usage import APIUsage as UsageModel
    base_query = UsageModel.query.filter(UsageModel.api_endpoint.like('/api/%'))
    stats = chart_stats_for_period(base_query, 'monthly')
    assert len(stats) == 30


def test_chart_stats_for_period_yearly(app, db_session):
    now = utcnow()
    db_session.add(
        APIUsage(
            api_endpoint='/api/v1/templates',
            ip_address='10.0.0.3',
            method='GET',
            status_code=200,
            response_time=3.0,
            timestamp=now - timedelta(days=200),
        )
    )
    db_session.commit()

    from app.models.api_usage import APIUsage as UsageModel
    base_query = UsageModel.query.filter(UsageModel.api_endpoint.like('/api/%'))
    stats = chart_stats_for_period(base_query, 'yearly')
    assert len(stats) == 12
