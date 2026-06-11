"""Direct unit tests for app/routes/api/mobile/admin_requests.py."""
import pytest
from unittest.mock import patch, MagicMock
from flask_login import login_user

from tests.factories import create_test_admin, create_test_user, create_test_country

pytestmark = [pytest.mark.unit]


def _jwt_headers(app, user_id, sid=None):
    from app.utils.mobile_jwt import issue_token_pair
    with app.app_context():
        tokens = issue_token_pair(user_id, session_id=sid or f'req-sid-{user_id}')
    return {'Authorization': f'Bearer {tokens["access_token"]}'}


def _unpack(resp):
    if isinstance(resp, tuple):
        return resp[0], resp[1]
    return resp, 200


class TestListAccessRequests:
    def test_list_returns_pending_and_processed(self, app, db_session):
        from app.routes.api.mobile.admin_requests import list_access_requests

        admin = create_test_admin(db_session, email='req-admin1@example.com')
        headers = _jwt_headers(app, admin.id)

        with app.test_request_context(
            '/api/mobile/v1/admin/access-requests',
            method='GET',
            headers=headers,
        ):
            login_user(admin)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.admin.shared.user_has_permission', return_value=True):
                resp = list_access_requests()

        body, status = _unpack(resp)
        assert status == 200
        data = body.get_json()
        assert data['success'] is True
        assert 'pending' in data['data']
        assert 'processed' in data['data']

    def test_list_no_auth_returns_401(self, app):
        client = app.test_client()
        resp = client.get('/api/mobile/v1/admin/access-requests')
        assert resp.status_code == 401

    def test_list_no_permission_returns_403(self, app, db_session):
        from app.routes.api.mobile.admin_requests import list_access_requests

        admin = create_test_admin(db_session, email='req-admin1b@example.com')
        headers = _jwt_headers(app, admin.id)

        with app.test_request_context(
            '/api/mobile/v1/admin/access-requests',
            method='GET',
            headers=headers,
        ):
            login_user(admin)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.admin.shared.user_has_permission', return_value=False):
                resp = list_access_requests()

        _, status = _unpack(resp)
        assert status == 403

    def test_list_with_existing_requests(self, app, db_session):
        """Ensure serializer runs over actual records including null user/country paths."""
        from app.models.system import CountryAccessRequest
        from app.routes.api.mobile.admin_requests import list_access_requests

        admin = create_test_admin(db_session, email='req-admin1c@example.com')
        requester = create_test_user(db_session, email='req-user-for-list@example.com')
        country = create_test_country(db_session)
        car = CountryAccessRequest(
            user_id=requester.id,
            country_id=country.id,
            status='pending',
        )
        db_session.add(car)
        db_session.commit()

        headers = _jwt_headers(app, admin.id)
        with app.test_request_context(
            '/api/mobile/v1/admin/access-requests',
            method='GET',
            headers=headers,
        ):
            login_user(admin)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.admin.shared.user_has_permission', return_value=True):
                resp = list_access_requests()

        body, status = _unpack(resp)
        assert status == 200
        pending = body.get_json()['data']['pending']
        assert len(pending) >= 1
        entry = pending[0]
        assert entry['user_email'] == requester.email
        assert entry['country_name'] == country.name


class TestApproveAccessRequest:
    def test_approve_not_found(self, app, db_session):
        from app.routes.api.mobile.admin_requests import approve_access_request

        admin = create_test_admin(db_session, email='req-admin2@example.com')
        headers = _jwt_headers(app, admin.id)

        with app.test_request_context(
            '/api/mobile/v1/admin/access-requests/99999/approve',
            method='POST',
            headers=headers,
        ):
            login_user(admin)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.admin.shared.user_has_permission', return_value=True):
                resp = approve_access_request(99999)

        _, status = _unpack(resp)
        assert status == 404

    def test_approve_already_processed(self, app, db_session):
        from app.models.system import CountryAccessRequest
        from app.routes.api.mobile.admin_requests import approve_access_request

        admin = create_test_admin(db_session, email='req-admin3@example.com')
        requester = create_test_user(db_session, email='req-user2@example.com')
        country = create_test_country(db_session)
        car = CountryAccessRequest(
            user_id=requester.id,
            country_id=country.id,
            status='approved',
        )
        db_session.add(car)
        db_session.commit()

        headers = _jwt_headers(app, admin.id)
        with app.test_request_context(
            f'/api/mobile/v1/admin/access-requests/{car.id}/approve',
            method='POST',
            headers=headers,
        ):
            login_user(admin)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.admin.shared.user_has_permission', return_value=True):
                resp = approve_access_request(car.id)

        _, status = _unpack(resp)
        assert status == 400

    def test_approve_user_or_country_not_found(self, app, db_session):
        from app.models.system import CountryAccessRequest
        from app.routes.api.mobile.admin_requests import approve_access_request

        admin = create_test_admin(db_session, email='req-admin4@example.com')
        requester = create_test_user(db_session, email='req-user3@example.com')
        country = create_test_country(db_session)
        car = CountryAccessRequest(
            user_id=requester.id,
            country_id=country.id,
            status='pending',
        )
        db_session.add(car)
        db_session.commit()

        headers = _jwt_headers(app, admin.id)
        with app.test_request_context(
            f'/api/mobile/v1/admin/access-requests/{car.id}/approve',
            method='POST',
            headers=headers,
        ):
            login_user(admin)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.admin.shared.user_has_permission', return_value=True), \
                 patch('app.models.User.query') as mock_uq:
                mock_uq.get.return_value = None
                resp = approve_access_request(car.id)

        _, status = _unpack(resp)
        assert status == 404

    def test_approve_success(self, app, db_session):
        from app.models.system import CountryAccessRequest
        from app.routes.api.mobile.admin_requests import approve_access_request

        admin = create_test_admin(db_session, email='req-admin5@example.com')
        requester = create_test_user(db_session, email='req-user4@example.com')
        country = create_test_country(db_session)
        car = CountryAccessRequest(
            user_id=requester.id,
            country_id=country.id,
            status='pending',
        )
        db_session.add(car)
        db_session.commit()

        headers = _jwt_headers(app, admin.id)
        with app.test_request_context(
            f'/api/mobile/v1/admin/access-requests/{car.id}/approve',
            method='POST',
            headers=headers,
        ):
            login_user(admin)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.admin.shared.user_has_permission', return_value=True), \
                 patch.object(requester.__class__, 'add_entity_permission', create=True):
                resp = approve_access_request(car.id)

        _, status = _unpack(resp)
        assert status == 200

    def test_approve_handles_exception(self, app, db_session):
        from app.models.system import CountryAccessRequest
        from app.routes.api.mobile.admin_requests import approve_access_request

        admin = create_test_admin(db_session, email='req-admin6@example.com')
        requester = create_test_user(db_session, email='req-user5@example.com')
        country = create_test_country(db_session)
        car = CountryAccessRequest(
            user_id=requester.id,
            country_id=country.id,
            status='pending',
        )
        db_session.add(car)
        db_session.commit()

        headers = _jwt_headers(app, admin.id)
        with app.test_request_context(
            f'/api/mobile/v1/admin/access-requests/{car.id}/approve',
            method='POST',
            headers=headers,
        ):
            login_user(admin)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.admin.shared.user_has_permission', return_value=True), \
                 patch('app.models.User.query') as mock_uq, \
                 patch('app.utils.transactions.request_transaction_rollback'):
                mock_uq.get.side_effect = RuntimeError('db failure')
                resp = approve_access_request(car.id)

        _, status = _unpack(resp)
        assert status == 500


class TestRejectAccessRequest:
    def test_reject_not_found(self, app, db_session):
        from app.routes.api.mobile.admin_requests import reject_access_request

        admin = create_test_admin(db_session, email='req-admin7@example.com')
        headers = _jwt_headers(app, admin.id)

        with app.test_request_context(
            '/api/mobile/v1/admin/access-requests/99999/reject',
            method='POST',
            headers=headers,
        ):
            login_user(admin)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.admin.shared.user_has_permission', return_value=True):
                resp = reject_access_request(99999)

        _, status = _unpack(resp)
        assert status == 404

    def test_reject_already_processed(self, app, db_session):
        from app.models.system import CountryAccessRequest
        from app.routes.api.mobile.admin_requests import reject_access_request

        admin = create_test_admin(db_session, email='req-admin8@example.com')
        requester = create_test_user(db_session, email='req-user6@example.com')
        country = create_test_country(db_session)
        car = CountryAccessRequest(
            user_id=requester.id,
            country_id=country.id,
            status='rejected',
        )
        db_session.add(car)
        db_session.commit()

        headers = _jwt_headers(app, admin.id)
        with app.test_request_context(
            f'/api/mobile/v1/admin/access-requests/{car.id}/reject',
            method='POST',
            headers=headers,
        ):
            login_user(admin)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.admin.shared.user_has_permission', return_value=True):
                resp = reject_access_request(car.id)

        _, status = _unpack(resp)
        assert status == 400

    def test_reject_success(self, app, db_session):
        from app.models.system import CountryAccessRequest
        from app.routes.api.mobile.admin_requests import reject_access_request

        admin = create_test_admin(db_session, email='req-admin9@example.com')
        requester = create_test_user(db_session, email='req-user7@example.com')
        country = create_test_country(db_session)
        car = CountryAccessRequest(
            user_id=requester.id,
            country_id=country.id,
            status='pending',
        )
        db_session.add(car)
        db_session.commit()

        headers = _jwt_headers(app, admin.id)
        with app.test_request_context(
            f'/api/mobile/v1/admin/access-requests/{car.id}/reject',
            method='POST',
            headers=headers,
        ):
            login_user(admin)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.admin.shared.user_has_permission', return_value=True):
                resp = reject_access_request(car.id)

        _, status = _unpack(resp)
        assert status == 200

    def test_reject_handles_exception(self, app, db_session):
        from app.models.system import CountryAccessRequest
        from app.routes.api.mobile.admin_requests import reject_access_request

        admin = create_test_admin(db_session, email='req-admin10@example.com')
        requester = create_test_user(db_session, email='req-user8@example.com')
        country = create_test_country(db_session)
        car = CountryAccessRequest(
            user_id=requester.id,
            country_id=country.id,
            status='pending',
        )
        db_session.add(car)
        db_session.commit()

        headers = _jwt_headers(app, admin.id)
        with app.test_request_context(
            f'/api/mobile/v1/admin/access-requests/{car.id}/reject',
            method='POST',
            headers=headers,
        ):
            login_user(admin)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.admin.shared.user_has_permission', return_value=True), \
                 patch('app.db.session') as mock_sess, \
                 patch('app.utils.transactions.request_transaction_rollback'):
                mock_sess.flush.side_effect = RuntimeError('flush error')
                resp = reject_access_request(car.id)

        _, status = _unpack(resp)
        assert status == 500


class TestApproveAllAccessRequests:
    def test_approve_all_no_pending(self, app, db_session):
        from app.routes.api.mobile.admin_requests import approve_all_access_requests

        admin = create_test_admin(db_session, email='req-admin11@example.com')
        headers = _jwt_headers(app, admin.id)

        with app.test_request_context(
            '/api/mobile/v1/admin/access-requests/approve-all',
            method='POST',
            headers=headers,
        ):
            login_user(admin)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.admin.shared.user_has_permission', return_value=True):
                resp = approve_all_access_requests()

        body, status = _unpack(resp)
        assert status == 200
        data = body.get_json()
        assert data['data']['approved_count'] == 0

    def test_approve_all_with_pending(self, app, db_session):
        from app.models.system import CountryAccessRequest
        from app.routes.api.mobile.admin_requests import approve_all_access_requests

        admin = create_test_admin(db_session, email='req-admin12@example.com')
        requester = create_test_user(db_session, email='req-user9@example.com')
        country = create_test_country(db_session)
        car = CountryAccessRequest(
            user_id=requester.id,
            country_id=country.id,
            status='pending',
        )
        db_session.add(car)
        db_session.commit()

        headers = _jwt_headers(app, admin.id)
        with app.test_request_context(
            '/api/mobile/v1/admin/access-requests/approve-all',
            method='POST',
            headers=headers,
        ):
            login_user(admin)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.admin.shared.user_has_permission', return_value=True), \
                 patch.object(requester.__class__, 'add_entity_permission', create=True):
                resp = approve_all_access_requests()

        body, status = _unpack(resp)
        assert status == 200
        assert body.get_json()['data']['approved_count'] >= 1

    def test_approve_all_skips_missing_user_or_country(self, app, db_session):
        """Requests with missing user or country should be skipped (not crash)."""
        from app.models.system import CountryAccessRequest
        from app.routes.api.mobile.admin_requests import approve_all_access_requests

        admin = create_test_admin(db_session, email='req-admin13@example.com')
        requester = create_test_user(db_session, email='req-user10@example.com')
        country = create_test_country(db_session)
        car = CountryAccessRequest(
            user_id=requester.id,
            country_id=country.id,
            status='pending',
        )
        db_session.add(car)
        db_session.commit()

        headers = _jwt_headers(app, admin.id)
        with app.test_request_context(
            '/api/mobile/v1/admin/access-requests/approve-all',
            method='POST',
            headers=headers,
        ):
            login_user(admin)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.admin.shared.user_has_permission', return_value=True), \
                 patch('app.models.User.query') as mock_uq:
                mock_uq.get.return_value = None
                resp = approve_all_access_requests()

        body, status = _unpack(resp)
        assert status == 200
        # approved_count should be 0 since user lookup returned None
        assert body.get_json()['data']['approved_count'] == 0

    def test_approve_all_handles_exception(self, app, db_session):
        from app.models.system import CountryAccessRequest
        from app.routes.api.mobile.admin_requests import approve_all_access_requests

        admin = create_test_admin(db_session, email='req-admin14@example.com')
        requester = create_test_user(db_session, email='req-user11@example.com')
        country = create_test_country(db_session)
        car = CountryAccessRequest(
            user_id=requester.id,
            country_id=country.id,
            status='pending',
        )
        db_session.add(car)
        db_session.commit()

        headers = _jwt_headers(app, admin.id)
        with app.test_request_context(
            '/api/mobile/v1/admin/access-requests/approve-all',
            method='POST',
            headers=headers,
        ):
            login_user(admin)
            with patch('app.utils.mobile_auth._try_jwt_auth', return_value=True), \
                 patch('app.routes.admin.shared.user_has_permission', return_value=True), \
                 patch('app.models.User.query') as mock_uq, \
                 patch('app.utils.transactions.request_transaction_rollback'):
                mock_uq.get.side_effect = RuntimeError('bulk failure')
                resp = approve_all_access_requests()

        _, status = _unpack(resp)
        assert status == 500

    def test_approve_all_no_auth_returns_401(self, app):
        client = app.test_client()
        resp = client.post('/api/mobile/v1/admin/access-requests/approve-all')
        assert resp.status_code == 401
