"""Tests for platform scope heuristics (humanitarian databank vs general chat)."""

import pytest


def test_heuristic_in_scope_data_queries(app):
    from app.services.ai_query_rewriter import heuristic_likely_in_platform_scope

    with app.app_context():
        assert heuristic_likely_in_platform_scope("volunteers in Syria 2024") is True
        assert heuristic_likely_in_platform_scope("Which MENA countries have UPL documents?") is True
        assert heuristic_likely_in_platform_scope("What can you do?") is True


def test_heuristic_in_scope_not_generically_true_for_coding_requests(app):
    from app.services.ai_query_rewriter import heuristic_likely_in_platform_scope

    with app.app_context():
        assert heuristic_likely_in_platform_scope("generate a code of a calculator app in python") is False
        assert heuristic_likely_in_platform_scope("Write me a tkinter GUI for tic tac toe") is False


def test_is_message_in_platform_scope_respects_disable_flag(app):
    from app.services.ai_query_rewriter import is_message_in_platform_scope

    with app.app_context():
        app.config["AI_PLATFORM_SCOPE_ENFORCE_ENABLED"] = False
        assert is_message_in_platform_scope("any random thing") is True
