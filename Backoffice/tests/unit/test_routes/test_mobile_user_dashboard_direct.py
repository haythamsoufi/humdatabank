"""Direct unit tests for app/routes/api/mobile/user_dashboard.py."""
import json
import pytest
from unittest.mock import patch, MagicMock
from flask import Response as FlaskResponse
from flask_login import login_user

from tests.factories import create_test_user

pytestmark = [pytest.mark.unit]


def _jwt_headers(app, user_id, sid=None):
    from app.utils.mobile_jwt import issue_token_pair
    with app.app_context():
        tokens = issue_token_pair(user_id, session_id=sid or f'dash-sid-{user_id}')
    return {'Authorization': f'Bearer {tokens["access_token"]}'}


def _unpack(resp):
    if isinstance(resp, tuple):
        return resp[0], resp[1]
    return resp, 200


def _make_json_response(app, data: dict, status: int = 200):
    """Build a real Flask JSON response object within an app context."""
    resp = app.response_class(
        response=json.dumps(data),
        status=status,
        mimetype='application/json',
    )
    return resp


class TestMobileUserDashboard:
    def test_success_get_dashboard_returns_tuple_200(self, app, db_session):
        """inner returns (Response, 200) — should be wrapped in mobile_ok."""
        from app.routes.api.mobile.user_dashboard import mobile_user_dashboard

        user = create_test_user(db_session, email='dash-user1@example.com')
        headers = _jwt_headers(app, user.id)

        dashboard_payload = {
            'current_assignments': [],
            'past_assignments': [],
            'entities': [],
            'selected_entity': None,
        }

        with app.test_request_context(
            '/api/mobile/v1/user/dashboard',
            method='GET',
            headers=headers,
        ):
            login_user(user)
            inner_resp = _make_json_response(app, dashboard_payload, 200)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.api.mobile.user_dashboard.get_dashboard', return_value=(inner_resp, 200)):
                resp = mobile_user_dashboard()

        body, status = _unpack(resp)
        assert status == 200
        result = body.get_json()
        assert result['success'] is True
        assert 'current_assignments' in result['data']

    def test_success_get_dashboard_returns_response_directly(self, app, db_session):
        """inner returns a bare Response (not a tuple) — should default to 200."""
        from app.routes.api.mobile.user_dashboard import mobile_user_dashboard

        user = create_test_user(db_session, email='dash-user2@example.com')
        headers = _jwt_headers(app, user.id)

        dashboard_payload = {'current_assignments': [], 'past_assignments': [], 'entities': []}

        with app.test_request_context(
            '/api/mobile/v1/user/dashboard',
            method='GET',
            headers=headers,
        ):
            login_user(user)
            inner_resp = _make_json_response(app, dashboard_payload, 200)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.api.mobile.user_dashboard.get_dashboard', return_value=inner_resp):
                resp = mobile_user_dashboard()

        body, status = _unpack(resp)
        assert status == 200
        assert body.get_json()['success'] is True

    def test_inner_non_200_returns_mobile_error(self, app, db_session):
        """When inner returns a non-200 tuple, mobile_user_dashboard wraps it as error."""
        from app.routes.api.mobile.user_dashboard import mobile_user_dashboard

        user = create_test_user(db_session, email='dash-user3@example.com')
        headers = _jwt_headers(app, user.id)

        with app.test_request_context(
            '/api/mobile/v1/user/dashboard',
            method='GET',
            headers=headers,
        ):
            login_user(user)
            error_resp = _make_json_response(app, {'error': 'Forbidden'}, 403)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.api.mobile.user_dashboard.get_dashboard', return_value=(error_resp, 403)):
                resp = mobile_user_dashboard()

        body, status = _unpack(resp)
        assert status == 403

    def test_inner_non_200_without_error_key_falls_back_to_default_message(self, app, db_session):
        """Non-200 response with no 'error' key uses default message."""
        from app.routes.api.mobile.user_dashboard import mobile_user_dashboard

        user = create_test_user(db_session, email='dash-user4@example.com')
        headers = _jwt_headers(app, user.id)

        with app.test_request_context(
            '/api/mobile/v1/user/dashboard',
            method='GET',
            headers=headers,
        ):
            login_user(user)
            empty_resp = _make_json_response(app, {}, 500)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.api.mobile.user_dashboard.get_dashboard', return_value=(empty_resp, 500)):
                resp = mobile_user_dashboard()

        _, status = _unpack(resp)
        assert status == 500

    def test_exception_in_get_dashboard_returns_500(self, app, db_session):
        """Any exception from the inner get_dashboard call should return 500."""
        from app.routes.api.mobile.user_dashboard import mobile_user_dashboard

        user = create_test_user(db_session, email='dash-user5@example.com')
        headers = _jwt_headers(app, user.id)

        with app.test_request_context(
            '/api/mobile/v1/user/dashboard',
            method='GET',
            headers=headers,
        ):
            login_user(user)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.api.mobile.user_dashboard.get_dashboard', side_effect=RuntimeError('bang')):
                resp = mobile_user_dashboard()

        _, status = _unpack(resp)
        assert status == 500

    def test_no_auth_returns_401(self, app):
        client = app.test_client()
        resp = client.get('/api/mobile/v1/user/dashboard')
        assert resp.status_code == 401

    def test_dict_response_from_get_dashboard(self, app, db_session):
        """If get_dashboard returns a plain dict (not Response), it should be forwarded."""
        from app.routes.api.mobile.user_dashboard import mobile_user_dashboard

        user = create_test_user(db_session, email='dash-user6@example.com')
        headers = _jwt_headers(app, user.id)

        with app.test_request_context(
            '/api/mobile/v1/user/dashboard',
            method='GET',
            headers=headers,
        ):
            login_user(user)
            # Return a plain dict tuple: (dict, 200) — resp_obj is not a Response instance
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch(
                     'app.routes.api.mobile.user_dashboard.get_dashboard',
                     return_value=({'assignments': []}, 200),
                 ):
                resp = mobile_user_dashboard()

        body, status = _unpack(resp)
        assert status == 200
        assert body.get_json()['success'] is True
