"""Unit tests for api_authentication service."""
import base64
import time
from collections import deque
from datetime import timedelta
from unittest.mock import patch

import pytest
from flask import g
from flask_login import login_user

from app import db
from app.models import FormData, TemplateShare
from app.models.api_key_management import API_KEY_DATA_READ_SCOPED
from app.services.security import api_authentication as auth_mod
from app.services.security.api_authentication import (
    _env_mobile_api_key_rate_limit_exceeded,
    _extract_bearer_or_x_api_key,
    _get_user_allowed_country_ids,
    _plaintext_matches_env_mobile_api_key,
    _try_finish_auth_with_env_mobile_api_key,
    apply_api_key_data_scoping,
    apply_user_template_scoping,
    authenticate_api_request,
    authenticate_db_api_key_only,
    get_user_allowed_template_ids,
    validate_plaintext_db_api_key_for_mobile_auth,
)
from app.utils.datetime_helpers import utcnow
from tests.factories import (
    _grant_entity_permission,
    create_test_admin,
    create_test_api_key,
    create_test_country,
    create_test_template,
    create_test_user,
)


def _assert_empty_query(query):
    sql = str(query.statement.compile(compile_kwargs={"literal_binds": True}))
    assert "false" in sql.lower() or "1 = 0" in sql.lower() or "0 = 1" in sql.lower()


def _bearer_headers(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


@pytest.fixture(autouse=True)
def _clear_api_key_rate_limits():
    auth_mod._api_key_rate_limit_storage.clear()
    yield
    auth_mod._api_key_rate_limit_storage.clear()


@pytest.mark.unit
class TestExtractBearerOrXApiKey:
    def test_bearer_header(self, app):
        with app.test_request_context(headers={"Authorization": "Bearer my-key"}):
            assert _extract_bearer_or_x_api_key() == "my-key"

    def test_x_api_key_header(self, app):
        with app.test_request_context(headers={"X-API-Key": "legacy-key"}):
            assert _extract_bearer_or_x_api_key() == "legacy-key"

    def test_x_api_key_uppercase_header(self, app):
        with app.test_request_context(headers={"X-API-KEY": "legacy-key"}):
            assert _extract_bearer_or_x_api_key() == "legacy-key"

    def test_missing_key(self, app):
        with app.test_request_context():
            assert _extract_bearer_or_x_api_key() == ""


@pytest.mark.unit
class TestEnvMobileApiKey:
    def test_plaintext_match(self, app):
        app.config["MOBILE_APP_API_KEY"] = "mobile-secret"
        with app.app_context():
            assert _plaintext_matches_env_mobile_api_key("mobile-secret") is True
            assert _plaintext_matches_env_mobile_api_key("wrong") is False
            assert _plaintext_matches_env_mobile_api_key("") is False

    def test_plaintext_length_mismatch(self, app):
        app.config["MOBILE_APP_API_KEY"] = "short"
        with app.app_context():
            assert _plaintext_matches_env_mobile_api_key("much-longer-key") is False

    def test_plaintext_compare_exception_returns_false(self, app):
        app.config["MOBILE_APP_API_KEY"] = "mobile-secret"
        with app.app_context():
            with patch(
                "app.services.security.api_authentication.secrets.compare_digest",
                side_effect=RuntimeError("compare failed"),
            ):
                assert _plaintext_matches_env_mobile_api_key("mobile-secret") is False

    def test_rate_limit_exceeded(self, app):
        app.config["MOBILE_APP_API_KEY_RATE_LIMIT_PER_MINUTE"] = 2
        with app.test_request_context():
            assert _env_mobile_api_key_rate_limit_exceeded() is False
            assert _env_mobile_api_key_rate_limit_exceeded() is False
            assert _env_mobile_api_key_rate_limit_exceeded() is True

    def test_rate_limit_prunes_stale_entries(self, app):
        app.config["MOBILE_APP_API_KEY_RATE_LIMIT_PER_MINUTE"] = 1
        bucket = auth_mod._ENV_MOBILE_API_KEY_RATE_BUCKET
        auth_mod._api_key_rate_limit_storage[bucket] = deque([time.time() - 120])
        with app.test_request_context():
            assert _env_mobile_api_key_rate_limit_exceeded() is False

    def test_try_finish_auth_rate_limit_exceeded(self, app):
        app.config["MOBILE_APP_API_KEY"] = "env-rate-key"
        app.config["MOBILE_APP_API_KEY_RATE_LIMIT_PER_MINUTE"] = 1
        auth_mod._api_key_rate_limit_storage[auth_mod._ENV_MOBILE_API_KEY_RATE_BUCKET] = deque(
            [time.time()]
        )
        with app.test_request_context("/api/v1/foo"):
            with patch.object(app.logger, "warning") as mock_warning:
                assert _try_finish_auth_with_env_mobile_api_key(
                    log_prefix="[test]",
                    provided_key="env-rate-key",
                ) is False
            mock_warning.assert_called_once()


@pytest.mark.unit
class TestAuthenticateDbApiKeyOnly:
    def test_missing_key_returns_401(self, app):
        with app.test_request_context("/api/v1/foo"):
            result = authenticate_db_api_key_only()
        assert result.status_code == 401

    def test_valid_db_key(self, app, db_session, api_key):
        _obj, full_key = api_key
        with app.test_request_context("/api/v1/foo", headers=_bearer_headers(full_key)):
            result = authenticate_db_api_key_only()
        assert hasattr(result, "client_name")
        assert g.api_key_record is not None
        assert g.api_key_usage_id == _obj.id

    def test_env_mobile_key_fallback(self, app, db_session):
        app.config["MOBILE_APP_API_KEY"] = "env-mobile-key-12345"
        with app.test_request_context(
            "/api/v1/foo",
            headers=_bearer_headers("env-mobile-key-12345"),
        ):
            result = authenticate_db_api_key_only()
        assert result is True
        assert g.api_key_record is None

    def test_x_api_key_header(self, app, db_session, api_key):
        _obj, full_key = api_key
        with app.test_request_context("/api/v1/foo", headers={"X-API-Key": full_key}):
            result = authenticate_db_api_key_only()
        assert hasattr(result, "client_name")

    def test_invalid_db_key_returns_401(self, app, db_session):
        with app.test_request_context("/api/v1/foo", headers=_bearer_headers("not-a-real-key")):
            result = authenticate_db_api_key_only()
        assert result.status_code == 401

    def test_revoked_key_returns_401(self, app, db_session, api_key):
        obj, full_key = api_key
        obj.revoke(reason="test")
        db_session.commit()
        with app.test_request_context("/api/v1/foo", headers=_bearer_headers(full_key)):
            result = authenticate_db_api_key_only()
        assert result.status_code == 401
        assert result.get_json()["error"] == "API key has been revoked"

    def test_expired_key_returns_401(self, app, db_session, api_key):
        obj, full_key = api_key
        obj.expires_at = utcnow() - timedelta(days=1)
        db_session.commit()
        with app.test_request_context("/api/v1/foo", headers=_bearer_headers(full_key)):
            result = authenticate_db_api_key_only()
        assert result.status_code == 401
        assert result.get_json()["error"] == "API key has expired"

    def test_disabled_key_returns_401(self, app, db_session, api_key):
        obj, full_key = api_key
        obj.disable(reason="paused")
        db_session.commit()
        with app.test_request_context("/api/v1/foo", headers=_bearer_headers(full_key)):
            result = authenticate_db_api_key_only()
        assert result.status_code == 401
        assert result.get_json()["error"] == "API key is not active"

    def test_rate_limit_exceeded(self, app, db_session, api_key):
        obj, full_key = api_key
        obj.rate_limit_per_minute = 1
        db_session.commit()
        with app.test_request_context("/api/v1/foo", headers=_bearer_headers(full_key)):
            assert authenticate_db_api_key_only() is not None
            result = authenticate_db_api_key_only()
        assert result.status_code == 429

    def test_rate_limit_prunes_stale_entries(self, app, db_session, api_key):
        obj, full_key = api_key
        obj.rate_limit_per_minute = 1
        db_session.commit()
        auth_mod._api_key_rate_limit_storage[f"api_key_{obj.id}"] = deque([time.time() - 120])
        with app.test_request_context("/api/v1/foo", headers=_bearer_headers(full_key)):
            result = authenticate_db_api_key_only()
        assert hasattr(result, "client_name")

    def test_update_last_used_failure_is_non_fatal(self, app, db_session, api_key):
        obj, full_key = api_key
        with app.test_request_context("/api/v1/foo", headers=_bearer_headers(full_key)):
            with patch(
                "app.models.api_key_management.APIKey.touch_last_used",
                side_effect=RuntimeError("db down"),
            ):
                with patch.object(app.logger, "warning") as mock_warning:
                    result = authenticate_db_api_key_only()
        assert hasattr(result, "client_name")
        mock_warning.assert_called()

    def test_logs_db_key_usage_when_enabled(self, app, db_session, api_key):
        _obj, full_key = api_key
        app.config["LOG_API_KEY_USAGE"] = True
        with app.test_request_context("/api/v1/foo", headers=_bearer_headers(full_key)):
            with patch.object(app.logger, "info") as mock_info:
                authenticate_db_api_key_only()
        assert mock_info.called

    def test_env_key_logs_when_enabled(self, app, db_session):
        app.config["MOBILE_APP_API_KEY"] = "log-test-key-12345"
        app.config["LOG_API_KEY_USAGE"] = True
        with app.test_request_context(
            "/api/v1/foo",
            headers=_bearer_headers("log-test-key-12345"),
        ):
            with patch.object(app.logger, "info") as mock_info:
                result = authenticate_db_api_key_only()
        assert result is True
        assert mock_info.called

    def test_env_key_rate_limit_returns_401(self, app, db_session):
        app.config["MOBILE_APP_API_KEY"] = "env-limited-key"
        app.config["MOBILE_APP_API_KEY_RATE_LIMIT_PER_MINUTE"] = 1
        auth_mod._api_key_rate_limit_storage[auth_mod._ENV_MOBILE_API_KEY_RATE_BUCKET] = deque(
            [time.time()]
        )
        with app.test_request_context("/api/v1/foo", headers=_bearer_headers("env-limited-key")):
            result = authenticate_db_api_key_only()
        assert result.status_code == 401

    def test_authentication_error_returns_500(self, app, db_session):
        with app.test_request_context("/api/v1/foo", headers=_bearer_headers("any-key")):
            with patch(
                "app.models.api_key_management.APIKey.hash_key",
                side_effect=RuntimeError("hash failed"),
            ):
                with patch.object(app.logger, "error") as mock_error:
                    result = authenticate_db_api_key_only()
        assert result.status_code == 500
        mock_error.assert_called()


@pytest.mark.unit
class TestValidatePlaintextDbApiKeyForMobileAuth:
    def test_empty_key(self, app):
        with app.test_request_context():
            assert validate_plaintext_db_api_key_for_mobile_auth("") is False

    def test_valid_db_key(self, app, db_session, api_key):
        _obj, full_key = api_key
        with app.test_request_context():
            assert validate_plaintext_db_api_key_for_mobile_auth(full_key) is True

    def test_env_key_fallback(self, app, db_session):
        app.config["MOBILE_APP_API_KEY"] = "mobile-x-auth-key"
        with app.test_request_context():
            assert validate_plaintext_db_api_key_for_mobile_auth("mobile-x-auth-key") is True

    def test_revoked_key(self, app, db_session, api_key):
        obj, full_key = api_key
        obj.is_revoked = True
        db_session.commit()
        with app.test_request_context():
            assert validate_plaintext_db_api_key_for_mobile_auth(full_key) is False

    def test_disabled_key(self, app, db_session, api_key):
        obj, full_key = api_key
        obj.disable()
        db_session.commit()
        with app.test_request_context():
            assert validate_plaintext_db_api_key_for_mobile_auth(full_key) is False

    def test_rate_limit_exceeded(self, app, db_session, api_key):
        obj, full_key = api_key
        obj.rate_limit_per_minute = 1
        db_session.commit()
        with app.test_request_context("/api/v1/foo"):
            assert validate_plaintext_db_api_key_for_mobile_auth(full_key) is True
            with patch.object(app.logger, "warning") as mock_warning:
                assert validate_plaintext_db_api_key_for_mobile_auth(full_key) is False
            mock_warning.assert_called()

    def test_rate_limit_prunes_stale_entries(self, app, db_session, api_key):
        obj, full_key = api_key
        obj.rate_limit_per_minute = 1
        db_session.commit()
        auth_mod._api_key_rate_limit_storage[f"api_key_{obj.id}"] = deque([time.time() - 120])
        with app.test_request_context():
            assert validate_plaintext_db_api_key_for_mobile_auth(full_key) is True

    def test_update_last_used_failure_is_non_fatal(self, app, db_session, api_key):
        obj, full_key = api_key
        with app.test_request_context():
            with patch(
                "app.models.api_key_management.APIKey.touch_last_used",
                side_effect=RuntimeError("db down"),
            ):
                with patch.object(app.logger, "warning") as mock_warning:
                    assert validate_plaintext_db_api_key_for_mobile_auth(full_key) is True
        mock_warning.assert_called()

    def test_logs_db_key_usage_when_enabled(self, app, db_session, api_key):
        _obj, full_key = api_key
        app.config["LOG_API_KEY_USAGE"] = True
        with app.test_request_context():
            with patch.object(app.logger, "info") as mock_info:
                assert validate_plaintext_db_api_key_for_mobile_auth(full_key) is True
        assert mock_info.called

    def test_env_key_rate_limit_returns_false(self, app, db_session):
        app.config["MOBILE_APP_API_KEY"] = "mobile-limited"
        app.config["MOBILE_APP_API_KEY_RATE_LIMIT_PER_MINUTE"] = 1
        auth_mod._api_key_rate_limit_storage[auth_mod._ENV_MOBILE_API_KEY_RATE_BUCKET] = deque(
            [time.time()]
        )
        with app.test_request_context():
            assert validate_plaintext_db_api_key_for_mobile_auth("mobile-limited") is False

    def test_validation_error_returns_false(self, app, db_session):
        with app.test_request_context():
            with patch(
                "app.models.api_key_management.APIKey.hash_key",
                side_effect=RuntimeError("hash failed"),
            ):
                with patch.object(app.logger, "error") as mock_error:
                    assert validate_plaintext_db_api_key_for_mobile_auth("any-key") is False
        mock_error.assert_called()


@pytest.mark.unit
class TestAuthenticateApiRequest:
    def test_session_auth(self, app, db_session, test_user):
        with app.test_request_context("/api/v1/foo"):
            login_user(test_user)
            result = authenticate_api_request()
        elevated, user, key = result
        assert elevated is False
        assert user.id == test_user.id
        assert key is None

    def test_basic_auth_valid(self, app, db_session, test_user):
        creds = base64.b64encode(b"test_user@example.com:user_password").decode()
        with app.test_request_context(
            "/api/v1/foo",
            headers={"Authorization": f"Basic {creds}"},
        ):
            result = authenticate_api_request()
        assert result[1].email == "test_user@example.com"

    def test_basic_auth_invalid(self, app, db_session, test_user):
        creds = base64.b64encode(b"test_user@example.com:wrong").decode()
        with app.test_request_context(
            "/api/v1/foo",
            headers={"Authorization": f"Basic {creds}"},
        ):
            result = authenticate_api_request()
        assert result.status_code == 401
        assert "WWW-Authenticate" in result.headers

    def test_query_api_key(self, app, db_session, api_key):
        _obj, full_key = api_key
        with app.test_request_context(f"/api/v1/foo?api_key={full_key}"):
            result = authenticate_api_request()
        assert result[2] is not None

    def test_no_credentials_returns_401_with_challenge(self, app):
        with app.test_request_context("/api/v1/foo"):
            result = authenticate_api_request()
        assert result.status_code == 401
        assert "WWW-Authenticate" in result.headers

    def test_invalid_key(self, app, db_session):
        with app.test_request_context("/api/v1/foo", headers=_bearer_headers("bogus-key")):
            result = authenticate_api_request()
        assert result.status_code == 401

    def test_revoked_key(self, app, db_session, api_key):
        obj, full_key = api_key
        obj.revoke()
        db_session.commit()
        with app.test_request_context("/api/v1/foo", headers=_bearer_headers(full_key)):
            result = authenticate_api_request()
        assert result.status_code == 401
        assert result.get_json()["error"] == "API key has been revoked"

    def test_expired_key(self, app, db_session, api_key):
        obj, full_key = api_key
        obj.expires_at = utcnow() - timedelta(days=1)
        db_session.commit()
        with app.test_request_context("/api/v1/foo", headers=_bearer_headers(full_key)):
            result = authenticate_api_request()
        assert result.status_code == 401
        assert result.get_json()["error"] == "API key has expired"

    def test_disabled_key(self, app, db_session, api_key):
        obj, full_key = api_key
        obj.disable()
        db_session.commit()
        with app.test_request_context("/api/v1/foo", headers=_bearer_headers(full_key)):
            result = authenticate_api_request()
        assert result.status_code == 401
        assert result.get_json()["error"] == "API key is not active"

    def test_rate_limit_exceeded(self, app, db_session, api_key):
        obj, full_key = api_key
        obj.rate_limit_per_minute = 1
        db_session.commit()
        with app.test_request_context("/api/v1/foo", headers=_bearer_headers(full_key)):
            assert isinstance(authenticate_api_request(), tuple)
            result = authenticate_api_request()
        assert result.status_code == 429

    def test_rate_limit_prunes_stale_entries(self, app, db_session, api_key):
        obj, full_key = api_key
        obj.rate_limit_per_minute = 1
        db_session.commit()
        auth_mod._api_key_rate_limit_storage[f"api_key_{obj.id}"] = deque([time.time() - 120])
        with app.test_request_context("/api/v1/foo", headers=_bearer_headers(full_key)):
            result = authenticate_api_request()
        assert isinstance(result, tuple)

    def test_read_all_grants_elevated_access(self, app, db_session, api_key):
        _obj, full_key = api_key
        with app.test_request_context("/api/v1/foo", headers=_bearer_headers(full_key)):
            elevated, user, key = authenticate_api_request()
        assert elevated is True
        assert user is None
        assert key is not None
        assert getattr(g, "api_key_data_scope", "unset") is None

    def test_read_scoped_sets_scope(self, app, db_session):
        with app.app_context():
            template = create_test_template(db_session)
            country = create_test_country(db_session)
            template_id = template.id
            country_id = country.id
            _obj, full_key = create_test_api_key(
                db_session,
                permissions={
                    "data": API_KEY_DATA_READ_SCOPED,
                    "template_ids": [template_id],
                    "country_ids": [country_id],
                },
            )
        with app.test_request_context("/api/v1/foo", headers=_bearer_headers(full_key)):
            elevated, user, key = authenticate_api_request()
        assert elevated is False
        assert key is not None
        assert g.api_key_data_scope == {
            "template_ids": [template_id],
            "country_ids": [country_id],
        }

    def test_no_data_permission_returns_403(self, app, db_session):
        with app.app_context():
            _obj, full_key = create_test_api_key(db_session, permissions={"data": "none"})
        with app.test_request_context("/api/v1/foo", headers=_bearer_headers(full_key)):
            result = authenticate_api_request()
        assert result.status_code == 403

    def test_env_mobile_key_success(self, app, db_session):
        app.config["MOBILE_APP_API_KEY"] = "env-api-request-key"
        with app.test_request_context(
            "/api/v1/foo",
            headers=_bearer_headers("env-api-request-key"),
        ):
            elevated, user, key = authenticate_api_request()
        assert elevated is True
        assert user is None
        assert key is None
        assert g.api_key_record is None

    def test_env_mobile_key_rate_limit_returns_401(self, app, db_session):
        app.config["MOBILE_APP_API_KEY"] = "env-limited-api-key"
        app.config["MOBILE_APP_API_KEY_RATE_LIMIT_PER_MINUTE"] = 1
        auth_mod._api_key_rate_limit_storage[auth_mod._ENV_MOBILE_API_KEY_RATE_BUCKET] = deque(
            [time.time()]
        )
        with app.test_request_context(
            "/api/v1/foo",
            headers=_bearer_headers("env-limited-api-key"),
        ):
            result = authenticate_api_request()
        assert result.status_code == 401

    def test_logs_db_key_usage_when_enabled(self, app, db_session, api_key):
        _obj, full_key = api_key
        app.config["LOG_API_KEY_USAGE"] = True
        with app.test_request_context("/api/v1/foo", headers=_bearer_headers(full_key)):
            with patch.object(app.logger, "info") as mock_info:
                authenticate_api_request()
        assert mock_info.called

    def test_update_last_used_failure_is_non_fatal(self, app, db_session, api_key):
        obj, full_key = api_key
        with app.test_request_context("/api/v1/foo", headers=_bearer_headers(full_key)):
            with patch(
                "app.models.api_key_management.APIKey.touch_last_used",
                side_effect=RuntimeError("db down"),
            ):
                with patch.object(app.logger, "warning") as mock_warning:
                    result = authenticate_api_request()
        assert isinstance(result, tuple)
        mock_warning.assert_called()

    def test_authentication_error_returns_500(self, app, db_session):
        with app.test_request_context("/api/v1/foo", headers=_bearer_headers("any-key")):
            with patch(
                "app.models.api_key_management.APIKey.hash_key",
                side_effect=RuntimeError("hash failed"),
            ):
                with patch.object(app.logger, "error") as mock_error:
                    result = authenticate_api_request()
        assert result.status_code == 500
        mock_error.assert_called()


@pytest.mark.unit
class TestGetUserAllowedTemplateIds:
    def test_empty(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session)
            assert get_user_allowed_template_ids(user.id) == []

    def test_owned_template(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session)
            template = create_test_template(db_session, owner_id=user.id)
            ids = get_user_allowed_template_ids(user.id)
            assert template.id in ids

    def test_shared_template(self, app, db_session):
        with app.app_context():
            owner = create_test_user(db_session)
            user = create_test_user(db_session)
            template = create_test_template(db_session, owner_id=owner.id)
            db.session.add(
                TemplateShare(
                    template_id=template.id,
                    shared_with_user_id=user.id,
                    shared_by_user_id=owner.id,
                )
            )
            db.session.commit()
            ids = get_user_allowed_template_ids(user.id)
            assert template.id in ids

    def test_query_error_returns_empty_list(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session)
            with patch.object(db.session, "execute", side_effect=RuntimeError("db down")):
                with patch.object(app.logger, "error") as mock_error:
                    assert get_user_allowed_template_ids(user.id) == []
            mock_error.assert_called()


@pytest.mark.unit
class TestGetUserAllowedCountryIds:
    def test_system_manager_is_unrestricted(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session, role="system_manager")
            assert _get_user_allowed_country_ids(user) is None

    def test_admin_with_countries_view_is_unrestricted(self, app, db_session):
        with app.app_context():
            admin = create_test_admin(db_session)
            assert _get_user_allowed_country_ids(admin) is None

    def test_user_with_entity_permissions(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session, role="focal_point")
            country = create_test_country(db_session)
            _grant_entity_permission(db_session, user, "country", country.id)
            assert _get_user_allowed_country_ids(user) == {country.id}

    def test_user_without_entity_permissions(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session)
            assert _get_user_allowed_country_ids(user) == set()


@pytest.mark.unit
class TestApplyUserTemplateScoping:
    def test_no_templates_returns_empty_queries(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session)
            queries = {"assigned": FormData.query, "public": FormData.query}
            result = apply_user_template_scoping(queries, user)
            _assert_empty_query(result["assigned"])

    def test_system_manager_bypasses_scoping(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session, role="system_manager")
            queries = {"assigned": FormData.query, "public": FormData.query}
            result = apply_user_template_scoping(queries, user)
            assert result["assigned"] is queries["assigned"]
            assert result["public"] is queries["public"]

    def test_owned_template_applies_filter(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session)
            create_test_template(db_session, owner_id=user.id)
            queries = {"assigned": FormData.query, "public": FormData.query}
            result = apply_user_template_scoping(queries, user)
            assert result["assigned"] is not None

    def test_with_existing_joins_skips_extra_join(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session)
            template = create_test_template(db_session, owner_id=user.id)
            queries = {"assigned": FormData.query, "public": FormData.query}
            result = apply_user_template_scoping(
                queries,
                user,
                template_id=template.id,
            )
            assert result["assigned"] is not None

    def test_no_country_permissions_returns_empty_queries(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session)
            create_test_template(db_session, owner_id=user.id)
            queries = {"assigned": FormData.query, "public": FormData.query}
            result = apply_user_template_scoping(queries, user)
            _assert_empty_query(result["assigned"])

    def test_country_permissions_apply_filter(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session, role="focal_point")
            country = create_test_country(db_session)
            _grant_entity_permission(db_session, user, "country", country.id)
            create_test_template(db_session, owner_id=user.id)
            queries = {"assigned": FormData.query, "public": FormData.query}
            result = apply_user_template_scoping(queries, user)
            assert result["assigned"] is not None

    def test_admin_with_countries_view_is_unrestricted(self, app, db_session):
        with app.app_context():
            admin = create_test_admin(db_session)
            create_test_template(db_session, owner_id=admin.id)
            queries = {"assigned": FormData.query, "public": FormData.query}
            result = apply_user_template_scoping(queries, admin)
            assert result["assigned"] is not None

    def test_none_assigned_query_is_preserved(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session)
            create_test_template(db_session, owner_id=user.id)
            country = create_test_country(db_session)
            _grant_entity_permission(db_session, user, "country", country.id)
            queries = {"assigned": None, "public": FormData.query}
            result = apply_user_template_scoping(queries, user)
            assert result["assigned"] is None
            assert result["public"] is not None


@pytest.mark.unit
class TestApplyApiKeyDataScoping:
    def test_empty_scope_returns_empty_queries(self, app):
        with app.app_context():
            queries = {"assigned": FormData.query, "public": FormData.query}
            result = apply_api_key_data_scoping(queries, {"template_ids": [], "country_ids": []})
            _assert_empty_query(result["assigned"])

    def test_invalid_scope_returns_queries_unchanged(self, app):
        with app.app_context():
            queries = {"assigned": FormData.query, "public": FormData.query}
            assert apply_api_key_data_scoping(queries, None) is queries
            assert apply_api_key_data_scoping(queries, "bad") is queries

    def test_template_filter(self, app, db_session):
        with app.app_context():
            template = create_test_template(db_session)
            queries = {"assigned": FormData.query, "public": FormData.query}
            scope = {"template_ids": [template.id], "country_ids": []}
            result = apply_api_key_data_scoping(queries, scope)
            assert result["assigned"] is not None

    def test_template_id_mismatch_returns_empty_queries(self, app, db_session):
        with app.app_context():
            template = create_test_template(db_session)
            queries = {"assigned": FormData.query, "public": FormData.query}
            scope = {"template_ids": [template.id], "country_ids": []}
            result = apply_api_key_data_scoping(queries, scope, template_id=template.id + 999)
            _assert_empty_query(result["assigned"])

    def test_country_mismatch_returns_empty_queries(self, app, db_session):
        with app.app_context():
            queries = {"assigned": FormData.query, "public": FormData.query}
            scope = {"template_ids": [1], "country_ids": [99]}
            result = apply_api_key_data_scoping(queries, scope, country_id=1)
            _assert_empty_query(result["assigned"])

    def test_country_filter_applied(self, app, db_session):
        with app.app_context():
            country = create_test_country(db_session)
            queries = {"assigned": FormData.query, "public": FormData.query}
            scope = {"template_ids": [], "country_ids": [country.id]}
            result = apply_api_key_data_scoping(queries, scope)
            assert result["assigned"] is not None
            assert result["public"] is not None

    def test_with_existing_joins_skips_extra_join(self, app, db_session):
        with app.app_context():
            template = create_test_template(db_session)
            queries = {"assigned": FormData.query, "public": FormData.query}
            scope = {"template_ids": [template.id], "country_ids": []}
            result = apply_api_key_data_scoping(queries, scope, template_id=template.id)
            assert result["assigned"] is not None

    def test_none_assigned_query_is_preserved(self, app, db_session):
        with app.app_context():
            country = create_test_country(db_session)
            queries = {"assigned": None, "public": FormData.query}
            scope = {"template_ids": [], "country_ids": [country.id]}
            result = apply_api_key_data_scoping(queries, scope)
            assert result["assigned"] is None
            assert result["public"] is not None
