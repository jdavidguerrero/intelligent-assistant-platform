"""Infrastructure layer — resilience patterns for the Musical Intelligence Platform.

Modules:
    cache       Redis-backed response cache with TTL and invalidation.
    retry       Exponential backoff retry decorator.
    rate_limiter  Per-session sliding-window rate limiter.
    circuit_breaker  Circuit breaker for external API calls.
    metrics     Prometheus metrics registry.
"""
