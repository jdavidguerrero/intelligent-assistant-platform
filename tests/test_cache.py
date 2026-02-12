"""Tests for embedding cache with TTL and LRU eviction."""

import time

from ingestion.cache import EmbeddingCache


class TestEmbeddingCache:
    """Tests for EmbeddingCache class."""

    def test_cache_hit(self) -> None:
        """Cached embedding is retrieved on second request."""
        cache = EmbeddingCache(max_size=10, ttl_seconds=60.0)
        embedding = [0.1, 0.2, 0.3]

        # First request - miss
        assert cache.get("test query") is None

        # Store embedding
        cache.put("test query", embedding)

        # Second request - hit
        cached = cache.get("test query")
        assert cached == embedding

    def test_cache_miss_different_query(self) -> None:
        """Different query results in cache miss."""
        cache = EmbeddingCache(max_size=10, ttl_seconds=60.0)
        cache.put("query one", [0.1, 0.2])

        # Different query - miss
        assert cache.get("query two") is None

    def test_lru_eviction(self) -> None:
        """Least recently used entry is evicted when cache is full."""
        cache = EmbeddingCache(max_size=3, ttl_seconds=60.0)

        cache.put("query1", [0.1])
        cache.put("query2", [0.2])
        cache.put("query3", [0.3])

        # Cache is full (3 entries)
        assert cache.size() == 3

        # Add 4th entry - should evict query1 (oldest)
        cache.put("query4", [0.4])

        assert cache.size() == 3
        assert cache.get("query1") is None  # Evicted
        assert cache.get("query2") == [0.2]  # Still present
        assert cache.get("query3") == [0.3]
        assert cache.get("query4") == [0.4]

    def test_lru_reordering_on_get(self) -> None:
        """Accessing an entry marks it as recently used."""
        cache = EmbeddingCache(max_size=2, ttl_seconds=60.0)

        cache.put("query1", [0.1])
        cache.put("query2", [0.2])

        # Access query1 - moves to end
        cache.get("query1")

        # Add query3 - should evict query2 (now oldest)
        cache.put("query3", [0.3])

        assert cache.get("query1") == [0.1]  # Still present
        assert cache.get("query2") is None  # Evicted
        assert cache.get("query3") == [0.3]

    def test_ttl_expiration(self) -> None:
        """Expired entries return None on get."""
        cache = EmbeddingCache(max_size=10, ttl_seconds=0.1)  # 100ms TTL

        cache.put("query", [0.1, 0.2])

        # Immediate access - hit
        assert cache.get("query") == [0.1, 0.2]

        # Wait for expiration
        time.sleep(0.15)

        # Expired - miss
        assert cache.get("query") is None

    def test_evict_expired_manual(self) -> None:
        """Manual eviction removes expired entries."""
        cache = EmbeddingCache(max_size=10, ttl_seconds=0.1)

        cache.put("query1", [0.1])
        cache.put("query2", [0.2])

        assert cache.size() == 2

        # Wait for expiration
        time.sleep(0.15)

        # Manual eviction
        evicted = cache.evict_expired()

        assert evicted == 2
        assert cache.size() == 0

    def test_clear_cache(self) -> None:
        """Clear removes all entries."""
        cache = EmbeddingCache(max_size=10, ttl_seconds=60.0)

        cache.put("query1", [0.1])
        cache.put("query2", [0.2])
        cache.put("query3", [0.3])

        assert cache.size() == 3

        cache.clear()

        assert cache.size() == 0
        assert cache.get("query1") is None
        assert cache.get("query2") is None

    def test_update_existing_entry(self) -> None:
        """Updating an existing entry refreshes timestamp."""
        cache = EmbeddingCache(max_size=10, ttl_seconds=60.0)

        cache.put("query", [0.1])
        cached1 = cache.get("query")

        # Update same query with new embedding
        cache.put("query", [0.2])
        cached2 = cache.get("query")

        assert cached1 == [0.1]
        assert cached2 == [0.2]  # Updated value
        assert cache.size() == 1  # Still only 1 entry

    def test_case_sensitive_queries(self) -> None:
        """Cache keys are case-sensitive."""
        cache = EmbeddingCache(max_size=10, ttl_seconds=60.0)

        cache.put("Query", [0.1])
        cache.put("query", [0.2])

        # Different cases = different cache keys
        assert cache.get("Query") == [0.1]
        assert cache.get("query") == [0.2]
        assert cache.size() == 2
