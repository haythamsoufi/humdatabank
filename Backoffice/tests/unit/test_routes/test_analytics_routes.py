"""
Comprehensive pytest tests for app/routes/admin/analytics.py

Covers analytics dashboard, audit trail, login/activity/session/security logs,
user analytics, chart endpoints, and cleanup operations.
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from tests.factories import create_test_country, create_test_user

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


# ---------------------------------------------------------------------------
# analytics_dashboard
# ---------------------------------------------------------------------------

class TestAnalyticsDashboard:
    def test_get(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/dashboard")
        _assert_status(resp, 200, 302)

    def test_get_with_days_param(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/dashboard?days=7")
        _assert_status(resp, 200, 302)

    def test_get_with_large_days(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/dashboard?days=90")
        _assert_status(resp, 200, 302)

    def test_unauthenticated(self, client, db_session):
        resp = client.get("/admin/analytics/dashboard")
        _assert_status(resp, 302, 401, 403)


# ---------------------------------------------------------------------------
# page_path_analytics
# ---------------------------------------------------------------------------

class TestPagePathAnalytics:
    def test_get(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/page-paths")
        _assert_status(resp, 200, 302)

    def test_get_with_user_id_filter(self, logged_in_client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session)
            user_id = user.id
        resp = logged_in_client.get(f"/admin/analytics/page-paths?user_id={user_id}")
        _assert_status(resp, 200, 302)

    def test_get_with_email_filter(self, logged_in_client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session)
            email = user.email
        resp = logged_in_client.get(f"/admin/analytics/page-paths?user={email}")
        _assert_status(resp, 200, 302)

    def test_get_with_email_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/page-paths?user=notfound@example.com")
        _assert_status(resp, 200, 302)

    def test_get_with_path_prefix(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/page-paths?path_prefix=/admin")
        _assert_status(resp, 200, 302)

    def test_export_csv(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/page-paths?export=csv")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            assert "text/csv" in resp.headers.get("Content-Type", "")

    def test_export_csv_with_user_filter(self, logged_in_client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session)
            email = user.email
        resp = logged_in_client.get(f"/admin/analytics/page-paths?export=csv&user={email}")
        _assert_status(resp, 200, 302)


# ---------------------------------------------------------------------------
# login_logs
# ---------------------------------------------------------------------------

class TestLoginLogs:
    def test_get(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/login-logs")
        _assert_status(resp, 200, 302)

    def test_get_with_user_filter(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/login-logs?user=test@example.com")
        _assert_status(resp, 200, 302)

    def test_get_with_event_type_filter(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/login-logs?event_type=login_success")
        _assert_status(resp, 200, 302)

    def test_get_with_ip_filter(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/login-logs?ip=127.0.0.1")
        _assert_status(resp, 200, 302)

    def test_get_with_suspicious_filter(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/login-logs?suspicious_only=true")
        _assert_status(resp, 200, 302)

    def test_get_with_date_range(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/analytics/login-logs?date_from=2024-01-01&date_to=2024-12-31"
        )
        _assert_status(resp, 200, 302)

    def test_unauthenticated(self, client, db_session):
        resp = client.get("/admin/analytics/login-logs")
        _assert_status(resp, 302, 401, 403)


# ---------------------------------------------------------------------------
# activity_logs
# ---------------------------------------------------------------------------

class TestActivityLogs:
    def test_get(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/activity-logs")
        _assert_status(resp, 200, 302)

    def test_get_with_user_filter(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/activity-logs?user=admin@example.com")
        _assert_status(resp, 200, 302)

    def test_get_with_activity_type_filter(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/activity-logs?activity_type=page_view")
        _assert_status(resp, 200, 302)

    def test_get_with_endpoint_filter(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/activity-logs?endpoint=/admin")
        _assert_status(resp, 200, 302)

    def test_get_with_valid_date_range(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/analytics/activity-logs?date_from=2024-01-01&date_to=2024-12-31"
        )
        _assert_status(resp, 200, 302)

    def test_get_with_invalid_date_range(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/analytics/activity-logs?date_from=bad-date&date_to=also-bad"
        )
        _assert_status(resp, 200, 302)

    def test_get_paginated(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/activity-logs?page=1&per_page=10")
        _assert_status(resp, 200, 302)


# ---------------------------------------------------------------------------
# session_logs
# ---------------------------------------------------------------------------

class TestSessionLogs:
    def test_get(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/sessions")
        _assert_status(resp, 200, 302)

    def test_get_with_user_filter(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/sessions?user=admin@example.com")
        _assert_status(resp, 200, 302)

    def test_get_active_only(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/sessions?active_only=true")
        _assert_status(resp, 200, 302)

    def test_get_with_min_duration(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/sessions?min_duration=10")
        _assert_status(resp, 200, 302)

    def test_get_with_session_id(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/sessions?session_id=abc123")
        _assert_status(resp, 200, 302)


# ---------------------------------------------------------------------------
# admin_actions
# ---------------------------------------------------------------------------

class TestAdminActions:
    def test_get(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/admin-actions")
        _assert_status(resp, 200, 302)

    def test_get_with_admin_filter(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/admin-actions?admin=admin@example.com")
        _assert_status(resp, 200, 302)

    def test_get_with_action_type_filter(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/admin-actions?action_type=delete_user")
        _assert_status(resp, 200, 302)

    def test_get_with_risk_level_filter(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/admin-actions?risk_level=high")
        _assert_status(resp, 200, 302)

    def test_get_with_multiple_risk_levels(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/analytics/admin-actions?risk_level=high&risk_level=medium"
        )
        _assert_status(resp, 200, 302)

    def test_get_requires_review(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/admin-actions?requires_review=true")
        _assert_status(resp, 200, 302)


# ---------------------------------------------------------------------------
# security_events
# ---------------------------------------------------------------------------

class TestSecurityEvents:
    def test_get(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/security-events")
        _assert_status(resp, 200, 302)

    def test_get_with_severity_filter(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/security-events?severity=high")
        _assert_status(resp, 200, 302)

    def test_get_with_event_type_filter(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/security-events?event_type=failed_login")
        _assert_status(resp, 200, 302)

    def test_get_unresolved_only(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/security-events?unresolved_only=true")
        _assert_status(resp, 200, 302)


# ---------------------------------------------------------------------------
# resolve_security_event
# ---------------------------------------------------------------------------

class TestResolveSecurityEvent:
    def _create_security_event(self, app, db_session):
        from app.models import SecurityEvent
        with app.app_context():
            event = SecurityEvent(
                event_type="failed_login",
                severity="medium",
                is_resolved=False,
            )
            db_session.add(event)
            db_session.commit()
            return event.id

    def test_resolve_event(self, logged_in_client, db_session, app):
        with patch("app.services.platform.user_analytics_service.log_admin_action"):
            event_id = self._create_security_event(app, db_session)
            resp = logged_in_client.post(
                f"/admin/analytics/security-events/{event_id}/resolve",
                data={"resolution_notes": "Fixed"},
                follow_redirects=False,
            )
        _assert_status(resp, 302, 200)

    def test_resolve_event_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/analytics/security-events/999999/resolve",
            data={"resolution_notes": "Test"},
        )
        _assert_status(resp, 404, 302)

    def test_resolve_event_no_notes(self, logged_in_client, db_session, app):
        with patch("app.services.platform.user_analytics_service.log_admin_action"):
            event_id = self._create_security_event(app, db_session)
            resp = logged_in_client.post(
                f"/admin/analytics/security-events/{event_id}/resolve",
                data={},
                follow_redirects=False,
            )
        _assert_status(resp, 302, 200)


# ---------------------------------------------------------------------------
# user_analytics
# ---------------------------------------------------------------------------

class TestUserAnalytics:
    def test_get_existing_user(self, logged_in_client, db_session, app, admin_user):
        with app.app_context():
            user_id = admin_user.id
        resp = logged_in_client.get(f"/admin/analytics/user/{user_id}")
        _assert_status(resp, 200, 302)

    def test_get_with_days_param(self, logged_in_client, db_session, app, admin_user):
        with app.app_context():
            user_id = admin_user.id
        resp = logged_in_client.get(f"/admin/analytics/user/{user_id}?days=7")
        _assert_status(resp, 200, 302)

    def test_get_partial(self, logged_in_client, db_session, app, admin_user):
        with app.app_context():
            user_id = admin_user.id
        resp = logged_in_client.get(f"/admin/analytics/user/{user_id}?partial=1")
        _assert_status(resp, 200, 302)

    def test_get_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/user/999999")
        _assert_status(resp, 404, 302)


# ---------------------------------------------------------------------------
# chart_login_activity
# ---------------------------------------------------------------------------

class TestChartLoginActivity:
    def test_get(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/api/charts/login-activity")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert "success" in data or "daily_activity" in data

    def test_get_with_days_param(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/api/charts/login-activity?days=7")
        _assert_status(resp, 200, 302)


# ---------------------------------------------------------------------------
# chart_user_activity
# ---------------------------------------------------------------------------

class TestChartUserActivity:
    def test_get(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/api/charts/user-activity")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert "success" in data or "daily_activity" in data

    def test_get_with_days_param(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/api/charts/user-activity?days=14")
        _assert_status(resp, 200, 302)


# ---------------------------------------------------------------------------
# cleanup_sessions
# ---------------------------------------------------------------------------

class TestCleanupSessions:
    def test_cleanup(self, logged_in_client, db_session):
        with patch("app.services.platform.user_analytics_service.cleanup_inactive_sessions", return_value=5) as mock_cleanup, \
             patch("app.services.platform.user_analytics_service.log_admin_action"):
            resp = logged_in_client.post(
                "/admin/analytics/cleanup-sessions",
                follow_redirects=False,
            )
        _assert_status(resp, 302, 200)

    def test_cleanup_error(self, logged_in_client, db_session):
        with patch(
            "app.services.platform.user_analytics_service.cleanup_inactive_sessions",
            side_effect=Exception("cleanup error"),
        ), patch("app.services.platform.user_analytics_service.log_admin_action"):
            resp = logged_in_client.post(
                "/admin/analytics/cleanup-sessions",
                follow_redirects=False,
            )
        _assert_status(resp, 302, 200)


# ---------------------------------------------------------------------------
# end_session (HTML route)
# ---------------------------------------------------------------------------

class TestEndSession:
    def test_session_not_found(self, logged_in_client, db_session):
        with patch("app.services.platform.user_analytics_service.log_admin_action"):
            resp = logged_in_client.post(
                "/admin/analytics/end-session/nonexistent-session-id",
                follow_redirects=False,
            )
        _assert_status(resp, 302, 200)

    def test_session_already_ended(self, logged_in_client, db_session, app):
        from app.models import UserSessionLog
        with app.app_context():
            session_log = UserSessionLog(
                session_id="test-session-123",
                user_id=None,
                is_active=False,
            )
            db_session.add(session_log)
            db_session.commit()
        with patch("app.services.platform.user_analytics_service.log_admin_action"):
            resp = logged_in_client.post(
                "/admin/analytics/end-session/test-session-123",
                follow_redirects=False,
            )
        _assert_status(resp, 302, 200)

    def test_end_active_session(self, logged_in_client, db_session, app, admin_user):
        from app.models import UserSessionLog
        with app.app_context():
            user_id = admin_user.id
            session_log = UserSessionLog(
                session_id="test-active-session-456",
                user_id=user_id,
                is_active=True,
            )
            db_session.add(session_log)
            db_session.commit()
        with patch("app.services.platform.user_analytics_service.end_user_session"), \
             patch("app.services.platform.user_analytics_service.add_session_to_blacklist"), \
             patch("app.services.platform.user_analytics_service.log_admin_action"):
            resp = logged_in_client.post(
                "/admin/analytics/end-session/test-active-session-456",
                follow_redirects=False,
            )
        _assert_status(resp, 302, 200)

    def test_end_session_error(self, logged_in_client, db_session, app, admin_user):
        from app.models import UserSessionLog
        with app.app_context():
            user_id = admin_user.id
            session_log = UserSessionLog(
                session_id="test-error-session-789",
                user_id=user_id,
                is_active=True,
            )
            db_session.add(session_log)
            db_session.commit()
        with patch(
            "app.services.platform.user_analytics_service.end_user_session",
            side_effect=Exception("test error"),
        ), patch("app.services.platform.user_analytics_service.log_admin_action"):
            resp = logged_in_client.post(
                "/admin/analytics/end-session/test-error-session-789",
                follow_redirects=False,
            )
        _assert_status(resp, 302, 200)


# ---------------------------------------------------------------------------
# audit_trail
# ---------------------------------------------------------------------------

class TestAuditTrail:
    def test_get(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/audit-trail")
        _assert_status(resp, 200, 302)

    def test_get_with_user_filter(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/analytics/audit-trail?user=admin@example.com"
        )
        _assert_status(resp, 200, 302)

    def test_get_with_multiple_users(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/analytics/audit-trail?user=admin@example.com&user=other@example.com"
        )
        _assert_status(resp, 200, 302)

    def test_get_with_date_range(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/analytics/audit-trail?date_from=2024-01-01&date_to=2024-12-31"
        )
        _assert_status(resp, 200, 302)

    def test_get_with_invalid_date_from(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/analytics/audit-trail?date_from=bad-date"
        )
        _assert_status(resp, 200, 302)

    def test_get_with_invalid_date_to(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/analytics/audit-trail?date_to=bad-date"
        )
        _assert_status(resp, 200, 302)

    def test_get_with_risk_level_filter(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/analytics/audit-trail?risk_level=high"
        )
        _assert_status(resp, 200, 302)

    def test_get_with_endpoint_filter(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/analytics/audit-trail?endpoint=/admin/users"
        )
        _assert_status(resp, 200, 302)

    def test_get_with_description_filter(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/analytics/audit-trail?description=deleted"
        )
        _assert_status(resp, 200, 302)

    def test_get_with_activity_type_filter(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/analytics/audit-trail?activity_type=page_view"
        )
        _assert_status(resp, 200, 302)

    def test_get_with_country_filter(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            country_id = country.id
        resp = logged_in_client.get(
            f"/admin/analytics/audit-trail?country={country_id}"
        )
        _assert_status(resp, 200, 302)

    def test_get_with_session_id_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/analytics/audit-trail?session_id=nonexistent-session"
        )
        _assert_status(resp, 200, 302)

    def test_get_with_session_id_numeric_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/analytics/audit-trail?session_id=999999"
        )
        _assert_status(resp, 200, 302)

    def test_get_with_session_id_found(self, logged_in_client, db_session, app, admin_user):
        from app.models import UserSessionLog
        with app.app_context():
            user_id = admin_user.id
            session_log = UserSessionLog(
                session_id="audit-trail-session-abc",
                user_id=user_id,
                is_active=False,
            )
            db_session.add(session_log)
            db_session.commit()
            session_log_id = session_log.id
        resp = logged_in_client.get(
            f"/admin/analytics/audit-trail?session_id={session_log_id}"
        )
        _assert_status(resp, 200, 302)

    def test_get_json_request(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/analytics/audit-trail",
            headers={"Accept": "application/json"},
        )
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert "entries" in data or "success" in data

    def test_get_requires_review_filter(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/analytics/audit-trail?requires_review=true"
        )
        _assert_status(resp, 200, 302)


# ---------------------------------------------------------------------------
# activity_endpoint_catalog
# ---------------------------------------------------------------------------

class TestActivityEndpointCatalog:
    def test_get(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/activity-endpoint-catalog")
        _assert_status(resp, 200, 302)

    def test_get_with_query(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/analytics/activity-endpoint-catalog?q=user")
        _assert_status(resp, 200, 302)

    def test_export_csv(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/analytics/activity-endpoint-catalog?export=csv"
        )
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            assert "text/csv" in resp.headers.get("Content-Type", "")

    def test_export_csv_with_query(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/analytics/activity-endpoint-catalog?q=admin&export=csv"
        )
        _assert_status(resp, 200, 302)
