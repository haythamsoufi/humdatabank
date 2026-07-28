"""Unit tests for API usage aggregation helpers."""

from datetime import timedelta

import pytest

from app.models.api_key_management import APIKey
from app.models.api_usage import APIUsage
from app.services.platform.api_usage_stats import (
    bulk_endpoint_usage_stats,
    chart_stats_for_period,
    endpoint_path_prefix,
    subtract_months,
)
from app.utils.datetime_helpers import utcnow


def test_generate_key_id_is_independent_of_secret():
    full_key, key_id, key_hash, key_prefix = APIKey.generate_key()
    assert full_key not in key_id
    assert key_id not in full_key
    assert key_prefix == full_key[:8]
    assert len(key_hash) == 64


def test_endpoint_path_prefix_strips_flask_variables():
    assert endpoint_path_prefix('/api/v1/data/<template_id>') == '/api/v1/data/'
    assert endpoint_path_prefix('/api/v1/data/{template_id}') == '/api/v1/data/'


def test_bulk_endpoint_usage_stats_aggregates_by_prefix(app, db_session):
    now = utcnow()
    db_session.add_all([
        APIUsage(
            api_endpoint='/api/v1/data',
            ip_address='127.0.0.1',
            method='GET',
            status_code=200,
            response_time=12.0,
            timestamp=now,
        ),
        APIUsage(
            api_endpoint='/api/v1/data/extra',
            ip_address='127.0.0.1',
            method='GET',
            status_code=500,
            response_time=20.0,
            timestamp=now,
        ),
        APIUsage(
            api_endpoint='/api/v1/templates',
            ip_address='127.0.0.1',
            method='GET',
            status_code=200,
            response_time=8.0,
            timestamp=now,
        ),
    ])
    db_session.commit()

    stats = bulk_endpoint_usage_stats(['/api/v1/data', '/api/v1/templates'])
    assert stats['/api/v1/data']['total_requests'] == 2
    assert stats['/api/v1/data']['success_rate'] == 50.0
    assert stats['/api/v1/templates']['total_requests'] == 1


def test_subtract_months_handles_year_boundary():
    dt = utcnow().replace(month=2, day=28, hour=12, minute=0, second=0, microsecond=0)
    shifted = subtract_months(dt, 2)
    assert shifted.month == 12
    assert shifted.year == dt.year - 1


def test_chart_stats_for_period_quarterly_returns_90_days(app, db_session):
    now = utcnow()
    db_session.add(
        APIUsage(
            api_endpoint='/api/v1/data',
            ip_address='127.0.0.1',
            method='GET',
            status_code=200,
            response_time=5.0,
            timestamp=now - timedelta(days=10),
        )
    )
    db_session.commit()

    from app.models.api_usage import APIUsage as UsageModel
    base_query = UsageModel.query.filter(UsageModel.api_endpoint.like('/api/%'))
    stats = chart_stats_for_period(base_query, 'quarterly')
    assert len(stats) == 90
    assert sum(row['count'] for row in stats) >= 1
