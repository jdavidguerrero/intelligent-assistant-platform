"""Prometheus metrics for the Musical Intelligence Platform.

Exposes musical context in metrics so dashboards show production-session
patterns, not just generic HTTP stats.

Metrics:
    ask_requests_total               Counter by status (hit/miss/error/degraded) and subdomain
    ask_latency_seconds              Histogram of end-to-end /ask latency
    cache_hits_total                 Counter of response cache hits
    cache_misses_total               Counter of response cache misses
    embedding_cache_hits_total       Counter of embedding cache hits
    rate_limited_total               Requests rejected by rate limiter
    circuit_breaker_trips_total      Times a circuit breaker tripped to OPEN
    circuit_breaker_rejected_total   Calls rejected while circuit is OPEN

Usage::

    from infrastructure.metrics import (
        record_ask,
        record_cache_hit,
        record_cache_miss,
        record_embedding_cache_hit,
    )
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

# Lazy import — prometheus_client is optional. If not installed, all calls
# are no-ops and the /metrics endpoint is simply not registered.
_registry_available = False
try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Histogram,
        generate_latest,
    )

    _REGISTRY = CollectorRegistry()

    ask_requests_total = Counter(
        "mip_ask_requests_total",
        "Total /ask requests by status and subdomain",
        ["status", "subdomain"],
        registry=_REGISTRY,
    )

    ask_latency_seconds = Histogram(
        "mip_ask_latency_seconds",
        "End-to-end /ask latency in seconds",
        ["subdomain"],
        buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
        registry=_REGISTRY,
    )

    cache_hits_total = Counter(
        "mip_cache_hits_total",
        "Response cache hits (Redis)",
        registry=_REGISTRY,
    )

    cache_misses_total = Counter(
        "mip_cache_misses_total",
        "Response cache misses (Redis)",
        registry=_REGISTRY,
    )

    embedding_cache_hits_total = Counter(
        "mip_embedding_cache_hits_total",
        "Embedding cache hits (in-memory)",
        registry=_REGISTRY,
    )

    rate_limited_total = Counter(
        "mip_rate_limited_total",
        "Requests rejected by rate limiter",
        registry=_REGISTRY,
    )

    circuit_breaker_trips_total = Counter(
        "mip_circuit_breaker_trips_total",
        "Number of times a circuit breaker tripped to OPEN state",
        ["breaker_name"],
        registry=_REGISTRY,
    )

    circuit_breaker_rejected_total = Counter(
        "mip_circuit_breaker_rejected_total",
        "Requests rejected because circuit was OPEN (short-circuited)",
        ["breaker_name"],
        registry=_REGISTRY,
    )

    _registry_available = True
    logger.info("Prometheus metrics registry initialized")

except ImportError:
    logger.info("prometheus_client not installed — metrics disabled")
    _REGISTRY = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Public helpers — all are no-ops when prometheus_client is not installed
# ---------------------------------------------------------------------------


def record_ask(
    *,
    status: str,
    subdomain: str,
    latency_seconds: float,
) -> None:
    """Record a completed /ask request.

    Args:
        status: One of "success", "cache_hit", "rejected", "error".
        subdomain: Detected subdomain or "global".
        latency_seconds: End-to-end wall-clock time in seconds.
    """
    if not _registry_available:
        return
    ask_requests_total.labels(status=status, subdomain=subdomain).inc()
    ask_latency_seconds.labels(subdomain=subdomain).observe(latency_seconds)


def record_cache_hit() -> None:
    """Increment response cache hit counter."""
    if _registry_available:
        cache_hits_total.inc()


def record_cache_miss() -> None:
    """Increment response cache miss counter."""
    if _registry_available:
        cache_misses_total.inc()


def record_embedding_cache_hit() -> None:
    """Increment embedding (in-memory) cache hit counter."""
    if _registry_available:
        embedding_cache_hits_total.inc()


def record_rate_limited() -> None:
    """Increment rate-limited requests counter."""
    if _registry_available:
        rate_limited_total.inc()


def record_circuit_trip(breaker_name: str) -> None:
    """Increment circuit breaker trip counter.

    Args:
        breaker_name: Name of the circuit breaker that tripped.
    """
    if _registry_available:
        circuit_breaker_trips_total.labels(breaker_name=breaker_name).inc()


def record_circuit_rejected(breaker_name: str) -> None:
    """Increment circuit breaker rejected-call counter.

    Args:
        breaker_name: Name of the circuit breaker that rejected the call.
    """
    if _registry_available:
        circuit_breaker_rejected_total.labels(breaker_name=breaker_name).inc()


def get_metrics_response() -> tuple[bytes, str]:
    """Generate Prometheus text exposition format.

    Returns:
        Tuple of (body_bytes, content_type_string).
        Returns empty bytes if prometheus_client is not available.
    """
    if not _registry_available:
        return b"", "text/plain"
    return generate_latest(_REGISTRY), CONTENT_TYPE_LATEST


class LatencyTimer:
    """Context manager for measuring latency.

    Usage::

        with LatencyTimer() as t:
            result = run_pipeline()
        record_ask(status="success", subdomain="mixing", latency_seconds=t.elapsed)
    """

    def __init__(self) -> None:
        """Initialize timer."""
        self._start: float = 0.0
        self.elapsed: float = 0.0

    def __enter__(self) -> LatencyTimer:
        """Start timing."""
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_: object) -> None:
        """Stop timing and record elapsed."""
        self.elapsed = time.perf_counter() - self._start
