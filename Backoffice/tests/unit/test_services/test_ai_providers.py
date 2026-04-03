"""
Unit tests for app.services.ai_providers (embedding and chat provider abstractions).
"""

import pytest


class TestLocalEmbeddingProvider:
    """Tests for LocalEmbeddingProvider."""

    def test_generate_embedding(self):
        """Local provider returns deterministic vector and zero cost."""
        from app.services.ai_providers.local_embedding import LocalEmbeddingProvider

        provider = LocalEmbeddingProvider(dimensions=64, model_name="local")
        emb, cost = provider.generate_embedding("hello world")
        assert len(emb) == 64
        assert all(isinstance(x, float) for x in emb)
        assert cost == 0.0

    def test_generate_embedding_same_text_same_vector(self):
        """Same text produces same vector."""
        from app.services.ai_providers.local_embedding import LocalEmbeddingProvider

        provider = LocalEmbeddingProvider(dimensions=32)
        emb1, _ = provider.generate_embedding("same")
        emb2, _ = provider.generate_embedding("same")
        assert emb1 == emb2

    def test_generate_embeddings_batch(self):
        """Batch returns one vector per non-empty text."""
        from app.services.ai_providers.local_embedding import LocalEmbeddingProvider

        provider = LocalEmbeddingProvider(dimensions=16)
        texts = ["a", "b", "c"]
        embeddings, cost = provider.generate_embeddings_batch(texts)
        assert len(embeddings) == 3
        assert cost == 0.0

    def test_empty_text_raises(self):
        """Empty text raises ValueError."""
        from app.services.ai_providers.local_embedding import LocalEmbeddingProvider

        provider = LocalEmbeddingProvider(dimensions=16)
        with pytest.raises(ValueError, match="empty"):
            provider.generate_embedding("")
        with pytest.raises(ValueError, match="empty"):
            provider.generate_embedding("   ")


class TestGetEmbeddingProvider:
    """Tests for get_embedding_provider() factory."""

    def test_local_provider_when_config_local(self, app):
        """When AI_EMBEDDING_PROVIDER=local, factory returns LocalEmbeddingProvider."""
        with app.app_context():
            app.config["AI_EMBEDDING_PROVIDER"] = "local"
            app.config["AI_EMBEDDING_DIMENSIONS"] = 128
            from app.services.ai_providers import get_embedding_provider
            from app.services.ai_providers.local_embedding import LocalEmbeddingProvider

            provider = get_embedding_provider()
            assert isinstance(provider, LocalEmbeddingProvider)
            assert provider.get_dimensions() >= 1
            emb, cost = provider.generate_embedding("test")
            assert len(emb) == provider.get_dimensions()
            assert cost == 0.0

    def test_openai_provider_requires_key(self, app):
        """When provider=openai and no key, OpenAIEmbeddingProvider raises in __init__."""
        with app.app_context():
            app.config["AI_EMBEDDING_PROVIDER"] = "openai"
            app.config["OPENAI_API_KEY"] = ""
            from app.services.ai_providers import get_embedding_provider

            with pytest.raises((ValueError, RuntimeError), match="OPENAI|key|required"):
                get_embedding_provider()
