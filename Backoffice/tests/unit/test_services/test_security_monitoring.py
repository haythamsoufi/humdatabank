"""
Comprehensive unit tests for app/services/security/monitoring.py
Targets 100% code coverage with database (db_session) and Flask app context.
"""
import logging
from datetime import timedelta
from unittest.mock import patch, MagicMock, call, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_security_event(
    id=1,
    event_type="test_event",
    severity="low",
    description="test",
    ip_address="127.0.0.1",
    user_id=None,
    timestamp=None,
):
    """Create a mock SecurityEvent object."""
    from app.utils.datetime_helpers import utcnow
    event = MagicMock()
    event.id = id
    event.event_type = event_type
    event.severity = severity
    event.description = description
    event.ip_address = ip_address
    event.user_id = user_id
    event.timestamp = timestamp or utcnow()
    return event


# ===========================================================================
# SecurityMonitor class attributes
# ===========================================================================

class TestSecurityMonitorClassAttributes:
    def test_thresholds_defined(self):
        from app.services.security.monitoring import SecurityMonitor
        assert "failed_logins_per_hour" in SecurityMonitor.THRESHOLDS
        assert SecurityMonitor.THRESHOLDS["failed_logins_per_hour"] == 10

    def test_severity_levels_defined(self):
        from app.services.security.monitoring import SecurityMonitor
        assert SecurityMonitor.SEVERITY_LEVELS["low"] == 1
        assert SecurityMonitor.SEVERITY_LEVELS["medium"] == 2
        assert SecurityMonitor.SEVERITY_LEVELS["high"] == 3
        assert SecurityMonitor.SEVERITY_LEVELS["critical"] == 4

    def test_module_level_instance_exists(self):
        from app.services.security.monitoring import security_monitor, SecurityMonitor
        assert isinstance(security_monitor, SecurityMonitor)


# ===========================================================================
# SecurityMonitor._get_client_info
# ===========================================================================

class TestGetClientInfo:
    def test_with_request_context(self, app):
        from app.services.security.monitoring import SecurityMonitor
        with app.test_request_context(
            "/test",
            method="POST",
            environ_base={"REMOTE_ADDR": "10.0.0.1"},
            headers={"User-Agent": "TestAgent/1.0"},
        ):
            info = SecurityMonitor._get_client_info()

        assert info["ip_address"] == "10.0.0.1"
        assert info["method"] == "POST"
        assert "url" in info
        assert "referrer" in info

    def test_without_request_context(self):
        from app.services.security.monitoring import SecurityMonitor
        with patch("app.services.security.monitoring.has_request_context", return_value=False):
            info = SecurityMonitor._get_client_info()
        assert info["ip_address"] == "system"
        assert info["user_agent"] == "unknown"
        assert info["method"] == "N/A"
        assert info["endpoint"] == "N/A"
        assert info["url"] == "N/A"

    def test_missing_remote_addr_uses_unknown(self, app):
        from app.services.security.monitoring import SecurityMonitor
        with app.test_request_context("/test"):
            with patch("app.services.security.monitoring.request") as mock_request:
                mock_request.remote_addr = None
                mock_request.user_agent.string = "UA"
                mock_request.referrer = None
                mock_request.method = "GET"
                mock_request.endpoint = "index"
                mock_request.url = "http://localhost/test"
                info = SecurityMonitor._get_client_info()
        assert info["ip_address"] == "unknown"

    def test_missing_user_agent_uses_unknown(self, app):
        from app.services.security.monitoring import SecurityMonitor
        with app.test_request_context("/test"):
            with patch("app.services.security.monitoring.request") as mock_request:
                mock_request.remote_addr = "1.2.3.4"
                mock_request.user_agent = None
                mock_request.referrer = None
                mock_request.method = "GET"
                mock_request.endpoint = "index"
                mock_request.url = "http://localhost/test"
                info = SecurityMonitor._get_client_info()
        assert info["user_agent"] == "unknown"

    def test_missing_endpoint_uses_unknown(self, app):
        from app.services.security.monitoring import SecurityMonitor
        with app.test_request_context("/test"):
            with patch("app.services.security.monitoring.request") as mock_request:
                mock_request.remote_addr = "1.2.3.4"
                mock_request.user_agent.string = "UA"
                mock_request.referrer = "http://referer.com"
                mock_request.method = "GET"
                mock_request.endpoint = None
                mock_request.url = "http://localhost/test"
                info = SecurityMonitor._get_client_info()
        assert info["endpoint"] == "unknown"

    def test_missing_url_uses_unknown(self, app):
        from app.services.security.monitoring import SecurityMonitor
        with app.test_request_context("/test"):
            with patch("app.services.security.monitoring.request") as mock_request:
                mock_request.remote_addr = "1.2.3.4"
                mock_request.user_agent.string = "UA"
                mock_request.referrer = None
                mock_request.method = "GET"
                mock_request.endpoint = "index"
                mock_request.url = None
                info = SecurityMonitor._get_client_info()
        assert info["url"] == "unknown"


# ===========================================================================
# SecurityMonitor.log_security_event
# ===========================================================================

class TestLogSecurityEvent:
    def test_logs_event_without_request_context(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            with patch("app.services.security.monitoring.has_request_context", return_value=False):
                SecurityMonitor.log_security_event(
                    event_type="test_event",
                    severity="low",
                    description="test description",
                    notify_admins=False,
                )
            from app.models import SecurityEvent
            event = SecurityEvent.query.filter_by(event_type="test_event").first()
            assert event is not None
            assert event.severity == "low"
            assert event.ip_address == "system"

    def test_logs_event_with_explicit_user_id(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor
        from tests.factories import create_test_user

        user = create_test_user(db_session)

        with app.app_context():
            with patch("app.services.security.monitoring.has_request_context", return_value=False):
                SecurityMonitor.log_security_event(
                    event_type="user_event",
                    severity="medium",
                    description="user action",
                    user_id=user.id,
                    notify_admins=False,
                )
            db_session.commit()
            from app.models import SecurityEvent
            event = SecurityEvent.query.filter_by(event_type="user_event").first()
            assert event is not None
            assert event.user_id == user.id

    def test_logs_event_with_request_context_authenticated_user(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor
        from tests.factories import create_test_user

        user = create_test_user(db_session)

        with app.app_context():
            mock_user = MagicMock()
            mock_user.id = user.id
            mock_user.is_authenticated = True

            with (
                patch("app.services.security.monitoring.has_request_context", return_value=True),
                patch("app.services.security.monitoring.current_user", mock_user),
                patch("app.services.security.monitoring.SecurityMonitor._get_client_info",
                      return_value={"ip_address": "1.2.3.4", "user_agent": "UA"}),
            ):
                SecurityMonitor.log_security_event(
                    event_type="auth_event",
                    severity="low",
                    description="authenticated action",
                    notify_admins=False,
                )

            db_session.commit()
            from app.models import SecurityEvent
            event = SecurityEvent.query.filter_by(event_type="auth_event").first()
            assert event is not None
            assert event.user_id == user.id

    def test_logs_event_with_request_context_anonymous_user(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            mock_user = MagicMock()
            mock_user.is_authenticated = False

            with (
                patch("app.services.security.monitoring.has_request_context", return_value=True),
                patch("app.services.security.monitoring.current_user", mock_user),
                patch("app.services.security.monitoring.SecurityMonitor._get_client_info",
                      return_value={"ip_address": "1.2.3.4", "user_agent": "UA"}),
            ):
                SecurityMonitor.log_security_event(
                    event_type="anon_event",
                    severity="low",
                    description="anonymous action",
                    notify_admins=False,
                )

            from app.models import SecurityEvent
            event = SecurityEvent.query.filter_by(event_type="anon_event").first()
            assert event is not None
            assert event.user_id is None

    def test_logs_event_current_user_raises_exception(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            with (
                patch("app.services.security.monitoring.has_request_context", return_value=True),
                patch("app.services.security.monitoring.current_user",
                      new_callable=lambda: type("P", (), {"id": property(lambda s: (_ for _ in ()).throw(RuntimeError("no user")))})),
                patch("app.services.security.monitoring.SecurityMonitor._get_client_info",
                      return_value={"ip_address": "1.2.3.4", "user_agent": "UA"}),
            ):
                SecurityMonitor.log_security_event(
                    event_type="error_event",
                    severity="low",
                    description="exception in user",
                    notify_admins=False,
                )

            from app.models import SecurityEvent
            event = SecurityEvent.query.filter_by(event_type="error_event").first()
            assert event is not None

    def test_sends_alert_for_high_severity(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            with (
                patch("app.services.security.monitoring.has_request_context", return_value=False),
                patch.object(SecurityMonitor, "_send_security_alert") as mock_alert,
            ):
                SecurityMonitor.log_security_event(
                    event_type="high_event",
                    severity="high",
                    description="high severity event",
                    notify_admins=True,
                )
            mock_alert.assert_called_once()

    def test_sends_alert_for_critical_severity(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            with (
                patch("app.services.security.monitoring.has_request_context", return_value=False),
                patch.object(SecurityMonitor, "_send_security_alert") as mock_alert,
            ):
                SecurityMonitor.log_security_event(
                    event_type="critical_event",
                    severity="critical",
                    description="critical event",
                    notify_admins=True,
                )
            mock_alert.assert_called_once()

    def test_does_not_send_alert_for_low_severity(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            with (
                patch("app.services.security.monitoring.has_request_context", return_value=False),
                patch.object(SecurityMonitor, "_send_security_alert") as mock_alert,
            ):
                SecurityMonitor.log_security_event(
                    event_type="low_event",
                    severity="low",
                    description="low severity",
                    notify_admins=True,
                )
            mock_alert.assert_not_called()

    def test_client_javascript_error_never_sends_alert_even_when_high(self, app, db_session):
        from app.models import SecurityEvent
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            with (
                patch("app.services.security.monitoring.has_request_context", return_value=False),
                patch.object(SecurityMonitor, "_send_security_alert") as mock_alert,
            ):
                SecurityMonitor.log_security_event(
                    event_type="client_javascript_error",
                    severity="high",
                    description="ReferenceError: should not email",
                    notify_admins=True,
                )
            mock_alert.assert_not_called()

        event = SecurityEvent.query.filter_by(event_type="client_javascript_error").first()
        assert event is not None
        assert event.severity == "low"

    def test_does_not_send_alert_when_notify_false(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            with (
                patch("app.services.security.monitoring.has_request_context", return_value=False),
                patch.object(SecurityMonitor, "_send_security_alert") as mock_alert,
            ):
                SecurityMonitor.log_security_event(
                    event_type="notify_off_event",
                    severity="high",
                    description="no notify",
                    notify_admins=False,
                )
            mock_alert.assert_not_called()

    def test_exception_in_db_logs_error_and_rolls_back(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor
        from app import db

        with app.app_context():
            with (
                patch("app.services.security.monitoring.has_request_context", return_value=False),
                patch("app.services.security.monitoring.db.session.add", side_effect=RuntimeError("db fail")),
                patch("app.services.security.monitoring.db.session.rollback") as mock_rb,
            ):
                SecurityMonitor.log_security_event(
                    event_type="fail_event",
                    severity="low",
                    description="will fail",
                    notify_admins=False,
                )

            mock_rb.assert_called_once()

    def test_logs_with_context_data(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            with patch("app.services.security.monitoring.has_request_context", return_value=False):
                SecurityMonitor.log_security_event(
                    event_type="ctx_event",
                    severity="low",
                    description="with context",
                    context_data={"key": "value", "count": 5},
                    notify_admins=False,
                )

            from app.models import SecurityEvent
            event = SecurityEvent.query.filter_by(event_type="ctx_event").first()
            assert event is not None
            assert event.context_data["key"] == "value"


# ===========================================================================
# SecurityMonitor._send_security_alert
# ===========================================================================

class TestSendSecurityAlert:
    def test_logs_critical_and_sends_email(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        event = _make_security_event(
            event_type="brute_force",
            severity="high",
            ip_address="1.2.3.4",
        )

        with app.app_context():
            with patch.object(
                SecurityMonitor,
                "_get_active_system_manager_emails",
                return_value=["manager@ifrc.org"],
            ), patch("app.services.email.service.send_security_alert", return_value=True) as mock_send:
                SecurityMonitor._send_security_alert(event)

        mock_send.assert_called_once()
        kwargs = mock_send.call_args[1]
        assert kwargs["event_type"] == "brute_force"
        assert kwargs["severity"] == "high"
        assert kwargs["recipients"] == ["manager@ifrc.org"]

    def test_skips_email_when_no_system_managers(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        event = _make_security_event(event_type="brute_force", severity="high")

        with app.app_context():
            with patch.object(
                SecurityMonitor,
                "_get_active_system_manager_emails",
                return_value=[],
            ), patch("app.services.email.service.send_security_alert") as mock_send:
                SecurityMonitor._send_security_alert(event)

        mock_send.assert_not_called()

    def test_send_email_exception_logged(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        event = _make_security_event(
            event_type="test_event",
            severity="critical",
        )

        with app.app_context():
            with patch.object(
                SecurityMonitor,
                "_get_active_system_manager_emails",
                return_value=["manager@ifrc.org"],
            ), patch(
                "app.services.email.service.send_security_alert",
                side_effect=Exception("email server down"),
            ), patch("app.services.security.monitoring.current_app.logger") as mock_logger:
                SecurityMonitor._send_security_alert(event)  # Should not raise

        mock_logger.error.assert_called()

    def test_timestamp_str_for_events_without_isoformat(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        event = _make_security_event()
        event.timestamp = "2026-01-01 12:00:00"  # plain string, no isoformat method

        with app.app_context():
            with patch.object(
                SecurityMonitor,
                "_get_active_system_manager_emails",
                return_value=["manager@ifrc.org"],
            ), patch("app.services.email.service.send_security_alert", return_value=True) as mock_send:
                SecurityMonitor._send_security_alert(event)

        kwargs = mock_send.call_args[1]
        assert kwargs["timestamp"] == "2026-01-01 12:00:00"

    def test_no_cooldown_by_default_sends_every_time(self, app, db_session):
        """Backwards compatibility: omitting alert_cooldown_seconds never throttles."""
        from app.services.security.monitoring import SecurityMonitor

        event = _make_security_event(event_type="uncapped_event", severity="high")

        with app.app_context():
            with patch.object(
                SecurityMonitor,
                "_get_active_system_manager_emails",
                return_value=["manager@ifrc.org"],
            ), patch("app.services.email.service.send_security_alert", return_value=True) as mock_send:
                SecurityMonitor._send_security_alert(event)
                SecurityMonitor._send_security_alert(event)
                SecurityMonitor._send_security_alert(event)

        assert mock_send.call_count == 3

    def test_cooldown_suppresses_repeat_alert_emails(self, app, db_session):
        """Repeated calls within the cooldown window send at most one alert email."""
        from app.services.security.monitoring import SecurityMonitor
        from app.services.security import alert_cooldown

        alert_cooldown.reset_for_tests()
        event = _make_security_event(event_type="cooldown_event", severity="high")

        with app.app_context():
            with patch.object(
                SecurityMonitor,
                "_get_active_system_manager_emails",
                return_value=["manager@ifrc.org"],
            ), patch("app.services.email.service.send_security_alert", return_value=True) as mock_send, \
                 patch("app.services.security.monitoring.current_app.logger") as mock_logger:
                for _ in range(5):
                    SecurityMonitor._send_security_alert(event, alert_cooldown_seconds=600)

        mock_send.assert_called_once()
        # The CRITICAL log line must still fire every time, even when the email
        # is suppressed, so incident timelines stay complete.
        assert mock_logger.critical.call_count == 5
        alert_cooldown.reset_for_tests()

    def test_cooldown_does_not_affect_different_event_types(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor
        from app.services.security import alert_cooldown

        alert_cooldown.reset_for_tests()
        event_a = _make_security_event(event_type="cooldown_event_a", severity="high")
        event_b = _make_security_event(event_type="cooldown_event_b", severity="high")

        with app.app_context():
            with patch.object(
                SecurityMonitor,
                "_get_active_system_manager_emails",
                return_value=["manager@ifrc.org"],
            ), patch("app.services.email.service.send_security_alert", return_value=True) as mock_send:
                SecurityMonitor._send_security_alert(event_a, alert_cooldown_seconds=600)
                SecurityMonitor._send_security_alert(event_b, alert_cooldown_seconds=600)

        assert mock_send.call_count == 2
        alert_cooldown.reset_for_tests()

    def test_log_security_event_passes_cooldown_through(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor
        from app.services.security import alert_cooldown

        alert_cooldown.reset_for_tests()
        with app.app_context():
            with patch("app.services.security.monitoring.has_request_context", return_value=False):
                with patch.object(SecurityMonitor, "_send_security_alert") as mock_alert:
                    SecurityMonitor.log_security_event(
                        event_type="platform_502_bad_gateway",
                        severity="high",
                        description="x",
                        notify_admins=True,
                        alert_cooldown_seconds=600,
                    )
            mock_alert.assert_called_once()
            _, kwargs = mock_alert.call_args
            assert kwargs.get("alert_cooldown_seconds") == 600
        alert_cooldown.reset_for_tests()


# ===========================================================================
# SecurityMonitor.check_suspicious_activity
# ===========================================================================

class TestCheckSuspiciousActivity:
    def test_calls_all_checks(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            with app.test_request_context("/test"):
                with (
                    patch.object(SecurityMonitor, "_check_failed_logins") as mock_fl,
                    patch.object(SecurityMonitor, "_check_suspicious_requests") as mock_sr,
                    patch.object(SecurityMonitor, "_check_admin_activity") as mock_aa,
                    patch.object(SecurityMonitor, "_check_brute_force_attempts") as mock_bf,
                ):
                    SecurityMonitor.check_suspicious_activity()

        mock_fl.assert_called_once()
        mock_sr.assert_called_once()
        mock_aa.assert_called_once()
        mock_bf.assert_called_once()

    def test_exception_logged(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            with app.test_request_context("/test"):
                with (
                    patch.object(
                        SecurityMonitor,
                        "_check_failed_logins",
                        side_effect=RuntimeError("check failed"),
                    ),
                    patch.object(SecurityMonitor, "_check_suspicious_requests"),
                    patch.object(SecurityMonitor, "_check_admin_activity"),
                    patch.object(SecurityMonitor, "_check_brute_force_attempts"),
                    patch("app.services.security.monitoring.current_app.logger") as mock_logger,
                ):
                    SecurityMonitor.check_suspicious_activity()

        mock_logger.error.assert_called()


# ===========================================================================
# SecurityMonitor._check_failed_logins
# ===========================================================================

class TestCheckFailedLogins:
    def test_no_alert_below_threshold(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            mock_query = MagicMock()
            mock_query.filter.return_value.count.return_value = 5  # below threshold of 10

            with patch("app.services.security.monitoring.SecurityEvent.query", mock_query):
                with patch.object(SecurityMonitor, "log_security_event") as mock_log:
                    SecurityMonitor._check_failed_logins()

            mock_log.assert_not_called()

    def test_alert_at_threshold(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            mock_query = MagicMock()
            mock_query.filter.return_value.count.return_value = 10  # at threshold

            with patch("app.services.security.monitoring.SecurityEvent.query", mock_query):
                with patch.object(SecurityMonitor, "log_security_event") as mock_log:
                    SecurityMonitor._check_failed_logins()

            mock_log.assert_called_once()
            kwargs = mock_log.call_args[1]
            assert kwargs["event_type"] == "excessive_failed_logins"
            assert kwargs["severity"] == "high"

    def test_exception_logged(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            with patch(
                "app.services.security.monitoring.SecurityEvent.query",
                side_effect=RuntimeError("db error"),
            ), patch("app.services.security.monitoring.current_app.logger") as mock_logger:
                SecurityMonitor._check_failed_logins()

        mock_logger.error.assert_called()


# ===========================================================================
# SecurityMonitor._check_suspicious_requests
# ===========================================================================

class TestCheckSuspiciousRequests:
    def test_clean_user_agent_no_alert(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            with app.test_request_context("/test", headers={"User-Agent": "Mozilla/5.0 (normal browser)"}):
                with patch.object(SecurityMonitor, "log_security_event") as mock_log:
                    SecurityMonitor._check_suspicious_requests()
                mock_log.assert_not_called()

    def test_sqlmap_agent_triggers_alert(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            with app.test_request_context("/test", headers={"User-Agent": "sqlmap/1.5.8"}):
                with patch.object(SecurityMonitor, "log_security_event") as mock_log, \
                     patch("app.services.security.monitoring.request") as mock_req:
                    mock_req.user_agent.string = "sqlmap/1.5.8"
                    SecurityMonitor._check_suspicious_requests()
                mock_log.assert_called_once()
                kwargs = mock_log.call_args[1]
                assert kwargs["event_type"] == "suspicious_user_agent"

    @pytest.mark.parametrize("agent", ["nikto", "nmap", "masscan", "zap", "burp"])
    def test_known_scanner_agent_triggers_alert(self, agent, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            with app.test_request_context("/test", headers={"User-Agent": f"{agent}/2.0"}):
                with patch.object(SecurityMonitor, "log_security_event") as mock_log, \
                     patch("app.services.security.monitoring.request") as mock_req:
                    mock_req.user_agent.string = f"{agent}/2.0"
                    SecurityMonitor._check_suspicious_requests()
                mock_log.assert_called_once()

    def test_exception_logged(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            with app.test_request_context("/test"):
                with patch(
                    "app.services.security.monitoring.request",
                    side_effect=RuntimeError("request error"),
                ), patch("app.services.security.monitoring.current_app.logger") as mock_logger:
                    SecurityMonitor._check_suspicious_requests()

        mock_logger.error.assert_called()


# ===========================================================================
# SecurityMonitor._check_admin_activity
# ===========================================================================

class TestCheckAdminActivity:
    def test_anonymous_user_skips(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        mock_user = MagicMock()
        mock_user.is_authenticated = False

        with app.app_context():
            with app.test_request_context("/test"):
                with (
                    patch("app.services.security.monitoring.current_user", mock_user),
                    patch.object(SecurityMonitor, "log_security_event") as mock_log,
                ):
                    SecurityMonitor._check_admin_activity()
                mock_log.assert_not_called()

    def test_non_admin_user_skips(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 1

        with app.app_context():
            with app.test_request_context("/test"):
                with (
                    patch("app.services.security.monitoring.current_user", mock_user),
                    patch(
                        "app.services.organization.authorization_service.AuthorizationService.is_admin",
                        return_value=False,
                    ),
                    patch.object(SecurityMonitor, "log_security_event") as mock_log,
                ):
                    SecurityMonitor._check_admin_activity()
                mock_log.assert_not_called()

    def test_admin_with_high_action_count_triggers_alert(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 10

        mock_query = MagicMock()
        mock_query.filter.return_value.count.return_value = 15  # above threshold of 10

        with app.app_context():
            with app.test_request_context("/test"):
                with (
                    patch("app.services.security.monitoring.current_user", mock_user),
                    patch(
                        "app.services.organization.authorization_service.AuthorizationService.is_admin",
                        return_value=True,
                    ),
                    patch("app.services.security.monitoring.AdminActionLog.query", mock_query),
                    patch.object(SecurityMonitor, "log_security_event") as mock_log,
                ):
                    SecurityMonitor._check_admin_activity()
                mock_log.assert_called_once()
                kwargs = mock_log.call_args[1]
                assert kwargs["event_type"] == "excessive_admin_activity"

    def test_admin_below_threshold_no_alert(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 10

        mock_query = MagicMock()
        mock_query.filter.return_value.count.return_value = 5  # below threshold

        with app.app_context():
            with app.test_request_context("/test"):
                with (
                    patch("app.services.security.monitoring.current_user", mock_user),
                    patch(
                        "app.services.organization.authorization_service.AuthorizationService.is_admin",
                        return_value=True,
                    ),
                    patch("app.services.security.monitoring.AdminActionLog.query", mock_query),
                    patch.object(SecurityMonitor, "log_security_event") as mock_log,
                ):
                    SecurityMonitor._check_admin_activity()
                mock_log.assert_not_called()

    def test_exception_logged(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            with app.test_request_context("/test"):
                with patch(
                    "app.services.security.monitoring.current_user",
                ) as mock_user:
                    type(mock_user).is_authenticated = PropertyMock(
                        side_effect=RuntimeError("auth error")
                    )
                    with patch("app.services.security.monitoring.current_app.logger") as mock_logger:
                        SecurityMonitor._check_admin_activity()

        mock_logger.error.assert_called()


# ===========================================================================
# SecurityMonitor._check_brute_force_attempts
# ===========================================================================

class TestCheckBruteForceAttempts:
    def test_no_ip_address_skips(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            with app.test_request_context("/test"):
                with patch("app.services.security.monitoring.request") as mock_request:
                    mock_request.remote_addr = None
                    with patch.object(SecurityMonitor, "log_security_event") as mock_log:
                        SecurityMonitor._check_brute_force_attempts()
                    mock_log.assert_not_called()

    def test_below_threshold_no_alert(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        mock_query = MagicMock()
        mock_query.filter.return_value.count.return_value = 10  # below 20

        with app.app_context():
            with app.test_request_context(
                "/test",
                environ_base={"REMOTE_ADDR": "5.5.5.5"},
            ):
                with patch("app.services.security.monitoring.SecurityEvent.query", mock_query):
                    with patch.object(SecurityMonitor, "log_security_event") as mock_log:
                        SecurityMonitor._check_brute_force_attempts()
                    mock_log.assert_not_called()

    def test_at_threshold_triggers_alert(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        mock_query = MagicMock()
        mock_query.filter.return_value.count.return_value = 20  # at threshold

        with app.app_context():
            with app.test_request_context(
                "/test",
                environ_base={"REMOTE_ADDR": "5.5.5.5"},
            ):
                with patch("app.services.security.monitoring.SecurityEvent.query", mock_query):
                    with patch.object(SecurityMonitor, "log_security_event") as mock_log:
                        SecurityMonitor._check_brute_force_attempts()
                    mock_log.assert_called_once()
                    kwargs = mock_log.call_args[1]
                    assert kwargs["event_type"] == "potential_brute_force"
                    assert kwargs["severity"] == "high"

    def test_exception_logged(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            with app.test_request_context(
                "/test",
                environ_base={"REMOTE_ADDR": "5.5.5.5"},
            ):
                with patch(
                    "app.services.security.monitoring.SecurityEvent.query",
                    side_effect=RuntimeError("db error"),
                ), patch("app.services.security.monitoring.current_app.logger") as mock_logger:
                    SecurityMonitor._check_brute_force_attempts()

        mock_logger.error.assert_called()


# ===========================================================================
# SecurityMonitor.get_security_dashboard_data
# ===========================================================================

class TestGetSecurityDashboardData:
    def test_returns_dashboard_data(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            # Create some test events
            with patch("app.services.security.monitoring.has_request_context", return_value=False):
                SecurityMonitor.log_security_event(
                    "test_event", "low", "test", notify_admins=False
                )
                SecurityMonitor.log_security_event(
                    "test_event", "high", "test2", notify_admins=False
                )

            result = SecurityMonitor.get_security_dashboard_data(days=7)

        assert "events_by_severity" in result
        assert "events_by_type" in result
        assert "unresolved_count" in result
        assert result["period_days"] == 7

    def test_returns_custom_days(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            result = SecurityMonitor.get_security_dashboard_data(days=30)

        assert result["period_days"] == 30

    def test_exception_returns_empty_data(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            with patch("app.services.security.monitoring.db.session.query", side_effect=RuntimeError("db error")):
                result = SecurityMonitor.get_security_dashboard_data(days=7)

        assert result["events_by_severity"] == {}
        assert result["events_by_type"] == {}
        assert result["unresolved_count"] == 0
        assert result["period_days"] == 7

    def test_exception_logs_error(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            with patch("app.services.security.monitoring.db.session.query", side_effect=RuntimeError("db error")), \
                 patch("app.services.security.monitoring.current_app.logger") as mock_logger:
                SecurityMonitor.get_security_dashboard_data(days=7)

        mock_logger.error.assert_called()


# ===========================================================================
# Convenience functions (module-level)
# ===========================================================================

class TestConvenienceFunctions:
    def test_log_security_event_delegates_to_monitor(self, app, db_session):
        from app.services.security.monitoring import log_security_event, security_monitor

        with app.app_context():
            with patch.object(security_monitor, "log_security_event") as mock_log:
                log_security_event(
                    "conv_event",
                    "low",
                    "convenience function test",
                    context_data={"k": "v"},
                    user_id=5,
                    notify_admins=False,
                )

        mock_log.assert_called_once_with(
            "conv_event",
            "low",
            "convenience function test",
            {"k": "v"},
            user_id=5,
            notify_admins=False,
            alert_cooldown_seconds=None,
        )

    def test_check_security_thresholds_delegates(self, app, db_session):
        from app.services.security.monitoring import check_security_thresholds, security_monitor

        with app.app_context():
            with patch.object(security_monitor, "check_suspicious_activity") as mock_check:
                check_security_thresholds()

        mock_check.assert_called_once()

    def test_get_security_metrics_delegates(self, app, db_session):
        from app.services.security.monitoring import get_security_metrics, security_monitor

        expected = {
            "events_by_severity": {"low": 1},
            "events_by_type": {"test": 1},
            "unresolved_count": 0,
            "period_days": 14,
        }
        with app.app_context():
            with patch.object(
                security_monitor,
                "get_security_dashboard_data",
                return_value=expected,
            ) as mock_data:
                result = get_security_metrics(days=14)

        mock_data.assert_called_once_with(14)
        assert result == expected

    def test_get_security_metrics_default_days(self, app, db_session):
        from app.services.security.monitoring import get_security_metrics, security_monitor

        with app.app_context():
            with patch.object(
                security_monitor,
                "get_security_dashboard_data",
                return_value={},
            ) as mock_data:
                get_security_metrics()

        mock_data.assert_called_once_with(7)


# ===========================================================================
# SecurityMonitor.log_security_event — edge cases
# ===========================================================================

class TestLogSecurityEventEdgeCases:
    def test_none_context_data_uses_empty_dict(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor
        from app.models import SecurityEvent

        with app.app_context():
            with patch("app.services.security.monitoring.has_request_context", return_value=False):
                SecurityMonitor.log_security_event(
                    event_type="no_ctx_event",
                    severity="low",
                    description="no context data",
                    context_data=None,
                    notify_admins=False,
                )
            event = SecurityEvent.query.filter_by(event_type="no_ctx_event").first()
            assert event is not None
            assert event.context_data == {}

    def test_medium_severity_no_alert(self, app, db_session):
        from app.services.security.monitoring import SecurityMonitor

        with app.app_context():
            with (
                patch("app.services.security.monitoring.has_request_context", return_value=False),
                patch.object(SecurityMonitor, "_send_security_alert") as mock_alert,
            ):
                SecurityMonitor.log_security_event(
                    event_type="medium_event",
                    severity="medium",
                    description="medium severity",
                    notify_admins=True,
                )
            mock_alert.assert_not_called()
