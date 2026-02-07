"""
FastAPI dependency providers.

Reuses the canonical session factory from ``db.session`` to avoid
duplicate engine/sessionmaker definitions.
"""

from collections.abc import Generator

from sqlalchemy.orm import Session

from db.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session for FastAPI dependency injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
