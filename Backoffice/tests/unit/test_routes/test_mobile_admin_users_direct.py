"""Direct unit tests for app.routes.api.mobile.admin_users view functions.

Uses route_admin / route_user fixtures from local conftest.py (same pattern
as tests/api/mobile/conftest.py admin_mobile_user — calls create_test_admin
directly from a fixture, no nested app context).
"""
import json
from unittest.mock import patch

import pytest
from flask_login import login_user

from tests.factories import create_test_user

pytestmark = [pytest.mark.unit]


def _parse(resp):
    if isinstance(resp, tuple):
        body, status = resp
        return body, status
    return resp, resp.status_code


# ---------------------------------------------------------------------------
# list_users
# ---------------------------------------------------------------------------

class TestListUsers:
    def test_success_empty(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_users import list_users

        with app.test_request_context('/api/mobile/v1/admin/users', method='GET'):
            login_user(route_admin)
            with patch(
                'app.routes.admin.user_management.helpers.build_admin_user_list_rows',
                return_value=[],
            ):
                resp = list_users()

        body, status = _parse(resp)
        assert status == 200
        assert body.get_json()['data'] == []

    def test_with_users(self, app, db_session, route_admin, route_user):
        from app.routes.api.mobile.admin_users import list_users

        with app.test_request_context('/api/mobile/v1/admin/users', method='GET'):
            login_user(route_admin)
            with patch(
                'app.routes.admin.user_management.helpers.build_admin_user_list_rows',
                return_value=[
                    {'id': route_admin.id, 'email': route_admin.email},
                    {'id': route_user.id, 'email': route_user.email},
                ],
            ):
                resp = list_users()

        body, status = _parse(resp)
        assert status == 200
        assert len(body.get_json()['data']) == 2

    def test_with_search_filter(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_users import list_users

        with app.test_request_context('/api/mobile/v1/admin/users?search=test', method='GET'):
            login_user(route_admin)
            with patch(
                'app.routes.admin.user_management.helpers.build_admin_user_list_rows',
                return_value=[],
            ):
                resp = list_users()

        _, status = _parse(resp)
        assert status == 200

    def test_with_pagination(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_users import list_users

        with app.test_request_context(
            '/api/mobile/v1/admin/users?page=1&per_page=10', method='GET'
        ):
            login_user(route_admin)
            with patch(
                'app.routes.admin.user_management.helpers.build_admin_user_list_rows',
                return_value=[],
            ):
                resp = list_users()

        _, status = _parse(resp)
        assert status == 200


# ---------------------------------------------------------------------------
# get_user
# ---------------------------------------------------------------------------

class TestGetUser:
    def test_user_not_found(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_users import get_user

        with app.test_request_context('/api/mobile/v1/admin/users/99999', method='GET'):
            login_user(route_admin)
            with patch(
                'app.routes.admin.user_management.helpers.build_admin_user_detail_dict',
                return_value=None,
            ):
                resp = get_user(99999)

        _, status = _parse(resp)
        assert status == 404

    def test_success(self, app, db_session, route_admin, route_user):
        from app.routes.api.mobile.admin_users import get_user

        with app.test_request_context(
            f'/api/mobile/v1/admin/users/{route_user.id}', method='GET'
        ):
            login_user(route_admin)
            with patch(
                'app.routes.admin.user_management.helpers.build_admin_user_detail_dict',
                return_value={
                    'id': route_user.id,
                    'email': route_user.email,
                    'name': route_user.name,
                },
            ):
                resp = get_user(route_user.id)

        body, status = _parse(resp)
        assert status == 200
        assert body.get_json()['data']['user']['email'] == route_user.email


# ---------------------------------------------------------------------------
# update_user
# ---------------------------------------------------------------------------

class TestUpdateUser:
    def _put(self, path, payload):
        return dict(
            path=path,
            method='PUT',
            data=json.dumps(payload),
            content_type='application/json',
        )

    def test_user_not_found(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_users import update_user

        with app.test_request_context(**self._put('/api/mobile/v1/admin/users/99999', {'name': 'X'})):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = update_user(99999)

        _, status = _parse(resp)
        assert status == 404

    def test_no_updatable_fields_returns_400(self, app, db_session, route_admin, route_user):
        from app.routes.api.mobile.admin_users import update_user

        with app.test_request_context(**self._put(
            f'/api/mobile/v1/admin/users/{route_user.id}', {'unsupported_field': 'value'}
        )):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = update_user(route_user.id)

        _, status = _parse(resp)
        assert status == 400

    def test_update_name_success(self, app, db_session, route_admin, route_user):
        from app.routes.api.mobile.admin_users import update_user

        with app.test_request_context(**self._put(
            f'/api/mobile/v1/admin/users/{route_user.id}', {'name': 'New Name'}
        )):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.services.user_analytics_service.log_admin_action'):
                resp = update_user(route_user.id)

        _, status = _parse(resp)
        assert status == 200

    def test_update_name_too_long_returns_400(self, app, db_session, route_admin, route_user):
        from app.routes.api.mobile.admin_users import update_user

        with app.test_request_context(**self._put(
            f'/api/mobile/v1/admin/users/{route_user.id}', {'name': 'A' * 101}
        )):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = update_user(route_user.id)

        _, status = _parse(resp)
        assert status == 400

    def test_update_name_to_none(self, app, db_session, route_admin, route_user):
        from app.routes.api.mobile.admin_users import update_user

        with app.test_request_context(**self._put(
            f'/api/mobile/v1/admin/users/{route_user.id}', {'name': None}
        )):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.services.user_analytics_service.log_admin_action'):
                resp = update_user(route_user.id)

        _, status = _parse(resp)
        assert status == 200

    def test_update_title_success(self, app, db_session, route_admin, route_user):
        from app.routes.api.mobile.admin_users import update_user

        with app.test_request_context(**self._put(
            f'/api/mobile/v1/admin/users/{route_user.id}', {'title': 'Dr.'}
        )):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.services.user_analytics_service.log_admin_action'):
                resp = update_user(route_user.id)

        _, status = _parse(resp)
        assert status == 200

    def test_update_title_too_long_returns_400(self, app, db_session, route_admin, route_user):
        from app.routes.api.mobile.admin_users import update_user

        with app.test_request_context(**self._put(
            f'/api/mobile/v1/admin/users/{route_user.id}', {'title': 'T' * 101}
        )):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = update_user(route_user.id)

        _, status = _parse(resp)
        assert status == 400

    def test_update_title_to_none(self, app, db_session, route_admin, route_user):
        from app.routes.api.mobile.admin_users import update_user

        with app.test_request_context(**self._put(
            f'/api/mobile/v1/admin/users/{route_user.id}', {'title': None}
        )):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.services.user_analytics_service.log_admin_action'):
                resp = update_user(route_user.id)

        _, status = _parse(resp)
        assert status == 200

    def test_update_chatbot_enabled(self, app, db_session, route_admin, route_user):
        from app.routes.api.mobile.admin_users import update_user

        with app.test_request_context(**self._put(
            f'/api/mobile/v1/admin/users/{route_user.id}', {'chatbot_enabled': True}
        )):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.services.user_analytics_service.log_admin_action'):
                resp = update_user(route_user.id)

        _, status = _parse(resp)
        assert status == 200

    def test_update_profile_color_success(self, app, db_session, route_admin, route_user):
        from app.routes.api.mobile.admin_users import update_user

        with app.test_request_context(**self._put(
            f'/api/mobile/v1/admin/users/{route_user.id}', {'profile_color': '#FF5733'}
        )):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.services.user_analytics_service.log_admin_action'):
                resp = update_user(route_user.id)

        _, status = _parse(resp)
        assert status == 200

    def test_update_profile_color_invalid_returns_400(self, app, db_session, route_admin, route_user):
        from app.routes.api.mobile.admin_users import update_user

        with app.test_request_context(**self._put(
            f'/api/mobile/v1/admin/users/{route_user.id}', {'profile_color': 'not-a-color'}
        )):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = update_user(route_user.id)

        _, status = _parse(resp)
        assert status == 400

    def test_update_profile_color_empty_returns_400(self, app, db_session, route_admin, route_user):
        from app.routes.api.mobile.admin_users import update_user

        with app.test_request_context(**self._put(
            f'/api/mobile/v1/admin/users/{route_user.id}', {'profile_color': ''}
        )):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = update_user(route_user.id)

        _, status = _parse(resp)
        assert status == 400

    def test_update_active_to_false(self, app, db_session, route_admin, route_user):
        from app.routes.api.mobile.admin_users import update_user

        with app.test_request_context(**self._put(
            f'/api/mobile/v1/admin/users/{route_user.id}', {'active': False}
        )):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.services.user_analytics_service.log_admin_action'):
                resp = update_user(route_user.id)

        _, status = _parse(resp)
        assert status == 200

    def test_cannot_deactivate_self_returns_400(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_users import update_user

        with app.test_request_context(**self._put(
            f'/api/mobile/v1/admin/users/{route_admin.id}', {'active': False}
        )):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = update_user(route_admin.id)

        _, status = _parse(resp)
        assert status == 400

    def test_non_sysmanager_cannot_edit_admin_returns_403(self, app, db_session, route_admin, route_user):
        from app.routes.api.mobile.admin_users import update_user

        with app.test_request_context(**self._put(
            f'/api/mobile/v1/admin/users/{route_user.id}', {'name': 'Changed'}
        )):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.services.authorization_service.AuthorizationService.is_system_manager',
                       return_value=False), \
                 patch('app.services.authorization_service.AuthorizationService.is_admin',
                       return_value=True):
                resp = update_user(route_user.id)

        _, status = _parse(resp)
        assert status == 403

    def test_rbac_role_ids_no_permission_returns_403(self, app, db_session, route_admin, route_user):
        from app.routes.api.mobile.admin_users import update_user

        with app.test_request_context(**self._put(
            f'/api/mobile/v1/admin/users/{route_user.id}', {'rbac_role_ids': [1]}
        )):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.services.authorization_service.AuthorizationService.has_rbac_permission',
                       return_value=False):
                resp = update_user(route_user.id)

        _, status = _parse(resp)
        assert status == 403

    def test_rbac_roles_not_a_list_returns_400(self, app, db_session, route_admin, route_user):
        from app.routes.api.mobile.admin_users import update_user

        with app.test_request_context(**self._put(
            f'/api/mobile/v1/admin/users/{route_user.id}', {'rbac_role_ids': 'not-a-list'}
        )):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.services.authorization_service.AuthorizationService.has_rbac_permission',
                       return_value=True):
                resp = update_user(route_user.id)

        _, status = _parse(resp)
        assert status == 400

    def test_rbac_role_invalid_id_returns_400(self, app, db_session, route_admin, route_user):
        from app.routes.api.mobile.admin_users import update_user

        with app.test_request_context(**self._put(
            f'/api/mobile/v1/admin/users/{route_user.id}', {'rbac_role_ids': ['not-an-int']}
        )):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.services.authorization_service.AuthorizationService.has_rbac_permission',
                       return_value=True):
                resp = update_user(route_user.id)

        _, status = _parse(resp)
        assert status == 400

    def test_rbac_self_roles_change_returns_400(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_users import update_user

        with app.test_request_context(**self._put(
            f'/api/mobile/v1/admin/users/{route_admin.id}', {'rbac_role_ids': [1]}
        )):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.services.authorization_service.AuthorizationService.has_rbac_permission',
                       return_value=True), \
                 patch('app.services.authorization_service.AuthorizationService.is_system_manager',
                       return_value=False):
                resp = update_user(route_admin.id)

        _, status = _parse(resp)
        assert status == 400

    def test_exception_returns_500(self, app, db_session, route_admin, route_user):
        from app.routes.api.mobile.admin_users import update_user

        with app.test_request_context(**self._put(
            f'/api/mobile/v1/admin/users/{route_user.id}', {'name': 'Test'}
        )):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.services.user_analytics_service.log_admin_action',
                       side_effect=RuntimeError('db error')), \
                 patch('app.utils.transactions.request_transaction_rollback'):
                resp = update_user(route_user.id)

        _, status = _parse(resp)
        assert status == 500


# ---------------------------------------------------------------------------
# activate_user
# ---------------------------------------------------------------------------

class TestActivateUser:
    def test_user_not_found(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_users import activate_user

        with app.test_request_context(
            '/api/mobile/v1/admin/users/99999/activate', method='POST'
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = activate_user(99999)

        _, status = _parse(resp)
        assert status == 404

    def test_cannot_activate_self_returns_400(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_users import activate_user

        with app.test_request_context(
            f'/api/mobile/v1/admin/users/{route_admin.id}/activate', method='POST'
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = activate_user(route_admin.id)

        _, status = _parse(resp)
        assert status == 400

    def test_non_sysmanager_cannot_activate_admin_returns_400(self, app, db_session, route_admin, route_user):
        from app.routes.api.mobile.admin_users import activate_user

        with app.test_request_context(
            f'/api/mobile/v1/admin/users/{route_user.id}/activate', method='POST'
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.services.authorization_service.AuthorizationService.is_system_manager',
                       return_value=False), \
                 patch('app.services.authorization_service.AuthorizationService.is_admin',
                       return_value=True):
                resp = activate_user(route_user.id)

        _, status = _parse(resp)
        assert status == 400

    def test_success(self, app, db_session, route_admin, route_user):
        from app.routes.api.mobile.admin_users import activate_user

        with app.test_request_context(
            f'/api/mobile/v1/admin/users/{route_user.id}/activate', method='POST'
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = activate_user(route_user.id)

        _, status = _parse(resp)
        assert status == 200


# ---------------------------------------------------------------------------
# deactivate_user
# ---------------------------------------------------------------------------

class TestDeactivateUser:
    def test_user_not_found(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_users import deactivate_user

        with app.test_request_context(
            '/api/mobile/v1/admin/users/99999/deactivate', method='POST'
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = deactivate_user(99999)

        _, status = _parse(resp)
        assert status == 404

    def test_cannot_deactivate_self_returns_400(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_users import deactivate_user

        with app.test_request_context(
            f'/api/mobile/v1/admin/users/{route_admin.id}/deactivate', method='POST'
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = deactivate_user(route_admin.id)

        _, status = _parse(resp)
        assert status == 400

    def test_non_sysmanager_cannot_deactivate_admin_returns_400(self, app, db_session, route_admin, route_user):
        from app.routes.api.mobile.admin_users import deactivate_user

        with app.test_request_context(
            f'/api/mobile/v1/admin/users/{route_user.id}/deactivate', method='POST'
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.services.authorization_service.AuthorizationService.is_system_manager',
                       return_value=False), \
                 patch('app.services.authorization_service.AuthorizationService.is_admin',
                       return_value=True):
                resp = deactivate_user(route_user.id)

        _, status = _parse(resp)
        assert status == 400

    def test_success(self, app, db_session, route_admin, route_user):
        from app.routes.api.mobile.admin_users import deactivate_user

        with app.test_request_context(
            f'/api/mobile/v1/admin/users/{route_user.id}/deactivate', method='POST'
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = deactivate_user(route_user.id)

        _, status = _parse(resp)
        assert status == 200


# ---------------------------------------------------------------------------
# list_rbac_roles
# ---------------------------------------------------------------------------

class TestListRbacRoles:
    def test_success(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_users import list_rbac_roles

        with app.test_request_context(
            '/api/mobile/v1/admin/users/rbac-roles', method='GET'
        ):
            login_user(route_admin)
            resp = list_rbac_roles()

        body, status = _parse(resp)
        assert status == 200
        assert 'roles' in body.get_json()['data']
        roles = body.get_json()['data']['roles']
        assert isinstance(roles, list)
