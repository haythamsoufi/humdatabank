"""Unit tests for product analytics aggregation."""

from __future__ import annotations

import pytest

from app.services.platform import product_analytics_service as svc

pytestmark = [pytest.mark.unit]


class TestClassifyUserType:
    def test_ns_from_country_entity(self):
        assert svc.classify_user_type(
            "focal@example.org",
            {"country"},
            {"assignment_editor_submitter"},
        ) == "National Society"

    def test_secretariat_from_division(self):
        assert svc.classify_user_type(
            "someone@example.org",
            {"division"},
            {"admin_core"},
        ) == "Secretariat staff"

    def test_ifrc_email_without_entities(self):
        assert svc.classify_user_type(
            "person@ifrc.org",
            set(),
            set(),
        ) == "Secretariat staff"

    def test_ifrc_email_with_country_scope_is_secretariat(self):
        assert svc.classify_user_type(
            "delegate@ifrc.org",
            {"country"},
            {"assignment_editor_submitter"},
        ) == "Secretariat staff (mixed access)"

    def test_to_ifrc_vs_ns(self):
        assert svc.to_ifrc_vs_ns("Secretariat staff") == "IFRC"
        assert svc.to_ifrc_vs_ns("Secretariat staff (mixed access)") == "IFRC"
        assert svc.to_ifrc_vs_ns("National Society") == "NS"
        assert svc.to_ifrc_vs_ns("National Society (mixed access)") == "NS"
        assert svc.to_ifrc_vs_ns("Unclassified") == "Unclassified"

    def test_classify_ifrc_vs_ns_email_beats_country_entity(self):
        assert svc.classify_ifrc_vs_ns(
            "delegate@ifrc.org",
            {"country"},
            {"assignment_editor_submitter"},
        ) == "IFRC"

    def test_classify_ifrc_vs_ns_ns_focal(self):
        assert svc.classify_ifrc_vs_ns(
            "focal@example.org",
            {"country"},
            {"assignment_editor_submitter"},
        ) == "NS"

    def test_classify_ifrc_vs_ns_redcross_domain_alone_is_ns_if_country(self):
        # National Society redcross domains must not count as IFRC.
        assert svc.classify_ifrc_vs_ns(
            "user@redcross.org.uk",
            {"country"},
            set(),
        ) == "NS"


class TestWorkdayHelpers:
    def test_weekend_key_is_none(self):
        from datetime import datetime, timezone

        sat = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)  # Saturday
        sun = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)  # Sunday
        mon = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)  # Monday
        assert svc._workday_key(sat) is None
        assert svc._workday_key(sun) is None
        assert svc._workday_key(mon) == "2026-10-26"

    def test_count_workdays_excludes_weekend(self):
        from datetime import datetime, timezone

        # Fri 2026-10-23 00:00 → Mon 2026-10-26 00:00 covers Fri only in [start, end)
        # Use a full week Mon–next Mon
        start = datetime(2026, 10, 19, 0, 0, tzinfo=timezone.utc)  # Monday
        end = datetime(2026, 10, 26, 0, 0, tzinfo=timezone.utc)  # next Monday
        assert svc._count_workdays(start, end) == 5


class TestFrequencyThresholds:
    def test_thirty_day_window(self):
        daily, weekly, labels = svc._frequency_thresholds(30, workdays=22)
        assert daily == 15
        assert weekly == 4
        assert "Daily" in labels[0]
        assert "workdays" in labels[0]

    def test_seven_day_window(self):
        daily, weekly, labels = svc._frequency_thresholds(7, workdays=5)
        assert daily == 4  # miss at most one workday
        assert weekly == 2
        assert labels[0].startswith("Near-daily")
        assert "workdays" in labels[0]


class TestGetProductAnalytics:
    def test_empty_db_shape(self, app, db_session):
        with app.app_context():
            result = svc.get_product_analytics(days=30)
        assert result["mau"]["unique_users"] == 0
        assert result["window_days"] == 30
        assert "frequency" in result
        assert "active_users" in result
        assert result["active_users"]["labels"] == [
            "DAU (1 day)",
            "WAU (7 days)",
            "MAU (30 days)",
        ]
        assert result["active_users"]["counts"] == [0, 0, 0]
        assert result["active_users"]["dau"] == 0
        assert result["active_users"]["wau"] == 0
        assert result["active_users"]["mau_30d"] == 0
        assert "user_types" in result
        assert result["user_types"]["labels"] == ["IFRC", "NS"]
        assert result["user_types"]["counts"] == [0, 0]
        assert "geographic" in result
        assert "monthly" in result
        assert isinstance(result["monthly"]["series"], list)
        assert isinstance(result["frequency"]["buckets"], list)
        assert len(result["frequency"]["buckets"]) == 3
