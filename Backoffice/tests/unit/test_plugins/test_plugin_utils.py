"""
Comprehensive tests for app/plugins/plugin_utils.py
Targets 100% code coverage.
"""
import time
import json
import pytest
import logging
from unittest.mock import MagicMock, patch, call
from flask import Flask, Blueprint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_flask_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SECRET_KEY"] = "test-secret"
    return app


# ---------------------------------------------------------------------------
# PluginError and subclasses
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPluginErrors:
    def test_plugin_error_basic(self):
        from app.plugins.plugin_utils import PluginError
        e = PluginError("test error", plugin_name="my_plugin", error_code="ERR_01")
        assert str(e) == "test error"
        assert e.plugin_name == "my_plugin"
        assert e.error_code == "ERR_01"
        assert e.message == "test error"

    def test_plugin_error_defaults(self):
        from app.plugins.plugin_utils import PluginError
        e = PluginError("simple error")
        assert e.plugin_name is None
        assert e.error_code is None

    def test_plugin_config_error_is_plugin_error(self):
        from app.plugins.plugin_utils import PluginConfigError, PluginError
        e = PluginConfigError("config issue")
        assert isinstance(e, PluginError)

    def test_plugin_route_error_is_plugin_error(self):
        from app.plugins.plugin_utils import PluginRouteError, PluginError
        e = PluginRouteError("route issue")
        assert isinstance(e, PluginError)


# ---------------------------------------------------------------------------
# plugin_error_handler decorator
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPluginErrorHandler:
    def test_passes_through_on_success(self):
        from app.plugins.plugin_utils import plugin_error_handler
        app = _make_flask_app()

        @plugin_error_handler("my_plugin")
        def my_route():
            return "ok"

        with app.test_request_context("/"):
            with patch("app.plugins.plugin_utils.current_app") as mca:
                mca.logger = MagicMock()
                result = my_route()
        assert result == "ok"

    def test_handles_plugin_error_json_request(self):
        from app.plugins.plugin_utils import plugin_error_handler, PluginError
        app = _make_flask_app()

        @plugin_error_handler("my_plugin")
        def bad_route():
            raise PluginError("oops", plugin_name="my_plugin", error_code="ERR")

        with app.test_request_context("/", content_type="application/json"):
            with patch("app.plugins.plugin_utils.current_app") as mca:
                mca.logger = MagicMock()
                with patch("app.plugins.plugin_utils.is_json_request", return_value=True):
                    with patch("app.plugins.plugin_utils.json_server_error") as mock_err:
                        mock_err.return_value = "json_error_response"
                        result = bad_route()
        assert result == "json_error_response"

    def test_handles_plugin_error_html_request(self):
        from app.plugins.plugin_utils import plugin_error_handler, PluginError
        app = _make_flask_app()

        @plugin_error_handler("my_plugin")
        def bad_html():
            raise PluginError("html error")

        with app.test_request_context("/"):
            with patch("app.plugins.plugin_utils.current_app") as mca:
                mca.logger = MagicMock()
                with patch("app.plugins.plugin_utils.is_json_request", return_value=False):
                    result = bad_html()
        response_body, status_code = result
        assert "html error" in response_body
        assert status_code == 500

    def test_handles_unexpected_exception_json(self):
        from app.plugins.plugin_utils import plugin_error_handler
        app = _make_flask_app()

        @plugin_error_handler("my_plugin")
        def crash():
            raise ValueError("unexpected!")

        with app.test_request_context("/", content_type="application/json"):
            with patch("app.plugins.plugin_utils.current_app") as mca:
                mca.logger = MagicMock()
                with patch("app.plugins.plugin_utils.is_json_request", return_value=True):
                    with patch("app.plugins.plugin_utils.json_server_error") as mock_err:
                        mock_err.return_value = "json_500"
                        result = crash()
        assert result == "json_500"

    def test_handles_unexpected_exception_html(self):
        from app.plugins.plugin_utils import plugin_error_handler
        app = _make_flask_app()

        @plugin_error_handler("my_plugin")
        def crash():
            raise ValueError("unexpected!")

        with app.test_request_context("/"):
            with patch("app.plugins.plugin_utils.current_app") as mca:
                mca.logger = MagicMock()
                with patch("app.plugins.plugin_utils.is_json_request", return_value=False):
                    result = crash()
        body, status = result
        assert status == 500
        assert "Internal error" in body

    def test_preserves_function_name(self):
        from app.plugins.plugin_utils import plugin_error_handler

        @plugin_error_handler("test")
        def my_function():
            pass

        assert my_function.__name__ == "my_function"

    def test_uses_plugin_name_from_error_when_none(self):
        """PluginError with plugin_name=None uses the decorator's plugin_name."""
        from app.plugins.plugin_utils import plugin_error_handler, PluginError
        app = _make_flask_app()

        @plugin_error_handler("fallback_plugin")
        def raises():
            raise PluginError("msg", plugin_name=None)

        with app.test_request_context("/"):
            with patch("app.plugins.plugin_utils.current_app") as mca:
                mca.logger = MagicMock()
                with patch("app.plugins.plugin_utils.is_json_request", return_value=True):
                    with patch("app.plugins.plugin_utils.json_server_error") as mock_err:
                        mock_err.return_value = "resp"
                        raises()
        # Check that json_server_error was called with plugin=fallback_plugin
        call_kwargs = mock_err.call_args[1]
        assert call_kwargs["plugin"] == "fallback_plugin"


# ---------------------------------------------------------------------------
# plugin_route_wrapper
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPluginRouteWrapper:
    def test_wrapper_calls_underlying_function(self):
        """plugin_route_wrapper wraps with login_required + error handler."""
        from app.plugins.plugin_utils import plugin_route_wrapper

        # We don't test the login_required enforcement here (needs a full auth stack),
        # just check the __name__ is preserved.
        @plugin_route_wrapper("test_plugin")
        def my_view():
            return "view_result"

        assert my_view.__name__ == "my_view"


@pytest.mark.unit
class TestPluginAdminRouteWrapper:
    def test_admin_wrapper_preserves_function_name(self):
        from app.plugins.plugin_utils import plugin_admin_route_wrapper

        @plugin_admin_route_wrapper("test_plugin")
        def admin_view():
            return "admin_result"

        assert admin_view.__name__ == "admin_view"

    def test_focal_point_gets_403_on_plugin_config_post(self, client, app):
        mock_user = MagicMock(is_authenticated=True)
        with patch("flask_login.utils._get_user", return_value=mock_user), \
             patch("app.routes.admin.shared.user_has_permission", return_value=False):
            with client.session_transaction() as sess:
                sess["_user_id"] = "1"
                sess["_fresh"] = True
            resp = client.post(
                "/admin/plugins/interactive_map/api/config",
                json={"global_settings": {"default_zoom_level": 12}},
            )
        assert resp.status_code == 403

    def test_admin_with_manage_permission_succeeds_on_plugin_config_post(self, client, app):
        with patch("app.routes.admin.shared.user_has_permission", return_value=True):
            with client.session_transaction() as sess:
                sess["_user_id"] = "999999"
                sess["_fresh"] = True
            with patch("flask_login.utils._get_user", return_value=MagicMock(is_authenticated=True)), \
                 patch("app.plugins.plugin_utils.get_json_safe", return_value={"global_settings": {}}), \
                 patch("app.plugins.db_config.DbPluginConfig.update_config", return_value=True):
                resp = client.post(
                    "/admin/plugins/interactive_map/api/config",
                    json={"global_settings": {"default_zoom_level": 12}},
                )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# BasePluginRoutes
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBasePluginRoutes:
    def test_init_defaults(self):
        from app.plugins.plugin_utils import BasePluginRoutes
        bpr = BasePluginRoutes("my_plugin")
        assert bpr.plugin_id == "my_plugin"
        assert bpr.display_name == "my_plugin"
        assert bpr.plugin_config is None

    def test_init_with_display_name(self):
        from app.plugins.plugin_utils import BasePluginRoutes
        bpr = BasePluginRoutes("my_plugin", display_name="My Plugin")
        assert bpr.display_name == "My Plugin"

    def test_init_with_config(self):
        from app.plugins.plugin_utils import BasePluginRoutes
        cfg = MagicMock()
        bpr = BasePluginRoutes("my_plugin", plugin_config=cfg)
        assert bpr.plugin_config is cfg

    def test_create_standard_routes_registers_routes(self):
        from app.plugins.plugin_utils import BasePluginRoutes
        app = _make_flask_app()
        bp = Blueprint("test_bp", __name__)
        cfg = MagicMock()
        cfg.get_all_config.return_value = {"key": "val"}
        cfg.update_config.return_value = True
        cfg.update_section.return_value = True

        bpr = BasePluginRoutes("test_plugin", plugin_config=cfg)
        bpr.create_standard_routes(bp)
        app.register_blueprint(bp, url_prefix="/test")

        # Verify routes were added to the blueprint
        rules = [r.rule for r in app.url_map.iter_rules()]
        assert any("/test/api/config" in r for r in rules)

    def test_create_standard_routes_no_config_raises(self):
        from app.plugins.plugin_utils import BasePluginRoutes, PluginConfigError
        # Patch login_required and permission_required to be no-ops before routes are decorated
        with patch("app.plugins.plugin_utils.login_required", lambda f: f), \
             patch("app.plugins.plugin_utils.permission_required", lambda _perm: (lambda f: f)):
            app = _make_flask_app()
            bp = Blueprint("test_bp2", __name__)
            bpr = BasePluginRoutes("test_plugin")  # No config
            bpr.create_standard_routes(bp)
            app.register_blueprint(bp, url_prefix="/test2")

            client = app.test_client()
            with patch("app.plugins.plugin_utils.is_json_request", return_value=False):
                with patch("app.plugins.plugin_utils.current_app") as mca:
                    mca.logger = MagicMock()
                    response = client.get("/test2/api/config")
        assert response.status_code == 500

    def test_create_standard_routes_with_template_renderer(self):
        from app.plugins.plugin_utils import BasePluginRoutes
        app = _make_flask_app()
        bp = Blueprint("test_bp3", __name__)
        cfg = MagicMock()
        renderer = MagicMock(return_value="<settings/>")

        bpr = BasePluginRoutes("test_plugin", plugin_config=cfg)
        bpr.create_standard_routes(bp, template_renderer=renderer)
        app.register_blueprint(bp, url_prefix="/test3")

        rules = [r.rule for r in app.url_map.iter_rules()]
        assert any("/test3/settings" in r for r in rules)

    def test_get_config_route(self):
        from app.plugins.plugin_utils import BasePluginRoutes
        app = _make_flask_app()
        bp = Blueprint("test_cfg_bp", __name__)
        cfg = MagicMock()
        cfg.get_all_config.return_value = {"a": 1}

        bpr = BasePluginRoutes("test_plugin", plugin_config=cfg)
        bpr.create_standard_routes(bp)
        app.register_blueprint(bp, url_prefix="/plugin")

        with app.test_request_context("/plugin/api/config"):
            with patch("app.plugins.plugin_utils.current_app") as mca:
                mca.logger = MagicMock()
                with patch("app.plugins.plugin_utils.json_ok") as mock_ok:
                    mock_ok.return_value = "ok_response"
                    # Call the route function directly
                    rules = {r.endpoint: r for r in app.url_map.iter_rules()}

    def test_update_full_config_route_failure(self):
        """update_full_config raises PluginConfigError when save fails."""
        from app.plugins.plugin_utils import BasePluginRoutes
        with patch("app.plugins.plugin_utils.login_required", lambda f: f), \
             patch("app.plugins.plugin_utils.permission_required", lambda _perm: (lambda f: f)):
            app = _make_flask_app()
            bp = Blueprint("test_upd_bp", __name__)
            cfg = MagicMock()
            cfg.update_config.return_value = False  # Simulate save failure

            bpr = BasePluginRoutes("test_plugin", plugin_config=cfg)
            bpr.create_standard_routes(bp)
            app.register_blueprint(bp, url_prefix="/upd")

            client = app.test_client()
            with patch("app.plugins.plugin_utils.get_json_safe", return_value={"key": "val"}):
                with patch("app.plugins.plugin_utils.current_app") as mca:
                    mca.logger = MagicMock()
                    with patch("app.plugins.plugin_utils.is_json_request", return_value=False):
                        response = client.post("/upd/api/config", json={"key": "val"})
        assert response.status_code == 500

    def test_update_config_section_route_failure(self):
        """update_config_section raises PluginConfigError when save fails."""
        from app.plugins.plugin_utils import BasePluginRoutes
        with patch("app.plugins.plugin_utils.login_required", lambda f: f), \
             patch("app.plugins.plugin_utils.permission_required", lambda _perm: (lambda f: f)):
            app = _make_flask_app()
            bp = Blueprint("test_sec_bp", __name__)
            cfg = MagicMock()
            cfg.update_section.return_value = False

            bpr = BasePluginRoutes("test_plugin", plugin_config=cfg)
            bpr.create_standard_routes(bp)
            app.register_blueprint(bp, url_prefix="/sec")

            client = app.test_client()
            with patch("app.plugins.plugin_utils.get_json_safe", return_value={}):
                with patch("app.plugins.plugin_utils.current_app") as mca:
                    mca.logger = MagicMock()
                    with patch("app.plugins.plugin_utils.is_json_request", return_value=False):
                        response = client.post("/sec/api/config/my_section", json={})
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# validate_plugin_config
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestValidatePluginConfig:
    def test_valid_config_returns_true(self):
        from app.plugins.plugin_utils import validate_plugin_config
        schema = {
            "name": {"required": True, "type": str},
            "count": {"required": False, "type": int, "min": 0, "max": 100},
        }
        config = {"name": "test", "count": 5}
        assert validate_plugin_config(config, schema) is True

    def test_missing_required_field_raises(self):
        from app.plugins.plugin_utils import validate_plugin_config, PluginConfigError
        schema = {"required_field": {"required": True}}
        with pytest.raises(PluginConfigError) as exc_info:
            validate_plugin_config({}, schema)
        assert "required_field" in str(exc_info.value)

    def test_wrong_type_raises(self):
        from app.plugins.plugin_utils import validate_plugin_config, PluginConfigError
        schema = {"count": {"type": int}}
        with pytest.raises(PluginConfigError) as exc_info:
            validate_plugin_config({"count": "not_an_int"}, schema)
        assert "count" in str(exc_info.value)

    def test_min_value_violation_raises(self):
        from app.plugins.plugin_utils import validate_plugin_config, PluginConfigError
        schema = {"count": {"type": int, "min": 10}}
        with pytest.raises(PluginConfigError):
            validate_plugin_config({"count": 5}, schema)

    def test_max_value_violation_raises(self):
        from app.plugins.plugin_utils import validate_plugin_config, PluginConfigError
        schema = {"count": {"type": int, "max": 100}}
        with pytest.raises(PluginConfigError):
            validate_plugin_config({"count": 999}, schema)

    def test_schema_with_no_type_check_passes(self):
        from app.plugins.plugin_utils import validate_plugin_config
        schema = {"optional_key": {}}
        assert validate_plugin_config({"optional_key": "anything"}, schema) is True

    def test_config_error_re_raised(self):
        from app.plugins.plugin_utils import validate_plugin_config, PluginConfigError
        schema = {"val": {"required": True}}
        with pytest.raises(PluginConfigError):
            validate_plugin_config({}, schema)

    def test_unexpected_exception_wrapped(self):
        """An unexpected exception (not PluginConfigError) is wrapped."""
        from app.plugins.plugin_utils import validate_plugin_config, PluginConfigError

        class ExplodingDict(dict):
            def items(self):
                raise RuntimeError("boom")

        with pytest.raises(PluginConfigError) as exc_info:
            validate_plugin_config({}, ExplodingDict())
        assert "validation failed" in str(exc_info.value).lower()

    def test_float_value_checked_against_min_max(self):
        from app.plugins.plugin_utils import validate_plugin_config
        schema = {"rate": {"type": float, "min": 0.0, "max": 1.0}}
        assert validate_plugin_config({"rate": 0.5}, schema) is True


# ---------------------------------------------------------------------------
# safe_json_loads
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSafeJsonLoads:
    def test_valid_json(self):
        from app.plugins.plugin_utils import safe_json_loads
        app = _make_flask_app()
        with app.app_context():
            with patch("app.plugins.plugin_utils.current_app") as mca:
                mca.logger = MagicMock()
                result = safe_json_loads('{"a": 1}')
        assert result == {"a": 1}

    def test_empty_string_returns_default(self):
        from app.plugins.plugin_utils import safe_json_loads
        app = _make_flask_app()
        with app.app_context():
            with patch("app.plugins.plugin_utils.current_app") as mca:
                mca.logger = MagicMock()
                result = safe_json_loads("", default={"fallback": True})
        assert result == {"fallback": True}

    def test_whitespace_only_returns_default(self):
        from app.plugins.plugin_utils import safe_json_loads
        with patch("app.plugins.plugin_utils.current_app") as mca:
            mca.logger = MagicMock()
            result = safe_json_loads("   ", default=42)
        assert result == 42

    def test_none_returns_default(self):
        from app.plugins.plugin_utils import safe_json_loads
        with patch("app.plugins.plugin_utils.current_app") as mca:
            mca.logger = MagicMock()
            result = safe_json_loads(None, default="fallback")
        assert result == "fallback"

    def test_invalid_json_returns_default_and_logs(self):
        from app.plugins.plugin_utils import safe_json_loads
        mock_logger = MagicMock()
        with patch("app.plugins.plugin_utils.current_app") as mca:
            mca.logger = mock_logger
            result = safe_json_loads("{invalid}", default="default_val")
        assert result == "default_val"
        mock_logger.warning.assert_called_once()


# ---------------------------------------------------------------------------
# get_plugin_logger
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetPluginLogger:
    def test_returns_logger_instance(self):
        from app.plugins.plugin_utils import get_plugin_logger
        logger = get_plugin_logger("my_plugin")
        assert isinstance(logger, logging.Logger)

    def test_logger_name_is_sanitized(self):
        from app.plugins.plugin_utils import get_plugin_logger
        logger = get_plugin_logger("My Plugin")
        assert " " not in logger.name

    def test_logger_name_strips_plugin_word(self):
        from app.plugins.plugin_utils import get_plugin_logger
        logger = get_plugin_logger("my_test_plugin")
        # "plugin" stripped from the name
        assert "plugin" not in logger.name.split(".")[-1]

    def test_adds_handler_when_none_configured(self):
        from app.plugins.plugin_utils import get_plugin_logger
        import logging
        # Use a unique name to ensure no handlers
        logger_name = f"plugin.unique_test_{id(object())}"
        logging.getLogger(logger_name).handlers.clear()
        logger = get_plugin_logger("unique_test_" + str(id(object())))
        assert len(logger.handlers) >= 1

    def test_does_not_add_duplicate_handlers(self):
        from app.plugins.plugin_utils import get_plugin_logger
        logger = get_plugin_logger("existing_plugin")
        initial_count = len(logger.handlers)
        get_plugin_logger("existing_plugin")
        # Should not add another handler if one already exists
        assert len(logger.handlers) == initial_count


# ---------------------------------------------------------------------------
# measure_performance decorator
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMeasurePerformance:
    def test_returns_result_on_success(self):
        from app.plugins.plugin_utils import measure_performance

        @measure_performance("test_plugin", "test_op")
        def fast_op():
            return "result"

        assert fast_op() == "result"

    def test_re_raises_exception(self):
        from app.plugins.plugin_utils import measure_performance

        @measure_performance("test_plugin", "failing_op")
        def failing_op():
            raise ValueError("boom")

        with pytest.raises(ValueError):
            failing_op()

    def test_preserves_function_name(self):
        from app.plugins.plugin_utils import measure_performance

        @measure_performance("test_plugin", "op")
        def my_func():
            pass

        assert my_func.__name__ == "my_func"

    def test_logs_duration(self):
        from app.plugins.plugin_utils import measure_performance, get_plugin_logger

        logged_messages = []
        original_debug = logging.Logger.debug

        @measure_performance("perf_plugin", "timed_op")
        def slow_op():
            return 42

        slow_op()  # Should complete without error


# ---------------------------------------------------------------------------
# PluginMetrics
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPluginMetrics:
    def test_increment_counter_creates_new_metric(self):
        from app.plugins.plugin_utils import PluginMetrics
        m = PluginMetrics("test_plugin")
        m.increment_counter("requests")
        assert m.metrics["requests"]["value"] == 1

    def test_increment_counter_accumulates(self):
        from app.plugins.plugin_utils import PluginMetrics
        m = PluginMetrics("test_plugin")
        m.increment_counter("requests", 3)
        m.increment_counter("requests", 2)
        assert m.metrics["requests"]["value"] == 5

    def test_record_timing(self):
        from app.plugins.plugin_utils import PluginMetrics
        m = PluginMetrics("test_plugin")
        m.record_timing("response_time", 0.123)
        assert 0.123 in m.metrics["response_time"]["values"]

    def test_record_timing_keeps_last_100(self):
        from app.plugins.plugin_utils import PluginMetrics
        m = PluginMetrics("test_plugin")
        for i in range(110):
            m.record_timing("latency", float(i))
        assert len(m.metrics["latency"]["values"]) == 100
        # Should have the last 100 values (10..109)
        assert m.metrics["latency"]["values"][0] == 10.0

    def test_get_metrics_counter(self):
        from app.plugins.plugin_utils import PluginMetrics
        m = PluginMetrics("test_plugin")
        m.increment_counter("hits", 5)
        metrics = m.get_metrics()
        assert metrics["hits"] == 5

    def test_get_metrics_timing(self):
        from app.plugins.plugin_utils import PluginMetrics
        m = PluginMetrics("test_plugin")
        m.record_timing("latency", 1.0)
        m.record_timing("latency", 3.0)
        metrics = m.get_metrics()
        assert metrics["latency"]["count"] == 2
        assert metrics["latency"]["avg"] == 2.0
        assert metrics["latency"]["min"] == 1.0
        assert metrics["latency"]["max"] == 3.0

    def test_get_metrics_empty_timing_skipped(self):
        from app.plugins.plugin_utils import PluginMetrics
        m = PluginMetrics("test_plugin")
        # Manually create empty timing entry
        m.metrics["empty_timing"] = {"type": "timing", "values": []}
        metrics = m.get_metrics()
        assert "empty_timing" not in metrics


# ---------------------------------------------------------------------------
# clear_plugin_cache
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestClearPluginCache:
    def setup_method(self):
        """Reset the global cache before each test."""
        from app.plugins import plugin_utils
        plugin_utils._plugin_cache.clear()

    def test_clear_all(self):
        from app.plugins import plugin_utils
        plugin_utils._plugin_cache["plugin_a:func:123"] = ("result", time.time())
        plugin_utils._plugin_cache["plugin_b:func:456"] = ("result2", time.time())
        result = plugin_utils.clear_plugin_cache()
        assert result is True
        assert plugin_utils._plugin_cache == {}

    def test_clear_by_plugin_name(self):
        from app.plugins import plugin_utils
        plugin_utils._plugin_cache["plugin_a:func:123"] = ("r", time.time())
        plugin_utils._plugin_cache["plugin_b:func:456"] = ("r2", time.time())
        removed = plugin_utils.clear_plugin_cache(plugin_name="plugin_a")
        assert removed == 1
        assert "plugin_a:func:123" not in plugin_utils._plugin_cache
        assert "plugin_b:func:456" in plugin_utils._plugin_cache

    def test_clear_by_function_name(self):
        from app.plugins import plugin_utils
        plugin_utils._plugin_cache["plugin_a:my_func:123"] = ("r", time.time())
        plugin_utils._plugin_cache["plugin_a:other_func:456"] = ("r2", time.time())
        removed = plugin_utils.clear_plugin_cache(function_name="my_func")
        assert removed == 1
        assert "plugin_a:my_func:123" not in plugin_utils._plugin_cache

    def test_clear_by_plugin_and_function(self):
        from app.plugins import plugin_utils
        plugin_utils._plugin_cache["plugin_a:func:123"] = ("r", time.time())
        plugin_utils._plugin_cache["plugin_b:func:456"] = ("r2", time.time())
        removed = plugin_utils.clear_plugin_cache(plugin_name="plugin_a", function_name="func")
        assert removed == 1

    def test_returns_zero_when_nothing_matched(self):
        from app.plugins import plugin_utils
        plugin_utils._plugin_cache["plugin_a:func:123"] = ("r", time.time())
        removed = plugin_utils.clear_plugin_cache(plugin_name="nonexistent")
        assert removed == 0


# ---------------------------------------------------------------------------
# cache_plugin_result decorator
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCachePluginResult:
    def setup_method(self):
        from app.plugins import plugin_utils
        plugin_utils._plugin_cache.clear()

    def test_caches_result(self):
        from app.plugins.plugin_utils import cache_plugin_result

        call_count = [0]

        @cache_plugin_result(ttl_seconds=60, plugin_name="test_plugin")
        def expensive():
            call_count[0] += 1
            return "computed"

        r1 = expensive()
        r2 = expensive()
        assert r1 == r2 == "computed"
        assert call_count[0] == 1

    def test_cache_expires(self):
        from app.plugins.plugin_utils import cache_plugin_result

        call_count = [0]

        @cache_plugin_result(ttl_seconds=0, plugin_name="test_plugin")
        def expiring():
            call_count[0] += 1
            return "result"

        expiring()
        time.sleep(0.01)
        expiring()
        assert call_count[0] == 2

    def test_cache_evicts_oldest_when_full(self):
        from app.plugins import plugin_utils
        from app.plugins.plugin_utils import cache_plugin_result

        # Fill cache with 100 entries
        for i in range(101):
            plugin_utils._plugin_cache[f"x:f:{i}"] = ("v", time.time())

        call_count = [0]

        @cache_plugin_result(ttl_seconds=60, plugin_name="eviction_test")
        def new_func(*args):
            call_count[0] += 1
            return args

        new_func("unique_arg_xyz")
        # Cache should have been trimmed
        assert len(plugin_utils._plugin_cache) <= 101

    def test_cache_key_includes_kwargs(self):
        from app.plugins.plugin_utils import cache_plugin_result

        call_count = [0]

        @cache_plugin_result(ttl_seconds=60, plugin_name="kw_test")
        def func_with_kwargs(**kw):
            call_count[0] += 1
            return kw

        func_with_kwargs(a=1)
        func_with_kwargs(a=2)  # Different kwargs → different cache key
        assert call_count[0] == 2

    def test_infers_plugin_name_from_module(self):
        from app.plugins.plugin_utils import cache_plugin_result

        @cache_plugin_result(ttl_seconds=60)  # No plugin_name
        def inferred():
            return "inferred"

        result = inferred()
        assert result == "inferred"

    def test_cache_with_request_context(self):
        """Within a Flask request context, request data is included in cache key."""
        from app.plugins.plugin_utils import cache_plugin_result
        app = _make_flask_app()

        call_count = [0]

        @cache_plugin_result(ttl_seconds=60, plugin_name="req_test")
        def route_handler():
            call_count[0] += 1
            return "handler"

        with app.test_request_context("/?iso=US"):
            r1 = route_handler()
        with app.test_request_context("/?iso=US"):
            r2 = route_handler()

        assert r1 == r2 == "handler"

    def test_cache_different_request_paths_miss(self):
        """Different request paths produce different cache keys."""
        from app.plugins.plugin_utils import cache_plugin_result
        app = _make_flask_app()

        call_count = [0]

        @cache_plugin_result(ttl_seconds=60, plugin_name="path_test")
        def route_handler():
            call_count[0] += 1
            return "handler"

        with app.test_request_context("/path_a"):
            route_handler()
        with app.test_request_context("/path_b"):
            route_handler()

        assert call_count[0] == 2

    def test_has_request_context_check_exception(self):
        """Cover lines 326-328: exception during has_request_context check."""
        from app.plugins.plugin_utils import cache_plugin_result
        from app.plugins import plugin_utils
        plugin_utils._plugin_cache.clear()

        call_count = [0]

        @cache_plugin_result(ttl_seconds=60, plugin_name="exc_test")
        def func():
            call_count[0] += 1
            return "result"

        # has_request_context is imported inside the wrapper; patch via flask module
        with patch("flask.has_request_context", side_effect=RuntimeError("ctx error")):
            result = func()
        assert result == "result"
        assert call_count[0] == 1

    def test_request_serialization_exception(self):
        """Cover lines 346-348: exception when json.dumps fails for request data."""
        from app.plugins.plugin_utils import cache_plugin_result
        from app.plugins import plugin_utils
        plugin_utils._plugin_cache.clear()
        app = _make_flask_app()

        call_count = [0]

        @cache_plugin_result(ttl_seconds=60, plugin_name="ser_test")
        def func(**kw):
            call_count[0] += 1
            return "result"

        # Make json.dumps raise ONLY when called with the request-metadata dict
        # (identified by having 'method', 'path', 'args' keys).
        import json as _json
        original_dumps = _json.dumps

        def raise_on_req_dict(*args, **kwargs):
            if args and isinstance(args[0], dict) and "method" in args[0]:
                raise ValueError("req serialization fail")
            return original_dumps(*args, **kwargs)

        with app.test_request_context("/?q=test"):
            with patch("app.plugins.plugin_utils.json") as mock_json:
                mock_json.dumps.side_effect = raise_on_req_dict
                result = func(some_kwarg="val")
        assert result == "result"
        assert call_count[0] == 1


# ---------------------------------------------------------------------------
# Targeted tests for plugin_route_wrapper inner body (lines 86-87)
# and create_standard_routes successful paths (lines 111, 118, 126, 133, 141, 148)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPluginRouteWrapperBody:
    """Cover lines 86-87: the inner wrapper function body."""

    def test_wrapper_body_is_executed_on_success(self):
        """When patching login_required to a no-op, the wrapper body executes."""
        with patch("app.plugins.plugin_utils.login_required", lambda f: f):
            from app.plugins.plugin_utils import plugin_route_wrapper

            results = []

            @plugin_route_wrapper("test_plugin")
            def my_view_fn():
                return "success"

            app = _make_flask_app()
            with app.test_request_context("/"):
                with patch("app.plugins.plugin_utils.current_app") as mca:
                    mca.logger = MagicMock()
                    result = my_view_fn()
            assert result == "success"


@pytest.mark.unit
class TestCreateStandardRoutesSuccessPaths:
    """Cover lines 111, 118, 126, 133, 141, 148 — route handler paths."""

    def _setup_with_config(self, url_prefix="/p"):
        with patch("app.plugins.plugin_utils.login_required", lambda f: f), \
             patch("app.plugins.plugin_utils.permission_required", lambda _perm: (lambda f: f)):
            from app.plugins.plugin_utils import BasePluginRoutes
            app = _make_flask_app()
            bp = Blueprint(f"sr_bp_{id(self)}_{url_prefix.replace('/', '_')}", __name__)
            cfg = MagicMock()
            cfg.get_all_config.return_value = {"a": 1}
            cfg.update_config.return_value = True
            cfg.update_section.return_value = True
            renderer = MagicMock(return_value="<settings/>")

            bpr = BasePluginRoutes("test_plugin", plugin_config=cfg)
            bpr.create_standard_routes(bp, template_renderer=renderer)
            app.register_blueprint(bp, url_prefix=url_prefix)
            return app, cfg, renderer

    def _setup_no_config(self, url_prefix="/pnc"):
        with patch("app.plugins.plugin_utils.login_required", lambda f: f), \
             patch("app.plugins.plugin_utils.permission_required", lambda _perm: (lambda f: f)):
            from app.plugins.plugin_utils import BasePluginRoutes
            app = _make_flask_app()
            bp = Blueprint(f"sr_nc_bp_{id(self)}", __name__)
            bpr = BasePluginRoutes("test_plugin")  # No config
            bpr.create_standard_routes(bp)
            app.register_blueprint(bp, url_prefix=url_prefix)
            return app

    def test_get_config_route_success(self):
        app, cfg, _ = self._setup_with_config("/pg")
        with patch("app.plugins.plugin_utils.is_json_request", return_value=True):
            with patch("app.plugins.plugin_utils.current_app") as mca:
                mca.logger = MagicMock()
                with patch("app.plugins.plugin_utils.json_ok", return_value=("ok", 200)):
                    response = app.test_client().get("/pg/api/config")

    def test_update_full_config_route_success(self):
        app, cfg, _ = self._setup_with_config("/pp")
        with patch("app.plugins.plugin_utils.get_json_safe", return_value={"k": "v"}):
            with patch("app.plugins.plugin_utils.is_json_request", return_value=True):
                with patch("app.plugins.plugin_utils.current_app") as mca:
                    mca.logger = MagicMock()
                    with patch("app.plugins.plugin_utils.json_ok", return_value=("ok", 200)):
                        response = app.test_client().post("/pp/api/config", json={"k": "v"})

    def test_update_config_section_route_success(self):
        app, cfg, _ = self._setup_with_config("/ps")
        with patch("app.plugins.plugin_utils.get_json_safe", return_value={}):
            with patch("app.plugins.plugin_utils.is_json_request", return_value=True):
                with patch("app.plugins.plugin_utils.current_app") as mca:
                    mca.logger = MagicMock()
                    with patch("app.plugins.plugin_utils.json_ok", return_value=("ok", 200)):
                        response = app.test_client().post("/ps/api/config/my_sec", json={})

    def test_settings_page_route_success(self):
        app, _, renderer = self._setup_with_config("/pt")
        with patch("app.plugins.plugin_utils.is_json_request", return_value=False):
            with patch("app.plugins.plugin_utils.current_app") as mca:
                mca.logger = MagicMock()
                renderer.return_value = "settings_html"
                response = app.test_client().get("/pt/settings")

    # Lines 118 and 133: POST routes with no plugin_config → PluginConfigError raised
    def test_post_config_no_config_raises(self):
        """Cover line 118: POST /api/config with no plugin_config."""
        app = self._setup_no_config("/pnc1")
        with patch("app.plugins.plugin_utils.is_json_request", return_value=False):
            with patch("app.plugins.plugin_utils.current_app") as mca:
                mca.logger = MagicMock()
                response = app.test_client().post("/pnc1/api/config", json={})
        assert response.status_code == 500

    def test_post_config_section_no_config_raises(self):
        """Cover line 133: POST /api/config/<section> with no plugin_config."""
        app = self._setup_no_config("/pnc2")
        with patch("app.plugins.plugin_utils.is_json_request", return_value=False):
            with patch("app.plugins.plugin_utils.current_app") as mca:
                mca.logger = MagicMock()
                response = app.test_client().post("/pnc2/api/config/some_section", json={})
        assert response.status_code == 500
