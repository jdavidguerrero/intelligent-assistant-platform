"""Tests for the EmbeddingProvider protocol in core/embeddings/base.py."""

from core.embeddings.base import EmbeddingProvider


class _FakeProvider:
    """Minimal implementation satisfying EmbeddingProvider."""

    @property
    def embedding_dim(self) -> int:
        return 3

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 3 for _ in texts]


class _IncompleteProvider:
    """Missing embed_texts — should NOT satisfy the protocol."""

    @property
    def embedding_dim(self) -> int:
        return 3


class TestEmbeddingProviderProtocol:
    def test_fake_provider_satisfies_protocol(self) -> None:
        provider = _FakeProvider()
        assert isinstance(provider, EmbeddingProvider)

    def test_incomplete_provider_fails_protocol(self) -> None:
        provider = _IncompleteProvider()
        assert not isinstance(provider, EmbeddingProvider)

    def test_fake_provider_returns_correct_dim(self) -> None:
        provider = _FakeProvider()
        assert provider.embedding_dim == 3

    def test_fake_provider_embed_texts_shape(self) -> None:
        provider = _FakeProvider()
        result = provider.embed_texts(["hello", "world"])
        assert len(result) == 2
        assert all(len(v) == 3 for v in result)
