"""
Embedding cache with TTL (Time-To-Live) and LRU (Least Recently Used) eviction.

Reduces latency for repeated queries by caching embedding API results.
"""

import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class CacheEntry:
    """Cached embedding with metadata."""

    embedding: list[float]
    timestamp: float  # Unix timestamp when cached
    query: str  # Original query text for debugging


class EmbeddingCache:
    """
    Thread-safe embedding cache with TTL and LRU eviction.

    Args:
        max_size: Maximum number of entries (default: 1000)
        ttl_seconds: Time-to-live in seconds (default: 3600 = 1 hour)
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: float = 3600.0) -> None:
        """Initialize cache with size and TTL limits."""
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = Lock()

    def _make_key(self, query: str) -> str:
        """
        Generate cache key from query text.

        Uses SHA256 hash to avoid collisions and support arbitrary-length queries.

        Args:
            query: Query text

        Returns:
            Hex-encoded SHA256 hash
        """
        return hashlib.sha256(query.encode("utf-8")).hexdigest()

    def get(self, query: str) -> list[float] | None:
        """
        Retrieve cached embedding if available and not expired.

        Args:
            query: Query text

        Returns:
            Cached embedding vector if found and valid, None otherwise
        """
        key = self._make_key(query)

        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                return None

            # Check TTL expiration
            age = time.time() - entry.timestamp
            if age > self.ttl_seconds:
                # Expired - remove from cache
                del self._cache[key]
                return None

            # Move to end (mark as recently used)
            self._cache.move_to_end(key)

            return entry.embedding

    def put(self, query: str, embedding: list[float]) -> None:
        """
        Store embedding in cache with current timestamp.

        Evicts least-recently-used entry if cache is full.

        Args:
            query: Query text
            embedding: Embedding vector to cache
        """
        key = self._make_key(query)

        with self._lock:
            # Evict LRU entry if at capacity
            if len(self._cache) >= self.max_size and key not in self._cache:
                # Remove oldest (first) item
                self._cache.popitem(last=False)

            # Store entry (or update if exists)
            entry = CacheEntry(
                embedding=embedding,
                timestamp=time.time(),
                query=query,
            )
            self._cache[key] = entry

            # Move to end (mark as recently used)
            self._cache.move_to_end(key)

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        """Return current number of cached entries."""
        with self._lock:
            return len(self._cache)

    def evict_expired(self) -> int:
        """
        Remove all expired entries based on TTL.

        Returns:
            Number of entries evicted
        """
        now = time.time()
        evicted = 0

        with self._lock:
            # Collect expired keys
            expired_keys = [
                key
                for key, entry in self._cache.items()
                if (now - entry.timestamp) > self.ttl_seconds
            ]

            # Remove expired entries
            for key in expired_keys:
                del self._cache[key]
                evicted += 1

        return evicted
