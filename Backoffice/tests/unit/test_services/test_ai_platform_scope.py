"""Tests for platform scope heuristics (humanitarian databank vs general chat)."""

import pytest


def test_heuristic_in_scope_data_queries(app):
    from app.services.ai.planning.query_rewriter import heuristic_likely_in_platform_scope

    with app.app_context():
        assert heuristic_likely_in_platform_scope("volunteers in Syria 2024") is True
        assert heuristic_likely_in_platform_scope("Which MENA countries have UPL documents?") is True
        assert heuristic_likely_in_platform_scope("What can you do?") is True


def test_heuristic_in_scope_not_generically_true_for_coding_requests(app):
    from app.services.ai.planning.query_rewriter import heuristic_likely_in_platform_scope

    with app.app_context():
        assert heuristic_likely_in_platform_scope("generate a code of a calculator app in python") is False
        assert heuristic_likely_in_platform_scope("Write me a tkinter GUI for tic tac toe") is False


def test_is_message_in_platform_scope_respects_disable_flag(app):
    from app.services.ai.planning.query_rewriter import is_message_in_platform_scope

    with app.app_context():
        app.config["AI_PLATFORM_SCOPE_ENFORCE_ENABLED"] = False
        assert is_message_in_platform_scope("any random thing") is True


def test_classify_skips_llm_when_heuristics_settle_it_even_with_rewrite_enabled(app, monkeypatch):
    """Substantive in-scope questions must not pay a model round trip (rewrite never changes the text)."""
    from app.services.ai.planning import query_rewriter

    def _boom(*_a, **_k):
        raise AssertionError("unified preflight LLM must not run for a clearly in-scope data question")

    monkeypatch.setattr(query_rewriter, "_unified_preflight_llm", _boom)

    with app.app_context():
        app.config["OPENAI_API_KEY"] = "sk-test"
        app.config["AI_QUERY_REWRITE_ENABLED"] = True
        app.config["AI_PLATFORM_SCOPE_ENFORCE_ENABLED"] = True
        rewritten, greeting, in_scope = query_rewriter.classify_and_rewrite_user_message(
            "what are these documents"
        )
    assert (rewritten, greeting, in_scope) == ("what are these documents", False, True)


def test_classify_still_uses_llm_for_short_ambiguous_messages(app, monkeypatch):
    from app.services.ai.planning import query_rewriter

    calls = []

    def _fake(raw, **_k):
        calls.append(raw)
        return raw, True, True

    monkeypatch.setattr(query_rewriter, "_unified_preflight_llm", _fake)

    with app.app_context():
        app.config["OPENAI_API_KEY"] = "sk-test"
        app.config["AI_QUERY_REWRITE_ENABLED"] = True
        out = query_rewriter.classify_and_rewrite_user_message("hello there")
    assert calls == ["hello there"]
    assert out == ("hello there", True, True)
