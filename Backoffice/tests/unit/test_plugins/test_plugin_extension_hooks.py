"""CLI discovery, plugin-owned hooks consumed by core, and secrets encryption at rest."""
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.plugins.base import AiToolSet
from app.plugins.cli_discovery import register_plugin_cli_commands
from app.plugins.secret_store import PREFIX, decrypt_secrets, encrypt_secrets

from .test_manager import _make_manager
from .test_manager_lifecycle import _load, _write_plugin


@pytest.mark.unit
class TestCliDiscovery:
    def test_registers_commands_from_plugin_cli_modules(self):
        flask_app = Flask("cli-test")
        registered = register_plugin_cli_commands(flask_app)
        assert "fdrs" in registered and "nsd_report_forms" in registered
        assert {"fdrs-public-export", "nsd-migrate-projects", "nsd-migrate-slots"} <= set(flask_app.cli.commands)

    def test_missing_plugins_root_is_not_an_error(self, tmp_path):
        assert register_plugin_cli_commands(Flask("x"), tmp_path / "absent") == []


@pytest.mark.unit
class TestManagerHooks:
    def test_list_option_count_returns_first_definite_answer(self, tmp_path):
        pm, d = _make_manager(tmp_path)
        _write_plugin(d, "a_plugin")
        _write_plugin(d, "b_plugin")
        _load(pm)
        pm.plugins["a_plugin"].get_list_option_count = lambda *a: None
        pm.plugins["b_plugin"].get_list_option_count = lambda *a: 0
        assert pm.get_list_option_count("lst", object(), object()) == 0

    def test_list_option_count_defaults_to_unknown(self, tmp_path):
        pm, d = _make_manager(tmp_path)
        _write_plugin(d, "a_plugin")
        _load(pm)
        assert pm.get_list_option_count("lst", object(), object()) is None

    def test_materialize_document_prefers_a_claiming_plugin(self, tmp_path):
        pm, d = _make_manager(tmp_path)
        _write_plugin(d, "a_plugin")
        _load(pm)
        pm.plugins["a_plugin"].materialize_document = lambda doc: (False, "private")
        assert pm.materialize_document(object()) == (False, "private")

    def test_materialize_document_unclaimed(self, tmp_path):
        pm, d = _make_manager(tmp_path)
        _write_plugin(d, "a_plugin")
        _load(pm)
        assert pm.materialize_document(object()) == (False, None)

    def test_ai_tool_sets_collect_and_skip_broken_plugins(self, tmp_path):
        pm, d = _make_manager(tmp_path)
        _write_plugin(d, "a_plugin")
        _write_plugin(d, "b_plugin")
        _load(pm)
        spec = {"type": "function", "function": {"name": "demo_tool"}}
        tool_set = AiToolSet(specs=[spec], functions={"demo_tool": lambda: {"ok": True}})
        pm.plugins["a_plugin"].get_ai_tools = lambda: tool_set

        def boom():
            raise RuntimeError("nope")

        pm.plugins["b_plugin"].get_ai_tools = boom
        sets = pm.get_ai_tool_sets()
        assert sets == [tool_set]
        assert tool_set.names == frozenset({"demo_tool"})
        assert tool_set.is_available() is True


@pytest.mark.unit
class TestSecretsAtRest:
    def _app(self, key):
        flask_app = Flask("secrets-test")
        if key:
            flask_app.config["PLUGIN_SECRETS_KEY"] = key
        return flask_app

    def test_round_trip_encrypts_only_secret_looking_strings(self):
        data = {"mapbox": {"api_key": "abc", "style": "x", "rows": [{"token": "t"}]}, "password": "********"}
        with self._app("passphrase").app_context():
            stored = encrypt_secrets(data)
            assert stored["mapbox"]["api_key"].startswith(PREFIX)
            assert stored["mapbox"]["rows"][0]["token"].startswith(PREFIX)
            assert stored["mapbox"]["style"] == "x"
            assert stored["password"] == "********"
            assert decrypt_secrets(stored) == data

    def test_without_key_nothing_changes(self):
        data = {"api_key": "abc"}
        with self._app(None).app_context():
            assert encrypt_secrets(data) == data
            assert decrypt_secrets(data) == data

    def test_plaintext_stays_readable_after_enabling_the_key(self):
        with self._app("passphrase").app_context():
            assert decrypt_secrets({"api_key": "plain"}) == {"api_key": "plain"}

    def test_already_encrypted_values_are_not_encrypted_twice(self):
        with self._app("passphrase").app_context():
            once = encrypt_secrets({"api_key": "abc"})
            assert encrypt_secrets(once) == once
