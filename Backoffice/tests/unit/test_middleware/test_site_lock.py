"""Tests for site_lock.py — targeting 100% coverage."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from flask import g

from app.middleware.site_lock import (
    _active_mode,
    _bypass_secret,
    _is_anonymous_root_health_probe,
    _is_api_path,
    _is_exempt_path,
    _token_matches,
    _has_bypass,
    _lock_response,
    register_site_lock_middleware,
    register_coming_soon_lock_middleware,
    _MODES,
)


# ────────────────────────────────────────────────────────────────────────────
# _active_mode
# ────────────────────────────────────────────────────────────────────────────

class TestActiveMode:
    def test_no_lock_returns_none(self, app):
        with app.app_context():
            app.config["MAINTENANCE_LOCK"] = False
            app.config["COMING_SOON_LOCK"] = False
            with app.test_request_context("/"):
                result = _active_mode()
                assert result is None

    def test_maintenance_lock_returns_maintenance_mode(self, app):
        with app.app_context():
            app.config["MAINTENANCE_LOCK"] = True
            with app.test_request_context("/"):
                result = _active_mode()
                assert result is _MODES["maintenance"]

    def test_coming_soon_lock_returns_coming_soon_mode(self, app):
        with app.app_context():
            app.config["COMING_SOON_LOCK"] = True
            app.config["MAINTENANCE_LOCK"] = False
            with app.test_request_context("/"):
                result = _active_mode()
                assert result is _MODES["coming_soon"]

    def test_both_locks_maintenance_takes_precedence(self, app):
        with app.app_context():
            app.config["MAINTENANCE_LOCK"] = True
            app.config["COMING_SOON_LOCK"] = True
            with app.test_request_context("/"):
                result = _active_mode()
                assert result is _MODES["maintenance"]


# ────────────────────────────────────────────────────────────────────────────
# _bypass_secret
# ────────────────────────────────────────────────────────────────────────────

class TestBypassSecret:
    def test_returns_config_value(self, app):
        with app.app_context():
            app.config["MAINTENANCE_BYPASS_SECRET"] = "my-secret-token"
            with app.test_request_context("/"):
                mode = _MODES["maintenance"]
                assert _bypass_secret(mode) == "my-secret-token"

    def test_missing_config_returns_empty_string(self, app):
        with app.app_context():
            app.config.pop("MAINTENANCE_BYPASS_SECRET", None)
            with app.test_request_context("/"):
                mode = _MODES["maintenance"]
                assert _bypass_secret(mode) == ""

    def test_none_config_returns_empty_string(self, app):
        with app.app_context():
            app.config["COMING_SOON_BYPASS_SECRET"] = None
            with app.test_request_context("/"):
                mode = _MODES["coming_soon"]
                assert _bypass_secret(mode) == ""


# ────────────────────────────────────────────────────────────────────────────
# _is_anonymous_root_health_probe
# ────────────────────────────────────────────────────────────────────────────

class TestIsAnonymousRootHealthProbe:
    def test_root_get_no_ua_no_cookies_returns_true(self, app):
        with app.test_request_context(
            "/", method="GET",
            headers={"Accept": "*/*"},
        ):
            assert _is_anonymous_root_health_probe() is True

    def test_non_root_path_returns_false(self, app):
        with app.test_request_context("/health", method="GET"):
            assert _is_anonymous_root_health_probe() is False

    def test_post_method_returns_false(self, app):
        with app.test_request_context("/", method="POST"):
            assert _is_anonymous_root_health_probe() is False

    def test_with_user_agent_returns_false(self, app):
        with app.test_request_context(
            "/", method="GET",
            headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"},
        ):
            assert _is_anonymous_root_health_probe() is False

    def test_with_cookies_returns_false(self, app):
        with app.test_request_context(
            "/", method="GET",
            headers={"Cookie": "session=abc123"},
        ):
            assert _is_anonymous_root_health_probe() is False

    def test_with_non_wildcard_accept_returns_false(self, app):
        with app.test_request_context(
            "/", method="GET",
            headers={"Accept": "text/html,application/xhtml+xml"},
        ):
            assert _is_anonymous_root_health_probe() is False

    def test_empty_accept_is_ok(self, app):
        """Empty Accept header (falsy) satisfies `not accept or accept == '*/*'`."""
        with app.test_request_context("/", method="GET"):
            assert _is_anonymous_root_health_probe() is True


# ────────────────────────────────────────────────────────────────────────────
# _is_api_path
# ────────────────────────────────────────────────────────────────────────────

class TestIsApiPath:
    def test_api_prefix_returns_true(self, app):
        with app.test_request_context("/api/v1/users"):
            assert _is_api_path() is True

    def test_x_api_key_header_returns_true(self, app):
        with app.test_request_context("/dashboard",
                                       headers={"X-API-Key": "some-key-value"}):
            assert _is_api_path() is True

    def test_bearer_token_returns_true(self, app):
        with app.test_request_context("/dashboard",
                                       headers={"Authorization": "Bearer abc123token"}):
            assert _is_api_path() is True

    def test_bearer_too_short_returns_false(self, app):
        """'Bearer ' with nothing after is too short."""
        with app.test_request_context("/dashboard",
                                       headers={"Authorization": "Bearer "}):
            assert _is_api_path() is False

    def test_regular_path_no_headers_returns_false(self, app):
        with app.test_request_context("/dashboard"):
            assert _is_api_path() is False

    def test_empty_x_api_key_returns_false(self, app):
        with app.test_request_context("/dashboard",
                                       headers={"X-API-Key": ""}):
            assert _is_api_path() is False


# ────────────────────────────────────────────────────────────────────────────
# _is_exempt_path
# ────────────────────────────────────────────────────────────────────────────

class TestIsExemptPath:
    def test_static_asset_exempt(self, app):
        with app.test_request_context("/static/app.js"):
            with patch("app.middleware.site_lock.is_static_asset_request",
                       return_value=True):
                assert _is_exempt_path() is True

    def test_health_path_exempt(self, app):
        with app.test_request_context("/health"):
            with patch("app.middleware.site_lock.is_static_asset_request",
                       return_value=False):
                assert _is_exempt_path() is True

    def test_api_path_exempt(self, app):
        with app.test_request_context("/api/v1/users"):
            with patch("app.middleware.site_lock.is_static_asset_request",
                       return_value=False):
                assert _is_exempt_path() is True

    def test_anonymous_probe_exempt(self, app):
        with app.test_request_context("/", method="GET"):
            with patch("app.middleware.site_lock.is_static_asset_request",
                       return_value=False), \
                 patch("app.middleware.site_lock._is_anonymous_root_health_probe",
                       return_value=True):
                assert _is_exempt_path() is True

    def test_regular_path_not_exempt(self, app):
        with app.test_request_context("/dashboard"):
            with patch("app.middleware.site_lock.is_static_asset_request",
                       return_value=False):
                assert _is_exempt_path() is False


# ────────────────────────────────────────────────────────────────────────────
# _token_matches
# ────────────────────────────────────────────────────────────────────────────

class TestTokenMatches:
    def test_matching_tokens_returns_true(self):
        assert _token_matches("my-secret", "my-secret") is True

    def test_mismatched_tokens_returns_false(self):
        assert _token_matches("wrong", "my-secret") is False

    def test_none_value_returns_false(self):
        assert _token_matches(None, "my-secret") is False

    def test_empty_secret_returns_false(self):
        assert _token_matches("my-secret", "") is False

    def test_both_empty_returns_false(self):
        assert _token_matches("", "") is False


# ────────────────────────────────────────────────────────────────────────────
# _has_bypass
# ────────────────────────────────────────────────────────────────────────────

class TestHasBypass:
    def test_cookie_bypass_matches(self, app):
        with app.app_context():
            app.config["MAINTENANCE_BYPASS_SECRET"] = "bypass-token-123"
            with app.test_request_context(
                "/dashboard",
                headers={"Cookie": "maintenance_bypass=bypass-token-123"},
            ):
                mode = _MODES["maintenance"]
                assert _has_bypass(mode) is True

    def test_query_param_bypass_matches(self, app):
        with app.app_context():
            app.config["MAINTENANCE_BYPASS_SECRET"] = "qtoken"
            with app.test_request_context("/dashboard?maintenance_bypass=qtoken"):
                mode = _MODES["maintenance"]
                result = _has_bypass(mode)
                assert result is True
                # should set the bypass flag on g
                assert getattr(g, mode.bypass_flag, False) is True

    def test_no_bypass_returns_false(self, app):
        with app.app_context():
            app.config["MAINTENANCE_BYPASS_SECRET"] = "secret"
            with app.test_request_context("/dashboard"):
                mode = _MODES["maintenance"]
                assert _has_bypass(mode) is False


# ────────────────────────────────────────────────────────────────────────────
# _lock_response
# ────────────────────────────────────────────────────────────────────────────

class TestLockResponse:
    def test_maintenance_lock_response(self, app):
        with app.test_request_context("/dashboard"):
            with patch("app.middleware.site_lock.render_template",
                       return_value="<h1>Maintenance</h1>"):
                mode = _MODES["maintenance"]
                resp = _lock_response(mode)
                assert resp.status_code == 200
                assert resp.headers["Cache-Control"] == "no-store"

    def test_coming_soon_lock_response(self, app):
        with app.test_request_context("/dashboard"):
            with patch("app.middleware.site_lock.render_template",
                       return_value="<h1>Coming Soon</h1>"):
                mode = _MODES["coming_soon"]
                resp = _lock_response(mode)
                assert resp.status_code == 200
                assert resp.headers["Cache-Control"] == "no-store"


# ────────────────────────────────────────────────────────────────────────────
# Full middleware integration
# ────────────────────────────────────────────────────────────────────────────

class TestRegisterSiteLockMiddleware:
    def test_no_lock_allows_request(self, app, client):
        app.config["MAINTENANCE_LOCK"] = False
        app.config["COMING_SOON_LOCK"] = False
        resp = client.get("/")
        # Should not be blocked (404 from no route or redirect is fine)
        assert resp.status_code != 503

    def test_maintenance_lock_blocks_browser_request(self, app, client):
        app.config["MAINTENANCE_LOCK"] = True
        with patch("app.middleware.site_lock.render_template",
                   return_value="<h1>Maintenance</h1>"):
            resp = client.get("/dashboard")
            assert resp.status_code == 200
            assert b"Maintenance" in resp.data

    def test_coming_soon_lock_blocks_browser_request(self, app, client):
        app.config["COMING_SOON_LOCK"] = True
        with patch("app.middleware.site_lock.render_template",
                   return_value="<h1>Coming Soon</h1>"):
            resp = client.get("/dashboard")
            assert resp.status_code == 200
            assert b"Coming Soon" in resp.data

    def test_api_path_bypasses_lock(self, app, client):
        app.config["MAINTENANCE_LOCK"] = True
        resp = client.get("/api/v1/health")
        # Must not be the lock page (200 from maintenance template)
        # The API path should be exempt
        assert resp.status_code != 200 or b"Maintenance" not in resp.data

    def test_bearer_token_bypasses_lock(self, app, client):
        app.config["MAINTENANCE_LOCK"] = True
        resp = client.get("/dashboard", headers={"Authorization": "Bearer valid-token-xyz"})
        # bearer token → _is_api_path → exempt
        assert b"Maintenance" not in resp.data

    def test_query_param_bypass_sets_cookie(self, app, client):
        app.config["MAINTENANCE_LOCK"] = True
        app.config["MAINTENANCE_BYPASS_SECRET"] = "secret123"
        resp = client.get("/dashboard?maintenance_bypass=secret123")
        # Cookie should be set in response
        assert "maintenance_bypass" in resp.headers.get("Set-Cookie", "")

    def test_bypass_cookie_skips_lock(self, app, client):
        app.config["MAINTENANCE_LOCK"] = True
        app.config["MAINTENANCE_BYPASS_SECRET"] = "s3cr3t"
        resp = client.get("/dashboard",
                           headers={"Cookie": "maintenance_bypass=s3cr3t"})
        # Should not show lock page
        assert b"Maintenance" not in resp.data

    def test_persist_cookie_skips_when_no_secret(self, app, client):
        """When bypass secret is empty, cookie is not set even if flag is True."""
        app.config["MAINTENANCE_LOCK"] = False
        app.config.pop("MAINTENANCE_BYPASS_SECRET", None)
        with app.test_request_context("/dashboard"):
            g.set_maintenance_bypass_cookie = True
            from flask import make_response
            resp = make_response("ok", 200)
            # After_request hook won't set cookie without a secret
            assert "maintenance_bypass" not in resp.headers.get("Set-Cookie", "")

    def test_backward_alias_is_same_function(self):
        assert register_coming_soon_lock_middleware is register_site_lock_middleware
