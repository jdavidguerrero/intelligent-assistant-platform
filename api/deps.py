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
from ingestion.embeddings import OpenAIEmbeddingProvider
from ingestion.generation import create_generation_provider


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
