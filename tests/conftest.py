"""
Shared fixtures for the test suite.

Centralizes reusable test infrastructure so individual test files
don't need to repeat override/mock boilerplate.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.deps import get_db, get_embedding_provider
from api.main import app

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FAKE_EMBEDDING: list[float] = [0.1] * 1536
"""Deterministic 1536-dim embedding vector for tests."""


# ---------------------------------------------------------------------------
# Fake embedding provider
# ---------------------------------------------------------------------------


class FakeEmbeddingProvider:
    """Deterministic embedding provider — no OpenAI calls."""

    @property
    def embedding_dim(self) -> int:
        return 1536

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [FAKE_EMBEDDING for _ in texts]

    @property
    def last_cache_hit(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# Mock record factory
# ---------------------------------------------------------------------------


def make_mock_record(**overrides: object) -> MagicMock:
    """Build a ``MagicMock`` that looks like a ``ChunkRecord``.

    Default attributes can be overridden via keyword arguments.
    """
    defaults: dict[str, object] = {
        "text": "sample chunk",
        "source_name": "doc.md",
        "source_path": "/data/doc.md",
        "chunk_index": 0,
        "token_start": 0,
        "token_end": 100,
    }
    defaults.update(overrides)
    rec = MagicMock()
    for k, v in defaults.items():
        setattr(rec, k, v)
    return rec


# ---------------------------------------------------------------------------
# FastAPI test client fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def api_client():
    """FastAPI ``TestClient`` with DB and embedder overridden.

    ``search_chunks`` is patched to return an empty list by default.
    The patch mock is accessible as ``client._search_mock``.
    """

    def _override_db():
        yield MagicMock(spec=Session)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_embedding_provider] = FakeEmbeddingProvider

    with (
        patch("api.routes.search.search_chunks", return_value=[]) as mock,
        TestClient(app) as c,
    ):
        c._search_mock = mock  # type: ignore[attr-defined]
        yield c

    app.dependency_overrides.clear()
