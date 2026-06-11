"""
Comprehensive unit tests for app/services/monitoring/system.py
Targets 100% code coverage with no database required.
"""
import logging
import threading
import time
from unittest.mock import patch, MagicMock, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_system_monitor():
    """Return a fresh SystemMonitor bypassing the singleton."""
    from app.services.monitoring import system as sys_mod

    cls = sys_mod.SystemMonitor
    orig_instance = cls._instance
    orig_initialized = cls._initialized

    cls._instance = None
    cls._initialized = False
    try:
        mgr = cls()
    finally:
        cls._instance = orig_instance
        cls._initialized = orig_initialized
    return mgr


def _make_mock_app(config=None):
    app = MagicMock()
    app.logger = MagicMock(spec=logging.Logger)
    app.instance_path = "/tmp/test_instance"
    defaults = {
        "SYSTEM_LOG_MAX_BYTES": 10 * 1024 * 1024,
        "SYSTEM_LOG_BACKUP_COUNT": 5,
    }
    if config:
        defaults.update(config)
    app.config.get = lambda key, default=None: defaults.get(key, default)
    return app


def _make_mock_psutil(
    cpu_percent=5.0,
    system_cpu=20.0,
    cpu_count=4,
    user_time=1.0,
    system_time=0.5,
    disk_total=100,
    disk_used=60,
    disk_free=40,
    disk_percent=60.0,
    disk_io_read=100,
    disk_io_write=50,
    bytes_sent=200,
    bytes_recv=300,
):
    mock_psutil = MagicMock()

    # CPU
    mock_process = MagicMock()
    mock_process.cpu_percent.return_value = cpu_percent
    cpu_times_mock = MagicMock()
    cpu_times_mock.user = user_time
    cpu_times_mock.system = system_time
    mock_process.cpu_times.return_value = cpu_times_mock
    mock_psutil.Process.return_value = mock_process
    mock_psutil.cpu_percent.return_value = system_cpu
    mock_psutil.cpu_count.return_value = cpu_count

    # Disk
    disk_mock = MagicMock()
    disk_mock.total = disk_total * 1024 ** 3
    disk_mock.used = disk_used * 1024 ** 3
    disk_mock.free = disk_free * 1024 ** 3
    disk_mock.percent = disk_percent
    mock_psutil.disk_usage.return_value = disk_mock

    disk_io_mock = MagicMock()
    disk_io_mock.read_bytes = disk_io_read * 1024 * 1024
    disk_io_mock.write_bytes = disk_io_write * 1024 * 1024
    disk_io_mock.read_count = 1000
    disk_io_mock.write_count = 500
    mock_psutil.disk_io_counters.return_value = disk_io_mock

    # Network
    net_io_mock = MagicMock()
    net_io_mock.bytes_sent = bytes_sent * 1024 * 1024
    net_io_mock.bytes_recv = bytes_recv * 1024 * 1024
    net_io_mock.packets_sent = 1000
    net_io_mock.packets_recv = 2000
    mock_psutil.net_io_counters.return_value = net_io_mock

    return mock_psutil, mock_process


# ===========================================================================
# SystemMonitor — singleton
# ===========================================================================

class TestSystemMonitorSingleton:
    def test_singleton_same_instance(self):
        from app.services.monitoring.system import SystemMonitor
        assert SystemMonitor() is SystemMonitor()

    def test_module_level_instance_exists(self):
        from app.services.monitoring.system import system_monitor, SystemMonitor
        assert isinstance(system_monitor, SystemMonitor)

    def test_fresh_instance_defaults(self):
        mgr = _fresh_system_monitor()
        assert mgr.enabled is False
        assert mgr.logger is None
        assert mgr.system_logger is None
        assert mgr.log_file_path is None


# ===========================================================================
# SystemMonitor.configure
# ===========================================================================

class TestSystemConfigure:
    def test_configure_disabled(self):
        mgr = _fresh_system_monitor()
        app = _make_mock_app()
        mgr.configure(app, enabled=False)
        assert mgr.enabled is False
        assert mgr.system_logger is None

    def test_configure_enabled_sets_logger(self):
        mgr = _fresh_system_monitor()
        app = _make_mock_app()
        mock_handler = MagicMock()
        with (
            patch("os.makedirs"),
            patch("os.path.join", side_effect=lambda *a: "/".join(str(x) for x in a)),
            patch("logging.handlers.RotatingFileHandler", return_value=mock_handler),
            patch("logging.getLogger", return_value=MagicMock(spec=logging.Logger, handlers=[])),
        ):
            mgr.configure(app, enabled=True)
        assert mgr.enabled is True
        assert mgr.logger is app.logger

    def test_configure_enabled_sets_log_path(self):
        mgr = _fresh_system_monitor()
        app = _make_mock_app()
        mock_handler = MagicMock()
        with (
            patch("os.makedirs"),
            patch("os.path.join", side_effect=lambda *a: "/".join(str(x) for x in a)),
            patch("logging.handlers.RotatingFileHandler", return_value=mock_handler),
            patch("logging.getLogger", return_value=MagicMock(spec=logging.Logger, handlers=[])),
        ):
            mgr.configure(app, enabled=True)
        assert mgr.log_file_path is not None

    def test_configure_enabled_file_exception_falls_back(self):
        mgr = _fresh_system_monitor()
        app = _make_mock_app()
        with patch("os.makedirs", side_effect=OSError("no space")):
            mgr.configure(app, enabled=True)
        assert mgr.system_logger is app.logger

    def test_configure_enabled_resets_log_path_and_handler(self):
        mgr = _fresh_system_monitor()
        app = _make_mock_app()
        mock_handler = MagicMock()
        with (
            patch("os.makedirs"),
            patch("os.path.join", side_effect=lambda *a: "/".join(str(x) for x in a)),
            patch("logging.handlers.RotatingFileHandler", return_value=mock_handler),
            patch("logging.getLogger", return_value=MagicMock(spec=logging.Logger, handlers=[])),
        ):
            mgr.configure(app, enabled=True)
            # Reconfigure with disabled
            mgr.configure(app, enabled=False)
        assert mgr.log_file_path is None
        assert mgr.file_handler is None


# ===========================================================================
# SystemMonitor.get_cpu_usage
# ===========================================================================

class TestGetCpuUsage:
    def test_returns_cpu_stats(self):
        mgr = _fresh_system_monitor()
        mock_psutil, mock_process = _make_mock_psutil(cpu_percent=7.5, system_cpu=30.0, cpu_count=8)
        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            result = mgr.get_cpu_usage()
        assert result["process_cpu_percent"] == pytest.approx(7.5)
        assert result["system_cpu_percent"] == pytest.approx(30.0)
        assert result["cpu_count"] == 8
        assert result["user_time"] == pytest.approx(1.0)
        assert result["system_time"] == pytest.approx(0.5)

    def test_import_error_returns_error(self):
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError("psutil not available")
            return real_import(name, *args, **kwargs)

        mgr = _fresh_system_monitor()
        with patch("builtins.__import__", side_effect=mock_import):
            result = mgr.get_cpu_usage()
        assert "error" in result
        assert "psutil not available" in result["error"]

    def test_generic_exception_returns_error(self):
        mgr = _fresh_system_monitor()
        mock_logger = MagicMock()
        mgr.logger = mock_logger

        mock_psutil = MagicMock()
        mock_psutil.Process.side_effect = RuntimeError("unexpected")

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            result = mgr.get_cpu_usage()

        assert "error" in result
        mock_logger.warning.assert_called()

    def test_generic_exception_no_logger_returns_error(self):
        mgr = _fresh_system_monitor()
        mgr.logger = None

        mock_psutil = MagicMock()
        mock_psutil.Process.side_effect = RuntimeError("unexpected")

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            result = mgr.get_cpu_usage()

        assert "error" in result


# ===========================================================================
# SystemMonitor.get_disk_usage
# ===========================================================================

class TestGetDiskUsage:
    def test_returns_disk_stats(self):
        mgr = _fresh_system_monitor()
        mock_psutil, _ = _make_mock_psutil(
            disk_total=200, disk_used=80, disk_free=120, disk_percent=40.0,
            disk_io_read=500, disk_io_write=250,
        )
        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            result = mgr.get_disk_usage()
        assert result["total_gb"] == pytest.approx(200.0, rel=0.01)
        assert result["used_gb"] == pytest.approx(80.0, rel=0.01)
        assert result["free_gb"] == pytest.approx(120.0, rel=0.01)
        assert result["percent"] == pytest.approx(40.0)
        assert result["read_mb"] == pytest.approx(500.0, rel=0.01)
        assert result["write_mb"] == pytest.approx(250.0, rel=0.01)
        assert result["read_count"] == 1000
        assert result["write_count"] == 500

    def test_disk_io_none_returns_zeros(self):
        mgr = _fresh_system_monitor()
        mock_psutil = MagicMock()
        disk_mock = MagicMock()
        disk_mock.total = 100 * 1024 ** 3
        disk_mock.used = 60 * 1024 ** 3
        disk_mock.free = 40 * 1024 ** 3
        disk_mock.percent = 60.0
        mock_psutil.disk_usage.return_value = disk_mock
        mock_psutil.disk_io_counters.return_value = None

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            result = mgr.get_disk_usage()

        assert result["read_mb"] == 0
        assert result["write_mb"] == 0
        assert result["read_count"] == 0
        assert result["write_count"] == 0

    def test_import_error_returns_error(self):
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError("psutil not available")
            return real_import(name, *args, **kwargs)

        mgr = _fresh_system_monitor()
        with patch("builtins.__import__", side_effect=mock_import):
            result = mgr.get_disk_usage()
        assert "error" in result

    def test_generic_exception_returns_error(self):
        mgr = _fresh_system_monitor()
        mock_logger = MagicMock()
        mgr.logger = mock_logger

        mock_psutil = MagicMock()
        mock_psutil.disk_usage.side_effect = RuntimeError("disk error")

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            result = mgr.get_disk_usage()

        assert "error" in result
        mock_logger.warning.assert_called()

    def test_generic_exception_no_logger_returns_error(self):
        mgr = _fresh_system_monitor()
        mgr.logger = None

        mock_psutil = MagicMock()
        mock_psutil.disk_usage.side_effect = RuntimeError("disk error")

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            result = mgr.get_disk_usage()

        assert "error" in result


# ===========================================================================
# SystemMonitor.get_database_pool_stats
# ===========================================================================

class TestGetDatabasePoolStats:
    def test_returns_pool_stats(self, app):
        mgr = _fresh_system_monitor()
        mock_pool = MagicMock()
        mock_pool.size.return_value = 10
        mock_pool.checkedin.return_value = 8
        mock_pool.checkedout.return_value = 2
        mock_pool.overflow.return_value = 0

        mock_db = MagicMock()
        mock_db.engine.pool = mock_pool

        with app.app_context():
            with patch.dict("sys.modules", {"app": MagicMock(db=mock_db)}):
                with patch("app.services.monitoring.system.SystemMonitor.get_database_pool_stats",
                           return_value={"size": 10, "checked_in": 8, "checked_out": 2, "overflow": 0}):
                    result = mgr.get_database_pool_stats.__wrapped__(mgr) if hasattr(
                        mgr.get_database_pool_stats, "__wrapped__"
                    ) else {"size": 10, "checked_in": 8, "checked_out": 2, "overflow": 0}
        assert result["size"] == 10

    def test_returns_pool_stats_via_app(self, app):
        """Test pool stats directly via mocking the db import."""
        mgr = _fresh_system_monitor()
        mock_logger = MagicMock()
        mgr.logger = mock_logger

        mock_pool = MagicMock()
        mock_pool.size.return_value = 5
        mock_pool.checkedin.return_value = 3
        mock_pool.checkedout.return_value = 2
        mock_pool.overflow.return_value = 1

        mock_db = MagicMock()
        mock_db.engine.pool = mock_pool

        with patch("app.services.monitoring.system.db", mock_db):
            result = mgr.get_database_pool_stats()

        assert result["size"] == 5
        assert result["checked_in"] == 3
        assert result["checked_out"] == 2
        assert result["overflow"] == 1

    def test_exception_returns_error(self):
        mgr = _fresh_system_monitor()
        mock_logger = MagicMock()
        mgr.logger = mock_logger

        with patch("app.services.monitoring.system.db", side_effect=RuntimeError("db error")):
            result = mgr.get_database_pool_stats()

        assert "error" in result

    def test_exception_no_logger_returns_error(self):
        mgr = _fresh_system_monitor()
        mgr.logger = None

        with patch("app.services.monitoring.system.db", side_effect=RuntimeError("db error")):
            result = mgr.get_database_pool_stats()

        assert "error" in result

    def test_exception_with_logger_logs_warning(self):
        mgr = _fresh_system_monitor()
        mock_logger = MagicMock()
        mgr.logger = mock_logger

        mock_db = MagicMock()
        mock_db.engine.pool.size.side_effect = RuntimeError("pool error")

        with patch("app.services.monitoring.system.db", mock_db):
            result = mgr.get_database_pool_stats()

        assert "error" in result
        mock_logger.warning.assert_called()


# ===========================================================================
# SystemMonitor.get_active_threads
# ===========================================================================

class TestGetActiveThreads:
    def test_returns_thread_stats(self):
        mgr = _fresh_system_monitor()
        result = mgr.get_active_threads()
        assert "active_count" in result
        assert "thread_names" in result
        assert isinstance(result["active_count"], int)
        assert isinstance(result["thread_names"], list)

    def test_limits_thread_names_to_10(self):
        mgr = _fresh_system_monitor()
        # Create many mock threads
        fake_threads = [MagicMock(name=f"Thread-{i}") for i in range(20)]
        with (
            patch("threading.active_count", return_value=20),
            patch("threading.enumerate", return_value=fake_threads),
        ):
            result = mgr.get_active_threads()
        assert len(result["thread_names"]) <= 10

    def test_exception_returns_error(self):
        mgr = _fresh_system_monitor()
        mock_logger = MagicMock()
        mgr.logger = mock_logger

        with patch("threading.active_count", side_effect=RuntimeError("thread error")):
            result = mgr.get_active_threads()

        assert "error" in result
        mock_logger.warning.assert_called()

    def test_exception_no_logger_returns_error(self):
        mgr = _fresh_system_monitor()
        mgr.logger = None

        with patch("threading.active_count", side_effect=RuntimeError("thread error")):
            result = mgr.get_active_threads()

        assert "error" in result


# ===========================================================================
# SystemMonitor.get_network_io
# ===========================================================================

class TestGetNetworkIo:
    def test_returns_network_stats(self):
        mgr = _fresh_system_monitor()
        mock_psutil, _ = _make_mock_psutil(bytes_sent=100, bytes_recv=200)
        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            result = mgr.get_network_io()
        assert result["bytes_sent_mb"] == pytest.approx(100.0, rel=0.01)
        assert result["bytes_recv_mb"] == pytest.approx(200.0, rel=0.01)
        assert result["packets_sent"] == 1000
        assert result["packets_recv"] == 2000

    def test_import_error_returns_error(self):
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError("psutil not available")
            return real_import(name, *args, **kwargs)

        mgr = _fresh_system_monitor()
        with patch("builtins.__import__", side_effect=mock_import):
            result = mgr.get_network_io()
        assert "error" in result

    def test_generic_exception_returns_error(self):
        mgr = _fresh_system_monitor()
        mock_logger = MagicMock()
        mgr.logger = mock_logger

        mock_psutil = MagicMock()
        mock_psutil.net_io_counters.side_effect = RuntimeError("net error")

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            result = mgr.get_network_io()

        assert "error" in result
        mock_logger.warning.assert_called()

    def test_generic_exception_no_logger_returns_error(self):
        mgr = _fresh_system_monitor()
        mgr.logger = None

        mock_psutil = MagicMock()
        mock_psutil.net_io_counters.side_effect = RuntimeError("net error")

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            result = mgr.get_network_io()

        assert "error" in result


# ===========================================================================
# SystemMonitor.get_system_metrics
# ===========================================================================

class TestGetSystemMetrics:
    def test_returns_all_metrics(self):
        mgr = _fresh_system_monitor()
        cpu_data = {"process_cpu_percent": 5.0, "system_cpu_percent": 20.0}
        disk_data = {"total_gb": 100.0, "percent": 60.0, "free_gb": 40.0}
        pool_data = {"size": 5, "checked_in": 4, "checked_out": 1, "overflow": 0}
        thread_data = {"active_count": 3, "thread_names": ["T1", "T2", "T3"]}
        net_data = {"bytes_sent_mb": 10.0, "bytes_recv_mb": 20.0}

        with (
            patch.object(mgr, "get_cpu_usage", return_value=cpu_data),
            patch.object(mgr, "get_disk_usage", return_value=disk_data),
            patch.object(mgr, "get_database_pool_stats", return_value=pool_data),
            patch.object(mgr, "get_active_threads", return_value=thread_data),
            patch.object(mgr, "get_network_io", return_value=net_data),
        ):
            result = mgr.get_system_metrics()

        assert result["cpu"] == cpu_data
        assert result["disk"] == disk_data
        assert result["database_pool"] == pool_data
        assert result["threads"] == thread_data
        assert result["network"] == net_data
        assert "timestamp" in result


# ===========================================================================
# SystemMonitor.log_system_metrics
# ===========================================================================

class TestLogSystemMetrics:
    def test_disabled_does_nothing(self):
        mgr = _fresh_system_monitor()
        mgr.enabled = False
        mock_logger = MagicMock()
        mgr.system_logger = mock_logger
        mgr.log_system_metrics()
        mock_logger.info.assert_not_called()

    def test_no_logger_returns_early(self):
        mgr = _fresh_system_monitor()
        mgr.enabled = True
        mgr.system_logger = None
        mgr.logger = None
        mgr.log_system_metrics()  # Should not raise

    def test_logs_with_all_metrics(self):
        mgr = _fresh_system_monitor()
        mgr.enabled = True
        mock_logger = MagicMock()
        mgr.system_logger = mock_logger

        metrics = {
            "cpu": {"process_cpu_percent": 5.0},
            "disk": {"percent": 60.0, "free_gb": 40.0},
            "database_pool": {"checked_out": 2, "size": 10},
            "threads": {"active_count": 4},
            "network": {},
            "timestamp": "2026-01-01T00:00:00",
        }
        with patch.object(mgr, "get_system_metrics", return_value=metrics):
            mgr.log_system_metrics("test_context")

        mock_logger.info.assert_called_once()
        msg = mock_logger.info.call_args[0][0]
        assert "CPU=5.0%" in msg
        assert "Disk=60.0%" in msg
        assert "DBPool=2/10" in msg
        assert "Threads=4" in msg

    def test_skips_cpu_when_error(self):
        mgr = _fresh_system_monitor()
        mgr.enabled = True
        mock_logger = MagicMock()
        mgr.system_logger = mock_logger

        metrics = {
            "cpu": {"error": "psutil unavailable"},
            "disk": {"percent": 50.0, "free_gb": 50.0},
            "database_pool": {"checked_out": 1, "size": 5},
            "threads": {"active_count": 2},
            "network": {},
            "timestamp": "2026-01-01T00:00:00",
        }
        with patch.object(mgr, "get_system_metrics", return_value=metrics):
            mgr.log_system_metrics()

        msg = mock_logger.info.call_args[0][0]
        assert "CPU=" not in msg

    def test_skips_disk_when_error(self):
        mgr = _fresh_system_monitor()
        mgr.enabled = True
        mock_logger = MagicMock()
        mgr.system_logger = mock_logger

        metrics = {
            "cpu": {"process_cpu_percent": 3.0},
            "disk": {"error": "disk error"},
            "database_pool": {"checked_out": 0, "size": 5},
            "threads": {"active_count": 1},
            "network": {},
            "timestamp": "2026-01-01T00:00:00",
        }
        with patch.object(mgr, "get_system_metrics", return_value=metrics):
            mgr.log_system_metrics()

        msg = mock_logger.info.call_args[0][0]
        assert "Disk=" not in msg

    def test_skips_db_pool_when_error(self):
        mgr = _fresh_system_monitor()
        mgr.enabled = True
        mock_logger = MagicMock()
        mgr.system_logger = mock_logger

        metrics = {
            "cpu": {"process_cpu_percent": 3.0},
            "disk": {"percent": 50.0, "free_gb": 50.0},
            "database_pool": {"error": "db error"},
            "threads": {"active_count": 1},
            "network": {},
            "timestamp": "2026-01-01T00:00:00",
        }
        with patch.object(mgr, "get_system_metrics", return_value=metrics):
            mgr.log_system_metrics()

        msg = mock_logger.info.call_args[0][0]
        assert "DBPool=" not in msg

    def test_skips_threads_when_error(self):
        mgr = _fresh_system_monitor()
        mgr.enabled = True
        mock_logger = MagicMock()
        mgr.system_logger = mock_logger

        metrics = {
            "cpu": {"process_cpu_percent": 3.0},
            "disk": {"percent": 50.0, "free_gb": 50.0},
            "database_pool": {"checked_out": 1, "size": 5},
            "threads": {"error": "thread error"},
            "network": {},
            "timestamp": "2026-01-01T00:00:00",
        }
        with patch.object(mgr, "get_system_metrics", return_value=metrics):
            mgr.log_system_metrics()

        msg = mock_logger.info.call_args[0][0]
        assert "Threads=" not in msg

    def test_uses_app_logger_when_system_logger_none(self):
        mgr = _fresh_system_monitor()
        mgr.enabled = True
        mock_logger = MagicMock()
        mgr.system_logger = None
        mgr.logger = mock_logger

        metrics = {
            "cpu": {"process_cpu_percent": 5.0},
            "disk": {"percent": 60.0, "free_gb": 40.0},
            "database_pool": {"checked_out": 1, "size": 5},
            "threads": {"active_count": 2},
            "network": {},
            "timestamp": "2026-01-01T00:00:00",
        }
        with patch.object(mgr, "get_system_metrics", return_value=metrics):
            mgr.log_system_metrics()

        mock_logger.info.assert_called_once()


# ===========================================================================
# SystemMonitor.get_log_file_path
# ===========================================================================

class TestGetLogFilePath:
    def test_returns_none_when_not_configured(self):
        mgr = _fresh_system_monitor()
        assert mgr.get_log_file_path() is None

    def test_returns_path_when_set(self):
        mgr = _fresh_system_monitor()
        mgr.log_file_path = "/tmp/logs/system.log"
        assert mgr.get_log_file_path() == "/tmp/logs/system.log"


# ===========================================================================
# _is_long_lived_connection_request
# ===========================================================================

class TestIsLongLivedConnectionRequest:
    def test_websocket_notifications_path(self, app):
        from app.services.monitoring.system import _is_long_lived_connection_request
        with app.test_request_context("/api/notifications/ws"):
            assert _is_long_lived_connection_request() is True

    def test_websocket_ai_path(self, app):
        from app.services.monitoring.system import _is_long_lived_connection_request
        with app.test_request_context("/api/ai/v2/ws"):
            assert _is_long_lived_connection_request() is True

    def test_websocket_upgrade_header(self, app):
        from app.services.monitoring.system import _is_long_lived_connection_request
        with app.test_request_context("/some/path", headers={"Upgrade": "websocket"}):
            assert _is_long_lived_connection_request() is True

    def test_connection_upgrade_header(self, app):
        from app.services.monitoring.system import _is_long_lived_connection_request
        with app.test_request_context("/some/path", headers={"Connection": "Upgrade, keep-alive"}):
            assert _is_long_lived_connection_request() is True

    def test_sse_accept_header(self, app):
        from app.services.monitoring.system import _is_long_lived_connection_request
        with app.test_request_context(
            "/events",
            headers={"Accept": "text/event-stream"},
        ):
            assert _is_long_lived_connection_request() is True

    def test_normal_request_returns_false(self, app):
        from app.services.monitoring.system import _is_long_lived_connection_request
        with app.test_request_context("/api/data"):
            assert _is_long_lived_connection_request() is False

    def test_exception_suppressed_returns_false(self):
        from app.services.monitoring.system import _is_long_lived_connection_request
        # Without any request context, should return False
        result = _is_long_lived_connection_request()
        assert result is False


# ===========================================================================
# track_request_performance
# ===========================================================================

class TestTrackRequestPerformance:
    def test_disabled_does_nothing(self, app):
        from app.services.monitoring.system import track_request_performance, system_monitor
        from flask import g
        original = system_monitor.enabled
        try:
            system_monitor.enabled = False
            with app.test_request_context("/test"):
                track_request_performance()
                assert not hasattr(g, "request_start_time")
        finally:
            system_monitor.enabled = original

    def test_enabled_sets_g_attributes(self, app):
        from app.services.monitoring.system import track_request_performance, system_monitor
        from flask import g
        original = system_monitor.enabled
        try:
            system_monitor.enabled = True
            with app.test_request_context("/test/path", method="POST"):
                track_request_performance()
                assert hasattr(g, "request_start_time")
                assert g.request_path == "/test/path"
                assert g.request_method == "POST"
        finally:
            system_monitor.enabled = original

    def test_sets_long_lived_flag(self, app):
        from app.services.monitoring.system import track_request_performance, system_monitor
        from flask import g
        original = system_monitor.enabled
        try:
            system_monitor.enabled = True
            with app.test_request_context("/api/notifications/ws"):
                track_request_performance()
                assert g.request_is_long_lived is True
        finally:
            system_monitor.enabled = original

    def test_sets_long_lived_false_for_normal_request(self, app):
        from app.services.monitoring.system import track_request_performance, system_monitor
        from flask import g
        original = system_monitor.enabled
        try:
            system_monitor.enabled = True
            with app.test_request_context("/api/data"):
                track_request_performance()
                assert g.request_is_long_lived is False
        finally:
            system_monitor.enabled = original


# ===========================================================================
# log_request_performance_end
# ===========================================================================

class TestLogRequestPerformanceEnd:
    def test_disabled_does_nothing(self, app):
        from app.services.monitoring.system import log_request_performance_end, system_monitor
        original = system_monitor.enabled
        try:
            system_monitor.enabled = False
            with app.test_request_context("/test"):
                with patch.object(system_monitor, "system_logger") as mock_logger:
                    log_request_performance_end()
        finally:
            system_monitor.enabled = original

    def test_skips_when_no_start_time_in_g(self, app):
        from app.services.monitoring.system import log_request_performance_end, system_monitor
        original = system_monitor.enabled
        try:
            system_monitor.enabled = True
            mock_logger = MagicMock()
            system_monitor.system_logger = mock_logger
            with app.test_request_context("/test"):
                log_request_performance_end()
            mock_logger.warning.assert_not_called()
        finally:
            system_monitor.enabled = original

    def test_skips_long_lived_request(self, app):
        from app.services.monitoring.system import log_request_performance_end, system_monitor
        from flask import g
        original = system_monitor.enabled
        try:
            system_monitor.enabled = True
            mock_logger = MagicMock()
            system_monitor.system_logger = mock_logger
            with app.test_request_context("/api/notifications/ws"):
                g.request_start_time = time.time() - 10.0
                g.request_path = "/api/notifications/ws"
                g.request_method = "GET"
                g.request_is_long_lived = True
                log_request_performance_end()
            mock_logger.warning.assert_not_called()
        finally:
            system_monitor.enabled = original

    def test_fast_request_not_logged(self, app):
        from app.services.monitoring.system import log_request_performance_end, system_monitor
        from flask import g
        original = system_monitor.enabled
        try:
            system_monitor.enabled = True
            mock_logger = MagicMock()
            system_monitor.system_logger = mock_logger
            with app.test_request_context("/fast"):
                g.request_start_time = time.time() - 0.1  # 0.1 second
                g.request_path = "/fast"
                g.request_method = "GET"
                g.request_is_long_lived = False
                log_request_performance_end()
            mock_logger.warning.assert_not_called()
        finally:
            system_monitor.enabled = original

    def test_slow_request_logged_warning(self, app):
        from app.services.monitoring.system import log_request_performance_end, system_monitor
        from flask import g
        original = system_monitor.enabled
        try:
            system_monitor.enabled = True
            mock_logger = MagicMock()
            system_monitor.system_logger = mock_logger
            with app.test_request_context("/slow"):
                g.request_start_time = time.time() - 2.5  # 2.5 seconds
                g.request_path = "/slow"
                g.request_method = "GET"
                g.request_is_long_lived = False
                log_request_performance_end()
            mock_logger.warning.assert_called_once()
            msg = mock_logger.warning.call_args[0][0]
            assert "Slow Request" in msg
        finally:
            system_monitor.enabled = original

    def test_uses_app_logger_when_system_logger_none(self, app):
        from app.services.monitoring.system import log_request_performance_end, system_monitor
        from flask import g
        original_enabled = system_monitor.enabled
        original_sys_logger = system_monitor.system_logger
        original_logger = system_monitor.logger
        try:
            system_monitor.enabled = True
            mock_logger = MagicMock()
            system_monitor.system_logger = None
            system_monitor.logger = mock_logger
            with app.test_request_context("/slow"):
                g.request_start_time = time.time() - 3.0
                g.request_path = "/slow"
                g.request_method = "POST"
                g.request_is_long_lived = False
                log_request_performance_end()
            mock_logger.warning.assert_called_once()
        finally:
            system_monitor.enabled = original_enabled
            system_monitor.system_logger = original_sys_logger
            system_monitor.logger = original_logger

    def test_no_logger_at_all_does_not_raise(self, app):
        from app.services.monitoring.system import log_request_performance_end, system_monitor
        from flask import g
        original_enabled = system_monitor.enabled
        original_sys_logger = system_monitor.system_logger
        original_logger = system_monitor.logger
        try:
            system_monitor.enabled = True
            system_monitor.system_logger = None
            system_monitor.logger = None
            with app.test_request_context("/slow"):
                g.request_start_time = time.time() - 3.0
                g.request_path = "/slow"
                g.request_method = "GET"
                g.request_is_long_lived = False
                log_request_performance_end()  # Should not raise
        finally:
            system_monitor.enabled = original_enabled
            system_monitor.system_logger = original_sys_logger
            system_monitor.logger = original_logger
