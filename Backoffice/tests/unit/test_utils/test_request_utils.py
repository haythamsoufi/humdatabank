"""
Unit tests for request_utils (is_json_request).
"""
import pytest

from app.utils.request_utils import is_json_request, is_top_level_navigation


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

    def test_api_management_page_is_not_json(self, app):
        with app.test_request_context(path='/admin/api-management'):
            assert is_json_request() is False

    def test_api_keys_page_is_not_json(self, app):
        with app.test_request_context(path='/admin/api-keys'):
            assert is_json_request() is False

    def test_validation_dashboard_api_subpath_is_json(self, app):
        with app.test_request_context(path='/admin/validation-dashboard/api/periods'):
            assert is_json_request() is True


class TestIsTopLevelNavigation:
    """Guards the CSRF-free GET context switch on the dashboard/documents pages."""

    def test_no_sec_fetch_headers_is_treated_as_navigation(self, app):
        with app.test_request_context(path='/'):
            assert is_top_level_navigation() is True

    def test_form_get_submission(self, app):
        with app.test_request_context(path='/', headers={
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Dest': 'document',
        }):
            assert is_top_level_navigation() is True

    def test_typed_url_has_no_site(self, app):
        with app.test_request_context(path='/', headers={
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Dest': 'document',
        }):
            assert is_top_level_navigation() is True

    def test_cross_site_top_level_link(self, app):
        with app.test_request_context(path='/', headers={
            'Sec-Fetch-Site': 'cross-site',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Dest': 'document',
        }):
            assert is_top_level_navigation() is False

    def test_sibling_site_navigation(self, app):
        with app.test_request_context(path='/', headers={
            'Sec-Fetch-Site': 'same-site',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Dest': 'document',
        }):
            assert is_top_level_navigation() is False

    def test_cross_site_image_load(self, app):
        with app.test_request_context(path='/', headers={
            'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Dest': 'image',
            'Sec-Fetch-Site': 'cross-site',
        }):
            assert is_top_level_navigation() is False

    def test_iframe_embed(self, app):
        with app.test_request_context(path='/', headers={
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Dest': 'iframe',
        }):
            assert is_top_level_navigation() is False

    def test_speculative_prefetch(self, app):
        with app.test_request_context(path='/', headers={
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Dest': 'document',
            'Sec-Purpose': 'prefetch;anonymous-client-ip',
        }):
            assert is_top_level_navigation() is False
