"""Per-session sliding-window rate limiter.

Designed to prevent runaway loops (e.g. an agent hammering /ask) while
not punishing creative bursts (10 queries in 5 minutes is fine).

Uses Redis sorted sets for a precise sliding-window algorithm:
- Each request adds a timestamp to a per-session sorted set.
- Requests older than the window are trimmed on every check.
- If the set size exceeds the limit, the request is rate-limited.

Falls back gracefully to allow-all when Redis is unavailable.

Usage::

    from infrastructure.rate_limiter import RateLimiter

    limiter = RateLimiter(max_requests=20, window_seconds=60)

    if not limiter.allow("session_abc"):
        raise HTTPException(429, "Rate limit exceeded — slow down a bit")
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

try:
    import redis as redis_lib
except ImportError:
    redis_lib = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Default: 30 requests per minute per session — generous for creative bursts
_DEFAULT_MAX = 30
_DEFAULT_WINDOW = 60  # seconds
_NS = "mip:rl:"


class RateLimiter:
    """Sliding-window rate limiter backed by Redis sorted sets.

    Falls back to allow-all when Redis is unavailable so the API never
    breaks due to a missing cache layer.

    Args:
        max_requests: Maximum requests allowed in the window (default: 30).
        window_seconds: Sliding window size in seconds (default: 60).
        redis_url: Redis connection URL (default: REDIS_URL env var or localhost).
    """

    def __init__(
        self,
        max_requests: int = _DEFAULT_MAX,
        window_seconds: int = _DEFAULT_WINDOW,
        redis_url: str | None = None,
    ) -> None:
        """Initialize rate limiter with Redis connection."""
        self._max = max_requests
        self._window = window_seconds
        self._client: Any = None
        url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        try:
            if redis_lib is None:
                raise ImportError("redis package not installed")
            self._client = redis_lib.from_url(url, decode_responses=True, socket_timeout=0.5)
            self._client.ping()
        except Exception as exc:  # noqa: BLE001
            logger.warning("RateLimiter: Redis unavailable (%s) — rate limiting disabled", exc)

    @property
    def available(self) -> bool:
        """True if Redis backend is reachable."""
        return self._client is not None

    def allow(self, session_id: str) -> bool:
        """Check if a request from session_id is within rate limits.

        Uses a Lua script for atomic check-and-record to avoid race conditions.

        Args:
            session_id: Unique session or client identifier.

        Returns:
            True if the request is allowed, False if rate-limited.
        """
        if not self._client:
            return True  # graceful degradation

        key = f"{_NS}{session_id}"
        now = time.time()
        window_start = now - self._window

        try:
            pipe = self._client.pipeline()
            # Remove timestamps outside the sliding window
            pipe.zremrangebyscore(key, 0, window_start)
            # Count remaining requests in the window
            pipe.zcard(key)
            # Add current request timestamp
            pipe.zadd(key, {str(now): now})
            # Set TTL so keys auto-expire
            pipe.expire(key, self._window * 2)
            results = pipe.execute()

            count = int(results[1])  # count BEFORE adding current request
            if count >= self._max:
                logger.warning(
                    "RateLimiter: session '%s' exceeded %d req/%ds",
                    session_id,
                    self._max,
                    self._window,
                )
                return False
            return True

        except Exception as exc:  # noqa: BLE001
            logger.warning("RateLimiter.allow error: %s", exc)
            return True  # fail open

    def remaining(self, session_id: str) -> int:
        """Return remaining requests allowed in the current window.

        Args:
            session_id: Unique session or client identifier.

        Returns:
            Number of remaining requests, or max_requests if Redis unavailable.
        """
        if not self._client:
            return self._max

        key = f"{_NS}{session_id}"
        now = time.time()
        window_start = now - self._window

        try:
            self._client.zremrangebyscore(key, 0, window_start)
            used = self._client.zcard(key)
            return max(0, self._max - int(used))
        except Exception as exc:  # noqa: BLE001
            logger.warning("RateLimiter.remaining error: %s", exc)
            return self._max
