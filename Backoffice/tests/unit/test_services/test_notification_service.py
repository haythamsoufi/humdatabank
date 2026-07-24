"""
Tests for app/services/notification/service.py

Targets 100% coverage of the NotificationService class.
"""
from datetime import timedelta
from unittest.mock import patch, MagicMock
import pytest

from app.services.notification.service import NotificationService, MESSAGE_PRIMARY_NOTIFICATION_TYPES, ACTOR_BADGE_ICON_BY_TYPE
from app.models.enums import NotificationType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_user_and_notification(db, email_suffix, nt=NotificationType.admin_message,
                                   is_read=False, is_archived=False, priority='normal'):
    """Create a user + notification in DB, return (user, notification)."""
    from app.models import User, Notification
    user = User(email=f'svc_{email_suffix}@test.com', name=f'SVC {email_suffix}', active=True)
    user.set_password('pw')
    db.session.add(user)
    db.session.flush()

    notif = Notification(
        user_id=user.id,
        notification_type=nt,
        title='Test Title',
        message='Test Message',
        is_read=is_read,
        is_archived=is_archived,
        priority=priority,
    )
    db.session.add(notif)
    db.session.commit()
    return user, notif


# ---------------------------------------------------------------------------
# _get_translated_notification_type_label
# ---------------------------------------------------------------------------

class TestGetTranslatedNotificationTypeLabel:
    def test_known_type_returns_string(self, app, db_session):
        with app.app_context():
            result = NotificationService._get_translated_notification_type_label('admin_message')
        assert isinstance(result, str)
        assert len(result) > 0

    def test_unknown_type_returns_formatted_value(self, app, db_session):
        with app.app_context():
            result = NotificationService._get_translated_notification_type_label('unknown_type')
        assert 'Unknown Type' in result

    def test_all_known_types_return_non_empty(self, app, db_session):
        with app.app_context():
            known_types = [
                'assignment_created', 'assignment_submitted', 'assignment_approved',
                'assignment_reopened', 'form_updated', 'document_uploaded',
                'user_added_to_country', 'self_report_created',
                'deadline_reminder', 'admin_message', 'access_request_received',
                'validation_questions', 'public_submission_received',
            ]
            for t in known_types:
                result = NotificationService._get_translated_notification_type_label(t)
                assert isinstance(result, str) and len(result) > 0

    def test_handles_translation_exception(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.service.NotificationService._get_translated_notification_type_label',
                       wraps=NotificationService._get_translated_notification_type_label):
                with patch('app.services.notification.service._', side_effect=lambda x: x):
                    result = NotificationService._get_translated_notification_type_label('admin_message')
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# get_unread_count / get_archived_count / get_all_count
# ---------------------------------------------------------------------------

class TestCountMethods:
    def test_get_unread_count_zero_initially(self, app, db_session):
        from app import db

        with app.app_context():
            from app.models import User
            user = User(email='count_zero@test.com', name='Count', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.commit()

            count = NotificationService.get_unread_count(user.id)
        assert count == 0

    def test_get_unread_count_with_unread(self, app, db_session):
        from app import db

        with app.app_context():
            user, notif = _create_user_and_notification(db, 'unread_count', is_read=False)
            count = NotificationService.get_unread_count(user.id)
        assert count >= 1

    def test_get_unread_count_excludes_read(self, app, db_session):
        from app import db

        with app.app_context():
            user, notif = _create_user_and_notification(db, 'read_count', is_read=True)
            count = NotificationService.get_unread_count(user.id)
        assert count == 0

    def test_get_unread_count_excludes_user_hidden_types(self, app, db_session):
        from app import db

        with app.app_context():
            user, notif = _create_user_and_notification(
                db, 'hidden_digest', nt=NotificationType.email_digest, is_read=False
            )
            count = NotificationService.get_unread_count(user.id)
        assert count == 0

    def test_get_all_count_excludes_user_hidden_types(self, app, db_session):
        from app import db

        with app.app_context():
            user, notif = _create_user_and_notification(
                db, 'hidden_all', nt=NotificationType.email_digest
            )
            count = NotificationService.get_all_count(user.id)
        assert count == 0

    def test_get_archived_count_excludes_user_hidden_types(self, app, db_session):
        from app import db

        with app.app_context():
            user, notif = _create_user_and_notification(
                db, 'hidden_archived',
                nt=NotificationType.email_digest,
                is_archived=True,
            )
            count = NotificationService.get_archived_count(user.id)
        assert count == 0

    def test_get_unread_count_error_returns_zero(self, app, db_session):
        with app.app_context():
            with patch.object(NotificationService, '_safe_notification_count', return_value=0):
                count = NotificationService.get_unread_count(1)
        assert count == 0

    def test_get_unread_count_error_rolls_back_session(self, app, db_session):
        from app import db
        mock_query = MagicMock()
        mock_query.count.side_effect = Exception('timeout')
        with app.app_context():
            with patch.object(db.session, 'rollback') as mock_rb:
                result = NotificationService._safe_notification_count(mock_query, 'test count')
        assert result == 0
        mock_rb.assert_called_once()

    def test_get_archived_count_with_archived(self, app, db_session):
        from app import db

        with app.app_context():
            user, notif = _create_user_and_notification(db, 'archived_count', is_archived=True)
            count = NotificationService.get_archived_count(user.id)
        assert count >= 1

    def test_get_archived_count_error_returns_zero(self, app, db_session):
        with app.app_context():
            with patch.object(NotificationService, '_safe_notification_count', return_value=0):
                count = NotificationService.get_archived_count(1)
        assert count == 0

    def test_get_all_count_returns_count(self, app, db_session):
        from app import db

        with app.app_context():
            user, notif = _create_user_and_notification(db, 'all_count')
            count = NotificationService.get_all_count(user.id)
        assert count >= 1

    def test_get_all_count_error_returns_zero(self, app, db_session):
        with app.app_context():
            with patch.object(NotificationService, '_safe_notification_count', return_value=0):
                count = NotificationService.get_all_count(1)
        assert count == 0


# ---------------------------------------------------------------------------
# mark_as_read / mark_as_unread
# ---------------------------------------------------------------------------

class TestMarkAsRead:
    def test_marks_notifications_as_read(self, app, db_session):
        from app import db

        with app.app_context():
            user, notif = _create_user_and_notification(db, 'mark_read', is_read=False)
            result = NotificationService.mark_as_read([notif.id], user.id)

        assert result is True

    def test_returns_true_for_empty_list(self, app, db_session):
        with app.app_context():
            result = NotificationService.mark_as_read([], 1)
        assert result is True

    def test_returns_true_for_nonexistent_ids(self, app, db_session):
        with app.app_context():
            result = NotificationService.mark_as_read([99999], 1)
        assert result is True

    def test_handles_partial_match(self, app, db_session):
        from app import db

        with app.app_context():
            user, notif = _create_user_and_notification(db, 'partial_match')
            result = NotificationService.mark_as_read([notif.id, 99999], user.id)

        assert result is True

    def test_returns_false_on_exception(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.service.Notification') as MockN:
                MockN.query.filter.side_effect = Exception('db fail')
                with patch('app.services.notification.service.db') as mock_db:
                    result = NotificationService.mark_as_read([1], 1)
        assert result is False


class TestMarkAsUnread:
    def test_marks_notifications_as_unread(self, app, db_session):
        from app import db

        with app.app_context():
            user, notif = _create_user_and_notification(db, 'mark_unread', is_read=True)
            result = NotificationService.mark_as_unread([notif.id], user.id)

        assert result is True

    def test_returns_true_for_empty_list(self, app, db_session):
        with app.app_context():
            result = NotificationService.mark_as_unread([], 1)
        assert result is True

    def test_returns_false_on_exception(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.service.Notification') as MockN:
                MockN.query.filter.side_effect = Exception('fail')
                with patch('app.services.notification.service.db') as mock_db:
                    result = NotificationService.mark_as_unread([1], 1)
        assert result is False


# ---------------------------------------------------------------------------
# mark_all_as_read
# ---------------------------------------------------------------------------

class TestMarkAllAsRead:
    def test_marks_all_unread_as_read(self, app, db_session):
        from app import db

        with app.app_context():
            user, notif = _create_user_and_notification(db, 'mark_all', is_read=False)
            result = NotificationService.mark_all_as_read(user.id)

        assert result is True

    def test_returns_false_on_exception(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.service.Notification') as MockN:
                MockN.query.filter.side_effect = Exception('fail')
                with patch('app.services.notification.service.db') as mock_db:
                    result = NotificationService.mark_all_as_read(1)
        assert result is False


# ---------------------------------------------------------------------------
# archive_notifications
# ---------------------------------------------------------------------------

class TestArchiveNotifications:
    def test_archives_notifications(self, app, db_session):
        from app import db

        with app.app_context():
            user, notif = _create_user_and_notification(db, 'archive')
            result = NotificationService.archive_notifications([notif.id], user.id)

        assert result is True

    def test_returns_true_for_empty_list(self, app, db_session):
        with app.app_context():
            result = NotificationService.archive_notifications([], 1)
        assert result is True

    def test_handles_partial_match(self, app, db_session):
        from app import db

        with app.app_context():
            user, notif = _create_user_and_notification(db, 'archive_partial')
            result = NotificationService.archive_notifications([notif.id, 99999], user.id)

        assert result is True

    def test_returns_false_on_exception(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.service.Notification') as MockN:
                MockN.query.filter.side_effect = Exception('fail')
                with patch('app.services.notification.service.db') as mock_db:
                    result = NotificationService.archive_notifications([1], 1)
        assert result is False


# ---------------------------------------------------------------------------
# delete_notifications
# ---------------------------------------------------------------------------

class TestDeleteNotifications:
    def test_deletes_notifications(self, app, db_session):
        from app import db

        with app.app_context():
            user, notif = _create_user_and_notification(db, 'delete')
            result = NotificationService.delete_notifications([notif.id], user.id)

        assert result is True

    def test_returns_true_for_nonexistent_ids(self, app, db_session):
        with app.app_context():
            result = NotificationService.delete_notifications([99999], 1)
        assert result is True

    def test_handles_partial_match_count_logging(self, app, db_session):
        from app import db

        with app.app_context():
            user, notif = _create_user_and_notification(db, 'delete_partial')
            result = NotificationService.delete_notifications([notif.id, 88888], user.id)

        assert result is True

    def test_returns_false_on_exception(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.service.Notification') as MockN:
                MockN.query.filter.side_effect = Exception('fail')
                with patch('app.services.notification.service.db') as mock_db:
                    result = NotificationService.delete_notifications([1], 1)
        assert result is False


# ---------------------------------------------------------------------------
# get_notification_preferences
# ---------------------------------------------------------------------------

class TestGetNotificationPreferences:
    def test_creates_default_when_not_found(self, app, db_session):
        from app.models import User
        from app import db

        with app.app_context():
            user = User(email='get_prefs@test.com', name='GetPrefs', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.commit()

            prefs = NotificationService.get_notification_preferences(user.id)

        assert prefs is not None
        assert prefs.email_notifications is True

    def test_returns_existing_preferences(self, app, db_session):
        from app.models import User, NotificationPreferences
        from app import db

        with app.app_context():
            user = User(email='existing_prefs@test.com', name='ExistPrefs', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            pref = NotificationPreferences(
                user_id=user.id,
                email_notifications=False,
                notification_types_enabled=['admin_message'],
                notification_frequency='daily',
                sound_enabled=True
            )
            db.session.add(pref)
            db.session.commit()

            prefs = NotificationService.get_notification_preferences(user.id)

        assert prefs.email_notifications is False
        assert 'admin_message' in prefs.notification_types_enabled


# ---------------------------------------------------------------------------
# update_notification_preferences
# ---------------------------------------------------------------------------

class TestUpdateNotificationPreferences:
    def test_updates_email_notifications(self, app, db_session):
        from app.models import User
        from app import db

        with app.app_context():
            user = User(email='update_prefs@test.com', name='UpdatePrefs', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.commit()

            result = NotificationService.update_notification_preferences(
                user.id, email_notifications=False
            )

        assert result is not None
        assert result.email_notifications is False

    def test_updates_sound_enabled(self, app, db_session):
        from app.models import User
        from app import db

        with app.app_context():
            user = User(email='update_sound@test.com', name='Sound', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.commit()

            result = NotificationService.update_notification_preferences(
                user.id, sound_enabled=False
            )

        assert result.sound_enabled is False

    def test_updates_notification_types_with_dict(self, app, db_session):
        from app.models import User
        from app import db

        with app.app_context():
            user = User(email='update_types@test.com', name='Types', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.commit()

            result = NotificationService.update_notification_preferences(
                user.id,
                notification_types_enabled={'admin_message': True, 'deadline_reminder': False}
            )

        assert 'admin_message' in result.notification_types_enabled
        assert 'deadline_reminder' not in result.notification_types_enabled

    def test_updates_notification_types_with_list(self, app, db_session):
        from app.models import User
        from app import db

        with app.app_context():
            user = User(email='update_types_list@test.com', name='TypesList', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.commit()

            result = NotificationService.update_notification_preferences(
                user.id,
                notification_types_enabled=['admin_message']
            )

        assert result.notification_types_enabled == ['admin_message']

    def test_updates_notification_types_with_invalid_type(self, app, db_session):
        from app.models import User
        from app import db

        with app.app_context():
            user = User(email='update_types_invalid@test.com', name='TypesInv', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.commit()

            result = NotificationService.update_notification_preferences(
                user.id,
                notification_types_enabled=42  # invalid type
            )

        assert result.notification_types_enabled == []

    def test_updates_notification_frequency(self, app, db_session):
        from app.models import User
        from app import db

        with app.app_context():
            user = User(email='update_freq@test.com', name='Freq', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.commit()

            result = NotificationService.update_notification_preferences(
                user.id, notification_frequency='daily'
            )

        assert result.notification_frequency == 'daily'

    def test_updates_push_notifications(self, app, db_session):
        from app.models import User
        from app import db

        with app.app_context():
            user = User(email='update_push@test.com', name='Push', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.commit()

            result = NotificationService.update_notification_preferences(
                user.id, push_notifications=False
            )

        assert result.push_notifications is False

    def test_updates_digest_day_and_time(self, app, db_session):
        from app.models import User
        from app import db

        with app.app_context():
            user = User(email='update_digest@test.com', name='Digest', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.commit()

            result = NotificationService.update_notification_preferences(
                user.id,
                notification_frequency='weekly',
                digest_day='monday',
                digest_time='09:00'
            )

        assert result is not None

    def test_returns_none_on_exception(self, app, db_session):
        with app.app_context():
            with patch.object(NotificationService, 'get_notification_preferences', side_effect=Exception('fail')):
                result = NotificationService.update_notification_preferences(1)
        assert result is None


# ---------------------------------------------------------------------------
# get_user_notifications
# ---------------------------------------------------------------------------

class TestGetUserNotifications:
    def test_returns_notifications_list_and_count(self, app, db_session):
        from app import db

        with app.app_context():
            user, notif = _create_user_and_notification(db, 'get_notifs')
            notifications, total = NotificationService.get_user_notifications(user.id)

        assert isinstance(notifications, list)
        assert isinstance(total, int)
        assert total >= 1

    def test_excludes_user_hidden_types(self, app, db_session):
        from app import db

        with app.app_context():
            user, notif = _create_user_and_notification(
                db, 'hidden_list', nt=NotificationType.email_digest
            )
            notifications, total = NotificationService.get_user_notifications(user.id)

        assert notifications == []
        assert total == 0

    def test_filters_unread_only(self, app, db_session):
        from app import db

        with app.app_context():
            user, unread_notif = _create_user_and_notification(db, 'unread_only_a', is_read=False)
            _, read_notif = _create_user_and_notification(db, 'unread_only_b', is_read=True)

            # Assign read notification to same user
            from app.models import Notification
            read_notif.user_id = user.id
            db.session.commit()

            notifications, total = NotificationService.get_user_notifications(
                user.id, unread_only=True
            )

        # All returned should be unread
        for n in notifications:
            assert n.get('is_read') is False

    def test_filters_by_notification_type(self, app, db_session):
        from app import db

        with app.app_context():
            user, notif = _create_user_and_notification(
                db, 'type_filter', nt=NotificationType.admin_message
            )
            notifications, total = NotificationService.get_user_notifications(
                user.id, notification_type='admin_message'
            )

        assert total >= 1

    def test_filters_by_priority(self, app, db_session):
        from app import db

        with app.app_context():
            user, notif = _create_user_and_notification(db, 'priority_filter', priority='high')
            notifications, total = NotificationService.get_user_notifications(
                user.id, priority='high'
            )

        assert total >= 1

    def test_archived_only_filter(self, app, db_session):
        from app import db

        with app.app_context():
            user, notif = _create_user_and_notification(db, 'archived_only', is_archived=True)
            notifications, total = NotificationService.get_user_notifications(
                user.id, archived_only=True
            )

        assert total >= 1

    def test_include_archived_filter(self, app, db_session):
        from app import db

        with app.app_context():
            user, notif = _create_user_and_notification(db, 'include_archived', is_archived=True)
            notifications, total = NotificationService.get_user_notifications(
                user.id, include_archived=True
            )

        assert total >= 1

    def test_pagination_limit_offset(self, app, db_session):
        from app import db
        from app.models import User, Notification

        with app.app_context():
            user = User(email='pagination@test.com', name='Paginate', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            for i in range(5):
                notif = Notification(
                    user_id=user.id,
                    notification_type=NotificationType.admin_message,
                    title=f'Notif {i}', message='m', is_read=False, is_archived=False
                )
                db.session.add(notif)
            db.session.commit()

            page1, total = NotificationService.get_user_notifications(
                user.id, limit=2, offset=0
            )
            page2, _ = NotificationService.get_user_notifications(
                user.id, limit=2, offset=2
            )

        assert len(page1) == 2
        assert len(page2) == 2
        assert total == 5

    def test_returns_empty_on_exception(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.service.Notification') as MockN:
                MockN.query.filter.side_effect = Exception('fail')
                notifications, total = NotificationService.get_user_notifications(1)
        assert notifications == []
        assert total == 0

    def test_date_from_filter(self, app, db_session):
        from app import db
        from app.utils.datetime_helpers import utcnow

        with app.app_context():
            user, notif = _create_user_and_notification(db, 'date_from')
            past_cutoff = utcnow() - timedelta(days=1)
            notifications, total = NotificationService.get_user_notifications(
                user.id, date_from=past_cutoff
            )

        assert total >= 1

    def test_date_to_filter(self, app, db_session):
        from app import db
        from app.utils.datetime_helpers import utcnow

        with app.app_context():
            user, notif = _create_user_and_notification(db, 'date_to')
            future_cutoff = utcnow() + timedelta(days=1)
            notifications, total = NotificationService.get_user_notifications(
                user.id, date_to=future_cutoff
            )

        assert total >= 1

    def test_category_filter(self, app, db_session):
        from app import db
        from app.models import User, Notification

        with app.app_context():
            user = User(email='category_filter@test.com', name='Category', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            notif = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='t', message='m', is_read=False, is_archived=False,
                category='assignment'
            )
            db.session.add(notif)
            db.session.commit()

            notifications, total = NotificationService.get_user_notifications(
                user.id, category='assignment'
            )

        assert total >= 1

    def test_notification_type_as_enum(self, app, db_session):
        from app import db

        with app.app_context():
            user, notif = _create_user_and_notification(
                db, 'type_enum', nt=NotificationType.deadline_reminder
            )
            notifications, total = NotificationService.get_user_notifications(
                user.id, notification_type=NotificationType.deadline_reminder
            )

        assert total >= 1


# ---------------------------------------------------------------------------
# get_notifications (page-based wrapper)
# ---------------------------------------------------------------------------

class TestGetNotifications:
    def test_returns_paginated_response(self, app, db_session):
        from app import db

        with app.app_context():
            user, notif = _create_user_and_notification(db, 'page_based')
            result = NotificationService.get_notifications(user_id=user.id, page=1, per_page=10)

        assert 'notifications' in result
        assert 'total' in result
        assert 'page' in result
        assert 'per_page' in result
        assert 'total_pages' in result

    def test_total_pages_calculated(self, app, db_session):
        from app import db
        from app.models import User, Notification

        with app.app_context():
            user = User(email='total_pages@test.com', name='TotalPages', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            for _ in range(5):
                db.session.add(Notification(
                    user_id=user.id,
                    notification_type=NotificationType.admin_message,
                    title='t', message='m', is_read=False, is_archived=False
                ))
            db.session.commit()

            result = NotificationService.get_notifications(user_id=user.id, page=1, per_page=2)

        assert result['total_pages'] == 3  # ceil(5/2)


# ---------------------------------------------------------------------------
# build_actor_display_fields_map
# ---------------------------------------------------------------------------

class TestBuildActorDisplayFieldsMap:
    def test_returns_empty_dict_for_empty_list(self, app, db_session):
        with app.app_context():
            result = NotificationService.build_actor_display_fields_map([], {})
        assert result == {}

    def test_returns_dict_with_notification_ids(self, app, db_session):
        from app import db
        from app.models import Notification

        with app.app_context():
            user, notif = _create_user_and_notification(db, 'actor_map')
            result = NotificationService.build_actor_display_fields_map([notif], {})

        assert notif.id in result
        assert 'actor' in result[notif.id]
        assert 'primary_is_message' in result[notif.id]

    def test_primary_is_message_for_assignment_submitted(self, app, db_session):
        from app import db

        with app.app_context():
            user, notif = _create_user_and_notification(
                db, 'primary_msg', nt=NotificationType.assignment_submitted
            )
            result = NotificationService.build_actor_display_fields_map([notif], {})

        assert result[notif.id]['primary_is_message'] is True

    def test_excludes_self_actor(self, app, db_session):
        """Actor should be None if actor_uid == recipient_uid."""
        from app import db
        from app.models import Notification

        with app.app_context():
            user, notif = _create_user_and_notification(
                db, 'self_actor', nt=NotificationType.assignment_submitted
            )
            # Set related_object_type/id to trigger assignment lookup
            notif.related_object_type = 'assignment'
            notif.related_object_id = 1
            db.session.commit()

            # Mock assignment status to return self as actor
            mock_aes = MagicMock()
            mock_aes.submitted_by_user_id = user.id
            mock_aes.approved_by_user_id = None

            result = NotificationService.build_actor_display_fields_map(
                [notif], {1: mock_aes}
            )

        assert result[notif.id]['actor'] is None


# ---------------------------------------------------------------------------
# _validate_action_buttons_for_serialization
# ---------------------------------------------------------------------------

class TestValidateActionButtonsForSerialization:
    def test_delegates_to_core_validator(self, app, db_session):
        with app.app_context():
            result = NotificationService._validate_action_buttons_for_serialization(None)
        assert result is None

    def test_valid_buttons_returned(self, app, db_session):
        with app.app_context():
            buttons = [{'action': 'approve', 'label': 'Approve'}]
            result = NotificationService._validate_action_buttons_for_serialization(buttons)
        assert result is not None


# ---------------------------------------------------------------------------
# _apply_localized_country_param
# ---------------------------------------------------------------------------

class TestApplyLocalizedCountryParam:
    def test_localizes_user_added_to_country_message(self, app, db_session):
        with app.app_context():
            notification = MagicMock()
            notification.id = 42
            notification.entity_type = 'country'
            notification.entity_id = 7
            country = MagicMock()
            country.name = 'Lebanon'
            message_params = {'country': 'Lebanon'}

            with patch('app.models.Country.query') as mock_query, \
                 patch('app.utils.form_localization.get_localized_country_name', return_value='لبنان') as mock_localize:
                mock_query.get.return_value = country
                result = NotificationService._apply_localized_country_param(
                    notification,
                    'notification.user_added_to_country.message',
                    message_params,
                    locale='ar',
                )

            assert result['country'] == 'لبنان'
            mock_localize.assert_called_once_with(country)

    def test_skips_non_country_message_keys(self, app, db_session):
        with app.app_context():
            notification = MagicMock(entity_type='country', entity_id=7)
            message_params = {'country': 'Lebanon'}
            result = NotificationService._apply_localized_country_param(
                notification,
                'notification.form_updated.message',
                message_params,
            )
            assert result == message_params


# ---------------------------------------------------------------------------
# _resolve_actor_user_id_for_notification
# ---------------------------------------------------------------------------

class TestResolveActorUserIdForNotification:
    def test_user_added_to_country_returns_none(self, app, db_session):
        with app.app_context():
            n = MagicMock()
            result = NotificationService._resolve_actor_user_id_for_notification(
                n, 'user_added_to_country', {}, {}
            )
        assert result is None

    def test_access_request_received_returns_car_user(self, app, db_session):
        with app.app_context():
            n = MagicMock()
            n.related_object_type = 'country_access_request'
            n.related_object_id = 5
            car_id_to_user_id = {5: 99}
            result = NotificationService._resolve_actor_user_id_for_notification(
                n, 'access_request_received', car_id_to_user_id, {}
            )
        assert result == 99

    def test_non_assignment_related_returns_none(self, app, db_session):
        with app.app_context():
            n = MagicMock()
            n.related_object_type = 'other'
            n.related_object_id = 1
            result = NotificationService._resolve_actor_user_id_for_notification(
                n, 'some_type', {}, {}
            )
        assert result is None

    def test_assignment_no_status_in_cache_returns_none(self, app, db_session):
        with app.app_context():
            n = MagicMock()
            n.related_object_type = 'assignment'
            n.related_object_id = 1
            result = NotificationService._resolve_actor_user_id_for_notification(
                n, 'assignment_submitted', {}, {}  # empty cache
            )
        assert result is None

    def test_assignment_submitted_returns_submitted_by(self, app, db_session):
        with app.app_context():
            n = MagicMock()
            n.related_object_type = 'assignment'
            n.related_object_id = 1
            mock_aes = MagicMock()
            mock_aes.submitted_by_user_id = 42
            result = NotificationService._resolve_actor_user_id_for_notification(
                n, 'assignment_submitted', {}, {1: mock_aes}
            )
        assert result == 42

    def test_assignment_approved_returns_approved_by(self, app, db_session):
        with app.app_context():
            n = MagicMock()
            n.related_object_type = 'assignment'
            n.related_object_id = 2
            mock_aes = MagicMock()
            mock_aes.approved_by_user_id = 77
            result = NotificationService._resolve_actor_user_id_for_notification(
                n, 'assignment_approved', {}, {2: mock_aes}
            )
        assert result == 77

    def test_other_assignment_type_returns_none(self, app, db_session):
        with app.app_context():
            n = MagicMock()
            n.related_object_type = 'assignment'
            n.related_object_id = 3
            mock_aes = MagicMock()
            result = NotificationService._resolve_actor_user_id_for_notification(
                n, 'assignment_created', {}, {3: mock_aes}
            )
        assert result is None


# ---------------------------------------------------------------------------
# _serialize_actor_user
# ---------------------------------------------------------------------------

class TestSerializeActorUser:
    def test_returns_dict_with_required_keys(self, app, db_session):
        from app.models import User
        from app import db

        with app.app_context():
            user = User(email='serialize_actor@test.com', name='Actor User', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.commit()

            result = NotificationService._serialize_actor_user(user)

        assert 'id' in result
        assert 'name' in result
        assert 'initials' in result
        assert 'profile_color' in result

    def test_uses_profile_color_when_set(self, app, db_session):
        from app.models import User
        from app import db

        with app.app_context():
            user = User(email='color_actor@test.com', name='Colored', active=True,
                       profile_color='#FF0000')
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.commit()

            result = NotificationService._serialize_actor_user(user)

        assert result['profile_color'] == '#FF0000'


# ---------------------------------------------------------------------------
# build_email_delivery_fields_map
# ---------------------------------------------------------------------------

class TestBuildEmailDeliveryFieldsMap:
    def test_empty_ids_returns_empty_map(self, app):
        with app.app_context():
            assert NotificationService.build_email_delivery_fields_map([]) == {}

    def test_latest_log_wins_on_retries(self, app, db_session):
        from app.models import User, Notification, NotificationType, EmailDeliveryLog
        from app import db
        from app.utils.datetime_helpers import utcnow
        from datetime import timedelta

        with app.app_context():
            user = User(email='email_map@test.com', name='Email Map', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            notification = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='Test',
                message='Body',
            )
            db.session.add(notification)
            db.session.flush()

            older = EmailDeliveryLog(
                notification_id=notification.id,
                user_id=user.id,
                email_address=user.email,
                subject='Old subject',
                status='failed',
                created_at=utcnow() - timedelta(minutes=5),
            )
            newer = EmailDeliveryLog(
                notification_id=notification.id,
                user_id=user.id,
                email_address=user.email,
                subject='New subject',
                status='sent',
                sent_at=utcnow(),
                created_at=utcnow(),
            )
            db.session.add_all([older, newer])
            db.session.commit()

            result = NotificationService.build_email_delivery_fields_map([notification.id])

        row = result[notification.id]
        assert row['has_email'] is True
        assert row['email_status'] == 'sent'
        assert row['email_subject'] == 'New subject'

    def test_missing_log_returns_empty_email_fields(self, app, db_session):
        from app.models import User, Notification, NotificationType
        from app import db

        with app.app_context():
            user = User(email='no_log@test.com', name='No Log', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            notification = Notification(
                user_id=user.id,
                notification_type=NotificationType.assignment_created,
                title='In-app only',
                message='No email',
            )
            db.session.add(notification)
            db.session.commit()

            result = NotificationService.build_email_delivery_fields_map([notification.id])

        row = result[notification.id]
        assert row['has_email'] is False
        assert row['email_status'] is None
        assert row['email_can_retry'] is False

    def test_retrying_status_displayed_as_failed(self, app, db_session):
        from app.models import User, Notification, NotificationType, EmailDeliveryLog
        from app import db

        with app.app_context():
            user = User(email='retrying_display@test.com', name='Retry Display', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            notification = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='Test',
                message='Body',
            )
            db.session.add(notification)
            db.session.flush()

            log = EmailDeliveryLog(
                notification_id=notification.id,
                user_id=user.id,
                email_address=user.email,
                subject='Subject',
                status='retrying',
            )
            db.session.add(log)
            db.session.commit()

            row = NotificationService.build_email_delivery_fields_map([notification.id])[notification.id]

        assert row['email_status'] == 'failed'
        assert row['email_can_retry'] is True

    def test_email_content_populated_when_notifications_passed(self, app, db_session):
        from app.models import User, Notification, NotificationType, EmailDeliveryLog
        from app import db

        with app.app_context():
            user = User(email='email_content@test.com', name='Email Content', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            notification = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='Alert title',
                message='<p>Hello <b>team</b></p>',
            )
            db.session.add(notification)
            db.session.flush()

            log = EmailDeliveryLog(
                notification_id=notification.id,
                user_id=user.id,
                email_address=user.email,
                subject='Alert title',
                status='sent',
            )
            db.session.add(log)
            db.session.commit()

            result = NotificationService.build_email_delivery_fields_map(
                [notification.id],
                notifications=[notification],
            )

        row = result[notification.id]
        assert row['has_email'] is True
        assert row['email_content'] == 'Hello team'

    def test_email_content_empty_without_email_log(self, app, db_session):
        from app.models import User, Notification, NotificationType
        from app import db

        with app.app_context():
            user = User(email='no_email_content@test.com', name='No Email', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            notification = Notification(
                user_id=user.id,
                notification_type=NotificationType.assignment_created,
                title='In-app',
                message='No email sent',
            )
            db.session.add(notification)
            db.session.commit()

            result = NotificationService.build_email_delivery_fields_map(
                [notification.id],
                notifications=[notification],
            )

        row = result[notification.id]
        assert row['has_email'] is False
        assert row['email_content'] == ''


class TestModuleConstants:
    def test_message_primary_notification_types_is_frozenset(self):
        assert isinstance(MESSAGE_PRIMARY_NOTIFICATION_TYPES, frozenset)
        assert 'assignment_submitted' in MESSAGE_PRIMARY_NOTIFICATION_TYPES

    def test_actor_badge_icon_by_type_is_dict(self):
        assert isinstance(ACTOR_BADGE_ICON_BY_TYPE, dict)
        assert 'assignment_submitted' in ACTOR_BADGE_ICON_BY_TYPE
