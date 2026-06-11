"""Direct unit tests for app/routes/api/mobile/notifications.py."""
import json
import pytest
from unittest.mock import patch, MagicMock
from flask_login import login_user

from tests.factories import create_test_user

pytestmark = [pytest.mark.unit]


def _jwt_headers(app, user_id, sid=None):
    from app.utils.mobile_jwt import issue_token_pair
    with app.app_context():
        tokens = issue_token_pair(user_id, session_id=sid or f'notif-sid-{user_id}')
    return {'Authorization': f'Bearer {tokens["access_token"]}'}


def _unpack(resp):
    if isinstance(resp, tuple):
        return resp[0], resp[1]
    return resp, 200


def _mock_notification_service():
    """Return a MagicMock mirroring NotificationService for patching."""
    svc = MagicMock()
    svc.get_notifications.return_value = {'notifications': [], 'total': 0}
    svc.get_unread_count.return_value = 3
    svc.mark_all_as_read.return_value = None
    svc.mark_as_read.return_value = None
    svc.mark_as_unread.return_value = None

    prefs = MagicMock()
    prefs.email_notifications = True
    prefs.notification_frequency = 'immediate'
    prefs.sound_enabled = True
    prefs.push_notifications = True
    prefs.notification_types_enabled = []
    prefs.push_notification_types_enabled = []
    prefs.digest_day = None
    prefs.digest_time = None
    prefs.timezone = 'UTC'
    svc.get_notification_preferences.return_value = prefs
    svc.update_notification_preferences.return_value = None
    return svc


class TestListNotifications:
    def test_list_returns_paginated(self, app, db_session):
        from app.routes.api.mobile.notifications import list_notifications

        user = create_test_user(db_session, email='notif-user1@example.com')
        headers = _jwt_headers(app, user.id)

        with app.test_request_context(
            '/api/mobile/v1/notifications',
            method='GET',
            headers=headers,
        ):
            login_user(user)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.utils.rate_limiting.mobile_rate_limit', side_effect=lambda **kw: lambda f: f), \
                 patch('app.services.notification.service.NotificationService', _mock_notification_service()):
                resp = list_notifications()

        _, status = _unpack(resp)
        assert status == 200

    def test_list_with_unread_only_filter(self, app, db_session):
        from app.routes.api.mobile.notifications import list_notifications

        user = create_test_user(db_session, email='notif-user2@example.com')
        headers = _jwt_headers(app, user.id)

        with app.test_request_context(
            '/api/mobile/v1/notifications?unread_only=true',
            method='GET',
            headers=headers,
        ):
            login_user(user)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.utils.rate_limiting.mobile_rate_limit', side_effect=lambda **kw: lambda f: f), \
                 patch('app.services.notification.service.NotificationService', _mock_notification_service()):
                resp = list_notifications()

        _, status = _unpack(resp)
        assert status == 200

    def test_list_with_priority_filter_valid(self, app, db_session):
        from app.routes.api.mobile.notifications import list_notifications

        user = create_test_user(db_session, email='notif-user3@example.com')
        headers = _jwt_headers(app, user.id)

        with app.test_request_context(
            '/api/mobile/v1/notifications?priority=high',
            method='GET',
            headers=headers,
        ):
            login_user(user)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.utils.rate_limiting.mobile_rate_limit', side_effect=lambda **kw: lambda f: f), \
                 patch('app.services.notification.service.NotificationService', _mock_notification_service()):
                resp = list_notifications()

        _, status = _unpack(resp)
        assert status == 200

    def test_list_with_priority_filter_invalid_ignored(self, app, db_session):
        from app.routes.api.mobile.notifications import list_notifications

        user = create_test_user(db_session, email='notif-user4@example.com')
        headers = _jwt_headers(app, user.id)

        with app.test_request_context(
            '/api/mobile/v1/notifications?priority=INVALID',
            method='GET',
            headers=headers,
        ):
            login_user(user)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.utils.rate_limiting.mobile_rate_limit', side_effect=lambda **kw: lambda f: f), \
                 patch('app.services.notification.service.NotificationService', _mock_notification_service()):
                resp = list_notifications()

        _, status = _unpack(resp)
        assert status == 200

    def test_list_no_auth_returns_401(self, app):
        client = app.test_client()
        resp = client.get('/api/mobile/v1/notifications')
        assert resp.status_code == 401


class TestNotificationCount:
    def test_count_returns_unread_count(self, app, db_session):
        from app.routes.api.mobile.notifications import notification_count

        user = create_test_user(db_session, email='notif-user5@example.com')
        headers = _jwt_headers(app, user.id)

        with app.test_request_context(
            '/api/mobile/v1/notifications/count',
            method='GET',
            headers=headers,
        ):
            login_user(user)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.utils.rate_limiting.mobile_rate_limit', side_effect=lambda **kw: lambda f: f), \
                 patch('app.services.notification.service.NotificationService', _mock_notification_service()):
                resp = notification_count()

        body, status = _unpack(resp)
        assert status == 200
        assert body.get_json()['data']['unread_count'] == 3

    def test_count_no_auth_returns_401(self, app):
        client = app.test_client()
        resp = client.get('/api/mobile/v1/notifications/count')
        assert resp.status_code == 401


class TestMarkNotificationsRead:
    def test_mark_all_as_read(self, app, db_session):
        from app.routes.api.mobile.notifications import mark_notifications_read

        user = create_test_user(db_session, email='notif-user6@example.com')
        headers = _jwt_headers(app, user.id)

        with app.test_request_context(
            '/api/mobile/v1/notifications/mark-read',
            method='POST',
            data=json.dumps({'mark_all': True}),
            content_type='application/json',
            headers=headers,
        ):
            login_user(user)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.utils.rate_limiting.mobile_rate_limit', side_effect=lambda **kw: lambda f: f), \
                 patch('app.services.notification.service.NotificationService', _mock_notification_service()):
                resp = mark_notifications_read()

        _, status = _unpack(resp)
        assert status == 200

    def test_mark_specific_ids_as_read(self, app, db_session):
        from app.routes.api.mobile.notifications import mark_notifications_read

        user = create_test_user(db_session, email='notif-user7@example.com')
        headers = _jwt_headers(app, user.id)

        with app.test_request_context(
            '/api/mobile/v1/notifications/mark-read',
            method='POST',
            data=json.dumps({'notification_ids': [1, 2, 3]}),
            content_type='application/json',
            headers=headers,
        ):
            login_user(user)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.utils.rate_limiting.mobile_rate_limit', side_effect=lambda **kw: lambda f: f), \
                 patch('app.services.notification.service.NotificationService', _mock_notification_service()):
                resp = mark_notifications_read()

        _, status = _unpack(resp)
        assert status == 200

    def test_mark_read_no_ids_no_mark_all_returns_400(self, app, db_session):
        from app.routes.api.mobile.notifications import mark_notifications_read

        user = create_test_user(db_session, email='notif-user8@example.com')
        headers = _jwt_headers(app, user.id)

        with app.test_request_context(
            '/api/mobile/v1/notifications/mark-read',
            method='POST',
            data=json.dumps({}),
            content_type='application/json',
            headers=headers,
        ):
            login_user(user)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.utils.rate_limiting.mobile_rate_limit', side_effect=lambda **kw: lambda f: f), \
                 patch('app.services.notification.service.NotificationService', _mock_notification_service()):
                resp = mark_notifications_read()

        _, status = _unpack(resp)
        assert status == 400

    def test_mark_read_service_exception_returns_500(self, app, db_session):
        from app.routes.api.mobile.notifications import mark_notifications_read

        user = create_test_user(db_session, email='notif-user9@example.com')
        headers = _jwt_headers(app, user.id)

        svc = _mock_notification_service()
        svc.mark_all_as_read.side_effect = RuntimeError('db error')

        with app.test_request_context(
            '/api/mobile/v1/notifications/mark-read',
            method='POST',
            data=json.dumps({'mark_all': True}),
            content_type='application/json',
            headers=headers,
        ):
            login_user(user)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.utils.rate_limiting.mobile_rate_limit', side_effect=lambda **kw: lambda f: f), \
                 patch('app.services.notification.service.NotificationService', svc):
                resp = mark_notifications_read()

        _, status = _unpack(resp)
        assert status == 500

    def test_mark_read_no_auth_returns_401(self, app):
        client = app.test_client()
        resp = client.post('/api/mobile/v1/notifications/mark-read', json={'mark_all': True})
        assert resp.status_code == 401


class TestMarkNotificationsUnread:
    def test_mark_unread_success(self, app, db_session):
        from app.routes.api.mobile.notifications import mark_notifications_unread

        user = create_test_user(db_session, email='notif-user10@example.com')
        headers = _jwt_headers(app, user.id)

        with app.test_request_context(
            '/api/mobile/v1/notifications/mark-unread',
            method='POST',
            data=json.dumps({'notification_ids': [5, 6]}),
            content_type='application/json',
            headers=headers,
        ):
            login_user(user)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.utils.rate_limiting.mobile_rate_limit', side_effect=lambda **kw: lambda f: f), \
                 patch('app.services.notification.service.NotificationService', _mock_notification_service()):
                resp = mark_notifications_unread()

        _, status = _unpack(resp)
        assert status == 200

    def test_mark_unread_no_ids_returns_400(self, app, db_session):
        from app.routes.api.mobile.notifications import mark_notifications_unread

        user = create_test_user(db_session, email='notif-user11@example.com')
        headers = _jwt_headers(app, user.id)

        with app.test_request_context(
            '/api/mobile/v1/notifications/mark-unread',
            method='POST',
            data=json.dumps({'notification_ids': []}),
            content_type='application/json',
            headers=headers,
        ):
            login_user(user)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.utils.rate_limiting.mobile_rate_limit', side_effect=lambda **kw: lambda f: f), \
                 patch('app.services.notification.service.NotificationService', _mock_notification_service()):
                resp = mark_notifications_unread()

        _, status = _unpack(resp)
        assert status == 400

    def test_mark_unread_service_exception_returns_500(self, app, db_session):
        from app.routes.api.mobile.notifications import mark_notifications_unread

        user = create_test_user(db_session, email='notif-user12@example.com')
        headers = _jwt_headers(app, user.id)

        svc = _mock_notification_service()
        svc.mark_as_unread.side_effect = RuntimeError('db error')

        with app.test_request_context(
            '/api/mobile/v1/notifications/mark-unread',
            method='POST',
            data=json.dumps({'notification_ids': [1]}),
            content_type='application/json',
            headers=headers,
        ):
            login_user(user)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.utils.rate_limiting.mobile_rate_limit', side_effect=lambda **kw: lambda f: f), \
                 patch('app.services.notification.service.NotificationService', svc):
                resp = mark_notifications_unread()

        _, status = _unpack(resp)
        assert status == 500


class TestNotificationPreferences:
    def test_get_preferences_returns_ok(self, app, db_session):
        from app.routes.api.mobile.notifications import get_notification_preferences

        user = create_test_user(db_session, email='notif-user13@example.com')
        headers = _jwt_headers(app, user.id)

        with app.test_request_context(
            '/api/mobile/v1/notifications/preferences',
            method='GET',
            headers=headers,
        ):
            login_user(user)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.services.notification.service.NotificationService', _mock_notification_service()):
                resp = get_notification_preferences()

        body, status = _unpack(resp)
        assert status == 200
        data = body.get_json()['data']
        assert 'preferences' in data
        assert 'email_notifications' in data['preferences']

    def test_get_preferences_no_auth_returns_401(self, app):
        client = app.test_client()
        resp = client.get('/api/mobile/v1/notifications/preferences')
        assert resp.status_code == 401

    def test_update_preferences_success(self, app, db_session):
        from app.routes.api.mobile.notifications import update_notification_preferences

        user = create_test_user(db_session, email='notif-user14@example.com')
        headers = _jwt_headers(app, user.id)

        with app.test_request_context(
            '/api/mobile/v1/notifications/preferences',
            method='POST',
            data=json.dumps({'email_notifications': False, 'sound_enabled': False}),
            content_type='application/json',
            headers=headers,
        ):
            login_user(user)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.utils.rate_limiting.mobile_rate_limit', side_effect=lambda **kw: lambda f: f), \
                 patch('app.services.notification.service.NotificationService', _mock_notification_service()):
                resp = update_notification_preferences()

        _, status = _unpack(resp)
        assert status == 200

    def test_update_preferences_service_exception_returns_500(self, app, db_session):
        from app.routes.api.mobile.notifications import update_notification_preferences

        user = create_test_user(db_session, email='notif-user15@example.com')
        headers = _jwt_headers(app, user.id)

        svc = _mock_notification_service()
        svc.update_notification_preferences.side_effect = RuntimeError('boom')

        with app.test_request_context(
            '/api/mobile/v1/notifications/preferences',
            method='POST',
            data=json.dumps({'sound_enabled': True}),
            content_type='application/json',
            headers=headers,
        ):
            login_user(user)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.utils.rate_limiting.mobile_rate_limit', side_effect=lambda **kw: lambda f: f), \
                 patch('app.services.notification.service.NotificationService', svc):
                resp = update_notification_preferences()

        _, status = _unpack(resp)
        assert status == 500

    def test_update_preferences_no_auth_returns_401(self, app):
        client = app.test_client()
        resp = client.post(
            '/api/mobile/v1/notifications/preferences',
            json={'sound_enabled': True},
        )
        assert resp.status_code == 401
