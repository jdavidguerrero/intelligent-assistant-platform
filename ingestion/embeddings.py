"""
OpenAI embedding provider.

Implements the ``EmbeddingProvider`` protocol from core using
the OpenAI embeddings API.  Lives in ingestion/ because it
performs network I/O (core/ must remain pure).
"""

import os

import openai
from dotenv import load_dotenv

from ingestion.cache import EmbeddingCache


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
        cache_enabled: bool = True,
        cache_max_size: int = 1000,
        cache_ttl_seconds: float = 3600.0,
    ) -> None:
        load_dotenv()
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not resolved_key:
            raise ValueError("OPENAI_API_KEY must be set in the environment or passed explicitly")
        self._client = openai.OpenAI(api_key=resolved_key)
        self._model = model
        # text-embedding-3-small produces 1536-dim vectors by default
        self._embedding_dim = 1536

        # Optional embedding cache with TTL + LRU
        self._cache_enabled = cache_enabled
        if cache_enabled:
            self._cache = EmbeddingCache(max_size=cache_max_size, ttl_seconds=cache_ttl_seconds)
        else:
            self._cache = None

        # Track cache hit/miss for response metadata
        self._last_cache_hit = False

    @property
    def embedding_dim(self) -> int:
        """Dimensionality of vectors produced by this provider."""
        return self._embedding_dim

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a batch of texts via the OpenAI API (with optional caching).

        Args:
            texts: Non-empty list of strings.

        Returns:
            List of embedding vectors (each of length ``embedding_dim``).

        Raises:
            ValueError: If *texts* is empty.
        """
        if not texts:
            raise ValueError("texts must be a non-empty list")

        # Single-query optimization: check cache for single text
        if len(texts) == 1 and self._cache_enabled and self._cache:
            cached = self._cache.get(texts[0])
            if cached is not None:
                self._last_cache_hit = True
                return [cached]

        # Cache miss or batch request: call API
        self._last_cache_hit = False
        response = self._client.embeddings.create(input=texts, model=self._model)
        # Sort by index to guarantee order matches input
        sorted_data = sorted(response.data, key=lambda d: d.index)
        embeddings = [item.embedding for item in sorted_data]

        # Cache single-query result
        if len(texts) == 1 and self._cache_enabled and self._cache:
            self._cache.put(texts[0], embeddings[0])

        return embeddings

    @property
    def last_cache_hit(self) -> bool:
        """
        Check if the last embed_texts() call was a cache hit.

        Returns:
            True if last embedding was retrieved from cache, False otherwise.
        """
        return self._last_cache_hit
