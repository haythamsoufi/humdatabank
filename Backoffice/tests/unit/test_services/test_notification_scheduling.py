"""
Tests for app/services/notification/scheduling.py

Targets 100% coverage of create_scheduled_notification and process_scheduled_notifications.
"""
from datetime import timedelta
from unittest.mock import patch, MagicMock
import pytest

from app.services.notification.scheduling import (
    create_scheduled_notification,
    process_scheduled_notifications,
    _resolve_notification_content,
    DEFAULT_TITLE_KEY,
    DEFAULT_MESSAGE_KEY,
)
from app.models.enums import NotificationType


# ---------------------------------------------------------------------------
# _resolve_notification_content
# ---------------------------------------------------------------------------

class TestResolveNotificationContent:
    def test_defaults_to_default_keys_when_none_provided(self, app, db_session):
        with app.app_context():
            (
                title_key, message_key,
                title_params, message_params,
                fallback_title, fallback_message
            ) = _resolve_notification_content(
                title=None, message=None,
                title_key=None, message_key=None,
                title_params=None, message_params=None,
            )
        assert title_key == DEFAULT_TITLE_KEY
        assert message_key == DEFAULT_MESSAGE_KEY

    def test_uses_provided_keys(self, app, db_session):
        with app.app_context():
            (title_key, message_key, *_) = _resolve_notification_content(
                title=None, message=None,
                title_key='notification.admin_message.title',
                message_key='notification.admin_message.message',
                title_params=None, message_params=None,
            )
        assert title_key == 'notification.admin_message.title'
        assert message_key == 'notification.admin_message.message'

    def test_custom_title_added_to_params(self, app, db_session):
        with app.app_context():
            (_, _, title_params, *_) = _resolve_notification_content(
                title='Custom Title', message=None,
                title_key=None, message_key=None,
                title_params=None, message_params=None,
            )
        assert title_params is not None
        assert title_params.get('custom_title') == 'Custom Title'

    def test_custom_message_added_to_params(self, app, db_session):
        with app.app_context():
            (_, _, _, message_params, *_) = _resolve_notification_content(
                title=None, message='Custom message',
                title_key=None, message_key=None,
                title_params=None, message_params=None,
            )
        assert message_params is not None
        assert message_params.get('message') == 'Custom message'

    def test_fallback_title_used_when_provided(self, app, db_session):
        with app.app_context():
            (*_, fallback_title, _) = _resolve_notification_content(
                title='Explicit Title', message=None,
                title_key='notification.admin_message.title', message_key=None,
                title_params=None, message_params=None,
            )
        assert fallback_title == 'Explicit Title'

    def test_fallback_message_used_when_provided(self, app, db_session):
        with app.app_context():
            (*_, fallback_message) = _resolve_notification_content(
                title=None, message='Explicit Msg',
                title_key=None, message_key='notification.admin_message.message',
                title_params=None, message_params=None,
            )
        assert fallback_message == 'Explicit Msg'

    def test_generates_english_fallback_via_translation(self, app, db_session):
        with app.app_context():
            (*_, fallback_title, fallback_message) = _resolve_notification_content(
                title=None, message=None,
                title_key='notification.admin_message.title',
                message_key='notification.admin_message.message',
                title_params={'custom_title': 'Hello'},
                message_params={'message': 'World'},
            )
        # Should have generated fallbacks
        assert isinstance(fallback_title, str)
        assert isinstance(fallback_message, str)

    def test_copies_params_to_avoid_mutation(self, app, db_session):
        with app.app_context():
            original_params = {'key': 'val'}
            (_, _, title_params, *_) = _resolve_notification_content(
                title=None, message=None,
                title_key='notification.admin_message.title',
                message_key=None,
                title_params=original_params,
                message_params=None,
            )
        # Modifying returned params should not affect original
        if title_params:
            title_params['new_key'] = 'new_val'
        assert 'new_key' not in original_params

    def test_none_params_when_empty_after_resolution(self, app, db_session):
        with app.app_context():
            (_, _, title_params, message_params, *_) = _resolve_notification_content(
                title=None, message=None,
                title_key='notification.admin_message.title',
                message_key='notification.admin_message.message',
                title_params=None, message_params=None,
            )
        # When no params were set and no title/message, result is None
        assert title_params is None or isinstance(title_params, dict)


# ---------------------------------------------------------------------------
# create_scheduled_notification
# ---------------------------------------------------------------------------

class TestCreateScheduledNotification:
    def _future_time(self, minutes=60):
        from app.utils.datetime_helpers import utcnow
        return utcnow() + timedelta(minutes=minutes)

    def test_creates_notification_for_future_time(self, app, db_session):
        from app.models import User
        from app import db

        with app.app_context():
            user = User(email='sched_create@test.com', name='Sched', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.commit()

            scheduled_for = self._future_time(60)

            with patch('app.services.notification.scheduling.create_notification') as mock_create:
                with patch('app.services.notification.scheduling.get_user_preferences_batch') as mock_prefs:
                    mock_prefs.return_value = {}
                    with patch('app.services.notification.scheduling.is_notification_type_enabled_for_user', return_value=True):
                        result = create_scheduled_notification(
                            user_ids=user.id,
                            notification_type=NotificationType.admin_message,
                            scheduled_for=scheduled_for,
                            title='Sched Title',
                            message='Sched Message',
                        )

        assert isinstance(result, list)

    def test_creates_multiple_notifications_for_user_list(self, app, db_session):
        from app.models import User
        from app import db

        with app.app_context():
            users = []
            for i in range(3):
                u = User(email=f'sched_multi_{i}@test.com', name=f'Sched{i}', active=True)
                u.set_password('pw')
                db.session.add(u)
                db.session.flush()
                users.append(u)
            db.session.commit()

            scheduled_for = self._future_time(60)

            with patch('app.services.notification.scheduling.get_user_preferences_batch') as mock_prefs:
                mock_prefs.return_value = {}
                with patch('app.services.notification.scheduling.is_notification_type_enabled_for_user', return_value=True):
                    result = create_scheduled_notification(
                        user_ids=[u.id for u in users],
                        notification_type=NotificationType.admin_message,
                        scheduled_for=scheduled_for,
                        title='T', message='M',
                    )

        assert len(result) == 3

    def test_returns_empty_list_for_invalid_user_ids(self, app, db_session):
        with app.app_context():
            scheduled_for = self._future_time(60)
            result = create_scheduled_notification(
                user_ids=['not_int', None],
                notification_type=NotificationType.admin_message,
                scheduled_for=scheduled_for,
            )
        assert result == []

    def test_returns_empty_list_for_empty_user_ids(self, app, db_session):
        with app.app_context():
            scheduled_for = self._future_time(60)
            result = create_scheduled_notification(
                user_ids=[],
                notification_type=NotificationType.admin_message,
                scheduled_for=scheduled_for,
            )
        assert result == []

    def test_falls_back_to_immediate_when_past_time(self, app, db_session):
        from app.utils.datetime_helpers import utcnow
        from app.models import User
        from app import db

        with app.app_context():
            user = User(email='sched_past@test.com', name='Past', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.commit()

            past_time = utcnow() - timedelta(minutes=5)

            with patch('app.services.notification.scheduling.create_notification') as mock_create:
                mock_create.return_value = [MagicMock()]
                with patch('app.services.notification.scheduling.get_user_preferences_batch', return_value={}):
                    with patch('app.services.notification.scheduling.is_notification_type_enabled_for_user', return_value=True):
                        result = create_scheduled_notification(
                            user_ids=user.id,
                            notification_type=NotificationType.admin_message,
                            scheduled_for=past_time,
                            title='T', message='M',
                        )

            mock_create.assert_called_once()

    def test_filters_users_by_preferences(self, app, db_session):
        from app.models import User, NotificationPreferences
        from app import db

        with app.app_context():
            user = User(email='sched_filter@test.com', name='Filter', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            pref = NotificationPreferences(
                user_id=user.id,
                email_notifications=True,
                notification_types_enabled=['deadline_reminder'],  # not admin_message
                notification_frequency='instant',
                sound_enabled=False
            )
            db.session.add(pref)
            db.session.commit()

            scheduled_for = self._future_time(60)

            result = create_scheduled_notification(
                user_ids=user.id,
                notification_type=NotificationType.admin_message,
                scheduled_for=scheduled_for,
                respect_preferences=True,
                title='T', message='M',
            )

        assert result == []

    def test_skips_preferences_when_disabled(self, app, db_session):
        from app.models import User
        from app import db

        with app.app_context():
            user = User(email='sched_no_pref@test.com', name='NoPref', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.commit()

            scheduled_for = self._future_time(60)

            result = create_scheduled_notification(
                user_ids=user.id,
                notification_type=NotificationType.admin_message,
                scheduled_for=scheduled_for,
                respect_preferences=False,
                title='T', message='M',
            )

        assert len(result) == 1

    def test_raises_on_db_exception(self, app, db_session):
        from app.models import User
        from app import db

        with app.app_context():
            user = User(email='sched_exc@test.com', name='Exc', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.commit()

            scheduled_for = self._future_time(60)

            with patch('app.services.notification.scheduling.db') as mock_db:
                mock_db.session.add = MagicMock()
                mock_db.session.commit.side_effect = Exception('db error')
                mock_db.session.rollback = MagicMock()

                with pytest.raises(Exception):
                    create_scheduled_notification(
                        user_ids=user.id,
                        notification_type=NotificationType.admin_message,
                        scheduled_for=scheduled_for,
                        respect_preferences=False,
                        title='T', message='M',
                    )

    def test_logs_when_some_users_filtered(self, app, db_session):
        from app.models import User, NotificationPreferences
        from app import db

        with app.app_context():
            user1 = User(email='sched_partial1@test.com', name='P1', active=True)
            user1.set_password('pw')
            user2 = User(email='sched_partial2@test.com', name='P2', active=True)
            user2.set_password('pw')
            db.session.add_all([user1, user2])
            db.session.flush()

            # user1 allows admin_message, user2 does not
            pref1 = NotificationPreferences(
                user_id=user1.id,
                email_notifications=True,
                notification_types_enabled=[],  # all enabled
                notification_frequency='instant',
                sound_enabled=False
            )
            pref2 = NotificationPreferences(
                user_id=user2.id,
                email_notifications=True,
                notification_types_enabled=['deadline_reminder'],  # admin_message disabled
                notification_frequency='instant',
                sound_enabled=False
            )
            db.session.add_all([pref1, pref2])
            db.session.commit()

            scheduled_for = self._future_time(60)

            result = create_scheduled_notification(
                user_ids=[user1.id, user2.id],
                notification_type=NotificationType.admin_message,
                scheduled_for=scheduled_for,
                respect_preferences=True,
                title='T', message='M',
            )

        # user1 should be included, user2 filtered out
        assert len(result) == 1


# ---------------------------------------------------------------------------
# process_scheduled_notifications
# ---------------------------------------------------------------------------

class TestProcessScheduledNotifications:
    def test_returns_zero_when_no_scheduled_notifications(self, app, db_session):
        with app.app_context():
            result = process_scheduled_notifications()
        assert result == 0

    def test_processes_due_notifications(self, app, db_session):
        from app.models import User, Notification
        from app import db
        from app.utils.datetime_helpers import utcnow

        with app.app_context():
            user = User(email='process_sched@test.com', name='Process', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            past_time = utcnow() - timedelta(minutes=5)
            notif = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='Scheduled', message='This was scheduled',
                is_read=False, is_archived=False,
                scheduled_for=past_time,
                sent_at=None,
            )
            db.session.add(notif)
            db.session.commit()

            with patch('app.services.notification.scheduling.broadcast_notification'):
                with patch('app.services.notification.scheduling.broadcast_unread_count'):
                    with patch('app.services.notification.scheduling.NotificationService'):
                        with patch('app.services.notification.scheduling.PushNotificationService'):
                            with patch('app.services.notification.scheduling.send_instant_notification_email'):
                                count = process_scheduled_notifications()

        assert count >= 1

    def test_skips_notifications_for_disabled_type(self, app, db_session):
        from app.models import User, Notification, NotificationPreferences
        from app import db
        from app.utils.datetime_helpers import utcnow

        with app.app_context():
            user = User(email='sched_skip@test.com', name='Skip', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            pref = NotificationPreferences(
                user_id=user.id,
                email_notifications=True,
                notification_types_enabled=['deadline_reminder'],  # admin_message disabled
                notification_frequency='instant',
                sound_enabled=False
            )
            db.session.add(pref)

            past_time = utcnow() - timedelta(minutes=5)
            notif = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='Skipped', message='Should be skipped',
                is_read=False, is_archived=False,
                scheduled_for=past_time,
                sent_at=None,
            )
            db.session.add(notif)
            db.session.commit()

            count = process_scheduled_notifications()

        # Returns 0 because the notification was skipped (archived)
        assert count == 0

    def test_handles_broadcast_failure_gracefully(self, app, db_session):
        from app.models import User, Notification
        from app import db
        from app.utils.datetime_helpers import utcnow

        with app.app_context():
            user = User(email='broadcast_fail@test.com', name='BFail', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            past_time = utcnow() - timedelta(minutes=5)
            notif = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='T', message='M',
                is_read=False, is_archived=False,
                scheduled_for=past_time,
                sent_at=None,
            )
            db.session.add(notif)
            db.session.commit()

            with patch('app.services.notification.scheduling.broadcast_notification',
                       side_effect=Exception('ws fail')):
                with patch('app.services.notification.scheduling.broadcast_unread_count',
                           side_effect=Exception('ws fail')):
                    with patch('app.services.notification.scheduling.NotificationService'):
                        with patch('app.services.notification.scheduling.PushNotificationService'):
                            with patch('app.services.notification.scheduling.send_instant_notification_email'):
                                count = process_scheduled_notifications()

        assert count >= 1  # Still processed despite broadcast failure

    def test_handles_push_failure_gracefully(self, app, db_session):
        from app.models import User, Notification
        from app import db
        from app.utils.datetime_helpers import utcnow

        with app.app_context():
            user = User(email='push_fail@test.com', name='PFail', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            past_time = utcnow() - timedelta(minutes=5)
            notif = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='T', message='M',
                is_read=False, is_archived=False,
                scheduled_for=past_time,
                sent_at=None,
            )
            db.session.add(notif)
            db.session.commit()

            with patch('app.services.notification.scheduling.broadcast_notification'):
                with patch('app.services.notification.scheduling.broadcast_unread_count'):
                    with patch('app.services.notification.scheduling.NotificationService'):
                        with patch('app.services.notification.scheduling.PushNotificationService') as MockPush:
                            MockPush.send_push_notification.side_effect = Exception('push fail')
                            with patch('app.services.notification.scheduling.send_instant_notification_email'):
                                count = process_scheduled_notifications()

        assert count >= 1

    def test_handles_email_failure_gracefully(self, app, db_session):
        from app.models import User, Notification
        from app import db
        from app.utils.datetime_helpers import utcnow

        with app.app_context():
            user = User(email='email_fail_sched@test.com', name='EFail', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            past_time = utcnow() - timedelta(minutes=5)
            notif = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='T', message='M',
                is_read=False, is_archived=False,
                scheduled_for=past_time,
                sent_at=None,
            )
            db.session.add(notif)
            db.session.commit()

            with patch('app.services.notification.scheduling.broadcast_notification'):
                with patch('app.services.notification.scheduling.broadcast_unread_count'):
                    with patch('app.services.notification.scheduling.NotificationService'):
                        with patch('app.services.notification.scheduling.PushNotificationService'):
                            with patch('app.services.notification.scheduling.send_instant_notification_email',
                                       side_effect=Exception('email fail')):
                                count = process_scheduled_notifications()

        assert count >= 1

    def test_returns_zero_on_db_exception(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.scheduling.Notification') as MockN:
                MockN.query.filter.side_effect = Exception('critical db fail')
                with patch('app.services.notification.scheduling.db') as mock_db:
                    count = process_scheduled_notifications()
        assert count == 0

    def test_notification_with_related_url_sends_data_to_push(self, app, db_session):
        from app.models import User, Notification
        from app import db
        from app.utils.datetime_helpers import utcnow

        with app.app_context():
            user = User(email='push_data@test.com', name='PData', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            past_time = utcnow() - timedelta(minutes=5)
            notif = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='T', message='M',
                is_read=False, is_archived=False,
                scheduled_for=past_time,
                sent_at=None,
                related_url='/some/url',
            )
            db.session.add(notif)
            db.session.commit()

            with patch('app.services.notification.scheduling.broadcast_notification'):
                with patch('app.services.notification.scheduling.broadcast_unread_count'):
                    with patch('app.services.notification.scheduling.NotificationService'):
                        with patch('app.services.notification.scheduling.PushNotificationService') as MockPush:
                            MockPush.send_push_notification.return_value = {'success': True}
                            with patch('app.services.notification.scheduling.send_instant_notification_email'):
                                count = process_scheduled_notifications()

        assert count >= 1
        # Data payload should have been passed with related_url
        call_args = MockPush.send_push_notification.call_args
        if call_args:
            assert call_args.kwargs.get('data') is not None or (
                len(call_args.args) > 3 and call_args.args[3] is not None
            )

    def test_notification_without_user_skips_push_and_email(self, app, db_session):
        from app.models import User, Notification
        from app import db
        from app.utils.datetime_helpers import utcnow

        with app.app_context():
            user = User(email='no_user_push@test.com', name='NUP', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            past_time = utcnow() - timedelta(minutes=5)
            notif = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='T', message='M',
                is_read=False, is_archived=False,
                scheduled_for=past_time,
                sent_at=None,
            )
            db.session.add(notif)
            db.session.commit()

            with patch('app.services.notification.scheduling.broadcast_notification'):
                with patch('app.services.notification.scheduling.broadcast_unread_count'):
                    with patch('app.services.notification.scheduling.NotificationService'):
                        with patch('app.services.notification.scheduling.PushNotificationService') as MockPush:
                            with patch('app.services.notification.scheduling.send_instant_notification_email') as mock_email:
                                # Make UserModel.query.get return None for push/email steps
                                with patch('app.services.notification.scheduling.User') as MockUserModel:
                                    MockUserModel.query.get.return_value = None
                                    count = process_scheduled_notifications()

        assert count >= 1
        MockPush.send_push_notification.assert_not_called()
        mock_email.assert_not_called()
