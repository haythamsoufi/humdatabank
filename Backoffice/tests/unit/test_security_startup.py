"""FLASK_CONFIG fail-closed resolution and startup security validation."""
import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask

from app.utils import security_startup
from app.utils.security_startup import collect_security_findings, detect_worker_count, validate_security_settings

pytestmark = [pytest.mark.unit, pytest.mark.auth_security]

BACKOFFICE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STRONG = "s" * 48


def _run_config(env_overrides, snippet, *, unset=()):
    env = {k: v for k, v in os.environ.items() if k not in unset and k != "FLASK_CONFIG"}
    env.update({"SECRET_KEY": STRONG, "PYTHONPATH": BACKOFFICE_DIR})
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", snippet], cwd=BACKOFFICE_DIR, env=env, capture_output=True, text=True, timeout=120,
    )


class TestFlaskConfigResolution:
    SNIPPET = (
        "from config.config import Config, _RESOLVED_FLASK_CONFIG as r; "
        "import os; print(r, Config.DEBUG, Config.TRUST_PROXY_HEADERS, Config.PLUGIN_UPLOAD_ENABLED, os.environ['FLASK_CONFIG'])"
    )

    def test_unset_flask_config_fails_closed_to_production(self):
        proc = _run_config({}, self.SNIPPET)
        assert proc.returncode == 0, proc.stderr
        resolved, debug, trust_proxy, plugin_upload, env_value = proc.stdout.split()
        assert resolved == "production"
        assert debug == "False"
        assert trust_proxy == "True"
        assert plugin_upload == "False"
        assert env_value == "production"
        assert "defaulting to 'production'" in proc.stderr

    def test_empty_flask_config_is_treated_as_unset(self):
        proc = _run_config({"FLASK_CONFIG": ""}, self.SNIPPET)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.split()[0] == "production"

    def test_explicit_development_still_works(self):
        proc = _run_config({"FLASK_CONFIG": "development"}, self.SNIPPET)
        assert proc.returncode == 0, proc.stderr
        resolved, debug, trust_proxy, plugin_upload, _ = proc.stdout.split()
        assert (resolved, debug, trust_proxy, plugin_upload) == ("development", "True", "False", "True")

    def test_staging_trusts_proxy_by_default(self):
        proc = _run_config({"FLASK_CONFIG": "staging"}, self.SNIPPET)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.split()[:4] == ["staging", "False", "True", "False"]

    def test_default_alias_is_deprecated_with_warning(self):
        proc = _run_config({"FLASK_CONFIG": "default"}, self.SNIPPET)
        assert proc.returncode == 0, proc.stderr
        assert "deprecated" in proc.stderr

    def test_unknown_value_is_rejected(self):
        proc = _run_config({"FLASK_CONFIG": "prod"}, self.SNIPPET)
        assert proc.returncode != 0
        assert "Invalid FLASK_CONFIG" in proc.stderr

    def test_interactive_run_py_on_loopback_is_development(self):
        snippet = (
            "import sys, types; m = types.ModuleType('__main__'); m.__file__ = '/x/run.py'; "
            "sys.modules['__main__'] = m; sys.argv = ['run.py']; "
            "from config.config import _RESOLVED_FLASK_CONFIG as r; print(r)"
        )
        proc = _run_config({}, snippet)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "development"

    def test_run_py_bound_to_all_interfaces_is_not_development(self):
        snippet = (
            "import sys, types; m = types.ModuleType('__main__'); m.__file__ = '/x/run.py'; "
            "sys.modules['__main__'] = m; sys.argv = ['run.py']; "
            "from config.config import _RESOLVED_FLASK_CONFIG as r; print(r)"
        )
        proc = _run_config({"FLASK_RUN_HOST": "0.0.0.0"}, snippet)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "production"

    def test_create_app_rejects_unknown_config_name(self):
        from app import create_app

        with pytest.raises(RuntimeError, match="Unknown config"):
            create_app("nope")


def _app(**config):
    flask_app = Flask(__name__)
    base = {
        "FLASK_CONFIG": "production",
        "DEBUG": False,
        "TESTING": False,
        "SECRET_KEY": STRONG,
        "MOBILE_JWT_SECRET": "m" * 48,
        "MOBILE_JWT_SECRET_EXPLICIT": True,
        "AI_JWT_SECRET": "a" * 48,
        "SESSION_COOKIE_SECURE": True,
        "TRUST_PROXY_HEADERS": True,
        "PLUGIN_UPLOAD_ENABLED": False,
        "MOBILE_JWT_ACCEPT_LEGACY_SECRET_KEY": False,
        "AI_JWT_ACCEPT_LEGACY_SECRET_KEY": False,
        "MOBILE_OAUTH_ALLOW_LEGACY_TOKEN_DEEP_LINK": False,
        "AUTH_STATE_BACKEND": "auto",
        "RATE_LIMIT_SHARED_FALLBACK": "db",
        "RATE_LIMIT_REQUIRE_SHARED_STORAGE": False,
        "RATELIMIT_STORAGE_URI": None,
        "REDIS_URL": None,
    }
    base.update(config)
    flask_app.config.update(base)
    return flask_app


@pytest.fixture(autouse=True)
def _single_worker(monkeypatch):
    for name in ("GUNICORN_WORKERS", "WEB_CONCURRENCY", "STRICT_ENV_VALIDATION", "SERVER_SOFTWARE"):
        monkeypatch.delenv(name, raising=False)


class TestSecurityFindings:
    def test_clean_production_config_has_no_findings(self):
        errors, warnings = collect_security_findings(_app())
        assert errors == []
        assert warnings == []

    def test_missing_mobile_jwt_secret_is_fatal_in_production(self):
        flask_app = _app(MOBILE_JWT_SECRET=STRONG, MOBILE_JWT_SECRET_EXPLICIT=False)
        with pytest.raises(RuntimeError, match="MOBILE_JWT_SECRET is not set"):
            validate_security_settings(flask_app)

    def test_mobile_secret_equal_to_secret_key_is_fatal(self):
        flask_app = _app(MOBILE_JWT_SECRET=STRONG)
        with pytest.raises(RuntimeError, match="must differ from SECRET_KEY"):
            validate_security_settings(flask_app)

    def test_short_mobile_secret_is_fatal(self):
        flask_app = _app(MOBILE_JWT_SECRET="short")
        with pytest.raises(RuntimeError, match="too short"):
            validate_security_settings(flask_app)

    def test_ai_secret_missing_is_warning_not_fatal(self):
        errors, warnings = collect_security_findings(_app(AI_JWT_SECRET=None))
        assert errors == []
        assert any("AI_JWT_SECRET is not set" in w for w in warnings)

    def test_ai_secret_reusing_another_secret_is_fatal(self):
        errors, _ = collect_security_findings(_app(AI_JWT_SECRET=STRONG))
        assert any("AI_JWT_SECRET must differ" in e for e in errors)

    def test_debug_in_production_is_fatal(self):
        errors, _ = collect_security_findings(_app(DEBUG=True))
        assert any("DEBUG must be false" in e for e in errors)

    def test_staging_is_validated_like_production(self):
        errors, _ = collect_security_findings(_app(FLASK_CONFIG="staging", MOBILE_JWT_SECRET_EXPLICIT=False))
        assert errors

    def test_development_reports_findings_but_never_raises(self):
        flask_app = _app(FLASK_CONFIG="development", DEBUG=True, MOBILE_JWT_SECRET_EXPLICIT=False)
        validate_security_settings(flask_app)

    def test_strict_override_can_force_validation_in_development(self, monkeypatch):
        monkeypatch.setenv("STRICT_ENV_VALIDATION", "true")
        flask_app = _app(FLASK_CONFIG="development", AUTH_STATE_BACKEND="redis")
        with pytest.raises(RuntimeError, match="AUTH_STATE_BACKEND=redis"):
            validate_security_settings(flask_app)

    def test_testing_config_is_not_strict(self):
        validate_security_settings(_app(FLASK_CONFIG="testing", TESTING=True, MOBILE_JWT_SECRET_EXPLICIT=False))

    def test_debug_skip_login_outside_development_is_always_fatal(self):
        flask_app = _app(FLASK_CONFIG="testing", TESTING=True, DEBUG_SKIP_LOGIN=True)
        with pytest.raises(RuntimeError, match="DEBUG_SKIP_LOGIN"):
            validate_security_settings(flask_app)

    def test_debug_skip_login_allowed_in_development_with_debug(self):
        flask_app = _app(FLASK_CONFIG="development", DEBUG=True, DEBUG_SKIP_LOGIN=True)
        validate_security_settings(flask_app)

    def test_debug_skip_login_in_development_without_debug_is_fatal(self):
        flask_app = _app(FLASK_CONFIG="development", DEBUG=False, DEBUG_SKIP_LOGIN=True)
        with pytest.raises(RuntimeError, match="DEBUG_SKIP_LOGIN"):
            validate_security_settings(flask_app)

    def test_untrusted_proxy_headers_warn_in_production(self):
        _, warnings = collect_security_findings(_app(TRUST_PROXY_HEADERS=False))
        assert any("TRUST_PROXY_HEADERS" in w for w in warnings)

    def test_plugin_upload_enabled_in_production_warns(self):
        _, warnings = collect_security_findings(_app(PLUGIN_UPLOAD_ENABLED=True))
        assert any("PLUGIN_UPLOAD_ENABLED" in w for w in warnings)

    def test_legacy_flags_warn(self):
        _, warnings = collect_security_findings(_app(
            MOBILE_JWT_ACCEPT_LEGACY_SECRET_KEY=True, MOBILE_OAUTH_ALLOW_LEGACY_TOKEN_DEEP_LINK=True,
        ))
        joined = " ".join(warnings)
        assert "MOBILE_JWT_ACCEPT_LEGACY_SECRET_KEY" in joined
        assert "MOBILE_OAUTH_ALLOW_LEGACY_TOKEN_DEEP_LINK" in joined

    def test_invalid_auth_state_backend_is_fatal(self):
        errors, _ = collect_security_findings(_app(AUTH_STATE_BACKEND="memcached"))
        assert any("invalid" in e for e in errors)


class TestMultiWorkerStorage:
    def test_multi_worker_without_redis_and_memory_fallback_warns(self, monkeypatch):
        monkeypatch.setenv("GUNICORN_WORKERS", "4")
        _, warnings = collect_security_findings(_app(RATE_LIMIT_SHARED_FALLBACK="memory"))
        assert any("4 workers" in w and "per-process" in w for w in warnings)

    def test_multi_worker_with_db_fallback_is_informational_only(self, monkeypatch):
        monkeypatch.setenv("GUNICORN_WORKERS", "4")
        errors, warnings = collect_security_findings(_app())
        assert errors == []
        assert any("auth_state_entry" in w for w in warnings)

    def test_multi_worker_with_redis_has_no_storage_finding(self, monkeypatch):
        monkeypatch.setenv("GUNICORN_WORKERS", "4")
        errors, warnings = collect_security_findings(_app(RATELIMIT_STORAGE_URI="redis://cache:6379/0"))
        assert errors == []
        assert warnings == []

    def test_require_shared_storage_refuses_memory_fallback(self, monkeypatch):
        monkeypatch.setenv("GUNICORN_WORKERS", "3")
        flask_app = _app(RATE_LIMIT_SHARED_FALLBACK="memory", RATE_LIMIT_REQUIRE_SHARED_STORAGE=True)
        with pytest.raises(RuntimeError, match="RATE_LIMIT_REQUIRE_SHARED_STORAGE"):
            validate_security_settings(flask_app)

    def test_single_worker_never_complains(self):
        errors, warnings = collect_security_findings(
            _app(RATE_LIMIT_SHARED_FALLBACK="memory", RATE_LIMIT_REQUIRE_SHARED_STORAGE=True)
        )
        assert errors == []
        assert warnings == []


class TestDetectWorkerCount:
    def test_default_is_one(self):
        assert detect_worker_count() == 1

    def test_gunicorn_workers_env(self, monkeypatch):
        monkeypatch.setenv("GUNICORN_WORKERS", "5")
        assert detect_worker_count() == 5

    def test_web_concurrency_env(self, monkeypatch):
        monkeypatch.setenv("WEB_CONCURRENCY", "2")
        assert detect_worker_count() == 2

    def test_auto_uses_cpu_count(self, monkeypatch):
        monkeypatch.setenv("GUNICORN_WORKERS", "auto")
        with patch.object(security_startup.multiprocessing, "cpu_count", return_value=4):
            assert detect_worker_count() == 9

    def test_gunicorn_without_env_uses_conf_default(self, monkeypatch):
        monkeypatch.setenv("SERVER_SOFTWARE", "gunicorn/22.0")
        assert detect_worker_count() == security_startup._GUNICORN_CONF_DEFAULT_WORKERS

    def test_garbage_value_is_ignored(self, monkeypatch):
        monkeypatch.setenv("GUNICORN_WORKERS", "lots")
        assert detect_worker_count() == 1


class TestRedisConfigured:
    @pytest.mark.parametrize("key", ["RATELIMIT_STORAGE_URI", "REDIS_URL"])
    def test_either_setting_counts(self, key):
        assert security_startup.redis_configured(_app(**{key: "redis://x:6379/0"})) is True

    def test_memory_uri_does_not_count(self):
        assert security_startup.redis_configured(_app(RATELIMIT_STORAGE_URI="memory://")) is False


class TestDefaultsOnTheConfigClasses:
    def test_secure_defaults_for_new_switches(self):
        from config.config import Config

        assert Config.MOBILE_OAUTH_CODE_TTL_SECONDS == 60
        assert Config.REGISTRATION_EMAIL_CHECK_ENABLED is False
        assert Config.REGISTRATION_REVEAL_EXISTING_EMAIL is False
        assert Config.MOBILE_REVEAL_DEACTIVATED_ACCOUNT is False
        assert Config.MOBILE_JWT_BEARER_PATH_PREFIXES == ["/api/mobile/v1/"]
        assert Config.MOBILE_JWT_LEGACY_BEARER_PATH_PREFIXES == []
        assert Config.DEBUG_SKIP_LOGIN is False
