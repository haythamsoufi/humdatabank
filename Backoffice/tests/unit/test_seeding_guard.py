"""Seeding must be an allowlist: FLASK_CONFIG=development and a local database only."""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.seeding import create_default_data, dev_seeding_refusal_reason

BACKOFFICE = Path(__file__).resolve().parents[2]
LOCAL_URL = "postgresql+psycopg2://app:pw@localhost:5432/db"


class TestRefusalReason:
    def test_development_and_localhost_allowed(self):
        assert dev_seeding_refusal_reason(LOCAL_URL, "development") is None

    @pytest.mark.parametrize(
        "url",
        [
            "postgresql://u:p@127.0.0.1/db",
            "postgresql://u:p@[::1]/db",
            "postgresql://u:p@host.docker.internal/db",
            "postgresql:///db?host=/var/run/postgresql",
        ],
    )
    def test_local_hosts_allowed(self, url):
        assert dev_seeding_refusal_reason(url, "development") is None

    @pytest.mark.parametrize("config", ["", "production", "staging", "testing", "default", "prod", "Development-x"])
    def test_anything_but_development_is_refused(self, config):
        reason = dev_seeding_refusal_reason(LOCAL_URL, config)
        assert reason and "FLASK_CONFIG" in reason

    def test_unset_flask_config_fails_closed(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FLASK_CONFIG", None)
            assert dev_seeding_refusal_reason(LOCAL_URL) is not None

    @pytest.mark.parametrize(
        "url",
        [
            "postgresql://u:p@databank-db.privatelink.postgres.database.azure.com:5432/db",
            "postgresql://u:p@10.0.0.5/db",
            "postgresql://u:p@localhost.evil.example/db",
        ],
    )
    def test_remote_database_refused_even_in_development(self, url):
        reason = dev_seeding_refusal_reason(url, "development")
        assert reason and "not local" in reason

    def test_unknown_database_url_fails_closed(self):
        assert dev_seeding_refusal_reason("", "development") is not None

    def test_extra_allowed_hosts_via_env(self):
        url = "postgresql://u:p@devbox.internal/db"
        assert dev_seeding_refusal_reason(url, "development") is not None
        with patch.dict(os.environ, {"SEED_ALLOWED_DB_HOSTS": "devbox.internal, other"}):
            assert dev_seeding_refusal_reason(url, "development") is None


class TestCreateDefaultDataGuard:
    def test_remote_database_never_opens_app_context(self):
        app = MagicMock()
        env = {
            "FLASK_CONFIG": "development",
            "DATABASE_URL": "postgresql://u:p@prod-db.example.com/db",
        }
        with patch.dict(os.environ, env):
            create_default_data(app)
        app.app_context.assert_not_called()
        app.logger.warning.assert_called()

    def test_unset_flask_config_never_opens_app_context(self):
        app = MagicMock()
        with patch.dict(os.environ, {"DATABASE_URL": LOCAL_URL}):
            os.environ.pop("FLASK_CONFIG", None)
            create_default_data(app)
        app.app_context.assert_not_called()


def _load_init_data():
    path = BACKOFFICE / "scripts" / "seeding" / "init_data.py"
    spec = importlib.util.spec_from_file_location("_init_data_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestInitDataScript:
    def test_has_no_literal_passwords(self):
        source = (BACKOFFICE / "scripts" / "seeding" / "init_data.py").read_text()
        assert "test123" not in source
        assert not re.search(r"set_password\(\s*['\"]", source)

    @pytest.mark.parametrize("config", [None, "production", "staging", "testing"])
    def test_refuses_without_explicit_development(self, config):
        module = _load_init_data()
        env = {"DATABASE_URL": LOCAL_URL}
        if config:
            env["FLASK_CONFIG"] = config
        with patch.dict(os.environ, env):
            if config is None:
                os.environ.pop("FLASK_CONFIG", None)
            assert module.main() == 1

    def test_refuses_remote_database(self):
        module = _load_init_data()
        env = {"FLASK_CONFIG": "development", "DATABASE_URL": "postgresql://u:p@db.example.com/x"}
        with patch.dict(os.environ, env):
            assert module.main() == 1

    def test_passwords_from_env_else_random_and_never_recorded(self):
        module = _load_init_data()
        randomized: set = set()
        with patch.dict(os.environ, {"TEST_ADMIN_PASSWORD": "from-env-value"}):
            os.environ.pop("TEST_FOCAL_PASSWORD", None)
            assert module._password_for("admin", randomized) == "from-env-value"
            first = module._password_for("focal", randomized)
            second = module._password_for("focal", randomized)
        assert len(first) >= 16 and first != "test123"
        assert first != second
        assert randomized == {"focal"}


class TestScanSecretsFlagsSeedPasswords:
    def test_pattern_detects_literal_set_password(self):
        sys.path.insert(0, str(BACKOFFICE / "scripts" / "ci"))
        try:
            import scan_secrets
        finally:
            sys.path.pop(0)
        pattern = next(p for p in scan_secrets.SECRET_PATTERNS if p.name.startswith("Hardcoded password passed"))
        assert re.search(pattern.pattern, "admin.set_password('test123')")
        assert not re.search(pattern.pattern, "admin.set_password(password)")
        assert not any("test123" in fp for fp in scan_secrets.FALSE_POSITIVE_PATTERNS)
