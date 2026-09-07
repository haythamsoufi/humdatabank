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
    def test_id_token_in_cookie_exceeds_browser_limit(self, app):
        """Document why the Azure ID token must not live in the Flask cookie.

        Flask compresses cookie sessions, so a repeated character string stays
        small. Real ID tokens are already base64 (high entropy) and do not.
        """
        import secrets

        serializer = app.session_interface.get_signing_serializer(app)
        raw = serializer.dumps({
            B2C_ID_TOKEN_SESSION_KEY: secrets.token_urlsafe(3000),
            "_user_id": "12345",
            "_fresh": True,
            "session_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "csrf_token": secrets.token_hex(40),
            "last_activity": "2026-09-07T10:00:00.123456+00:00",
            "session_start": "2026-09-07T09:00:00.123456+00:00",
            "language": "en",
            "prompt_profile_completion": True,
            "_permanent": True,
        })
        header = (
            f"session={raw}; HttpOnly; Path=/; SameSite=Lax; Secure; "
            "Expires=Wed, 07 Sep 2026 22:00:00 GMT"
        )
        assert len(header) >= BROWSER_COOKIE_MAX_BYTES

    def test_request_strips_legacy_token(self, app):
        token = "e" * 2800
        client = app.test_client()
        with client.session_transaction() as sess:
            sess[B2C_ID_TOKEN_SESSION_KEY] = token
            sess["session_id"] = "sid-live"
        resp = client.get("/login")
        assert resp.status_code == 200
        with client.session_transaction() as sess:
            assert B2C_ID_TOKEN_SESSION_KEY not in sess
        assert pop_oauth_logout_hint("sid-live") == token
        size = session_set_cookie_bytes(resp)
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
