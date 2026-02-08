"""
SQLAlchemy session factory.

Reads ``DATABASE_URL`` from the environment and provides a
``SessionLocal`` sessionmaker plus a ``get_session`` context manager.
"""

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+psycopg://ia:ia@localhost:5432/ia")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session, closing it on exit."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
