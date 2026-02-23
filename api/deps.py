"""
FastAPI dependency providers.

Reuses the canonical session factory from ``db.session`` to avoid
duplicate engine/sessionmaker definitions.  Provides singletons for
the embedding and generation providers so they are created once and
reused across requests.
"""

from collections.abc import Generator

from sqlalchemy.orm import Session

from core.generation.base import GenerationProvider
from db.session import SessionLocal
from infrastructure.cache import ResponseCache
from infrastructure.circuit_breaker import CircuitBreaker
from infrastructure.rate_limiter import RateLimiter
from ingestion.embeddings import OpenAIEmbeddingProvider
from ingestion.generation import create_generation_provider
from ingestion.memory_store import MemoryStore


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session for FastAPI dependency injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


_embedding_provider: OpenAIEmbeddingProvider | None = None


def get_embedding_provider() -> OpenAIEmbeddingProvider:
    """
    Return a cached ``OpenAIEmbeddingProvider`` singleton.

    The provider is created on first call and reused thereafter.
    This avoids re-reading env vars and re-creating the OpenAI client
    on every request.
    """
    global _embedding_provider  # noqa: PLW0603
    if _embedding_provider is None:
        _embedding_provider = OpenAIEmbeddingProvider()
    return _embedding_provider


_generation_provider: GenerationProvider | None = None


def get_generation_provider() -> GenerationProvider:
    """
    Return a cached generation provider singleton.

    Reads ``LLM_PROVIDER`` from the environment on first call to decide
    between OpenAI and Anthropic.  The provider is reused thereafter.
    """
    global _generation_provider  # noqa: PLW0603
    if _generation_provider is None:
        _generation_provider = create_generation_provider()
    return _generation_provider


_response_cache: ResponseCache | None = None


def get_response_cache() -> ResponseCache:
    """Return a cached ResponseCache singleton (Redis-backed).

    Falls back gracefully to a no-op cache if Redis is unavailable.
    """
    global _response_cache  # noqa: PLW0603
    if _response_cache is None:
        _response_cache = ResponseCache()
    return _response_cache


_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Return a cached RateLimiter singleton (Redis sliding-window).

    Falls back gracefully to allow-all if Redis is unavailable.
    """
    global _rate_limiter  # noqa: PLW0603
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(max_requests=30, window_seconds=60)
    return _rate_limiter


# ---------------------------------------------------------------------------
# Circuit breakers — one per external service
# ---------------------------------------------------------------------------

# LLM generation breaker: trips after 3 consecutive failures,
# resets after 30s. Used for both OpenAI and Anthropic generation calls.
_llm_breaker: CircuitBreaker | None = None

# Embedding breaker: trips after 3 consecutive failures.
# Separate from LLM because embeddings and generation use different
# API quotas and can fail independently.
_embedding_breaker: CircuitBreaker | None = None


def get_llm_breaker() -> CircuitBreaker:
    """Return the LLM generation circuit breaker singleton.

    Shared across all requests so failure counts accumulate correctly
    across the lifetime of the server process.
    """
    global _llm_breaker  # noqa: PLW0603
    if _llm_breaker is None:
        _llm_breaker = CircuitBreaker(
            name="llm_generation",
            failure_threshold=3,
            reset_timeout_seconds=30.0,
        )
    return _llm_breaker


def get_embedding_breaker() -> CircuitBreaker:
    """Return the embedding circuit breaker singleton."""
    global _embedding_breaker  # noqa: PLW0603
    if _embedding_breaker is None:
        _embedding_breaker = CircuitBreaker(
            name="embedding",
            failure_threshold=3,
            reset_timeout_seconds=30.0,
        )
    return _embedding_breaker


_memory_store: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    """Return a cached MemoryStore singleton (SQLite-backed, local-first).

    Created on first call. SQLite file created at data/memory.db if it
    does not exist. Thread-safe in WAL mode.
    """
    global _memory_store  # noqa: PLW0603
    if _memory_store is None:
        _memory_store = MemoryStore()
    return _memory_store
