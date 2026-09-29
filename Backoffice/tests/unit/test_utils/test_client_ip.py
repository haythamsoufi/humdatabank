"""Canonical client-IP resolution (app/utils/client_ip.py) and its ProxyFix wiring."""
from unittest.mock import patch

import pytest
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from app.utils.client_ip import (
    UNKNOWN_CLIENT_IP,
    get_client_ip,
    is_loopback_ip,
    is_loopback_request,
    normalize_ip,
)

pytestmark = [pytest.mark.unit, pytest.mark.auth_security]


def _probe_app(*, x_for=None):
    flask_app = Flask(__name__)

    @flask_app.route("/ip")
    def ip():
        return get_client_ip()

    @flask_app.route("/loopback")
    def loopback():
        return "yes" if is_loopback_request() else "no"

    if x_for is not None:
        flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app, x_for=x_for)
    return flask_app


class TestNormalizeIp:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("203.0.113.9", "203.0.113.9"),
            ("203.0.113.9:4711", "203.0.113.9"),
            ("[2001:db8::1]:443", "2001:db8::1"),
            ("2001:db8::1", "2001:db8::1"),
            ("::ffff:192.0.2.1", "192.0.2.1"),
            ("", UNKNOWN_CLIENT_IP),
            (None, UNKNOWN_CLIENT_IP),
            ("not-an-ip", UNKNOWN_CLIENT_IP),
            ("1.2.3.4, 5.6.7.8", UNKNOWN_CLIENT_IP),
            ("<script>", UNKNOWN_CLIENT_IP),
        ],
    )
    def test_normalize(self, raw, expected):
        assert normalize_ip(raw) == expected


class TestGetClientIpWithoutProxy:
    def test_forwarding_headers_are_never_trusted(self):
        client = _probe_app().test_client()
        resp = client.get(
            "/ip",
            headers={"X-Forwarded-For": "6.6.6.6", "X-Real-IP": "7.7.7.7", "Forwarded": "for=8.8.8.8"},
            environ_overrides={"REMOTE_ADDR": "203.0.113.50"},
        )
        assert resp.get_data(as_text=True) == "203.0.113.50"

    def test_outside_request_context_is_unknown(self):
        assert get_client_ip() == UNKNOWN_CLIENT_IP


class TestGetClientIpBehindProxyFix:
    def test_one_hop_uses_the_address_the_proxy_appended(self):
        client = _probe_app(x_for=1).test_client()
        resp = client.get(
            "/ip",
            headers={"X-Forwarded-For": "6.6.6.6, 198.51.100.4"},
            environ_overrides={"REMOTE_ADDR": "10.0.0.1"},
        )
        assert resp.get_data(as_text=True) == "198.51.100.4"

    def test_spoofed_prefix_cannot_change_the_result(self):
        client = _probe_app(x_for=1).test_client()
        clean = client.get(
            "/ip", headers={"X-Forwarded-For": "198.51.100.4"}, environ_overrides={"REMOTE_ADDR": "10.0.0.1"},
        ).get_data(as_text=True)
        spoofed = client.get(
            "/ip",
            headers={"X-Forwarded-For": "1.1.1.1, 2.2.2.2, 198.51.100.4"},
            environ_overrides={"REMOTE_ADDR": "10.0.0.1"},
        ).get_data(as_text=True)
        assert clean == spoofed == "198.51.100.4"

    def test_two_hops_skip_both_proxies(self):
        client = _probe_app(x_for=2).test_client()
        resp = client.get(
            "/ip",
            headers={"X-Forwarded-For": "9.9.9.9, 198.51.100.4, 10.1.1.1"},
            environ_overrides={"REMOTE_ADDR": "10.0.0.1"},
        )
        assert resp.get_data(as_text=True) == "198.51.100.4"

    def test_azure_style_address_with_port_is_stripped(self):
        client = _probe_app(x_for=1).test_client()
        resp = client.get(
            "/ip",
            headers={"X-Forwarded-For": "198.51.100.4:51234"},
            environ_overrides={"REMOTE_ADDR": "10.0.0.1"},
        )
        assert resp.get_data(as_text=True) == "198.51.100.4"


class TestLoopback:
    @pytest.mark.parametrize("value", ["127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1", "127.5.5.5"])
    def test_loopback_values(self, value):
        assert is_loopback_ip(value) is True

    @pytest.mark.parametrize("value", ["10.0.0.1", "203.0.113.9", "", None, "garbage"])
    def test_non_loopback_values(self, value):
        assert is_loopback_ip(value) is False

    def test_direct_loopback_connection(self):
        client = _probe_app().test_client()
        resp = client.get("/loopback", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
        assert resp.get_data(as_text=True) == "yes"

    @pytest.mark.parametrize("header", ["X-Forwarded-For", "X-Real-IP", "Forwarded"])
    def test_same_host_reverse_proxy_is_not_loopback(self, header):
        """A local nginx/Azure sidecar relays remote clients from 127.0.0.1 with forwarding headers."""
        client = _probe_app().test_client()
        resp = client.get(
            "/loopback", headers={header: "203.0.113.9"}, environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
        )
        assert resp.get_data(as_text=True) == "no"

    def test_remote_address_is_not_loopback(self):
        client = _probe_app().test_client()
        resp = client.get("/loopback", environ_overrides={"REMOTE_ADDR": "203.0.113.9"})
        assert resp.get_data(as_text=True) == "no"

    def test_no_request_context_is_not_loopback(self):
        assert is_loopback_request() is False


class TestSingleSourceOfTruth:
    def test_analytics_service_delegates_to_canonical_function(self):
        from app.services.platform import user_analytics_service

        assert user_analytics_service.get_client_ip is get_client_ip

    def test_rate_limiting_uses_canonical_function(self):
        from app.utils import rate_limiting

        assert rate_limiting.get_client_ip is get_client_ip

    def test_flask_limiter_key_func_is_canonical(self):
        from app.extensions import limiter

        assert limiter._key_func is get_client_ip


class TestCreateAppProxyWiring:
    """create_app applies ProxyFix with the configured hop counts (staging included)."""

    @staticmethod
    def _wsgi_layers(flask_app):
        layers = []
        wsgi = flask_app.wsgi_app
        while wsgi is not None:
            layers.append(wsgi)
            wsgi = getattr(wsgi, "app", None)
        return layers

    def _create(self, **overrides):
        from app import create_app
        from config.config import TestingConfig

        attrs = {"TRUST_PROXY_HEADERS": True, "PROXY_FIX_X_FOR": 1, "PROXY_FIX_X_PROTO": 1,
                 "PROXY_FIX_X_HOST": 1, "PROXY_FIX_X_PORT": 1, "PROXY_FIX_X_PREFIX": 1}
        attrs.update(overrides)
        config_cls = type("ProxyTestConfig", (TestingConfig,), attrs)
        with patch.dict("config.config.config", {"_proxy_test": config_cls}):
            return create_app("_proxy_test")

    def test_proxyfix_hops_come_from_config(self):
        flask_app = self._create(PROXY_FIX_X_FOR=2)
        fixes = [layer for layer in self._wsgi_layers(flask_app) if isinstance(layer, ProxyFix)]
        assert len(fixes) == 1
        assert fixes[0].x_for == 2

    def test_proxyfix_not_applied_when_untrusted(self):
        flask_app = self._create(TRUST_PROXY_HEADERS=False)
        assert not [layer for layer in self._wsgi_layers(flask_app) if isinstance(layer, ProxyFix)]

    def test_forged_header_ignored_end_to_end(self):
        flask_app = self._create(PROXY_FIX_X_FOR=1)

        @flask_app.route("/_ip_probe")
        def _ip_probe():
            return get_client_ip()

        resp = flask_app.test_client().get(
            "/_ip_probe",
            headers={"X-Forwarded-For": "1.1.1.1, 198.51.100.77"},
            environ_overrides={"REMOTE_ADDR": "10.0.0.1"},
        )
        assert resp.get_data(as_text=True) == "198.51.100.77"
