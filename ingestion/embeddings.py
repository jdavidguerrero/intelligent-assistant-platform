"""
OpenAI embedding provider.

Implements the ``EmbeddingProvider`` protocol from core using
the OpenAI embeddings API.  Lives in ingestion/ because it
performs network I/O (core/ must remain pure).
"""

import os

import openai
from dotenv import load_dotenv


class OpenAIEmbeddingProvider:
    """
    Embedding provider backed by OpenAI's text-embedding models.

    Reads ``OPENAI_API_KEY`` from the environment.  Model name is
    configurable (default: ``text-embedding-3-small``).

    Satisfies the ``EmbeddingProvider`` protocol.
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        *,
        api_key: str | None = None,
    ) -> None:
        load_dotenv()
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not resolved_key:
            raise ValueError("OPENAI_API_KEY must be set in the environment or passed explicitly")
        self._client = openai.OpenAI(api_key=resolved_key)
        self._model = model
        # text-embedding-3-small produces 1536-dim vectors by default
        self._embedding_dim = 1536

    @property
    def embedding_dim(self) -> int:
        """Dimensionality of vectors produced by this provider."""
        return self._embedding_dim

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a batch of texts via the OpenAI API.

        Args:
            texts: Non-empty list of strings.

        Returns:
            List of embedding vectors (each of length ``embedding_dim``).

        Raises:
            ValueError: If *texts* is empty.
        """
        if not texts:
            raise ValueError("texts must be a non-empty list")

        response = self._client.embeddings.create(input=texts, model=self._model)
        # Sort by index to guarantee order matches input
        sorted_data = sorted(response.data, key=lambda d: d.index)
        return [item.embedding for item in sorted_data]
