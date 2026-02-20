"""Tests for infrastructure/ resilience layer.

Covers:
- ResponseCache: get/set/invalidate/flush, graceful Redis failure
- RateLimiter: allow/deny, sliding window, graceful failure
- retry decorator: backoff, max attempts, exception filtering
- metrics: no-op when prometheus_client absent
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from infrastructure.cache import ResponseCache, _make_key, _tag_key
from infrastructure.rate_limiter import RateLimiter
from infrastructure.retry import with_retry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cache_no_redis() -> ResponseCache:
    """ResponseCache with Redis patched to fail — exercises no-op path."""
    with patch("infrastructure.cache.redis_lib") as mock_redis:
        mock_redis.from_url.side_effect = ConnectionError("no redis")
        cache = ResponseCache(redis_url="redis://nowhere:9999/0")
    return cache


def _make_mock_redis() -> MagicMock:
    """Create a mock Redis client that behaves like a real one."""
    client = MagicMock()
    client.ping.return_value = True
    client.get.return_value = None
    client.setex.return_value = True
    client.smembers.return_value = set()
    client.delete.return_value = 1
    client.sadd.return_value = 1
    client.expire.return_value = True
    client.pipeline.return_value.__enter__ = MagicMock(return_value=MagicMock())
    client.pipeline.return_value.__exit__ = MagicMock(return_value=False)
    return client


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------


class TestCacheKeyHelpers:
    def test_make_key_deterministic(self) -> None:
        k1 = _make_key("How to EQ kick?", top_k=5, threshold=0.58)
        k2 = _make_key("How to EQ kick?", top_k=5, threshold=0.58)
        assert k1 == k2

    def test_make_key_namespace(self) -> None:
        assert _make_key("q", top_k=5, threshold=0.5).startswith("mip:resp:")

    def test_make_key_case_insensitive(self) -> None:
        k1 = _make_key("How to EQ kick?", top_k=5, threshold=0.58)
        k2 = _make_key("how to eq kick?", top_k=5, threshold=0.58)
        assert k1 == k2

    def test_make_key_differs_on_top_k(self) -> None:
        k1 = _make_key("q", top_k=5, threshold=0.58)
        k2 = _make_key("q", top_k=10, threshold=0.58)
        assert k1 != k2

    def test_make_key_differs_on_threshold(self) -> None:
        k1 = _make_key("q", top_k=5, threshold=0.58)
        k2 = _make_key("q", top_k=5, threshold=0.70)
        assert k1 != k2

    def test_tag_key_namespace(self) -> None:
        assert _tag_key("Bob_Katz.pdf").startswith("mip:tag:")

    def test_tag_key_deterministic(self) -> None:
        assert _tag_key("Bob_Katz.pdf") == _tag_key("Bob_Katz.pdf")


# ---------------------------------------------------------------------------
# ResponseCache — no Redis
# ---------------------------------------------------------------------------


class TestResponseCacheNoRedis:
    def test_available_false_when_redis_unreachable(self) -> None:
        cache = _make_cache_no_redis()
        assert cache.available is False

    def test_get_returns_none_when_unavailable(self) -> None:
        cache = _make_cache_no_redis()
        assert cache.get("anything", top_k=5, threshold=0.58) is None

    def test_set_is_noop_when_unavailable(self) -> None:
        cache = _make_cache_no_redis()
        # Should not raise
        cache.set("q", top_k=5, threshold=0.58, response={"answer": "x"})

    def test_invalidate_returns_zero_when_unavailable(self) -> None:
        cache = _make_cache_no_redis()
        assert cache.invalidate_source("Bob_Katz.pdf") == 0

    def test_flush_returns_zero_when_unavailable(self) -> None:
        cache = _make_cache_no_redis()
        assert cache.flush() == 0

    def test_stats_returns_unavailable(self) -> None:
        cache = _make_cache_no_redis()
        stats = cache.stats()
        assert stats["available"] is False


# ---------------------------------------------------------------------------
# ResponseCache — with mock Redis
# ---------------------------------------------------------------------------


class TestResponseCacheWithRedis:
    def _make_cache(self) -> tuple[ResponseCache, MagicMock]:
        mock_client = _make_mock_redis()
        with patch("infrastructure.cache.redis_lib") as mock_redis_mod:
            mock_redis_mod.from_url.return_value = mock_client
            cache = ResponseCache(redis_url="redis://localhost:6379/0")
        cache._client = mock_client
        return cache, mock_client

    def test_available_true_with_redis(self) -> None:
        cache, _ = self._make_cache()
        assert cache.available is True

    def test_get_miss_returns_none(self) -> None:
        cache, mock_client = self._make_cache()
        mock_client.get.return_value = None
        result = cache.get("unknown query", top_k=5, threshold=0.58)
        assert result is None

    def test_get_hit_returns_parsed_dict(self) -> None:
        import json

        cache, mock_client = self._make_cache()
        payload = {"answer": "Use a high-pass filter.", "citations": [1]}
        mock_client.get.return_value = json.dumps(payload)
        result = cache.get("EQ vocals", top_k=5, threshold=0.58)
        assert result == payload

    def test_set_calls_setex(self) -> None:
        cache, mock_client = self._make_cache()
        cache.set("q", top_k=5, threshold=0.58, response={"answer": "x"})
        assert mock_client.setex.called

    def test_set_registers_source_tags(self) -> None:
        cache, mock_client = self._make_cache()
        cache.set(
            "q",
            top_k=5,
            threshold=0.58,
            response={"answer": "x"},
            sources=["Bob_Katz.pdf"],
        )
        mock_client.sadd.assert_called_once()
        call_args = mock_client.sadd.call_args[0]
        assert call_args[0] == _tag_key("Bob_Katz.pdf")

    def test_invalidate_source_deletes_tagged_keys(self) -> None:
        cache, mock_client = self._make_cache()
        mock_client.smembers.return_value = {"mip:resp:abc", "mip:resp:def"}
        deleted = cache.invalidate_source("Bob_Katz.pdf")
        assert deleted == 1
        assert mock_client.delete.called

    def test_invalidate_source_no_tags_returns_zero(self) -> None:
        cache, mock_client = self._make_cache()
        mock_client.smembers.return_value = set()
        deleted = cache.invalidate_source("nonexistent.pdf")
        assert deleted == 0

    def test_get_error_returns_none_gracefully(self) -> None:
        cache, mock_client = self._make_cache()
        mock_client.get.side_effect = ConnectionError("Redis down")
        result = cache.get("q", top_k=5, threshold=0.58)
        assert result is None

    def test_set_error_does_not_raise(self) -> None:
        cache, mock_client = self._make_cache()
        mock_client.setex.side_effect = ConnectionError("Redis down")
        # Must not raise
        cache.set("q", top_k=5, threshold=0.58, response={"answer": "x"})


# ---------------------------------------------------------------------------
# RateLimiter — no Redis
# ---------------------------------------------------------------------------


class TestRateLimiterNoRedis:
    def _make_limiter_no_redis(self) -> RateLimiter:
        with patch("infrastructure.rate_limiter.redis_lib") as mock_redis:
            mock_redis.from_url.side_effect = ConnectionError("no redis")
            return RateLimiter(redis_url="redis://nowhere:9999/0")

    def test_available_false(self) -> None:
        limiter = self._make_limiter_no_redis()
        assert limiter.available is False

    def test_allow_always_true_when_unavailable(self) -> None:
        limiter = self._make_limiter_no_redis()
        for _ in range(100):
            assert limiter.allow("session1") is True

    def test_remaining_returns_max_when_unavailable(self) -> None:
        limiter = self._make_limiter_no_redis()
        assert limiter.remaining("session1") == 30


# ---------------------------------------------------------------------------
# RateLimiter — with mock Redis
# ---------------------------------------------------------------------------


class TestRateLimiterWithRedis:
    def _make_limiter(self, max_requests: int = 3) -> tuple[RateLimiter, MagicMock]:
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        with patch("infrastructure.rate_limiter.redis_lib") as mock_redis_mod:
            mock_redis_mod.from_url.return_value = mock_client
            limiter = RateLimiter(max_requests=max_requests, window_seconds=60)
        limiter._client = mock_client
        return limiter, mock_client

    def test_allow_returns_true_under_limit(self) -> None:
        limiter, mock_client = self._make_limiter(max_requests=5)
        # pipeline returns [None, 2, 1, True] — 2 existing requests, under limit of 5
        pipe_mock = MagicMock()
        pipe_mock.execute.return_value = [None, 2, 1, True]
        mock_client.pipeline.return_value = pipe_mock
        assert limiter.allow("session1") is True

    def test_allow_returns_false_at_limit(self) -> None:
        limiter, mock_client = self._make_limiter(max_requests=3)
        # 3 existing requests = at limit
        pipe_mock = MagicMock()
        pipe_mock.execute.return_value = [None, 3, 1, True]
        mock_client.pipeline.return_value = pipe_mock
        assert limiter.allow("session1") is False

    def test_allow_fails_open_on_redis_error(self) -> None:
        limiter, mock_client = self._make_limiter()
        mock_client.pipeline.side_effect = ConnectionError("Redis down")
        assert limiter.allow("session1") is True


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------


class TestWithRetry:
    def test_succeeds_on_first_attempt(self) -> None:
        call_count = 0

        @with_retry(max_attempts=3, base_seconds=0.0)
        def fn() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        result = fn()
        assert result == "ok"
        assert call_count == 1

    def test_retries_on_failure_then_succeeds(self) -> None:
        call_count = 0

        @with_retry(max_attempts=3, base_seconds=0.0, exceptions=(ValueError,))
        def fn() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("transient")
            return "ok"

        result = fn()
        assert result == "ok"
        assert call_count == 3

    def test_raises_after_max_attempts(self) -> None:
        @with_retry(max_attempts=3, base_seconds=0.0, exceptions=(ValueError,))
        def fn() -> None:
            raise ValueError("always fails")

        with pytest.raises(RuntimeError, match="failed after 3 attempts"):
            fn()

    def test_does_not_retry_unregistered_exception(self) -> None:
        call_count = 0

        @with_retry(max_attempts=3, base_seconds=0.0, exceptions=(ValueError,))
        def fn() -> None:
            nonlocal call_count
            call_count += 1
            raise TypeError("not retried")

        with pytest.raises(TypeError):
            fn()
        assert call_count == 1

    def test_preserves_return_value(self) -> None:
        @with_retry(max_attempts=2, base_seconds=0.0)
        def fn() -> dict:
            return {"key": "value"}

        assert fn() == {"key": "value"}

    def test_preserves_function_name(self) -> None:
        @with_retry(max_attempts=2, base_seconds=0.0)
        def my_function() -> None:
            pass

        assert my_function.__name__ == "my_function"


# ---------------------------------------------------------------------------
# Metrics — no-op when prometheus_client absent
# ---------------------------------------------------------------------------


class TestMetricsNoOp:
    def test_record_ask_noop(self) -> None:
        from infrastructure import metrics

        orig = metrics._registry_available
        metrics._registry_available = False
        try:
            # Should not raise
            metrics.record_ask(status="success", subdomain="mixing", latency_seconds=0.5)
        finally:
            metrics._registry_available = orig

    def test_record_cache_hit_noop(self) -> None:
        from infrastructure import metrics

        orig = metrics._registry_available
        metrics._registry_available = False
        try:
            metrics.record_cache_hit()
            metrics.record_cache_miss()
            metrics.record_embedding_cache_hit()
            metrics.record_rate_limited()
        finally:
            metrics._registry_available = orig

    def test_get_metrics_response_empty_when_unavailable(self) -> None:
        from infrastructure import metrics

        orig = metrics._registry_available
        metrics._registry_available = False
        try:
            body, content_type = metrics.get_metrics_response()
            assert body == b""
        finally:
            metrics._registry_available = orig

    def test_latency_timer(self) -> None:
        import time

        from infrastructure.metrics import LatencyTimer

        with LatencyTimer() as t:
            time.sleep(0.01)

        assert t.elapsed >= 0.01
        assert t.elapsed < 1.0
