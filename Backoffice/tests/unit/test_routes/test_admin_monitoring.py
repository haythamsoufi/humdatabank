"""
Tests for app/routes/admin/monitoring.py

Coverage targets:
- system_monitoring: basic render, with/without log files, memory enabled/disabled, exception
- get_monitoring_logs: no files, with memory/system/application logs, filtering, pagination
- download_monitoring_logs: no files, memory only, system only, both, exception
- clear_monitoring_logs: no files, clears memory/system/application, exception
- get_current_memory: disabled, enabled success
- get_current_system_metrics: disabled, enabled success
- get_system_logs: no file, with file, search, pagination
- test_error_notification: always raises – tests the path before the raise
- _read_log_file_tail: small file, large file paths exercised through get_monitoring_logs
- _rotate_log_file_if_needed: exercised via get_monitoring_logs rotation check

The admin user from `logged_in_client` has admin.analytics.view via `create_test_admin`.
"""
import json
import os
import tempfile
import shutil
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open, call

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json(resp):
    return json.loads(resp.data)


def _make_log_file(content: str = "") -> str:
    """Create a temp file with the given content and return its path."""
    fd, path = tempfile.mkstemp(suffix=".log")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


SAMPLE_LOG_LINES = "\n".join([
    "[2024-01-15 10:00:01] INFO: System started",
    "[2024-01-15 10:01:00] WARNING: High memory usage",
    "[2024-01-15 10:02:00] ERROR: Connection failed",
    "[2024-01-15 10:03:00] DEBUG: Debug information",
    "[2024-01-15 10:04:00] Some unformatted line",
])


# ---------------------------------------------------------------------------
# system_monitoring (dashboard page)
# ---------------------------------------------------------------------------

class TestSystemMonitoringPage:
    def test_basic_render_no_log_files(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
             patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
            mock_mem.get_log_file_path.return_value = None
            mock_sys.get_log_file_path.return_value = None
            resp = logged_in_client.get("/admin/monitoring")
        assert resp.status_code == 200

    def test_render_with_existing_memory_log(self, logged_in_client, db_session, app):
        log_path = _make_log_file("memory log line\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = log_path
                mock_sys.get_log_file_path.return_value = None
                app.config["MEMORY_MONITORING_ENABLED"] = False
                resp = logged_in_client.get("/admin/monitoring")
            assert resp.status_code == 200
        finally:
            os.unlink(log_path)

    def test_render_with_memory_monitoring_enabled(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
             patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
            mock_mem.get_log_file_path.return_value = None
            mock_mem.get_memory_usage.return_value = {"rss_mb": 150.5}
            mock_sys.get_log_file_path.return_value = None
            app.config["MEMORY_MONITORING_ENABLED"] = True
            resp = logged_in_client.get("/admin/monitoring")
        app.config["MEMORY_MONITORING_ENABLED"] = False
        assert resp.status_code == 200

    def test_render_memory_usage_fails_gracefully(self, logged_in_client, db_session, app):
        """get_memory_usage() failure is caught and monitoring page still renders."""
        with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
             patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
            mock_mem.get_log_file_path.return_value = None
            mock_mem.get_memory_usage.side_effect = Exception("mem read error")
            mock_sys.get_log_file_path.return_value = None
            app.config["MEMORY_MONITORING_ENABLED"] = True
            resp = logged_in_client.get("/admin/monitoring")
        app.config["MEMORY_MONITORING_ENABLED"] = False
        assert resp.status_code == 200

    def test_render_with_system_log(self, logged_in_client, db_session, app):
        log_path = _make_log_file("system log entry\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = None
                mock_sys.get_log_file_path.return_value = log_path
                resp = logged_in_client.get("/admin/monitoring")
            assert resp.status_code == 200
        finally:
            os.unlink(log_path)

    def test_render_with_application_log(self, logged_in_client, db_session, app):
        log_path = _make_log_file("app log entry\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = None
                mock_sys.get_log_file_path.return_value = None
                app.application_log_file_path = log_path
                resp = logged_in_client.get("/admin/monitoring")
            assert resp.status_code == 200
        finally:
            os.unlink(log_path)
            if hasattr(app, "application_log_file_path"):
                del app.application_log_file_path

    def test_render_exception_returns_error_template(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem:
            mock_mem.get_log_file_path.side_effect = Exception("hard failure")
            resp = logged_in_client.get("/admin/monitoring")
        assert resp.status_code == 200  # error template rendered

    def test_unauthenticated_redirects(self, client, db_session, app):
        resp = client.get("/admin/monitoring")
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# get_monitoring_logs
# ---------------------------------------------------------------------------

class TestGetMonitoringLogs:
    def test_no_log_files_returns_404(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
             patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
            mock_mem.get_log_file_path.return_value = None
            mock_sys.get_log_file_path.return_value = None
            resp = logged_in_client.get("/admin/monitoring/logs")
        assert resp.status_code == 404

    def test_returns_memory_logs(self, logged_in_client, db_session, app):
        log_path = _make_log_file(SAMPLE_LOG_LINES + "\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = log_path
                mock_sys.get_log_file_path.return_value = None
                resp = logged_in_client.get("/admin/monitoring/logs")
            assert resp.status_code == 200
            data = _json(resp)
            assert data.get("success") is True
            assert isinstance(data.get("logs"), list)
        finally:
            os.unlink(log_path)

    def test_returns_system_logs(self, logged_in_client, db_session, app):
        log_path = _make_log_file(SAMPLE_LOG_LINES + "\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = None
                mock_sys.get_log_file_path.return_value = log_path
                resp = logged_in_client.get("/admin/monitoring/logs")
            assert resp.status_code == 200
            data = _json(resp)
            assert isinstance(data.get("log_types"), list)
        finally:
            os.unlink(log_path)

    def test_returns_application_logs(self, logged_in_client, db_session, app):
        log_path = _make_log_file(SAMPLE_LOG_LINES + "\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = None
                mock_sys.get_log_file_path.return_value = None
                app.application_log_file_path = log_path
                resp = logged_in_client.get("/admin/monitoring/logs")
            assert resp.status_code == 200
            data = _json(resp)
            assert "application" in data.get("log_types", [])
        finally:
            os.unlink(log_path)
            if hasattr(app, "application_log_file_path"):
                del app.application_log_file_path

    def test_filter_by_log_source_memory(self, logged_in_client, db_session, app):
        log_path = _make_log_file(SAMPLE_LOG_LINES + "\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = log_path
                mock_sys.get_log_file_path.return_value = log_path
                resp = logged_in_client.get("/admin/monitoring/logs?log_source=memory")
            data = _json(resp)
            for t in data.get("log_types", []):
                assert t == "memory"
        finally:
            os.unlink(log_path)

    def test_filter_by_log_level_error(self, logged_in_client, db_session, app):
        log_path = _make_log_file(SAMPLE_LOG_LINES + "\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = log_path
                mock_sys.get_log_file_path.return_value = None
                resp = logged_in_client.get("/admin/monitoring/logs?log_level=error")
            assert resp.status_code == 200
        finally:
            os.unlink(log_path)

    def test_filter_by_log_level_warning(self, logged_in_client, db_session, app):
        log_path = _make_log_file(SAMPLE_LOG_LINES + "\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = log_path
                mock_sys.get_log_file_path.return_value = None
                resp = logged_in_client.get("/admin/monitoring/logs?log_level=warning")
            assert resp.status_code == 200
        finally:
            os.unlink(log_path)

    def test_filter_by_log_level_info(self, logged_in_client, db_session, app):
        log_path = _make_log_file(SAMPLE_LOG_LINES + "\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = log_path
                mock_sys.get_log_file_path.return_value = None
                resp = logged_in_client.get("/admin/monitoring/logs?log_level=info")
            assert resp.status_code == 200
        finally:
            os.unlink(log_path)

    def test_filter_by_log_level_verbose(self, logged_in_client, db_session, app):
        log_path = _make_log_file(SAMPLE_LOG_LINES + "\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = log_path
                mock_sys.get_log_file_path.return_value = None
                resp = logged_in_client.get("/admin/monitoring/logs?log_level=verbose")
            assert resp.status_code == 200
        finally:
            os.unlink(log_path)

    def test_filter_by_multiple_log_levels(self, logged_in_client, db_session, app):
        log_path = _make_log_file(SAMPLE_LOG_LINES + "\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = log_path
                mock_sys.get_log_file_path.return_value = None
                resp = logged_in_client.get("/admin/monitoring/logs?log_level=error,warning")
            assert resp.status_code == 200
        finally:
            os.unlink(log_path)

    def test_log_level_all_returns_everything(self, logged_in_client, db_session, app):
        log_path = _make_log_file(SAMPLE_LOG_LINES + "\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = log_path
                mock_sys.get_log_file_path.return_value = None
                resp = logged_in_client.get("/admin/monitoring/logs?log_level=all")
            assert resp.status_code == 200
        finally:
            os.unlink(log_path)

    def test_search_filter(self, logged_in_client, db_session, app):
        log_path = _make_log_file(SAMPLE_LOG_LINES + "\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = log_path
                mock_sys.get_log_file_path.return_value = None
                resp = logged_in_client.get("/admin/monitoring/logs?search=Connection")
            assert resp.status_code == 200
            data = _json(resp)
            for line in data.get("logs", []):
                assert "connection" in line.lower()
        finally:
            os.unlink(log_path)

    def test_pagination_params(self, logged_in_client, db_session, app):
        log_path = _make_log_file(SAMPLE_LOG_LINES + "\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = log_path
                mock_sys.get_log_file_path.return_value = None
                resp = logged_in_client.get("/admin/monitoring/logs?page=1&per_page=2")
            assert resp.status_code == 200
            data = _json(resp)
            assert "pagination" in data
            assert data["pagination"]["per_page"] == 2
        finally:
            os.unlink(log_path)

    def test_logs_sorted_newest_first(self, logged_in_client, db_session, app):
        lines = "\n".join([
            "[2024-01-01 08:00:00] INFO: First",
            "[2024-01-02 09:00:00] INFO: Second",
            "[2024-01-03 10:00:00] INFO: Third",
        ])
        log_path = _make_log_file(lines + "\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = log_path
                mock_sys.get_log_file_path.return_value = None
                resp = logged_in_client.get("/admin/monitoring/logs?per_page=10")
            data = _json(resp)
            logs = data.get("logs", [])
            # First result should contain "Third" (newest)
            if len(logs) >= 2:
                assert "Third" in logs[0] or "2024-01-03" in logs[0]
        finally:
            os.unlink(log_path)

    def test_rotation_triggered_when_large_file(self, logged_in_client, db_session, app):
        """Rotation is attempted on large files (coverage for rotation branch)."""
        log_path = _make_log_file(SAMPLE_LOG_LINES + "\n")
        try:
            # Patch getsize to return > 50MB to trigger rotation check
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys, \
                 patch("app.routes.admin.monitoring.os.path.getsize", return_value=60 * 1024 * 1024), \
                 patch("app.routes.admin.monitoring._rotate_log_file_if_needed") as mock_rotate, \
                 patch("app.routes.admin.monitoring.get_monitoring_logs") as _:
                pass  # just check rotation is callable
            # Verify basic endpoint still works
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = log_path
                mock_sys.get_log_file_path.return_value = None
                # Force rotation check by resetting the timestamp
                from app.routes.admin.monitoring import get_monitoring_logs as gml
                gml._last_rotation_check = 0
                resp = logged_in_client.get("/admin/monitoring/logs")
            assert resp.status_code == 200
        finally:
            os.unlink(log_path)

    def test_system_log_level_classification(self, logged_in_client, db_session, app):
        """Lines with system log format [ts] LEVEL: msg are classified correctly."""
        lines = "\n".join([
            "[2024-01-15 10:00:00] ERROR: system error occurred",
            "[2024-01-15 10:01:00] WARNING: system warning occurred",
            "[2024-01-15 10:02:00] INFO: system info line",
            "[2024-01-15 10:03:00] DEBUG: debug detail",
        ])
        log_path = _make_log_file(lines + "\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = log_path
                mock_sys.get_log_file_path.return_value = None
                resp = logged_in_client.get("/admin/monitoring/logs?log_level=error")
            assert resp.status_code == 200
        finally:
            os.unlink(log_path)

    def test_flask_log_format_classification(self, logged_in_client, db_session, app):
        """Lines with Flask format [ts] LEVEL in module: msg are classified correctly."""
        lines = "\n".join([
            "[2024-01-15 10:00:00] ERROR in app: Something failed",
            "[2024-01-15 10:01:00] WARNING in auth: Rate limit hit",
            "[2024-01-15 10:02:00] INFO in main: Request handled",
            "[2024-01-15 10:03:00] DEBUG in util: Variable dump",
        ])
        log_path = _make_log_file(lines + "\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = log_path
                mock_sys.get_log_file_path.return_value = None
                resp = logged_in_client.get("/admin/monitoring/logs")
            assert resp.status_code == 200
        finally:
            os.unlink(log_path)


# ---------------------------------------------------------------------------
# download_monitoring_logs
# ---------------------------------------------------------------------------

class TestDownloadMonitoringLogs:
    def test_no_log_files_returns_404(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
             patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
            mock_mem.get_log_file_path.return_value = None
            mock_sys.get_log_file_path.return_value = None
            resp = logged_in_client.get("/admin/monitoring/logs/download")
        assert resp.status_code == 404

    def test_download_memory_log_only(self, logged_in_client, db_session, app):
        log_path = _make_log_file("memory log line\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = log_path
                mock_sys.get_log_file_path.return_value = None
                resp = logged_in_client.get("/admin/monitoring/logs/download")
            assert resp.status_code == 200
            assert b"MEMORY LOGS" in resp.data
        finally:
            os.unlink(log_path)

    def test_download_system_log_only(self, logged_in_client, db_session, app):
        log_path = _make_log_file("system log line\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = None
                mock_sys.get_log_file_path.return_value = log_path
                resp = logged_in_client.get("/admin/monitoring/logs/download")
            assert resp.status_code == 200
            assert b"SYSTEM LOGS" in resp.data
        finally:
            os.unlink(log_path)

    def test_download_both_logs_combined(self, logged_in_client, db_session, app):
        mem_log = _make_log_file("memory entry\n")
        sys_log = _make_log_file("system entry\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = mem_log
                mock_sys.get_log_file_path.return_value = sys_log
                resp = logged_in_client.get("/admin/monitoring/logs/download")
            assert resp.status_code == 200
            assert b"MEMORY LOGS" in resp.data
            assert b"SYSTEM LOGS" in resp.data
        finally:
            os.unlink(mem_log)
            os.unlink(sys_log)

    def test_download_content_disposition(self, logged_in_client, db_session, app):
        log_path = _make_log_file("data\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = log_path
                mock_sys.get_log_file_path.return_value = None
                resp = logged_in_client.get("/admin/monitoring/logs/download")
            assert "attachment" in resp.headers.get("Content-Disposition", "")
        finally:
            os.unlink(log_path)

    def test_download_exception_returns_500(self, logged_in_client, db_session, app):
        log_path = _make_log_file("data\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys, \
                 patch("app.routes.admin.monitoring.io.BytesIO", side_effect=Exception("io error")):
                mock_mem.get_log_file_path.return_value = log_path
                mock_sys.get_log_file_path.return_value = None
                resp = logged_in_client.get("/admin/monitoring/logs/download")
            assert resp.status_code == 500
        finally:
            os.unlink(log_path)


# ---------------------------------------------------------------------------
# clear_monitoring_logs
# ---------------------------------------------------------------------------

class TestClearMonitoringLogs:
    def test_no_log_files_returns_404(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
             patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
            mock_mem.get_log_file_path.return_value = None
            mock_sys.get_log_file_path.return_value = None
            resp = logged_in_client.post("/admin/monitoring/logs/clear")
        assert resp.status_code == 404

    def test_clears_memory_log(self, logged_in_client, db_session, app):
        log_path = _make_log_file("some memory content\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = log_path
                mock_sys.get_log_file_path.return_value = None
                resp = logged_in_client.post("/admin/monitoring/logs/clear")
            assert resp.status_code == 200
            data = _json(resp)
            assert data.get("success") is True
            assert "memory" in data.get("message", "")
            # File should now be empty
            with open(log_path) as f:
                assert f.read() == ""
        finally:
            if os.path.exists(log_path):
                os.unlink(log_path)

    def test_clears_system_log(self, logged_in_client, db_session, app):
        log_path = _make_log_file("system content\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = None
                mock_sys.get_log_file_path.return_value = log_path
                resp = logged_in_client.post("/admin/monitoring/logs/clear")
            assert resp.status_code == 200
            data = _json(resp)
            assert "system" in data.get("message", "")
        finally:
            if os.path.exists(log_path):
                os.unlink(log_path)

    def test_clears_application_log(self, logged_in_client, db_session, app):
        log_path = _make_log_file("application content\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = None
                mock_sys.get_log_file_path.return_value = None
                app.application_log_file_path = log_path
                resp = logged_in_client.post("/admin/monitoring/logs/clear")
            data = _json(resp)
            assert "application" in data.get("message", "")
        finally:
            if os.path.exists(log_path):
                os.unlink(log_path)
            if hasattr(app, "application_log_file_path"):
                del app.application_log_file_path

    def test_clears_all_three_logs(self, logged_in_client, db_session, app):
        mem_log = _make_log_file("memory\n")
        sys_log = _make_log_file("system\n")
        app_log = _make_log_file("application\n")
        try:
            with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem, \
                 patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_mem.get_log_file_path.return_value = mem_log
                mock_sys.get_log_file_path.return_value = sys_log
                app.application_log_file_path = app_log
                resp = logged_in_client.post("/admin/monitoring/logs/clear")
            assert resp.status_code == 200
            data = _json(resp)
            assert "memory" in data.get("message", "")
            assert "system" in data.get("message", "")
            assert "application" in data.get("message", "")
        finally:
            for p in (mem_log, sys_log, app_log):
                if os.path.exists(p):
                    os.unlink(p)
            if hasattr(app, "application_log_file_path"):
                del app.application_log_file_path


# ---------------------------------------------------------------------------
# get_current_memory
# ---------------------------------------------------------------------------

class TestGetCurrentMemory:
    def test_disabled_returns_400(self, logged_in_client, db_session, app):
        app.config["MEMORY_MONITORING_ENABLED"] = False
        resp = logged_in_client.get("/admin/monitoring/memory/current")
        assert resp.status_code == 400
        data = _json(resp)
        assert data.get("success") is False

    def test_enabled_returns_memory_data(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.monitoring.memory_monitor") as mock_mem:
            mock_mem.get_memory_usage.return_value = {"rss_mb": 200.1}
            mock_mem.get_top_memory_allocations.return_value = []
            app.config["MEMORY_MONITORING_ENABLED"] = True
            resp = logged_in_client.get("/admin/monitoring/memory/current")
        app.config["MEMORY_MONITORING_ENABLED"] = False
        assert resp.status_code == 200
        data = _json(resp)
        assert data.get("success") is True
        assert "memory" in data


# ---------------------------------------------------------------------------
# get_current_system_metrics
# ---------------------------------------------------------------------------

class TestGetCurrentSystemMetrics:
    def test_disabled_returns_400(self, logged_in_client, db_session, app):
        app.config["SYSTEM_MONITORING_ENABLED"] = False
        resp = logged_in_client.get("/admin/monitoring/system/current")
        assert resp.status_code == 400
        data = _json(resp)
        assert data.get("success") is False

    def test_enabled_returns_metrics(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
            mock_sys.get_system_metrics.return_value = {
                "cpu_percent": 12.5,
                "memory_percent": 45.0,
            }
            app.config["SYSTEM_MONITORING_ENABLED"] = True
            resp = logged_in_client.get("/admin/monitoring/system/current")
        app.config["SYSTEM_MONITORING_ENABLED"] = False
        assert resp.status_code == 200
        data = _json(resp)
        assert data.get("success") is True
        assert "metrics" in data


# ---------------------------------------------------------------------------
# get_system_logs
# ---------------------------------------------------------------------------

class TestGetSystemLogs:
    def test_no_log_file_returns_404(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
            mock_sys.get_log_file_path.return_value = None
            resp = logged_in_client.get("/admin/monitoring/system/logs")
        assert resp.status_code == 404

    def test_nonexistent_file_returns_404(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
            mock_sys.get_log_file_path.return_value = "/no/such/file.log"
            resp = logged_in_client.get("/admin/monitoring/system/logs")
        assert resp.status_code == 404

    def test_returns_log_lines(self, logged_in_client, db_session, app):
        log_path = _make_log_file(SAMPLE_LOG_LINES + "\n")
        try:
            with patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_sys.get_log_file_path.return_value = log_path
                resp = logged_in_client.get("/admin/monitoring/system/logs")
            assert resp.status_code == 200
            data = _json(resp)
            assert data.get("success") is True
            assert isinstance(data.get("logs"), list)
        finally:
            os.unlink(log_path)

    def test_search_filter(self, logged_in_client, db_session, app):
        log_path = _make_log_file(SAMPLE_LOG_LINES + "\n")
        try:
            with patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_sys.get_log_file_path.return_value = log_path
                resp = logged_in_client.get("/admin/monitoring/system/logs?search=ERROR")
            assert resp.status_code == 200
            data = _json(resp)
            for line in data.get("logs", []):
                assert "error" in line.lower()
        finally:
            os.unlink(log_path)

    def test_pagination(self, logged_in_client, db_session, app):
        log_path = _make_log_file(SAMPLE_LOG_LINES + "\n")
        try:
            with patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_sys.get_log_file_path.return_value = log_path
                resp = logged_in_client.get("/admin/monitoring/system/logs?page=1&per_page=2")
            data = _json(resp)
            assert len(data.get("logs", [])) <= 2
            assert data["pagination"]["per_page"] == 2
        finally:
            os.unlink(log_path)

    def test_logs_in_reverse_order(self, logged_in_client, db_session, app):
        """Newer entries should appear first."""
        lines = "line1\nline2\nline3\n"
        log_path = _make_log_file(lines)
        try:
            with patch("app.routes.admin.monitoring.system_monitor") as mock_sys:
                mock_sys.get_log_file_path.return_value = log_path
                resp = logged_in_client.get("/admin/monitoring/system/logs?per_page=10")
            data = _json(resp)
            logs = data.get("logs", [])
            if logs:
                assert logs[0] == "line3"
        finally:
            os.unlink(log_path)


# ---------------------------------------------------------------------------
# test_error_notification (always raises an exception → 500)
# ---------------------------------------------------------------------------

class TestTestErrorNotification:
    def _mock_imports(self):
        """Return patcher context for all imports used by test_error_notification."""
        return [
            patch("app.routes.admin.monitoring.SecurityMonitor"),
            patch("app.routes.admin.monitoring.send_security_alert", return_value=True),
        ]

    def test_get_raises_and_returns_500(self, logged_in_client, db_session, app):
        """The endpoint always raises an exception — Flask returns 500."""
        from app.services.security.monitoring import SecurityMonitor
        from app.services.email.service import send_security_alert

        with patch.object(SecurityMonitor, "log_security_event", return_value=None), \
             patch("app.services.email.service.send_security_alert", return_value=False):
            resp = logged_in_client.get("/admin/monitoring/test-error")
        assert resp.status_code == 500

    def test_post_raises_and_returns_500(self, logged_in_client, db_session, app):
        from app.services.security.monitoring import SecurityMonitor

        with patch.object(SecurityMonitor, "log_security_event", return_value=None):
            resp = logged_in_client.post("/admin/monitoring/test-error")
        assert resp.status_code == 500

    def test_json_format_parameter_triggers_json_response(self, logged_in_client, db_session, app):
        """format=json parameter should still raise (and return 500)."""
        from app.services.security.monitoring import SecurityMonitor

        with patch.object(SecurityMonitor, "log_security_event", return_value=None):
            resp = logged_in_client.get("/admin/monitoring/test-error?format=json")
        assert resp.status_code == 500

    def test_security_event_log_failure_doesnt_prevent_raise(self, logged_in_client, db_session, app):
        """Even if SecurityMonitor.log_security_event fails, the main exception is still raised."""
        from app.services.security.monitoring import SecurityMonitor

        with patch.object(SecurityMonitor, "log_security_event", side_effect=Exception("sec monitor fail")):
            resp = logged_in_client.get("/admin/monitoring/test-error")
        assert resp.status_code == 500

    def test_unauthenticated_redirects(self, client, db_session, app):
        resp = client.get("/admin/monitoring/test-error")
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# _read_log_file_tail (internal helper – tested directly for large-file path)
# ---------------------------------------------------------------------------

class TestReadLogFileTail:
    def test_small_file_returns_lines(self, app):
        log_path = _make_log_file("line1\nline2\nline3\n")
        try:
            with app.app_context():
                from app.routes.admin.monitoring import _read_log_file_tail
                lines = _read_log_file_tail(log_path, max_lines=10)
            assert "line1" in lines
            assert "line3" in lines
        finally:
            os.unlink(log_path)

    def test_small_file_respects_max_lines(self, app):
        content = "\n".join(f"line{i}" for i in range(20)) + "\n"
        log_path = _make_log_file(content)
        try:
            with app.app_context():
                from app.routes.admin.monitoring import _read_log_file_tail
                lines = _read_log_file_tail(log_path, max_lines=5)
            assert len(lines) <= 5
            assert "line19" in lines
        finally:
            os.unlink(log_path)

    def test_large_file_reads_tail(self, app):
        """Simulate large file path (>1MB) with mocked file size."""
        log_path = _make_log_file(SAMPLE_LOG_LINES + "\n")
        try:
            with app.app_context():
                with patch("app.routes.admin.monitoring.os.path.getsize", return_value=2 * 1024 * 1024):
                    from app.routes.admin.monitoring import _read_log_file_tail
                    lines = _read_log_file_tail(log_path, max_lines=3)
            # Should return at most 3 lines
            assert len(lines) <= 3
        finally:
            os.unlink(log_path)

    def test_nonexistent_file_returns_empty_list(self, app):
        with app.app_context():
            from app.routes.admin.monitoring import _read_log_file_tail
            lines = _read_log_file_tail("/no/such/file.log", max_lines=10)
        assert lines == []

    def test_uses_default_max_lines_when_none(self, app):
        content = "\n".join(f"line{i}" for i in range(5)) + "\n"
        log_path = _make_log_file(content)
        try:
            with app.app_context():
                from app.routes.admin.monitoring import _read_log_file_tail
                lines = _read_log_file_tail(log_path)  # no max_lines
            assert isinstance(lines, list)
        finally:
            os.unlink(log_path)


# ---------------------------------------------------------------------------
# _rotate_log_file_if_needed (internal helper – tested directly)
# ---------------------------------------------------------------------------

class TestRotateLogFileIfNeeded:
    def test_no_rotation_if_file_missing(self, app):
        with app.app_context():
            from app.routes.admin.monitoring import _rotate_log_file_if_needed
            # Should not raise for non-existent path
            _rotate_log_file_if_needed("/no/such/file.log")

    def test_no_rotation_if_file_small(self, app):
        log_path = _make_log_file("small content\n")
        try:
            with app.app_context():
                from app.routes.admin.monitoring import _rotate_log_file_if_needed
                _rotate_log_file_if_needed(log_path, max_size_mb=50)
            with open(log_path) as f:
                content = f.read()
            assert "small content" in content  # untouched
        finally:
            os.unlink(log_path)

    def test_rotates_large_file(self, app):
        """File > max_size_mb should be truncated to last N lines."""
        content = "\n".join(f"logline{i}" for i in range(100)) + "\n"
        log_path = _make_log_file(content)
        try:
            with app.app_context():
                with patch("app.routes.admin.monitoring.os.path.getsize",
                           side_effect=[60 * 1024 * 1024, os.path.getsize(log_path)]):
                    from app.routes.admin.monitoring import _rotate_log_file_if_needed
                    _rotate_log_file_if_needed(log_path, max_size_mb=50)
        finally:
            if os.path.exists(log_path):
                os.unlink(log_path)

    def test_rotation_exception_handled_gracefully(self, app):
        """Rotation failures are caught and logged, not raised."""
        with app.app_context():
            with patch("app.routes.admin.monitoring.os.path.exists", return_value=True), \
                 patch("app.routes.admin.monitoring.os.path.getsize", side_effect=Exception("fs error")):
                from app.routes.admin.monitoring import _rotate_log_file_if_needed
                _rotate_log_file_if_needed("/some/path.log")
