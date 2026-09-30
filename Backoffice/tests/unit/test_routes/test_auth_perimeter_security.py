"""Web auth hardening: mobile OAuth start validation, registration and check-email abuse controls."""
import base64
import hashlib
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import jwt
import pytest

from tests.factories import create_test_user

pytestmark = [pytest.mark.auth_security]


def _challenge(verifier="v" * 64):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


@pytest.fixture
def b2c(app):
    app.config.update({
        "AZURE_B2C_TENANT": "testtenant.onmicrosoft.com",
        "AZURE_B2C_POLICY": "B2C_1_signin",
        "AZURE_B2C_CLIENT_ID": "client-id",
        "AZURE_B2C_CLIENT_SECRET": "secret",
        "AZURE_B2C_REDIRECT_URI": "http://localhost/callback",
    })
    meta = {"authorization_endpoint": "https://login.example.com/authorize"}
    with patch("app.routes.auth._b2c_metadata", return_value=meta):
        yield


def _state_claims(app, location):
    state = parse_qs(urlparse(location).query)["state"][0]
    return jwt.decode(state, app.config["SECRET_KEY"], algorithms=["HS256"])


@pytest.mark.integration
class TestMobileOAuthStart:
    def test_valid_challenge_is_bound_into_the_signed_state(self, client, app, b2c):
        cc = _challenge()
        resp = client.get(f"/login/azure?mobile_return_scheme=humdatabank&app_code_challenge={cc}")
        assert resp.status_code == 302
        claims = _state_claims(app, resp.headers["Location"])
        assert claims["mobile"] is True
        assert claims["app_cc"] == cc

    def test_web_login_carries_no_challenge(self, client, app, b2c):
        resp = client.get("/login/azure")
        assert _state_claims(app, resp.headers["Location"])["app_cc"] is None

    @pytest.mark.parametrize("bad", ["short", "!" * 43, "a" * 200])
    def test_malformed_challenge_is_rejected_via_deep_link(self, client, b2c, bad):
        resp = client.get(f"/login/azure?mobile_return_scheme=humdatabank&app_code_challenge={bad}")
        assert resp.status_code == 302
        assert resp.headers["Location"].startswith("humdatabank://oauth-error")
        assert "invalid_request" in resp.headers["Location"]

    def test_plain_method_is_rejected(self, client, b2c):
        resp = client.get(
            f"/login/azure?mobile_return_scheme=humdatabank&app_code_challenge={_challenge()}"
            "&app_code_challenge_method=plain"
        )
        assert resp.headers["Location"].startswith("humdatabank://oauth-error")

    def test_missing_challenge_allowed_only_while_legacy_flag_is_on(self, client, app, b2c):
        app.config["MOBILE_OAUTH_ALLOW_LEGACY_TOKEN_DEEP_LINK"] = True
        ok = client.get("/login/azure?mobile_return_scheme=humdatabank")
        assert ok.headers["Location"].startswith("https://login.example.com/")
        app.config["MOBILE_OAUTH_ALLOW_LEGACY_TOKEN_DEEP_LINK"] = False
        try:
            denied = client.get("/login/azure?mobile_return_scheme=humdatabank")
        finally:
            app.config["MOBILE_OAUTH_ALLOW_LEGACY_TOKEN_DEEP_LINK"] = True
        assert denied.headers["Location"].startswith("humdatabank://oauth-error")


@pytest.mark.integration
class TestMobileOAuthRedirectHandoff:
    def test_challenge_yields_code_and_no_tokens_in_url(self, app, db_session):
        from app.routes.auth import _mobile_oauth_redirect

        user = create_test_user(db_session, email="oauth-handoff@example.com")
        with app.test_request_context("/auth/azure/callback"):
            resp = _mobile_oauth_redirect(user, "sid-1", _challenge())
        location = resp.headers["Location"]
        query = parse_qs(urlparse(location).query)
        assert location.startswith("humdatabank://oauth-success?")
        assert set(query) == {"code"}

    def test_legacy_flow_disabled_returns_update_required(self, app, db_session):
        from app.routes.auth import _mobile_oauth_redirect

        user = create_test_user(db_session, email="oauth-legacy@example.com")
        app.config["MOBILE_OAUTH_ALLOW_LEGACY_TOKEN_DEEP_LINK"] = False
        try:
            with app.test_request_context("/auth/azure/callback"):
                resp = _mobile_oauth_redirect(user, "sid-1", None)
        finally:
            app.config["MOBILE_OAUTH_ALLOW_LEGACY_TOKEN_DEEP_LINK"] = True
        assert "app_update_required" in resp.headers["Location"]
        assert "access_token" not in resp.headers["Location"]

    def test_legacy_flow_enabled_still_returns_tokens(self, app, db_session):
        from app.routes.auth import _mobile_oauth_redirect

        user = create_test_user(db_session, email="oauth-legacy2@example.com")
        app.config["MOBILE_OAUTH_ALLOW_LEGACY_TOKEN_DEEP_LINK"] = True
        with app.test_request_context("/auth/azure/callback"):
            resp = _mobile_oauth_redirect(user, "sid-1", None)
        assert "access_token=" in resp.headers["Location"]

    def test_store_outage_fails_closed_to_error_link(self, app, db_session):
        from app.routes.auth import _mobile_oauth_redirect
        from app.utils.auth_state import AuthStateUnavailable

        user = create_test_user(db_session, email="oauth-outage@example.com")
        with app.test_request_context("/auth/azure/callback"), \
             patch("app.utils.mobile_oauth_code.create_oauth_code", side_effect=AuthStateUnavailable("down")):
            resp = _mobile_oauth_redirect(user, "sid-1", _challenge())
        assert "temporarily_unavailable" in resp.headers["Location"]


@pytest.mark.integration
class TestRegisterAbuseControls:
    def test_post_register_is_rate_limited_per_client_ip(self, client, app, db_session, monkeypatch):
        monkeypatch.setattr("app.routes.auth.is_azure_b2c_configured", lambda: False)
        monkeypatch.setattr("app.routes.auth.RegisterForm.validate_on_submit", lambda self: False)
        monkeypatch.setattr("app.utils.security_startup.redis_configured", lambda _app: False)
        app.config["DEBUG"] = False
        app.config["RATE_LIMIT_SKIP_DEBUG"] = False
        app.config["RATE_LIMIT_SHARED_FALLBACK"] = "memory"

        from app.utils import rate_limiting as rl

        rl._rate_limit_storage.clear()

        def post(ip, headers=None):
            return client.post("/register", data={}, headers=headers or {}, environ_overrides={"REMOTE_ADDR": ip})

        first = [post("198.51.100.7").status_code for _ in range(5)]
        assert set(first) == {200}
        assert post("198.51.100.7").status_code == 302
        assert post("198.51.100.7", {"X-Forwarded-For": "203.0.113.99"}).status_code == 302
        assert post("198.51.100.8").status_code == 200

    def test_forwarded_for_header_does_not_change_the_rate_limit_key(self, app):
        from app.utils.client_ip import get_client_ip

        with app.test_request_context(
            "/register", method="POST", headers={"X-Forwarded-For": "203.0.113.99"},
            environ_overrides={"REMOTE_ADDR": "198.51.100.7"},
        ):
            assert get_client_ip() == "198.51.100.7"


@pytest.mark.integration
class TestCheckEmailEndpoint:
    def test_disabled_endpoint_is_indistinguishable_from_unknown_route(self, client, app, db_session):
        app.config["REGISTRATION_EMAIL_CHECK_ENABLED"] = False
        create_test_user(db_session, email="taken@example.com")
        assert client.get("/register/check-email?email=taken@example.com").status_code == 404
        assert client.get("/register/check-email?email=free@example.com").status_code == 404
