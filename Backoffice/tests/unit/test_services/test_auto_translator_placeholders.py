"""Tests for MT placeholder protection in auto_translator."""

from unittest.mock import MagicMock

import pytest

from app.services.translation.auto_translator import (
    AutoTranslator,
    _MT_JINJA_TOKEN_PREFIX,
    _MT_VAR_TOKEN_PREFIX,
)

pytestmark = [pytest.mark.unit]


class TestProtectVariables:
    def test_bracket_placeholder_replaced_with_opaque_token(self):
        protected, token_map = AutoTranslator._protect_variables(
            "National Society [assignment_period] Total Funding"
        )
        assert "[assignment_period]" not in protected
        assert len(token_map) == 1
        token = next(iter(token_map))
        assert token.startswith(_MT_VAR_TOKEN_PREFIX)
        assert "IFRC" not in token
        assert "PLACEHOLDER" not in token.upper()
        assert token_map[token] == "[assignment_period]"
        assert token in protected

    def test_multiple_placeholders_get_distinct_tokens(self):
        protected, token_map = AutoTranslator._protect_variables(
            "Hello [a] and [b]"
        )
        assert len(token_map) == 2
        tokens = list(token_map.keys())
        assert tokens[0] != tokens[1]
        for token in tokens:
            assert token.startswith(_MT_VAR_TOKEN_PREFIX)

    def test_restore_roundtrip(self):
        original = "National Society [assignment_period] Total Funding"
        protected, token_map = AutoTranslator._protect_variables(original)
        restored = AutoTranslator._restore_variables(protected, token_map)
        assert restored == original

    def test_restore_after_simulated_french_translation(self):
        original = "National Society [assignment_period] Total Funding"
        protected, token_map = AutoTranslator._protect_variables(original)
        token = next(iter(token_map))
        simulated = (
            f"Société nationale {token} un financement total"
        )
        restored = AutoTranslator._restore_variables(simulated, token_map)
        assert restored == f"Société nationale [assignment_period] un financement total"
        assert "IFRC" not in restored
        assert "PLACEHOLDER" not in restored.upper()


class TestProtectJinjaExpressions:
    def test_jinja_uses_distinct_opaque_prefix(self):
        protected, token_map = AutoTranslator._protect_jinja_expressions(
            "Hello {{ user.name }}!"
        )
        token = next(iter(token_map))
        assert token.startswith(_MT_JINJA_TOKEN_PREFIX)
        assert "JINJA" not in token.upper()
        assert token_map[token] == "{{ user.name }}"


class TestTokenPreservationCheck:
    def test_rejects_mangled_placeholder_response(self):
        original = "National Society [assignment_period] Total Funding"
        protected, token_map = AutoTranslator._protect_variables(original)
        token = next(iter(token_map))
        assert AutoTranslator._all_tokens_preserved(protected, token_map)

        mangled = protected.replace(
            token,
            "IFRC Titulaire de place",
        )
        assert not AutoTranslator._all_tokens_preserved(mangled, token_map)


class TestTranslateTextRejectsMangledTokens:
    def test_falls_back_when_service_mangles_placeholder(self):
        tr = AutoTranslator.__new__(AutoTranslator)
        tr.services = {}
        tr.default_service = None

        good_svc = MagicMock()
        good_svc.service_name = "google"
        good_svc.translate_text.return_value = None

        bad_svc = MagicMock()
        bad_svc.service_name = "ifrc"

        original = "National Society [assignment_period] Total Funding"
        protected, token_map = AutoTranslator._protect_variables(original)
        token = next(iter(token_map))
        bad_svc.translate_text.return_value = protected.replace(
            token, "IFRC Titulaire de place"
        )

        ok_svc = MagicMock()
        ok_svc.service_name = "fallback"
        ok_svc.translate_text.return_value = protected.replace(
            token, token
        ).replace(
            "National Society",
            "Société nationale",
        )

        tr.services = {"ifrc": bad_svc, "fallback": ok_svc}
        tr.default_service = "ifrc"

        result = tr.translate_text(original, "fr", "en", service_name=None)
        assert result == "Société nationale [assignment_period] Total Funding"
        assert "IFRC" not in (result or "")
        bad_svc.translate_text.assert_called_once()
        ok_svc.translate_text.assert_called_once()
