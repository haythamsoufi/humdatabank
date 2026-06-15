"""
Comprehensive unit tests for app/services/monitoring/memory.py
Targets 100% code coverage with no database required.
"""
import logging
import os
from unittest.mock import patch, MagicMock, PropertyMock, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_memory_monitor():
    """Return a fresh MemoryMonitor bypassing the singleton."""
    from app.services.monitoring import memory as mem_mod

    cls = mem_mod.MemoryMonitor
    orig_instance = cls._instance
    orig_initialized = cls._initialized
    orig_tracemalloc = cls._tracemalloc_started

    cls._instance = None
    cls._initialized = False
    cls._tracemalloc_started = False
    try:
        mgr = cls()
    finally:
        cls._instance = orig_instance
        cls._initialized = orig_initialized
        cls._tracemalloc_started = orig_tracemalloc
    return mgr


def _make_mock_app(config=None):
    app = MagicMock()
    app.logger = MagicMock(spec=logging.Logger)
    app.instance_path = "/tmp/test_instance"
    defaults = {
        "MEMORY_LOG_MAX_BYTES": 10 * 1024 * 1024,
        "MEMORY_LOG_BACKUP_COUNT": 5,
        "TRACEMALLOC_ENABLED": False,
    }
    if config:
        defaults.update(config)
    app.config.get = lambda key, default=None: defaults.get(key, default)
    return app


def _make_psutil_memory_info(rss=100, vms=200):
    mem_info = MagicMock()
    mem_info.rss = rss * 1024 * 1024
    mem_info.vms = vms * 1024 * 1024
    return mem_info


def _make_psutil_virtual_memory(available=500, total=1024):
    vm = MagicMock()
    vm.available = available * 1024 * 1024
    vm.total = total * 1024 * 1024
    return vm


# ===========================================================================
# MemoryMonitor — singleton
# ===========================================================================

class TestMemoryMonitorSingleton:
    def test_singleton_same_instance(self):
        from app.services.monitoring.memory import MemoryMonitor
        assert MemoryMonitor() is MemoryMonitor()

    def test_module_level_instance_exists(self):
        from app.services.monitoring.memory import memory_monitor, MemoryMonitor
        assert isinstance(memory_monitor, MemoryMonitor)

    def test_fresh_instance_defaults(self):
        mgr = _fresh_memory_monitor()
        assert mgr.enabled is False
        assert mgr.logger is None
        assert mgr.memory_logger is None
        assert mgr.log_file_path is None
        assert mgr.file_handler is None


# ===========================================================================
# MemoryMonitor.configure
# ===========================================================================

class TestMemoryConfigure:
    def test_configure_disabled(self):
        mgr = _fresh_memory_monitor()
        app = _make_mock_app()
        mgr.configure(app, enabled=False)
        assert mgr.enabled is False
        assert mgr.memory_logger is None

    def test_configure_enabled_sets_logger(self):
        mgr = _fresh_memory_monitor()
        app = _make_mock_app()
        mock_handler = MagicMock()
        with (
            patch("os.makedirs"),
            patch("os.path.join", side_effect=lambda *a: "/".join(str(x) for x in a)),
            patch("app.utils.logging_handlers.create_rotating_file_handler", return_value=mock_handler),
            patch("logging.getLogger", return_value=MagicMock(spec=logging.Logger, handlers=[])),
        ):
            mgr.configure(app, enabled=True)
        assert mgr.enabled is True
        assert mgr.logger is app.logger

    def test_configure_enabled_sets_log_file_path(self):
        mgr = _fresh_memory_monitor()
        app = _make_mock_app()
        mock_handler = MagicMock()
        with (
            patch("os.makedirs"),
            patch("os.path.join", side_effect=lambda *a: "/".join(str(x) for x in a)),
            patch("app.utils.logging_handlers.create_rotating_file_handler", return_value=mock_handler),
            patch("logging.getLogger", return_value=MagicMock(spec=logging.Logger, handlers=[])),
        ):
            mgr.configure(app, enabled=True)
        assert mgr.log_file_path is not None

    def test_configure_enabled_file_exception_falls_back(self):
        mgr = _fresh_memory_monitor()
        app = _make_mock_app()
        with patch("os.makedirs", side_effect=OSError("no space")):
            mgr.configure(app, enabled=True)
        assert mgr.memory_logger is app.logger  # fallback

    def test_configure_tracemalloc_enabled_starts(self):
        mgr = _fresh_memory_monitor()
        app = _make_mock_app({"TRACEMALLOC_ENABLED": True})
        mock_handler = MagicMock()
        with (
            patch("os.makedirs"),
            patch("os.path.join", side_effect=lambda *a: "/".join(str(x) for x in a)),
            patch("app.utils.logging_handlers.create_rotating_file_handler", return_value=mock_handler),
            patch("logging.getLogger", return_value=MagicMock(spec=logging.Logger, handlers=[])),
            patch("tracemalloc.start") as mock_start,
            patch("tracemalloc.is_tracing", return_value=False),
        ):
            mgr.configure(app, enabled=True)
        mock_start.assert_called_once()
        assert mgr._tracemalloc_started is True

    def test_configure_tracemalloc_already_started_skips(self):
        mgr = _fresh_memory_monitor()
        mgr._tracemalloc_started = True
        app = _make_mock_app({"TRACEMALLOC_ENABLED": True})
        mock_handler = MagicMock()
        with (
            patch("os.makedirs"),
            patch("os.path.join", side_effect=lambda *a: "/".join(str(x) for x in a)),
            patch("app.utils.logging_handlers.create_rotating_file_handler", return_value=mock_handler),
            patch("logging.getLogger", return_value=MagicMock(spec=logging.Logger, handlers=[])),
            patch("tracemalloc.start") as mock_start,
        ):
            mgr.configure(app, enabled=True)
        mock_start.assert_not_called()

    def test_configure_tracemalloc_start_exception_logged(self):
        mgr = _fresh_memory_monitor()
        app = _make_mock_app({"TRACEMALLOC_ENABLED": True})
        mock_handler = MagicMock()
        with (
            patch("os.makedirs"),
            patch("os.path.join", side_effect=lambda *a: "/".join(str(x) for x in a)),
            patch("app.utils.logging_handlers.create_rotating_file_handler", return_value=mock_handler),
            patch("logging.getLogger", return_value=MagicMock(spec=logging.Logger, handlers=[])),
            patch("tracemalloc.start", side_effect=RuntimeError("cannot start")),
        ):
            mgr.configure(app, enabled=True)
        app.logger.warning.assert_called()

    def test_configure_tracemalloc_disabled_logs_message(self):
        mgr = _fresh_memory_monitor()
        app = _make_mock_app({"TRACEMALLOC_ENABLED": False})
        mock_handler = MagicMock()
        with (
            patch("os.makedirs"),
            patch("os.path.join", side_effect=lambda *a: "/".join(str(x) for x in a)),
            patch("app.utils.logging_handlers.create_rotating_file_handler", return_value=mock_handler),
            patch("logging.getLogger", return_value=MagicMock(spec=logging.Logger, handlers=[])),
        ):
            mgr.configure(app, enabled=True)
        app.logger.debug.assert_called()


# ===========================================================================
# MemoryMonitor.get_memory_usage
# ===========================================================================

class TestGetMemoryUsage:
    def test_returns_psutil_stats(self):
        mgr = _fresh_memory_monitor()
        mock_process = MagicMock()
        mock_process.memory_info.return_value = _make_psutil_memory_info(rss=128, vms=256)
        mock_process.memory_percent.return_value = 12.5

        mock_psutil = MagicMock()
        mock_psutil.Process.return_value = mock_process
        mock_psutil.virtual_memory.return_value = _make_psutil_virtual_memory(500, 1024)

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            result = mgr.get_memory_usage()

        assert result["rss_mb"] == pytest.approx(128.0, rel=0.01)
        assert result["vms_mb"] == pytest.approx(256.0, rel=0.01)
        assert result["percent"] == pytest.approx(12.5)

    def test_import_error_falls_back_to_tracemalloc_tracing(self):
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError("psutil not available")
            return real_import(name, *args, **kwargs)

        mgr = _fresh_memory_monitor()
        with (
            patch("builtins.__import__", side_effect=mock_import),
            patch("tracemalloc.is_tracing", return_value=True),
            patch("tracemalloc.get_traced_memory", return_value=(50 * 1024 * 1024, 80 * 1024 * 1024)),
        ):
            result = mgr.get_memory_usage()

        assert result["current_mb"] == pytest.approx(50.0, rel=0.01)
        assert result["peak_mb"] == pytest.approx(80.0, rel=0.01)
        assert result["method"] == "tracemalloc"

    def test_import_error_no_tracing_returns_error(self):
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError("psutil not available")
            return real_import(name, *args, **kwargs)

        mgr = _fresh_memory_monitor()
        with (
            patch("builtins.__import__", side_effect=mock_import),
            patch("tracemalloc.is_tracing", return_value=False),
        ):
            result = mgr.get_memory_usage()

        assert "error" in result


# ===========================================================================
# MemoryMonitor.get_top_memory_allocations
# ===========================================================================

class TestGetTopMemoryAllocations:
    def test_returns_empty_when_not_tracing(self):
        mgr = _fresh_memory_monitor()
        with patch("tracemalloc.is_tracing", return_value=False):
            result = mgr.get_top_memory_allocations()
        assert result == []

    def test_returns_stats_when_tracing(self):
        mgr = _fresh_memory_monitor()

        mock_frame = MagicMock()
        mock_frame.filename = "/app/module.py"
        mock_frame.lineno = 42

        mock_stat = MagicMock()
        mock_stat.traceback = [mock_frame]
        mock_stat.size = 5 * 1024 * 1024
        mock_stat.count = 100

        mock_snapshot = MagicMock()
        mock_snapshot.statistics.return_value = [mock_stat]

        with (
            patch("tracemalloc.is_tracing", return_value=True),
            patch("tracemalloc.take_snapshot", return_value=mock_snapshot),
        ):
            result = mgr.get_top_memory_allocations(limit=5)

        assert len(result) == 1
        assert result[0]["filename"] == "/app/module.py"
        assert result[0]["lineno"] == 42
        assert result[0]["size_mb"] == pytest.approx(5.0, rel=0.01)
        assert result[0]["count"] == 100

    def test_handles_empty_traceback(self):
        mgr = _fresh_memory_monitor()

        mock_stat = MagicMock()
        mock_stat.traceback = []
        mock_stat.size = 1024
        mock_stat.count = 1

        mock_snapshot = MagicMock()
        mock_snapshot.statistics.return_value = [mock_stat]

        with (
            patch("tracemalloc.is_tracing", return_value=True),
            patch("tracemalloc.take_snapshot", return_value=mock_snapshot),
        ):
            result = mgr.get_top_memory_allocations()

        assert result[0]["filename"] == "unknown"
        assert result[0]["lineno"] == 0

    def test_exception_logged_returns_empty(self):
        mgr = _fresh_memory_monitor()
        mgr.logger = MagicMock()

        with (
            patch("tracemalloc.is_tracing", return_value=True),
            patch("tracemalloc.take_snapshot", side_effect=RuntimeError("snapshot failed")),
        ):
            result = mgr.get_top_memory_allocations()

        assert result == []
        mgr.logger.warning.assert_called()

    def test_exception_no_logger_returns_empty(self):
        mgr = _fresh_memory_monitor()
        mgr.logger = None

        with (
            patch("tracemalloc.is_tracing", return_value=True),
            patch("tracemalloc.take_snapshot", side_effect=RuntimeError("boom")),
        ):
            result = mgr.get_top_memory_allocations()

        assert result == []


# ===========================================================================
# MemoryMonitor.log_memory_usage
# ===========================================================================

class TestLogMemoryUsage:
    def test_disabled_monitor_does_nothing(self):
        mgr = _fresh_memory_monitor()
        mgr.enabled = False
        mgr.memory_logger = MagicMock()
        mgr.log_memory_usage("test")
        mgr.memory_logger.log.assert_not_called()

    def test_no_logger_returns_early(self):
        mgr = _fresh_memory_monitor()
        mgr.enabled = True
        mgr.memory_logger = None
        mgr.logger = None
        mgr.log_memory_usage("test")  # Should not raise

    def test_logs_error_key_in_memory(self):
        mgr = _fresh_memory_monitor()
        mgr.enabled = True
        mock_logger = MagicMock()
        mgr.memory_logger = mock_logger
        with patch.object(mgr, "get_memory_usage", return_value={"error": "no monitoring"}):
            mgr.log_memory_usage("ctx")
        mock_logger.log.assert_called_once()
        msg = mock_logger.log.call_args[0][1]
        assert "no monitoring" in msg

    def test_logs_psutil_stats(self):
        mgr = _fresh_memory_monitor()
        mgr.enabled = True
        mock_logger = MagicMock()
        mgr.memory_logger = mock_logger
        mem = {"rss_mb": 128.0, "vms_mb": 256.0, "percent": 12.5, "available_mb": 500.0, "total_mb": 1024.0}
        with patch.object(mgr, "get_memory_usage", return_value=mem):
            mgr.log_memory_usage("request")
        mock_logger.log.assert_called_once()
        msg = mock_logger.log.call_args[0][1]
        assert "RSS=128.0MB" in msg

    def test_logs_tracemalloc_stats(self):
        mgr = _fresh_memory_monitor()
        mgr.enabled = True
        mock_logger = MagicMock()
        mgr.memory_logger = mock_logger
        mem = {"current_mb": 50.0, "peak_mb": 80.0, "method": "tracemalloc"}
        with patch.object(mgr, "get_memory_usage", return_value=mem):
            mgr.log_memory_usage("ctx")
        msg = mock_logger.log.call_args[0][1]
        assert "Current=50.0MB" in msg

    def test_uses_app_logger_when_memory_logger_none(self):
        mgr = _fresh_memory_monitor()
        mgr.enabled = True
        mock_logger = MagicMock()
        mgr.memory_logger = None
        mgr.logger = mock_logger
        mem = {"rss_mb": 64.0, "vms_mb": 128.0, "percent": 6.0, "available_mb": 400.0, "total_mb": 800.0}
        with patch.object(mgr, "get_memory_usage", return_value=mem):
            mgr.log_memory_usage("ctx")
        mock_logger.log.assert_called_once()


# ===========================================================================
# MemoryMonitor.log_memory_diff
# ===========================================================================

class TestLogMemoryDiff:
    def test_disabled_does_nothing(self):
        mgr = _fresh_memory_monitor()
        mgr.enabled = False
        mock_logger = MagicMock()
        mgr.memory_logger = mock_logger
        mgr.log_memory_diff({}, {}, "ctx")
        mock_logger.info.assert_not_called()

    def test_no_logger_returns_early(self):
        mgr = _fresh_memory_monitor()
        mgr.enabled = True
        mgr.memory_logger = None
        mgr.logger = None
        mgr.log_memory_diff({"rss_mb": 10}, {"rss_mb": 20}, "ctx")

    def test_skips_when_error_in_before(self):
        mgr = _fresh_memory_monitor()
        mgr.enabled = True
        mock_logger = MagicMock()
        mgr.memory_logger = mock_logger
        mgr.log_memory_diff({"error": "fail"}, {"rss_mb": 20.0, "percent": 10.0}, "ctx")
        mock_logger.info.assert_not_called()

    def test_skips_when_error_in_after(self):
        mgr = _fresh_memory_monitor()
        mgr.enabled = True
        mock_logger = MagicMock()
        mgr.memory_logger = mock_logger
        mgr.log_memory_diff({"rss_mb": 10.0, "percent": 5.0}, {"error": "fail"}, "ctx")
        mock_logger.info.assert_not_called()

    def test_logs_psutil_diff(self):
        mgr = _fresh_memory_monitor()
        mgr.enabled = True
        mock_logger = MagicMock()
        mgr.memory_logger = mock_logger
        before = {"rss_mb": 100.0, "percent": 10.0}
        after = {"rss_mb": 115.0, "percent": 11.5}
        mgr.log_memory_diff(before, after, "my_operation")
        mock_logger.info.assert_called_once()
        msg = mock_logger.info.call_args[0][0]
        assert "ΔRSS=+15.0MB" in msg

    def test_logs_tracemalloc_diff(self):
        mgr = _fresh_memory_monitor()
        mgr.enabled = True
        mock_logger = MagicMock()
        mgr.memory_logger = mock_logger
        before = {"current_mb": 40.0}
        after = {"current_mb": 55.0}
        mgr.log_memory_diff(before, after, "ctx")
        msg = mock_logger.info.call_args[0][0]
        assert "ΔMemory=+15.0MB" in msg

    def test_uses_app_logger_when_memory_logger_none(self):
        mgr = _fresh_memory_monitor()
        mgr.enabled = True
        mock_logger = MagicMock()
        mgr.memory_logger = None
        mgr.logger = mock_logger
        before = {"rss_mb": 50.0, "percent": 5.0}
        after = {"rss_mb": 60.0, "percent": 6.0}
        mgr.log_memory_diff(before, after, "ctx")
        mock_logger.info.assert_called_once()


# ===========================================================================
# MemoryMonitor.get_log_file_path
# ===========================================================================

class TestGetLogFilePath:
    def test_returns_none_when_not_configured(self):
        mgr = _fresh_memory_monitor()
        assert mgr.get_log_file_path() is None

    def test_returns_path_when_configured(self):
        mgr = _fresh_memory_monitor()
        mgr.log_file_path = "/tmp/logs/memory.log"
        assert mgr.get_log_file_path() == "/tmp/logs/memory.log"


# ===========================================================================
# memory_tracker decorator
# ===========================================================================

class TestMemoryTracker:
    def test_disabled_monitor_passes_through(self):
        from app.services.monitoring.memory import memory_tracker, memory_monitor
        original = memory_monitor.enabled
        try:
            memory_monitor.enabled = False

            @memory_tracker("op")
            def func():
                return "result"

            assert func() == "result"
        finally:
            memory_monitor.enabled = original

    def test_enabled_tracks_before_and_after(self):
        from app.services.monitoring.memory import memory_tracker, memory_monitor
        original_enabled = memory_monitor.enabled
        original_logger = memory_monitor.memory_logger
        try:
            memory_monitor.enabled = True
            mock_logger = MagicMock()
            memory_monitor.memory_logger = mock_logger

            mem = {"rss_mb": 100.0, "percent": 10.0}
            with patch.object(memory_monitor, "get_memory_usage", return_value=mem):
                with patch.object(memory_monitor, "log_memory_usage") as mock_log:
                    with patch.object(memory_monitor, "log_memory_diff") as mock_diff:

                        @memory_tracker("my_op")
                        def func():
                            return 42

                        result = func()

            assert result == 42
            assert mock_log.call_count == 2
            mock_diff.assert_called_once()
        finally:
            memory_monitor.enabled = original_enabled
            memory_monitor.memory_logger = original_logger

    def test_uses_module_and_name_when_op_name_none(self):
        from app.services.monitoring.memory import memory_tracker, memory_monitor
        original_enabled = memory_monitor.enabled
        try:
            memory_monitor.enabled = True
            mem = {"rss_mb": 100.0, "percent": 10.0}
            with patch.object(memory_monitor, "get_memory_usage", return_value=mem):
                with patch.object(memory_monitor, "log_memory_usage") as mock_log:
                    with patch.object(memory_monitor, "log_memory_diff"):

                        @memory_tracker()  # no operation_name
                        def named_func():
                            return "x"

                        named_func()

            # Check that the function module + name was used
            first_call_context = mock_log.call_args_list[0][0][0]
            assert "named_func" in first_call_context
        finally:
            memory_monitor.enabled = original_enabled

    def test_exception_logs_diff_and_reraises(self):
        from app.services.monitoring.memory import memory_tracker, memory_monitor
        original_enabled = memory_monitor.enabled
        try:
            memory_monitor.enabled = True
            mem = {"rss_mb": 100.0, "percent": 10.0}
            with patch.object(memory_monitor, "get_memory_usage", return_value=mem):
                with patch.object(memory_monitor, "log_memory_usage"):
                    with patch.object(memory_monitor, "log_memory_diff") as mock_diff:

                        @memory_tracker("err_op")
                        def failing_func():
                            raise ValueError("test error")

                        with pytest.raises(ValueError, match="test error"):
                            failing_func()

            mock_diff.assert_called_once()
            context = mock_diff.call_args[0][2]
            assert "ERROR" in context
        finally:
            memory_monitor.enabled = original_enabled

    def test_log_top_allocations_when_flag_set(self):
        from app.services.monitoring.memory import memory_tracker, memory_monitor
        original_enabled = memory_monitor.enabled
        original_logger = memory_monitor.memory_logger
        try:
            memory_monitor.enabled = True
            mock_logger = MagicMock()
            memory_monitor.memory_logger = mock_logger
            alloc = {"filename": "f.py", "lineno": 1, "size_mb": 2.0, "count": 10}

            mem = {"rss_mb": 100.0, "percent": 10.0}
            with patch.object(memory_monitor, "get_memory_usage", return_value=mem):
                with patch.object(memory_monitor, "log_memory_usage"):
                    with patch.object(memory_monitor, "log_memory_diff"):
                        with patch.object(memory_monitor, "get_top_memory_allocations", return_value=[alloc]):

                            @memory_tracker("alloc_op", log_top_allocations=True)
                            def func():
                                return "done"

                            func()

            mock_logger.info.assert_called()
        finally:
            memory_monitor.enabled = original_enabled
            memory_monitor.memory_logger = original_logger

    def test_log_top_allocations_empty_list_skips(self):
        from app.services.monitoring.memory import memory_tracker, memory_monitor
        original_enabled = memory_monitor.enabled
        original_logger = memory_monitor.memory_logger
        try:
            memory_monitor.enabled = True
            mock_logger = MagicMock()
            memory_monitor.memory_logger = mock_logger
            mem = {"rss_mb": 100.0, "percent": 10.0}
            with patch.object(memory_monitor, "get_memory_usage", return_value=mem):
                with patch.object(memory_monitor, "log_memory_usage"):
                    with patch.object(memory_monitor, "log_memory_diff"):
                        with patch.object(memory_monitor, "get_top_memory_allocations", return_value=[]):

                            @memory_tracker("empty_alloc_op", log_top_allocations=True)
                            def func():
                                return "ok"

                            func()

            mock_logger.info.assert_not_called()
        finally:
            memory_monitor.enabled = original_enabled
            memory_monitor.memory_logger = original_logger

    def test_preserves_function_name(self):
        from app.services.monitoring.memory import memory_tracker

        @memory_tracker("meta")
        def documented():
            """doc"""
            pass

        assert documented.__name__ == "documented"


# ===========================================================================
# MemoryContext
# ===========================================================================

class TestMemoryContext:
    def test_disabled_monitor_noop(self):
        from app.services.monitoring.memory import MemoryContext, memory_monitor
        original = memory_monitor.enabled
        try:
            memory_monitor.enabled = False
            with patch.object(memory_monitor, "log_memory_usage") as mock_log:
                with MemoryContext("test"):
                    pass
            mock_log.assert_not_called()
        finally:
            memory_monitor.enabled = original

    def test_enabled_logs_enter_and_exit(self):
        from app.services.monitoring.memory import MemoryContext, memory_monitor
        original = memory_monitor.enabled
        try:
            memory_monitor.enabled = True
            mem = {"rss_mb": 100.0, "percent": 10.0}
            with patch.object(memory_monitor, "get_memory_usage", return_value=mem):
                with patch.object(memory_monitor, "log_memory_usage") as mock_log:
                    with patch.object(memory_monitor, "log_memory_diff"):
                        with MemoryContext("my_ctx"):
                            pass
            assert mock_log.call_count == 2
            contexts = [c[0][0] for c in mock_log.call_args_list]
            assert any("Enter my_ctx" in c for c in contexts)
            assert any("Exit my_ctx" in c for c in contexts)
        finally:
            memory_monitor.enabled = original

    def test_log_top_allocations_in_context(self):
        from app.services.monitoring.memory import MemoryContext, memory_monitor
        original_enabled = memory_monitor.enabled
        original_logger = memory_monitor.memory_logger
        try:
            memory_monitor.enabled = True
            mock_logger = MagicMock()
            memory_monitor.memory_logger = mock_logger
            alloc = {"filename": "f.py", "lineno": 5, "size_mb": 1.0, "count": 5}

            mem = {"rss_mb": 100.0, "percent": 10.0}
            with patch.object(memory_monitor, "get_memory_usage", return_value=mem):
                with patch.object(memory_monitor, "log_memory_usage"):
                    with patch.object(memory_monitor, "log_memory_diff"):
                        with patch.object(memory_monitor, "get_top_memory_allocations", return_value=[alloc]):
                            with MemoryContext("ctx", log_top_allocations=True):
                                pass

            mock_logger.info.assert_called()
        finally:
            memory_monitor.enabled = original_enabled
            memory_monitor.memory_logger = original_logger

    def test_log_top_allocations_empty_list_skips(self):
        from app.services.monitoring.memory import MemoryContext, memory_monitor
        original_enabled = memory_monitor.enabled
        original_logger = memory_monitor.memory_logger
        try:
            memory_monitor.enabled = True
            mock_logger = MagicMock()
            memory_monitor.memory_logger = mock_logger

            mem = {"rss_mb": 100.0, "percent": 10.0}
            with patch.object(memory_monitor, "get_memory_usage", return_value=mem):
                with patch.object(memory_monitor, "log_memory_usage"):
                    with patch.object(memory_monitor, "log_memory_diff"):
                        with patch.object(memory_monitor, "get_top_memory_allocations", return_value=[]):
                            with MemoryContext("ctx", log_top_allocations=True):
                                pass

            mock_logger.info.assert_not_called()
        finally:
            memory_monitor.enabled = original_enabled
            memory_monitor.memory_logger = original_logger

    def test_context_uses_app_logger_when_memory_logger_none(self):
        from app.services.monitoring.memory import MemoryContext, memory_monitor
        original_enabled = memory_monitor.enabled
        original_logger = memory_monitor.memory_logger
        original_app_logger = memory_monitor.logger
        try:
            memory_monitor.enabled = True
            mock_logger = MagicMock()
            memory_monitor.memory_logger = None
            memory_monitor.logger = mock_logger
            alloc = {"filename": "f.py", "lineno": 1, "size_mb": 0.5, "count": 2}

            mem = {"rss_mb": 100.0, "percent": 10.0}
            with patch.object(memory_monitor, "get_memory_usage", return_value=mem):
                with patch.object(memory_monitor, "log_memory_usage"):
                    with patch.object(memory_monitor, "log_memory_diff"):
                        with patch.object(memory_monitor, "get_top_memory_allocations", return_value=[alloc]):
                            with MemoryContext("ctx", log_top_allocations=True):
                                pass

            mock_logger.info.assert_called()
        finally:
            memory_monitor.enabled = original_enabled
            memory_monitor.memory_logger = original_logger
            memory_monitor.logger = original_app_logger


# ===========================================================================
# log_request_memory
# ===========================================================================

class TestLogRequestMemory:
    def test_disabled_returns_immediately(self, app):
        from app.services.monitoring.memory import log_request_memory, memory_monitor
        original = memory_monitor.enabled
        try:
            memory_monitor.enabled = False
            with app.test_request_context("/test"):
                with patch.object(memory_monitor, "get_memory_usage") as mock_mem:
                    log_request_memory()
            mock_mem.assert_not_called()
        finally:
            memory_monitor.enabled = original

    def test_skips_static_path(self, app):
        from app.services.monitoring.memory import log_request_memory, memory_monitor
        original = memory_monitor.enabled
        try:
            memory_monitor.enabled = True
            with app.test_request_context("/static/app.js"):
                with patch.object(memory_monitor, "get_memory_usage") as mock_mem:
                    log_request_memory()
            mock_mem.assert_not_called()
        finally:
            memory_monitor.enabled = original

    def test_skips_flags_path(self, app):
        from app.services.monitoring.memory import log_request_memory, memory_monitor
        original = memory_monitor.enabled
        try:
            memory_monitor.enabled = True
            with app.test_request_context("/flags/test.png"):
                with patch.object(memory_monitor, "get_memory_usage") as mock_mem:
                    log_request_memory()
            mock_mem.assert_not_called()
        finally:
            memory_monitor.enabled = original

    def test_stores_memory_in_g(self, app):
        from app.services.monitoring.memory import log_request_memory, memory_monitor
        from flask import g
        original = memory_monitor.enabled
        try:
            memory_monitor.enabled = True
            mem = {"rss_mb": 100.0, "percent": 10.0}
            with app.test_request_context("/data"):
                with patch.object(memory_monitor, "get_memory_usage", return_value=mem):
                    with patch.object(memory_monitor, "log_memory_usage"):
                        log_request_memory()
                assert hasattr(g, "request_memory_before")
        finally:
            memory_monitor.enabled = original

    def test_logs_when_high_rss(self, app):
        from app.services.monitoring.memory import log_request_memory, memory_monitor
        original = memory_monitor.enabled
        try:
            memory_monitor.enabled = True
            mem = {"rss_mb": 600.0, "percent": 90.0}
            with app.test_request_context("/data"):
                with patch.object(memory_monitor, "get_memory_usage", return_value=mem):
                    with patch.object(memory_monitor, "log_memory_usage") as mock_log:
                        log_request_memory()
            mock_log.assert_called()
        finally:
            memory_monitor.enabled = original

    def test_logs_when_high_percent(self, app):
        from app.services.monitoring.memory import log_request_memory, memory_monitor
        original = memory_monitor.enabled
        try:
            memory_monitor.enabled = True
            mem = {"rss_mb": 200.0, "percent": 85.0}
            with app.test_request_context("/data"):
                with patch.object(memory_monitor, "get_memory_usage", return_value=mem):
                    with patch.object(memory_monitor, "log_memory_usage") as mock_log:
                        log_request_memory()
            mock_log.assert_called()
        finally:
            memory_monitor.enabled = original

    def test_no_log_when_memory_normal(self, app):
        from app.services.monitoring.memory import log_request_memory, memory_monitor
        original = memory_monitor.enabled
        try:
            memory_monitor.enabled = True
            mem = {"rss_mb": 100.0, "percent": 10.0}
            with app.test_request_context("/data"):
                with patch.object(memory_monitor, "get_memory_usage", return_value=mem):
                    with patch.object(memory_monitor, "log_memory_usage") as mock_log:
                        log_request_memory()
            mock_log.assert_not_called()
        finally:
            memory_monitor.enabled = original

    def test_tracemalloc_high_memory_logs(self, app):
        from app.services.monitoring.memory import log_request_memory, memory_monitor
        original = memory_monitor.enabled
        try:
            memory_monitor.enabled = True
            mem = {"current_mb": 600.0}
            with app.test_request_context("/data"):
                with patch.object(memory_monitor, "get_memory_usage", return_value=mem):
                    with patch.object(memory_monitor, "log_memory_usage") as mock_log:
                        log_request_memory()
            mock_log.assert_called()
        finally:
            memory_monitor.enabled = original

    def test_tracemalloc_normal_memory_no_log(self, app):
        from app.services.monitoring.memory import log_request_memory, memory_monitor
        original = memory_monitor.enabled
        try:
            memory_monitor.enabled = True
            mem = {"current_mb": 50.0}
            with app.test_request_context("/data"):
                with patch.object(memory_monitor, "get_memory_usage", return_value=mem):
                    with patch.object(memory_monitor, "log_memory_usage") as mock_log:
                        log_request_memory()
            mock_log.assert_not_called()
        finally:
            memory_monitor.enabled = original


# ===========================================================================
# log_request_memory_end
# ===========================================================================

class TestLogRequestMemoryEnd:
    def test_disabled_returns_immediately(self, app):
        from app.services.monitoring.memory import log_request_memory_end, memory_monitor
        original = memory_monitor.enabled
        try:
            memory_monitor.enabled = False
            with app.test_request_context("/test"):
                with patch.object(memory_monitor, "log_memory_diff") as mock_diff:
                    log_request_memory_end()
            mock_diff.assert_not_called()
        finally:
            memory_monitor.enabled = original

    def test_skips_static_path(self, app):
        from app.services.monitoring.memory import log_request_memory_end, memory_monitor
        original = memory_monitor.enabled
        try:
            memory_monitor.enabled = True
            with app.test_request_context("/static/js/app.js"):
                with patch.object(memory_monitor, "log_memory_diff") as mock_diff:
                    log_request_memory_end()
            mock_diff.assert_not_called()
        finally:
            memory_monitor.enabled = original

    def test_skips_when_no_before_in_g(self, app):
        from app.services.monitoring.memory import log_request_memory_end, memory_monitor
        original = memory_monitor.enabled
        try:
            memory_monitor.enabled = True
            with app.test_request_context("/data"):
                with patch.object(memory_monitor, "log_memory_diff") as mock_diff:
                    log_request_memory_end()
            mock_diff.assert_not_called()
        finally:
            memory_monitor.enabled = original

    def test_logs_when_large_rss_increase(self, app):
        from app.services.monitoring.memory import log_request_memory_end, memory_monitor
        from flask import g
        original = memory_monitor.enabled
        try:
            memory_monitor.enabled = True
            before = {"rss_mb": 100.0, "percent": 10.0}
            after = {"rss_mb": 115.0, "percent": 11.5}
            with app.test_request_context("/data"):
                g.request_memory_before = before
                with patch.object(memory_monitor, "get_memory_usage", return_value=after):
                    with patch.object(memory_monitor, "log_memory_diff") as mock_diff:
                        log_request_memory_end()
            mock_diff.assert_called_once()
        finally:
            memory_monitor.enabled = original

    def test_logs_when_high_percent_after(self, app):
        from app.services.monitoring.memory import log_request_memory_end, memory_monitor
        from flask import g
        original = memory_monitor.enabled
        try:
            memory_monitor.enabled = True
            before = {"rss_mb": 100.0, "percent": 79.0}
            after = {"rss_mb": 102.0, "percent": 81.0}
            with app.test_request_context("/data"):
                g.request_memory_before = before
                with patch.object(memory_monitor, "get_memory_usage", return_value=after):
                    with patch.object(memory_monitor, "log_memory_diff") as mock_diff:
                        log_request_memory_end()
            mock_diff.assert_called_once()
        finally:
            memory_monitor.enabled = original

    def test_no_log_for_normal_request(self, app):
        from app.services.monitoring.memory import log_request_memory_end, memory_monitor
        from flask import g
        original = memory_monitor.enabled
        try:
            memory_monitor.enabled = True
            before = {"rss_mb": 100.0, "percent": 10.0}
            after = {"rss_mb": 101.0, "percent": 10.1}
            with app.test_request_context("/data"):
                g.request_memory_before = before
                with patch.object(memory_monitor, "get_memory_usage", return_value=after):
                    with patch.object(memory_monitor, "log_memory_diff") as mock_diff:
                        log_request_memory_end()
            mock_diff.assert_not_called()
        finally:
            memory_monitor.enabled = original

    def test_tracemalloc_large_diff_logs(self, app):
        from app.services.monitoring.memory import log_request_memory_end, memory_monitor
        from flask import g
        original = memory_monitor.enabled
        try:
            memory_monitor.enabled = True
            before = {"current_mb": 100.0}
            after = {"current_mb": 115.0}
            with app.test_request_context("/data"):
                g.request_memory_before = before
                with patch.object(memory_monitor, "get_memory_usage", return_value=after):
                    with patch.object(memory_monitor, "log_memory_diff") as mock_diff:
                        log_request_memory_end()
            mock_diff.assert_called_once()
        finally:
            memory_monitor.enabled = original

    def test_tracemalloc_high_current_logs(self, app):
        from app.services.monitoring.memory import log_request_memory_end, memory_monitor
        from flask import g
        original = memory_monitor.enabled
        try:
            memory_monitor.enabled = True
            before = {"current_mb": 490.0}
            after = {"current_mb": 510.0}
            with app.test_request_context("/data"):
                g.request_memory_before = before
                with patch.object(memory_monitor, "get_memory_usage", return_value=after):
                    with patch.object(memory_monitor, "log_memory_diff") as mock_diff:
                        log_request_memory_end()
            mock_diff.assert_called_once()
        finally:
            memory_monitor.enabled = original

    def test_tracemalloc_no_log_normal(self, app):
        from app.services.monitoring.memory import log_request_memory_end, memory_monitor
        from flask import g
        original = memory_monitor.enabled
        try:
            memory_monitor.enabled = True
            before = {"current_mb": 50.0}
            after = {"current_mb": 51.0}
            with app.test_request_context("/data"):
                g.request_memory_before = before
                with patch.object(memory_monitor, "get_memory_usage", return_value=after):
                    with patch.object(memory_monitor, "log_memory_diff") as mock_diff:
                        log_request_memory_end()
            mock_diff.assert_not_called()
        finally:
            memory_monitor.enabled = original
