"""
Unit tests for app/utils/datetime_helpers.py – 100% coverage target.
"""
import pytest
from datetime import datetime, timezone, timedelta

from app.utils.datetime_helpers import (
    ORG_TIMEZONE_LABEL,
    ORG_TIMEZONE_NAME,
    ensure_utc,
    format_in_org_timezone,
    get_org_timezone,
    get_timezone,
    isoformat_utc,
    now_in_org_timezone,
    org_day_start_utc,
    utcnow,
)


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


@pytest.mark.unit
class TestOrgTimezone:
    def test_constants(self):
        assert ORG_TIMEZONE_NAME == "Europe/Zurich"
        assert ORG_TIMEZONE_LABEL == "Geneva"

    def test_get_org_timezone(self):
        tz = get_org_timezone()
        assert tz is not None

    def test_now_in_org_timezone_is_aware(self):
        result = now_in_org_timezone()
        assert result.tzinfo is not None

    def test_org_day_start_utc_is_utc(self):
        start = org_day_start_utc()
        assert start.tzinfo == timezone.utc

    def test_format_in_org_timezone_none(self):
        assert format_in_org_timezone(None) == ""

    def test_format_in_org_timezone_utc_input(self):
        dt = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
        result = format_in_org_timezone(dt)
        assert ORG_TIMEZONE_LABEL in result

    def test_get_timezone_invalid_falls_back_to_utc(self):
        tz = get_timezone("Not/A_Real_Zone")
        assert tz == timezone.utc
