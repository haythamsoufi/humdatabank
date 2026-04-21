"""Unit tests for app.utils.mobile_responses — no database required."""
import pytest
import json


@pytest.mark.unit
class TestMobileOk:
    def test_bare_call(self, app):
        with app.test_request_context():
            from app.utils.mobile_responses import mobile_ok
            resp, status = mobile_ok()
            assert status == 200
            body = json.loads(resp.get_data())
            assert body == {'success': True}

    def test_with_data_dict(self, app):
        with app.test_request_context():
            from app.utils.mobile_responses import mobile_ok
            resp, status = mobile_ok(data={'foo': 'bar'})
            body = json.loads(resp.get_data())
            assert body['success'] is True
            assert body['data'] == {'foo': 'bar'}

    def test_with_data_list(self, app):
        with app.test_request_context():
            from app.utils.mobile_responses import mobile_ok
            resp, status = mobile_ok(data=[1, 2, 3])
            body = json.loads(resp.get_data())
            assert body['data'] == [1, 2, 3]

    def test_with_message(self, app):
        with app.test_request_context():
            from app.utils.mobile_responses import mobile_ok
            resp, status = mobile_ok(message='Done')
            body = json.loads(resp.get_data())
            assert body['message'] == 'Done'
            assert body['success'] is True

    def test_with_meta(self, app):
        with app.test_request_context():
            from app.utils.mobile_responses import mobile_ok
            resp, status = mobile_ok(meta={'page': 1})
            body = json.loads(resp.get_data())
            assert body['meta'] == {'page': 1}

    def test_extra_kwargs_merged(self, app):
        with app.test_request_context():
            from app.utils.mobile_responses import mobile_ok
            resp, status = mobile_ok(requires_reauth=True)
            body = json.loads(resp.get_data())
            assert body['requires_reauth'] is True
            assert body['success'] is True


@pytest.mark.unit
class TestMobileCreated:
    def test_returns_201(self, app):
        with app.test_request_context():
            from app.utils.mobile_responses import mobile_created
            resp, status = mobile_created(data={'id': 42})
            assert status == 201
            body = json.loads(resp.get_data())
            assert body['success'] is True
            assert body['data'] == {'id': 42}


@pytest.mark.unit
class TestMobilePaginated:
    def test_envelope(self, app):
        with app.test_request_context():
            from app.utils.mobile_responses import mobile_paginated
            resp, status = mobile_paginated(items=['a', 'b'], total=10, page=1, per_page=5)
            assert status == 200
            body = json.loads(resp.get_data())
            assert body['success'] is True
            assert body['data'] == ['a', 'b']
            assert body['meta']['total'] == 10
            assert body['meta']['page'] == 1
            assert body['meta']['per_page'] == 5
            assert body['meta']['total_pages'] == 2

    def test_ceiling_division(self, app):
        with app.test_request_context():
            from app.utils.mobile_responses import mobile_paginated
            resp, _ = mobile_paginated(items=[], total=7, page=1, per_page=3)
            body = json.loads(resp.get_data())
            assert body['meta']['total_pages'] == 3  # ceil(7/3)


@pytest.mark.unit
class TestMobileError:
    def test_default_400(self, app):
        with app.test_request_context():
            from app.utils.mobile_responses import mobile_error
            resp, status = mobile_error('bad input')
            assert status == 400
            body = json.loads(resp.get_data())
            assert body['success'] is False
            assert body['error'] == 'bad input'
            assert 'error_code' not in body

    def test_custom_status_and_code(self, app):
        with app.test_request_context():
            from app.utils.mobile_responses import mobile_error
            resp, status = mobile_error('conflict', 409, error_code='CONFLICT')
            assert status == 409
            body = json.loads(resp.get_data())
            assert body['error_code'] == 'CONFLICT'

    def test_extra_kwargs(self, app):
        with app.test_request_context():
            from app.utils.mobile_responses import mobile_error
            resp, status = mobile_error('err', retry_after=60)
            body = json.loads(resp.get_data())
            assert body['retry_after'] == 60


@pytest.mark.unit
class TestConvenienceWrappers:
    def test_bad_request(self, app):
        with app.test_request_context():
            from app.utils.mobile_responses import mobile_bad_request
            _, status = mobile_bad_request()
            assert status == 400

    def test_auth_error(self, app):
        with app.test_request_context():
            from app.utils.mobile_responses import mobile_auth_error
            resp, status = mobile_auth_error()
            assert status == 401
            body = json.loads(resp.get_data())
            assert body['error_code'] == 'AUTH_REQUIRED'

    def test_forbidden(self, app):
        with app.test_request_context():
            from app.utils.mobile_responses import mobile_forbidden
            resp, status = mobile_forbidden()
            assert status == 403
            body = json.loads(resp.get_data())
            assert body['error_code'] == 'FORBIDDEN'

    def test_not_found(self, app):
        with app.test_request_context():
            from app.utils.mobile_responses import mobile_not_found
            resp, status = mobile_not_found()
            assert status == 404
            body = json.loads(resp.get_data())
            assert body['error_code'] == 'NOT_FOUND'

    def test_server_error(self, app):
        with app.test_request_context():
            from app.utils.mobile_responses import mobile_server_error
            resp, status = mobile_server_error()
            assert status == 500
            body = json.loads(resp.get_data())
            assert body['error_code'] == 'SERVER_ERROR'
