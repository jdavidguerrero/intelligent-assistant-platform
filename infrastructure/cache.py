"""Redis-backed response cache for the Musical Intelligence Platform.

Two cache tiers:
    1. Embedding cache (in-memory, already in ingestion/cache.py) — fast, per-process.
    2. Response cache (Redis) — shared across workers, survives restarts.

Response cache key = SHA-256(query + top_k + confidence_threshold).
Entries are stored as JSON with a TTL. Invalidation is tag-based: every entry
is tagged with its source filenames; when a source is re-ingested the tag is
deleted, expiring all dependent responses.

Usage::

    from infrastructure.cache import ResponseCache

    cache = ResponseCache()
    hit = cache.get(query, top_k=5, threshold=0.58)
    if hit:
        return hit
    result = ... # run pipeline
    cache.set(query, top_k=5, threshold=0.58, response=result, sources=["bob_katz.pdf"])
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

try:
    import redis as redis_lib
except ImportError:
    redis_lib = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Cache TTL: 24 hours. Musical knowledge doesn't change within a session.
_DEFAULT_TTL_SECONDS = 86_400
# Tag TTL: slightly longer so invalidation has time to propagate.
_TAG_TTL_SECONDS = 90_000
# Redis key namespace
_NS = "mip:resp:"
_TAG_NS = "mip:tag:"


def _make_key(query: str, top_k: int, threshold: float) -> str:
    """Deterministic cache key from query parameters.

    Args:
        query: The user query string.
        top_k: Number of results requested.
        threshold: Confidence threshold used.

    Returns:
        Namespaced Redis key string.
    """
    raw = f"{query.strip().lower()}|{top_k}|{threshold:.4f}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"{_NS}{digest}"


def _tag_key(source_name: str) -> str:
    """Redis key for a source invalidation tag set.

    Args:
        source_name: Filename or source identifier.

    Returns:
        Namespaced Redis key for the tag set.
    """
    return f"{_TAG_NS}{source_name}"


class ResponseCache:
    """Redis-backed cache for /ask responses.

    Falls back gracefully to a no-op if Redis is unavailable — the API
    continues working, just without caching.

    Args:
        redis_url: Redis connection URL (default: from REDIS_URL env var or
            ``redis://localhost:6379/0``).
        ttl_seconds: Cache TTL in seconds (default: 86400 = 24h).
    """

    def __init__(
        self,
        redis_url: str | None = None,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        """Initialize Redis connection (lazy — fails gracefully)."""
        self._ttl = ttl_seconds
        self._client: Any = None
        url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        try:
            if redis_lib is None:
                raise ImportError("redis package not installed")
            self._client = redis_lib.from_url(url, decode_responses=True, socket_timeout=0.5)
            self._client.ping()
            logger.info("ResponseCache: connected to Redis at %s", url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ResponseCache: Redis unavailable (%s) — caching disabled", exc)
            self._client = None

    @property
    def available(self) -> bool:
        """True if Redis is reachable."""
        return self._client is not None

    def get(self, query: str, *, top_k: int, threshold: float) -> dict[str, Any] | None:
        """Return cached response dict or None on miss / error.

        Args:
            query: User query string.
            top_k: Number of results parameter.
            threshold: Confidence threshold parameter.

        Returns:
            Cached response dict if found and valid, None otherwise.
        """
        if not self._client:
            return None
        key = _make_key(query, top_k, threshold)
        try:
            raw = self._client.get(key)
            if raw is None:
                return None
            data: dict[str, Any] = json.loads(raw)
            logger.debug("ResponseCache HIT: %s", query[:60])
            return data
        except Exception as exc:  # noqa: BLE001
            logger.warning("ResponseCache.get error: %s", exc)
            return None

    def set(
        self,
        query: str,
        *,
        top_k: int,
        threshold: float,
        response: dict[str, Any],
        sources: list[str] | None = None,
    ) -> None:
        """Store response in cache and register source tags.

        Args:
            query: User query string.
            top_k: Number of results parameter.
            threshold: Confidence threshold parameter.
            response: Full response dict to cache.
            sources: List of source filenames cited in the response.
                Used for tag-based invalidation.
        """
        if not self._client:
            return
        key = _make_key(query, top_k, threshold)
        try:
            payload = json.dumps(response)
            self._client.setex(key, self._ttl, payload)

            # Register key under each source tag for invalidation
            if sources:
                for source in sources:
                    tag = _tag_key(source)
                    self._client.sadd(tag, key)
                    self._client.expire(tag, _TAG_TTL_SECONDS)

            logger.debug("ResponseCache SET: %s (sources=%s)", query[:60], sources)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ResponseCache.set error: %s", exc)

    def invalidate_source(self, source_name: str) -> int:
        """Invalidate all cached responses that cited a given source.

        Called after re-ingestion of a document to ensure stale answers
        are not served.

        Args:
            source_name: Filename or source identifier to invalidate.

        Returns:
            Number of cache entries deleted.
        """
        if not self._client:
            return 0
        tag = _tag_key(source_name)
        try:
            keys = self._client.smembers(tag)
            if not keys:
                return 0
            deleted = self._client.delete(*keys)
            self._client.delete(tag)
            logger.info(
                "ResponseCache: invalidated %d entries for source '%s'", deleted, source_name
            )
            return int(deleted)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ResponseCache.invalidate_source error: %s", exc)
            return 0

    def flush(self) -> int:
        """Delete all response cache entries (not embedding cache).

        Returns:
            Number of keys deleted.
        """
        if not self._client:
            return 0
        try:
            keys = list(self._client.scan_iter(f"{_NS}*"))
            tag_keys = list(self._client.scan_iter(f"{_TAG_NS}*"))
            all_keys = keys + tag_keys
            if not all_keys:
                return 0
            deleted = self._client.delete(*all_keys)
            logger.info("ResponseCache: flushed %d keys", deleted)
            return int(deleted)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ResponseCache.flush error: %s", exc)
            return 0

    def stats(self) -> dict[str, Any]:
        """Return basic cache statistics.

        Returns:
            Dict with keys: available, response_keys, tag_keys.
        """
        if not self._client:
            return {"available": False, "response_keys": 0, "tag_keys": 0}
        try:
            resp_keys = sum(1 for _ in self._client.scan_iter(f"{_NS}*"))
            tag_keys = sum(1 for _ in self._client.scan_iter(f"{_TAG_NS}*"))
            return {"available": True, "response_keys": resp_keys, "tag_keys": tag_keys}
        except Exception as exc:  # noqa: BLE001
            logger.warning("ResponseCache.stats error: %s", exc)
            return {"available": False, "response_keys": 0, "tag_keys": 0}
