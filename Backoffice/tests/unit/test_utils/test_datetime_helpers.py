"""
Unit tests for app/utils/datetime_helpers.py – 100% coverage target.
"""
import pytest
from datetime import datetime, timezone, timedelta

from app.utils.datetime_helpers import utcnow, isoformat_utc, ensure_utc


@pytest.mark.unit
class TestUtcnow:
    def test_returns_datetime(self):
        result = utcnow()
        assert isinstance(result, datetime)

    def test_is_timezone_aware(self):
        result = utcnow()
        assert result.tzinfo is not None

    def test_timezone_is_utc(self):
        result = utcnow()
        assert result.utcoffset() == timedelta(0)

    def test_is_recent(self):
        result = utcnow()
        now = datetime.now(timezone.utc)
        diff = abs((now - result).total_seconds())
        assert diff < 5


@pytest.mark.unit
class TestIsoformatUtc:
    def test_returns_string(self):
        result = isoformat_utc()
        assert isinstance(result, str)

    def test_contains_timezone_offset(self):
        result = isoformat_utc()
        # ISO format with UTC tz should contain '+00:00'
        assert '+00:00' in result or result.endswith('Z')

    def test_is_parseable_iso8601(self):
        result = isoformat_utc()
        parsed = datetime.fromisoformat(result)
        assert parsed.tzinfo is not None


@pytest.mark.unit
class TestEnsureUtc:
    def test_none_returns_none(self):
        assert ensure_utc(None) is None

    def test_naive_datetime_gets_utc_tzinfo(self):
        naive = datetime(2023, 6, 15, 12, 0, 0)
        result = ensure_utc(naive)
        assert result.tzinfo is not None
        assert result.utcoffset() == timedelta(0)

    def test_naive_datetime_value_unchanged(self):
        naive = datetime(2023, 6, 15, 12, 30, 45)
        result = ensure_utc(naive)
        assert result.year == 2023
        assert result.month == 6
        assert result.day == 15
        assert result.hour == 12
        assert result.minute == 30
        assert result.second == 45

    def test_aware_utc_datetime_returned_unchanged(self):
        aware = datetime(2023, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = ensure_utc(aware)
        assert result == aware
        assert result.utcoffset() == timedelta(0)

    def test_aware_non_utc_datetime_converted_to_utc(self):
        # UTC+5 timezone
        tz_plus5 = timezone(timedelta(hours=5))
        aware = datetime(2023, 6, 15, 17, 0, 0, tzinfo=tz_plus5)
        result = ensure_utc(aware)
        assert result.utcoffset() == timedelta(0)
        # 17:00 UTC+5 == 12:00 UTC
        assert result.hour == 12

    def test_aware_negative_offset_converted_to_utc(self):
        tz_minus3 = timezone(timedelta(hours=-3))
        aware = datetime(2023, 6, 15, 9, 0, 0, tzinfo=tz_minus3)
        result = ensure_utc(aware)
        assert result.utcoffset() == timedelta(0)
        # 09:00 UTC-3 == 12:00 UTC
        assert result.hour == 12
