"""
Embedding provider protocol for the RAG pipeline.

Defines the contract that all embedding implementations must satisfy.
This module is pure — no I/O, no network calls, no side effects.
Concrete implementations (e.g., OpenAI) live outside core/.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    """
    Protocol for embedding providers.

    Any class that implements ``embed_texts`` and ``embedding_dim``
    can be used as an embedding backend in the ingestion pipeline.
    """

    @property
    def embedding_dim(self) -> int:
        """Dimensionality of the embedding vectors produced by this provider."""
        ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a batch of texts into dense vectors.

        Args:
            texts: Non-empty list of strings to embed.

        Returns:
            List of embedding vectors, one per input text.
            Each vector has length ``embedding_dim``.

        Raises:
            ValueError: If texts is empty.
        """
        ...
