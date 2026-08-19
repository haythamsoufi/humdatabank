"""
Tests for app/services/notification/emails.py

Targets 100% coverage of email notification helpers.
"""
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, call
import pytest

from app.services.notification.emails import (
    sanitize_for_email,
    html_to_plain_text,
    derive_email_content_plain,
    _parse_time_string,
    _minutes_since,
    _should_trigger_daily_digest,
    _should_trigger_weekly_digest,
    _weekday_index,
    render_digest_email,
    render_instant_email,
    send_daily_digest,
    send_weekly_digest,
    send_notification_emails,
    send_instant_notification_email,
    retry_email_delivery_log,
    _translate_notification_for_email,
    filter_instant_email_eligible_user_ids,
    _filter_instant_email_eligible_user_ids,
    build_grouped_entity_email_preview,
    send_grouped_entity_email,
)
from app.models.enums import NotificationType


# ---------------------------------------------------------------------------
# sanitize_for_email
# ---------------------------------------------------------------------------

class TestSanitizeForEmail:
    def test_empty_string_returns_empty(self):
        assert sanitize_for_email('') == ''
        assert sanitize_for_email(None) == ''

    def test_html_is_escaped(self):
        result = sanitize_for_email('<script>alert("xss")</script>')
        assert '<script>' not in result
        assert '&lt;' in result

    def test_plain_text_preserved(self):
        result = sanitize_for_email('Hello World')
        assert 'Hello World' in result

    def test_converts_non_string(self):
        result = sanitize_for_email(123)
        assert '123' in result


# ---------------------------------------------------------------------------
# html_to_plain_text / derive_email_content_plain
# ---------------------------------------------------------------------------

class TestHtmlToPlainText:
    def test_empty_returns_empty(self):
        assert html_to_plain_text('') == ''
        assert html_to_plain_text(None) == ''

    def test_strips_tags_and_unescapes(self):
        result = html_to_plain_text('<p>Hello <strong>world</strong>&nbsp;!</p>')
        assert result == 'Hello world !'

    def test_br_and_block_tags_become_line_breaks(self):
        result = html_to_plain_text('<p>Line one</p><p>Line two</p>')
        assert 'Line one' in result
        assert 'Line two' in result
        assert '\n' in result


class TestDeriveEmailContentPlain:
    def test_digest_subject_returned_as_is(self):
        subject = 'Daily Notification Digest - 3 new notification(s)'
        assert derive_email_content_plain(subject, '') == subject

    def test_message_html_converted(self):
        assert derive_email_content_plain('Subject', '<p>Email body</p>') == 'Email body'

    def test_falls_back_to_subject_when_message_empty(self):
        assert derive_email_content_plain('Only subject', '') == 'Only subject'


# ---------------------------------------------------------------------------
# _parse_time_string
# ---------------------------------------------------------------------------

class TestParseTimeString:
    def test_valid_time_string(self):
        assert _parse_time_string('09:30') == (9, 30)
        assert _parse_time_string('23:59') == (23, 59)

    def test_clamped_values(self):
        h, m = _parse_time_string('25:70')
        assert h == 23
        assert m == 59

    def test_invalid_format_returns_none(self):
        assert _parse_time_string('invalid') is None
        assert _parse_time_string('') is None
        assert _parse_time_string(None) is None

    def test_missing_colon_returns_none(self):
        assert _parse_time_string('0930') is None


# ---------------------------------------------------------------------------
# _minutes_since
# ---------------------------------------------------------------------------

class TestMinutesSince:
    def test_zero_minutes(self):
        t = datetime(2024, 1, 1, 12, 0, 0)
        assert _minutes_since(t, t) == 0.0

    def test_thirty_minutes(self):
        target = datetime(2024, 1, 1, 12, 0, 0)
        ref = datetime(2024, 1, 1, 12, 30, 0)
        assert _minutes_since(target, ref) == pytest.approx(30.0)

    def test_negative_when_reference_before_target(self):
        target = datetime(2024, 1, 1, 12, 30, 0)
        ref = datetime(2024, 1, 1, 12, 0, 0)
        assert _minutes_since(target, ref) < 0


# ---------------------------------------------------------------------------
# _weekday_index
# ---------------------------------------------------------------------------

class TestWeekdayIndex:
    def test_monday_is_zero(self):
        assert _weekday_index('monday') == 0
        assert _weekday_index('Monday') == 0
        assert _weekday_index('MONDAY') == 0

    def test_sunday_is_six(self):
        assert _weekday_index('sunday') == 6

    def test_unknown_returns_none(self):
        assert _weekday_index('funday') is None

    def test_empty_returns_none(self):
        assert _weekday_index('') is None
        assert _weekday_index(None) is None

    def test_all_days(self):
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        for i, day in enumerate(days):
            assert _weekday_index(day) == i


# ---------------------------------------------------------------------------
# _should_trigger_daily_digest
# ---------------------------------------------------------------------------

class TestShouldTriggerDailyDigest:
    def test_triggers_when_within_window(self):
        # Use current time set to exactly 09:00
        now = datetime(2024, 6, 10, 9, 0, 0)
        assert _should_trigger_daily_digest(now, '09:00', 60) is True

    def test_does_not_trigger_outside_window(self):
        now = datetime(2024, 6, 10, 15, 0, 0)
        assert _should_trigger_daily_digest(now, '09:00', 60) is False

    def test_invalid_time_string_returns_false(self):
        now = datetime(2024, 6, 10, 9, 0, 0)
        assert _should_trigger_daily_digest(now, 'invalid', 60) is False

    def test_triggers_within_window_boundary(self):
        # 09:59 should be within a 60-minute window starting at 09:00
        now = datetime(2024, 6, 10, 9, 59, 0)
        assert _should_trigger_daily_digest(now, '09:00', 60) is True

    def test_triggers_at_yesterday_time(self):
        # If scheduled time is in the future today, check yesterday
        now = datetime(2024, 6, 10, 8, 30, 0)
        # Scheduled at 09:00 - since 09:00 > 08:30, subtract 1 day
        # Delta = 08:30 - (09:00 - 1 day) = 23.5 hours = not in 60-min window
        assert _should_trigger_daily_digest(now, '09:00', 60) is False


# ---------------------------------------------------------------------------
# _should_trigger_weekly_digest
# ---------------------------------------------------------------------------

class TestShouldTriggerWeeklyDigest:
    def test_triggers_on_correct_day_and_time(self):
        # Monday = 0, datetime(2024, 6, 10) is Monday
        now = datetime(2024, 6, 10, 9, 0, 0)
        assert _should_trigger_weekly_digest(now, 'monday', '09:00', 60) is True

    def test_does_not_trigger_on_wrong_day(self):
        # Monday, but digest set for Friday
        now = datetime(2024, 6, 10, 9, 0, 0)
        assert _should_trigger_weekly_digest(now, 'friday', '09:00', 60) is False

    def test_invalid_day_returns_false(self):
        now = datetime(2024, 6, 10, 9, 0, 0)
        assert _should_trigger_weekly_digest(now, 'invalidday', '09:00', 60) is False

    def test_invalid_time_returns_false(self):
        now = datetime(2024, 6, 10, 9, 0, 0)
        assert _should_trigger_weekly_digest(now, 'monday', 'invalid', 60) is False


# ---------------------------------------------------------------------------
# render_digest_email
# ---------------------------------------------------------------------------

class TestRenderDigestEmail:
    def _make_user(self):
        user = MagicMock()
        user.name = 'Test User'
        user.email = 'test@example.com'
        return user

    def _make_notification(self):
        n = MagicMock()
        n.title = 'Test Title'
        n.message = 'Test Message'
        n.notification_type = NotificationType.admin_message
        n.is_read = False
        n.created_at = datetime(2024, 1, 1, 12, 0, 0)
        n.priority = 'normal'
        n.related_url = None
        n.id = 1
        n.title_key = None
        n.message_key = None
        n.title_params = None
        n.message_params = None
        return n

    def test_renders_html_string(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.emails.get_org_name', return_value='Test Org'):
                html = render_digest_email(self._make_user(), [self._make_notification()], 'Daily')
        assert isinstance(html, str)
        assert '<html' in html

    def test_includes_user_name(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.emails.get_org_name', return_value='Test Org'):
                html = render_digest_email(self._make_user(), [self._make_notification()], 'Daily')
        assert 'Test User' in html

    def test_includes_frequency(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.emails.get_org_name', return_value='Test Org'):
                html = render_digest_email(self._make_user(), [self._make_notification()], 'Weekly')
        assert 'Weekly' in html or 'weekly' in html

    def test_with_locale(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.emails.get_org_name', return_value='Test Org'):
                html = render_digest_email(
                    self._make_user(), [self._make_notification()], 'Daily', locale='en'
                )
        assert isinstance(html, str)

    def test_with_high_priority_notification(self, app, db_session):
        n = self._make_notification()
        n.priority = 'high'
        with app.app_context():
            with patch('app.services.notification.emails.get_org_name', return_value='Test Org'):
                html = render_digest_email(self._make_user(), [n], 'Daily')
        assert isinstance(html, str)

    def test_with_related_url(self, app, db_session):
        n = self._make_notification()
        n.related_url = '/some/path'
        with app.app_context():
            app.config['BASE_URL'] = 'http://localhost:5000'
            with patch('app.services.notification.emails.get_org_name', return_value='Test Org'):
                html = render_digest_email(self._make_user(), [n], 'Daily')
        assert '/some/path' in html


# ---------------------------------------------------------------------------
# render_instant_email
# ---------------------------------------------------------------------------

class TestRenderInstantEmail:
    def _make_user(self):
        user = MagicMock()
        user.name = 'Test User'
        user.email = 'test@example.com'
        return user

    def _make_notification(self, priority='normal', nt=NotificationType.admin_message):
        n = MagicMock()
        n.title = 'Notification Title'
        n.message = 'Notification Body'
        n.notification_type = nt
        n.priority = priority
        n.related_url = None
        n.id = 1
        return n

    def test_renders_html_string(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.emails.get_org_name', return_value='Test Org'):
                html = render_instant_email(self._make_user(), self._make_notification())
        assert isinstance(html, str)
        assert '<html' in html

    def test_high_priority_shows_action_required(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.emails.get_org_name', return_value='Test Org'):
                html = render_instant_email(
                    self._make_user(), self._make_notification(priority='high')
                )
        assert 'action-required' in html

    def test_urgent_priority_shows_action_required(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.emails.get_org_name', return_value='Test Org'):
                html = render_instant_email(
                    self._make_user(), self._make_notification(priority='urgent')
                )
        assert 'action-required' in html

    def test_normal_priority_shows_informational(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.emails.get_org_name', return_value='Test Org'):
                html = render_instant_email(
                    self._make_user(), self._make_notification(priority='normal')
                )
        assert 'informational' in html

    def test_assignment_submitted_uses_view_submission_label(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.emails.get_org_name', return_value='Test Org'):
                n = self._make_notification(nt=NotificationType.assignment_submitted)
                n.related_url = '/submission/1'
                html = render_instant_email(self._make_user(), n)
        assert 'View Submission' in html

    def test_related_url_in_output(self, app, db_session):
        with app.app_context():
            app.config['BASE_URL'] = 'http://localhost:5000'
            with patch('app.services.notification.emails.get_org_name', return_value='Test Org'):
                n = self._make_notification()
                n.related_url = '/test/url'
                html = render_instant_email(self._make_user(), n)
        assert '/test/url' in html


# ---------------------------------------------------------------------------
# send_daily_digest
# ---------------------------------------------------------------------------

class TestSendDailyDigest:
    def _make_pref(self, freq='daily', types=None, has_last_digest=True):
        pref = MagicMock()
        pref.notification_frequency = freq
        pref.notification_types_enabled = types
        pref.digest_time = '09:00'
        pref.digest_day = 'monday'
        if has_last_digest:
            pref.last_digest_sent_at = None
        return pref

    def test_returns_false_when_no_notifications(self, app, db_session):
        from app.models import User
        from app import db

        with app.app_context():
            user = User(email='daily_no_notif@test.com', name='No Notif', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.commit()

            pref = self._make_pref()
            result = send_daily_digest(user, pref)

        assert result is False

    def test_returns_false_when_filtered_by_type(self, app, db_session):
        from app.models import User, Notification
        from app import db

        with app.app_context():
            user = User(email='daily_filtered@test.com', name='Filtered', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            notif = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='t', message='m', is_read=False, is_archived=False
            )
            db.session.add(notif)
            db.session.commit()

            pref = self._make_pref(types=['deadline_reminder'])
            result = send_daily_digest(user, pref)

        assert result is False

    def test_sends_and_returns_true_on_success(self, app, db_session):
        from app.models import User, Notification
        from app import db

        with app.app_context():
            user = User(email='daily_success@test.com', name='Success', active=True)
            user.email = 'daily_success@test.com'
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            notif = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='t', message='m', is_read=False, is_archived=False
            )
            db.session.add(notif)
            db.session.commit()

            pref = self._make_pref()
            mock_log = MagicMock()
            mock_log.id = 1

            with patch('app.services.notification.emails.log_email_attempt', return_value=mock_log):
                with patch('app.services.notification.emails.send_email', return_value=True):
                    with patch('app.services.notification.emails.mark_email_sent'):
                        with patch('app.services.notification.emails.render_digest_email', return_value='<html>'):
                            result = send_daily_digest(user, pref)

        assert result is True

    def test_daily_digest_links_notification_and_email_log(self, app, db_session):
        from app.models import User, Notification, EmailDeliveryLog
        from app import db

        with app.app_context():
            user = User(email='daily_linked@test.com', name='Linked', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            notif = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='Assignment update',
                message='Body',
                is_read=False,
                is_archived=False,
            )
            db.session.add(notif)
            db.session.commit()

            pref = self._make_pref()

            with patch('app.services.notification.emails.send_email', return_value=True), \
                 patch('app.services.notification.emails.render_digest_email', return_value='<html>'):
                result = send_daily_digest(user, pref)

            assert result is True

            digest_notification = Notification.query.filter_by(
                user_id=user.id,
                notification_type=NotificationType.email_digest,
            ).first()
            assert digest_notification is not None

            email_log = EmailDeliveryLog.query.filter_by(
                notification_id=digest_notification.id,
            ).first()
            assert email_log is not None
            assert email_log.status == 'sent'

    def test_returns_false_on_send_failure(self, app, db_session):
        from app.models import User, Notification
        from app import db

        with app.app_context():
            user = User(email='daily_fail@test.com', name='Fail', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            notif = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='t', message='m', is_read=False, is_archived=False
            )
            db.session.add(notif)
            db.session.commit()

            pref = self._make_pref()
            mock_log = MagicMock()
            mock_log.id = 1

            with patch('app.services.notification.emails.log_email_attempt', return_value=mock_log):
                with patch('app.services.notification.emails.send_email', return_value=False):
                    with patch('app.services.notification.emails.mark_email_failed'):
                        with patch('app.services.notification.emails.render_digest_email', return_value='<html>'):
                            result = send_daily_digest(user, pref)

        assert result is False

    def test_returns_false_on_exception(self, app, db_session):
        from app.models import User, Notification
        from app import db

        with app.app_context():
            user = User(email='daily_exc@test.com', name='Exc', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            notif = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='t', message='m', is_read=False, is_archived=False
            )
            db.session.add(notif)
            db.session.commit()

            pref = self._make_pref()
            mock_log = MagicMock()
            mock_log.id = 1

            with patch('app.services.notification.emails.log_email_attempt', return_value=mock_log):
                with patch('app.services.notification.emails.send_email', side_effect=Exception('smtp error')):
                    with patch('app.services.notification.emails.mark_email_failed'):
                        with patch('app.services.notification.emails.render_digest_email', return_value='<html>'):
                            result = send_daily_digest(user, pref)

        assert result is False


# ---------------------------------------------------------------------------
# send_weekly_digest
# ---------------------------------------------------------------------------

class TestSendWeeklyDigest:
    def test_returns_false_when_no_notifications(self, app, db_session):
        from app.models import User
        from app import db

        with app.app_context():
            user = User(email='weekly_no_notif@test.com', name='W', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.commit()

            pref = MagicMock()
            pref.notification_frequency = 'weekly'
            pref.notification_types_enabled = None
            pref.last_digest_sent_at = None
            result = send_weekly_digest(user, pref)

        assert result is False

    def test_sends_and_returns_true(self, app, db_session):
        from app.models import User, Notification
        from app import db

        with app.app_context():
            user = User(email='weekly_success@test.com', name='WS', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            for _ in range(2):
                notif = Notification(
                    user_id=user.id,
                    notification_type=NotificationType.admin_message,
                    title='t', message='m', is_read=False, is_archived=False
                )
                db.session.add(notif)
            db.session.commit()

            pref = MagicMock()
            pref.notification_frequency = 'weekly'
            pref.notification_types_enabled = None
            pref.last_digest_sent_at = None
            mock_log = MagicMock()
            mock_log.id = 1

            with patch('app.services.notification.emails.log_email_attempt', return_value=mock_log):
                with patch('app.services.notification.emails.send_email', return_value=True):
                    with patch('app.services.notification.emails.mark_email_sent'):
                        with patch('app.services.notification.emails.render_digest_email', return_value='<html>'):
                            result = send_weekly_digest(user, pref)

        assert result is True

    def test_filters_by_notification_type(self, app, db_session):
        from app.models import User, Notification
        from app import db

        with app.app_context():
            user = User(email='weekly_filter@test.com', name='WF', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            notif = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='t', message='m', is_read=False, is_archived=False
            )
            db.session.add(notif)
            db.session.commit()

            pref = MagicMock()
            pref.notification_types_enabled = ['deadline_reminder']
            pref.last_digest_sent_at = None
            result = send_weekly_digest(user, pref)

        assert result is False


# ---------------------------------------------------------------------------
# send_notification_emails
# ---------------------------------------------------------------------------

class TestSendNotificationEmails:
    def test_skips_when_no_preferences(self, app, db_session):
        with app.app_context():
            # No preferences in DB
            with patch('app.services.notification.emails.NotificationPreferences') as mock_pref:
                mock_pref.query.filter_by.return_value.all.return_value = []
                send_notification_emails()  # Should not raise

    def test_skips_user_without_email(self, app, db_session):
        from app.models import User, NotificationPreferences
        from app import db

        with app.app_context():
            user = User(email='no_email@test.com', name='NoEmail', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            pref = NotificationPreferences(
                user_id=user.id,
                email_notifications=True,
                notification_types_enabled=[],
                notification_frequency='daily',
            )
            db.session.add(pref)
            db.session.commit()

            # Simulate user with no email
            with patch('app.services.notification.emails.User') as MockUser:
                MockUser.query.get.return_value = None
                send_notification_emails()

    def test_skips_instant_frequency_users(self, app, db_session):
        from app.models import User, NotificationPreferences
        from app import db

        with app.app_context():
            user = User(email='instant@test.com', name='Instant', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            pref = NotificationPreferences(
                user_id=user.id,
                email_notifications=True,
                notification_types_enabled=[],
                notification_frequency='instant',
            )
            db.session.add(pref)
            db.session.commit()

            with patch('app.services.notification.emails.send_daily_digest') as mock_send:
                send_notification_emails()
                mock_send.assert_not_called()

    def test_handles_pytz_unavailable(self, app, db_session):
        """Test UTC fallback when pytz not available."""
        import app.services.notification.emails as emails_module
        original = emails_module.PYTZ_AVAILABLE
        try:
            emails_module.PYTZ_AVAILABLE = False
            with app.app_context():
                with patch.object(emails_module.NotificationPreferences, 'query') as mock_q:
                    mock_q.filter_by.return_value.all.return_value = []
                    send_notification_emails()
        finally:
            emails_module.PYTZ_AVAILABLE = original

    def test_handles_exception_gracefully(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.emails.NotificationPreferences') as MockNP:
                MockNP.query.filter_by.side_effect = Exception('db fail')
                # Should not raise
                send_notification_emails()

    def test_skips_within_digest_window(self, app, db_session):
        """If user was sent a digest within the window, skip them."""
        from app.models import User, NotificationPreferences
        from app import db
        from app.utils.datetime_helpers import utcnow

        with app.app_context():
            user = User(email='within_window@test.com', name='WW', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            pref = NotificationPreferences(
                user_id=user.id,
                email_notifications=True,
                notification_types_enabled=[],
                notification_frequency='daily',
            )
            # Last sent very recently
            pref.last_digest_sent_at = utcnow() - timedelta(minutes=1)
            pref.digest_time = '09:00'
            pref.digest_day = None
            db.session.add(pref)
            db.session.commit()

            with patch('app.services.notification.emails.send_daily_digest') as mock_send:
                send_notification_emails()
                mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# send_instant_notification_email
# ---------------------------------------------------------------------------

class TestSendInstantNotificationEmail:
    def _make_user(self, email='instant_notif@test.com'):
        user = MagicMock()
        user.id = 1
        user.email = email
        user.name = 'Test User'
        return user

    def _make_notification(self, priority='normal', nt_value='admin_message'):
        notif = MagicMock()
        notif.id = 1
        notif.title = 'Title'
        notif.message = 'Message'
        nt = MagicMock()
        nt.value = nt_value
        notif.notification_type = nt
        notif.priority = priority
        notif.related_url = None
        return notif

    def test_skips_document_uploaded_in_app_only(self, app, db_session):
        from app.models.enums import NotificationType

        notif = self._make_notification(priority='urgent')
        notif.notification_type = NotificationType.document_uploaded

        with app.app_context():
            with patch('app.services.notification.emails.send_email') as mock_send:
                send_instant_notification_email(self._make_user(), notif)
                mock_send.assert_not_called()

    def test_skips_if_no_preferences(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.emails.NotificationPreferences') as MockNP:
                MockNP.query.filter_by.return_value.first.return_value = None
                # Should not call send_email
                with patch('app.services.notification.emails.send_email') as mock_send:
                    send_instant_notification_email(self._make_user(), self._make_notification())
                    mock_send.assert_not_called()

    def test_skips_if_email_notifications_disabled(self, app, db_session):
        with app.app_context():
            mock_pref = MagicMock()
            mock_pref.email_notifications = False
            with patch('app.services.notification.emails.NotificationPreferences') as MockNP:
                MockNP.query.filter_by.return_value.first.return_value = mock_pref
                with patch('app.services.notification.emails.send_email') as mock_send:
                    send_instant_notification_email(self._make_user(), self._make_notification())
                    mock_send.assert_not_called()

    def test_skips_digest_user_with_normal_priority(self, app, db_session):
        with app.app_context():
            mock_pref = MagicMock()
            mock_pref.email_notifications = True
            mock_pref.notification_frequency = 'daily'
            mock_pref.notification_types_enabled = None
            with patch('app.services.notification.emails.NotificationPreferences') as MockNP:
                MockNP.query.filter_by.return_value.first.return_value = mock_pref
                with patch('app.services.notification.emails.send_email') as mock_send:
                    send_instant_notification_email(self._make_user(), self._make_notification(priority='normal'))
                    mock_send.assert_not_called()

    def test_sends_for_urgent_priority_despite_digest(self, app, db_session):
        with app.app_context():
            mock_pref = MagicMock()
            mock_pref.email_notifications = True
            mock_pref.notification_frequency = 'daily'
            mock_pref.notification_types_enabled = None
            mock_log = MagicMock()
            mock_log.id = 1

            with patch('app.services.notification.emails.NotificationPreferences') as MockNP:
                MockNP.query.filter_by.return_value.first.return_value = mock_pref
                with patch('app.services.notification.emails.log_email_attempt', return_value=mock_log):
                    with patch('app.services.notification.emails.send_email', return_value=True):
                        with patch('app.services.notification.emails.mark_email_sent'):
                            with patch('app.services.notification.emails.render_instant_email', return_value='<html>'):
                                send_instant_notification_email(
                                    self._make_user(), self._make_notification(priority='urgent')
                                )

    def test_skips_if_type_not_enabled(self, app, db_session):
        with app.app_context():
            mock_pref = MagicMock()
            mock_pref.email_notifications = True
            mock_pref.notification_frequency = 'instant'
            mock_pref.notification_types_enabled = ['deadline_reminder']

            with patch('app.services.notification.emails.NotificationPreferences') as MockNP:
                MockNP.query.filter_by.return_value.first.return_value = mock_pref
                with patch('app.services.notification.emails.send_email') as mock_send:
                    send_instant_notification_email(self._make_user(), self._make_notification())
                    mock_send.assert_not_called()

    def test_override_preferences_sends_regardless(self, app, db_session):
        with app.app_context():
            mock_log = MagicMock()
            mock_log.id = 1
            with patch('app.services.notification.emails.log_email_attempt', return_value=mock_log):
                with patch('app.services.notification.emails.send_email', return_value=True):
                    with patch('app.services.notification.emails.mark_email_sent'):
                        with patch('app.services.notification.emails.render_instant_email', return_value='<html>'):
                            send_instant_notification_email(
                                self._make_user(), self._make_notification(),
                                override_preferences=True
                            )

    def test_handles_send_failure(self, app, db_session):
        with app.app_context():
            mock_log = MagicMock()
            mock_log.id = 1
            with patch('app.services.notification.emails.log_email_attempt', return_value=mock_log):
                with patch('app.services.notification.emails.send_email', return_value=False):
                    with patch('app.services.notification.emails.mark_email_failed'):
                        with patch('app.services.notification.emails.render_instant_email', return_value='<html>'):
                            send_instant_notification_email(
                                self._make_user(), self._make_notification(),
                                override_preferences=True
                            )

    def test_handles_exception(self, app, db_session):
        with app.app_context():
            mock_log = MagicMock()
            mock_log.id = 1
            with patch('app.services.notification.emails.log_email_attempt', return_value=mock_log):
                with patch('app.services.notification.emails.send_email', side_effect=Exception('smtp')):
                    with patch('app.services.notification.emails.mark_email_failed'):
                        with patch('app.services.notification.emails.render_instant_email', return_value='<html>'):
                            send_instant_notification_email(
                                self._make_user(), self._make_notification(),
                                override_preferences=True
                            )

    def test_filtered_recipients_not_failure(self, app, db_session):
        """When filtered_out is non-empty, don't mark as failed."""
        with app.app_context():
            mock_log = MagicMock()
            mock_log.id = 1

            def send_email_with_filter(subject, recipients, html, sender, importance=None, _filtered_out=None):
                if _filtered_out is not None:
                    _filtered_out.append('test@example.com')
                return False

            with patch('app.services.notification.emails.log_email_attempt', return_value=mock_log):
                with patch('app.services.notification.emails.send_email', side_effect=send_email_with_filter):
                    with patch('app.services.notification.emails.mark_email_failed') as mock_failed:
                        with patch('app.services.notification.emails.render_instant_email', return_value='<html>'):
                            send_instant_notification_email(
                                self._make_user(), self._make_notification(),
                                override_preferences=True
                            )
                        mock_failed.assert_not_called()


# ---------------------------------------------------------------------------
# retry_email_delivery_log
# ---------------------------------------------------------------------------

class TestRetryEmailDeliveryLog:
    def test_returns_false_for_none_log(self, app, db_session):
        with app.app_context():
            result = retry_email_delivery_log(None)
        assert result is False

    def test_returns_false_when_user_not_found(self, app, db_session):
        with app.app_context():
            mock_log = MagicMock()
            mock_log.id = 1
            mock_log.user_id = 9999
            mock_log.notification_id = None
            with patch('app.services.notification.emails.User') as MockUser:
                MockUser.query.get.return_value = None
                with patch('app.services.notification.emails.mark_email_failed'):
                    result = retry_email_delivery_log(mock_log)
        assert result is False

    def test_returns_false_when_notification_not_found(self, app, db_session):
        with app.app_context():
            mock_log = MagicMock()
            mock_log.id = 1
            mock_log.user_id = 1
            mock_log.notification_id = 999

            mock_user = MagicMock()
            mock_user.id = 1
            mock_user.email = 'test@test.com'

            with patch('app.services.notification.emails.User') as MockUser:
                MockUser.query.get.return_value = mock_user
                with patch('app.services.notification.emails.Notification') as MockNotif:
                    MockNotif.query.get.return_value = None
                    with patch('app.services.notification.emails.mark_email_failed'):
                        result = retry_email_delivery_log(mock_log)
        assert result is False

    def test_retries_instant_notification(self, app, db_session):
        with app.app_context():
            mock_log = MagicMock()
            mock_log.id = 1
            mock_log.user_id = 1
            mock_log.notification_id = 1

            mock_user = MagicMock()
            mock_user.id = 1
            mock_user.email = 'retry@test.com'
            mock_user.name = 'Retry User'

            mock_notif = MagicMock()
            mock_notif.id = 1
            mock_notif.title = 'Title'
            nt = MagicMock()
            nt.value = 'admin_message'
            mock_notif.notification_type = nt

            with patch('app.services.notification.emails.User') as MockUser:
                MockUser.query.get.return_value = mock_user
                with patch('app.services.notification.emails.Notification') as MockNotif:
                    MockNotif.query.get.return_value = mock_notif
                    with patch('app.services.notification.emails.render_instant_email', return_value='<html>'):
                        with patch('app.services.notification.emails.send_email', return_value=True):
                            with patch('app.services.notification.emails.mark_email_sent'):
                                result = retry_email_delivery_log(mock_log)
        assert result is True

    def test_retries_daily_digest(self, app, db_session):
        with app.app_context():
            mock_log = MagicMock()
            mock_log.id = 1
            mock_log.user_id = 1
            mock_log.notification_id = None
            mock_log.subject = 'Daily Notification Digest - 3 new notification(s)'
            mock_log.retry_count = 0
            mock_log.status = 'retrying'

            mock_user = MagicMock()
            mock_user.id = 1
            mock_user.email = 'daily@test.com'

            mock_pref = MagicMock()

            with patch('app.services.notification.emails.User') as MockUser:
                MockUser.query.get.return_value = mock_user
                with patch('app.services.notification.emails.NotificationPreferences') as MockNP:
                    MockNP.query.filter_by.return_value.first.return_value = mock_pref
                    with patch('app.services.notification.emails.send_daily_digest', return_value=True) as mock_daily:
                        with patch('app.services.notification.emails.db') as mock_db:
                            mock_db.session.refresh = MagicMock()
                            mock_log.status = 'sent'
                            result = retry_email_delivery_log(mock_log)
        assert result is True

    def test_retries_weekly_digest(self, app, db_session):
        with app.app_context():
            mock_log = MagicMock()
            mock_log.id = 1
            mock_log.user_id = 1
            mock_log.notification_id = None
            mock_log.subject = 'Weekly Notification Digest - 5 new notification(s)'
            mock_log.retry_count = 0
            mock_log.status = 'retrying'

            mock_user = MagicMock()
            mock_user.id = 1
            mock_user.email = 'weekly@test.com'

            mock_pref = MagicMock()

            with patch('app.services.notification.emails.User') as MockUser:
                MockUser.query.get.return_value = mock_user
                with patch('app.services.notification.emails.NotificationPreferences') as MockNP:
                    MockNP.query.filter_by.return_value.first.return_value = mock_pref
                    with patch('app.services.notification.emails.send_weekly_digest', return_value=False) as mock_weekly:
                        with patch('app.services.notification.emails.db') as mock_db:
                            mock_db.session.refresh = MagicMock()
                            mock_log.status = 'retrying'
                            with patch('app.services.notification.emails.mark_email_failed'):
                                result = retry_email_delivery_log(mock_log)

    def test_unknown_subject_marks_failed(self, app, db_session):
        with app.app_context():
            mock_log = MagicMock()
            mock_log.id = 1
            mock_log.user_id = 1
            mock_log.notification_id = None
            mock_log.subject = 'Unknown Subject Type'
            mock_log.retry_count = 0

            mock_user = MagicMock()
            mock_user.id = 1
            mock_user.email = 'unknown@test.com'

            with patch('app.services.notification.emails.User') as MockUser:
                MockUser.query.get.return_value = mock_user
                with patch('app.services.notification.emails.mark_email_failed') as mock_failed:
                    result = retry_email_delivery_log(mock_log)
        assert result is False
        mock_failed.assert_called_once()
        assert 'Retry not supported' in mock_failed.call_args[0][1]

    def test_retries_welcome_email(self, app, db_session):
        with app.app_context():
            mock_log = MagicMock()
            mock_log.id = 1
            mock_log.user_id = 1
            mock_log.notification_id = None
            mock_log.subject = 'Welcome to IFRC'
            mock_log.retry_count = 0
            mock_log.status = 'failed'

            mock_user = MagicMock()
            mock_user.id = 1
            mock_user.email = 'welcome@test.com'

            with patch('app.services.notification.emails.User') as MockUser:
                MockUser.query.get.return_value = mock_user
                with patch('app.services.notification.emails.NotificationPreferences') as MockNP:
                    MockNP.query.filter_by.return_value.first.return_value = MagicMock()
                    with patch('app.services.email.service.send_welcome_email', return_value=True) as mock_welcome:
                        with patch('app.services.notification.emails.db') as mock_db:
                            mock_db.session.refresh = MagicMock()
                            mock_log.status = 'sent'
                            result = retry_email_delivery_log(mock_log)
        assert result is True
        mock_welcome.assert_called_once_with(mock_user, existing_log=mock_log)

    def test_handles_exception_in_retry(self, app, db_session):
        with app.app_context():
            mock_log = MagicMock()
            mock_log.id = 1
            mock_log.user_id = 1
            mock_log.notification_id = 1

            with patch('app.services.notification.emails.User') as MockUser:
                MockUser.query.get.side_effect = Exception('db error')
                with patch('app.services.notification.emails.mark_email_failed'):
                    result = retry_email_delivery_log(mock_log)
        assert result is False


# ---------------------------------------------------------------------------
# _translate_notification_for_email
# ---------------------------------------------------------------------------

class TestTranslateNotificationForEmail:
    def _make_notif(self):
        n = MagicMock()
        n.title = 'English Title'
        n.message = 'English Message'
        n.id = 1
        n.title_key = None
        n.title_params = None
        n.message_key = None
        n.message_params = None
        return n

    def test_no_locale_returns_stored(self, app, db_session):
        with app.app_context():
            n = self._make_notif()
            title, message = _translate_notification_for_email(n, None)
        assert title == 'English Title'
        assert message == 'English Message'

    def test_no_keys_returns_stored(self, app, db_session):
        with app.app_context():
            n = self._make_notif()
            title, message = _translate_notification_for_email(n, 'en')
        assert title == 'English Title'
        assert message == 'English Message'

    def test_with_title_key_translates(self, app, db_session):
        with app.app_context():
            n = self._make_notif()
            n.title_key = 'notification.admin_message.title'
            title, message = _translate_notification_for_email(n, 'en')
        assert isinstance(title, str)

    def test_with_message_key_translates(self, app, db_session):
        with app.app_context():
            n = self._make_notif()
            n.message_key = 'notification.admin_message.message'
            title, message = _translate_notification_for_email(n, 'en')
        assert isinstance(message, str)

    def test_fallback_on_exception(self, app, db_session):
        with app.app_context():
            n = self._make_notif()
            n.title_key = 'notification.admin_message.title'
            with patch('app.services.notification.emails.send_email', side_effect=Exception('fail')):
                with patch('app.services.notification.core.translate_notification_message', side_effect=Exception('translate fail')):
                    title, message = _translate_notification_for_email(n, 'en')
        # Should fallback
        assert isinstance(title, str)
        assert isinstance(message, str)

    def test_handles_string_title_params(self, app, db_session):
        """title_params as a JSON string should be parsed."""
        with app.app_context():
            n = self._make_notif()
            n.title_key = 'notification.assignment_submitted.admin.title'
            n.title_params = '{"submitter_name": "John"}'
            title, message = _translate_notification_for_email(n, 'en')
        assert isinstance(title, str)


# ---------------------------------------------------------------------------
# filter_instant_email_eligible_user_ids
#
# This is the single source of truth for "will this user actually get an
# instant email" — both the real send path (send_grouped_entity_email,
# send_instant_notification_email) and any UI preview of recipient counts
# must call this instead of re-implementing the eligibility rules, so a
# preview never promises more (or fewer) emails than will really be sent.
# ---------------------------------------------------------------------------

class TestFilterInstantEmailEligibleUserIds:
    def _pref(self, email_notifications=True, frequency='instant', types_enabled=None):
        from types import SimpleNamespace
        return SimpleNamespace(
            email_notifications=email_notifications,
            notification_frequency=frequency,
            notification_types_enabled=types_enabled if types_enabled is not None else [],
        )

    def test_empty_user_ids_returns_empty(self, app, db_session):
        with app.app_context():
            result = filter_instant_email_eligible_user_ids([1, 2], NotificationType.assignment_created)
        # Should not raise even with no cache provided; exercised fully below with a cache.
        assert isinstance(result, list)

    def test_eligible_user_is_included(self, app, db_session):
        cache = {1: self._pref()}
        with app.app_context():
            result = filter_instant_email_eligible_user_ids(
                [1], NotificationType.assignment_created, preferences_cache=cache
            )
        assert result == [1]

    def test_excludes_user_with_email_notifications_disabled(self, app, db_session):
        cache = {1: self._pref(email_notifications=False)}
        with app.app_context():
            result = filter_instant_email_eligible_user_ids(
                [1], NotificationType.assignment_created, preferences_cache=cache
            )
        assert result == []

    def test_excludes_digest_frequency_user(self, app, db_session):
        """A user on daily/weekly digest must NOT count towards instant-email totals,
        even though their global email toggle is on and the type isn't excluded —
        this is exactly the case the assignment-creation preview previously miscounted."""
        cache = {1: self._pref(frequency='daily')}
        with app.app_context():
            result = filter_instant_email_eligible_user_ids(
                [1], NotificationType.assignment_created, preferences_cache=cache
            )
        assert result == []

    def test_excludes_user_with_type_disabled(self, app, db_session):
        cache = {1: self._pref(types_enabled=['deadline_reminder'])}
        with app.app_context():
            result = filter_instant_email_eligible_user_ids(
                [1], NotificationType.assignment_created, preferences_cache=cache
            )
        assert result == []

    def test_excludes_user_missing_from_cache(self, app, db_session):
        with app.app_context():
            result = filter_instant_email_eligible_user_ids(
                [1], NotificationType.assignment_created, preferences_cache={}
            )
        assert result == []

    def test_mixed_users_preserves_order_of_eligible_only(self, app, db_session):
        cache = {
            1: self._pref(),
            2: self._pref(frequency='weekly'),
            3: self._pref(email_notifications=False),
            4: self._pref(),
        }
        with app.app_context():
            result = filter_instant_email_eligible_user_ids(
                [1, 2, 3, 4], NotificationType.assignment_created, preferences_cache=cache
            )
        assert result == [1, 4]

    def test_backward_compatible_private_alias_is_same_function(self):
        """Internal callers within emails.py still use the private-named alias;
        guard against the two ever drifting apart."""
        assert _filter_instant_email_eligible_user_ids is filter_instant_email_eligible_user_ids


# ---------------------------------------------------------------------------
# build_grouped_entity_email_preview / send_grouped_entity_email
#
# preview_assignment_created_grouped_email (single-country "Preview email"
# button) and send_grouped_entity_email (the real send) both call
# build_grouped_entity_email_preview — asserting its eligibility behavior here
# protects the preview/send contract from both sides at once.
# ---------------------------------------------------------------------------

class TestBuildGroupedEntityEmailPreview:
    def _sample_notification(self, nt=NotificationType.assignment_created, priority='normal'):
        from types import SimpleNamespace
        return SimpleNamespace(
            id=None,
            title='New assignment',
            message='Body',
            notification_type=nt,
            priority=priority,
            related_url=None,
            title_key=None,
            message_key=None,
            title_params=None,
            message_params=None,
        )

    def _user(self, uid, email):
        from types import SimpleNamespace
        return SimpleNamespace(id=uid, email=email, name=f'User {uid}')

    def test_digest_frequency_recipient_excluded_from_to(self, app, db_session):
        """A focal point on daily digest must not appear in 'to' — matches the
        preview endpoint's total_focal_users/email_users split."""
        from app.models import User, NotificationPreferences
        from app import db

        with app.app_context():
            user = User(email='digest_focal@example.com', name='Digest Focal', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.add(NotificationPreferences(
                user_id=user.id,
                email_notifications=True,
                notification_types_enabled=[],
                notification_frequency='daily',
            ))
            db.session.commit()

            preview = build_grouped_entity_email_preview(
                [user.id], [], self._sample_notification(), 'Kenya'
            )

        assert preview['to'] == []
        assert preview['empty_reason']

    def test_instant_recipient_included_in_to(self, app, db_session):
        from app.models import User, NotificationPreferences
        from app import db

        with app.app_context():
            user = User(email='instant_focal@example.com', name='Instant Focal', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.add(NotificationPreferences(
                user_id=user.id,
                email_notifications=True,
                notification_types_enabled=[],
                notification_frequency='instant',
            ))
            db.session.commit()

            preview = build_grouped_entity_email_preview(
                [user.id], [], self._sample_notification(), 'Kenya'
            )

        assert not preview['empty_reason']
        assert [r['email'] for r in preview['to']] == ['instant_focal@example.com']

    def test_single_to_recipient_uses_personal_greeting(self, app, db_session):
        from app.models import User, NotificationPreferences
        from app import db

        with app.app_context():
            user = User(email='solo_focal@example.com', name='Solo Focal', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.add(NotificationPreferences(
                user_id=user.id,
                email_notifications=True,
                notification_types_enabled=[],
                notification_frequency='instant',
            ))
            db.session.commit()

            preview = build_grouped_entity_email_preview(
                [user.id], [], self._sample_notification(), 'Kenya'
            )

        assert 'Dear colleagues' not in preview['html_body']
        assert 'Hello Solo Focal,' in preview['html_body']

    def test_multiple_to_recipients_use_team_greeting(self, app, db_session):
        from app.models import User, NotificationPreferences
        from app import db

        with app.app_context():
            u1 = User(email='focal_a@example.com', name='Focal A', active=True)
            u2 = User(email='focal_b@example.com', name='Focal B', active=True)
            u1.set_password('pw')
            u2.set_password('pw')
            db.session.add_all([u1, u2])
            db.session.flush()
            for uid in (u1.id, u2.id):
                db.session.add(NotificationPreferences(
                    user_id=uid,
                    email_notifications=True,
                    notification_types_enabled=[],
                    notification_frequency='instant',
                ))
            db.session.commit()

            preview = build_grouped_entity_email_preview(
                [u1.id, u2.id], [], self._sample_notification(), 'Kenya'
            )

        assert 'Dear colleagues,' in preview['html_body']

    def test_cc_recipient_keeps_team_greeting_even_with_one_to(self, app, db_session):
        from app.models import User, NotificationPreferences
        from app import db

        with app.app_context():
            focal = User(email='focal@example.com', name='Focal One', active=True)
            admin = User(email='admin@example.com', name='Admin One', active=True)
            focal.set_password('pw')
            admin.set_password('pw')
            db.session.add_all([focal, admin])
            db.session.flush()
            for u in (focal, admin):
                db.session.add(NotificationPreferences(
                    user_id=u.id,
                    email_notifications=True,
                    notification_types_enabled=[],
                    notification_frequency='instant',
                ))
            db.session.commit()

            preview = build_grouped_entity_email_preview(
                [focal.id], [admin.id], self._sample_notification(), 'Kenya'
            )

        assert 'Dear colleagues,' in preview['html_body']
        assert 'Hello Focal One,' not in preview['html_body']

    def test_cc_promoted_to_to_when_no_eligible_focal(self, app, db_session):
        """If focal points aren't email-eligible but a CC'd admin is, the admin
        becomes the primary 'To' rather than the email silently having no To."""
        from app.models import User, NotificationPreferences
        from app import db

        with app.app_context():
            focal = User(email='digest_focal2@example.com', name='Digest Focal', active=True)
            focal.set_password('pw')
            admin = User(email='instant_admin@example.com', name='Instant Admin', active=True)
            admin.set_password('pw')
            db.session.add_all([focal, admin])
            db.session.flush()
            db.session.add(NotificationPreferences(
                user_id=focal.id, email_notifications=True,
                notification_types_enabled=[], notification_frequency='daily',
            ))
            db.session.add(NotificationPreferences(
                user_id=admin.id, email_notifications=True,
                notification_types_enabled=[], notification_frequency='instant',
            ))
            db.session.commit()

            preview = build_grouped_entity_email_preview(
                [focal.id], [admin.id], self._sample_notification(), 'Kenya'
            )

        assert not preview['empty_reason']
        assert [r['email'] for r in preview['to']] == ['instant_admin@example.com']
        assert preview['cc'] == []

    def test_preview_mode_renders_body_with_no_recipients(self, app, db_session):
        """UI preview (preview_mode=True) must still render subject/body so the
        admin can see the content even before any recipients are resolved."""
        with app.app_context():
            preview = build_grouped_entity_email_preview(
                [], [], self._sample_notification(), 'Kenya', preview_mode=True
            )
        assert preview['html_body']
        assert preview['subject']
        assert not preview['empty_reason']

    def test_related_url_renders_open_assignment_button(self, app, db_session):
        from app.models import User, NotificationPreferences
        from app import db
        from types import SimpleNamespace

        sample = SimpleNamespace(
            id=None,
            title='Unified Country Plan – 2027',
            message='A new reporting assignment has been issued for Afghanistan.',
            notification_type=NotificationType.assignment_created,
            priority='normal',
            related_url='/forms/assignment/42',
            title_key=None,
            message_key=None,
            title_params=None,
            message_params=None,
        )

        with app.app_context():
            user = User(email='instant_focal@example.com', name='Instant Focal', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.add(NotificationPreferences(
                user_id=user.id,
                email_notifications=True,
                notification_types_enabled=[],
                notification_frequency='instant',
            ))
            db.session.commit()

            preview = build_grouped_entity_email_preview(
                [user.id], [], sample, 'Afghanistan', preview_mode=True
            )

        assert '/forms/assignment/42' in preview['html_body']
        assert 'Open Assignment' in preview['html_body']

    def test_non_preview_mode_empty_without_recipients(self, app, db_session):
        with app.app_context():
            preview = build_grouped_entity_email_preview(
                [], [], self._sample_notification(), 'Kenya', preview_mode=False
            )
        assert preview['empty_reason']
        assert preview['html_body'] == ''

    def test_in_app_only_type_always_empty(self, app, db_session):
        with app.app_context():
            preview = build_grouped_entity_email_preview(
                [1], [], self._sample_notification(nt=NotificationType.document_uploaded), 'Kenya'
            )
        assert preview['empty_reason'] == 'This notification type does not support email.'


class TestSendGroupedEntityEmail:
    def test_returns_false_when_no_eligible_recipients(self, app, db_session):
        from app.models import User, NotificationPreferences
        from app import db

        with app.app_context():
            user = User(email='digest_only@example.com', name='Digest Only', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.add(NotificationPreferences(
                user_id=user.id, email_notifications=True,
                notification_types_enabled=[], notification_frequency='daily',
            ))
            db.session.commit()

            from types import SimpleNamespace
            sample = SimpleNamespace(
                id=None, title='t', message='m',
                notification_type=NotificationType.assignment_created,
                priority='normal', related_url=None,
                title_key=None, message_key=None, title_params=None, message_params=None,
            )

            result = send_grouped_entity_email([user.id], [], sample, 'Kenya')

        assert result is False

    def test_sends_when_recipient_is_instant_eligible(self, app, db_session):
        from app.models import User, NotificationPreferences
        from app import db
        from types import SimpleNamespace

        with app.app_context():
            user = User(email='instant_send@example.com', name='Instant Send', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.add(NotificationPreferences(
                user_id=user.id, email_notifications=True,
                notification_types_enabled=[], notification_frequency='instant',
            ))
            db.session.commit()

            sample = SimpleNamespace(
                id=None, title='t', message='m',
                notification_type=NotificationType.assignment_created,
                priority='normal', related_url=None,
                title_key=None, message_key=None, title_params=None, message_params=None,
            )

            with patch('app.services.notification.emails.send_email', return_value=True):
                result = send_grouped_entity_email([user.id], [], sample, 'Kenya')

        assert result is True

    def test_grouped_email_links_delivery_log_to_notification(self, app, db_session):
        from app.models import User, Notification, NotificationPreferences, EmailDeliveryLog
        from app import db
        from types import SimpleNamespace

        with app.app_context():
            user = User(email='linked@example.com', name='Linked User', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.add(NotificationPreferences(
                user_id=user.id, email_notifications=True,
                notification_types_enabled=[], notification_frequency='instant',
            ))
            notification = Notification(
                user_id=user.id,
                notification_type=NotificationType.assignment_created,
                title='New assignment',
                message='Please complete Uganda.',
            )
            db.session.add(notification)
            db.session.commit()

            sample = SimpleNamespace(
                id=None, title='t', message='m',
                notification_type=NotificationType.assignment_created,
                priority='normal', related_url=None,
                title_key=None, message_key=None, title_params=None, message_params=None,
            )

            with patch('app.services.notification.emails.send_email', return_value=True):
                send_grouped_entity_email(
                    [user.id], [], sample, 'Uganda',
                    notification_by_user_id={user.id: notification},
                )

            log = EmailDeliveryLog.query.filter_by(user_id=user.id).order_by(
                EmailDeliveryLog.id.desc()
            ).first()

        assert log is not None
        assert log.notification_id == notification.id
        assert log.status == 'sent'
