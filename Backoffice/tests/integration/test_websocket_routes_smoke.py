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

        # AI WS follows WEBSOCKET_ENABLED (config default is False).
        if not app.config.get("WEBSOCKET_ENABLED", False):
            assert not _path_is_registered(app, "/api/ai/v2/ws")
            return

        assert _path_is_registered(app, "/api/ai/v2/ws")
        assert _path_is_registered(app, "/api/ai/documents/ws")

    def test_notifications_ws_never_registered_on_app_fixture(self, app):
        """Notification bell is HTTP-only; route must not be registered."""
        assert not _path_is_registered(app, "/api/notifications/ws")

    def test_notifications_ws_not_registered_even_when_websocket_enabled(self):
        """WEBSOCKET_ENABLED controls AI only; notifications WS stays off."""
        flask_sock_available = importlib.util.find_spec("flask_sock") is not None
        if not flask_sock_available:
            pytest.skip("flask-sock not installed in this environment")

        from app.routes.notifications_ws import register_notifications_ws

        ws_on_app = Flask(__name__)
        ws_on_app.config["WEBSOCKET_ENABLED"] = True
        ws_on_app.config["WS_MAX_MESSAGE_BYTES"] = 256 * 1024
        register_notifications_ws(ws_on_app)

        assert not _path_is_registered(ws_on_app, "/api/notifications/ws")

    def test_notifications_ws_not_registered_when_websocket_disabled(self):
        flask_sock_available = importlib.util.find_spec("flask_sock") is not None
        if not flask_sock_available:
            pytest.skip("flask-sock not installed in this environment")

        from app.routes.notifications_ws import register_notifications_ws

        ws_off_app = Flask(__name__)
        ws_off_app.config["WEBSOCKET_ENABLED"] = False
        register_notifications_ws(ws_off_app)

        assert not _path_is_registered(ws_off_app, "/api/notifications/ws")
