"""
SQLAlchemy session factory.

Reads connection parameters from environment variables and provides a
``SessionLocal`` sessionmaker plus a ``get_session`` context manager.

Environment variables
---------------------
``DATABASE_URL``
    Full SQLAlchemy connection URL.  Default:
    ``postgresql+psycopg://ia:ia@localhost:5432/ia``

``DB_POOL_SIZE``
    Number of persistent connections in the pool (default ``5``).

``DB_MAX_OVERFLOW``
    Extra connections allowed above ``pool_size`` under burst
    load (default ``10``).
"""

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://ia:ia@localhost:5432/ia",
)

_pool_size: int = int(os.getenv("DB_POOL_SIZE", "5"))
_max_overflow: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=_pool_size,
    max_overflow=_max_overflow,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_session() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session, closing it on exit."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
