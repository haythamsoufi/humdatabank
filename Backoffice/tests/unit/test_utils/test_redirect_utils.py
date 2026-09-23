"""
Unit tests for app/utils/redirect_utils.py

Covers: get_current_relative_url, _is_same_origin_netloc,
        is_safe_redirect_url, get_safe_redirect_url, safe_redirect
"""
import pytest
from unittest.mock import patch


@pytest.mark.unit
class TestGetCurrentRelativeUrl:
    def test_plain_path(self, app):
        from app.utils.redirect_utils import get_current_relative_url
        with app.test_request_context("/admin/dashboard"):
            assert get_current_relative_url() == "/admin/dashboard"

    def test_path_with_query_string(self, app):
        from app.utils.redirect_utils import get_current_relative_url
        with app.test_request_context("/admin/users?page=2&sort=name"):
            result = get_current_relative_url()
            assert result == "/admin/users?page=2&sort=name"

    def test_path_without_query_string(self, app):
        from app.utils.redirect_utils import get_current_relative_url
        with app.test_request_context("/login"):
            assert get_current_relative_url() == "/login"

    def test_root_path(self, app):
        from app.utils.redirect_utils import get_current_relative_url
        with app.test_request_context("/"):
            assert get_current_relative_url() == "/"


@pytest.mark.unit
class TestIsSameOriginNetloc:
    def test_empty_netloc_returns_false(self, app):
        from app.utils.redirect_utils import _is_same_origin_netloc
        with app.test_request_context("/", base_url="http://example.com"):
            assert _is_same_origin_netloc("") is False

    def test_matching_host(self, app):
        from app.utils.redirect_utils import _is_same_origin_netloc
        with app.test_request_context("/", base_url="http://example.com"):
            assert _is_same_origin_netloc("example.com") is True

    def test_different_host_returns_false(self, app):
        from app.utils.redirect_utils import _is_same_origin_netloc
        with app.test_request_context("/", base_url="http://example.com"):
            assert _is_same_origin_netloc("evil.com") is False

    def test_server_name_config_match(self, app):
        from app.utils.redirect_utils import _is_same_origin_netloc
        original = app.config.get("SERVER_NAME")
        try:
            app.config["SERVER_NAME"] = "myapp.example.com"
            with app.test_request_context("/", base_url="http://myapp.example.com"):
                assert _is_same_origin_netloc("myapp.example.com") is True
        finally:
            # Restore to original value; always keep the key present in config
            app.config["SERVER_NAME"] = original

    def test_localhost_same_port_is_same_origin(self, app):
        from app.utils.redirect_utils import _is_same_origin_netloc
        with app.test_request_context("/", base_url="http://localhost:5000"):
            assert _is_same_origin_netloc("127.0.0.1:5000") is True

    def test_localhost_different_port_is_not_same_origin(self, app):
        from app.utils.redirect_utils import _is_same_origin_netloc
        with app.test_request_context("/", base_url="http://localhost:5000"):
            assert _is_same_origin_netloc("localhost:9999") is False

    def test_ipv6_localhost_same_port(self, app):
        from app.utils.redirect_utils import _is_same_origin_netloc
        with app.test_request_context("/", base_url="http://localhost:5000"):
            assert _is_same_origin_netloc("[::1]:5000") is True

    def test_host_without_port_vs_host_with_port(self, app):
        from app.utils.redirect_utils import _is_same_origin_netloc
        with app.test_request_context("/", base_url="http://example.com"):
            # example.com vs example.com:443 are different netlocs
            assert _is_same_origin_netloc("example.com:443") is False


@pytest.mark.unit
class TestIsSafeRedirectUrl:
    def test_none_is_unsafe(self, app):
        from app.utils.redirect_utils import is_safe_redirect_url
        with app.test_request_context("/"):
            assert is_safe_redirect_url(None) is False

    def test_empty_string_is_unsafe(self, app):
        from app.utils.redirect_utils import is_safe_redirect_url
        with app.test_request_context("/"):
            assert is_safe_redirect_url("") is False

    def test_non_string_is_unsafe(self, app):
        from app.utils.redirect_utils import is_safe_redirect_url
        with app.test_request_context("/"):
            assert is_safe_redirect_url(123) is False

    def test_relative_path_is_safe(self, app):
        from app.utils.redirect_utils import is_safe_redirect_url
        with app.test_request_context("/"):
            assert is_safe_redirect_url("/admin/dashboard") is True

    def test_relative_with_query_is_safe(self, app):
        from app.utils.redirect_utils import is_safe_redirect_url
        with app.test_request_context("/"):
            assert is_safe_redirect_url("/search?q=test") is True

    def test_protocol_relative_is_unsafe(self, app):
        from app.utils.redirect_utils import is_safe_redirect_url
        with app.test_request_context("/"):
            assert is_safe_redirect_url("//evil.com") is False

    def test_javascript_scheme_is_unsafe(self, app):
        from app.utils.redirect_utils import is_safe_redirect_url
        with app.test_request_context("/"):
            assert is_safe_redirect_url("javascript:alert(1)") is False

    def test_data_scheme_is_unsafe(self, app):
        from app.utils.redirect_utils import is_safe_redirect_url
        with app.test_request_context("/"):
            assert is_safe_redirect_url("data:text/html,<h1>hi</h1>") is False

    def test_null_byte_is_unsafe(self, app):
        from app.utils.redirect_utils import is_safe_redirect_url
        with app.test_request_context("/"):
            assert is_safe_redirect_url("/path\x00with_null") is False

    def test_newline_in_url_is_unsafe(self, app):
        from app.utils.redirect_utils import is_safe_redirect_url
        with app.test_request_context("/"):
            assert is_safe_redirect_url("/path\ninjected") is False

    def test_carriage_return_in_url_is_unsafe(self, app):
        from app.utils.redirect_utils import is_safe_redirect_url
        with app.test_request_context("/"):
            assert is_safe_redirect_url("/path\rinjected") is False

    def test_del_character_in_url_is_unsafe(self, app):
        from app.utils.redirect_utils import is_safe_redirect_url
        with app.test_request_context("/"):
            assert is_safe_redirect_url("/path\x7finjected") is False

    def test_whitespace_only_is_unsafe(self, app):
        from app.utils.redirect_utils import is_safe_redirect_url
        with app.test_request_context("/"):
            assert is_safe_redirect_url("   ") is False

    def test_absolute_same_origin_is_safe(self, app):
        from app.utils.redirect_utils import is_safe_redirect_url
        with app.test_request_context("/", base_url="http://localhost:5000"):
            assert is_safe_redirect_url("http://localhost:5000/admin") is True

    def test_absolute_external_is_unsafe(self, app):
        from app.utils.redirect_utils import is_safe_redirect_url
        with app.test_request_context("/", base_url="http://localhost:5000"):
            assert is_safe_redirect_url("http://evil.com/steal") is False

    def test_relative_without_leading_slash_is_unsafe(self, app):
        from app.utils.redirect_utils import is_safe_redirect_url
        with app.test_request_context("/"):
            assert is_safe_redirect_url("admin/page") is False

    def test_ftp_scheme_with_netloc_is_unsafe(self, app):
        from app.utils.redirect_utils import is_safe_redirect_url
        with app.test_request_context("/"):
            assert is_safe_redirect_url("ftp://localhost/path") is False

    def test_double_slash_in_path_logs_but_still_safe(self, app):
        from app.utils.redirect_utils import is_safe_redirect_url
        with app.test_request_context("/"):
            # Double slashes inside a path are suspicious but not blocked
            result = is_safe_redirect_url("/path//double")
            assert result is True

    def test_absolute_same_origin_https_is_safe(self, app):
        from app.utils.redirect_utils import is_safe_redirect_url
        with app.test_request_context("/", base_url="https://example.com"):
            with patch("app.utils.redirect_utils._is_same_origin_netloc", return_value=True):
                assert is_safe_redirect_url("https://example.com/page") is True

    def test_absolute_no_netloc_is_unsafe(self, app):
        from app.utils.redirect_utils import is_safe_redirect_url
        with app.test_request_context("/"):
            # A string like "localhost:5000/path" parses without scheme -> no netloc
            assert is_safe_redirect_url("localhost:5000/path") is False


@pytest.mark.unit
class TestGetSafeRedirectUrl:
    def test_safe_url_returned_as_is(self, app):
        from app.utils.redirect_utils import get_safe_redirect_url
        with app.test_request_context("/"):
            result = get_safe_redirect_url("/admin/dashboard")
            assert result == "/admin/dashboard"

    def test_unsafe_url_returns_default_route(self, app):
        from app.utils.redirect_utils import get_safe_redirect_url
        with app.test_request_context("/"):
            with patch("app.utils.redirect_utils.url_for", return_value="/dashboard") as mock_url_for:
                result = get_safe_redirect_url("http://evil.com")
                mock_url_for.assert_called_once_with("main.dashboard")
                assert result == "/dashboard"

    def test_none_target_returns_default_route(self, app):
        from app.utils.redirect_utils import get_safe_redirect_url
        with app.test_request_context("/"):
            with patch("app.utils.redirect_utils.url_for", return_value="/dashboard"):
                result = get_safe_redirect_url(None)
                assert result == "/dashboard"

    def test_custom_default_route_used(self, app):
        from app.utils.redirect_utils import get_safe_redirect_url
        with app.test_request_context("/"):
            with patch("app.utils.redirect_utils.url_for", return_value="/login") as mock_url_for:
                result = get_safe_redirect_url(None, default_route="auth.login")
                mock_url_for.assert_called_once_with("auth.login")
                assert result == "/login"

    def test_empty_target_returns_default(self, app):
        from app.utils.redirect_utils import get_safe_redirect_url
        with app.test_request_context("/"):
            with patch("app.utils.redirect_utils.url_for", return_value="/dashboard"):
                result = get_safe_redirect_url("")
                assert result == "/dashboard"


@pytest.mark.unit
class TestSafeRedirect:
    def test_safe_url_creates_redirect_response(self, app):
        from app.utils.redirect_utils import safe_redirect
        with app.test_request_context("/"):
            response = safe_redirect("/admin/dashboard")
            assert response.status_code == 302
            assert "/admin/dashboard" in response.headers.get("Location", "")

    def test_unsafe_url_redirects_to_default(self, app):
        from app.utils.redirect_utils import safe_redirect
        with app.test_request_context("/"):
            with patch("app.utils.redirect_utils.url_for", return_value="/dashboard"):
                response = safe_redirect("http://evil.com")
                assert response.status_code == 302
                assert "/dashboard" in response.headers.get("Location", "")

    def test_none_target_redirects_to_default(self, app):
        from app.utils.redirect_utils import safe_redirect
        with app.test_request_context("/"):
            with patch("app.utils.redirect_utils.url_for", return_value="/dashboard"):
                response = safe_redirect(None)
                assert response.status_code == 302

    def test_custom_default_route(self, app):
        from app.utils.redirect_utils import safe_redirect
        with app.test_request_context("/"):
            with patch("app.utils.redirect_utils.url_for", return_value="/login") as mock_url_for:
                response = safe_redirect(None, default_route="auth.login")
                mock_url_for.assert_called_once_with("auth.login")
                assert response.status_code == 302
