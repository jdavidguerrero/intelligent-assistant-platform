"""Tests for infrastructure/circuit_breaker.py.

Covers:
- State machine transitions: CLOSED → OPEN → HALF-OPEN → CLOSED
- CircuitOpenError raised and rejected_calls counter
- Successful recovery via HALF-OPEN probe
- Thread-safety (basic lock coverage)
- reset() forces CLOSED
- status() snapshot
- success_threshold > 1 requires multiple successes
"""

from __future__ import annotations

import threading
import time

import pytest

from infrastructure.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_breaker(**kwargs) -> CircuitBreaker:
    """Create a breaker with fast timeout for tests."""
    defaults = {
        "name": "test",
        "failure_threshold": 3,
        "reset_timeout_seconds": 0.05,  # 50ms — keeps tests fast
    }
    defaults.update(kwargs)
    return CircuitBreaker(**defaults)


def _trigger_failures(breaker: CircuitBreaker, n: int) -> None:
    """Force n failures through the breaker."""
    for _ in range(n):
        with pytest.raises(RuntimeError):
            breaker.call(_raise_runtime)


def _raise_runtime() -> None:
    raise RuntimeError("simulated failure")


def _succeed() -> str:
    return "ok"


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------


class TestInitialState:
    def test_starts_closed(self) -> None:
        b = _make_breaker()
        assert b.state == CircuitState.CLOSED

    def test_is_open_false_initially(self) -> None:
        b = _make_breaker()
        assert b.is_open is False

    def test_stats_zero_on_init(self) -> None:
        b = _make_breaker()
        s = b.stats
        assert s.total_calls == 0
        assert s.successful_calls == 0
        assert s.failed_calls == 0
        assert s.rejected_calls == 0


# ---------------------------------------------------------------------------
# CLOSED state — normal operation
# ---------------------------------------------------------------------------


class TestClosedState:
    def test_passes_through_on_success(self) -> None:
        b = _make_breaker()
        result = b.call(_succeed)
        assert result == "ok"

    def test_increments_total_and_success_counters(self) -> None:
        b = _make_breaker()
        b.call(_succeed)
        b.call(_succeed)
        assert b.stats.total_calls == 2
        assert b.stats.successful_calls == 2

    def test_failure_counted_but_below_threshold_stays_closed(self) -> None:
        b = _make_breaker(failure_threshold=3)
        # 2 failures, threshold is 3 → stays CLOSED
        for _ in range(2):
            with pytest.raises(RuntimeError):
                b.call(_raise_runtime)
        assert b.state == CircuitState.CLOSED

    def test_success_resets_failure_count(self) -> None:
        b = _make_breaker(failure_threshold=3)
        # 2 failures then 1 success → failure count resets
        with pytest.raises(RuntimeError):
            b.call(_raise_runtime)
        with pytest.raises(RuntimeError):
            b.call(_raise_runtime)
        b.call(_succeed)
        # Now 2 more failures shouldn't trip (count was reset)
        with pytest.raises(RuntimeError):
            b.call(_raise_runtime)
        with pytest.raises(RuntimeError):
            b.call(_raise_runtime)
        assert b.state == CircuitState.CLOSED

    def test_re_raises_exception(self) -> None:
        b = _make_breaker()
        with pytest.raises(ValueError, match="test error"):
            b.call(lambda: (_ for _ in ()).throw(ValueError("test error")))


# ---------------------------------------------------------------------------
# Transition to OPEN
# ---------------------------------------------------------------------------


class TestTransitionToOpen:
    def test_trips_after_threshold_failures(self) -> None:
        b = _make_breaker(failure_threshold=3)
        _trigger_failures(b, 3)
        assert b.state == CircuitState.OPEN

    def test_is_open_true_when_open(self) -> None:
        b = _make_breaker(failure_threshold=3)
        _trigger_failures(b, 3)
        assert b.is_open is True

    def test_circuit_open_error_on_next_call(self) -> None:
        b = _make_breaker(failure_threshold=3)
        _trigger_failures(b, 3)
        with pytest.raises(CircuitOpenError) as exc_info:
            b.call(_succeed)
        assert exc_info.value.name == "test"

    def test_rejected_calls_counter_increments(self) -> None:
        b = _make_breaker(failure_threshold=3)
        _trigger_failures(b, 3)
        for _ in range(5):
            with pytest.raises(CircuitOpenError):
                b.call(_succeed)
        assert b.stats.rejected_calls == 5

    def test_circuit_open_error_contains_reset_info(self) -> None:
        b = _make_breaker(failure_threshold=2, reset_timeout_seconds=30.0)
        _trigger_failures(b, 2)
        with pytest.raises(CircuitOpenError) as exc_info:
            b.call(_succeed)
        # reset_in_seconds should be positive (some time remains)
        assert exc_info.value.reset_in_seconds >= 0.0
        assert "OPEN" in str(exc_info.value)

    def test_only_tracked_exceptions_count_as_failures(self) -> None:
        b = _make_breaker(
            failure_threshold=3,
            exceptions=(ValueError,),  # only ValueError counts
        )
        # TypeError is NOT tracked — should not increment failure count
        for _ in range(3):
            with pytest.raises(TypeError):
                b.call(lambda: (_ for _ in ()).throw(TypeError("untracked")))
        # Should still be CLOSED (TypeError not tracked)
        assert b.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# OPEN → HALF-OPEN transition (probe after timeout)
# ---------------------------------------------------------------------------


class TestHalfOpen:
    def test_transitions_to_half_open_after_timeout(self) -> None:
        b = _make_breaker(failure_threshold=2, reset_timeout_seconds=0.05)
        _trigger_failures(b, 2)
        assert b.state == CircuitState.OPEN

        time.sleep(0.06)  # wait for reset timeout

        # Next call triggers HALF-OPEN transition
        result = b.call(_succeed)
        assert result == "ok"
        assert b.state == CircuitState.CLOSED

    def test_probe_failure_goes_back_to_open(self) -> None:
        b = _make_breaker(failure_threshold=2, reset_timeout_seconds=0.05)
        _trigger_failures(b, 2)
        assert b.state == CircuitState.OPEN

        time.sleep(0.06)

        # Probe fails → back to OPEN
        with pytest.raises(RuntimeError):
            b.call(_raise_runtime)
        assert b.state == CircuitState.OPEN

    def test_still_open_before_timeout(self) -> None:
        b = _make_breaker(failure_threshold=2, reset_timeout_seconds=60.0)
        _trigger_failures(b, 2)
        # No sleep — should still be OPEN
        with pytest.raises(CircuitOpenError):
            b.call(_succeed)
        assert b.state == CircuitState.OPEN

    def test_success_threshold_requires_multiple_successes(self) -> None:
        b = _make_breaker(
            failure_threshold=2,
            reset_timeout_seconds=0.05,
            success_threshold=2,  # need 2 successes to close
        )
        _trigger_failures(b, 2)
        time.sleep(0.06)

        # First success → still HALF-OPEN
        b.call(_succeed)
        assert b.state == CircuitState.HALF_OPEN

        # Second success → CLOSED
        b.call(_succeed)
        assert b.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# reset() — manual recovery
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_forces_closed_from_open(self) -> None:
        b = _make_breaker(failure_threshold=2)
        _trigger_failures(b, 2)
        assert b.state == CircuitState.OPEN

        b.reset()
        assert b.state == CircuitState.CLOSED

    def test_reset_clears_failure_count(self) -> None:
        b = _make_breaker(failure_threshold=3)
        # 2 failures, then reset
        with pytest.raises(RuntimeError):
            b.call(_raise_runtime)
        with pytest.raises(RuntimeError):
            b.call(_raise_runtime)
        b.reset()
        # After reset, need 3 new failures to trip
        with pytest.raises(RuntimeError):
            b.call(_raise_runtime)
        with pytest.raises(RuntimeError):
            b.call(_raise_runtime)
        assert b.state == CircuitState.CLOSED

    def test_call_succeeds_after_reset(self) -> None:
        b = _make_breaker(failure_threshold=2)
        _trigger_failures(b, 2)
        b.reset()
        assert b.call(_succeed) == "ok"


# ---------------------------------------------------------------------------
# status() snapshot
# ---------------------------------------------------------------------------


class TestStatus:
    def test_status_returns_dict(self) -> None:
        b = _make_breaker()
        s = b.status()
        assert s["name"] == "test"
        assert s["state"] == "closed"
        assert "failure_count" in s
        assert "stats" in s

    def test_status_updates_after_failures(self) -> None:
        b = _make_breaker(failure_threshold=3)
        with pytest.raises(RuntimeError):
            b.call(_raise_runtime)
        s = b.status()
        assert s["failure_count"] == 1
        assert s["stats"]["failed"] == 1

    def test_status_shows_open_state(self) -> None:
        b = _make_breaker(failure_threshold=2)
        _trigger_failures(b, 2)
        s = b.status()
        assert s["state"] == "open"
        assert s["last_failure_ago_seconds"] is not None
        assert s["last_failure_ago_seconds"] >= 0.0

    def test_status_shows_no_last_failure_when_clean(self) -> None:
        b = _make_breaker()
        s = b.status()
        assert s["last_failure_ago_seconds"] is None


# ---------------------------------------------------------------------------
# CircuitOpenError attributes
# ---------------------------------------------------------------------------


class TestCircuitOpenError:
    def test_has_name_attribute(self) -> None:
        err = CircuitOpenError("my_service", 15.5)
        assert err.name == "my_service"

    def test_has_reset_in_seconds_attribute(self) -> None:
        err = CircuitOpenError("my_service", 15.5)
        assert err.reset_in_seconds == 15.5

    def test_str_contains_service_name(self) -> None:
        err = CircuitOpenError("openai", 30.0)
        assert "openai" in str(err)

    def test_is_exception(self) -> None:
        assert issubclass(CircuitOpenError, Exception)


# ---------------------------------------------------------------------------
# Thread safety (basic)
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_successes_do_not_corrupt_count(self) -> None:
        b = _make_breaker(failure_threshold=100)
        results = []

        def worker() -> None:
            for _ in range(10):
                results.append(b.call(_succeed))

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 50
        assert b.stats.successful_calls == 50
        assert b.stats.total_calls == 50
