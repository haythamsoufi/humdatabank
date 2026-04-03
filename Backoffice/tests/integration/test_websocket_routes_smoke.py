import importlib.util

import pytest
from flask import Flask


def _path_is_registered(app, path: str) -> bool:
    return any(getattr(r, "rule", None) == path for r in app.url_map.iter_rules())


@pytest.mark.integration
class TestWebSocketRoutesSmoke:
    def test_ai_ws_routes_registered_when_flask_sock_available(self, app):
        flask_sock_available = importlib.util.find_spec("flask_sock") is not None
        if not flask_sock_available:
            pytest.skip("flask-sock not installed in this environment")

        assert _path_is_registered(app, "/api/ai/v2/ws")
        assert _path_is_registered(app, "/api/ai/documents/ws")

    def test_notifications_ws_route_registered_when_enabled_and_flask_sock_available(self, app):
        flask_sock_available = importlib.util.find_spec("flask_sock") is not None
        if not flask_sock_available:
            pytest.skip("flask-sock not installed in this environment")

        # Some test environments intentionally disable websockets.
        if not app.config.get("WEBSOCKET_ENABLED", True):
            assert not _path_is_registered(app, "/api/notifications/ws")
            return

        assert _path_is_registered(app, "/api/notifications/ws")

    def test_notifications_ws_not_registered_when_websocket_disabled(self, monkeypatch):
        """
        Ensure register function is conditional on WEBSOCKET_ENABLED.
        This is a pure registration check (no WS connection needed).
        """
        flask_sock_available = importlib.util.find_spec("flask_sock") is not None
        if not flask_sock_available:
            pytest.skip("flask-sock not installed in this environment")

        from app.routes.notifications_ws import register_notifications_ws

        ws_off_app = Flask(__name__)
        ws_off_app.config["WEBSOCKET_ENABLED"] = False
        register_notifications_ws(ws_off_app)

        assert not _path_is_registered(ws_off_app, "/api/notifications/ws")

