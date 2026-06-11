"""Direct unit/integration tests for app.routes.api.mobile.auth view functions."""
import json
from unittest.mock import MagicMock, patch

import pytest
from flask_login import login_user

from tests.factories import create_test_user

pytestmark = [pytest.mark.unit, pytest.mark.auth_security]


@pytest.mark.unit
class TestIssueTokensDirect:
    def test_issue_tokens_success(self, app, db_session):
        from app.routes.api.mobile.auth import issue_tokens

        with app.app_context():
            create_test_user(db_session, email='direct-mobile@example.com', password='MobilePass123!')
        with app.test_request_context(
            '/api/mobile/v1/auth/token',
            method='POST',
            data=json.dumps({'email': 'direct-mobile@example.com', 'password': 'MobilePass123!'}),
            content_type='application/json',
        ):
            with patch('app.services.user_analytics_service.log_login_attempt'), \
                 patch('app.services.user_analytics_service.start_user_session'), \
                 patch('app.services.user_analytics_service.log_user_activity'):
                resp = issue_tokens()
        if isinstance(resp, tuple):
            body, status = resp
        else:
            body, status = resp, resp.status_code
        assert status == 200
        data = body.get_json()['data']
        assert 'access_token' in data
        assert 'refresh_token' in data

    def test_issue_tokens_missing_credentials(self, app):
        from app.routes.api.mobile.auth import issue_tokens

        with app.test_request_context(
            '/api/mobile/v1/auth/token',
            method='POST',
            data=json.dumps({}),
            content_type='application/json',
        ):
            resp = issue_tokens()
        if isinstance(resp, tuple):
            _, status = resp
        else:
            status = resp.status_code
        assert status == 400


@pytest.mark.unit
class TestRefreshTokenDirect:
    def test_refresh_invalid_token(self, app):
        from app.routes.api.mobile.auth import refresh_token

        with app.test_request_context(
            '/api/mobile/v1/auth/refresh',
            method='POST',
            data=json.dumps({'refresh_token': 'not-a-valid-token'}),
            content_type='application/json',
        ):
            resp = refresh_token()
        if isinstance(resp, tuple):
            _, status = resp
        else:
            status = resp.status_code
        assert status == 401


@pytest.mark.unit
class TestExchangeSessionDirect:
    def test_exchange_session_issues_tokens(self, app, db_session):
        from app.routes.api.mobile.auth import exchange_session_for_tokens

        with app.app_context():
            user = create_test_user(db_session, email='exchange@example.com', password='Pass123!')
        with app.test_request_context(
            '/api/mobile/v1/auth/exchange-session',
            method='POST',
        ):
            login_user(user)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.services.user_analytics_service.log_user_activity'), \
                 patch('app.services.user_analytics_service.start_user_session'):
                resp = exchange_session_for_tokens()
        if isinstance(resp, tuple):
            body, status = resp
        else:
            body, status = resp, resp.status_code
        assert status == 200
        assert 'access_token' in body.get_json()['data']


@pytest.mark.unit
class TestMobileLogoutDirect:
    def test_mobile_logout_without_auth(self, app):
        from app.routes.api.mobile.auth import mobile_logout

        with app.test_request_context('/api/mobile/v1/auth/logout', method='POST'):
            resp = mobile_logout()
        if isinstance(resp, tuple):
            body, status = resp
        else:
            body, status = resp, resp.status_code
        assert status == 200
        assert body.get_json()['success'] is True

    def _client_info(self):
        return {
            'ip_address': '127.0.0.1',
            'user_agent': 'pytest',
            'browser': 'pytest',
            'operating_system': 'Windows',
            'device_type': 'desktop',
        }

    def test_mobile_logout_jwt_loads_user_without_session(self, app, db_session):
        from app.routes.api.mobile.auth import mobile_logout
        from app.utils.mobile_jwt import issue_token_pair

        with app.app_context():
            user = create_test_user(db_session, email='jwt-logout@example.com', password='Pass123!')
            sid = 'jwt-logout-direct-sid'
            tokens = issue_token_pair(user.id, session_id=sid)
        with app.test_request_context(
            '/api/mobile/v1/auth/logout',
            method='POST',
            headers={'Authorization': f'Bearer {tokens["access_token"]}'},
        ):
            with patch('app.services.user_analytics_service.add_session_to_blacklist'), \
                 patch('app.services.user_analytics_service.end_user_session'), \
                 patch('app.services.user_analytics_service.log_user_activity_for_user'), \
                 patch('app.services.user_analytics_service.get_client_info', return_value=self._client_info()):
                resp = mobile_logout()
        if isinstance(resp, tuple):
            _, status = resp
        else:
            status = resp.status_code
        assert status == 200

    def test_mobile_logout_end_session_failure_still_succeeds(self, app, db_session):
        from app.routes.api.mobile.auth import mobile_logout
        from app.utils.mobile_jwt import issue_token_pair

        with app.app_context():
            user = create_test_user(db_session, email='end-sess-fail@example.com', password='Pass123!')
            tokens = issue_token_pair(user.id, session_id='end-sess-fail-sid')
        with app.test_request_context(
            '/api/mobile/v1/auth/logout',
            method='POST',
            headers={'Authorization': f'Bearer {tokens["access_token"]}'},
        ):
            with patch('app.services.user_analytics_service.add_session_to_blacklist'), \
                 patch('app.services.user_analytics_service.end_user_session', side_effect=RuntimeError('db down')), \
                 patch('app.services.user_analytics_service.log_user_activity_for_user'), \
                 patch('app.services.user_analytics_service.get_client_info', return_value=self._client_info()):
                resp = mobile_logout()
        if isinstance(resp, tuple):
            _, status = resp
        else:
            status = resp.status_code
        assert status == 200

    def test_mobile_logout_records_session_duration(self, app, db_session):
        from app.models.core import UserLoginLog, UserSessionLog
        from app.routes.api.mobile.auth import mobile_logout
        from app.utils.mobile_jwt import issue_token_pair

        sid = 'duration-logout-sid'
        with app.app_context():
            user = create_test_user(db_session, email='duration-logout@example.com', password='Pass123!')
            db_session.add(UserSessionLog(
                user_id=user.id,
                session_id=sid,
                ip_address='127.0.0.1',
                duration_minutes=42,
            ))
            db_session.commit()
            tokens = issue_token_pair(user.id, session_id=sid)
        with app.test_request_context(
            '/api/mobile/v1/auth/logout',
            method='POST',
            headers={'Authorization': f'Bearer {tokens["access_token"]}'},
        ):
            with patch('app.services.user_analytics_service.add_session_to_blacklist'), \
                 patch('app.services.user_analytics_service.end_user_session'), \
                 patch('app.services.user_analytics_service.get_client_info', return_value=self._client_info()):
                resp = mobile_logout()
        if isinstance(resp, tuple):
            _, status = resp
        else:
            status = resp.status_code
        assert status == 200
        with app.app_context():
            logout_log = UserLoginLog.query.filter_by(
                user_id=user.id,
                event_type='logout',
            ).order_by(UserLoginLog.id.desc()).first()
            assert logout_log is not None
            assert logout_log.session_duration_minutes == 42


@pytest.mark.unit
class TestMobileProfileDirect:
    def test_mobile_profile_get(self, app, db_session):
        from app.routes.api.mobile.auth import mobile_profile

        with app.app_context():
            user = create_test_user(db_session, email='profile-direct@example.com', password='Pass123!')
        with app.test_request_context('/api/mobile/v1/auth/profile', method='GET'):
            login_user(user)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = mobile_profile()
        if isinstance(resp, tuple):
            body, status = resp
        else:
            body, status = resp, resp.status_code
        assert status == 200
        user_data = body.get_json()['data']['user']
        assert user_data['email'] == 'profile-direct@example.com'
        assert 'rbac_roles' in user_data

    def test_mobile_update_profile(self, app, db_session):
        from app.routes.api.mobile.auth import mobile_update_profile

        with app.app_context():
            user = create_test_user(db_session, email='update-direct@example.com', password='Pass123!')
        with app.test_request_context(
            '/api/mobile/v1/auth/profile',
            method='PUT',
            data=json.dumps({'name': 'Updated', 'title': 'Lead'}),
            content_type='application/json',
        ):
            login_user(user)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.services.user_analytics_service.log_user_activity'):
                resp = mobile_update_profile()
        if isinstance(resp, tuple):
            _, status = resp
        else:
            status = resp.status_code
        assert status == 200


@pytest.mark.unit
class TestMobileChangePasswordDirect:
    def test_change_password_wrong_current(self, app, db_session):
        from app.routes.api.mobile.auth import mobile_change_password

        with app.app_context():
            user = create_test_user(db_session, email='chg-pw@example.com', password='OldPass123!')
        with app.test_request_context(
            '/api/mobile/v1/auth/change-password',
            method='POST',
            data=json.dumps({'current_password': 'Wrong!', 'new_password': 'NewPass123!'}),
            content_type='application/json',
        ):
            login_user(user)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = mobile_change_password()
        if isinstance(resp, tuple):
            _, status = resp
        else:
            status = resp.status_code
        assert status == 401
