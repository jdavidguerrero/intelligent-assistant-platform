"""Exponential backoff retry decorator for external API calls.

Designed for production sessions where a transient LLM timeout must not
surface as a 500 error. The decorator wraps any callable and retries on
the specified exceptions with jittered exponential backoff.

Usage::

    from infrastructure.retry import with_retry

    @with_retry(max_attempts=3, base_seconds=1.0, exceptions=(openai.APIError,))
    def call_llm(prompt: str) -> str:
        return client.generate(prompt)
"""

from __future__ import annotations

import functools
import logging
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# Default exceptions that trigger a retry (transient failures)
_DEFAULT_RETRYABLE: tuple[type[Exception], ...] = (
    OSError,
    TimeoutError,
    ConnectionError,
)


def with_retry(
    *,
    max_attempts: int = 3,
    base_seconds: float = 1.0,
    max_seconds: float = 30.0,
    jitter: bool = True,
    exceptions: tuple[type[Exception], ...] = _DEFAULT_RETRYABLE,
) -> Callable[[F], F]:
    """Decorator factory for exponential backoff retry.

    Args:
        max_attempts: Total attempts including the first try (default: 3).
        base_seconds: Base wait time in seconds (default: 1.0).
        max_seconds: Maximum wait time cap in seconds (default: 30.0).
        jitter: Add random jitter ±25% to avoid thundering herd (default: True).
        exceptions: Tuple of exception types that trigger a retry.

    Returns:
        Decorator that wraps the function with retry logic.

    Example::

        @with_retry(max_attempts=4, base_seconds=2.0, exceptions=(APIError,))
        def embed(text: str) -> list[float]:
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        break
                    wait = min(base_seconds * (2 ** (attempt - 1)), max_seconds)
                    if jitter:
                        wait *= 1 + random.uniform(-0.25, 0.25)  # noqa: S311
                    logger.warning(
                        "retry: %s attempt %d/%d failed (%s) — retrying in %.2fs",
                        func.__name__,
                        attempt,
                        max_attempts,
                        exc,
                        wait,
                    )
                    time.sleep(wait)
            raise RuntimeError(
                f"{func.__name__} failed after {max_attempts} attempts"
            ) from last_exc

        return wrapper  # type: ignore[return-value]

    return decorator
