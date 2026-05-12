"""
Unit tests for app.utils.ai_pricing (centralized model pricing).
"""

import pytest


class TestAIPricing:
    """Tests for get_chat_pricing, get_embedding_pricing, estimate_chat_cost."""

    def test_get_chat_pricing_exact_model(self):
        """Exact model name returns correct per-token pricing."""
        from app.utils.ai_pricing import get_chat_pricing

        p = get_chat_pricing("gpt-5-mini")
        assert "input" in p
        assert "output" in p
        assert 0 < p["input"] < 1
        assert 0 < p["output"] < 1

    def test_get_chat_pricing_fallback_pattern(self):
        """Unknown model falls back by pattern (e.g. gpt-5 -> gpt-5-mini)."""
        from app.utils.ai_pricing import get_chat_pricing

        p = get_chat_pricing("gpt-5-some-variant")
        assert "input" in p
        assert "output" in p

    def test_estimate_chat_cost(self):
        """estimate_chat_cost returns non-negative USD."""
        from app.utils.ai_pricing import estimate_chat_cost

        cost = estimate_chat_cost("gpt-5-mini", 1000, 500)
        assert isinstance(cost, (int, float))
        assert cost >= 0

    def test_get_embedding_pricing_exact_model(self):
        """Embedding model returns per-token cost."""
        from app.utils.ai_pricing import get_embedding_pricing

        per_token = get_embedding_pricing("text-embedding-3-small")
        assert isinstance(per_token, (int, float))
        assert per_token >= 0

    def test_get_embedding_pricing_unknown_fallback(self):
        """Unknown embedding model falls back to default."""
        from app.utils.ai_pricing import get_embedding_pricing

        per_token = get_embedding_pricing("unknown-model")
        assert per_token >= 0

    def test_chat_pricing_override_from_config(self, app):
        """AI_MODEL_PRICING config override is used when in app context."""
        from app.utils.ai_pricing import get_chat_pricing, _get_config_overrides

        with app.app_context():
            app.config["AI_MODEL_PRICING"] = {
                "chat": {
                    "gpt-5-mini": {"input": 1.0, "output": 2.0},
                },
            }
            # Force re-read (module caches _ENABLED, not overrides)
            p = get_chat_pricing("gpt-5-mini")
            # Override is per 1M tokens, we return per-token
            assert p["input"] == 1.0 / 1_000_000
            assert p["output"] == 2.0 / 1_000_000
