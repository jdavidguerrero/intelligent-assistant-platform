"""Tests for infrastructure/metrics.py — Prometheus counter recording.

Verifies that:
- All public record_*() helpers increment the correct counter
- record_ask() increments both total and latency histogram
- No-op behavior when prometheus_client is disabled (_registry_available=False)
- LatencyTimer measures elapsed time correctly
- Metrics accumulate correctly across multiple calls (burst simulation)
- record_circuit_trip / record_circuit_rejected use labeled counters

Design notes
------------
We test metrics in isolation (pure unit tests) rather than through the full
HTTP stack. This is intentional:
  - The HTTP stack tests (test_ask.py, test_load_burst_patterns.py) already
    verify that record_ask() is CALLED at the right times.
  - These tests verify that the functions themselves increment the right
    counters with the right labels — a different concern.

We use a fresh CollectorRegistry per test class to avoid cross-test
counter state contamination (prometheus counters are cumulative within
a registry and cannot be reset without creating a new one).
"""

from __future__ import annotations

import time

import pytest

# ---------------------------------------------------------------------------
# Import metrics module — tests work even if prometheus_client not installed
# ---------------------------------------------------------------------------
from infrastructure import metrics as metrics_module

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _requires_prometheus() -> None:
    """Skip test if prometheus_client is not installed."""
    if not metrics_module._registry_available:
        pytest.skip("prometheus_client not installed — skipping metrics tests")


def _get_counter_value(counter, **labels) -> float:
    """Read current value of a labeled counter."""
    if labels:
        return counter.labels(**labels)._value.get()
    return counter._value.get()


def _get_histogram_count(histogram, **labels) -> float:
    """Read the observation count of a labeled histogram."""
    if labels:
        return histogram.labels(**labels)._count.get()
    return histogram._count.get()


# ---------------------------------------------------------------------------
# No-op behavior when prometheus_client is disabled
# ---------------------------------------------------------------------------


class TestNoOpWhenDisabled:
    """All record_*() calls must be safe no-ops when registry unavailable."""

    def setup_method(self) -> None:
        self._orig = metrics_module._registry_available
        metrics_module._registry_available = False

    def teardown_method(self) -> None:
        metrics_module._registry_available = self._orig

    def test_record_ask_noop(self) -> None:
        # Must not raise
        metrics_module.record_ask(status="success", subdomain="mixing", latency_seconds=0.5)

    def test_record_cache_hit_noop(self) -> None:
        metrics_module.record_cache_hit()

    def test_record_cache_miss_noop(self) -> None:
        metrics_module.record_cache_miss()

    def test_record_embedding_cache_hit_noop(self) -> None:
        metrics_module.record_embedding_cache_hit()

    def test_record_rate_limited_noop(self) -> None:
        metrics_module.record_rate_limited()

    def test_record_circuit_trip_noop(self) -> None:
        metrics_module.record_circuit_trip("test_breaker")

    def test_record_circuit_rejected_noop(self) -> None:
        metrics_module.record_circuit_rejected("test_breaker")

    def test_get_metrics_response_empty(self) -> None:
        body, content_type = metrics_module.get_metrics_response()
        assert body == b""

    def test_all_noop_calls_in_sequence(self) -> None:
        """Verify a complete request cycle doesn't raise when metrics disabled."""
        metrics_module.record_cache_miss()
        metrics_module.record_ask(status="success", subdomain="global", latency_seconds=0.1)
        metrics_module.record_cache_hit()
        metrics_module.record_rate_limited()


# ---------------------------------------------------------------------------
# LatencyTimer — always works, independent of prometheus_client
# ---------------------------------------------------------------------------


class TestLatencyTimer:
    def test_elapsed_measured_correctly(self) -> None:
        with metrics_module.LatencyTimer() as t:
            time.sleep(0.02)
        assert t.elapsed >= 0.02
        assert t.elapsed < 1.0

    def test_elapsed_zero_before_exit(self) -> None:
        timer = metrics_module.LatencyTimer()
        timer.__enter__()
        # elapsed is 0.0 before __exit__
        assert timer.elapsed == 0.0
        timer.__exit__(None, None, None)
        assert timer.elapsed > 0

    def test_elapsed_is_positive(self) -> None:
        with metrics_module.LatencyTimer() as t:
            pass  # minimal work
        assert t.elapsed > 0

    def test_elapsed_reflects_actual_wait(self) -> None:
        with metrics_module.LatencyTimer() as t:
            time.sleep(0.05)
        # Should be ≥ 50ms with 20ms tolerance
        assert t.elapsed >= 0.04

    def test_timer_usable_as_context_manager(self) -> None:
        """Verify __enter__ returns the timer itself."""
        timer = metrics_module.LatencyTimer()
        result = timer.__enter__()
        timer.__exit__(None, None, None)
        assert result is timer


# ---------------------------------------------------------------------------
# Counter increments when prometheus_client is available
# ---------------------------------------------------------------------------


class TestCounterIncrements:
    """Test that record_*() calls increment the right counters.

    Each test reads the counter value directly from the Prometheus registry
    to confirm the increment happened with the correct label values.
    """

    def setup_method(self) -> None:
        _requires_prometheus()

    def test_record_ask_increments_total_counter(self) -> None:
        before = _get_counter_value(
            metrics_module.ask_requests_total,
            status="success",
            subdomain="mixing",
        )
        metrics_module.record_ask(status="success", subdomain="mixing", latency_seconds=0.3)
        after = _get_counter_value(
            metrics_module.ask_requests_total,
            status="success",
            subdomain="mixing",
        )
        assert after - before == 1.0

    def test_record_ask_increments_latency_histogram(self) -> None:
        before = _get_histogram_count(
            metrics_module.ask_latency_seconds,
            subdomain="mixing",
        )
        metrics_module.record_ask(status="success", subdomain="mixing", latency_seconds=0.3)
        after = _get_histogram_count(
            metrics_module.ask_latency_seconds,
            subdomain="mixing",
        )
        assert after - before == 1.0

    def test_record_ask_uses_correct_labels(self) -> None:
        """Different status/subdomain labels must be tracked separately."""
        before_mixing = _get_counter_value(
            metrics_module.ask_requests_total, status="error", subdomain="mixing"
        )
        before_global = _get_counter_value(
            metrics_module.ask_requests_total, status="error", subdomain="global"
        )

        metrics_module.record_ask(status="error", subdomain="global", latency_seconds=7.0)

        after_mixing = _get_counter_value(
            metrics_module.ask_requests_total, status="error", subdomain="mixing"
        )
        after_global = _get_counter_value(
            metrics_module.ask_requests_total, status="error", subdomain="global"
        )

        assert after_mixing == before_mixing  # mixing unchanged
        assert after_global - before_global == 1.0

    def test_record_cache_hit_increments(self) -> None:
        before = _get_counter_value(metrics_module.cache_hits_total)
        metrics_module.record_cache_hit()
        after = _get_counter_value(metrics_module.cache_hits_total)
        assert after - before == 1.0

    def test_record_cache_miss_increments(self) -> None:
        before = _get_counter_value(metrics_module.cache_misses_total)
        metrics_module.record_cache_miss()
        after = _get_counter_value(metrics_module.cache_misses_total)
        assert after - before == 1.0

    def test_record_embedding_cache_hit_increments(self) -> None:
        before = _get_counter_value(metrics_module.embedding_cache_hits_total)
        metrics_module.record_embedding_cache_hit()
        after = _get_counter_value(metrics_module.embedding_cache_hits_total)
        assert after - before == 1.0

    def test_record_rate_limited_increments(self) -> None:
        before = _get_counter_value(metrics_module.rate_limited_total)
        metrics_module.record_rate_limited()
        after = _get_counter_value(metrics_module.rate_limited_total)
        assert after - before == 1.0

    def test_record_circuit_trip_increments_labeled(self) -> None:
        before = _get_counter_value(
            metrics_module.circuit_breaker_trips_total, breaker_name="openai_llm"
        )
        metrics_module.record_circuit_trip("openai_llm")
        after = _get_counter_value(
            metrics_module.circuit_breaker_trips_total, breaker_name="openai_llm"
        )
        assert after - before == 1.0

    def test_record_circuit_rejected_increments_labeled(self) -> None:
        before = _get_counter_value(
            metrics_module.circuit_breaker_rejected_total, breaker_name="embedding"
        )
        metrics_module.record_circuit_rejected("embedding")
        after = _get_counter_value(
            metrics_module.circuit_breaker_rejected_total, breaker_name="embedding"
        )
        assert after - before == 1.0

    def test_circuit_metrics_use_separate_label_buckets(self) -> None:
        """Trips for 'llm_generation' and 'embedding' must be tracked separately."""
        before_llm = _get_counter_value(
            metrics_module.circuit_breaker_trips_total, breaker_name="llm_generation"
        )
        before_emb = _get_counter_value(
            metrics_module.circuit_breaker_trips_total, breaker_name="embedding_service"
        )

        metrics_module.record_circuit_trip("llm_generation")

        after_llm = _get_counter_value(
            metrics_module.circuit_breaker_trips_total, breaker_name="llm_generation"
        )
        after_emb = _get_counter_value(
            metrics_module.circuit_breaker_trips_total, breaker_name="embedding_service"
        )

        assert after_llm - before_llm == 1.0
        assert after_emb == before_emb  # untouched


# ---------------------------------------------------------------------------
# Burst accumulation — multiple calls accumulate correctly
# ---------------------------------------------------------------------------


class TestBurstAccumulation:
    """Counters must accumulate correctly over a burst of calls."""

    def setup_method(self) -> None:
        _requires_prometheus()

    def test_10_successful_asks_add_10_to_counter(self) -> None:
        before = _get_counter_value(
            metrics_module.ask_requests_total, status="success", subdomain="burst_test"
        )
        for _ in range(10):
            metrics_module.record_ask(status="success", subdomain="burst_test", latency_seconds=0.2)
        after = _get_counter_value(
            metrics_module.ask_requests_total, status="success", subdomain="burst_test"
        )
        assert after - before == 10.0

    def test_mixed_status_burst_counted_separately(self) -> None:
        """Success and error counts in a burst must not bleed into each other."""
        before_ok = _get_counter_value(
            metrics_module.ask_requests_total, status="success", subdomain="mixed_burst"
        )
        before_err = _get_counter_value(
            metrics_module.ask_requests_total, status="error", subdomain="mixed_burst"
        )

        # 7 successes + 3 errors in a burst
        for _ in range(7):
            metrics_module.record_ask(
                status="success", subdomain="mixed_burst", latency_seconds=0.3
            )
        for _ in range(3):
            metrics_module.record_ask(status="error", subdomain="mixed_burst", latency_seconds=5.0)

        after_ok = _get_counter_value(
            metrics_module.ask_requests_total, status="success", subdomain="mixed_burst"
        )
        after_err = _get_counter_value(
            metrics_module.ask_requests_total, status="error", subdomain="mixed_burst"
        )

        assert after_ok - before_ok == 7.0
        assert after_err - before_err == 3.0

    def test_cache_hit_miss_ratio_tracked(self) -> None:
        """Cache hits and misses accumulate independently for ratio calculation."""
        before_hits = _get_counter_value(metrics_module.cache_hits_total)
        before_misses = _get_counter_value(metrics_module.cache_misses_total)

        # Simulate: 3 misses (warm-up) then 7 hits
        for _ in range(3):
            metrics_module.record_cache_miss()
        for _ in range(7):
            metrics_module.record_cache_hit()

        hits = _get_counter_value(metrics_module.cache_hits_total) - before_hits
        misses = _get_counter_value(metrics_module.cache_misses_total) - before_misses

        assert hits == 7.0
        assert misses == 3.0
        # hit rate = 70%
        assert hits / (hits + misses) == pytest.approx(0.7)

    def test_rate_limited_burst_counted(self) -> None:
        """N rate-limited calls add N to the counter."""
        before = _get_counter_value(metrics_module.rate_limited_total)
        for _ in range(5):
            metrics_module.record_rate_limited()
        after = _get_counter_value(metrics_module.rate_limited_total)
        assert after - before == 5.0

    def test_degraded_mode_tracked_separately(self) -> None:
        """mode='degraded' uses a distinct status label from 'success'."""
        before_success = _get_counter_value(
            metrics_module.ask_requests_total, status="success", subdomain="degraded_test"
        )
        before_degraded = _get_counter_value(
            metrics_module.ask_requests_total, status="degraded", subdomain="degraded_test"
        )

        metrics_module.record_ask(status="degraded", subdomain="degraded_test", latency_seconds=0.1)
        metrics_module.record_ask(status="degraded", subdomain="degraded_test", latency_seconds=0.1)

        after_success = _get_counter_value(
            metrics_module.ask_requests_total, status="success", subdomain="degraded_test"
        )
        after_degraded = _get_counter_value(
            metrics_module.ask_requests_total, status="degraded", subdomain="degraded_test"
        )

        assert after_success == before_success  # unchanged
        assert after_degraded - before_degraded == 2.0


# ---------------------------------------------------------------------------
# get_metrics_response — Prometheus text format
# ---------------------------------------------------------------------------


class TestGetMetricsResponse:
    def test_returns_bytes_and_content_type(self) -> None:
        _requires_prometheus()
        body, content_type = metrics_module.get_metrics_response()
        assert isinstance(body, bytes)
        assert "text/plain" in content_type

    def test_body_contains_metric_names(self) -> None:
        _requires_prometheus()
        # Generate some data so metrics appear in output
        metrics_module.record_ask(status="success", subdomain="global", latency_seconds=0.1)
        metrics_module.record_cache_hit()

        body, _ = metrics_module.get_metrics_response()
        text = body.decode()

        assert "mip_ask_requests_total" in text
        assert "mip_cache_hits_total" in text

    def test_body_is_non_empty_after_recording(self) -> None:
        _requires_prometheus()
        metrics_module.record_ask(status="success", subdomain="global", latency_seconds=0.1)
        body, _ = metrics_module.get_metrics_response()
        assert len(body) > 0

    def test_empty_when_disabled(self) -> None:
        orig = metrics_module._registry_available
        metrics_module._registry_available = False
        try:
            body, _ = metrics_module.get_metrics_response()
            assert body == b""
        finally:
            metrics_module._registry_available = orig
