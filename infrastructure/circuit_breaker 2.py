"""Circuit breaker for external API calls.

Prevents cascading failures when an external service (OpenAI, Anthropic,
pgvector) is degraded. The breaker has three states:

    CLOSED    — Normal operation. Requests pass through.
    OPEN      — Service is down. Requests fail immediately without calling
                the service. Waits ``reset_timeout_seconds`` before testing.
    HALF-OPEN — Testing recovery. One probe request is allowed through.
                If it succeeds → CLOSED. If it fails → back to OPEN.

State machine::

    CLOSED ──(N failures)──→ OPEN ──(timeout)──→ HALF-OPEN
      ↑                                               │
      └──────────────(success)───────────────────────┘
                              └──(failure)──→ OPEN

Why this matters for production sessions
-----------------------------------------
Without a circuit breaker, every request during an OpenAI outage waits
for 3 retries × exponential backoff = ~7 seconds before failing. With
10 concurrent queries during a 5-minute outage, that's 70 seconds of
blocked requests.

With the circuit breaker, after the first 3 failures the circuit opens
and subsequent requests fail in <1ms with a graceful degradation response.
The half-open probe fires every 30 seconds to detect recovery.

Usage::

    from infrastructure.circuit_breaker import CircuitBreaker, CircuitOpenError

    llm_breaker = CircuitBreaker(name="openai_llm", failure_threshold=3)

    try:
        result = llm_breaker.call(generator.generate, request)
    except CircuitOpenError:
        # Circuit is open — use degraded response
        return _build_degraded_response(chunks)
    except Exception as exc:
        # Real failure — breaker recorded it
        raise
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class CircuitState(Enum):
    """Circuit breaker state machine states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when a call is attempted while the circuit is OPEN.

    This is NOT a real service error — it means the breaker short-circuited
    the call to protect the system. Callers should handle this specifically
    to return a degraded response rather than propagating an error.

    Args:
        name: Circuit breaker name for context.
        reset_in_seconds: Approximate seconds until the circuit will probe again.
    """

    def __init__(self, name: str, reset_in_seconds: float) -> None:
        """Initialize with breaker name and time-to-reset."""
        self.name = name
        self.reset_in_seconds = reset_in_seconds
        super().__init__(
            f"Circuit '{name}' is OPEN — service unavailable. "
            f"Will probe again in ~{reset_in_seconds:.0f}s."
        )


@dataclass
class CircuitStats:
    """Runtime statistics for a circuit breaker instance."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0  # calls rejected because circuit was OPEN
    state_changes: list[tuple[str, float]] = field(default_factory=list)

    def record_state_change(self, new_state: CircuitState) -> None:
        """Record a state transition with timestamp."""
        self.state_changes.append((new_state.value, time.time()))


class CircuitBreaker:
    """Thread-safe circuit breaker for external API calls.

    Args:
        name: Human-readable name for logging and error messages.
        failure_threshold: Number of consecutive failures to trip the breaker
            (default: 3). Lower = more sensitive, higher = more tolerant.
        reset_timeout_seconds: How long to stay OPEN before probing again
            (default: 30s). Aligns with typical API recovery times.
        success_threshold: Successful calls in HALF-OPEN needed to close again
            (default: 1). Set higher for extra safety.
        exceptions: Exception types that count as failures. Defaults to all
            non-BaseException types.

    Example::

        breaker = CircuitBreaker(name="openai", failure_threshold=3)

        try:
            response = breaker.call(openai_client.generate, prompt)
        except CircuitOpenError as e:
            logger.warning("Circuit open: %s", e)
            return degraded_response
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        reset_timeout_seconds: float = 30.0,
        success_threshold: int = 1,
        exceptions: tuple[type[Exception], ...] = (Exception,),
    ) -> None:
        """Initialize the circuit breaker in CLOSED state."""
        self.name = name
        self._failure_threshold = failure_threshold
        self._reset_timeout = reset_timeout_seconds
        self._success_threshold = success_threshold
        self._tracked_exceptions = exceptions

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0.0
        self._lock = threading.Lock()
        self.stats = CircuitStats()

        logger.info(
            "CircuitBreaker '%s' initialized (threshold=%d, timeout=%.0fs)",
            name,
            failure_threshold,
            reset_timeout_seconds,
        )

    @property
    def state(self) -> CircuitState:
        """Current circuit state (thread-safe read)."""
        with self._lock:
            return self._state

    @property
    def is_open(self) -> bool:
        """True if circuit is OPEN (rejecting calls)."""
        return self.state == CircuitState.OPEN

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt a probe (OPEN → HALF-OPEN)."""
        return time.time() - self._last_failure_time >= self._reset_timeout

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state and log it. Must be called with lock held."""
        old_state = self._state
        self._state = new_state
        self.stats.record_state_change(new_state)
        logger.warning(
            "CircuitBreaker '%s': %s → %s",
            self.name,
            old_state.value.upper(),
            new_state.value.upper(),
        )

    def _on_success(self) -> None:
        """Record a successful call. Must be called with lock held."""
        self._failure_count = 0
        self.stats.successful_calls += 1

        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self._success_threshold:
                self._success_count = 0
                self._transition_to(CircuitState.CLOSED)
                logger.info("CircuitBreaker '%s': service recovered ✓", self.name)

    def _on_failure(self, exc: Exception) -> None:
        """Record a failed call. Must be called with lock held."""
        self._failure_count += 1
        self._last_failure_time = time.time()
        self.stats.failed_calls += 1

        if self._state == CircuitState.HALF_OPEN:
            # Probe failed — go back to OPEN
            self._success_count = 0
            self._transition_to(CircuitState.OPEN)
        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self._failure_threshold:
                self._transition_to(CircuitState.OPEN)
                logger.error(
                    "CircuitBreaker '%s': TRIPPED after %d failures. Last: %s",
                    self.name,
                    self._failure_count,
                    exc,
                )

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute a function through the circuit breaker.

        Args:
            func: The callable to protect (e.g. generator.generate).
            *args: Positional arguments forwarded to func.
            **kwargs: Keyword arguments forwarded to func.

        Returns:
            The return value of func.

        Raises:
            CircuitOpenError: If circuit is OPEN (call was rejected).
            Exception: Any exception raised by func (recorded as failure).
        """
        with self._lock:
            self.stats.total_calls += 1

            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    # Transition to HALF-OPEN for a probe
                    self._transition_to(CircuitState.HALF_OPEN)
                    self._success_count = 0
                else:
                    # Still open — reject immediately
                    self.stats.rejected_calls += 1
                    reset_in = self._reset_timeout - (time.time() - self._last_failure_time)
                    raise CircuitOpenError(self.name, max(0.0, reset_in))

        # Execute outside the lock to avoid blocking other threads
        try:
            result = func(*args, **kwargs)
            with self._lock:
                self._on_success()
            return result
        except self._tracked_exceptions as exc:
            with self._lock:
                self._on_failure(exc)
            raise

    def reset(self) -> None:
        """Manually force circuit to CLOSED state (e.g. after maintenance).

        Useful in tests and admin endpoints.
        """
        with self._lock:
            self._failure_count = 0
            self._success_count = 0
            self._transition_to(CircuitState.CLOSED)

    def status(self) -> dict[str, Any]:
        """Return a snapshot of the circuit breaker status.

        Returns:
            Dict with state, failure_count, stats, and config.
        """
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "failure_threshold": self._failure_threshold,
                "reset_timeout_seconds": self._reset_timeout,
                "last_failure_ago_seconds": (
                    round(time.time() - self._last_failure_time, 1)
                    if self._last_failure_time
                    else None
                ),
                "stats": {
                    "total": self.stats.total_calls,
                    "success": self.stats.successful_calls,
                    "failed": self.stats.failed_calls,
                    "rejected": self.stats.rejected_calls,
                },
            }
