"""
Unit tests for request_utils (is_json_request).
"""
import pytest

from app.utils.request_utils import is_json_request


@pytest.mark.unit
class TestIsJsonRequest:
    """Test is_json_request detection."""

    def test_accept_json(self, app):
        with app.test_request_context(
            path='/some/path',
            headers={'Accept': 'application/json'}
        ):
            assert is_json_request() is True

    def test_accept_html_not_json(self, app):
        with app.test_request_context(
            path='/some/page',
            headers={'Accept': 'text/html'}
        ):
            # Without any JSON indicators, should be False (request.is_json is False for GET)
            # request.is_json checks Content-Type, so GET with Accept: text/html -> False
            assert is_json_request() is False

    def test_content_type_json(self, app):
        with app.test_request_context(
            path='/api/foo',
            method='POST',
            headers={'Content-Type': 'application/json'},
            data='{}'
        ):
            assert is_json_request() is True

    def test_x_requested_with_xmlhttprequest(self, app):
        with app.test_request_context(
            path='/some/path',
            headers={'X-Requested-With': 'XMLHttpRequest'}
        ):
            assert is_json_request() is True

    def test_ajax_query_param(self, app):
        with app.test_request_context(
            path='/some/path?ajax=1'
        ):
            assert is_json_request() is True

    def test_admin_api_path(self, app):
        with app.test_request_context(path='/admin/api/foo'):
            assert is_json_request() is True

    def test_admin_users_api_path(self, app):
        with app.test_request_context(path='/admin/users/api/bar'):
            assert is_json_request() is True

    def test_admin_users_rbac_api_path(self, app):
        with app.test_request_context(path='/admin/users/rbac/api/baz'):
            assert is_json_request() is True

    def test_plain_html_path_no_headers(self, app):
        with app.test_request_context(path='/admin/dashboard'):
            assert is_json_request() is False
