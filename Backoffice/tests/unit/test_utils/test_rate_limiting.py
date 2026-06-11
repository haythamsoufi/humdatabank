"""
Unit tests for app/utils/rate_limiting.py

Covers: warn_if_multi_worker_without_redis, rate_limit decorator (all branches),
        mobile_rate_limit, and factory helpers.
"""
import logging
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clear_storage():
    from app.utils.rate_limiting import _rate_limit_storage
    _rate_limit_storage.clear()


# ---------------------------------------------------------------------------
# warn_if_multi_worker_without_redis
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestWarnIfMultiWorkerWithoutRedis:
    def test_no_warning_single_worker(self, app):
        from app.utils.rate_limiting import warn_if_multi_worker_without_redis
        import app.utils.rate_limiting as rl_module
        original_concurrency = app.config.get("WEB_CONCURRENCY")
        app.config["WEB_CONCURRENCY"] = 1
        try:
            with patch.object(rl_module._rl_logger, "warning") as mock_warn:
                warn_if_multi_worker_without_redis(app)
                mock_warn.assert_not_called()
        finally:
            app.config["WEB_CONCURRENCY"] = original_concurrency

    def test_warning_multi_worker_no_redis(self, app):
        from app.utils.rate_limiting import warn_if_multi_worker_without_redis
        import app.utils.rate_limiting as rl_module
        original_concurrency = app.config.get("WEB_CONCURRENCY")
        original_redis = app.config.get("RATELIMIT_STORAGE_URI")
        original_redis2 = app.config.get("REDIS_URL")
        try:
            app.config["WEB_CONCURRENCY"] = 4
            app.config["RATELIMIT_STORAGE_URI"] = None
            app.config["REDIS_URL"] = None
            with patch.object(rl_module._rl_logger, "warning") as mock_warn:
                warn_if_multi_worker_without_redis(app)
                mock_warn.assert_called_once()
                call_args = mock_warn.call_args[0]
                assert "RATE-LIMIT WARNING" in call_args[0]
        finally:
            app.config["WEB_CONCURRENCY"] = original_concurrency
            app.config["RATELIMIT_STORAGE_URI"] = original_redis
            app.config["REDIS_URL"] = original_redis2

    def test_no_warning_multi_worker_with_ratelimit_storage(self, app):
        from app.utils.rate_limiting import warn_if_multi_worker_without_redis
        import app.utils.rate_limiting as rl_module
        original_concurrency = app.config.get("WEB_CONCURRENCY")
        original_ratelimit = app.config.get("RATELIMIT_STORAGE_URI")
        try:
            app.config["WEB_CONCURRENCY"] = 4
            app.config["RATELIMIT_STORAGE_URI"] = "redis://localhost:6379/0"
            with patch.object(rl_module._rl_logger, "warning") as mock_warn:
                warn_if_multi_worker_without_redis(app)
                mock_warn.assert_not_called()
        finally:
            app.config["WEB_CONCURRENCY"] = original_concurrency
            app.config["RATELIMIT_STORAGE_URI"] = original_ratelimit

    def test_no_warning_multi_worker_with_redis_url(self, app):
        from app.utils.rate_limiting import warn_if_multi_worker_without_redis
        import app.utils.rate_limiting as rl_module
        original_concurrency = app.config.get("WEB_CONCURRENCY")
        original_redis = app.config.get("REDIS_URL")
        original_ratelimit = app.config.get("RATELIMIT_STORAGE_URI")
        try:
            app.config["WEB_CONCURRENCY"] = 4
            app.config["REDIS_URL"] = "redis://localhost:6379/0"
            app.config["RATELIMIT_STORAGE_URI"] = None
            with patch.object(rl_module._rl_logger, "warning") as mock_warn:
                warn_if_multi_worker_without_redis(app)
                mock_warn.assert_not_called()
        finally:
            app.config["WEB_CONCURRENCY"] = original_concurrency
            app.config["REDIS_URL"] = original_redis
            app.config["RATELIMIT_STORAGE_URI"] = original_ratelimit


# ---------------------------------------------------------------------------
# rate_limit decorator
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRateLimitDecorator:
    def setup_method(self):
        _clear_storage()

    def teardown_method(self):
        _clear_storage()

    # -- Debug skip ------------------------------------------------------------

    def test_debug_skip_bypasses_limiting(self, app):
        from app.utils.rate_limiting import rate_limit
        original_skip = app.config.get("RATE_LIMIT_SKIP_DEBUG")
        app.config["DEBUG"] = True
        app.config["RATE_LIMIT_SKIP_DEBUG"] = True
        try:
            @rate_limit(requests_per_minute=1)
            def view():
                return ("ok", 200)

            with app.test_request_context("/test"):
                with patch("app.utils.rate_limiting.get_client_ip", return_value="1.2.3.4"):
                    for _ in range(5):
                        result = view()
                    assert result == ("ok", 200)
        finally:
            app.config["DEBUG"] = False
            app.config["RATE_LIMIT_SKIP_DEBUG"] = original_skip

    # -- Exempt IP -------------------------------------------------------------

    def test_exempt_ip_list_bypasses_limiting(self, app):
        from app.utils.rate_limiting import rate_limit
        original_exempt = app.config.get("RATE_LIMIT_EXEMPT_IPS")
        app.config["DEBUG"] = False
        app.config["RATE_LIMIT_EXEMPT_IPS"] = ["192.168.0.1"]
        try:
            @rate_limit(requests_per_minute=1)
            def view():
                return ("ok", 200)

            with app.test_request_context("/test"):
                with patch("app.utils.rate_limiting.get_client_ip", return_value="192.168.0.1"):
                    for _ in range(5):
                        result = view()
                    assert result == ("ok", 200)
        finally:
            app.config["RATE_LIMIT_EXEMPT_IPS"] = original_exempt

    def test_exempt_ip_string_config(self, app):
        from app.utils.rate_limiting import rate_limit
        original_exempt = app.config.get("RATE_LIMIT_EXEMPT_IPS")
        app.config["DEBUG"] = False
        app.config["RATE_LIMIT_EXEMPT_IPS"] = "10.0.0.1, 10.0.0.2"
        try:
            @rate_limit(requests_per_minute=1)
            def view():
                return ("ok", 200)

            with app.test_request_context("/test"):
                with patch("app.utils.rate_limiting.get_client_ip", return_value="10.0.0.2"):
                    result = view()
                    assert result == ("ok", 200)
        finally:
            app.config["RATE_LIMIT_EXEMPT_IPS"] = original_exempt

    # -- Method filtering -------------------------------------------------------

    def test_get_request_not_counted_when_methods_is_post_only(self, app):
        from app.utils.rate_limiting import rate_limit
        app.config["DEBUG"] = False
        @rate_limit(requests_per_minute=1, methods=["POST"])
        def view():
            return ("ok", 200)

        with app.test_request_context("/test", method="GET"):
            with patch("app.utils.rate_limiting.get_client_ip", return_value="3.3.3.3"):
                for _ in range(5):
                    result = view()
                assert result == ("ok", 200)

    # -- Rate limit exceeded: JSON response ------------------------------------

    def test_json_request_gets_429(self, app):
        from app.utils.rate_limiting import rate_limit
        app.config["DEBUG"] = False
        @rate_limit(requests_per_minute=2)
        def view():
            return ("ok", 200)

        with app.test_request_context("/test", headers={"Accept": "application/json"}):
            with patch("app.utils.rate_limiting.get_client_ip", return_value="5.5.5.5"):
                view()
                view()
                result = view()  # third call exceeds limit of 2
                assert result[1] == 429

    # -- Rate limit exceeded: web redirect with endpoint -----------------------

    def test_web_request_with_endpoint_redirects_to_path(self, app):
        from app.utils.rate_limiting import rate_limit
        app.config["DEBUG"] = False
        @rate_limit(requests_per_minute=1)
        def view():
            return ("ok", 200)

        with app.test_request_context("/the/path"):
            with patch("app.utils.rate_limiting.get_client_ip", return_value="6.6.6.6"):
                with patch("app.utils.rate_limiting.is_json_request", return_value=False):
                    with patch("app.utils.rate_limiting.request") as mock_req:
                        mock_req.method = "POST"
                        mock_req.endpoint = "some.view"
                        mock_req.path = "/the/path"
                        view()
                        result = view()  # second call exceeds limit of 1
                        assert result.status_code == 302

    # -- Rate limit exceeded: web redirect with redirect_to --------------------

    def test_web_request_with_redirect_to_uses_url_for(self, app):
        from app.utils.rate_limiting import rate_limit
        app.config["DEBUG"] = False
        @rate_limit(requests_per_minute=1, redirect_to="auth.login")
        def view():
            return ("ok", 200)

        with app.test_request_context("/test"):
            with patch("app.utils.rate_limiting.get_client_ip", return_value="7.7.7.7"):
                with patch("app.utils.rate_limiting.is_json_request", return_value=False):
                    with patch("app.utils.rate_limiting.url_for", return_value="/login") as mock_url_for:
                        view()
                        result = view()
                        mock_url_for.assert_called_with("auth.login")
                        assert result.status_code == 302

    # -- Rate limit exceeded: web redirect no endpoint fallback ----------------

    def test_web_request_no_endpoint_falls_back_to_root(self, app):
        from app.utils.rate_limiting import rate_limit
        app.config["DEBUG"] = False
        @rate_limit(requests_per_minute=1)
        def view():
            return ("ok", 200)

        with app.test_request_context("/test"):
            with patch("app.utils.rate_limiting.get_client_ip", return_value="8.8.8.8"):
                with patch("app.utils.rate_limiting.is_json_request", return_value=False):
                    with patch("app.utils.rate_limiting.request") as mock_req:
                        mock_req.method = "POST"
                        mock_req.endpoint = None
                        mock_req.path = "/test"
                        with patch("app.utils.rate_limiting.url_for", side_effect=Exception("no route")):
                            view()
                            result = view()
                            assert result.status_code == 302
                            assert result.headers["Location"] == "/"

    # -- Custom key function ---------------------------------------------------

    def test_custom_key_func(self, app):
        from app.utils.rate_limiting import rate_limit
        app.config["DEBUG"] = False
        @rate_limit(requests_per_minute=2, key_func=lambda: "fixed_key_abc")
        def view():
            return ("ok", 200)

        with app.test_request_context("/test", headers={"Accept": "application/json"}):
            with patch("app.utils.rate_limiting.get_client_ip", return_value="9.9.9.9"):
                view()
                view()
                result = view()
                assert result[1] == 429

    # -- on_limit callback returns response ------------------------------------

    def test_on_limit_returns_fallback_response(self, app):
        from app.utils.rate_limiting import rate_limit
        app.config["DEBUG"] = False
        fallback = ("stale", 200)
        @rate_limit(requests_per_minute=1, on_limit=lambda: fallback)
        def view():
            return ("ok", 200)

        with app.test_request_context("/test"):
            with patch("app.utils.rate_limiting.get_client_ip", return_value="10.0.1.1"):
                view()
                result = view()
                assert result == fallback

    # -- on_limit callback returns None falls through to 429 ------------------

    def test_on_limit_returns_none_falls_through(self, app):
        from app.utils.rate_limiting import rate_limit
        app.config["DEBUG"] = False
        @rate_limit(requests_per_minute=1, on_limit=lambda: None)
        def view():
            return ("ok", 200)

        with app.test_request_context("/test", headers={"Accept": "application/json"}):
            with patch("app.utils.rate_limiting.get_client_ip", return_value="10.0.2.2"):
                view()
                result = view()
                assert result[1] == 429

    # -- Custom flash message --------------------------------------------------

    def test_custom_flash_message_used(self, app):
        from app.utils.rate_limiting import rate_limit
        app.config["DEBUG"] = False
        @rate_limit(requests_per_minute=1, flash_message="Custom limit message")
        def view():
            return ("ok", 200)

        with app.test_request_context("/test"):
            with patch("app.utils.rate_limiting.get_client_ip", return_value="11.0.0.1"):
                with patch("app.utils.rate_limiting.is_json_request", return_value=False):
                    with patch("app.utils.rate_limiting.flash") as mock_flash:
                        with patch("app.utils.rate_limiting.request") as mock_req:
                            mock_req.method = "POST"
                            mock_req.endpoint = "view"
                            mock_req.path = "/test"
                            view()
                            view()
                            mock_flash.assert_called_once_with("Custom limit message", "warning")


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFactoryHelpers:
    def test_plugin_management_rate_limit(self):
        from app.utils.rate_limiting import plugin_management_rate_limit
        assert callable(plugin_management_rate_limit())

    def test_plugin_install_rate_limit(self):
        from app.utils.rate_limiting import plugin_install_rate_limit
        assert callable(plugin_install_rate_limit())

    def test_auth_rate_limit(self):
        from app.utils.rate_limiting import auth_rate_limit
        assert callable(auth_rate_limit())

    def test_password_reset_rate_limit(self):
        from app.utils.rate_limiting import password_reset_rate_limit
        assert callable(password_reset_rate_limit())

    def test_api_rate_limit(self):
        from app.utils.rate_limiting import api_rate_limit
        assert callable(api_rate_limit())

    def test_mobile_destructive_rate_limit(self):
        from app.utils.rate_limiting import mobile_destructive_rate_limit
        assert callable(mobile_destructive_rate_limit())


# ---------------------------------------------------------------------------
# mobile_rate_limit decorator
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMobileRateLimit:
    def setup_method(self):
        _clear_storage()

    def teardown_method(self):
        _clear_storage()

    def test_debug_skip(self, app):
        from app.utils.rate_limiting import mobile_rate_limit
        original_skip = app.config.get("RATE_LIMIT_SKIP_DEBUG")
        app.config["DEBUG"] = True
        app.config["RATE_LIMIT_SKIP_DEBUG"] = True
        try:
            @mobile_rate_limit(requests_per_minute=1)
            def view():
                return ("ok", 200)

            with app.test_request_context("/api/test"):
                with patch("app.utils.rate_limiting.get_client_ip", return_value="20.0.0.1"):
                    for _ in range(5):
                        result = view()
                    assert result == ("ok", 200)
        finally:
            app.config["DEBUG"] = False
            app.config["RATE_LIMIT_SKIP_DEBUG"] = original_skip

    def test_exempt_ip_list(self, app):
        from app.utils.rate_limiting import mobile_rate_limit, _rate_limit_storage
        _rate_limit_storage.clear()
        original_exempt = app.config.get("RATE_LIMIT_EXEMPT_IPS")
        app.config["DEBUG"] = False
        app.config["RATE_LIMIT_EXEMPT_IPS"] = ["30.0.0.1"]
        try:
            @mobile_rate_limit(requests_per_minute=1)
            def view():
                return ("ok", 200)

            with app.test_request_context("/api/test"):
                with patch("app.utils.rate_limiting.get_client_ip", return_value="30.0.0.1"):
                    for _ in range(5):
                        result = view()
                    assert result == ("ok", 200)
        finally:
            app.config["RATE_LIMIT_EXEMPT_IPS"] = original_exempt
            _rate_limit_storage.clear()

    def test_exempt_ip_string_config(self, app):
        from app.utils.rate_limiting import mobile_rate_limit, _rate_limit_storage
        _rate_limit_storage.clear()
        original_exempt = app.config.get("RATE_LIMIT_EXEMPT_IPS")
        app.config["DEBUG"] = False
        app.config["RATE_LIMIT_EXEMPT_IPS"] = "40.0.0.1, 40.0.0.2"
        try:
            @mobile_rate_limit(requests_per_minute=1)
            def view():
                return ("ok", 200)

            with app.test_request_context("/api/test"):
                with patch("app.utils.rate_limiting.get_client_ip", return_value="40.0.0.2"):
                    result = view()
                    assert result == ("ok", 200)
        finally:
            app.config["RATE_LIMIT_EXEMPT_IPS"] = original_exempt
            _rate_limit_storage.clear()

    def test_rate_limit_exceeded_returns_mobile_error(self, app):
        from app.utils.rate_limiting import mobile_rate_limit, _rate_limit_storage
        _rate_limit_storage.clear()
        app.config["DEBUG"] = False
        @mobile_rate_limit(requests_per_minute=1)
        def view():
            return ("ok", 200)

        with app.test_request_context("/api/test"):
            with patch("app.utils.rate_limiting.get_client_ip", return_value="50.0.0.1"):
                view()
                result = view()  # second call exceeds limit of 1
                # mobile_error returns a (jsonify_response, status_code) tuple
                assert result[1] == 429
        _rate_limit_storage.clear()

    def test_normal_request_passes_through(self, app):
        from app.utils.rate_limiting import mobile_rate_limit
        app.config["DEBUG"] = False
        @mobile_rate_limit(requests_per_minute=10)
        def view():
            return ("ok", 200)

        with app.test_request_context("/api/test"):
            with patch("app.utils.rate_limiting.get_client_ip", return_value="60.0.0.1"):
                result = view()
                assert result == ("ok", 200)
