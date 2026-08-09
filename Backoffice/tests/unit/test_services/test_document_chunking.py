"""Tests for semantic chunking minimum-size safeguard."""

from app.services.ai.documents.chunking import AIChunkingService


class TestSemanticChunkingMinSize:
    def test_merges_trailing_tiny_chunk_into_previous(self, app):
        with app.app_context():
            chunker = AIChunkingService()
            chunker.min_chunk_size = 20
            text = (
                "This is a substantive paragraph about humanitarian operations and partnerships. "
                "It contains enough tokens to exceed the minimum chunk size on its own clearly.\n\n"
                "PARTNERSHIPS"
            )
            chunks = chunker.chunk_document(text, strategy="semantic")

        assert len(chunks) == 1
        assert "PARTNERSHIPS" in chunks[0].content
        assert chunker.count_tokens(chunks[0].content) >= 20
