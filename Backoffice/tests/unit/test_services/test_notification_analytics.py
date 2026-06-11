"""
Tests for app/services/notification/analytics.py

Targets 100% coverage of the NotificationAnalytics service.
"""
from datetime import timedelta
from unittest.mock import patch, MagicMock, PropertyMock
import pytest

from app.services.notification.analytics import NotificationAnalytics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_query(count_value=0, all_value=None):
    """Return a minimal SQLAlchemy query mock."""
    q = MagicMock()
    q.filter.return_value = q
    q.count.return_value = count_value
    q.all.return_value = all_value or []
    q.group_by.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    return q


# ---------------------------------------------------------------------------
# get_summary
# ---------------------------------------------------------------------------

class TestGetSummary:
    def test_returns_success_dict_with_correct_keys(self, app, db_session):
        with app.app_context():
            result = NotificationAnalytics.get_summary(days=30)
        assert result['success'] is True
        for key in ('period_days', 'total_created', 'total_unread', 'total_read',
                    'total_archived', 'total_expired', 'read_rate', 'unread_rate'):
            assert key in result

    def test_period_days_reflected(self, app, db_session):
        with app.app_context():
            result = NotificationAnalytics.get_summary(days=7)
        assert result['period_days'] == 7

    def test_zero_notifications_read_rate(self, app, db_session):
        with app.app_context():
            result = NotificationAnalytics.get_summary(days=30)
        # With empty DB total_created == 0 → read_rate and unread_rate both 0
        assert result['total_created'] == 0
        assert result['read_rate'] == 0
        assert result['unread_rate'] == 0

    def test_read_rate_and_unread_rate_computed(self, app, db_session):
        """read_rate + unread_rate == 100 when there are notifications."""
        from app.models import Notification, NotificationPreferences, User
        from app import db
        from app.models.enums import NotificationType

        with app.app_context():
            user = User(email='analytics_read@test.com', name='A', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            notif_read = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='t', message='m', is_read=True, is_archived=False
            )
            notif_unread = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='t2', message='m2', is_read=False, is_archived=False
            )
            db.session.add_all([notif_read, notif_unread])
            db.session.commit()

            result = NotificationAnalytics.get_summary(days=365)

        assert result['success'] is True
        assert result['total_read'] >= 1
        assert result['total_created'] >= 2
        assert result['read_rate'] + result['unread_rate'] == pytest.approx(100.0, abs=0.01)

    def test_returns_error_on_exception(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.analytics.Notification') as MockN:
                MockN.query.filter.side_effect = RuntimeError("db error")
                result = NotificationAnalytics.get_summary()
        assert result.get('success') is False or 'error' in result


# ---------------------------------------------------------------------------
# get_delivery_rates
# ---------------------------------------------------------------------------

class TestGetDeliveryRates:
    def test_returns_success_dict_empty_db(self, app, db_session):
        with app.app_context():
            result = NotificationAnalytics.get_delivery_rates(days=30)
        assert result['success'] is True
        assert isinstance(result['delivery_rates'], list)
        assert result['period_days'] == 30

    def test_delivery_rates_contain_correct_fields(self, app, db_session):
        """When notifications exist the result rows have all expected keys."""
        from app.models import Notification, User
        from app import db
        from app.models.enums import NotificationType

        with app.app_context():
            user = User(email='analytics_dr@test.com', name='B', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            notif = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='t', message='m', is_read=True, is_archived=False
            )
            db.session.add(notif)
            db.session.commit()

            result = NotificationAnalytics.get_delivery_rates(days=365)

        assert result['success'] is True
        if result['delivery_rates']:
            row = result['delivery_rates'][0]
            for key in ('notification_type', 'total', 'read_count', 'archived_count',
                        'read_rate', 'unread_count'):
                assert key in row

    def test_sorted_by_total_descending(self, app, db_session):
        """Results are sorted by total descending."""
        from app.models import Notification, User
        from app import db
        from app.models.enums import NotificationType

        with app.app_context():
            user = User(email='analytics_dr2@test.com', name='C', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            for _ in range(3):
                db.session.add(Notification(
                    user_id=user.id,
                    notification_type=NotificationType.admin_message,
                    title='t', message='m', is_read=False, is_archived=False
                ))
            db.session.add(Notification(
                user_id=user.id,
                notification_type=NotificationType.deadline_reminder,
                title='t2', message='m2', is_read=False, is_archived=False
            ))
            db.session.commit()

            result = NotificationAnalytics.get_delivery_rates(days=365)

        totals = [r['total'] for r in result['delivery_rates']]
        assert totals == sorted(totals, reverse=True)

    def test_returns_error_on_exception(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.analytics.db') as mock_db:
                mock_db.session.query.side_effect = RuntimeError("fail")
                result = NotificationAnalytics.get_delivery_rates()
        assert result.get('success') is False or 'error' in result

    def test_notification_type_value_attribute(self, app, db_session):
        """notification_type in output uses .value when available."""
        from app.models import Notification, User
        from app import db
        from app.models.enums import NotificationType

        with app.app_context():
            user = User(email='analytics_dr3@test.com', name='D', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.add(Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='t', message='m', is_read=False, is_archived=False
            ))
            db.session.commit()
            result = NotificationAnalytics.get_delivery_rates(days=365)

        if result['delivery_rates']:
            assert isinstance(result['delivery_rates'][0]['notification_type'], str)


# ---------------------------------------------------------------------------
# get_read_rates
# ---------------------------------------------------------------------------

class TestGetReadRates:
    def test_returns_success_with_expected_keys(self, app, db_session):
        with app.app_context():
            result = NotificationAnalytics.get_read_rates(days=30)
        assert result['success'] is True
        assert 'by_type' in result
        assert 'by_priority' in result
        assert result['period_days'] == 30

    def test_by_type_and_by_priority_are_lists(self, app, db_session):
        with app.app_context():
            result = NotificationAnalytics.get_read_rates()
        assert isinstance(result['by_type'], list)
        assert isinstance(result['by_priority'], list)

    def test_read_rates_populated_when_notifications_exist(self, app, db_session):
        from app.models import Notification, User
        from app import db
        from app.models.enums import NotificationType

        with app.app_context():
            user = User(email='analytics_rr@test.com', name='E', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.add(Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='t', message='m', is_read=True, is_archived=False,
                priority='high'
            ))
            db.session.commit()
            result = NotificationAnalytics.get_read_rates(days=365)

        assert result['success'] is True
        # Some data should be present
        assert len(result['by_type']) >= 1
        assert len(result['by_priority']) >= 1
        type_row = result['by_type'][0]
        for key in ('notification_type', 'total', 'read_count', 'read_rate'):
            assert key in type_row

    def test_returns_error_on_exception(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.analytics.db') as mock_db:
                mock_db.session.query.side_effect = Exception("fail")
                result = NotificationAnalytics.get_read_rates()
        assert result.get('success') is False or 'error' in result


# ---------------------------------------------------------------------------
# get_peak_times
# ---------------------------------------------------------------------------

class TestGetPeakTimes:
    def test_returns_success_with_all_24_hours(self, app, db_session):
        with app.app_context():
            result = NotificationAnalytics.get_peak_times(days=30)
        assert result['success'] is True
        assert len(result['hourly_counts']) == 24
        assert 'peak_hours' in result
        assert 'total_notifications' in result
        assert result['period_days'] == 30

    def test_peak_hours_at_most_5(self, app, db_session):
        with app.app_context():
            result = NotificationAnalytics.get_peak_times()
        assert len(result['peak_hours']) <= 5

    def test_missing_hours_filled_with_zero(self, app, db_session):
        with app.app_context():
            result = NotificationAnalytics.get_peak_times()
        for h in range(24):
            assert h in result['hourly_counts']

    def test_total_notifications_is_sum_of_hourly(self, app, db_session):
        with app.app_context():
            result = NotificationAnalytics.get_peak_times()
        expected = sum(result['hourly_counts'].values())
        assert result['total_notifications'] == expected

    def test_peak_hours_sorted_descending(self, app, db_session):
        from app.models import Notification, User
        from app import db
        from app.models.enums import NotificationType

        with app.app_context():
            user = User(email='analytics_pt@test.com', name='F', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            for _ in range(3):
                db.session.add(Notification(
                    user_id=user.id,
                    notification_type=NotificationType.admin_message,
                    title='t', message='m', is_read=False, is_archived=False
                ))
            db.session.commit()
            result = NotificationAnalytics.get_peak_times(days=365)

        counts = [h['count'] for h in result['peak_hours']]
        assert counts == sorted(counts, reverse=True)

    def test_returns_error_on_exception(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.analytics.db') as mock_db:
                mock_db.session.query.side_effect = Exception("fail")
                result = NotificationAnalytics.get_peak_times()
        assert result.get('success') is False or 'error' in result


# ---------------------------------------------------------------------------
# get_user_engagement
# ---------------------------------------------------------------------------

class TestGetUserEngagement:
    def test_returns_success_dict_empty_db(self, app, db_session):
        with app.app_context():
            result = NotificationAnalytics.get_user_engagement()
        assert result['success'] is True
        assert isinstance(result['user_engagement'], list)
        assert result['period_days'] == 30

    def test_limit_parameter_respected(self, app, db_session):
        from app.models import Notification, User
        from app import db
        from app.models.enums import NotificationType

        with app.app_context():
            users = []
            for i in range(5):
                u = User(email=f'analytics_ue{i}@test.com', name=f'G{i}', active=True)
                u.set_password('pw')
                db.session.add(u)
                db.session.flush()
                db.session.add(Notification(
                    user_id=u.id,
                    notification_type=NotificationType.admin_message,
                    title='t', message='m', is_read=False, is_archived=False
                ))
                users.append(u)
            db.session.commit()

            result = NotificationAnalytics.get_user_engagement(days=365, limit=3)

        assert len(result['user_engagement']) <= 3

    def test_user_engagement_row_fields(self, app, db_session):
        from app.models import Notification, User
        from app import db
        from app.models.enums import NotificationType

        with app.app_context():
            user = User(email='analytics_ue_f@test.com', name='H', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.add(Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='t', message='m', is_read=True, is_archived=False
            ))
            db.session.commit()
            result = NotificationAnalytics.get_user_engagement(days=365)

        if result['user_engagement']:
            row = result['user_engagement'][0]
            for key in ('user_id', 'total_received', 'total_read', 'total_archived', 'read_rate'):
                assert key in row

    def test_returns_error_on_exception(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.analytics.db') as mock_db:
                mock_db.session.query.side_effect = Exception("fail")
                result = NotificationAnalytics.get_user_engagement()
        assert result.get('success') is False or 'error' in result
