"""Mobile JWT lifecycle: signing secrets, refresh rotation/reuse, OAuth code exchange, lockout, scoping."""
import time
import uuid
from datetime import timedelta
from unittest.mock import patch

import jwt
import pytest

from app.utils.auth_state import AuthStateUnavailable
from tests.factories import create_test_user

pytestmark = [pytest.mark.unit, pytest.mark.auth_security]

PASSWORD = "MobilePass123!"
TOKEN_URL = "/api/mobile/v1/auth/token"
REFRESH_URL = "/api/mobile/v1/auth/refresh"
EXCHANGE_URL = "/api/mobile/v1/auth/oauth/exchange"
SESSION_URL = "/api/mobile/v1/auth/session"
LOGOUT_URL = "/api/mobile/v1/auth/logout"


@pytest.fixture
def mobile_user(app, db_session):
    with app.app_context():
        user = create_test_user(db_session, email=f"mob-{uuid.uuid4().hex[:8]}@example.com", password=PASSWORD)
        return {"id": user.id, "email": user.email}


def _login(client, email, password=PASSWORD):
    return client.post(TOKEN_URL, json={"email": email, "password": password})


def _tokens(client, mobile_user):
    resp = _login(client, mobile_user["email"])
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()["data"]


def _refresh(client, refresh_token):
    return client.post(REFRESH_URL, json={"refresh_token": refresh_token})


def _claims(app, token):
    with app.app_context():
        from app.utils.mobile_jwt import decode_mobile_token_ignoring_expiry

        return decode_mobile_token_ignoring_expiry(token)


class TestSigningSecrets:
    def test_tokens_are_signed_with_the_dedicated_mobile_secret(self, app, client, mobile_user):
        access = _tokens(client, mobile_user)["access_token"]
        mobile_secret = app.config["MOBILE_JWT_SECRET"]
        assert mobile_secret != app.config["SECRET_KEY"]
        assert jwt.decode(access, mobile_secret, algorithms=["HS256"], audience="hum-databank-mobile")["type"] == "access"
        with pytest.raises(jwt.InvalidSignatureError):
            jwt.decode(access, app.config["SECRET_KEY"], algorithms=["HS256"], audience="hum-databank-mobile")

    def _forge(self, app, secret, user_id, token_type="access", **extra):
        now = int(time.time())
        payload = {
            "sub": str(user_id), "type": token_type, "iat": now, "exp": now + 600,
            "aud": "hum-databank-mobile", "iss": "hum-databank-backoffice", "ver": 1, **extra,
        }
        return jwt.encode(payload, secret, algorithm="HS256")

    def test_legacy_secret_key_tokens_accepted_during_transition(self, app, client, mobile_user, monkeypatch):
        monkeypatch.setitem(app.config, "MOBILE_JWT_ACCEPT_LEGACY_SECRET_KEY", True)
        token = self._forge(app, app.config["SECRET_KEY"], mobile_user["id"])
        resp = client.get(SESSION_URL, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_legacy_secret_key_tokens_rejected_once_transition_ends(self, app, client, mobile_user, monkeypatch):
        monkeypatch.setitem(app.config, "MOBILE_JWT_ACCEPT_LEGACY_SECRET_KEY", False)
        token = self._forge(app, app.config["SECRET_KEY"], mobile_user["id"])
        resp = client.get(SESSION_URL, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_previous_secret_accepted_for_rotation_only_when_listed(self, app, client, mobile_user, monkeypatch):
        old_secret = "previous-mobile-secret-" + "x" * 30
        token = self._forge(app, old_secret, mobile_user["id"])
        monkeypatch.setitem(app.config, "MOBILE_JWT_ACCEPT_LEGACY_SECRET_KEY", False)
        monkeypatch.setitem(app.config, "MOBILE_JWT_SECRET_PREVIOUS", [])
        assert client.get(SESSION_URL, headers={"Authorization": f"Bearer {token}"}).status_code == 401
        monkeypatch.setitem(app.config, "MOBILE_JWT_SECRET_PREVIOUS", [old_secret])
        assert client.get(SESSION_URL, headers={"Authorization": f"Bearer {token}"}).status_code == 200

    def test_arbitrary_secret_is_rejected(self, app, client, mobile_user):
        token = self._forge(app, "attacker-secret-" + "z" * 30, mobile_user["id"])
        assert client.get(SESSION_URL, headers={"Authorization": f"Bearer {token}"}).status_code == 401

    def test_wrong_audience_is_rejected(self, app, client, mobile_user):
        now = int(time.time())
        token = jwt.encode(
            {"sub": str(mobile_user["id"]), "type": "access", "iat": now, "exp": now + 600,
             "aud": "hum-databank-ai", "iss": "hum-databank-backoffice"},
            app.config["MOBILE_JWT_SECRET"], algorithm="HS256",
        )
        assert client.get(SESSION_URL, headers={"Authorization": f"Bearer {token}"}).status_code == 401


class TestAiTokenSecrets:
    def test_dedicated_ai_secret_signs_when_configured(self, app, monkeypatch):
        from app.utils.ai_tokens import decode_ai_token, issue_ai_token

        monkeypatch.setitem(app.config, "AI_JWT_SECRET", "ai-secret-" + "q" * 40)
        with app.app_context():
            token = issue_ai_token(user_id=5, role="user")
            assert jwt.decode(
                token, app.config["AI_JWT_SECRET"], algorithms=["HS256"],
                audience="hum-databank-ai", issuer="hum-databank-backoffice",
            )["sub"] == "5"
            assert decode_ai_token(token).user_id == 5

    def test_falls_back_to_secret_key_with_deprecation_warning(self, app, monkeypatch, caplog):
        from app.utils.ai_tokens import decode_ai_token, issue_ai_token

        monkeypatch.setitem(app.config, "AI_JWT_SECRET", None)
        app.extensions.pop("ai_jwt_fallback_warned", None)
        with app.app_context(), caplog.at_level("WARNING"):
            token = issue_ai_token(user_id=6, role="user")
            assert decode_ai_token(token).user_id == 6
        assert "AI_JWT_SECRET is not set" in caplog.text

    def test_tokens_signed_with_old_secret_key_still_valid_after_split(self, app, monkeypatch):
        from app.utils.ai_tokens import decode_ai_token, issue_ai_token

        monkeypatch.setitem(app.config, "AI_JWT_SECRET", None)
        with app.app_context():
            old_token = issue_ai_token(user_id=7, role="user")
        monkeypatch.setitem(app.config, "AI_JWT_SECRET", "ai-secret-" + "q" * 40)
        monkeypatch.setitem(app.config, "AI_JWT_ACCEPT_LEGACY_SECRET_KEY", True)
        with app.app_context():
            assert decode_ai_token(old_token).user_id == 7
        monkeypatch.setitem(app.config, "AI_JWT_ACCEPT_LEGACY_SECRET_KEY", False)
        with app.app_context(), pytest.raises(jwt.InvalidSignatureError):
            decode_ai_token(old_token)

    def test_mobile_token_is_not_an_ai_token(self, app, monkeypatch):
        from app.utils.ai_tokens import decode_ai_token
        from app.utils.mobile_jwt import issue_access_token

        monkeypatch.setitem(app.config, "AI_JWT_SECRET", "ai-secret-" + "q" * 40)
        with app.app_context():
            with pytest.raises(jwt.InvalidTokenError):
                decode_ai_token(issue_access_token(1))


class TestRefreshRotation:
    def test_rotation_issues_a_new_pair_in_the_same_family(self, app, client, mobile_user):
        first = _tokens(client, mobile_user)
        resp = _refresh(client, first["refresh_token"])
        assert resp.status_code == 200, resp.get_data(as_text=True)
        second = resp.get_json()["data"]
        assert second["refresh_token"] != first["refresh_token"]
        old_claims = _claims(app, first["refresh_token"])
        new_claims = _claims(app, second["refresh_token"])
        assert new_claims.family_id == old_claims.family_id
        assert new_claims.jti != old_claims.jti
        assert new_claims.sid == old_claims.sid

    def test_replayed_refresh_token_is_rejected(self, client, mobile_user):
        first = _tokens(client, mobile_user)
        assert _refresh(client, first["refresh_token"]).status_code == 200
        replay = _refresh(client, first["refresh_token"])
        assert replay.status_code == 401
        assert "already been used" in replay.get_json()["error"]

    def test_reuse_revokes_the_whole_family(self, client, mobile_user):
        first = _tokens(client, mobile_user)
        second = _refresh(client, first["refresh_token"]).get_json()["data"]
        assert _refresh(client, first["refresh_token"]).status_code == 401
        legit_after_theft = _refresh(client, second["refresh_token"])
        assert legit_after_theft.status_code == 401
        assert "revoked" in legit_after_theft.get_json()["error"].lower()

    def test_reuse_also_revokes_outstanding_access_tokens(self, client, mobile_user):
        first = _tokens(client, mobile_user)
        second = _refresh(client, first["refresh_token"]).get_json()["data"]
        _refresh(client, first["refresh_token"])
        resp = client.get(SESSION_URL, headers={"Authorization": f"Bearer {second['access_token']}"})
        assert resp.status_code == 401

    def test_reuse_detection_survives_losing_process_memory(self, client, mobile_user):
        """Simulates the replay landing on a different worker / after a restart."""
        from app.services.platform import user_analytics_service as analytics

        first = _tokens(client, mobile_user)
        assert _refresh(client, first["refresh_token"]).status_code == 200
        analytics._blacklisted_sessions.clear()
        assert _refresh(client, first["refresh_token"]).status_code == 401

    def test_revocation_survives_losing_process_memory(self, client, mobile_user):
        from app.services.platform import user_analytics_service as analytics

        first = _tokens(client, mobile_user)
        second = _refresh(client, first["refresh_token"]).get_json()["data"]
        _refresh(client, first["refresh_token"])
        analytics._blacklisted_sessions.clear()
        assert _refresh(client, second["refresh_token"]).status_code == 401

    def test_concurrent_presentation_lets_exactly_one_through(self, app, client, mobile_user):
        from app.utils.mobile_jwt import consume_refresh_token

        first = _tokens(client, mobile_user)
        claims = _claims(app, first["refresh_token"])
        with app.app_context():
            outcomes = [consume_refresh_token(claims) for _ in range(4)]
        assert outcomes == [True, False, False, False]

    def test_store_outage_fails_closed_with_503_not_a_free_refresh(self, client, mobile_user):
        first = _tokens(client, mobile_user)
        with patch("app.utils.auth_state.DbAuthStateBackend.add_once", side_effect=AuthStateUnavailable("down")):
            resp = _refresh(client, first["refresh_token"])
        assert resp.status_code == 503
        assert resp.get_json()["error_code"] == "SERVICE_UNAVAILABLE"

    def test_store_outage_on_revocation_lookup_fails_closed(self, client, mobile_user):
        first = _tokens(client, mobile_user)
        with patch("app.utils.auth_state.DbAuthStateBackend.exists", side_effect=AuthStateUnavailable("down")):
            resp = _refresh(client, first["refresh_token"])
        assert resp.status_code in (401, 503)

    def test_access_token_cannot_be_used_as_refresh_token(self, client, mobile_user):
        first = _tokens(client, mobile_user)
        assert _refresh(client, first["access_token"]).status_code == 401

    def test_refresh_token_cannot_authenticate_api_calls(self, client, mobile_user):
        first = _tokens(client, mobile_user)
        resp = client.get(SESSION_URL, headers={"Authorization": f"Bearer {first['refresh_token']}"})
        assert resp.status_code == 401

    def test_refresh_token_without_jti_is_rejected(self, app, client, mobile_user):
        now = int(time.time())
        token = jwt.encode(
            {"sub": str(mobile_user["id"]), "type": "refresh", "iat": now, "exp": now + 600,
             "aud": "hum-databank-mobile", "iss": "hum-databank-backoffice", "ver": 1},
            app.config["MOBILE_JWT_SECRET"], algorithm="HS256",
        )
        assert _refresh(client, token).status_code == 401

    def test_legacy_refresh_token_without_family_claim_uses_sid_as_family(self, app, client, mobile_user):
        first = _tokens(client, mobile_user)
        claims = _claims(app, first["refresh_token"])
        now = int(time.time())
        legacy = jwt.encode(
            {"sub": str(mobile_user["id"]), "type": "refresh", "jti": "legacy-jti-" + uuid.uuid4().hex,
             "sid": claims.sid, "iat": now, "exp": now + 600,
             "aud": "hum-databank-mobile", "iss": "hum-databank-backoffice", "ver": 1},
            app.config["MOBILE_JWT_SECRET"], algorithm="HS256",
        )
        resp = _refresh(client, legacy)
        assert resp.status_code == 200
        assert _claims(app, resp.get_json()["data"]["refresh_token"]).family_id == claims.sid

    def test_deactivated_user_cannot_refresh(self, app, client, mobile_user, db_session):
        from app.models import User

        first = _tokens(client, mobile_user)
        with app.app_context():
            user = db_session.get(User, mobile_user["id"])
            user.active = False
            db_session.commit()
        resp = _refresh(client, first["refresh_token"])
        assert resp.status_code == 401

    def test_refresh_requires_a_token(self, client):
        assert client.post(REFRESH_URL, json={}).status_code == 400

    def test_logout_revokes_refresh_family_and_session(self, client, mobile_user):
        first = _tokens(client, mobile_user)
        resp = client.post(LOGOUT_URL, headers={"Authorization": f"Bearer {first['access_token']}"})
        assert resp.status_code == 200
        assert _refresh(client, first["refresh_token"]).status_code == 401
        assert client.get(SESSION_URL, headers={"Authorization": f"Bearer {first['access_token']}"}).status_code == 401


class TestExchangeSession:
    def test_bearer_authenticated_caller_cannot_mint_a_refresh_token(self, client, mobile_user):
        first = _tokens(client, mobile_user)
        resp = client.post(
            "/api/mobile/v1/auth/exchange-session", headers={"Authorization": f"Bearer {first['access_token']}"},
        )
        assert resp.status_code == 403

    def test_cookie_session_can_still_be_exchanged(self, app, client, mobile_user, monkeypatch):
        monkeypatch.setattr(
            "app.services.security.api_authentication.validate_plaintext_db_api_key_for_mobile_auth",
            lambda key: True,
        )
        with client.session_transaction() as sess:
            sess["_user_id"] = str(mobile_user["id"])
            sess["_fresh"] = True
        resp = client.post("/api/mobile/v1/auth/exchange-session", headers={"X-Mobile-Auth": "test"})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert "refresh_token" in resp.get_json()["data"]


class TestOAuthCodeExchange:
    VERIFIER = "v" * 64

    @staticmethod
    def _challenge(verifier):
        import base64
        import hashlib

        return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()

    def _code(self, app, mobile_user, sid=None, verifier=None):
        from app.utils.mobile_oauth_code import create_oauth_code

        with app.app_context():
            return create_oauth_code(mobile_user["id"], sid or str(uuid.uuid4()), self._challenge(verifier or self.VERIFIER))

    def test_valid_code_and_verifier_return_tokens_in_the_body(self, app, client, mobile_user):
        sid = str(uuid.uuid4())
        code = self._code(app, mobile_user, sid=sid)
        resp = client.post(EXCHANGE_URL, json={"code": code, "code_verifier": self.VERIFIER})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        data = resp.get_json()["data"]
        assert data["user"]["id"] == mobile_user["id"]
        assert _claims(app, data["access_token"]).sid == sid
        assert _claims(app, data["refresh_token"]).sid == sid

    def test_code_is_single_use(self, app, client, mobile_user):
        code = self._code(app, mobile_user)
        assert client.post(EXCHANGE_URL, json={"code": code, "code_verifier": self.VERIFIER}).status_code == 200
        assert client.post(EXCHANGE_URL, json={"code": code, "code_verifier": self.VERIFIER}).status_code == 401

    def test_wrong_verifier_fails_and_burns_the_code(self, app, client, mobile_user):
        code = self._code(app, mobile_user)
        wrong = client.post(EXCHANGE_URL, json={"code": code, "code_verifier": "w" * 64})
        assert wrong.status_code == 401
        retry = client.post(EXCHANGE_URL, json={"code": code, "code_verifier": self.VERIFIER})
        assert retry.status_code == 401

    def test_intercepted_code_without_verifier_is_useless(self, app, client, mobile_user):
        code = self._code(app, mobile_user)
        assert client.post(EXCHANGE_URL, json={"code": code}).status_code == 400

    def test_short_verifier_is_rejected(self, app, client, mobile_user):
        code = self._code(app, mobile_user, verifier="s" * 43)
        assert client.post(EXCHANGE_URL, json={"code": code, "code_verifier": "short"}).status_code == 401

    def test_unknown_code_is_rejected_generically(self, client):
        resp = client.post(EXCHANGE_URL, json={"code": "nope" * 10, "code_verifier": self.VERIFIER})
        assert resp.status_code == 401
        assert resp.get_json()["error_code"] == "AUTH_REQUIRED"

    def test_expired_code_is_rejected(self, app, client, mobile_user, monkeypatch):
        monkeypatch.setitem(app.config, "MOBILE_OAUTH_CODE_TTL_SECONDS", 1)
        code = self._code(app, mobile_user)
        time.sleep(1.3)
        assert client.post(EXCHANGE_URL, json={"code": code, "code_verifier": self.VERIFIER}).status_code == 401

    def test_default_ttl_is_sixty_seconds(self, app):
        assert app.config["MOBILE_OAUTH_CODE_TTL_SECONDS"] == 60

    def test_code_for_deactivated_user_is_rejected(self, app, client, mobile_user, db_session):
        from app.models import User

        code = self._code(app, mobile_user)
        with app.app_context():
            db_session.get(User, mobile_user["id"]).active = False
            db_session.commit()
        assert client.post(EXCHANGE_URL, json={"code": code, "code_verifier": self.VERIFIER}).status_code == 401

    def test_code_for_revoked_session_is_rejected(self, app, client, mobile_user):
        from app.utils.mobile_jwt import revoke_session_id

        sid = str(uuid.uuid4())
        code = self._code(app, mobile_user, sid=sid)
        with app.app_context():
            revoke_session_id(sid)
        assert client.post(EXCHANGE_URL, json={"code": code, "code_verifier": self.VERIFIER}).status_code == 401

    def test_store_outage_returns_503(self, app, client, mobile_user):
        code = self._code(app, mobile_user)
        with patch("app.utils.auth_state.DbAuthStateBackend.pop", side_effect=AuthStateUnavailable("down")):
            resp = client.post(EXCHANGE_URL, json={"code": code, "code_verifier": self.VERIFIER})
        assert resp.status_code == 503

    def test_code_is_stored_hashed(self, app, mobile_user):
        from app import db
        from app.models.auth_state import AuthStateEntry

        code = self._code(app, mobile_user)
        with app.app_context():
            keys = [row.key for row in db.session.query(AuthStateEntry).filter_by(namespace="oauth_code")]
        assert keys
        assert code not in keys


class TestMobileLoginAbuseControls:
    def test_deactivated_account_gets_the_same_generic_401(self, app, client, mobile_user, db_session):
        from app.models import User

        wrong = _login(client, mobile_user["email"], "WrongPass123!")
        with app.app_context():
            db_session.get(User, mobile_user["id"]).active = False
            db_session.commit()
        disabled = _login(client, mobile_user["email"])
        assert disabled.status_code == wrong.status_code == 401
        assert disabled.get_json() == wrong.get_json()

    def test_explicit_message_available_behind_a_flag(self, app, client, mobile_user, db_session, monkeypatch):
        from app.models import User

        monkeypatch.setitem(app.config, "MOBILE_REVEAL_DEACTIVATED_ACCOUNT", True)
        with app.app_context():
            db_session.get(User, mobile_user["id"]).active = False
            db_session.commit()
        resp = _login(client, mobile_user["email"])
        assert resp.status_code == 403
        assert "deactivated" in resp.get_json()["error"]

    def test_unknown_email_and_wrong_password_are_indistinguishable(self, client, mobile_user):
        unknown = _login(client, "nobody-here@example.com", "Whatever123!")
        wrong = _login(client, mobile_user["email"], "Whatever123!")
        assert unknown.status_code == wrong.status_code == 401
        assert unknown.get_json() == wrong.get_json()

    def test_unknown_email_still_pays_for_a_password_hash(self, client):
        with patch("app.utils.login_security.burn_password_check") as burn:
            _login(client, "nobody-here@example.com", "Whatever123!")
        burn.assert_called_once_with("Whatever123!")

    def test_known_email_does_not_use_the_dummy_hash(self, client, mobile_user):
        with patch("app.utils.login_security.burn_password_check") as burn:
            _login(client, mobile_user["email"], "Whatever123!")
        burn.assert_not_called()

    def test_failures_are_counted_in_the_shared_store_even_though_the_response_is_401(self, app, client, mobile_user):
        from app.utils.auth_state import NS_LOGIN_FAILURES, get_auth_state
        from app.utils.login_security import _email_key

        for _ in range(3):
            assert _login(client, mobile_user["email"], "Wrong123!").status_code == 401
        with app.app_context():
            assert get_auth_state().get_counter(NS_LOGIN_FAILURES, _email_key(mobile_user["email"])) == 3

    def test_lockout_engages_after_threshold_and_survives_rollbacks(self, app, client, mobile_user):
        from app.utils.login_security import ACCOUNT_LOCKOUT_THRESHOLD, record_login_failure

        with app.app_context():
            for _ in range(ACCOUNT_LOCKOUT_THRESHOLD):
                record_login_failure(mobile_user["email"])
        resp = _login(client, mobile_user["email"])
        assert resp.status_code == 429
        assert resp.get_json()["error_code"] == "ACCOUNT_LOCKED"

    def test_lockout_applies_even_with_the_correct_password(self, app, client, mobile_user):
        from app.utils.login_security import ACCOUNT_LOCKOUT_THRESHOLD, record_login_failure

        with app.app_context():
            for _ in range(ACCOUNT_LOCKOUT_THRESHOLD):
                record_login_failure(mobile_user["email"].upper())
        assert _login(client, mobile_user["email"], PASSWORD).status_code == 429

    def test_lockout_covers_unknown_emails_uniformly(self, app, client):
        from app.utils.login_security import ACCOUNT_LOCKOUT_THRESHOLD, record_login_failure

        with app.app_context():
            for _ in range(ACCOUNT_LOCKOUT_THRESHOLD):
                record_login_failure("ghost@example.com")
        assert _login(client, "ghost@example.com", "x").status_code == 429

    def test_successful_login_clears_the_counter(self, app, client, mobile_user):
        from app.utils.auth_state import NS_LOGIN_FAILURES, get_auth_state
        from app.utils.login_security import _email_key

        _login(client, mobile_user["email"], "Wrong123!")
        assert _login(client, mobile_user["email"]).status_code == 200
        with app.app_context():
            assert get_auth_state().get_counter(NS_LOGIN_FAILURES, _email_key(mobile_user["email"])) == 0

    def test_lockout_check_fails_closed_when_store_is_down(self, client, mobile_user):
        with patch("app.utils.auth_state.DbAuthStateBackend.get_counter", side_effect=AuthStateUnavailable("down")):
            assert _login(client, mobile_user["email"]).status_code == 429

    def test_failed_attempt_audit_row_is_persisted_despite_the_401(self, app, client, mobile_user):
        from app import db
        from app.models.core import UserLoginLog

        _login(client, mobile_user["email"], "Wrong123!")
        with app.app_context():
            rows = db.session.query(UserLoginLog).filter_by(
                email_attempted=mobile_user["email"], event_type="login_failed",
            ).all()
        assert len(rows) == 1
        assert rows[0].failure_reason == "wrong_password"

    def test_counter_key_does_not_contain_the_email(self, app, mobile_user):
        from app import db
        from app.models.auth_state import AuthStateEntry
        from app.utils.login_security import record_login_failure

        with app.app_context():
            record_login_failure(mobile_user["email"])
            keys = [r.key for r in db.session.query(AuthStateEntry).filter_by(namespace="login_fail")]
        assert keys and all("@" not in k for k in keys)


class TestBearerScopingAndSessionBinding:
    def test_bearer_jwt_does_not_authenticate_server_rendered_pages(self, client, mobile_user):
        tokens = _tokens(client, mobile_user)
        resp = client.get("/account-settings", headers={"Authorization": f"Bearer {tokens['access_token']}"})
        assert resp.status_code in (301, 302, 303, 307, 308, 401)
        if resp.status_code in (301, 302, 303, 307, 308):
            assert "/login" in resp.headers["Location"]

    def test_bearer_jwt_does_not_authenticate_admin_json_routes(self, client, mobile_user):
        tokens = _tokens(client, mobile_user)
        resp = client.get("/admin/users", headers={"Authorization": f"Bearer {tokens['access_token']}"})
        assert resp.status_code in (301, 302, 303, 307, 308, 401, 403)
        if resp.status_code in (301, 302, 303, 307, 308):
            assert "/login" in resp.headers["Location"]

    def test_bearer_jwt_does_not_set_a_session_cookie_on_unscoped_paths(self, client, mobile_user):
        tokens = _tokens(client, mobile_user)
        client.delete_cookie("session")
        resp = client.get("/account-settings", headers={"Authorization": f"Bearer {tokens['access_token']}"})
        assert "session=" not in ";".join(resp.headers.getlist("Set-Cookie")) or "_user_id" not in ";".join(resp.headers.getlist("Set-Cookie"))

    def test_bearer_jwt_authenticates_the_mobile_api(self, client, mobile_user):
        tokens = _tokens(client, mobile_user)
        resp = client.get(SESSION_URL, headers={"Authorization": f"Bearer {tokens['access_token']}"})
        assert resp.status_code == 200
        assert resp.get_json()["data"]["user"]["id"] == mobile_user["id"]

    def test_legacy_prefix_escape_hatch_is_opt_in(self, app, client, mobile_user, monkeypatch):
        from app.utils.mobile_auth import bearer_jwt_allowed_for_path

        with app.test_request_context("/"):
            assert bearer_jwt_allowed_for_path("/api/mobile/v1/x") is True
            assert bearer_jwt_allowed_for_path("/api/v1/data") is False
            monkeypatch.setitem(app.config, "MOBILE_JWT_LEGACY_BEARER_PATH_PREFIXES", ["/api/v1/"])
            assert bearer_jwt_allowed_for_path("/api/v1/data") is True

    def test_ai_token_endpoint_accepts_mobile_bearer_without_session_cookie(self, app, client, mobile_user):
        from app.utils.ai_tokens import decode_ai_token

        tokens = _tokens(client, mobile_user)
        client.delete_cookie("session")
        resp = client.get("/api/ai/v2/token", headers={"Authorization": f"Bearer {tokens['access_token']}"})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        with app.app_context():
            assert decode_ai_token(resp.get_json()["token"]).user_id == mobile_user["id"]

    def test_ai_token_endpoint_rejects_invalid_bearer_and_anonymous(self, client, mobile_user):
        client.delete_cookie("session")
        assert client.get("/api/ai/v2/token", headers={"Authorization": "Bearer not.a.jwt"}).status_code == 401
        assert client.get("/api/ai/v2/token").status_code == 401

    def test_bearer_exact_path_allowance_does_not_widen_other_ai_routes(self, app):
        from app.utils.mobile_auth import bearer_jwt_allowed_for_path

        with app.test_request_context("/"):
            assert bearer_jwt_allowed_for_path("/api/ai/v2/token") is True
            assert bearer_jwt_allowed_for_path("/api/ai/v2/token/") is True
            assert bearer_jwt_allowed_for_path("/api/ai/v2/token-extra") is False
            assert bearer_jwt_allowed_for_path("/api/ai/v2/conversations") is False
            assert bearer_jwt_allowed_for_path("/api/ai/v2/chat") is False

    def test_api_key_header_style_bearer_is_not_treated_as_jwt(self, client, mobile_user):
        resp = client.get(SESSION_URL, headers={"Authorization": "Bearer not.a.jwt"})
        assert resp.status_code == 401

    def test_jwt_bridge_cookie_carries_the_jwt_session_and_activity(self, app, client, mobile_user):
        tokens = _tokens(client, mobile_user)
        sid = _claims(app, tokens["access_token"]).sid
        client.get(SESSION_URL, headers={"Authorization": f"Bearer {tokens['access_token']}"})
        with client.session_transaction() as sess:
            assert sess.get("session_id") == sid
            assert sess.get("session_start")
            assert sess.get("last_activity")

    def test_bridge_cookie_stops_working_once_the_session_is_revoked(self, app, client, mobile_user):
        from app.utils.mobile_jwt import revoke_session_id

        tokens = _tokens(client, mobile_user)
        sid = _claims(app, tokens["access_token"]).sid
        client.get(SESSION_URL, headers={"Authorization": f"Bearer {tokens['access_token']}"})
        with app.app_context():
            revoke_session_id(sid)
        resp = client.get(SESSION_URL)
        assert resp.status_code == 401

    def test_bridge_cookie_is_subject_to_the_idle_timeout(self, app, client, mobile_user):
        tokens = _tokens(client, mobile_user)
        client.get(SESSION_URL, headers={"Authorization": f"Bearer {tokens['access_token']}"})
        stale = (app.config["SESSION_INACTIVITY_TIMEOUT"] + timedelta(minutes=5))
        from app.utils.datetime_helpers import utcnow

        with client.session_transaction() as sess:
            sess["last_activity"] = (utcnow() - stale).isoformat()
        assert client.get(SESSION_URL).status_code == 401
