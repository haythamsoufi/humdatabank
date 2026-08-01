"""Tests for app.services.platform.user_analytics_query_service."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.platform import user_analytics_query_service as query_svc


pytestmark = [pytest.mark.unit]


class TestHasTable:
    def test_returns_true_when_table_exists(self, app):
        with app.app_context():
            with patch('app.services.platform.user_analytics_query_service.inspect') as mock_inspect:
                mock_inspect.return_value.has_table.return_value = True
                assert query_svc.has_table('user_login_log') is True

    def test_returns_false_on_exception(self, app):
        with app.app_context():
            with patch('app.services.platform.user_analytics_query_service.inspect') as mock_inspect:
                mock_inspect.return_value.has_table.side_effect = RuntimeError('boom')
                assert query_svc.has_table('missing') is False


class TestDateParsing:
    def test_parse_date_from_valid(self):
        assert query_svc.parse_date_from('2024-06-15') == datetime(2024, 6, 15)

    def test_parse_date_from_invalid(self):
        assert query_svc.parse_date_from('bad') is None

    def test_parse_date_to_exclusive(self):
        result = query_svc.parse_date_to_exclusive('2024-06-15')
        assert result == datetime(2024, 6, 16)


class TestLoginLogsQuery:
    def test_paginate_login_logs_with_table(self, app):
        with app.app_context():
            with patch.object(query_svc, 'has_table', return_value=True), \
                 patch.object(query_svc, 'build_login_logs_query') as mock_build:
                mock_paginated = MagicMock()
                mock_paginated.items = []
                mock_paginated.total = 0
                mock_paginated.page = 1
                mock_paginated.per_page = 50
                mock_paginated.pages = 0
                mock_build.return_value.paginate.return_value = mock_paginated

                result = query_svc.paginate_login_logs(
                    1, 50, query_svc.LoginLogsFilters(user='admin@example.com'), variant='admin'
                )
                mock_build.assert_called_once()
                assert result['items'] == []
                assert result['total'] == 0

    def test_paginate_returns_empty_when_no_table(self, app):
        with app.app_context():
            with patch.object(query_svc, 'has_table', return_value=False):
                result = query_svc.paginate_login_logs(1, 50, query_svc.LoginLogsFilters())
                assert result == query_svc.empty_pagination_payload(page=1, per_page=50)

    def test_serialize_login_log_admin_variant(self):
        log = MagicMock()
        log.id = 1
        log.timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
        log.event_type = 'login_success'
        log.email_attempted = 'user@example.com'
        log.user = None
        log.ip_address = '1.1.1.1'
        log.location = None
        log.device_type = 'Desktop'
        log.operating_system = 'Windows'
        log.is_suspicious = False
        log.is_bot_detected = False
        log.user_agent = 'Mozilla/5.0'
        log.failure_reason = None
        log.failure_reason_display = None
        log.browser = 'Chrome'
        log.browser_name = 'Chrome'
        log.browser_version = '120'
        log.device_name = 'PC'
        log.referrer_url = None
        log.failed_attempts_count = 0

        item = query_svc.serialize_login_log(log, variant='admin')
        assert item['browser'] == 'Chrome'
        assert 'risk' not in item or item.get('risk') is None

    def test_serialize_login_log_mobile_variant(self):
        log = MagicMock()
        log.id = 2
        log.timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
        log.event_type = 'login_failed'
        log.email_attempted = 'user@example.com'
        log.user = None
        log.ip_address = '1.1.1.1'
        log.location = None
        log.device_type = 'Mobile'
        log.operating_system = 'Android'
        log.is_suspicious = True
        log.is_bot_detected = False
        log.user_agent = None
        log.failure_reason = 'wrong_password'
        log.failure_reason_display = 'Wrong password'
        log.browser_name = 'Chrome'

        item = query_svc.serialize_login_log(log, variant='mobile')
        assert 'browser' not in item
        assert item['browser_name'] == 'Chrome'


class TestSessionLogsQuery:
    def test_paginate_session_logs_with_table(self, app):
        with app.app_context():
            with patch.object(query_svc, 'has_table', return_value=True), \
                 patch.object(query_svc, 'build_session_logs_query') as mock_build, \
                 patch.object(query_svc, 'count_audit_visible_entries_for_sessions', return_value={}):
                mock_paginated = MagicMock()
                mock_paginated.items = []
                mock_paginated.total = 0
                mock_paginated.page = 2
                mock_paginated.per_page = 25
                mock_paginated.pages = 0
                mock_build.return_value.paginate.return_value = mock_paginated

                result = query_svc.paginate_session_logs(
                    2, 25, query_svc.SessionLogsFilters(active_only=True), variant='mobile'
                )
                mock_build.assert_called_once()
                assert result['page'] == 2
                assert result['items'] == []

    def test_paginate_returns_empty_when_no_table(self, app):
        with app.app_context():
            with patch.object(query_svc, 'has_table', return_value=False):
                result = query_svc.paginate_session_logs(2, 25, query_svc.SessionLogsFilters())
                assert result['page'] == 2
                assert result['per_page'] == 25
                assert result['items'] == []

    def test_serialize_session_log_admin_includes_session_log_id(self):
        session_log = MagicMock()
        session_log.id = 99
        session_log.session_id = 'sess-abc'
        session_log.session_start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        session_log.session_end = None
        session_log.last_activity = datetime(2024, 1, 1, 1, tzinfo=timezone.utc)
        session_log.page_views = 3
        session_log.page_view_path_counts = {'/a': 3}
        session_log.is_active = True
        session_log.device_type = 'Desktop'
        session_log.browser = 'Chrome'
        session_log.operating_system = 'Windows'
        session_log.ip_address = '1.1.1.1'
        session_log.user_agent = 'Mozilla/5.0'
        session_log.user = None

        with patch.object(query_svc, 'effective_session_duration_minutes', return_value=10), \
             patch.object(query_svc, 'effective_session_active_duration_minutes', return_value=5), \
             patch.object(query_svc, 'distinct_page_view_path_count', return_value=1), \
             patch.object(query_svc, 'session_log_device_icon_classes', return_value='fa-laptop'):
            item = query_svc.serialize_session_log_list_item(session_log, 7, variant='admin')

        assert item['session_log_id'] == 99
        assert item['has_path_breakdown'] is True
        assert 'page_view_path_counts' not in item

    def test_serialize_session_log_mobile_includes_path_counts(self):
        session_log = MagicMock()
        session_log.session_id = 'sess-abc'
        session_log.session_start = None
        session_log.session_end = None
        session_log.last_activity = None
        session_log.page_views = 0
        session_log.page_view_path_counts = {'/home': 2}
        session_log.is_active = False
        session_log.device_type = 'Mobile'
        session_log.browser = 'Safari'
        session_log.operating_system = 'iOS'
        session_log.ip_address = '1.1.1.1'
        session_log.user_agent = None
        session_log.user = None

        with patch.object(query_svc, 'effective_session_duration_minutes', return_value=None), \
             patch.object(query_svc, 'effective_session_active_duration_minutes', return_value=None), \
             patch.object(query_svc, 'distinct_page_view_path_count', return_value=1), \
             patch.object(query_svc, 'session_log_device_icon_classes', return_value='fa-mobile'):
            item = query_svc.serialize_session_log_list_item(session_log, 0, variant='mobile')

        assert item['page_view_path_counts'] == {'/home': 2}
        assert 'session_log_id' not in item


class TestDashboardStats:
    def test_get_admin_dashboard_stats(self, app):
        with app.app_context():
            with patch('app.services.platform.user_analytics_query_service.get_platform_stats', return_value={
                'total_users': 10,
                'total_countries': 5,
                'total_templates': 3,
                'total_indicators': 20,
            }), patch.object(query_svc, 'has_table', return_value=False), \
                 patch('app.services.platform.user_analytics_query_service.AssignedForm') as MockAF, \
                 patch('app.services.platform.user_analytics_query_service.PublicSubmission') as MockPS:
                MockAF.query.count.return_value = 2
                MockPS.query.count.return_value = 4
                MockPS.query.filter.return_value.count.return_value = 1

                data = query_svc.get_admin_dashboard_stats()
                assert data['user_count'] == 10
                assert data['assignment_count'] == 2
                assert data['public_submission_count'] == 4
                assert 'unresolved_security_events' in data


class TestEndSession:
    def test_execute_end_session_not_found(self, app):
        with app.app_context():
            with patch('app.services.platform.user_analytics_query_service.UserSessionLog') as MockSL:
                MockSL.query.filter_by.return_value.first.return_value = None
                actor = MagicMock(is_authenticated=True)
                result = query_svc.execute_end_session('missing', actor_user=actor, flask_session={})
                assert result.ok is False
                assert result.error == 'not_found'

    def test_execute_end_session_already_ended(self, app):
        with app.app_context():
            session_log = MagicMock(is_active=False)
            with patch('app.services.platform.user_analytics_query_service.UserSessionLog') as MockSL:
                MockSL.query.filter_by.return_value.first.return_value = session_log
                actor = MagicMock(is_authenticated=True)
                result = query_svc.execute_end_session('sess-1', actor_user=actor, flask_session={})
                assert result.ok is False
                assert result.error == 'already_ended'

    def test_execute_end_session_success(self, app):
        with app.app_context():
            target_user = MagicMock(id=5, email='user@example.com')
            session_log = MagicMock(is_active=True, user=target_user, id=42)
            actor = MagicMock(is_authenticated=True, id=99)
            flask_session = {'session_id': 'other'}

            with patch('app.services.platform.user_analytics_query_service.UserSessionLog') as MockSL, \
                 patch('app.services.platform.user_analytics_query_service.end_user_session') as mock_end, \
                 patch('app.services.platform.user_analytics_query_service.add_session_to_blacklist') as mock_blacklist:
                MockSL.query.filter_by.return_value.first.return_value = session_log
                result = query_svc.execute_end_session('sess-1', actor_user=actor, flask_session=flask_session)

                assert result.ok is True
                assert result.logged_out_self is False
                mock_end.assert_called_once_with('sess-1', ended_by='admin_action')
                mock_blacklist.assert_called_once_with('sess-1')

    def test_execute_end_session_logs_out_self(self, app):
        with app.app_context():
            target_user = MagicMock(id=5, email='user@example.com')
            session_log = MagicMock(is_active=True, user=target_user, id=42)
            actor = MagicMock(is_authenticated=True, id=5)
            flask_session = {'session_id': 'sess-self'}

            with patch('app.services.platform.user_analytics_query_service.UserSessionLog') as MockSL, \
                 patch('app.services.platform.user_analytics_query_service.end_user_session'), \
                 patch('app.services.platform.user_analytics_query_service.add_session_to_blacklist'):
                MockSL.query.filter_by.return_value.first.return_value = session_log
                result = query_svc.execute_end_session('sess-self', actor_user=actor, flask_session=flask_session)

                assert result.ok is True
                assert result.logged_out_self is True
                assert 'session_id' not in flask_session


class TestRequestArgHelpers:
    def test_login_logs_filters_from_request_args(self):
        args = MagicMock()
        args.get.side_effect = lambda key, default=None, type=None: {
            'user': 'a@b.com',
            'event_type': 'login_success',
            'ip': '127.0.0.1',
            'suspicious_only': True,
            'date_from': '2024-01-01',
            'date_to': '2024-12-31',
        }.get(key, default)

        filters = query_svc.login_logs_filters_from_request_args(args)
        assert filters.user == 'a@b.com'
        assert filters.suspicious_only is True

    def test_session_logs_filters_from_request_args(self):
        args = MagicMock()
        args.get.side_effect = lambda key, default=None, type=None: {
            'user': 'a@b.com',
            'active_only': True,
            'min_duration': 15,
            'session_id': 'sess-x',
        }.get(key, default)

        filters = query_svc.session_logs_filters_from_request_args(args)
        assert filters.session_id == 'sess-x'
        assert filters.min_duration == 15
