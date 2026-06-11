"""Tests for security_headers.py — targeting 100% coverage."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from app.middleware.security_headers import add_security_headers, init_security_headers


class TestAddSecurityHeaders:
    # ── Static file handling ─────────────────────────────────────────────

    def test_skip_cache_override_flag_preserves_cache_headers(self, app, client):
        """Response with _skip_cache_override=True must not have cache headers modified."""
        with app.test_request_context("/static/app.js"):
            from flask import make_response
            response = make_response("js content", 200)
            response._skip_cache_override = True
            response.headers["Cache-Control"] = "max-age=3600"

            result = add_security_headers(response)
            # Cache-Control must stay as set, not replaced with no-cache
            assert result.headers["Cache-Control"] == "max-age=3600"

    def test_static_endpoint_preserves_cache_headers(self, app):
        with app.test_request_context("/static/style.css", method="GET"):
            from flask import make_response
            response = make_response("css", 200)
            response.headers["Cache-Control"] = "max-age=86400"

            result = add_security_headers(response)
            assert result.headers["Cache-Control"] == "max-age=86400"

    def test_static_path_preserves_cache_headers(self, app):
        with app.test_request_context("/static/images/logo.png"):
            from flask import make_response
            response = make_response("img", 200)
            response.headers["Cache-Control"] = "max-age=86400"
            result = add_security_headers(response)
            assert result.headers["Cache-Control"] == "max-age=86400"

    def test_dynamic_response_gets_no_cache(self, app):
        with app.test_request_context("/dashboard"):
            from flask import make_response
            response = make_response("html", 200)
            # No Cache-Control set
            result = add_security_headers(response)
            assert "no-cache" in result.headers.get("Cache-Control", "")

    def test_dynamic_response_with_existing_cache_control_not_overwritten(self, app):
        with app.test_request_context("/dashboard"):
            from flask import make_response
            response = make_response("html", 200)
            response.headers["Cache-Control"] = "private, no-store"
            result = add_security_headers(response)
            # Pre-existing header preserved
            assert result.headers["Cache-Control"] == "private, no-store"

    # ── Security headers always present ─────────────────────────────────

    def test_x_frame_options_deny(self, app):
        with app.test_request_context("/dashboard"):
            from flask import make_response
            result = add_security_headers(make_response("ok", 200))
            assert result.headers["X-Frame-Options"] == "DENY"

    def test_x_content_type_options_nosniff(self, app):
        with app.test_request_context("/dashboard"):
            from flask import make_response
            result = add_security_headers(make_response("ok", 200))
            assert result.headers["X-Content-Type-Options"] == "nosniff"

    def test_xss_protection_header(self, app):
        with app.test_request_context("/dashboard"):
            from flask import make_response
            result = add_security_headers(make_response("ok", 200))
            assert result.headers["X-XSS-Protection"] == "1; mode=block"

    def test_referrer_policy_header(self, app):
        with app.test_request_context("/dashboard"):
            from flask import make_response
            result = add_security_headers(make_response("ok", 200))
            assert result.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_permissions_policy_header(self, app):
        with app.test_request_context("/dashboard"):
            from flask import make_response
            result = add_security_headers(make_response("ok", 200))
            assert "Permissions-Policy" in result.headers

    def test_server_header_removed(self, app):
        with app.test_request_context("/dashboard"):
            from flask import make_response
            response = make_response("ok", 200)
            response.headers["Server"] = "nginx/1.18"
            result = add_security_headers(response)
            assert "Server" not in result.headers

    def test_x_app_origin_header(self, app):
        with app.test_request_context("/dashboard"):
            from flask import make_response
            result = add_security_headers(make_response("ok", 200))
            assert result.headers["X-App-Origin"] == "1"

    def test_csp_header_present(self, app):
        with app.test_request_context("/dashboard"):
            from flask import make_response
            result = add_security_headers(make_response("ok", 200))
            assert "Content-Security-Policy" in result.headers

    def test_csp_contains_self_directive(self, app):
        with app.test_request_context("/dashboard"):
            from flask import make_response
            result = add_security_headers(make_response("ok", 200))
            csp = result.headers["Content-Security-Policy"]
            assert "'self'" in csp

    # ── HTTPS / HSTS ─────────────────────────────────────────────────────

    def test_hsts_header_added_for_https(self, app):
        """HSTS should be set for secure (HTTPS) requests."""
        with app.test_request_context("/dashboard",
                                       environ_base={"wsgi.url_scheme": "https"}):
            from flask import make_response
            result = add_security_headers(make_response("ok", 200))
            assert "Strict-Transport-Security" in result.headers
            assert "max-age=31536000" in result.headers["Strict-Transport-Security"]

    def test_hsts_header_absent_for_http(self, app):
        """HSTS should NOT be set for insecure (HTTP) requests."""
        with app.test_request_context("/dashboard",
                                       environ_base={"wsgi.url_scheme": "http"}):
            from flask import make_response
            result = add_security_headers(make_response("ok", 200))
            assert "Strict-Transport-Security" not in result.headers

    # ── CSP nonce failure path ────────────────────────────────────────────

    def test_csp_nonce_failure_falls_back_gracefully(self, app):
        """When get_csp_nonce() raises, CSP header is still set (without nonce)."""
        with app.test_request_context("/dashboard"):
            with patch("app.middleware.security_headers.get_csp_nonce",
                       side_effect=Exception("nonce service down")):
                from flask import make_response
                result = add_security_headers(make_response("ok", 200))
                # CSP must still be present even if nonce generation fails
                assert "Content-Security-Policy" in result.headers
                csp = result.headers["Content-Security-Policy"]
                # nonce directive should be absent
                assert "nonce-" not in csp

    # ── init_security_headers ─────────────────────────────────────────────

    def test_init_registers_after_request(self):
        """init_security_headers registers the after_request hook."""
        mock_app = MagicMock()
        init_security_headers(mock_app)
        mock_app.after_request.assert_called_once_with(add_security_headers)
