"""
Tests for the semantic search endpoint.

Covers:
- db/search.py: search_chunks input validation
- api/schemas/search.py: Pydantic validation
- api/routes/search.py: POST /search endpoint integration

All tests are deterministic — no network calls, no real database.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.deps import get_db, get_embedding_provider
from api.main import app
from api.schemas.search import SearchRequest, SearchResponse, SearchResult
from db.search import search_chunks

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_EMBEDDING = [0.1] * 1536


class _FakeEmbeddingProvider:
    """Deterministic embedding provider for tests."""

    @property
    def embedding_dim(self) -> int:
        return 1536

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [FAKE_EMBEDDING for _ in texts]


@pytest.fixture()
def client():
    """FastAPI test client with mocked dependencies.

    Patches ``search_chunks`` to avoid pgvector operator calls (not
    supported by SQLite) and overrides the embedding provider with a
    deterministic fake.
    """

    def _override_db():
        yield MagicMock(spec=Session)

    def _override_embedder() -> _FakeEmbeddingProvider:
        return _FakeEmbeddingProvider()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_embedding_provider] = _override_embedder

    with (
        patch("api.routes.search.search_chunks", return_value=[]) as _mock,
        TestClient(app) as c,
    ):
        c._search_mock = _mock  # type: ignore[attr-defined]
        yield c

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


class TestSearchRequest:
    """Tests for SearchRequest Pydantic model."""

    def test_valid_request(self) -> None:
        req = SearchRequest(query="how to chunk text", top_k=10)
        assert req.query == "how to chunk text"
        assert req.top_k == 10

    def test_default_top_k(self) -> None:
        req = SearchRequest(query="test query")
        assert req.top_k == 5

    def test_empty_query_raises(self) -> None:
        with pytest.raises(ValueError, match="query must be a non-empty string"):
            SearchRequest(query="")

    def test_whitespace_only_query_raises(self) -> None:
        with pytest.raises(ValueError, match="query must be a non-empty string"):
            SearchRequest(query="   \n\t  ")

    def test_top_k_below_range_raises(self) -> None:
        with pytest.raises(ValueError):
            SearchRequest(query="test", top_k=0)

    def test_top_k_above_range_raises(self) -> None:
        with pytest.raises(ValueError):
            SearchRequest(query="test", top_k=101)

    def test_top_k_boundary_min(self) -> None:
        req = SearchRequest(query="test", top_k=1)
        assert req.top_k == 1

    def test_top_k_boundary_max(self) -> None:
        req = SearchRequest(query="test", top_k=100)
        assert req.top_k == 100


class TestSearchResult:
    """Tests for SearchResult Pydantic model."""

    def test_round_trip(self) -> None:
        result = SearchResult(
            score=0.95,
            text="some chunk text",
            source_name="doc.md",
            source_path="/data/doc.md",
            chunk_index=3,
            token_start=100,
            token_end=200,
        )
        assert result.score == 0.95
        assert result.text == "some chunk text"
        assert result.source_name == "doc.md"
        assert result.chunk_index == 3
        assert result.token_start == 100
        assert result.token_end == 200


class TestSearchResponse:
    """Tests for SearchResponse Pydantic model."""

    def test_full_response(self) -> None:
        response = SearchResponse(
            query="test",
            top_k=5,
            results=[
                SearchResult(
                    score=0.9,
                    text="text",
                    source_name="doc.md",
                    source_path="/doc.md",
                    chunk_index=0,
                    token_start=0,
                    token_end=100,
                )
            ],
        )
        assert response.query == "test"
        assert len(response.results) == 1

    def test_empty_results(self) -> None:
        response = SearchResponse(query="test", top_k=5, results=[])
        assert response.results == []


# ---------------------------------------------------------------------------
# db/search.py tests
# ---------------------------------------------------------------------------


class TestSearchChunks:
    """Tests for the search_chunks database function."""

    def test_invalid_top_k_raises(self) -> None:
        session = MagicMock(spec=Session)
        with pytest.raises(ValueError, match="top_k must be >= 1"):
            search_chunks(session, FAKE_EMBEDDING, top_k=0)

    def test_negative_top_k_raises(self) -> None:
        session = MagicMock(spec=Session)
        with pytest.raises(ValueError, match="top_k must be >= 1"):
            search_chunks(session, FAKE_EMBEDDING, top_k=-5)


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestSearchEndpoint:
    """Integration tests for POST /search."""

    def test_health_still_works(self, client: TestClient) -> None:
        """Adding the search router must not break existing routes."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_search_returns_200_with_empty_db(self, client: TestClient) -> None:
        """An empty database should return 200 with zero results."""
        response = client.post("/search", json={"query": "test query"})
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "test query"
        assert data["top_k"] == 5
        assert data["results"] == []

    def test_search_custom_top_k(self, client: TestClient) -> None:
        response = client.post("/search", json={"query": "test", "top_k": 10})
        assert response.status_code == 200
        assert response.json()["top_k"] == 10

    def test_search_empty_query_returns_422(self, client: TestClient) -> None:
        response = client.post("/search", json={"query": ""})
        assert response.status_code == 422

    def test_search_whitespace_query_returns_422(self, client: TestClient) -> None:
        response = client.post("/search", json={"query": "   "})
        assert response.status_code == 422

    def test_search_missing_query_returns_422(self, client: TestClient) -> None:
        response = client.post("/search", json={})
        assert response.status_code == 422

    def test_search_top_k_out_of_range_returns_422(self, client: TestClient) -> None:
        response = client.post("/search", json={"query": "test", "top_k": 0})
        assert response.status_code == 422

    def test_search_top_k_above_max_returns_422(self, client: TestClient) -> None:
        response = client.post("/search", json={"query": "test", "top_k": 101})
        assert response.status_code == 422

    def test_response_structure(self, client: TestClient) -> None:
        """Verify the response JSON has the exact expected shape."""
        response = client.post("/search", json={"query": "hello"})
        data = response.json()
        assert "query" in data
        assert "top_k" in data
        assert "results" in data
        assert isinstance(data["results"], list)
