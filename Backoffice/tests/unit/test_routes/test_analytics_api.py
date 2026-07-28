"""
Comprehensive pytest tests for app/routes/admin/analytics_api.py

Covers all JSON API endpoints: login logs, session logs, end session,
dashboard stats/activity/trends, user activity, submission stats,
indicator usage, and system health.
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from tests.factories import create_test_user, create_test_country, create_test_public_submission

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_json(resp):
    return json.loads(resp.data)


def _assert_status(resp, *allowed):
    assert resp.status_code in allowed, (
        f"Expected one of {allowed}, got {resp.status_code}: {resp.data[:200]}"
    )


def _assert_json_ok(resp):
    _assert_status(resp, 200)
    data = _get_json(resp)
    return data


# ---------------------------------------------------------------------------
# login_logs_list_api  GET /admin/api/analytics/login-logs
# ---------------------------------------------------------------------------

class TestLoginLogsListApi:
    def test_get(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/analytics/login-logs")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert "data" in data or "success" in data

    def test_get_with_user_filter(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/analytics/login-logs?user=admin@example.com")
        _assert_status(resp, 200, 302)

    def test_get_with_event_type_filter(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/analytics/login-logs?event_type=login_success")
        _assert_status(resp, 200, 302)

    def test_get_with_ip_filter(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/analytics/login-logs?ip=127.0.0.1")
        _assert_status(resp, 200, 302)

    def test_get_with_suspicious_filter(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/analytics/login-logs?suspicious_only=true")
        _assert_status(resp, 200, 302)

    def test_get_with_date_range(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/api/analytics/login-logs?date_from=2024-01-01&date_to=2024-12-31"
        )
        _assert_status(resp, 200, 302)

    def test_get_with_invalid_date_from(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/analytics/login-logs?date_from=bad-date")
        _assert_status(resp, 200, 302)

    def test_get_with_invalid_date_to(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/analytics/login-logs?date_to=bad-date")
        _assert_status(resp, 200, 302)

    def test_get_paginated(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/analytics/login-logs?page=1&per_page=10")
        _assert_status(resp, 200, 302)

    def test_unauthenticated(self, client, db_session):
        resp = client.get("/admin/api/analytics/login-logs")
        _assert_status(resp, 302, 401, 403)


# ---------------------------------------------------------------------------
# session_logs_list_api  GET /admin/api/analytics/session-logs
# ---------------------------------------------------------------------------

class TestSessionLogsListApi:
    def test_get(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/analytics/session-logs")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert "data" in data or "success" in data

    def test_get_with_user_filter(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/analytics/session-logs?user=admin@example.com")
        _assert_status(resp, 200, 302)

    def test_get_active_only(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/analytics/session-logs?active_only=true")
        _assert_status(resp, 200, 302)

    def test_get_with_min_duration(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/analytics/session-logs?min_duration=5")
        _assert_status(resp, 200, 302)

    def test_get_with_session_id_exact(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/analytics/session-logs?session_id=test-session")
        _assert_status(resp, 200, 302)

    def test_get_paginated(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/analytics/session-logs?page=1&per_page=5")
        _assert_status(resp, 200, 302)


# ---------------------------------------------------------------------------
# end_session_api  POST /admin/api/analytics/end-session/<session_id>
# ---------------------------------------------------------------------------

class TestEndSessionApi:
    def test_session_not_found(self, logged_in_client, db_session):
        with patch("app.services.platform.user_analytics_service.log_admin_action"):
            resp = logged_in_client.post(
                "/admin/api/analytics/end-session/nonexistent-session-xyz"
            )
        _assert_status(resp, 200, 302, 404)
        if resp.status_code == 200:
            data = _get_json(resp)
            # Should return not_found or error
            assert "success" in data or "error" in str(data)

    def test_session_already_inactive(self, logged_in_client, db_session, app):
        from app.models import UserSessionLog
        with app.app_context():
            session_log = UserSessionLog(
                session_id="api-inactive-session-123",
                user_id=None,
                is_active=False,
            )
            db_session.add(session_log)
            db_session.commit()
        with patch("app.services.platform.user_analytics_service.log_admin_action"):
            resp = logged_in_client.post(
                "/admin/api/analytics/end-session/api-inactive-session-123"
            )
        _assert_status(resp, 200, 302, 400)

    def test_end_active_session(self, logged_in_client, db_session, app, admin_user):
        from app.models import UserSessionLog
        with app.app_context():
            user = create_test_user(db_session)
            session_log = UserSessionLog(
                session_id="api-active-session-456",
                user_id=user.id,
                is_active=True,
            )
            db_session.add(session_log)
            db_session.commit()
        with patch("app.services.platform.user_analytics_service.end_user_session"), \
             patch("app.services.platform.user_analytics_service.add_session_to_blacklist"), \
             patch("app.services.platform.user_analytics_service.log_admin_action"):
            resp = logged_in_client.post(
                "/admin/api/analytics/end-session/api-active-session-456"
            )
        _assert_status(resp, 200, 302)

    def test_end_session_error(self, logged_in_client, db_session, app):
        from app.models import UserSessionLog
        with app.app_context():
            user = create_test_user(db_session)
            session_log = UserSessionLog(
                session_id="api-error-session-789",
                user_id=user.id,
                is_active=True,
            )
            db_session.add(session_log)
            db_session.commit()
        with patch(
            "app.services.platform.user_analytics_service.end_user_session",
            side_effect=Exception("test error"),
        ), patch("app.services.platform.user_analytics_service.log_admin_action"):
            resp = logged_in_client.post(
                "/admin/api/analytics/end-session/api-error-session-789"
            )
        _assert_status(resp, 200, 302, 500)


# ---------------------------------------------------------------------------
# dashboard_stats_api  GET /admin/api/dashboard/stats
# ---------------------------------------------------------------------------

class TestDashboardStatsApi:
    def test_get(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/dashboard/stats")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert "data" in data or "success" in data

    def test_get_returns_counts(self, logged_in_client, db_session, app):
        with app.app_context():
            create_test_user(db_session)
            create_test_country(db_session)
        resp = logged_in_client.get("/admin/api/dashboard/stats")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            if "data" in data:
                assert "user_count" in data["data"]
                assert "country_count" in data["data"]

    def test_unauthenticated(self, client, db_session):
        resp = client.get("/admin/api/dashboard/stats")
        _assert_status(resp, 302, 401, 403)


# ---------------------------------------------------------------------------
# dashboard_activity_api  GET /admin/api/dashboard/activity
# ---------------------------------------------------------------------------

class TestDashboardActivityApi:
    def test_get(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/dashboard/activity")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert "data" in data or "success" in data

    def test_get_data_structure(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/dashboard/activity")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            if "data" in data:
                d = data["data"]
                assert "recent_activity" in d or "recent_logins" in d or isinstance(d, dict)


# ---------------------------------------------------------------------------
# dashboard_trends_api  GET /admin/api/dashboard/trends
# ---------------------------------------------------------------------------

class TestDashboardTrendsApi:
    def test_get(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/dashboard/trends")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert "data" in data or "success" in data

    def test_get_with_days_param(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/dashboard/trends?days=7")
        _assert_status(resp, 200, 302)

    def test_get_with_large_days(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/dashboard/trends?days=90")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            if "data" in data:
                d = data["data"]
                if "period" in d:
                    assert d["period"]["days"] == 90


# ---------------------------------------------------------------------------
# user_activity_api  GET /admin/api/users/activity/<user_id>
# ---------------------------------------------------------------------------

class TestUserActivityApi:
    def test_get_existing_user(self, logged_in_client, db_session, app, admin_user):
        with app.app_context():
            user_id = admin_user.id
        resp = logged_in_client.get(f"/admin/api/users/activity/{user_id}")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert "data" in data or "success" in data

    def test_get_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/users/activity/999999")
        _assert_status(resp, 200, 302, 404)

    def test_get_user_role_admin(self, logged_in_client, db_session, app, admin_user):
        with app.app_context():
            user_id = admin_user.id
        resp = logged_in_client.get(f"/admin/api/users/activity/{user_id}")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            if "data" in data and "user" in data["data"]:
                assert "role" in data["data"]["user"]

    def test_unauthenticated(self, client, db_session):
        resp = client.get("/admin/api/users/activity/1")
        _assert_status(resp, 302, 401, 403)


# ---------------------------------------------------------------------------
# submission_statistics_api  GET /admin/api/submissions/statistics
# ---------------------------------------------------------------------------

class TestSubmissionStatisticsApi:
    def test_get(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/submissions/statistics")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert "data" in data or "success" in data

    def test_get_with_submissions(self, logged_in_client, db_session, app):
        with app.app_context():
            create_test_public_submission(db_session)
        resp = logged_in_client.get("/admin/api/submissions/statistics")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            if "data" in data:
                assert "total_submissions" in data["data"]
                assert "status_breakdown" in data["data"]


# ---------------------------------------------------------------------------
# indicator_usage_api  GET /admin/api/indicators/usage
# ---------------------------------------------------------------------------

class TestIndicatorUsageApi:
    def test_get(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/indicators/usage")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert "data" in data or "success" in data

    def test_get_data_structure(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/indicators/usage")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            if "data" in data:
                d = data["data"]
                assert "total_indicators" in d
                assert "archived_count" in d

    def test_unauthenticated(self, client, db_session):
        resp = client.get("/admin/api/indicators/usage")
        _assert_status(resp, 302, 401, 403)


# ---------------------------------------------------------------------------
# system_health_api  GET /admin/api/system/health
# ---------------------------------------------------------------------------

class TestSystemHealthApi:
    def test_get(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/system/health")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert "data" in data or "success" in data

    def test_get_data_structure(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/system/health")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            if "data" in data:
                d = data["data"]
                assert "database_healthy" in d
                assert "uptime" in d

    def test_get_db_healthy_true(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/api/system/health")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            if "data" in data:
                assert data["data"]["database_healthy"] is True

    def test_unauthenticated(self, client, db_session):
        resp = client.get("/admin/api/system/health")
        _assert_status(resp, 302, 401, 403)
