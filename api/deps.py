"""
FastAPI dependency providers.

Reuses the canonical session factory from ``db.session`` to avoid
duplicate engine/sessionmaker definitions.
"""

from collections.abc import Generator

from sqlalchemy.orm import Session

from db.session import SessionLocal
from ingestion.embeddings import OpenAIEmbeddingProvider


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
