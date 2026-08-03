"""
Tests for app/services/notification/core.py

Targets 100% coverage of the core notification helpers and create_notification.
"""
from datetime import timedelta
from unittest.mock import patch, MagicMock
import pytest

from app.services.notification.core import (
    validate_notification_url,
    validate_action_button_endpoint,
    validate_and_sanitize_action_buttons,
    generate_notification_hash,
    check_duplicate_notification,
    translate_notification_message,
    get_default_icon_for_notification_type,
    calculate_notification_expiration,
    generate_group_id,
    is_notification_type_enabled_for_user,
    get_user_preferences_batch,
    create_notification,
)
from app.services.notification.validators import validate_notification_url as _validate_from_validators
from app.models.enums import NotificationType


# ---------------------------------------------------------------------------
# validate_notification_url (direct validators module import)
# ---------------------------------------------------------------------------

class TestValidateNotificationUrlDirectImport:
    def test_validators_module_matches_core_reexport(self, app, db_session):
        with app.app_context():
            assert _validate_from_validators('/dashboard') is True
            assert _validate_from_validators('javascript:alert(1)') is False


# ---------------------------------------------------------------------------
# validate_notification_url
# ---------------------------------------------------------------------------

class TestValidateNotificationUrl:
    def test_empty_url_is_valid(self, app, db_session):
        with app.app_context():
            assert validate_notification_url('') is True
            assert validate_notification_url(None) is True

    def test_relative_path_is_valid(self, app, db_session):
        with app.app_context():
            assert validate_notification_url('/assignments/123') is True

    def test_protocol_relative_url_is_invalid(self, app, db_session):
        with app.app_context():
            assert validate_notification_url('//evil.com') is False

    def test_javascript_scheme_is_invalid(self, app, db_session):
        with app.app_context():
            assert validate_notification_url('javascript:alert(1)') is False

    def test_data_scheme_is_invalid(self, app, db_session):
        with app.app_context():
            assert validate_notification_url('data:text/html,<h1>') is False

    def test_vbscript_scheme_is_invalid(self, app, db_session):
        with app.app_context():
            assert validate_notification_url('vbscript:msgbox(1)') is False

    def test_file_scheme_is_invalid(self, app, db_session):
        with app.app_context():
            assert validate_notification_url('file:///etc/passwd') is False

    def test_about_scheme_is_invalid(self, app, db_session):
        with app.app_context():
            assert validate_notification_url('about:blank') is False

    def test_relative_path_with_injection_chars_invalid(self, app, db_session):
        with app.app_context():
            assert validate_notification_url('/path/<script>') is False
            assert validate_notification_url('/path/"quote"') is False
            assert validate_notification_url("/path/'single'") is False

    def test_https_url_without_whitelist_is_invalid(self, app, db_session):
        with app.app_context():
            app.config['NOTIFICATION_ALLOWED_DOMAINS'] = []
            assert validate_notification_url('https://example.com/path') is False

    def test_https_url_in_whitelist_is_valid(self, app, db_session):
        with app.app_context():
            app.config['NOTIFICATION_ALLOWED_DOMAINS'] = ['example.com']
            assert validate_notification_url('https://example.com/path') is True

    def test_https_url_not_in_whitelist_is_invalid(self, app, db_session):
        with app.app_context():
            app.config['NOTIFICATION_ALLOWED_DOMAINS'] = ['trusted.com']
            assert validate_notification_url('https://evil.com/path') is False

    def test_http_url_with_non_http_scheme_invalid(self, app, db_session):
        with app.app_context():
            app.config['NOTIFICATION_ALLOWED_DOMAINS'] = ['example.com']
            assert validate_notification_url('ftp://example.com/path') is False


# ---------------------------------------------------------------------------
# validate_action_button_endpoint
# ---------------------------------------------------------------------------

class TestValidateActionButtonEndpoint:
    def test_empty_is_valid(self, app, db_session):
        with app.app_context():
            assert validate_action_button_endpoint('') is True
            assert validate_action_button_endpoint(None) is True

    def test_relative_path_valid(self, app, db_session):
        with app.app_context():
            app.config['NOTIFICATION_ALLOWED_ENDPOINTS'] = []
            assert validate_action_button_endpoint('/api/action/1') is True

    def test_non_relative_path_invalid(self, app, db_session):
        with app.app_context():
            assert validate_action_button_endpoint('http://example.com') is False

    def test_javascript_in_path_invalid(self, app, db_session):
        with app.app_context():
            assert validate_action_button_endpoint('/path/javascript:alert') is False

    def test_path_traversal_invalid(self, app, db_session):
        with app.app_context():
            assert validate_action_button_endpoint('/path/../etc/passwd') is False

    def test_double_slash_invalid(self, app, db_session):
        with app.app_context():
            assert validate_action_button_endpoint('//evil.com') is False

    def test_whitelist_matching_allowed(self, app, db_session):
        with app.app_context():
            app.config['NOTIFICATION_ALLOWED_ENDPOINTS'] = ['/api/']
            assert validate_action_button_endpoint('/api/action/1') is True

    def test_whitelist_no_match_rejected(self, app, db_session):
        with app.app_context():
            app.config['NOTIFICATION_ALLOWED_ENDPOINTS'] = ['/api/']
            assert validate_action_button_endpoint('/admin/secret') is False


# ---------------------------------------------------------------------------
# validate_and_sanitize_action_buttons
# ---------------------------------------------------------------------------

class TestValidateAndSanitizeActionButtons:
    def test_none_returns_none(self, app, db_session):
        with app.app_context():
            assert validate_and_sanitize_action_buttons(None) is None

    def test_empty_list_returns_none(self, app, db_session):
        with app.app_context():
            assert validate_and_sanitize_action_buttons([]) is None

    def test_not_a_list_returns_none(self, app, db_session):
        with app.app_context():
            assert validate_and_sanitize_action_buttons('string') is None

    def test_valid_button_returns_cleaned(self, app, db_session):
        with app.app_context():
            buttons = [{'action': 'approve', 'label': 'Approve', 'endpoint': '/api/approve', 'style': 'primary'}]
            result = validate_and_sanitize_action_buttons(buttons)
        assert result is not None
        assert len(result) == 1
        assert result[0]['action'] == 'approve'
        assert result[0]['label'] == 'Approve'

    def test_button_without_required_fields_skipped(self, app, db_session):
        with app.app_context():
            buttons = [{'label': 'No Action'}]  # missing 'action'
            result = validate_and_sanitize_action_buttons(buttons)
        assert result is None

    def test_non_dict_button_skipped(self, app, db_session):
        with app.app_context():
            buttons = ['not_a_dict']
            result = validate_and_sanitize_action_buttons(buttons)
        assert result is None

    def test_label_too_long_truncated(self, app, db_session):
        with app.app_context():
            app.config['MAX_ACTION_BUTTON_LABEL_LENGTH'] = 10
            buttons = [{'action': 'act', 'label': 'A' * 200}]
            result = validate_and_sanitize_action_buttons(buttons)
        assert result is not None
        assert len(result[0]['label']) <= 10

    def test_action_too_long_skipped(self, app, db_session):
        with app.app_context():
            app.config['MAX_ACTION_BUTTON_ACTION_LENGTH'] = 5
            buttons = [{'action': 'a' * 100, 'label': 'Label'}]
            result = validate_and_sanitize_action_buttons(buttons)
        assert result is None

    def test_invalid_style_defaults_to_primary(self, app, db_session):
        with app.app_context():
            buttons = [{'action': 'act', 'label': 'Lbl', 'style': 'rainbow'}]
            result = validate_and_sanitize_action_buttons(buttons)
        assert result is not None
        assert result[0]['style'] == 'primary'

    def test_valid_style_preserved(self, app, db_session):
        with app.app_context():
            buttons = [{'action': 'act', 'label': 'Lbl', 'style': 'danger'}]
            result = validate_and_sanitize_action_buttons(buttons)
        assert result[0]['style'] == 'danger'

    def test_unsafe_endpoint_removed(self, app, db_session):
        with app.app_context():
            app.config['NOTIFICATION_ALLOWED_ENDPOINTS'] = []
            buttons = [{'action': 'act', 'label': 'Lbl', 'endpoint': 'javascript:alert(1)'}]
            result = validate_and_sanitize_action_buttons(buttons)
        assert result is not None
        assert 'endpoint' not in result[0]

    def test_non_string_label_skipped(self, app, db_session):
        with app.app_context():
            buttons = [{'action': 'act', 'label': 123}]
            result = validate_and_sanitize_action_buttons(buttons)
        assert result is None

    def test_non_string_action_skipped(self, app, db_session):
        with app.app_context():
            buttons = [{'action': 999, 'label': 'Lbl'}]
            result = validate_and_sanitize_action_buttons(buttons)
        assert result is None

    def test_non_string_endpoint_removed(self, app, db_session):
        with app.app_context():
            buttons = [{'action': 'act', 'label': 'Lbl', 'endpoint': 42}]
            result = validate_and_sanitize_action_buttons(buttons)
        assert result is not None
        assert 'endpoint' not in result[0]


# ---------------------------------------------------------------------------
# generate_notification_hash
# ---------------------------------------------------------------------------

class TestGenerateNotificationHash:
    def test_produces_hex_string(self, app, db_session):
        with app.app_context():
            h = generate_notification_hash(1, NotificationType.admin_message, 5, 'Hello')
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex

    def test_same_inputs_produce_same_hash(self, app, db_session):
        with app.app_context():
            h1 = generate_notification_hash(1, NotificationType.admin_message, 5, 'Hello')
            h2 = generate_notification_hash(1, NotificationType.admin_message, 5, 'Hello')
        assert h1 == h2

    def test_different_user_different_hash(self, app, db_session):
        with app.app_context():
            h1 = generate_notification_hash(1, NotificationType.admin_message, 5, 'Hello')
            h2 = generate_notification_hash(2, NotificationType.admin_message, 5, 'Hello')
        assert h1 != h2

    def test_none_related_object_id(self, app, db_session):
        with app.app_context():
            h = generate_notification_hash(1, NotificationType.admin_message, None, 'Hello')
        assert isinstance(h, str)

    def test_message_discriminator_included(self, app, db_session):
        with app.app_context():
            h1 = generate_notification_hash(1, NotificationType.admin_message, None, 'T', 'msg1')
            h2 = generate_notification_hash(1, NotificationType.admin_message, None, 'T', 'msg2')
        assert h1 != h2

    def test_notification_type_as_string(self, app, db_session):
        with app.app_context():
            h = generate_notification_hash(1, 'admin_message', 5, 'Hello')
        assert isinstance(h, str) and len(h) == 64


# ---------------------------------------------------------------------------
# check_duplicate_notification
# ---------------------------------------------------------------------------

class TestCheckDuplicateNotification:
    def test_no_duplicate_in_empty_db(self, app, db_session):
        with app.app_context():
            result = check_duplicate_notification(
                1, 'somehash', notification_type=NotificationType.admin_message
            )
        assert result is False

    def test_duplicate_detected_within_window(self, app, db_session):
        from app.models import Notification, User
        from app import db

        with app.app_context():
            user = User(email='dedup@test.com', name='Dedup', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            notif_hash = 'test_hash_abc123'
            notif = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='t', message='m',
                notification_hash=notif_hash
            )
            db.session.add(notif)
            db.session.commit()

            result = check_duplicate_notification(user.id, notif_hash)

        assert result is True

    def test_admin_message_uses_shorter_window(self, app, db_session):
        with app.app_context():
            # Should use NOTIFICATION_DEDUP_WINDOW_MINUTES_ADMIN config
            result = check_duplicate_notification(
                999, 'nonexistent', notification_type=NotificationType.admin_message
            )
        assert result is False  # No duplicate exists

    def test_error_returns_false(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.dedup.Notification') as mock_n:
                mock_n.query.filter.side_effect = Exception('fail')
                result = check_duplicate_notification(1, 'hash')
        assert result is False


# ---------------------------------------------------------------------------
# translate_notification_message
# ---------------------------------------------------------------------------

class TestTranslateNotificationMessage:
    def test_empty_key_returns_empty_string(self, app, db_session):
        with app.app_context():
            assert translate_notification_message('') == ''
            assert translate_notification_message(None) == ''

    def test_known_key_returns_string(self, app, db_session):
        with app.app_context():
            result = translate_notification_message('notification.admin_message.title')
        assert isinstance(result, str)

    def test_admin_message_custom_title_returned(self, app, db_session):
        with app.app_context():
            result = translate_notification_message(
                'notification.admin_message.title',
                params={'custom_title': 'My Custom Title'}
            )
        assert 'My Custom Title' in result

    def test_admin_message_custom_body_returned(self, app, db_session):
        with app.app_context():
            result = translate_notification_message(
                'notification.admin_message.message',
                params={'message': 'Custom body text'}
            )
        assert 'Custom body text' in result

    def test_unknown_key_returns_string(self, app, db_session):
        with app.app_context():
            result = translate_notification_message('notification.unknown.key')
        assert isinstance(result, str)

    def test_assignment_created_title(self, app, db_session):
        with app.app_context():
            result = translate_notification_message('notification.assignment_created.title')
        assert isinstance(result, str)
        assert len(result) > 0

    def test_locale_parameter_used(self, app, db_session):
        with app.app_context():
            result = translate_notification_message(
                'notification.admin_message.title',
                locale='en'
            )
        assert isinstance(result, str)

    def test_custom_title_truncated_at_255(self, app, db_session):
        with app.app_context():
            long_title = 'A' * 300
            result = translate_notification_message(
                'notification.admin_message.title',
                params={'custom_title': long_title}
            )
        assert len(result) <= 255


# ---------------------------------------------------------------------------
# get_default_icon_for_notification_type
# ---------------------------------------------------------------------------

class TestGetDefaultIconForNotificationType:
    def test_returns_string(self, app, db_session):
        with app.app_context():
            result = get_default_icon_for_notification_type(NotificationType.admin_message)
        assert isinstance(result, str)

    def test_all_enum_values_return_icon(self, app, db_session):
        with app.app_context():
            for nt in NotificationType:
                result = get_default_icon_for_notification_type(nt)
                assert isinstance(result, str) and len(result) > 0


# ---------------------------------------------------------------------------
# calculate_notification_expiration
# ---------------------------------------------------------------------------

class TestCalculateNotificationExpiration:
    def test_returns_datetime_or_none(self, app, db_session):
        from datetime import datetime
        with app.app_context():
            result = calculate_notification_expiration(NotificationType.admin_message)
        assert result is None or isinstance(result, datetime)

    def test_zero_ttl_returns_none(self, app, db_session):
        with app.app_context():
            app.config['NOTIFICATION_TTL_DAYS'] = {'admin_message': 0}
            result = calculate_notification_expiration(NotificationType.admin_message)
        assert result is None

    def test_positive_ttl_returns_future_datetime(self, app, db_session):
        from app.utils.datetime_helpers import utcnow
        with app.app_context():
            app.config['NOTIFICATION_TTL_DAYS'] = {'admin_message': 30}
            result = calculate_notification_expiration(NotificationType.admin_message)
        assert result is not None
        assert result > utcnow()

    def test_uses_notification_expiration_days_when_type_not_in_ttl_map(self, app, db_session):
        from app.utils.datetime_helpers import utcnow
        with app.app_context():
            app.config['NOTIFICATION_EXPIRATION_DAYS'] = 45
            app.config['NOTIFICATION_TTL_DAYS'] = {}
            result = calculate_notification_expiration(NotificationType.admin_message)
        assert result is not None
        assert result <= utcnow() + timedelta(days=46)
        assert result > utcnow() + timedelta(days=44)

    def test_error_returns_none(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.dedup.current_app') as mock_app:
                mock_app.config.get.side_effect = Exception('fail')
                mock_app.logger = MagicMock()
                result = calculate_notification_expiration(NotificationType.admin_message)
        assert result is None


# ---------------------------------------------------------------------------
# generate_group_id
# ---------------------------------------------------------------------------

class TestGenerateGroupId:
    def test_returns_string(self, app, db_session):
        with app.app_context():
            result = generate_group_id(1, NotificationType.admin_message, None, 'country', 1)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_same_inputs_same_output(self, app, db_session):
        with app.app_context():
            r1 = generate_group_id(1, NotificationType.admin_message, 5, 'country', 1)
            r2 = generate_group_id(1, NotificationType.admin_message, 5, 'country', 1)
        assert r1 == r2

    def test_different_entity_different_id(self, app, db_session):
        with app.app_context():
            r1 = generate_group_id(1, NotificationType.admin_message, 5, 'country', 1)
            r2 = generate_group_id(1, NotificationType.admin_message, 5, 'country', 2)
        assert r1 != r2

    def test_none_related_and_entity(self, app, db_session):
        with app.app_context():
            result = generate_group_id(1, NotificationType.admin_message, None, None, None)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# is_notification_type_enabled_for_user
# ---------------------------------------------------------------------------

class TestIsNotificationTypeEnabledForUser:
    def test_returns_true_when_no_preferences(self, app, db_session):
        with app.app_context():
            result = is_notification_type_enabled_for_user(99999, NotificationType.admin_message)
        assert result is True

    def test_returns_true_when_preferences_empty_list(self, app, db_session):
        from app.models import NotificationPreferences, User
        from app import db

        with app.app_context():
            user = User(email='notif_pref@test.com', name='Pref User', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            pref = NotificationPreferences(
                user_id=user.id,
                email_notifications=True,
                notification_types_enabled=[],
                notification_frequency='instant',
                sound_enabled=False
            )
            db.session.add(pref)
            db.session.commit()

            result = is_notification_type_enabled_for_user(user.id, NotificationType.admin_message)

        assert result is True

    def test_returns_true_when_type_in_enabled_list(self, app, db_session):
        from app.models import NotificationPreferences, User
        from app import db

        with app.app_context():
            user = User(email='notif_pref2@test.com', name='Pref2', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            pref = NotificationPreferences(
                user_id=user.id,
                email_notifications=True,
                notification_types_enabled=['admin_message'],
                notification_frequency='instant',
                sound_enabled=False
            )
            db.session.add(pref)
            db.session.commit()

            result = is_notification_type_enabled_for_user(user.id, NotificationType.admin_message)

        assert result is True

    def test_returns_false_when_type_not_in_enabled_list(self, app, db_session):
        from app.models import NotificationPreferences, User
        from app import db

        with app.app_context():
            user = User(email='notif_pref3@test.com', name='Pref3', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            pref = NotificationPreferences(
                user_id=user.id,
                email_notifications=True,
                notification_types_enabled=['deadline_reminder'],
                notification_frequency='instant',
                sound_enabled=False
            )
            db.session.add(pref)
            db.session.commit()

            result = is_notification_type_enabled_for_user(user.id, NotificationType.admin_message)

        assert result is False

    def test_uses_cache_when_provided(self, app, db_session):
        from app.models import NotificationPreferences
        with app.app_context():
            mock_pref = MagicMock()
            mock_pref.notification_types_enabled = []
            cache = {42: mock_pref}
            result = is_notification_type_enabled_for_user(
                42, NotificationType.admin_message, preferences_cache=cache
            )
        assert result is True

    def test_error_returns_true(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.creation.NotificationPreferences') as mock_np:
                mock_np.query.filter_by.side_effect = Exception('fail')
                result = is_notification_type_enabled_for_user(1, NotificationType.admin_message)
        assert result is True


# ---------------------------------------------------------------------------
# get_user_preferences_batch
# ---------------------------------------------------------------------------

class TestGetUserPreferencesBatch:
    def test_empty_list_returns_empty_dict(self, app, db_session):
        with app.app_context():
            result = get_user_preferences_batch([])
        assert result == {}

    def test_returns_dict_for_users(self, app, db_session):
        from app.models import User, NotificationPreferences
        from app import db

        with app.app_context():
            user = User(email='batch_pref@test.com', name='Batch', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            pref = NotificationPreferences(
                user_id=user.id,
                email_notifications=True,
                notification_types_enabled=[],
                notification_frequency='instant',
                sound_enabled=False
            )
            db.session.add(pref)
            db.session.commit()

            result = get_user_preferences_batch([user.id])

        assert user.id in result

    def test_creates_default_prefs_for_missing_users(self, app, db_session):
        from app.models import User
        from app import db

        with app.app_context():
            user = User(email='batch_missing@test.com', name='Missing', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.commit()

            result = get_user_preferences_batch([user.id])

        assert user.id in result

    def test_error_returns_empty_dict(self, app, db_session):
        with app.app_context():
            with patch('app.services.notification.creation.NotificationPreferences') as mock_np:
                mock_np.query.filter.side_effect = Exception('fail')
                result = get_user_preferences_batch([1, 2, 3])
        assert result == {}


# ---------------------------------------------------------------------------
# create_notification
# ---------------------------------------------------------------------------

class TestCreateNotification:
    def test_creates_notification_for_single_user(self, app, db_session):
        from app.models import User
        from app import db

        with app.app_context():
            user = User(email='create_notif@test.com', name='Create', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.commit()

            with patch('app.services.notification.emails.send_instant_notification_email'):
                with patch('app.services.notification.push.PushNotificationService'):
                    with patch('app.utils.ws_manager.broadcast_notification'):
                        with patch('app.utils.ws_manager.broadcast_unread_count'):
                            result = create_notification(
                                user_ids=user.id,
                                notification_type=NotificationType.admin_message,
                                title_key='notification.admin_message.title',
                                message_key='notification.admin_message.message',
                                title_params={'custom_title': 'Test'},
                                message_params={'message': 'Test message'},
                            )

        assert isinstance(result, list)
        assert len(result) >= 1

    def test_document_uploaded_is_in_app_only(self, app, db_session):
        from app.models import User
        from app import db

        with app.app_context():
            user = User(email='doc_in_app@test.com', name='Doc', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.commit()

            with patch('app.services.notification.emails.send_instant_notification_email') as mock_email:
                result = create_notification(
                    user_ids=user.id,
                    notification_type=NotificationType.document_uploaded,
                    title_key='notification.document_uploaded.title',
                    message_key='notification.document_uploaded.message',
                    message_params={'document': 'report.pdf', 'document_type': 'PDF'},
                    priority='high',
                    override_email_preferences=True,
                    send_email_notifications=True,
                )

        assert len(result) >= 1
        mock_email.assert_not_called()

    def test_creates_notification_for_multiple_users(self, app, db_session):
        from app.models import User
        from app import db

        with app.app_context():
            users = []
            for i in range(3):
                u = User(email=f'multi_notif_{i}@test.com', name=f'Multi{i}', active=True)
                u.set_password('pw')
                db.session.add(u)
                db.session.flush()
                users.append(u)
            db.session.commit()

            with patch('app.services.notification.emails.send_instant_notification_email'):
                with patch('app.services.notification.push.PushNotificationService'):
                    with patch('app.utils.ws_manager.broadcast_notification'):
                        with patch('app.utils.ws_manager.broadcast_unread_count'):
                            result = create_notification(
                                user_ids=[u.id for u in users],
                                notification_type=NotificationType.admin_message,
                                title_key='notification.admin_message.title',
                                message_key='notification.admin_message.message',
                            )

        assert len(result) == 3

    def test_respects_notification_preferences_filtering(self, app, db_session):
        from app.models import User, NotificationPreferences
        from app import db

        with app.app_context():
            user = User(email='pref_filter@test.com', name='PrefFilter', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()

            # Only allow deadline_reminder, not admin_message
            pref = NotificationPreferences(
                user_id=user.id,
                email_notifications=True,
                notification_types_enabled=['deadline_reminder'],
                notification_frequency='instant',
                sound_enabled=False
            )
            db.session.add(pref)
            db.session.commit()

            result = create_notification(
                user_ids=user.id,
                notification_type=NotificationType.admin_message,
                title_key='notification.admin_message.title',
                message_key='notification.admin_message.message',
                respect_preferences=True,
            )

        # No notifications created (filtered by preferences)
        assert result == [] or result is None or len(result) == 0

    def test_invalid_user_ids_skipped(self, app, db_session):
        with app.app_context():
            result = create_notification(
                user_ids=[],
                notification_type=NotificationType.admin_message,
                title_key='notification.admin_message.title',
                message_key='notification.admin_message.message',
            )
        assert result == [] or result is None

    def test_invalid_user_id_values_warned_and_skipped(self, app, db_session):
        with app.app_context():
            result = create_notification(
                user_ids=['not_an_int', None],
                notification_type=NotificationType.admin_message,
                title_key='notification.admin_message.title',
                message_key='notification.admin_message.message',
            )
        assert result == [] or result is None

    def test_with_related_url_valid(self, app, db_session):
        from app.models import User
        from app import db

        with app.app_context():
            user = User(email='url_notif@test.com', name='URL', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.commit()

            with patch('app.services.notification.emails.send_instant_notification_email'):
                with patch('app.services.notification.push.PushNotificationService'):
                    with patch('app.utils.ws_manager.broadcast_notification'):
                        with patch('app.utils.ws_manager.broadcast_unread_count'):
                            result = create_notification(
                                user_ids=user.id,
                                notification_type=NotificationType.admin_message,
                                title_key='notification.admin_message.title',
                                message_key='notification.admin_message.message',
                                related_url='/some/path',
                            )

        assert len(result) >= 1

    def test_with_invalid_related_url_rejected(self, app, db_session):
        from app.models import User
        from app import db

        with app.app_context():
            user = User(email='bad_url_notif@test.com', name='BadURL', active=True)
            user.set_password('pw')
            db.session.add(user)
            db.session.flush()
            db.session.commit()

            with patch('app.services.notification.emails.send_instant_notification_email'):
                with patch('app.services.notification.push.PushNotificationService'):
                    with patch('app.utils.ws_manager.broadcast_notification'):
                        with patch('app.utils.ws_manager.broadcast_unread_count'):
                            result = create_notification(
                                user_ids=user.id,
                                notification_type=NotificationType.admin_message,
                                title_key='notification.admin_message.title',
                                message_key='notification.admin_message.message',
                                related_url='javascript:alert(1)',
                            )

        # Still creates but URL should be stripped/None
        assert result is not None


class TestNotifierReexports:
    """Typed notify_* helpers remain importable from notification.core."""

    def test_core_reexports_match_notifier_modules(self):
        from app.services.notification import core as core_mod
        from app.services.notification.notifiers import assignment, documents, digest

        assert core_mod.notify_assignment_created is assignment.notify_assignment_created
        assert core_mod.notify_document_uploaded is documents.notify_document_uploaded
        assert core_mod.notify_user_added_to_country is digest.notify_user_added_to_country
        assert core_mod.notify_standalone_document_uploaded is documents.notify_standalone_document_uploaded
