"""Direct unit tests for app/routes/api/mobile/admin_org.py."""
import pytest
from unittest.mock import patch, MagicMock
from flask_login import login_user

from tests.factories import create_test_admin, create_test_country

pytestmark = [pytest.mark.unit]


def _make_jwt_headers(app, user_id, session_id='org-test-sid'):
    """Issue a JWT access token and return the Authorization header dict."""
    from app.utils.mobile_jwt import issue_token_pair
    with app.app_context():
        tokens = issue_token_pair(user_id, session_id=session_id)
    return {'Authorization': f'Bearer {tokens["access_token"]}'}


class TestListBranches:
    def test_list_branches_returns_ok(self, app, db_session):
        from app.routes.api.mobile.admin_org import list_branches

        admin = create_test_admin(db_session, email='org-admin1@example.com')
        headers = _make_jwt_headers(app, admin.id, 'branches-sid')

        with app.test_request_context(
            '/api/mobile/v1/admin/org/branches/999',
            method='GET',
            headers=headers,
        ):
            login_user(admin)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.admin.shared.user_has_permission', return_value=True):
                resp = list_branches(999)

        if isinstance(resp, tuple):
            body, status = resp[0], resp[1]
        else:
            body, status = resp, 200
        assert status == 200
        data = body.get_json()
        assert data['success'] is True
        assert 'branches' in data['data']

    def test_list_branches_empty_result(self, app, db_session):
        from app.routes.api.mobile.admin_org import list_branches

        admin = create_test_admin(db_session, email='org-admin2@example.com')
        headers = _make_jwt_headers(app, admin.id, 'branches-empty-sid')

        with app.test_request_context(
            '/api/mobile/v1/admin/org/branches/0',
            method='GET',
            headers=headers,
        ):
            login_user(admin)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.admin.shared.user_has_permission', return_value=True):
                resp = list_branches(0)

        if isinstance(resp, tuple):
            body, status = resp[0], resp[1]
        else:
            body, status = resp, 200
        assert status == 200
        assert body.get_json()['data']['branches'] == []

    def test_list_branches_no_auth_returns_401(self, app, db_session):
        client = app.test_client()
        resp = client.get('/api/mobile/v1/admin/org/branches/1')
        assert resp.status_code == 401


class TestListSubbranches:
    def test_list_subbranches_returns_ok(self, app, db_session):
        from app.routes.api.mobile.admin_org import list_subbranches

        admin = create_test_admin(db_session, email='org-admin3@example.com')
        headers = _make_jwt_headers(app, admin.id, 'subbranches-sid')

        with app.test_request_context(
            '/api/mobile/v1/admin/org/subbranches/999',
            method='GET',
            headers=headers,
        ):
            login_user(admin)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.admin.shared.user_has_permission', return_value=True):
                resp = list_subbranches(999)

        if isinstance(resp, tuple):
            body, status = resp[0], resp[1]
        else:
            body, status = resp, 200
        assert status == 200
        data = body.get_json()
        assert data['success'] is True
        assert 'subbranches' in data['data']

    def test_list_subbranches_empty(self, app, db_session):
        from app.routes.api.mobile.admin_org import list_subbranches

        admin = create_test_admin(db_session, email='org-admin4@example.com')
        headers = _make_jwt_headers(app, admin.id, 'subbranches-empty-sid')

        with app.test_request_context(
            '/api/mobile/v1/admin/org/subbranches/0',
            method='GET',
            headers=headers,
        ):
            login_user(admin)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.admin.shared.user_has_permission', return_value=True):
                resp = list_subbranches(0)

        if isinstance(resp, tuple):
            body, status = resp[0], resp[1]
        else:
            body, status = resp, 200
        assert status == 200
        assert body.get_json()['data']['subbranches'] == []


class TestOrgStructure:
    def test_org_structure_returns_ok(self, app, db_session):
        from app.routes.api.mobile.admin_org import org_structure

        admin = create_test_admin(db_session, email='org-admin5@example.com')
        create_test_country(db_session, name='TestOrgCountry')
        headers = _make_jwt_headers(app, admin.id, 'structure-sid')

        with app.test_request_context(
            '/api/mobile/v1/admin/org/structure',
            method='GET',
            headers=headers,
        ):
            login_user(admin)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.admin.shared.user_has_permission', return_value=True):
                resp = org_structure()

        if isinstance(resp, tuple):
            body, status = resp[0], resp[1]
        else:
            body, status = resp, 200
        assert status == 200
        result = body.get_json()
        assert result['success'] is True
        assert 'countries' in result['data']
        assert 'branches' in result['data']
        assert 'subbranches' in result['data']
        assert result['data']['active_tab'] == 'countries'

    def test_org_structure_handles_db_exception(self, app, db_session):
        from app.routes.api.mobile.admin_org import org_structure

        admin = create_test_admin(db_session, email='org-admin6@example.com')
        headers = _make_jwt_headers(app, admin.id, 'structure-error-sid')

        with app.test_request_context(
            '/api/mobile/v1/admin/org/structure',
            method='GET',
            headers=headers,
        ):
            login_user(admin)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.admin.shared.user_has_permission', return_value=True), \
                 patch('app.models.Country') as mock_country:
                mock_country.query.order_by.return_value.all.side_effect = RuntimeError('db error')
                resp = org_structure()

        if isinstance(resp, tuple):
            body, status = resp[0], resp[1]
        else:
            body, status = resp, resp.status_code
        assert status == 500

    def test_org_structure_no_auth_returns_401(self, app):
        client = app.test_client()
        resp = client.get('/api/mobile/v1/admin/org/structure')
        assert resp.status_code == 401

    def test_org_structure_forbidden_without_permission(self, app, db_session):
        from app.routes.api.mobile.admin_org import org_structure

        admin = create_test_admin(db_session, email='org-admin7@example.com')
        headers = _make_jwt_headers(app, admin.id, 'structure-forbidden-sid')

        with app.test_request_context(
            '/api/mobile/v1/admin/org/structure',
            method='GET',
            headers=headers,
        ):
            login_user(admin)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.admin.shared.user_has_permission', return_value=False):
                resp = org_structure()

        if isinstance(resp, tuple):
            _, status = resp[0], resp[1]
        else:
            status = resp.status_code
        assert status == 403
