"""
Comprehensive unit tests for app/services/monitoring/debug.py
Targets 100% code coverage with no database required.
"""
import io
import logging
import sys
import time
import traceback
from unittest.mock import patch, MagicMock, PropertyMock, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_debug_manager():
    """Return a brand-new DebugManager instance (bypasses singleton)."""
    from app.services.monitoring import debug as dm_mod

    cls = dm_mod.DebugManager
    orig_instance = cls._instance
    orig_initialized = cls._initialized

    cls._instance = None
    cls._initialized = False
    try:
        mgr = cls()
    finally:
        # Restore singleton so other code still works
        cls._instance = orig_instance
        cls._initialized = orig_initialized
    return mgr


def _make_mock_app(config=None):
    """Build a minimal Flask-like mock app."""
    app = MagicMock()
    app.logger = MagicMock(spec=logging.Logger)
    app.logger.handlers = []
    app.instance_path = "/tmp/test_instance"
    defaults = {
        "LOG_LEVEL": "",
        "LOG_MODE": "normal",
        "LOG_TO_STDOUT": False,
        "APPLICATION_LOG_FILE_ENABLED": False,
        "AI_VERBOSE_OPENAI_HTTP": False,
    }
    if config:
        defaults.update(config)
    app.config.get = lambda key, default=None: defaults.get(key, default)
    return app


# ===========================================================================
# DebugManager — singleton behaviour
# ===========================================================================

class TestDebugManagerSingleton:
    def test_singleton_returns_same_instance(self):
        from app.services.monitoring.debug import DebugManager
        a = DebugManager()
        b = DebugManager()
        assert a is b

    def test_module_level_instance_exists(self):
        from app.services.monitoring.debug import debug_manager, DebugManager
        assert isinstance(debug_manager, DebugManager)

    def test_fresh_instance_has_defaults(self):
        mgr = _fresh_debug_manager()
        assert mgr.verbose_debug is False
        assert mgr.performance_tracking == {}


# ===========================================================================
# DebugManager.configure_logging — log-level resolution
# ===========================================================================

class TestConfigureLogging:
    """Tests for configure_logging() with various config combinations."""

    def _call(self, config=None, verbose_debug=False):
        mgr = _fresh_debug_manager()
        app = _make_mock_app(config)
        with (
            patch("os.makedirs"),
            patch("logging.getLogger", return_value=MagicMock(spec=logging.Logger, handlers=[])),
        ):
            mgr.configure_logging(app, verbose_debug=verbose_debug)
        return mgr, app

    # --- explicit LOG_LEVEL values ---
    def test_log_level_debug_string(self):
        mgr, _ = self._call({"LOG_LEVEL": "DEBUG"})
        assert mgr.verbose_debug is True

    def test_log_level_info_string(self):
        mgr, _ = self._call({"LOG_LEVEL": "INFO"})
        assert mgr.verbose_debug is False

    def test_log_level_warning_string(self):
        mgr, _ = self._call({"LOG_LEVEL": "WARNING"})
        assert mgr.verbose_debug is False

    def test_log_level_error_string(self):
        mgr, _ = self._call({"LOG_LEVEL": "ERROR"})
        assert mgr.verbose_debug is False

    def test_log_level_critical_string(self):
        mgr, _ = self._call({"LOG_LEVEL": "CRITICAL"})
        assert mgr.verbose_debug is False

    # --- LOG_MODE fallback ---
    def test_log_mode_quiet(self):
        mgr, _ = self._call({"LOG_LEVEL": "", "LOG_MODE": "quiet"})
        assert mgr.verbose_debug is False

    def test_log_mode_normal(self):
        mgr, _ = self._call({"LOG_LEVEL": "", "LOG_MODE": "normal"})
        assert mgr.verbose_debug is False

    def test_log_mode_debug(self):
        mgr, _ = self._call({"LOG_LEVEL": "", "LOG_MODE": "debug"})
        assert mgr.verbose_debug is True

    def test_log_mode_unknown_defaults_to_info(self):
        mgr, _ = self._call({"LOG_LEVEL": "", "LOG_MODE": "unknown"})
        assert mgr.verbose_debug is False

    # --- verbose_debug parameter ---
    def test_verbose_debug_param_promotes_to_debug(self):
        mgr, _ = self._call({"LOG_LEVEL": "", "LOG_MODE": "normal"}, verbose_debug=True)
        assert mgr.verbose_debug is True

    def test_verbose_debug_param_ignored_when_log_level_set(self):
        """When LOG_LEVEL is explicitly set, verbose_debug param is ignored."""
        mgr, _ = self._call({"LOG_LEVEL": "WARNING"}, verbose_debug=True)
        assert mgr.verbose_debug is False

    # --- logger info messages ---
    def test_debug_mode_logs_debug_enabled_message(self):
        mgr = _fresh_debug_manager()
        app = _make_mock_app({"LOG_LEVEL": "DEBUG"})
        with (
            patch("os.makedirs"),
            patch("logging.getLogger", return_value=MagicMock(spec=logging.Logger, handlers=[])),
        ):
            mgr.configure_logging(app)
        app.logger.info.assert_any_call(
            "Terminal logging: DEBUG enabled (LOG_MODE=debug / LOG_LEVEL=DEBUG)"
        )

    def test_info_mode_logs_info_enabled_message(self):
        mgr = _fresh_debug_manager()
        app = _make_mock_app({"LOG_LEVEL": "INFO"})
        with (
            patch("os.makedirs"),
            patch("logging.getLogger", return_value=MagicMock(spec=logging.Logger, handlers=[])),
        ):
            mgr.configure_logging(app)
        app.logger.info.assert_any_call(
            "Terminal logging: INFO enabled (LOG_MODE=normal / LOG_LEVEL=INFO)"
        )

    def test_warning_mode_logs_quiet_message(self):
        mgr = _fresh_debug_manager()
        app = _make_mock_app({"LOG_LEVEL": "WARNING"})
        with (
            patch("os.makedirs"),
            patch("logging.getLogger", return_value=MagicMock(spec=logging.Logger, handlers=[])),
        ):
            mgr.configure_logging(app)
        app.logger.info.assert_any_call(
            "Terminal logging: quiet mode enabled (LOG_MODE=quiet / LOG_LEVEL>=WARNING)"
        )

    # --- LOG_TO_STDOUT=True path ---
    def test_log_to_stdout_adds_stream_handler(self):
        mgr = _fresh_debug_manager()
        app = _make_mock_app({"LOG_TO_STDOUT": True, "APPLICATION_LOG_FILE_ENABLED": False})
        mock_handler = MagicMock(spec=logging.StreamHandler)
        with (
            patch("os.makedirs"),
            patch("logging.StreamHandler", return_value=mock_handler),
            patch("logging.getLogger", return_value=MagicMock(spec=logging.Logger, handlers=[])),
        ):
            mgr.configure_logging(app)
        app.logger.addHandler.assert_called()

    # --- APPLICATION_LOG_FILE_ENABLED=True path ---
    def test_file_logging_enabled_sets_log_path(self):
        mgr = _fresh_debug_manager()
        app = _make_mock_app({"APPLICATION_LOG_FILE_ENABLED": True, "LOG_TO_STDOUT": False})
        app.application_log_file_path = None

        mock_handler = MagicMock()
        with (
            patch("os.makedirs"),
            patch("os.path.join", side_effect=lambda *a: "/".join(str(x) for x in a)),
            patch("app.utils.logging_handlers.create_rotating_file_handler", return_value=mock_handler),
            patch("logging.getLogger", return_value=MagicMock(spec=logging.Logger, handlers=[])),
        ):
            mgr.configure_logging(app)

        assert hasattr(app, "application_log_file_path")

    def test_file_logging_disabled_sets_none(self):
        mgr = _fresh_debug_manager()
        app = _make_mock_app({"APPLICATION_LOG_FILE_ENABLED": False})
        with (
            patch("os.makedirs"),
            patch("logging.getLogger", return_value=MagicMock(spec=logging.Logger, handlers=[])),
        ):
            mgr.configure_logging(app)
        assert app.application_log_file_path is None

    def test_file_logging_exception_falls_back_gracefully(self):
        mgr = _fresh_debug_manager()
        app = _make_mock_app({"APPLICATION_LOG_FILE_ENABLED": True, "LOG_TO_STDOUT": False})

        with (
            patch("os.makedirs", side_effect=OSError("permission denied")),
            patch("logging.getLogger", return_value=MagicMock(spec=logging.Logger, handlers=[])),
        ):
            mgr.configure_logging(app)  # should not raise
        app.logger.warning.assert_called()

    def test_root_file_handler_added_when_log_path_set(self):
        """When file logging is enabled + path set, root logger also gets file handler."""
        mgr = _fresh_debug_manager()
        app = _make_mock_app({
            "APPLICATION_LOG_FILE_ENABLED": True,
            "LOG_TO_STDOUT": False,
        })
        mock_fh = MagicMock()

        with (
            patch("os.makedirs"),
            patch("os.path.join", side_effect=lambda *a: "/".join(str(x) for x in a)),
            patch("app.utils.logging_handlers.create_rotating_file_handler", return_value=mock_fh),
            patch("logging.getLogger", return_value=MagicMock(spec=logging.Logger, handlers=[])),
        ):
            mgr.configure_logging(app)

    def test_file_handler_creation_exception_logged(self):
        """If application log file handler creation fails, a warning is logged."""
        mgr = _fresh_debug_manager()
        app = _make_mock_app({
            "APPLICATION_LOG_FILE_ENABLED": True,
            "LOG_TO_STDOUT": False,
        })

        with (
            patch("os.makedirs"),
            patch("os.path.join", side_effect=lambda *a: "/".join(str(x) for x in a)),
            patch(
                "app.utils.logging_handlers.create_rotating_file_handler",
                side_effect=OSError("handler fails"),
            ),
            patch("logging.getLogger", return_value=MagicMock(spec=logging.Logger, handlers=[])),
        ):
            mgr.configure_logging(app)

        app.logger.warning.assert_called()

    def test_openai_verbose_env_var_suppresses_noisy_loggers(self):
        """When AI_VERBOSE_OPENAI_HTTP is falsy, openai loggers are set to WARNING."""
        mgr = _fresh_debug_manager()
        app = _make_mock_app({"AI_VERBOSE_OPENAI_HTTP": False})
        captured_loggers = {}

        real_get_logger = logging.getLogger

        def mock_get_logger(name=None):
            mock = MagicMock(spec=logging.Logger, handlers=[])
            if name:
                captured_loggers[name] = mock
            return mock

        with (
            patch("os.makedirs"),
            patch("logging.getLogger", side_effect=mock_get_logger),
            patch.dict("os.environ", {"AI_VERBOSE_OPENAI_HTTP": ""}, clear=False),
        ):
            mgr.configure_logging(app)

        # openai logger should have been configured
        assert "openai" in captured_loggers

    def test_azure_storage_loggers_suppressed_to_warning(self):
        """Azure Blob SDK HTTP wire logs are capped at WARNING (like urllib3)."""
        mgr = _fresh_debug_manager()
        app = _make_mock_app({})
        captured_loggers = {}

        def mock_get_logger(name=None):
            mock = MagicMock(spec=logging.Logger, handlers=[])
            if name:
                captured_loggers[name] = mock
            return mock

        with (
            patch("os.makedirs"),
            patch("logging.getLogger", side_effect=mock_get_logger),
        ):
            mgr.configure_logging(app)

        for logger_name in (
            "azure",
            "azure.core.pipeline.policies.http_logging_policy",
            "azure.storage.blob",
        ):
            assert logger_name in captured_loggers
            captured_loggers[logger_name].setLevel.assert_any_call(logging.WARNING)

    def test_openai_verbose_env_var_enabled_skips_suppression(self):
        """When AI_VERBOSE_OPENAI_HTTP is truthy, openai loggers are NOT suppressed."""
        mgr = _fresh_debug_manager()
        app = _make_mock_app({"AI_VERBOSE_OPENAI_HTTP": True})
        captured_loggers = {}

        def mock_get_logger(name=None):
            mock = MagicMock(spec=logging.Logger, handlers=[])
            if name:
                captured_loggers[name] = mock
            return mock

        with (
            patch("os.makedirs"),
            patch("logging.getLogger", side_effect=mock_get_logger),
        ):
            mgr.configure_logging(app)

        assert "openai" not in captured_loggers

    def test_weasyprint_and_fonttools_loggers_suppressed_to_warning(self):
        """PDF pipeline INFO (progress + glyph subsetting) is capped at WARNING."""
        mgr = _fresh_debug_manager()
        app = _make_mock_app({})
        captured_loggers = {}

        def mock_get_logger(name=None):
            mock = MagicMock(spec=logging.Logger, handlers=[])
            if name:
                captured_loggers[name] = mock
            return mock

        with (
            patch("os.makedirs"),
            patch("logging.getLogger", side_effect=mock_get_logger),
        ):
            mgr.configure_logging(app)

        for logger_name in (
            "weasyprint",
            "weasyprint.progress",
            "fontTools",
            "fontTools.subset",
            "fontTools.ttLib",
        ):
            assert logger_name in captured_loggers
            captured_loggers[logger_name].setLevel.assert_any_call(logging.WARNING)

    def test_log_to_stdout_also_adds_root_stream_handler(self):
        mgr = _fresh_debug_manager()
        app = _make_mock_app({"LOG_TO_STDOUT": True, "APPLICATION_LOG_FILE_ENABLED": False})
        root_mock = MagicMock(spec=logging.Logger, handlers=[])

        def mock_get_logger(name=None):
            if name is None or name == "":
                return root_mock
            return MagicMock(spec=logging.Logger, handlers=[])

        with (
            patch("os.makedirs"),
            patch("logging.getLogger", side_effect=mock_get_logger),
            patch("logging.StreamHandler", return_value=MagicMock()),
        ):
            mgr.configure_logging(app)
        root_mock.addHandler.assert_called()


# ===========================================================================
# DebugManager.get_logger
# ===========================================================================

class TestGetLogger:
    def test_returns_logger_instance(self):
        from app.services.monitoring.debug import debug_manager
        logger = debug_manager.get_logger("test.module")
        assert isinstance(logger, logging.Logger)

    def test_verbose_debug_sets_debug_level(self):
        mgr = _fresh_debug_manager()
        mgr.verbose_debug = True
        logger = mgr.get_logger("test.verbose")
        assert logger.level == logging.DEBUG

    def test_non_verbose_sets_info_level(self):
        mgr = _fresh_debug_manager()
        mgr.verbose_debug = False
        logger = mgr.get_logger("test.info")
        assert logger.level == logging.INFO


# ===========================================================================
# DebugManager.set_debug_mode
# ===========================================================================

class TestSetDebugMode:
    def test_enable_sets_verbose_debug_true(self):
        mgr = _fresh_debug_manager()
        mgr.set_debug_mode(True)
        assert mgr.verbose_debug is True

    def test_disable_sets_verbose_debug_false(self):
        mgr = _fresh_debug_manager()
        mgr.verbose_debug = True
        mgr.set_debug_mode(False)
        assert mgr.verbose_debug is False

    def test_updates_app_and_sqlalchemy_loggers(self):
        mgr = _fresh_debug_manager()
        with patch("logging.getLogger") as mock_get:
            mock_log = MagicMock(spec=logging.Logger, handlers=[])
            mock_get.return_value = mock_log
            mgr.set_debug_mode(True)
        mock_log.setLevel.assert_called()

    def test_werkzeug_always_stays_at_warning(self):
        mgr = _fresh_debug_manager()
        werkzeug_mock = MagicMock(spec=logging.Logger, handlers=[])

        def side_effect(name=None):
            if name == "werkzeug":
                return werkzeug_mock
            return MagicMock(spec=logging.Logger, handlers=[])

        with patch("logging.getLogger", side_effect=side_effect):
            mgr.set_debug_mode(True)

        werkzeug_mock.setLevel.assert_called_with(logging.WARNING)

    def test_root_logger_updated(self):
        mgr = _fresh_debug_manager()
        root_mock = MagicMock(spec=logging.Logger, handlers=[])

        def side_effect(name=None):
            if name is None or name == "":
                return root_mock
            return MagicMock(spec=logging.Logger, handlers=[])

        with patch("logging.getLogger", side_effect=side_effect):
            mgr.set_debug_mode(False)

        root_mock.setLevel.assert_called_with(logging.INFO)


# ===========================================================================
# performance_monitor decorator
# ===========================================================================

class TestPerformanceMonitor:
    def test_quiet_mode_skips_timing(self):
        from app.services.monitoring.debug import performance_monitor, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = True

            @performance_monitor("op", quiet=True)
            def my_func():
                return "result"

            assert my_func() == "result"
        finally:
            debug_manager.verbose_debug = original

    def test_non_verbose_debug_skips_timing(self):
        from app.services.monitoring.debug import performance_monitor, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = False

            @performance_monitor("op")
            def my_func():
                return 42

            assert my_func() == 42
        finally:
            debug_manager.verbose_debug = original

    def test_verbose_debug_tracks_performance(self):
        from app.services.monitoring.debug import performance_monitor, debug_manager
        original = debug_manager.verbose_debug
        original_tracking = dict(debug_manager.performance_tracking)
        try:
            debug_manager.verbose_debug = True
            debug_manager.performance_tracking = {}

            @performance_monitor("tracked_op")
            def my_func():
                return "done"

            my_func()
            assert "tracked_op" in debug_manager.performance_tracking
            assert len(debug_manager.performance_tracking["tracked_op"]) == 1
        finally:
            debug_manager.verbose_debug = original
            debug_manager.performance_tracking = original_tracking

    def test_accumulates_multiple_calls(self):
        from app.services.monitoring.debug import performance_monitor, debug_manager
        original = debug_manager.verbose_debug
        original_tracking = dict(debug_manager.performance_tracking)
        try:
            debug_manager.verbose_debug = True
            debug_manager.performance_tracking = {}

            @performance_monitor("multi_op")
            def my_func():
                return 1

            my_func()
            my_func()
            my_func()
            assert len(debug_manager.performance_tracking["multi_op"]) == 3
        finally:
            debug_manager.verbose_debug = original
            debug_manager.performance_tracking = original_tracking

    def test_slow_operation_logs_warning(self):
        from app.services.monitoring.debug import performance_monitor, debug_manager
        original = debug_manager.verbose_debug
        original_tracking = dict(debug_manager.performance_tracking)
        try:
            debug_manager.verbose_debug = True
            debug_manager.performance_tracking = {}

            mock_logger = MagicMock()

            @performance_monitor("slow_op")
            def slow_func():
                return "slow"

            with (
                patch.object(debug_manager, "get_logger", return_value=mock_logger),
                patch("time.time", side_effect=[0.0, 3.5]),
            ):
                slow_func()

            mock_logger.warning.assert_called()
        finally:
            debug_manager.verbose_debug = original
            debug_manager.performance_tracking = original_tracking

    def test_exception_reraises_and_logs_error(self):
        from app.services.monitoring.debug import performance_monitor, debug_manager
        original = debug_manager.verbose_debug
        original_tracking = dict(debug_manager.performance_tracking)
        try:
            debug_manager.verbose_debug = True
            debug_manager.performance_tracking = {}
            mock_logger = MagicMock()

            @performance_monitor("err_op")
            def failing_func():
                raise ValueError("boom")

            with patch.object(debug_manager, "get_logger", return_value=mock_logger):
                with pytest.raises(ValueError, match="boom"):
                    failing_func()

            mock_logger.error.assert_called()
        finally:
            debug_manager.verbose_debug = original
            debug_manager.performance_tracking = original_tracking

    def test_preserves_function_metadata(self):
        from app.services.monitoring.debug import performance_monitor

        @performance_monitor("meta_op")
        def documented_func():
            """My docstring."""
            pass

        assert documented_func.__name__ == "documented_func"
        assert documented_func.__doc__ == "My docstring."


# ===========================================================================
# debug_form_data
# ===========================================================================

class TestDebugFormData:
    def test_returns_early_when_verbose_debug_false(self):
        from app.services.monitoring.debug import debug_form_data, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = False
            mock_logger = MagicMock()
            debug_form_data({"key": "val"}, mock_logger)
            mock_logger.debug.assert_not_called()
        finally:
            debug_manager.verbose_debug = original

    def test_logs_summary_when_verbose(self, app):
        from app.services.monitoring.debug import debug_form_data, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = True
            mock_logger = MagicMock()
            with app.app_context():
                debug_form_data({"action": "save", "name": "test"}, mock_logger)
            mock_logger.debug.assert_called()
        finally:
            debug_manager.verbose_debug = original

    def test_uses_default_logger_when_none_passed(self, app):
        from app.services.monitoring.debug import debug_form_data, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = True
            with app.app_context():
                debug_form_data({"key": "val"})  # no logger — should use default
        finally:
            debug_manager.verbose_debug = original

    def test_runtime_error_outside_context_uses_false(self):
        from app.services.monitoring.debug import debug_form_data, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = True
            mock_logger = MagicMock()
            # No app context → current_app.config raises RuntimeError
            debug_form_data({"key": "val"}, mock_logger)
            mock_logger.debug.assert_called()
        finally:
            debug_manager.verbose_debug = original

    def test_full_payload_filters_sensitive_keys(self, app):
        from app.services.monitoring.debug import debug_form_data, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = True
            mock_logger = MagicMock()
            with app.app_context():
                app.config["VERBOSE_FORM_DATA_LOGGING"] = True
                try:
                    debug_form_data(
                        {"password": "secret", "api_key": "abc", "name": "john"},
                        mock_logger,
                    )
                finally:
                    app.config.pop("VERBOSE_FORM_DATA_LOGGING", None)
            # Check that the filtered dump was logged
            calls = [str(c) for c in mock_logger.debug.call_args_list]
            combined = " ".join(calls)
            assert "[FILTERED]" in combined
        finally:
            debug_manager.verbose_debug = original

    def test_full_payload_truncates_long_values(self, app):
        from app.services.monitoring.debug import debug_form_data, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = True
            mock_logger = MagicMock()
            with app.app_context():
                app.config["VERBOSE_FORM_DATA_LOGGING"] = True
                try:
                    debug_form_data({"long_field": "x" * 300}, mock_logger)
                finally:
                    app.config.pop("VERBOSE_FORM_DATA_LOGGING", None)
            calls = [str(c) for c in mock_logger.debug.call_args_list]
            assert any("TRUNCATED" in c for c in calls)
        finally:
            debug_manager.verbose_debug = original

    def test_meta_keys_included_in_summary(self, app):
        from app.services.monitoring.debug import debug_form_data, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = True
            mock_logger = MagicMock()
            with app.app_context():
                debug_form_data(
                    {"action": "submit", "template_id": "5", "other": "val"},
                    mock_logger,
                )
            first_call_args = mock_logger.debug.call_args_list[0][0][0]
            assert "action=" in first_call_args
        finally:
            debug_manager.verbose_debug = original

    def test_non_empty_values_counted_correctly(self, app):
        from app.services.monitoring.debug import debug_form_data, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = True
            mock_logger = MagicMock()
            with app.app_context():
                debug_form_data({"a": "val", "b": "", "c": None, "d": []}, mock_logger)
            first_call = mock_logger.debug.call_args_list[0][0][0]
            assert "non_empty_values=1" in first_call
        finally:
            debug_manager.verbose_debug = original


# ===========================================================================
# debug_request_info
# ===========================================================================

class TestDebugRequestInfo:
    def test_returns_early_when_verbose_debug_false(self, app):
        from app.services.monitoring.debug import debug_request_info, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = False
            mock_logger = MagicMock()
            with app.test_request_context("/test"):
                debug_request_info(mock_logger)
            mock_logger.debug.assert_not_called()
        finally:
            debug_manager.verbose_debug = original

    def test_logs_request_details_when_verbose(self, app):
        from app.services.monitoring.debug import debug_request_info, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = True
            mock_logger = MagicMock()
            with app.test_request_context("/test", method="GET"):
                debug_request_info(mock_logger)
            assert mock_logger.debug.call_count >= 3
        finally:
            debug_manager.verbose_debug = original

    def test_uses_default_logger_when_none(self, app):
        from app.services.monitoring.debug import debug_request_info, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = True
            with app.test_request_context("/test"):
                debug_request_info()  # no logger arg
        finally:
            debug_manager.verbose_debug = original

    def test_logs_form_data_when_present(self, app):
        from app.services.monitoring.debug import debug_request_info, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = True
            mock_logger = MagicMock()
            with app.test_request_context(
                "/test",
                method="POST",
                data={"field": "value"},
            ):
                debug_request_info(mock_logger)
            assert mock_logger.debug.call_count >= 3
        finally:
            debug_manager.verbose_debug = original


# ===========================================================================
# debug_database_query
# ===========================================================================

class TestDebugDatabaseQuery:
    def test_returns_early_when_not_verbose(self):
        from app.services.monitoring.debug import debug_database_query, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = False
            mock_logger = MagicMock()
            with patch.object(debug_manager, "get_logger", return_value=mock_logger):
                debug_database_query("SELECT *")
            mock_logger.debug.assert_not_called()
        finally:
            debug_manager.verbose_debug = original

    def test_logs_query_when_verbose(self):
        from app.services.monitoring.debug import debug_database_query, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = True
            mock_logger = MagicMock()
            with patch.object(debug_manager, "get_logger", return_value=mock_logger):
                debug_database_query("SELECT *")
            mock_logger.debug.assert_called()
        finally:
            debug_manager.verbose_debug = original

    def test_logs_result_count_when_provided(self):
        from app.services.monitoring.debug import debug_database_query, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = True
            mock_logger = MagicMock()
            with patch.object(debug_manager, "get_logger", return_value=mock_logger):
                debug_database_query("SELECT *", result_count=42)
            assert mock_logger.debug.call_count == 2
        finally:
            debug_manager.verbose_debug = original

    def test_does_not_log_result_count_when_none(self):
        from app.services.monitoring.debug import debug_database_query, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = True
            mock_logger = MagicMock()
            with patch.object(debug_manager, "get_logger", return_value=mock_logger):
                debug_database_query("SELECT *", result_count=None)
            assert mock_logger.debug.call_count == 1
        finally:
            debug_manager.verbose_debug = original


# ===========================================================================
# get_performance_stats
# ===========================================================================

class TestGetPerformanceStats:
    def test_empty_tracking_returns_empty_dict(self):
        from app.services.monitoring.debug import get_performance_stats, debug_manager
        original = dict(debug_manager.performance_tracking)
        try:
            debug_manager.performance_tracking = {}
            stats = get_performance_stats()
            assert stats == {}
        finally:
            debug_manager.performance_tracking = original

    def test_returns_correct_stats_structure(self):
        from app.services.monitoring.debug import get_performance_stats, debug_manager
        original = dict(debug_manager.performance_tracking)
        try:
            debug_manager.performance_tracking = {"op": [1.0, 2.0, 3.0]}
            stats = get_performance_stats()
            assert "op" in stats
            op = stats["op"]
            assert op["count"] == 3
            assert op["avg_time"] == 2.0
            assert op["max_time"] == 3.0
            assert op["min_time"] == 1.0
            assert op["total_time"] == 6.0
        finally:
            debug_manager.performance_tracking = original

    def test_skips_empty_time_lists(self):
        from app.services.monitoring.debug import get_performance_stats, debug_manager
        original = dict(debug_manager.performance_tracking)
        try:
            debug_manager.performance_tracking = {"empty_op": []}
            stats = get_performance_stats()
            assert "empty_op" not in stats
        finally:
            debug_manager.performance_tracking = original


# ===========================================================================
# log_user_action
# ===========================================================================

class TestLogUserAction:
    def test_logs_action_without_details(self, app):
        from app.services.monitoring.debug import log_user_action
        mock_logger = MagicMock()
        with app.app_context():
            log_user_action("login", user_id=1, logger=mock_logger)
        mock_logger.info.assert_called_once()
        msg = mock_logger.info.call_args[0][0]
        assert "login" in msg
        assert "User 1" in msg

    def test_logs_action_with_details(self, app):
        from app.services.monitoring.debug import log_user_action
        mock_logger = MagicMock()
        with app.app_context():
            log_user_action(
                "update",
                details={"field": "email", "password": "secret"},
                user_id=2,
                logger=mock_logger,
            )
        msg = mock_logger.info.call_args[0][0]
        assert "Details" in msg
        assert "password" not in msg  # filtered

    def test_uses_current_user_when_no_user_id(self, app):
        from app.services.monitoring.debug import log_user_action
        mock_logger = MagicMock()
        mock_user = MagicMock()
        mock_user.id = 99
        mock_user.is_authenticated = True
        with app.app_context():
            with patch(
                "app.services.monitoring.debug.current_user",
                new_callable=lambda: type("P", (), {"id": 99})
            ):
                log_user_action("view", logger=mock_logger)
        mock_logger.info.assert_called_once()

    def test_uses_default_logger_when_none(self, app):
        from app.services.monitoring.debug import log_user_action
        with app.app_context():
            log_user_action("action", user_id=1)

    def test_filters_token_and_secret_keys(self, app):
        from app.services.monitoring.debug import log_user_action
        mock_logger = MagicMock()
        with app.app_context():
            log_user_action(
                "test",
                details={"token": "abc", "secret_key": "xyz", "name": "visible"},
                user_id=1,
                logger=mock_logger,
            )
        msg = mock_logger.info.call_args[0][0]
        assert "visible" in msg
        assert "token" not in msg
        assert "secret_key" not in msg


# ===========================================================================
# format_error_context
# ===========================================================================

class TestFormatErrorContext:
    def test_basic_error_formatting(self):
        from app.services.monitoring.debug import format_error_context, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = False
            result = format_error_context(ValueError("test error"))
            assert "ValueError" in result
            assert "test error" in result
        finally:
            debug_manager.verbose_debug = original

    def test_includes_context_when_provided(self):
        from app.services.monitoring.debug import format_error_context, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = False
            result = format_error_context(
                RuntimeError("oops"), context={"request_id": "abc123"}
            )
            assert "request_id" in result
        finally:
            debug_manager.verbose_debug = original

    def test_includes_traceback_when_verbose(self):
        from app.services.monitoring.debug import format_error_context, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = True
            result = format_error_context(TypeError("bad type"))
            assert "Traceback" in result or "NoneType" in result or "format_error_context" in result
        finally:
            debug_manager.verbose_debug = original

    def test_no_traceback_when_not_verbose(self):
        from app.services.monitoring.debug import format_error_context, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = False
            result = format_error_context(TypeError("bad type"))
            # The word "Traceback" should not appear
            assert "Traceback" not in result
        finally:
            debug_manager.verbose_debug = original


# ===========================================================================
# Convenience functions: debug, info, warning, error
# ===========================================================================

class TestConvenienceFunctions:
    def test_debug_logs_when_verbose(self):
        from app.services.monitoring.debug import debug as _debug, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = True
            mock_logger = MagicMock()
            with patch.object(debug_manager, "get_logger", return_value=mock_logger):
                _debug("hello debug", module="my.module")
            mock_logger.debug.assert_called_once_with("hello debug")
        finally:
            debug_manager.verbose_debug = original

    def test_debug_skips_when_not_verbose(self):
        from app.services.monitoring.debug import debug as _debug, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = False
            mock_logger = MagicMock()
            with patch.object(debug_manager, "get_logger", return_value=mock_logger):
                _debug("silent")
            mock_logger.debug.assert_not_called()
        finally:
            debug_manager.verbose_debug = original

    def test_debug_uses_default_module_name(self):
        from app.services.monitoring.debug import debug as _debug, debug_manager
        original = debug_manager.verbose_debug
        try:
            debug_manager.verbose_debug = True
            mock_logger = MagicMock()
            with patch.object(debug_manager, "get_logger", return_value=mock_logger) as mock_get:
                _debug("no module")
            mock_get.assert_called()
        finally:
            debug_manager.verbose_debug = original

    def test_info_always_logs(self):
        from app.services.monitoring.debug import info as _info, debug_manager
        mock_logger = MagicMock()
        with patch.object(debug_manager, "get_logger", return_value=mock_logger):
            _info("some info")
        mock_logger.info.assert_called_once_with("some info")

    def test_info_with_module(self):
        from app.services.monitoring.debug import info as _info, debug_manager
        mock_logger = MagicMock()
        with patch.object(debug_manager, "get_logger", return_value=mock_logger) as mock_get:
            _info("msg", module="app.routes")
        mock_get.assert_called_with("app.routes")

    def test_warning_always_logs(self):
        from app.services.monitoring.debug import warning as _warning, debug_manager
        mock_logger = MagicMock()
        with patch.object(debug_manager, "get_logger", return_value=mock_logger):
            _warning("warn msg")
        mock_logger.warning.assert_called_once_with("warn msg")

    def test_error_always_logs(self):
        from app.services.monitoring.debug import error as _error, debug_manager
        mock_logger = MagicMock()
        with patch.object(debug_manager, "get_logger", return_value=mock_logger):
            _error("err msg")
        mock_logger.error.assert_called_once_with("err msg", exc_info=False)

    def test_error_with_exc_info(self):
        from app.services.monitoring.debug import error as _error, debug_manager
        mock_logger = MagicMock()
        with patch.object(debug_manager, "get_logger", return_value=mock_logger):
            _error("err", exc_info=True)
        mock_logger.error.assert_called_once_with("err", exc_info=True)

    def test_error_with_module(self):
        from app.services.monitoring.debug import error as _error, debug_manager
        mock_logger = MagicMock()
        with patch.object(debug_manager, "get_logger", return_value=mock_logger) as mock_get:
            _error("err", module="app.module")
        mock_get.assert_called_with("app.module")


# ===========================================================================
# Handler cleanup helpers (via configure_logging side-effects)
# ===========================================================================

class TestHandlerCleanup:
    """Cover the _clear_managed_handlers and _clear_app_handlers inner functions."""

    def test_managed_handlers_removed_on_reconfigure(self):
        """Re-configuring with LOG_TO_STDOUT=False removes managed handlers."""
        mgr = _fresh_debug_manager()
        app = _make_mock_app({"LOG_TO_STDOUT": False, "APPLICATION_LOG_FILE_ENABLED": False})

        # Use a dedicated stream — never sys.stdout (pytest replaces it during runs).
        managed_handler = logging.StreamHandler(io.StringIO())
        setattr(managed_handler, "_hdb_managed_logging_handler", True)

        with (
            patch("os.makedirs"),
            patch("logging.getLogger", return_value=MagicMock(
                spec=logging.Logger,
                handlers=[managed_handler],
            )),
        ):
            mgr.configure_logging(app)

    def test_handler_close_exception_suppressed(self):
        """Closing a broken handler does not propagate."""
        mgr = _fresh_debug_manager()
        app = _make_mock_app({"LOG_TO_STDOUT": False, "APPLICATION_LOG_FILE_ENABLED": False})

        broken_handler = MagicMock()
        broken_handler.close.side_effect = OSError("disk full")
        setattr(broken_handler, "_hdb_managed_logging_handler", True)
        mock_logger = MagicMock(spec=logging.Logger, handlers=[broken_handler])

        with patch("logging.getLogger", return_value=mock_logger):
            mgr.configure_logging(app)  # Should not raise
