"""Unit tests for app/utils/ws_helpers.py."""
import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from app.utils.ws_helpers import (
    WsInboundPump,
    check_websocket_origin,
    is_notifications_websocket_enabled,
    is_ws_disconnect_error,
    parse_ws_json,
    release_request_db_session,
    reset_ws_redis_client_for_tests,
)


@pytest.mark.unit
class TestIsNotificationsWebsocketEnabled:
    def test_always_false(self, app):
        """Notification WS is permanently off; WEBSOCKET_ENABLED is for AI only."""
        app.config["WEBSOCKET_ENABLED"] = True
        assert is_notifications_websocket_enabled(app) is False
        assert is_notifications_websocket_enabled() is False
        app.config["WEBSOCKET_ENABLED"] = False
        assert is_notifications_websocket_enabled(app) is False


@pytest.mark.unit
class TestIsWsDisconnectError:
    def test_closed_string(self):
        assert is_ws_disconnect_error(Exception("Connection closed")) is True

    def test_generic_error(self):
        assert is_ws_disconnect_error(Exception("boom")) is False


@pytest.mark.unit
class TestParseWsJson:
    def test_valid_dict(self):
        payload, err = parse_ws_json('{"type":"ping"}')
        assert err is None
        assert payload == {"type": "ping"}

    def test_invalid_json(self):
        payload, err = parse_ws_json("{not-json")
        assert payload is None
        assert err == "Invalid JSON"

    def test_too_large(self):
        raw = '{"x":"' + ("a" * 1000) + '"}'
        payload, err = parse_ws_json(raw, max_bytes=10)
        assert payload is None
        assert err == "Message too large"

    def test_non_object(self):
        payload, err = parse_ws_json("[1,2]")
        assert payload is None
        assert err == "Invalid JSON object"


@pytest.mark.unit
class TestCheckWebsocketOrigin:
    def test_missing_origin_allowed(self, app):
        with app.test_request_context("/api/notifications/ws"):
            ok, err = check_websocket_origin(channel="notifications")
            assert ok is True
            assert err is None

    def test_same_host_allowed(self, app):
        with app.test_request_context(
            "/api/notifications/ws",
            headers={"Origin": "http://localhost"},
            base_url="http://localhost",
        ):
            ok, err = check_websocket_origin(channel="notifications")
            assert ok is True

    def test_foreign_origin_rejected(self, app):
        app.config["CORS_ALLOWED_ORIGINS"] = ["https://allowed.example"]
        with app.test_request_context(
            "/api/notifications/ws",
            headers={"Origin": "https://evil.example"},
            base_url="http://localhost:5000",
        ):
            ok, err = check_websocket_origin(channel="notifications")
            assert ok is False
            assert err

    def test_cors_allowlist(self, app):
        app.config["CORS_ALLOWED_ORIGINS"] = ["https://allowed.example"]
        with app.test_request_context(
            "/api/notifications/ws",
            headers={"Origin": "https://allowed.example"},
            base_url="http://localhost:5000",
        ):
            ok, err = check_websocket_origin(channel="notifications")
            assert ok is True


@pytest.mark.unit
class TestReleaseRequestDbSession:
    def test_safe_without_app_context(self):
        release_request_db_session(reason="test")

    def test_calls_safe_remove(self, app):
        with app.app_context():
            with patch("app.utils.transactions.safe_remove") as mock_remove:
                release_request_db_session(reason="unit_test")
                mock_remove.assert_called_once_with(reason="unit_test")


@pytest.mark.unit
class TestWsInboundPump:
    def test_cancel_sets_generation_event_not_closed(self):
        ws = MagicMock()
        # Soft cancel then idle (None) — must not close the connection.
        ws.receive = MagicMock(side_effect=['{"type":"cancel"}', None, None, None])
        ws.connected = True
        ws.send = MagicMock()

        closed = threading.Event()
        gen = threading.Event()
        pump = WsInboundPump(
            ws,
            closed,
            channel="ai_chat",
            on_cancel=gen.set,
        )
        pump.start()
        deadline = time.time() + 2
        while not gen.is_set() and time.time() < deadline:
            time.sleep(0.01)
        assert gen.is_set()
        assert not closed.is_set()
        pump.stop()

    def test_queues_application_messages(self):
        ws = MagicMock()
        ws.connected = True
        ws.send = MagicMock()
        calls = {"n": 0}

        def _recv(timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return '{"type":"user_message","message":"hi"}'
            return None

        ws.receive = _recv

        closed = threading.Event()
        pump = WsInboundPump(ws, closed, channel="ai_chat")
        pump.start()
        payload, status = pump.wait_message(idle_timeout=2.0)
        assert status == "ok"
        assert payload["type"] == "user_message"
        pump.stop()

    def test_ping_replies_with_pong(self):
        ws = MagicMock()
        ws.connected = True
        ws.send = MagicMock()
        calls = {"n": 0}

        def _recv(timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return '{"type":"ping"}'
            return None

        ws.receive = _recv

        closed = threading.Event()
        pump = WsInboundPump(ws, closed, channel="notifications")
        pump.start()
        deadline = time.time() + 2
        while ws.send.call_count < 1 and time.time() < deadline:
            time.sleep(0.01)
        assert ws.send.call_count >= 1
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["type"] == "pong"
        pump.stop()


@pytest.fixture(autouse=True)
def _reset_redis_cache():
    reset_ws_redis_client_for_tests()
    yield
    reset_ws_redis_client_for_tests()
