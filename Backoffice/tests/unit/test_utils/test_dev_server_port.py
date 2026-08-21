"""Unit tests for dev-server port helpers (Windows double-bind guard)."""

from unittest.mock import MagicMock, patch

from app.utils.dev_server_port import (
    connect_host,
    find_available_port,
    is_reloader_child,
    occupied_server_message,
    pid_listening_on,
    port_has_listener,
    probe_bind,
    should_guard_existing_server,
)


class TestReloaderGuard:
    def test_parent_process_guards(self, monkeypatch):
        monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
        assert is_reloader_child() is False
        assert should_guard_existing_server() is True

    def test_reloader_child_skips_guard(self, monkeypatch):
        monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
        assert is_reloader_child() is True
        assert should_guard_existing_server() is False


class TestConnectHost:
    def test_wildcard_maps_to_loopback(self):
        assert connect_host("0.0.0.0") == "127.0.0.1"
        assert connect_host("::") == "127.0.0.1"
        assert connect_host("") == "127.0.0.1"

    def test_explicit_host_kept(self):
        assert connect_host("127.0.0.1") == "127.0.0.1"


class TestPortHasListener:
    def test_true_when_connect_succeeds(self):
        mock_cm = MagicMock()
        with patch("app.utils.dev_server_port.socket.create_connection", return_value=mock_cm):
            assert port_has_listener("127.0.0.1", 5000) is True
        mock_cm.__enter__.assert_called()

    def test_false_when_connect_fails(self):
        with patch(
            "app.utils.dev_server_port.socket.create_connection",
            side_effect=OSError("refused"),
        ):
            assert port_has_listener("127.0.0.1", 5000) is False


class TestPidListeningOn:
    def test_parses_windows_netstat(self):
        netstat = (
            "  TCP    127.0.0.1:5000         0.0.0.0:0              LISTENING       29124\r\n"
            "  TCP    127.0.0.1:50001        0.0.0.0:0              LISTENING       999\r\n"
        )
        with patch("app.utils.dev_server_port.subprocess.check_output", return_value=netstat):
            assert pid_listening_on(5000) == 29124

    def test_returns_none_when_netstat_fails(self):
        with patch(
            "app.utils.dev_server_port.subprocess.check_output",
            side_effect=OSError("no netstat"),
        ):
            assert pid_listening_on(5000) is None


class TestProbeBind:
    def test_false_on_oserror(self):
        sock = MagicMock()
        sock.bind.side_effect = OSError(10048, "in use")
        with patch("app.utils.dev_server_port.socket.socket", return_value=sock):
            assert probe_bind("127.0.0.1", 5000) is False
        sock.close.assert_called()

    def test_true_when_bind_works(self):
        sock = MagicMock()
        with patch("app.utils.dev_server_port.socket.socket", return_value=sock), patch(
            "app.utils.dev_server_port.os.name", "nt"
        ):
            assert probe_bind("127.0.0.1", 5000) is True
        sock.setsockopt.assert_called()
        sock.bind.assert_called_once_with(("127.0.0.1", 5000))


class TestFindAvailablePort:
    def test_skips_port_with_http_listener(self):
        with patch(
            "app.utils.dev_server_port.port_has_listener",
            side_effect=lambda host, port: port == 5000,
        ), patch(
            "app.utils.dev_server_port.probe_bind",
            side_effect=lambda host, port: port == 5001,
        ):
            assert find_available_port("127.0.0.1", 5000) == 5001

    def test_falls_back_to_start_when_none_free(self):
        with patch("app.utils.dev_server_port.port_has_listener", return_value=True), patch(
            "app.utils.dev_server_port.probe_bind", return_value=False
        ):
            assert find_available_port("127.0.0.1", 5000, max_tries=3) == 5000


class TestOccupiedMessage:
    def test_includes_pid_and_taskkill(self):
        with patch("app.utils.dev_server_port.pid_listening_on", return_value=29124):
            msg = occupied_server_message("127.0.0.1", 5000)
        assert "29124" in msg
        assert "taskkill /F /PID 29124" in msg
        assert "second Flask" in msg
