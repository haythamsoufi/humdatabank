"""Cookie-session persistence: keep Azure ID tokens out of the Flask cookie."""

from unittest.mock import patch

import pytest
from flask import session

from app.utils.session_persistence import (
    B2C_ID_TOKEN_SESSION_KEY,
    BROWSER_COOKIE_MAX_BYTES,
    first_party_post_login_response,
    log_oversized_session_cookie,
    migrate_oauth_logout_hint_from_session,
    pop_oauth_logout_hint,
    reset_oauth_logout_hint_cache_for_tests,
    session_set_cookie_bytes,
    store_oauth_logout_hint,
)


@pytest.fixture(autouse=True)
def _clear_hint_cache():
    reset_oauth_logout_hint_cache_for_tests()
    yield
    reset_oauth_logout_hint_cache_for_tests()


@pytest.mark.unit
class TestOAuthLogoutHintStore:
    def test_store_and_pop_round_trip(self, app):
        with app.app_context():
            store_oauth_logout_hint("sid-1", "id-token-value")
            assert pop_oauth_logout_hint("sid-1") == "id-token-value"
            assert pop_oauth_logout_hint("sid-1") is None

    def test_store_ignores_empty(self, app):
        with app.app_context():
            store_oauth_logout_hint("", "token")
            store_oauth_logout_hint("sid", "")
            assert pop_oauth_logout_hint("sid") is None


@pytest.mark.unit
class TestMigrateOAuthTokenFromCookie:
    def test_moves_token_when_session_id_present(self, app):
        with app.test_request_context("/"):
            session[B2C_ID_TOKEN_SESSION_KEY] = "legacy-jwt"
            session["session_id"] = "sid-migrate"
            assert migrate_oauth_logout_hint_from_session() is True
            assert B2C_ID_TOKEN_SESSION_KEY not in session
            assert pop_oauth_logout_hint("sid-migrate") == "legacy-jwt"

    def test_leaves_token_when_session_id_missing(self, app):
        with app.test_request_context("/"):
            session[B2C_ID_TOKEN_SESSION_KEY] = "legacy-jwt"
            assert migrate_oauth_logout_hint_from_session() is False
            assert session.get(B2C_ID_TOKEN_SESSION_KEY) == "legacy-jwt"

    def test_noop_when_absent(self, app):
        with app.test_request_context("/"):
            assert migrate_oauth_logout_hint_from_session() is False


@pytest.mark.unit
class TestFirstPartyPostLoginResponse:
    def test_renders_continue_page_with_safe_next(self, app):
        with app.test_request_context("/auth/azure/callback"):
            resp = first_party_post_login_response("/admin/")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "/admin/" in body
        assert "window.location.replace" in body
        assert resp.headers["Cache-Control"].startswith("no-store")

    def test_rejects_external_next(self, app):
        with app.test_request_context("/auth/azure/callback"):
            resp = first_party_post_login_response("https://evil.example/phish")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "evil.example" not in body
        assert "/" in body


@pytest.mark.unit
class TestSessionCookieSize:
    def test_id_token_in_cookie_exceeds_browser_limit(self, app, logged_in_client):
        """Document why the Azure ID token must not live in the Flask cookie."""
        with logged_in_client.session_transaction() as sess:
            sess[B2C_ID_TOKEN_SESSION_KEY] = "e" * 2800
        resp = logged_in_client.get("/login")
        size = session_set_cookie_bytes(resp)
        assert size >= BROWSER_COOKIE_MAX_BYTES

    def test_request_strips_legacy_token_and_keeps_login(self, logged_in_client, app):
        token = "e" * 2800
        with logged_in_client.session_transaction() as sess:
            sess[B2C_ID_TOKEN_SESSION_KEY] = token
            sess["session_id"] = "sid-live"
        resp = logged_in_client.get("/login")
        assert resp.status_code == 302
        assert "login" not in (resp.headers.get("Location") or "").lower()
        with logged_in_client.session_transaction() as sess:
            assert B2C_ID_TOKEN_SESSION_KEY not in sess
            assert sess.get("_user_id")
        assert pop_oauth_logout_hint("sid-live") == token
        follow = logged_in_client.get("/login", follow_redirects=False)
        size = session_set_cookie_bytes(follow)
        if size:
            assert size < BROWSER_COOKIE_MAX_BYTES

    def test_log_oversized_cookie_warns(self, app, caplog):
        from flask import make_response

        with app.test_request_context("/admin/"):
            resp = make_response("ok")
            resp.headers["Set-Cookie"] = "session=" + ("x" * 3600)
            with caplog.at_level("WARNING"):
                log_oversized_session_cookie(resp)
        assert "Session cookie is" in caplog.text
