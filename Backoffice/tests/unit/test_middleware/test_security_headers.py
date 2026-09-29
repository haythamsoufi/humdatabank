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
            assert result.headers["X-XSS-Protection"] == "0"

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
        with app.test_request_context("/dashboard", base_url="https://localhost"):
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
            with patch("app.utils.csp_nonce.get_csp_nonce",
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


def _csp_directives(csp):
    return {d.split()[0]: d.split()[1:] for d in (part.strip() for part in csp.split(";")) if d}


def _headers(app, path="/dashboard", secure=False, mimetype="text/html", **env):
    from flask import make_response

    kwargs = {"base_url": "https://localhost"} if secure else {}
    with app.test_request_context(path, **kwargs):
        response = make_response("ok", 200)
        response.mimetype = mimetype
        return add_security_headers(response)


class TestHardenedDirectives:
    def test_object_src_none_and_base_uri_form_action_frame_ancestors(self, app):
        d = _csp_directives(_headers(app).headers["Content-Security-Policy"])
        assert d["object-src"] == ["'none'"]
        assert d["base-uri"] == ["'self'"]
        assert d["form-action"] == ["'self'"]
        assert d["frame-ancestors"] == ["'none'"]
        assert d["default-src"] == ["'self'"]

    def test_scripts_never_allow_unsafe_inline_or_eval(self, app):
        d = _csp_directives(_headers(app).headers["Content-Security-Policy"])
        assert "'unsafe-inline'" not in d["script-src"]
        assert "'unsafe-eval'" not in d["script-src"]
        assert any(src.startswith("'nonce-") for src in d["script-src"])

    def test_no_wildcard_or_scheme_only_sources_in_script_connect_frame(self, app):
        d = _csp_directives(_headers(app).headers["Content-Security-Policy"])
        for name in ("script-src", "connect-src", "frame-src"):
            assert "*" not in d[name]
            assert "https:" not in d[name] and "http:" not in d[name]

    def test_upgrade_insecure_requests_only_over_https(self, app):
        assert "upgrade-insecure-requests" not in _headers(app).headers["Content-Security-Policy"]
        assert "upgrade-insecure-requests" in _headers(app, secure=True).headers["Content-Security-Policy"]

    def test_default_img_src_is_unchanged_https(self, app):
        d = _csp_directives(_headers(app).headers["Content-Security-Policy"])
        assert "https:" in d["img-src"]

    def test_no_report_only_header_by_default(self, app):
        assert "Content-Security-Policy-Report-Only" not in _headers(app).headers


class TestStrictMode:
    def test_report_only_emits_strict_candidate_next_to_enforced_policy(self, app, monkeypatch):
        monkeypatch.setitem(app.config, "CSP_STRICT_MODE", "report-only")
        headers = _headers(app).headers
        enforced = _csp_directives(headers["Content-Security-Policy"])
        candidate = _csp_directives(headers["Content-Security-Policy-Report-Only"])
        assert "https:" in enforced["img-src"]
        assert "https:" not in candidate["img-src"]
        assert "https://code.jquery.com" not in candidate["script-src"]
        assert "https://unpkg.com" not in candidate["script-src"]
        assert "https://unpkg.com/swagger-ui-dist@5.9.0/" in candidate["script-src"]

    def test_enforce_replaces_the_enforced_policy(self, app, monkeypatch):
        monkeypatch.setitem(app.config, "CSP_STRICT_MODE", "enforce")
        headers = _headers(app).headers
        assert "https:" not in _csp_directives(headers["Content-Security-Policy"])["img-src"]
        assert "Content-Security-Policy-Report-Only" not in headers

    def test_unknown_mode_falls_back_to_off(self, app, monkeypatch):
        monkeypatch.setitem(app.config, "CSP_STRICT_MODE", "bogus")
        assert "Content-Security-Policy-Report-Only" not in _headers(app).headers

    def test_extra_sources_are_validated_against_header_injection(self, app, monkeypatch):
        monkeypatch.setitem(
            app.config, "CSP_IMG_SRC_EXTRA",
            "https://images.example.org http://insecure.example.org * 'unsafe-inline' https://ok.example.org;script-src",
        )
        img = _csp_directives(_headers(app).headers["Content-Security-Policy"])["img-src"]
        assert "https://images.example.org" in img
        assert "http://insecure.example.org" not in img
        assert "'unsafe-inline'" not in img
        assert "https://ok.example.org;script-src" not in img


class TestBaselineHeaders:
    def test_cross_origin_isolation_and_misc_headers(self, app):
        h = _headers(app).headers
        assert h["Cross-Origin-Opener-Policy"] == "same-origin-allow-popups"
        assert h["Cross-Origin-Resource-Policy"] == "same-origin"
        assert h["X-Permitted-Cross-Domain-Policies"] == "none"
        assert h["X-Frame-Options"] == "DENY"
        assert h["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_corp_not_applied_to_json_or_static(self, app):
        assert "Cross-Origin-Resource-Policy" not in _headers(app, mimetype="application/json").headers
        assert "Cross-Origin-Resource-Policy" not in _headers(app, path="/static/a.html").headers

    def test_permissions_policy_denies_powerful_features(self, app):
        pp = _headers(app).headers["Permissions-Policy"]
        for feature in ("camera=()", "microphone=()", "payment=()", "usb=()", "display-capture=()", "geolocation=(self)"):
            assert feature in pp

    def test_hsts_includes_subdomains_and_one_year(self, app):
        hsts = _headers(app, secure=True).headers["Strict-Transport-Security"]
        assert "max-age=31536000" in hsts and "includeSubDomains" in hsts

    def test_plugin_override_path_still_gets_baseline_headers(self, app):
        from types import SimpleNamespace

        override = SimpleNamespace(policy="default-src 'self'")
        with patch.object(app, "plugin_manager", create=True) as pm:
            pm.get_csp_override.return_value = override
            h = _headers(app, secure=True).headers
        assert h["Content-Security-Policy"] == "default-src 'self'"
        assert h["X-Frame-Options"] == "SAMEORIGIN"
        assert h["Cross-Origin-Opener-Policy"] == "same-origin-allow-popups"
        assert "Permissions-Policy" in h
        assert "Strict-Transport-Security" in h
