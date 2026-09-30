"""Production-safety behaviour of app/error_handlers.py: generic client messages, request IDs, sanitized events."""

from __future__ import annotations

import json
import re
from unittest.mock import patch

import pytest

JSON_HEADERS = {"Accept": "application/json"}
SECRET = "SUPER-SECRET-VALUE-42"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


@pytest.fixture
def prod_mode(app, monkeypatch):
    monkeypatch.setitem(app.config, "DEBUG", False)
    monkeypatch.setitem(app.config, "PROPAGATE_EXCEPTIONS", False)
    return app


def _boom(*_args, **_kwargs):
    raise ValueError(f"could not connect: password={SECRET} host=db.internal")


class TestRequestId:
    def test_every_response_carries_request_id(self, client):
        resp = client.get("/this-path-does-not-exist-at-all")
        assert _REQUEST_ID_RE.match(resp.headers["X-Request-ID"])

    def test_well_formed_inbound_id_is_reused(self, client):
        resp = client.get("/test-error/404", headers={**JSON_HEADERS, "X-Request-ID": "abc-123_DEF.456"})
        assert resp.headers["X-Request-ID"] == "abc-123_DEF.456"
        assert resp.get_json()["request_id"] == "abc-123_DEF.456"

    @pytest.mark.parametrize("bad", ["x", "has space and\ttabs", "a" * 200, "evil\r\nX-Injected: 1", "<script>alert(1)</script>"])
    def test_malformed_inbound_id_is_replaced(self, client, bad):
        resp = client.get("/test-error/404", headers={**JSON_HEADERS, "X-Request-ID": bad.replace("\r\n", "")})
        assert resp.headers["X-Request-ID"] != bad
        assert _REQUEST_ID_RE.match(resp.headers["X-Request-ID"])


class TestJsonEnvelope:
    @pytest.mark.parametrize("code,title", [(401, "Unauthorized"), (403, "Forbidden"), (404, "Not Found"),
                                             (500, "Internal Server Error"), (502, "Bad Gateway"),
                                             (503, "Service Unavailable")])
    def test_consistent_shape(self, client, code, title):
        resp = client.get(f"/test-error/{code}", headers=JSON_HEADERS)
        data = resp.get_json()
        assert resp.status_code == code
        assert data["success"] is False
        assert data["error"] == title
        assert data["message"]
        assert data["error_code"] == code
        assert data["request_id"] == resp.headers["X-Request-ID"]

    def test_405_json_keeps_allow_header(self, client):
        resp = client.post("/test-error/404", headers=JSON_HEADERS)
        assert resp.status_code == 405
        data = resp.get_json()
        assert data["error"] == "Method Not Allowed"
        assert "GET" in resp.headers["Allow"]

    def test_405_html(self, client):
        resp = client.post("/test-error/404", headers={"Accept": "text/html"})
        assert resp.status_code == 405
        assert b"405" in resp.data
        assert "GET" in resp.headers["Allow"]

    def test_429_json_and_retry_after(self, app, client, monkeypatch):
        from werkzeug.exceptions import TooManyRequests

        def limited():
            raise TooManyRequests(retry_after=30)

        monkeypatch.setitem(app.view_functions, "_error_triggers.trigger_404", limited)
        resp = client.get("/test-error/404", headers=JSON_HEADERS)
        assert resp.status_code == 429
        assert resp.headers["Retry-After"] == "30"
        data = resp.get_json()
        assert data["error"] == "Too Many Requests"
        assert data["retry_after"] == 30

    def test_413_json(self, app, client, monkeypatch):
        from werkzeug.exceptions import RequestEntityTooLarge

        def too_big():
            raise RequestEntityTooLarge()

        monkeypatch.setitem(app.view_functions, "_error_triggers.trigger_404", too_big)
        resp = client.get("/test-error/404", headers=JSON_HEADERS)
        assert resp.status_code == 413
        assert resp.get_json()["error"] == "Payload Too Large"


class TestBadRequestDoesNotLeakParserDetail:
    def test_malformed_json_body_gets_generic_message_in_production(self, app, prod_mode, client, monkeypatch):
        def parse():
            from flask import request
            return request.get_json()

        monkeypatch.setitem(app.view_functions, "_error_triggers.trigger_csrf", parse)
        resp = client.post(
            "/test-error/csrf",
            data='{"password": "x", broken',
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        assert resp.status_code == 400
        body = resp.get_data(as_text=True)
        assert "Expecting" not in body and "decode" not in body.lower()
        assert resp.get_json()["message"] == "The request was invalid or malformed."

    def test_description_is_hidden_when_not_debug(self, app, prod_mode, client):
        from werkzeug.exceptions import BadRequest

        def bad():
            raise BadRequest(description="Failed to decode JSON object: Expecting value: line 1 column 1 (char 0)")

        with patch.dict(app.view_functions, {"_error_triggers.trigger_400": bad}):
            resp = client.get("/test-error/400", headers=JSON_HEADERS)
        assert resp.status_code == 400
        body = resp.get_data(as_text=True)
        assert "decode" not in body and "char 0" not in body
        data = resp.get_json()
        assert data["message"] == "The request was invalid or malformed."
        assert "detail" not in data

    def test_description_is_returned_in_debug(self, app, client, monkeypatch):
        from werkzeug.exceptions import BadRequest

        monkeypatch.setitem(app.config, "DEBUG", True)

        def bad():
            raise BadRequest(description="specific parser detail")

        with patch.dict(app.view_functions, {"_error_triggers.trigger_400": bad}):
            resp = client.get("/test-error/400", headers=JSON_HEADERS)
        assert resp.get_json()["detail"] == "specific parser detail"


class TestInternalErrorPersistence:
    def _trigger(self, app, client, accept="application/json", path="/test-error/500?token=abc123&keep=1"):
        with patch.dict(app.view_functions, {"_error_triggers.trigger_500": _boom}), \
             patch("app.services.security.monitoring.SecurityMonitor.log_security_event") as log_event:
            resp = client.get(path, headers={"Accept": accept})
        return resp, log_event

    def test_client_never_sees_exception_text(self, prod_mode, client):
        resp, _ = self._trigger(prod_mode, client)
        assert resp.status_code == 500
        assert SECRET not in resp.get_data(as_text=True)
        assert "db.internal" not in resp.get_data(as_text=True)
        assert resp.get_json()["request_id"] == resp.headers["X-Request-ID"]

    def test_html_error_page_shows_reference_id(self, prod_mode, client):
        resp, _ = self._trigger(prod_mode, client, accept="text/html")
        assert resp.status_code == 500
        assert resp.headers["X-Request-ID"] in resp.get_data(as_text=True)
        assert SECRET not in resp.get_data(as_text=True)

    def test_security_event_has_no_exception_text_or_query_secrets(self, prod_mode, client):
        resp, log_event = self._trigger(prod_mode, client)
        log_event.assert_called_once()
        kwargs = log_event.call_args.kwargs
        stored = json.dumps({"description": kwargs["description"], "context": kwargs["context_data"]})
        assert SECRET not in stored
        assert "abc123" not in stored
        ctx = kwargs["context_data"]
        assert ctx["exception_type"] == "ValueError"
        assert ctx["request_id"] == resp.headers["X-Request-ID"]
        assert len(ctx["traceback_hash"]) == 32
        assert "traceback" not in ctx
        assert any("_boom" in frame for frame in ctx["traceback_frames"])

    def test_full_detail_is_kept_in_server_log_with_request_id(self, prod_mode, client, caplog):
        with caplog.at_level("ERROR"):
            resp, _ = self._trigger(prod_mode, client)
        logged = "\n".join(r.getMessage() + (r.exc_text or "") for r in caplog.records)
        assert f"request_id={resp.headers['X-Request-ID']}" in logged


class TestForbiddenEventUrlRedaction:
    def test_403_event_redacts_query_secrets(self, prod_mode, client):
        with patch("app.services.security.monitoring.SecurityMonitor.log_security_event") as log_event:
            client.get("/test-error/403?access_token=tok-123&x=1", headers=JSON_HEADERS)
        ctx = log_event.call_args.kwargs["context_data"]
        assert "tok-123" not in ctx["url"]
        assert "x=1" in ctx["url"]
        assert ctx["request_id"]
