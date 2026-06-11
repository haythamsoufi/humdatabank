"""Comprehensive unit tests for app/services/app_settings_service.py.

Covers all public and private functions to reach 100% branch coverage.
Database-backed functions use the ``db_session`` / ``app`` fixtures from
``tests/conftest.py``; JSON-fallback paths are exercised by temporarily
patching the app context and SystemSettings imports.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import app.services.app_settings_service as svc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clear_settings(db_session, app):
    """Remove all SystemSettings rows between tests."""
    from app.models.system import SystemSettings
    with app.app_context():
        SystemSettings.query.delete()
        db_session.commit()


# ---------------------------------------------------------------------------
# _get_settings_path
# ---------------------------------------------------------------------------

class TestGetSettingsPath:
    def test_uses_env_override(self, tmp_path):
        env_path = str(tmp_path / "custom_settings.json")
        with patch.dict(os.environ, {"APP_SETTINGS_PATH": env_path}):
            result = svc._get_settings_path()
        assert result == env_path

    def test_default_resolves_to_config_dir(self):
        with patch.dict(os.environ, {}, clear=False):
            env_backup = os.environ.pop("APP_SETTINGS_PATH", None)
            try:
                result = svc._get_settings_path()
                assert result.endswith("app_settings.json")
                assert "config" in result
            finally:
                if env_backup is not None:
                    os.environ["APP_SETTINGS_PATH"] = env_backup

    def test_blank_env_var_uses_default(self):
        with patch.dict(os.environ, {"APP_SETTINGS_PATH": "   "}):
            result = svc._get_settings_path()
        assert result.endswith("app_settings.json")
        assert "config" in result


# ---------------------------------------------------------------------------
# _read_settings_json_file / _write_settings_json_file
# ---------------------------------------------------------------------------

class TestJsonFileFallback:
    def test_read_returns_empty_when_missing(self, tmp_path):
        path = str(tmp_path / "nonexistent.json")
        with patch.object(svc, "_get_settings_path", return_value=path):
            result = svc._read_settings_json_file()
        assert result == {}

    def test_write_then_read_roundtrip(self, tmp_path):
        path = str(tmp_path / "settings.json")
        data = {"key": "value", "num": 42}
        with patch.object(svc, "_get_settings_path", return_value=path):
            assert svc._write_settings_json_file(data) is True
            result = svc._read_settings_json_file()
        assert result == data

    def test_read_malformed_json_returns_empty(self, tmp_path):
        path = str(tmp_path / "bad.json")
        with open(path, "w") as f:
            f.write("{ not valid json }")
        with patch.object(svc, "_get_settings_path", return_value=path):
            result = svc._read_settings_json_file()
        assert result == {}

    def test_write_failure_returns_false(self, tmp_path):
        path = "/root/unwritable/settings.json"
        with patch.object(svc, "_get_settings_path", return_value=path):
            result = svc._write_settings_json_file({"k": "v"})
        assert result is False


# ---------------------------------------------------------------------------
# read_settings / write_settings – DB path
# ---------------------------------------------------------------------------

class TestReadWriteSettings:
    def test_read_settings_returns_dict(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            result = svc.read_settings()
        assert isinstance(result, dict)

    def test_write_and_read_roundtrip(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.write_settings({"test_key": "test_value"})
            result = svc.read_settings()
        assert result.get("test_key") == "test_value"

    def test_write_settings_returns_true(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            ok = svc.write_settings({"x": 1})
        assert ok is True

    def test_write_settings_with_user_id(self, app, db_session, admin_user):
        with app.app_context():
            _clear_settings(db_session, app)
            ok = svc.write_settings({"y": 2}, user_id=admin_user.id)
        assert ok is True

    def test_read_settings_json_fallback_no_context(self, tmp_path):
        """Outside app context, read_settings must fall back to JSON."""
        path = str(tmp_path / "fallback.json")
        with open(path, "w") as f:
            json.dump({"fallback_key": "hello"}, f)
        with patch.object(svc, "_get_settings_path", return_value=path), \
             patch.object(svc, "has_app_context", return_value=False):
            result = svc.read_settings()
        assert result.get("fallback_key") == "hello"

    def test_write_settings_json_fallback_no_context(self, tmp_path):
        path = str(tmp_path / "fallback_write.json")
        with patch.object(svc, "_get_settings_path", return_value=path), \
             patch.object(svc, "has_app_context", return_value=False):
            ok = svc.write_settings({"fb": "val"})
        assert ok is True

    def test_write_settings_db_exception_returns_false(self, app, db_session):
        with app.app_context():
            with patch("app.models.system.SystemSettings.set_value", side_effect=Exception("DB fail")):
                result = svc.write_settings({"broken": True})
        assert result is False

    def test_read_settings_db_exception_falls_back(self, app, db_session, tmp_path):
        path = str(tmp_path / "fallback_read.json")
        with open(path, "w") as f:
            json.dump({"fb_key": "fb_val"}, f)
        with app.app_context():
            with patch("app.models.system.SystemSettings.get_all_as_dict",
                       side_effect=Exception("DB fail")), \
                 patch.object(svc, "_get_settings_path", return_value=path):
                result = svc.read_settings()
        assert result.get("fb_key") == "fb_val"


# ---------------------------------------------------------------------------
# Languages
# ---------------------------------------------------------------------------

class TestLanguages:
    def test_set_and_get_languages(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_supported_languages(["en", "fr", "es"])
            langs = svc.get_supported_languages()
        assert "en" in langs
        assert "fr" in langs

    def test_set_languages_adds_en(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_supported_languages(["fr", "de"])
            langs = svc.get_supported_languages()
        assert langs[0] == "en"

    def test_set_languages_deduplicates(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_supported_languages(["en", "fr", "en", "fr"])
            langs = svc.get_supported_languages()
        assert langs.count("en") == 1
        assert langs.count("fr") == 1

    def test_set_languages_requires_list(self, app, db_session):
        with app.app_context():
            with pytest.raises(ValueError):
                svc.set_supported_languages("en")

    def test_get_languages_empty_returns_default(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            langs = svc.get_supported_languages(default=["en"])
        assert langs == ["en"]


# ---------------------------------------------------------------------------
# show_language_flags
# ---------------------------------------------------------------------------

class TestShowLanguageFlags:
    def test_default_true(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            assert svc.get_show_language_flags() is True

    def test_set_false(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_show_language_flags(False)
            assert svc.get_show_language_flags() is False

    def test_coerce_int_true(self, app, db_session):
        with app.app_context():
            with patch.object(svc, "read_settings", return_value={"show_language_flags": 1}):
                assert svc.get_show_language_flags() is True

    def test_coerce_int_false(self, app, db_session):
        with app.app_context():
            with patch.object(svc, "read_settings", return_value={"show_language_flags": 0}):
                assert svc.get_show_language_flags() is False

    def test_coerce_string_true(self, app, db_session):
        for val in ["1", "true", "yes", "y", "on"]:
            with app.app_context():
                with patch.object(svc, "read_settings", return_value={"show_language_flags": val}):
                    assert svc.get_show_language_flags() is True

    def test_coerce_string_false(self, app, db_session):
        for val in ["0", "false", "no", "n", "off", ""]:
            with app.app_context():
                with patch.object(svc, "read_settings", return_value={"show_language_flags": val}):
                    assert svc.get_show_language_flags() is False

    def test_unknown_value_uses_default(self, app, db_session):
        with app.app_context():
            with patch.object(svc, "read_settings", return_value={"show_language_flags": []}):
                assert svc.get_show_language_flags(default=True) is True


# ---------------------------------------------------------------------------
# Document types
# ---------------------------------------------------------------------------

class TestDocumentTypes:
    def test_set_and_get(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_document_types(["Report", "Survey", "Assessment"])
            types = svc.get_document_types()
        assert "Report" in types

    def test_strips_whitespace(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_document_types(["  Report  ", "Survey"])
            types = svc.get_document_types()
        assert "Report" in types

    def test_deduplicates(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_document_types(["Report", "Report", "Survey"])
            types = svc.get_document_types()
        assert types.count("Report") == 1

    def test_requires_list(self, app, db_session):
        with app.app_context():
            with pytest.raises(ValueError):
                svc.set_document_types("Report")

    def test_get_empty_returns_default(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            types = svc.get_document_types(default=["Default Type"])
        assert types == ["Default Type"]

    def test_filters_empty_strings(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_document_types(["  ", "Valid", ""])
            types = svc.get_document_types()
        assert "" not in types
        assert "Valid" in types


# ---------------------------------------------------------------------------
# Age groups
# ---------------------------------------------------------------------------

class TestAgeGroups:
    def test_set_and_get(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_age_groups(["0-4", "5-17", "18-59", "60+"])
            groups = svc.get_age_groups()
        assert "0-4" in groups

    def test_strips_whitespace(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_age_groups(["  0-4  ", "5-17"])
            groups = svc.get_age_groups()
        assert "0-4" in groups

    def test_requires_list(self):
        with pytest.raises(ValueError):
            svc.set_age_groups("0-4")

    def test_get_default(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            groups = svc.get_age_groups(default=["All Ages"])
        assert groups == ["All Ages"]


# ---------------------------------------------------------------------------
# Sex categories
# ---------------------------------------------------------------------------

class TestSexCategories:
    def test_set_and_get(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_sex_categories(["Male", "Female", "Other"])
            cats = svc.get_sex_categories()
        assert "Male" in cats

    def test_requires_list(self):
        with pytest.raises(ValueError):
            svc.set_sex_categories("Male")

    def test_get_default(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            cats = svc.get_sex_categories(default=["Unknown"])
        assert cats == ["Unknown"]

    def test_strips_whitespace(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_sex_categories(["  Male  "])
            cats = svc.get_sex_categories()
        assert "Male" in cats


# ---------------------------------------------------------------------------
# Translations for list-type settings
# ---------------------------------------------------------------------------

class TestListTranslations:
    def test_set_and_get(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_list_translations("document_types", {"Report": {"fr": "Rapport", "es": "Informe"}})
            result = svc.get_list_translations("document_types")
        assert "Report" in result
        assert result["Report"]["fr"] == "Rapport"

    def test_empty_inner_dict_excluded(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_list_translations("document_types", {"Report": {}, "Survey": {"fr": "Enquête"}})
            result = svc.get_list_translations("document_types")
        assert "Report" not in result
        assert "Survey" in result

    def test_none_translations_treated_as_empty(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_list_translations("document_types", None)
            result = svc.get_list_translations("document_types")
        assert result == {}

    def test_empty_en_text_excluded(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_list_translations("document_types", {"  ": {"fr": "vide"}})
            result = svc.get_list_translations("document_types")
        assert "  " not in result and "" not in result

    def test_get_returns_empty_when_missing(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            result = svc.get_list_translations("document_types")
        assert result == {}


# ---------------------------------------------------------------------------
# Enabled entity types
# ---------------------------------------------------------------------------

class TestEnabledEntityTypes:
    def test_set_and_get(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_enabled_entity_types(["countries", "ns_structure"])
            result = svc.get_enabled_entity_types()
        assert "countries" in result
        assert "ns_structure" in result

    def test_invalid_group_excluded(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_enabled_entity_types(["countries", "invalid_group"])
            result = svc.get_enabled_entity_types()
        assert "invalid_group" not in result

    def test_empty_defaults_to_countries(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_enabled_entity_types([])
            result = svc.get_enabled_entity_types()
        assert "countries" in result

    def test_get_default_when_empty_settings(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            result = svc.get_enabled_entity_types(default=["countries"])
        assert "countries" in result

    def test_normalize_entity_group_list_non_list(self):
        result = svc._normalize_entity_group_list("not_a_list", fallback=["countries"])
        assert result == ["countries"]

    def test_normalize_entity_group_list_deduplicates(self):
        result = svc._normalize_entity_group_list(["countries", "countries", "ns_structure"])
        assert result.count("countries") == 1


# ---------------------------------------------------------------------------
# AI settings
# ---------------------------------------------------------------------------

class TestAiSettings:
    def test_set_and_get(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_settings({"AI_MODEL": "gpt-4", "MAX_TOKENS": 1000})
            result = svc.get_ai_settings()
        assert result["AI_MODEL"] == "gpt-4"

    def test_sensitive_keys_not_stored(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_settings({"OPENAI_API_KEY": "sk-secret", "AI_MODEL": "gpt-4"})
            result = svc.get_ai_settings()
        assert "OPENAI_API_KEY" not in result
        assert result.get("AI_MODEL") == "gpt-4"

    def test_none_values_stripped(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_settings({"AI_MODEL": None, "MAX_TOKENS": 500})
            result = svc.get_ai_settings()
        assert "AI_MODEL" not in result

    def test_empty_string_stripped(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_settings({"AI_MODEL": "  ", "MAX_TOKENS": 100})
            result = svc.get_ai_settings()
        assert "AI_MODEL" not in result

    def test_requires_dict(self, app, db_session):
        with app.app_context():
            with pytest.raises(ValueError):
                svc.set_ai_settings("not a dict")

    def test_get_empty_when_none_stored(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            result = svc.get_ai_settings()
        assert result == {}


# ---------------------------------------------------------------------------
# _coerce_bool
# ---------------------------------------------------------------------------

class TestCoerceBool:
    def test_bool_true(self):
        assert svc._coerce_bool(True) is True

    def test_bool_false(self):
        assert svc._coerce_bool(False) is False

    def test_int_nonzero(self):
        assert svc._coerce_bool(1) is True

    def test_int_zero(self):
        assert svc._coerce_bool(0) is False

    def test_string_true(self):
        for v in ["1", "true", "yes", "y", "on"]:
            assert svc._coerce_bool(v) is True

    def test_string_false(self):
        for v in ["0", "false", "no", "n", "off", ""]:
            assert svc._coerce_bool(v) is False

    def test_unknown_uses_default(self):
        assert svc._coerce_bool([], default=True) is True
        assert svc._coerce_bool([], default=False) is False


# ---------------------------------------------------------------------------
# _normalize_user_id_list
# ---------------------------------------------------------------------------

class TestNormalizeUserIdList:
    def test_none_returns_empty(self):
        assert svc._normalize_user_id_list(None) == []

    def test_list_of_ints(self):
        assert svc._normalize_user_id_list([1, 2, 3]) == [1, 2, 3]

    def test_string_csv(self):
        assert svc._normalize_user_id_list("1,2,3") == [1, 2, 3]

    def test_deduplicates(self):
        result = svc._normalize_user_id_list([1, 1, 2])
        assert result.count(1) == 1

    def test_filters_invalid(self):
        result = svc._normalize_user_id_list([1, "bad", None, -1, 0])
        assert result == [1]

    def test_set_input(self):
        result = svc._normalize_user_id_list({5, 3})
        assert 5 in result
        assert 3 in result

    def test_single_int(self):
        assert svc._normalize_user_id_list(42) == [42]


# ---------------------------------------------------------------------------
# AI beta access
# ---------------------------------------------------------------------------

class TestAiBetaAccess:
    def test_set_and_get(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_beta_access_settings(enabled=True, allowed_user_ids=[1, 2])
            result = svc.get_ai_beta_access_settings()
        assert result["enabled"] is True
        assert 1 in result["allowed_user_ids"]

    def test_env_override_enables(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_beta_access_settings(enabled=False, allowed_user_ids=[])
            with patch.dict(os.environ, {"AI_BETA_ENABLED": "true"}):
                result = svc.get_ai_beta_access_settings()
        assert result["enabled"] is True

    def test_env_override_disables(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_beta_access_settings(enabled=True, allowed_user_ids=[])
            with patch.dict(os.environ, {"AI_BETA_ENABLED": "false"}):
                result = svc.get_ai_beta_access_settings()
        assert result["enabled"] is False

    def test_env_allowed_user_ids_override(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_beta_access_settings(enabled=True, allowed_user_ids=[1])
            with patch.dict(os.environ, {"AI_BETA_ALLOWED_USER_IDS": "99,100"}):
                result = svc.get_ai_beta_access_settings()
        assert result["allowed_user_ids"] == [99, 100]

    def test_is_ai_beta_restricted_false(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_beta_access_settings(enabled=False, allowed_user_ids=[])
            assert svc.is_ai_beta_restricted() is False

    def test_is_ai_beta_restricted_true(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_beta_access_settings(enabled=True, allowed_user_ids=[])
            assert svc.is_ai_beta_restricted() is True

    def test_get_ai_beta_allowed_user_ids(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_beta_access_settings(enabled=True, allowed_user_ids=[7, 8])
            ids = svc.get_ai_beta_allowed_user_ids()
        assert 7 in ids and 8 in ids


# ---------------------------------------------------------------------------
# user_has_ai_beta_access
# ---------------------------------------------------------------------------

class TestUserHasAiBetaAccess:
    def test_unauthenticated_user_no_access(self, app, db_session):
        with app.app_context():
            user = MagicMock()
            user.is_authenticated = False
            assert svc.user_has_ai_beta_access(user) is False

    def test_none_user_no_access(self, app, db_session):
        with app.app_context():
            assert svc.user_has_ai_beta_access(None) is False

    def test_unrestricted_mode_all_access(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_beta_access_settings(enabled=False, allowed_user_ids=[])
            user = MagicMock()
            user.is_authenticated = True
            assert svc.user_has_ai_beta_access(user) is True

    def test_restricted_system_manager_has_access(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_beta_access_settings(enabled=True, allowed_user_ids=[])
            user = MagicMock()
            user.is_authenticated = True
            with patch("app.services.app_settings_service.AuthorizationService") as mock_auth:
                mock_auth.is_system_manager.return_value = True
                assert svc.user_has_ai_beta_access(user) is True

    def test_restricted_allowed_user_has_access(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_beta_access_settings(enabled=True, allowed_user_ids=[42])
            user = MagicMock()
            user.is_authenticated = True
            user.id = 42
            with patch("app.services.app_settings_service.AuthorizationService") as mock_auth:
                mock_auth.is_system_manager.return_value = False
                assert svc.user_has_ai_beta_access(user) is True

    def test_restricted_non_allowed_user_no_access(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_beta_access_settings(enabled=True, allowed_user_ids=[42])
            user = MagicMock()
            user.is_authenticated = True
            user.id = 99
            with patch("app.services.app_settings_service.AuthorizationService") as mock_auth:
                mock_auth.is_system_manager.return_value = False
                assert svc.user_has_ai_beta_access(user) is False

    def test_restricted_auth_service_exception(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_beta_access_settings(enabled=True, allowed_user_ids=[5])
            user = MagicMock()
            user.is_authenticated = True
            user.id = 5
            with patch("app.services.app_settings_service.AuthorizationService") as mock_auth:
                mock_auth.is_system_manager.side_effect = Exception("boom")
                result = svc.user_has_ai_beta_access(user)
            assert result is True  # in allowed list

    def test_invalid_user_id_returns_false(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_beta_access_settings(enabled=True, allowed_user_ids=[])
            user = MagicMock()
            user.is_authenticated = True
            user.id = "not-an-int"
            with patch("app.services.app_settings_service.AuthorizationService") as mock_auth:
                mock_auth.is_system_manager.return_value = False
                assert svc.user_has_ai_beta_access(user) is False


# ---------------------------------------------------------------------------
# user_is_explicit_beta_tester
# ---------------------------------------------------------------------------

class TestUserIsExplicitBetaTester:
    def test_unauthenticated_false(self, app, db_session):
        with app.app_context():
            user = MagicMock()
            user.is_authenticated = False
            assert svc.user_is_explicit_beta_tester(user) is False

    def test_none_user_false(self, app, db_session):
        with app.app_context():
            assert svc.user_is_explicit_beta_tester(None) is False

    def test_beta_off_returns_false(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_beta_access_settings(enabled=False, allowed_user_ids=[1])
            user = MagicMock()
            user.is_authenticated = True
            assert svc.user_is_explicit_beta_tester(user) is False

    def test_system_manager_not_beta_tester(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_beta_access_settings(enabled=True, allowed_user_ids=[])
            user = MagicMock()
            user.is_authenticated = True
            with patch("app.services.app_settings_service.AuthorizationService") as mock_auth:
                mock_auth.is_system_manager.return_value = True
                assert svc.user_is_explicit_beta_tester(user) is False

    def test_explicit_tester(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_beta_access_settings(enabled=True, allowed_user_ids=[77])
            user = MagicMock()
            user.is_authenticated = True
            user.id = 77
            with patch("app.services.app_settings_service.AuthorizationService") as mock_auth:
                mock_auth.is_system_manager.return_value = False
                assert svc.user_is_explicit_beta_tester(user) is True

    def test_not_in_list(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_beta_access_settings(enabled=True, allowed_user_ids=[77])
            user = MagicMock()
            user.is_authenticated = True
            user.id = 88
            with patch("app.services.app_settings_service.AuthorizationService") as mock_auth:
                mock_auth.is_system_manager.return_value = False
                assert svc.user_is_explicit_beta_tester(user) is False

    def test_auth_service_exception_ignored(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_beta_access_settings(enabled=True, allowed_user_ids=[55])
            user = MagicMock()
            user.is_authenticated = True
            user.id = 55
            with patch("app.services.app_settings_service.AuthorizationService") as mock_auth:
                mock_auth.is_system_manager.side_effect = Exception("boom")
                result = svc.user_is_explicit_beta_tester(user)
            assert result is True

    def test_invalid_user_id_returns_false(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_beta_access_settings(enabled=True, allowed_user_ids=[1])
            user = MagicMock()
            user.is_authenticated = True
            user.id = "invalid"
            with patch("app.services.app_settings_service.AuthorizationService") as mock_auth:
                mock_auth.is_system_manager.return_value = False
                assert svc.user_is_explicit_beta_tester(user) is False


# ---------------------------------------------------------------------------
# apply_ai_settings_to_config
# ---------------------------------------------------------------------------

class TestApplyAiSettingsToConfig:
    def test_applies_non_sensitive_settings(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_settings({"AI_MODEL": "claude-3", "MAX_TOKENS": 2000})
            svc.apply_ai_settings_to_config(app)
            assert app.config.get("AI_MODEL") == "claude-3"

    def test_does_not_apply_sensitive_keys(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            # Directly inject sensitive key into AI settings dict (bypassing set_ai_settings guard)
            from app.models.system import SystemSettings
            SystemSettings.set_value("ai_settings", {"OPENAI_API_KEY": "secret"})
            svc.apply_ai_settings_to_config(app)
            assert app.config.get("OPENAI_API_KEY") != "secret"

    def test_handles_exception_gracefully(self, app, db_session):
        with app.app_context():
            with patch.object(svc, "get_ai_settings", side_effect=Exception("db fail")):
                # Should not raise
                svc.apply_ai_settings_to_config(app)

    def test_skips_empty_settings(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            old_model = app.config.get("AI_MODEL")
            svc.apply_ai_settings_to_config(app)  # No settings stored – should be a no-op


# ---------------------------------------------------------------------------
# Organization branding
# ---------------------------------------------------------------------------

class TestOrganizationBranding:
    def test_set_and_get(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_organization_branding({
                "organization_name": "Test Org",
                "organization_domain": "testorg.org",
            })
            branding = svc.get_organization_branding()
        assert branding["organization_domain"] == "testorg.org"

    def test_requires_dict(self, app, db_session):
        with app.app_context():
            with pytest.raises(ValueError):
                svc.set_organization_branding("not a dict")

    def test_requires_name_and_domain(self, app, db_session):
        with app.app_context():
            with pytest.raises(ValueError):
                svc.set_organization_branding({"organization_name": "Test"})

    def test_localized_name_dict(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_organization_branding({
                "organization_name": {"en": "Test Org", "fr": "Org Test"},
                "organization_domain": "testorg.org",
            })
            branding = svc.get_organization_branding()
        name = branding["organization_name"]
        assert name["en"] == "Test Org"

    def test_localized_name_requires_en(self, app, db_session):
        with app.app_context():
            with pytest.raises(ValueError, match="'en'"):
                svc.set_organization_branding({
                    "organization_name": {"fr": "Org Test"},
                    "organization_domain": "testorg.org",
                })

    def test_optional_fields_excluded_when_empty(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_organization_branding({
                "organization_name": "Test Org",
                "organization_domain": "testorg.org",
                "organization_logo_path": "",
            })
            branding = svc.get_organization_branding()
        assert "organization_logo_path" not in branding

    def test_env_variable_fallback(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            with patch.dict(os.environ, {"ORGANIZATION_NAME": "Env Org", "ORGANIZATION_DOMAIN": "env.org"}):
                branding = svc.get_organization_branding()
        assert branding.get("organization_name") == "Env Org"

    def test_system_default_fallback(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            with patch.dict(os.environ, {}, clear=False):
                for key in ["ORGANIZATION_NAME", "ORGANIZATION_DOMAIN", "ORGANIZATION_SHORT_NAME",
                            "ORGANIZATION_EMAIL_DOMAIN", "ORGANIZATION_LOGO_PATH",
                            "ORGANIZATION_FAVICON_PATH", "ORGANIZATION_COPYRIGHT_YEAR"]:
                    os.environ.pop(key, None)
                branding = svc.get_organization_branding()
        assert "organization_name" in branding

    def test_short_name_derived_from_name(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_organization_branding({
                "organization_name": {"en": "Test Org", "fr": "Org Test"},
                "organization_domain": "testorg.org",
                "organization_short_name": "TO",
            })
            branding = svc.get_organization_branding()
        short = branding["organization_short_name"]
        assert short["en"] == "TO"

    def test_short_name_default_from_name(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_organization_branding({
                "organization_name": "My Org",
                "organization_domain": "myorg.org",
            })
            branding = svc.get_organization_branding()
        assert "organization_short_name" in branding

    def test_user_provided_default_used(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            with patch.dict(os.environ, {}, clear=False):
                for key in ["ORGANIZATION_NAME", "ORGANIZATION_DOMAIN", "ORGANIZATION_SHORT_NAME",
                            "ORGANIZATION_EMAIL_DOMAIN", "ORGANIZATION_LOGO_PATH",
                            "ORGANIZATION_FAVICON_PATH", "ORGANIZATION_COPYRIGHT_YEAR"]:
                    os.environ.pop(key, None)
                default = {"organization_name": "My Default", "organization_domain": "default.org"}
                branding = svc.get_organization_branding(default=default)
        assert branding["organization_name"] == "My Default"


# ---------------------------------------------------------------------------
# Organization name / domain / logo / favicon / copyright
# ---------------------------------------------------------------------------

class TestOrganizationAccessors:
    def _setup_branding(self, app, db_session):
        _clear_settings(db_session, app)
        svc.set_organization_branding({
            "organization_name": {"en": "Test Org", "fr": "Org Test"},
            "organization_short_name": {"en": "TO"},
            "organization_domain": "testorg.org",
            "organization_email_domain": "mail.testorg.org",
            "organization_logo_path": "logo.png",
            "organization_favicon_path": "favicon.ico",
            "organization_copyright_year": "2024",
        })

    def test_get_organization_name(self, app, db_session):
        with app.app_context():
            self._setup_branding(app, db_session)
            assert svc.get_organization_name() == "Test Org"

    def test_get_organization_name_french(self, app, db_session):
        with app.app_context():
            self._setup_branding(app, db_session)
            assert svc.get_organization_name(locale="fr") == "Org Test"

    def test_get_organization_short_name(self, app, db_session):
        with app.app_context():
            self._setup_branding(app, db_session)
            assert svc.get_organization_short_name() == "TO"

    def test_get_organization_domain(self, app, db_session):
        with app.app_context():
            self._setup_branding(app, db_session)
            assert svc.get_organization_domain() == "testorg.org"

    def test_get_organization_email_domain(self, app, db_session):
        with app.app_context():
            self._setup_branding(app, db_session)
            assert svc.get_organization_email_domain() == "mail.testorg.org"

    def test_get_organization_email_domain_fallback(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_organization_branding({
                "organization_name": "X",
                "organization_domain": "x.org",
            })
            # email_domain falls back to organization_domain when not set
            result = svc.get_organization_email_domain()
        assert result == "x.org"

    def test_get_organization_logo_path(self, app, db_session):
        with app.app_context():
            self._setup_branding(app, db_session)
            assert svc.get_organization_logo_path() == "logo.png"

    def test_get_organization_logo_path_default(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            for key in ["ORGANIZATION_NAME", "ORGANIZATION_DOMAIN", "ORGANIZATION_LOGO_PATH"]:
                os.environ.pop(key, None)
            assert svc.get_organization_logo_path() == "logo.svg"

    def test_get_organization_favicon_path(self, app, db_session):
        with app.app_context():
            self._setup_branding(app, db_session)
            assert svc.get_organization_favicon_path() == "favicon.ico"

    def test_get_organization_favicon_path_default(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            for key in ["ORGANIZATION_FAVICON_PATH", "ORGANIZATION_NAME", "ORGANIZATION_DOMAIN"]:
                os.environ.pop(key, None)
            assert svc.get_organization_favicon_path() == "favicon.svg"

    def test_get_organization_copyright_year(self, app, db_session):
        with app.app_context():
            self._setup_branding(app, db_session)
            assert svc.get_organization_copyright_year() == "2024"

    def test_get_organization_copyright_year_default(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            for k in ["ORGANIZATION_COPYRIGHT_YEAR", "ORGANIZATION_NAME", "ORGANIZATION_DOMAIN"]:
                os.environ.pop(k, None)
            year = svc.get_organization_copyright_year()
        assert year == str(datetime.now().year)


# ---------------------------------------------------------------------------
# is_organization_email
# ---------------------------------------------------------------------------

class TestIsOrganizationEmail:
    def test_matching_email(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_organization_branding({
                "organization_name": "Test",
                "organization_domain": "testorg.org",
                "organization_email_domain": "testorg.org",
            })
            assert svc.is_organization_email("user@testorg.org") is True

    def test_non_matching_email(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_organization_branding({
                "organization_name": "Test",
                "organization_domain": "testorg.org",
            })
            assert svc.is_organization_email("user@other.com") is False

    def test_empty_email_false(self, app, db_session):
        with app.app_context():
            assert svc.is_organization_email("") is False

    def test_none_email_false(self, app, db_session):
        with app.app_context():
            assert svc.is_organization_email(None) is False

    def test_case_insensitive(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_organization_branding({
                "organization_name": "Test",
                "organization_domain": "TestOrg.Org",
                "organization_email_domain": "TestOrg.Org",
            })
            assert svc.is_organization_email("USER@TESTORG.ORG") is True


# ---------------------------------------------------------------------------
# _resolve_locale
# ---------------------------------------------------------------------------

class TestResolveLocale:
    def test_explicit_locale(self, app):
        with app.app_context():
            assert svc._resolve_locale("fr") == "fr"

    def test_default_locale_when_none(self, app):
        with app.app_context():
            with patch.object(svc, "has_request_context", return_value=False):
                result = svc._resolve_locale(None)
        assert result == "en"

    def test_locale_from_request_context(self, app):
        with app.test_request_context():
            with patch.object(svc, "has_request_context", return_value=True), \
                 patch.object(svc, "get_locale", return_value="de"):
                result = svc._resolve_locale(None)
        assert result == "de"

    def test_locale_resolution_exception_fallback(self, app):
        with app.test_request_context():
            with patch.object(svc, "has_request_context", return_value=True), \
                 patch.object(svc, "get_locale", side_effect=Exception("broken")):
                result = svc._resolve_locale(None)
        assert result == "en"

    def test_locale_none_from_request(self, app):
        with app.test_request_context():
            with patch.object(svc, "has_request_context", return_value=True), \
                 patch.object(svc, "get_locale", return_value=None):
                result = svc._resolve_locale(None)
        assert result == "en"


# ---------------------------------------------------------------------------
# _extract_localized_value
# ---------------------------------------------------------------------------

class TestExtractLocalizedValue:
    def test_dict_exact_match(self):
        v = {"en": "English", "fr": "Français"}
        assert svc._extract_localized_value(v, "Default", "fr") == "Français"

    def test_dict_base_locale_fallback(self):
        v = {"en": "English"}
        assert svc._extract_localized_value(v, "Default", "en-US") == "English"

    def test_dict_en_fallback(self):
        v = {"en": "English", "fr": "Français"}
        assert svc._extract_localized_value(v, "Default", "de") == "English"

    def test_dict_first_value_fallback(self):
        v = {"fr": "Français"}
        assert svc._extract_localized_value(v, "Default", "de") == "Français"

    def test_empty_dict_returns_default(self):
        assert svc._extract_localized_value({}, "Default", "en") == "Default"

    def test_string_value(self):
        assert svc._extract_localized_value("Plain String", "Default", "en") == "Plain String"

    def test_blank_string_returns_default(self):
        assert svc._extract_localized_value("  ", "Default", "en") == "Default"

    def test_non_string_non_dict_returns_default(self):
        assert svc._extract_localized_value(42, "Default", "en") == "Default"

    def test_dict_with_empty_values_returns_default(self):
        v = {"en": "  ", "fr": ""}
        assert svc._extract_localized_value(v, "Default", "en") == "Default"


# ---------------------------------------------------------------------------
# _strip_visual_path_prefixes
# ---------------------------------------------------------------------------

class TestStripVisualPathPrefixes:
    def test_strips_static_prefix(self):
        assert svc._strip_visual_path_prefixes("static/logo.svg") == "logo.svg"

    def test_strips_multiple_static(self):
        assert svc._strip_visual_path_prefixes("static/static/logo.svg") == "logo.svg"

    def test_strips_leading_slash(self):
        assert svc._strip_visual_path_prefixes("/logo.svg") == "logo.svg"

    def test_no_prefix_unchanged(self):
        assert svc._strip_visual_path_prefixes("logo.svg") == "logo.svg"


# ---------------------------------------------------------------------------
# organization_visual_asset_href
# ---------------------------------------------------------------------------

class TestOrganizationVisualAssetHref:
    def test_static_file(self, app):
        with app.test_request_context():
            app.config["ASSET_VERSION"] = "v2"
            result = svc.organization_visual_asset_href("logo.svg")
        assert "logo.svg" in result
        assert "v=v2" in result

    def test_branding_asset(self, app):
        with app.test_request_context():
            app.config["ASSET_VERSION"] = "v1"
            result = svc.organization_visual_asset_href("branding/custom_logo.png")
        assert "custom_logo.png" in result

    def test_branding_empty_tail_uses_default(self, app):
        with app.test_request_context():
            app.config["ASSET_VERSION"] = "v1"
            result = svc.organization_visual_asset_href("branding/")
        assert "logo.svg" in result

    def test_none_path_uses_default(self, app):
        with app.test_request_context():
            app.config["ASSET_VERSION"] = "v1"
            result = svc.organization_visual_asset_href(None, default="logo.svg")
        assert "logo.svg" in result

    def test_no_asset_version_uses_v1(self, app):
        with app.test_request_context():
            app.config.pop("ASSET_VERSION", None)
            result = svc.organization_visual_asset_href("logo.svg")
        assert "v=v1" in result


# ---------------------------------------------------------------------------
# Chatbot settings
# ---------------------------------------------------------------------------

class TestChatbotSettings:
    def test_get_chatbot_name_default(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("CHATBOT_NAME", None)
                name = svc.get_chatbot_name(default="Assistant")
        assert name == "Assistant"

    def test_env_override(self, app, db_session):
        with app.app_context():
            with patch.dict(os.environ, {"CHATBOT_NAME": "Bot From Env"}):
                name = svc.get_chatbot_name()
        assert name == "Bot From Env"

    def test_set_and_get(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            os.environ.pop("CHATBOT_NAME", None)
            svc.set_chatbot_name("My Bot")
            name = svc.get_chatbot_name()
        assert name == "My Bot"

    def test_set_none_stores_empty(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_chatbot_name(None)
            os.environ.pop("CHATBOT_NAME", None)
            name = svc.get_chatbot_name(default="Fallback")
        assert name == "Fallback"

    def test_set_non_string_raises(self, app, db_session):
        with app.app_context():
            with pytest.raises(ValueError):
                svc.set_chatbot_name(123)

    def test_set_too_long_raises(self, app, db_session):
        with app.app_context():
            with pytest.raises(ValueError, match="too long"):
                svc.set_chatbot_name("x" * 81)

    def test_get_chatbot_org_only_env_true(self, app, db_session):
        with app.app_context():
            with patch.dict(os.environ, {"CHATBOT_ORG_ONLY": "true"}):
                assert svc.get_chatbot_org_only() is True

    def test_get_chatbot_org_only_env_false(self, app, db_session):
        with app.app_context():
            with patch.dict(os.environ, {"CHATBOT_ORG_ONLY": "false"}):
                assert svc.get_chatbot_org_only() is False

    def test_get_chatbot_org_only_db_bool(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_settings({"CHATBOT_ORG_ONLY": True})
            with patch.dict(os.environ, {"CHATBOT_ORG_ONLY": ""}):
                result = svc.get_chatbot_org_only()
        assert result is True

    def test_get_chatbot_org_only_db_string(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_ai_settings({"CHATBOT_ORG_ONLY": "yes"})
            with patch.dict(os.environ, {"CHATBOT_ORG_ONLY": ""}):
                result = svc.get_chatbot_org_only()
        assert result is True

    def test_get_chatbot_org_only_default_false(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            with patch.dict(os.environ, {"CHATBOT_ORG_ONLY": ""}):
                result = svc.get_chatbot_org_only()
        assert result is False


# ---------------------------------------------------------------------------
# Mobile minimum app version
# ---------------------------------------------------------------------------

class TestMobileMinAppVersion:
    def test_set_and_get(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_mobile_min_app_version("2.1.0")
            ver = svc.get_mobile_min_app_version()
        assert ver == "2.1.0"

    def test_invalid_version_raises(self, app, db_session):
        with app.app_context():
            with pytest.raises(ValueError, match="semver"):
                svc.set_mobile_min_app_version("abc")

    def test_too_long_version_raises(self, app, db_session):
        with app.app_context():
            with pytest.raises(ValueError, match="too long"):
                svc.set_mobile_min_app_version("1." * 20)

    def test_non_string_raises(self, app, db_session):
        with app.app_context():
            with pytest.raises(ValueError):
                svc.set_mobile_min_app_version(123)

    def test_empty_clears_setting(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_mobile_min_app_version("1.0.0")
            svc.set_mobile_min_app_version("")
            ver = svc.get_mobile_min_app_version()
        assert ver is None or ver == ""

    def test_none_clears_setting(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_mobile_min_app_version("1.0.0")
            svc.set_mobile_min_app_version(None)

    def test_env_fallback(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            with patch.dict(os.environ, {"MOBILE_MIN_APP_VERSION": "3.0.0"}):
                ver = svc.get_mobile_min_app_version()
        assert ver == "3.0.0"

    def test_config_fallback(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            app.config["MOBILE_MIN_APP_VERSION"] = "4.0.0"
            with patch.dict(os.environ, {"MOBILE_MIN_APP_VERSION": ""}):
                from app.models.system import SystemSettings
                SystemSettings.query.filter_by(
                    setting_key="mobile_min_app_version"
                ).delete()
                db_session.commit()
                ver = svc.get_mobile_min_app_version()
            app.config.pop("MOBILE_MIN_APP_VERSION", None)
        assert ver == "4.0.0"


# ---------------------------------------------------------------------------
# Notification priorities
# ---------------------------------------------------------------------------

class TestNotificationPriorities:
    def test_set_and_get(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_notification_priorities({"assignment_created": "high"})
            result = svc.get_notification_priorities()
        assert result.get("assignment_created") == "high"

    def test_invalid_priority_defaults_to_normal(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_notification_priorities({"assignment_created": "super-urgent"})
            result = svc.get_notification_priorities()
        assert result.get("assignment_created") == "normal"

    def test_empty_key_excluded(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_notification_priorities({"": "high", "assignment_created": "normal"})
            result = svc.get_notification_priorities()
        assert "" not in result

    def test_get_notification_priority(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_notification_priorities({"assignment_created": "urgent"})
            prio = svc.get_notification_priority("assignment_created")
        assert prio == "urgent"

    def test_get_notification_priority_default(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            prio = svc.get_notification_priority("unknown_type", default="low")
        assert prio == "low"

    def test_get_notification_priority_empty_type(self, app, db_session):
        with app.app_context():
            prio = svc.get_notification_priority("", default="normal")
        assert prio == "normal"

    def test_get_notification_priority_enum_value(self, app, db_session):
        """NotificationType-like object (has .value attribute)."""
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_notification_priorities({"assignment_created": "high"})
            nt = MagicMock()
            nt.value = "assignment_created"
            prio = svc.get_notification_priority(nt)
        assert prio == "high"

    def test_get_priorities_invalid_in_db(self, app, db_session):
        """Non-dict stored value returns empty dict."""
        with app.app_context():
            with patch.object(svc, "read_settings", return_value={"notification_priorities": "invalid"}):
                result = svc.get_notification_priorities()
        assert result == {}


# ---------------------------------------------------------------------------
# Notification audience rules
# ---------------------------------------------------------------------------

class TestNotificationAudienceRules:
    def test_get_merged_uses_defaults(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            merged = svc.get_merged_notification_audience_rules()
        assert "assignment_created" in merged

    def test_set_and_get_audience_rules(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_notification_audience_rules({
                "assignment_created": {"focal_points": False}
            })
            rules = svc.get_notification_audience_rules()
        assert rules.get("assignment_created", {}).get("focal_points") is False

    def test_invalid_notification_type_excluded(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_notification_audience_rules({
                "not_a_real_type": {"focal_points": True}
            })
            rules = svc.get_notification_audience_rules()
        assert "not_a_real_type" not in rules

    def test_audience_bucket_enabled(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            result = svc.audience_bucket_enabled("assignment_submitted", "admin_users")
        assert isinstance(result, bool)

    def test_audience_bucket_invalid_bucket(self, app, db_session):
        with app.app_context():
            result = svc.audience_bucket_enabled("assignment_created", "invalid_bucket")
        assert result is False

    def test_audience_bucket_unknown_type(self, app, db_session):
        with app.app_context():
            result = svc.audience_bucket_enabled("unknown_type", "focal_points")
        assert result is False

    def test_audience_bucket_enum_object(self, app, db_session):
        """audience_bucket_enabled accepts enum-like objects with .value."""
        with app.app_context():
            nt = MagicMock()
            nt.value = "assignment_created"
            result = svc.audience_bucket_enabled(nt, "focal_points")
        assert isinstance(result, bool)

    def test_get_audience_rules_invalid_stored_value(self, app, db_session):
        with app.app_context():
            with patch.object(svc, "read_settings",
                              return_value={"notification_audience_rules": "not_a_dict"}):
                result = svc.get_notification_audience_rules()
        assert result == {}

    def test_get_audience_rules_excludes_non_bool_buckets(self, app, db_session):
        with app.app_context():
            with patch.object(svc, "read_settings", return_value={
                "notification_audience_rules": {
                    "assignment_created": {"focal_points": "yes"}  # string, not bool
                }
            }):
                result = svc.get_notification_audience_rules()
        # "yes" is not bool, so should be excluded
        assert "assignment_created" not in result or \
               "focal_points" not in result.get("assignment_created", {})


# ---------------------------------------------------------------------------
# auto_approve_access_requests
# ---------------------------------------------------------------------------

class TestAutoApproveAccessRequests:
    def test_default_false(self):
        with patch.dict(os.environ, {"AUTO_APPROVE_ACCESS_REQUESTS": ""}):
            assert svc.get_auto_approve_access_requests() is False

    def test_truthy_values(self):
        for val in ["1", "true", "yes", "y", "on"]:
            with patch.dict(os.environ, {"AUTO_APPROVE_ACCESS_REQUESTS": val}):
                assert svc.get_auto_approve_access_requests() is True

    def test_false_values(self):
        for val in ["0", "false", "no", "off"]:
            with patch.dict(os.environ, {"AUTO_APPROVE_ACCESS_REQUESTS": val}):
                assert svc.get_auto_approve_access_requests() is False


# ---------------------------------------------------------------------------
# Email templates
# ---------------------------------------------------------------------------

class TestEmailTemplates:
    _VALID_KEY = "email_template_welcome"

    def test_set_and_get_string(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_email_template(self._VALID_KEY, "Hello {{ name }}")
            content = svc.get_email_template(self._VALID_KEY)
        assert "Hello" in content

    def test_set_and_get_dict(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_email_template(self._VALID_KEY, {"en": "Hi", "fr": "Bonjour"})
            en = svc.get_email_template(self._VALID_KEY, language="en")
            fr = svc.get_email_template(self._VALID_KEY, language="fr")
        assert en == "Hi"
        assert fr == "Bonjour"

    def test_get_unknown_language_falls_back_to_en(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_email_template(self._VALID_KEY, {"en": "English only"})
            result = svc.get_email_template(self._VALID_KEY, language="de")
        assert result == "English only"

    def test_get_returns_default_when_missing(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            result = svc.get_email_template(self._VALID_KEY, default="Default Content")
        assert result == "Default Content"

    def test_invalid_key_raises(self, app, db_session):
        with app.app_context():
            with pytest.raises(ValueError):
                svc.get_email_template("invalid_key")

    def test_invalid_key_set_raises(self, app, db_session):
        with app.app_context():
            with pytest.raises(ValueError):
                svc.set_email_template("invalid_key", "content")

    def test_invalid_content_type_raises(self, app, db_session):
        with app.app_context():
            with pytest.raises(ValueError):
                svc.set_email_template(self._VALID_KEY, 12345)

    def test_get_all_email_templates(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.set_email_template(self._VALID_KEY, {"en": "Hi"})
            all_tpl = svc.get_all_email_templates()
        assert self._VALID_KEY in all_tpl
        assert all_tpl[self._VALID_KEY].get("en") == "Hi"

    def test_get_all_email_templates_legacy_string(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            # Store as legacy string directly in the DB
            from app.models.system import SystemSettings
            data = svc.read_settings()
            data.setdefault("email_templates", {})[self._VALID_KEY] = "Legacy string"
            svc.write_settings(data)
            all_tpl = svc.get_all_email_templates()
        assert all_tpl[self._VALID_KEY].get("en") == "Legacy string"

    def test_set_all_email_templates(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            templates = {self._VALID_KEY: {"en": "Welcome", "fr": "Bienvenue"}}
            svc.set_all_email_templates(templates)
            all_tpl = svc.get_all_email_templates()
        assert "en" in all_tpl[self._VALID_KEY]

    def test_set_all_email_templates_invalid_type_raises(self, app, db_session):
        with app.app_context():
            with pytest.raises(ValueError):
                svc.set_all_email_templates("not a dict")

    def test_set_all_email_templates_invalid_key_raises(self, app, db_session):
        with app.app_context():
            with pytest.raises(ValueError):
                svc.set_all_email_templates({"bad_key": "content"})

    def test_set_all_email_templates_with_metadata(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            templates = {self._VALID_KEY: {"en": "Hi"}}
            metadata = {self._VALID_KEY: {"label": "Welcome Email", "priority": "high"}}
            svc.set_all_email_templates(templates, metadata=metadata)
            notif_tpl = svc.get_notification_templates()
        assert notif_tpl[self._VALID_KEY]["label"] == "Welcome Email"

    def test_set_all_email_templates_string_content(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            templates = {self._VALID_KEY: "String Content"}
            svc.set_all_email_templates(templates)
            all_tpl = svc.get_all_email_templates()
        assert all_tpl[self._VALID_KEY].get("en") == "String Content"

    def test_get_notification_templates(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            result = svc.get_notification_templates()
        assert self._VALID_KEY in result
        assert "label" in result[self._VALID_KEY]

    def test_get_template_metadata_alias(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            assert svc.get_template_metadata() == svc.get_notification_templates()


# ---------------------------------------------------------------------------
# get_frontend_url
# ---------------------------------------------------------------------------

class TestGetFrontendUrl:
    def test_env_override(self, app, db_session):
        with app.app_context():
            with patch.dict(os.environ, {"FRONTEND_URL": "https://env.example.com"}):
                result = svc.get_frontend_url()
        assert result == "https://env.example.com"

    def test_db_setting(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            svc.write_settings({"frontend_url": "https://db.example.com"})
            with patch.dict(os.environ, {"FRONTEND_URL": ""}):
                result = svc.get_frontend_url()
        assert result == "https://db.example.com"

    def test_returns_default_when_unset(self, app, db_session):
        with app.app_context():
            _clear_settings(db_session, app)
            with patch.dict(os.environ, {"FRONTEND_URL": ""}):
                result = svc.get_frontend_url(default="https://default.example.com")
        assert result == "https://default.example.com"


# ---------------------------------------------------------------------------
# _is_lang_key
# ---------------------------------------------------------------------------

class TestIsLangKey:
    def test_valid_en(self):
        assert svc._is_lang_key("en") is True

    def test_valid_fr(self):
        assert svc._is_lang_key("fr") is True

    def test_metadata_key_label(self):
        assert svc._is_lang_key("label") is False

    def test_metadata_key_priority(self):
        assert svc._is_lang_key("priority") is False

    def test_empty_string(self):
        assert svc._is_lang_key("") is False

    def test_none(self):
        assert svc._is_lang_key(None) is False

    def test_too_short(self):
        assert svc._is_lang_key("e") is False

    def test_too_long(self):
        assert svc._is_lang_key("toolong") is False

    def test_with_numbers_invalid(self):
        assert svc._is_lang_key("en123") is False
