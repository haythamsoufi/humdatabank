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


class TestFrequencyThresholds:
    def test_thirty_day_window(self):
        daily, weekly, labels = svc._frequency_thresholds(30)
        assert daily == 20
        assert weekly == 4
        assert "Daily" in labels[0]

    def test_seven_day_window(self):
        daily, weekly, labels = svc._frequency_thresholds(7)
        assert daily == 5
        assert weekly == 2
        assert labels[0].startswith("Near-daily")


class TestGetProductAnalytics:
    def test_empty_db_shape(self, app, db_session):
        with app.app_context():
            result = svc.get_product_analytics(days=30)
        assert result["mau"]["unique_users"] == 0
        assert result["window_days"] == 30
        assert "frequency" in result
        assert "user_types" in result
        assert "geographic" in result
        assert "monthly" in result
        assert isinstance(result["monthly"]["series"], list)
        assert isinstance(result["frequency"]["buckets"], list)
        assert len(result["frequency"]["buckets"]) == 3
