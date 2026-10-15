"""Tests for MT placeholder protection in auto_translator."""

import threading
from unittest.mock import MagicMock, patch

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

    def test_brace_format_field_replaced_with_opaque_token(self):
        protected, token_map = AutoTranslator._protect_variables(
            ". {admin_users} admins in-app"
        )
        assert "{admin_users}" not in protected
        assert len(token_map) == 1
        token = next(iter(token_map))
        assert token.startswith(_MT_VAR_TOKEN_PREFIX)
        assert token_map[token] == "{admin_users}"
        assert token in protected

    def test_brace_format_roundtrip(self):
        original = ". {admin_users} admins in-app"
        protected, token_map = AutoTranslator._protect_variables(original)
        assert AutoTranslator._restore_variables(protected, token_map) == original

    def test_brace_format_restore_after_simulated_arabic(self):
        original = ". {admin_users} admins in-app"
        protected, token_map = AutoTranslator._protect_variables(original)
        token = next(iter(token_map))
        # Engine translates the surrounding prose and preserves the opaque token.
        simulated = protected.replace("admins in-app", "مسؤولون داخل التطبيق")
        restored = AutoTranslator._restore_variables(simulated, token_map)
        assert restored == ". {admin_users} مسؤولون داخل التطبيق"
        assert "{admin_users}" in restored

    def test_brace_format_with_spec_and_access(self):
        original = "{count:,} of {obj[key]} ({value!r}) for {user.name}"
        protected, token_map = AutoTranslator._protect_variables(original)
        assert len(token_map) == 4
        for original_field in ("{count:,}", "{obj[key]}", "{value!r}", "{user.name}"):
            assert original_field not in protected
            assert original_field in token_map.values()
        assert AutoTranslator._restore_variables(protected, token_map) == original

    def test_jinja_braces_not_treated_as_format_fields(self):
        # `_protect_variables` must leave Jinja constructs alone (handled elsewhere).
        protected, token_map = AutoTranslator._protect_variables(
            "Hello {{ user.name }} and {% if x %}y{% endif %}"
        )
        assert token_map == {}
        assert protected == "Hello {{ user.name }} and {% if x %}y{% endif %}"

    def test_escaped_literal_braces_untouched(self):
        protected, token_map = AutoTranslator._protect_variables("Use {{ and }} literally")
        assert token_map == {}
        assert protected == "Use {{ and }} literally"

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


class TestFinalizeProtectedTranslation:
    def test_restores_and_validates_python_format_placeholders(self):
        original = "Showing the %(loaded)d most recent of %(total)d processed requests."
        protected, token_map = AutoTranslator._protect_variables(original)
        tokens = list(token_map.keys())
        simulated_fr = protected.replace(tokens[0], "le").replace(tokens[1], tokens[1])
        restored = AutoTranslator._finalize_protected_translation(original, simulated_fr, token_map)
        assert restored is not None
        assert "%(loaded)d" in restored
        assert "%(total)d" in restored

    def test_rejects_when_placeholders_cannot_be_restored(self):
        original = "%(count)d items"
        protected, token_map = AutoTranslator._protect_variables(original)
        restored = AutoTranslator._finalize_protected_translation(original, "articles", token_map)
        assert restored is not None
        assert "%(count)d" in restored


class TestTranslateTextRejectsMangledTokens:
    def test_falls_back_when_service_mangles_placeholder(self):
        tr = AutoTranslator.__new__(AutoTranslator)
        tr.services = {}
        tr.default_service = None
        tr._engine_trace = threading.local()

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

        # Isolate from the DB-backed result cache so the mocked engines are exercised
        # regardless of any persisted entry for this string.
        with patch(
            "app.services.translation.result_cache.get_cached", return_value=None
        ), patch("app.services.translation.result_cache.put_cached"):
            result = tr.translate_text(original, "fr", "en", service_name=None)
        assert result == "Société nationale [assignment_period] Total Funding"
        assert "IFRC" not in (result or "")
        bad_svc.translate_text.assert_called_once()
        ok_svc.translate_text.assert_called_once()


class TestKeepsSourceWhenUntranslatable:
    """When an engine can only echo a short/placeholder string unchanged and no other
    engine translates it, keep the source instead of dropping it to None (a "skip")."""

    @staticmethod
    def _translator(services, default):
        tr = AutoTranslator.__new__(AutoTranslator)
        tr.services = services
        tr.default_service = default
        # `__new__` bypasses __init__; the success path records engine usage.
        tr._engine_trace = threading.local()
        return tr

    def test_translate_text_keeps_source_on_unchanged_echo(self):
        # First engine echoes the (protected) input unchanged; the fallback engine is down.
        echo = MagicMock()
        echo.service_name = "google"
        echo.translate_text.side_effect = lambda t, tgt, src="en": t
        down = MagicMock()
        down.service_name = "libre"
        down.translate_text.return_value = None

        tr = self._translator({"google": echo, "libre": down}, "google")
        # Unique placeholder name keeps the result-cache key distinct from sibling
        # tests while the (short) prose stays below the suspicious-echo threshold.
        src = ". {admin_echo_case} admins in-app"
        result = tr.translate_text(src, "ar", "en")

        assert result == src
        echo.translate_text.assert_called_once()
        down.translate_text.assert_called_once()

    def test_translate_text_prefers_real_translation_over_source_fallback(self):
        echo = MagicMock()
        echo.service_name = "google"
        echo.translate_text.side_effect = lambda t, tgt, src="en": t
        real = MagicMock()
        real.service_name = "libre"
        # Translates the prose but preserves the opaque placeholder token.
        real.translate_text.side_effect = lambda t, tgt, src="en": t.replace(
            "admins online now", "مسؤولون متصلون الآن"
        )

        tr = self._translator({"google": echo, "libre": real}, "google")
        result = tr.translate_text(". {admin_users} admins online now", "ar", "en")

        assert result == ". {admin_users} مسؤولون متصلون الآن"

    def test_translate_text_still_none_for_suspicious_long_echo(self):
        # Long multi-word English echo is a real failure, not a legitimately-unchanged
        # string: it must NOT be persisted as a copy-source "translation".
        long_src = "National Society total funding received during the reporting period"
        echo = MagicMock()
        echo.service_name = "google"
        echo.translate_text.side_effect = lambda t, tgt, src="en": t
        down = MagicMock()
        down.service_name = "libre"
        down.translate_text.return_value = None

        tr = self._translator({"google": echo, "libre": down}, "google")
        assert tr.translate_text(long_src, "ar", "en") is None

    def test_translate_batch_keeps_source_on_unchanged_echo(self):
        echo = MagicMock()
        echo.service_name = "google"
        echo.translate_batch.side_effect = lambda texts, tgt, src="en": list(texts)
        down = MagicMock()
        down.service_name = "libre"
        down.translate_batch.return_value = None

        tr = self._translator({"google": echo, "libre": down}, "google")
        src = ". {admin_batch_case} admins in-app"
        out = tr.translate_batch([src], "ar", "en")

        assert out == [src]
