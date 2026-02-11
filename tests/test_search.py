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
            SearchRequest(query="test", top_k=21)

    def test_top_k_boundary_min(self) -> None:
        req = SearchRequest(query="test", top_k=1)
        assert req.top_k == 1

    def test_top_k_boundary_max(self) -> None:
        req = SearchRequest(query="test", top_k=20)
        assert req.top_k == 20

    def test_default_min_score(self) -> None:
        req = SearchRequest(query="test")
        assert req.min_score == 0.3

    def test_custom_min_score(self) -> None:
        req = SearchRequest(query="test", min_score=0.5)
        assert req.min_score == 0.5

    def test_min_score_below_range_raises(self) -> None:
        with pytest.raises(ValueError):
            SearchRequest(query="test", min_score=-0.1)

    def test_min_score_above_range_raises(self) -> None:
        with pytest.raises(ValueError):
            SearchRequest(query="test", min_score=1.1)


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
        assert response.reason is None

    def test_reason_low_confidence(self) -> None:
        response = SearchResponse(query="test", top_k=5, results=[], reason="low_confidence")
        assert response.reason == "low_confidence"

    def test_reason_defaults_to_none(self) -> None:
        response = SearchResponse(query="test", top_k=5, results=[])
        assert response.reason is None


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
        response = client.post("/search", json={"query": "test", "top_k": 21})
        assert response.status_code == 422

    def test_response_structure(self, client: TestClient) -> None:
        """Verify the response JSON has the exact expected shape."""
        response = client.post("/search", json={"query": "hello"})
        data = response.json()
        assert "query" in data
        assert "top_k" in data
        assert "results" in data
        assert "reason" in data
        assert isinstance(data["results"], list)

    def test_reason_is_null_for_empty_db(self, client: TestClient) -> None:
        """Empty DB returns no results but reason should be None (not low_confidence)."""
        response = client.post("/search", json={"query": "hello"})
        assert response.status_code == 200
        assert response.json()["reason"] is None


# ---------------------------------------------------------------------------
# Low-confidence rejection tests
# ---------------------------------------------------------------------------


def _make_mock_record(**overrides: object) -> MagicMock:
    """Build a MagicMock that looks like a ChunkRecord."""
    defaults = {
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


class TestLowConfidenceRejection:
    """Tests for the min_score filtering behaviour."""

    def test_high_score_results_returned(self) -> None:
        """Results above min_score pass through."""
        record = _make_mock_record()
        mock_results = [(record, 0.85)]

        def _override_db():
            yield MagicMock(spec=Session)

        def _override_embedder() -> _FakeEmbeddingProvider:
            return _FakeEmbeddingProvider()

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_embedding_provider] = _override_embedder

        with (
            patch("api.routes.search.search_chunks", return_value=mock_results),
            TestClient(app) as c,
        ):
            resp = c.post("/search", json={"query": "good query", "min_score": 0.3})

        app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["score"] == 0.85
        assert data["reason"] is None

    def test_low_score_results_filtered_out(self) -> None:
        """All results below min_score are discarded → reason=low_confidence."""
        record = _make_mock_record()
        mock_results = [(record, 0.15)]

        def _override_db():
            yield MagicMock(spec=Session)

        def _override_embedder() -> _FakeEmbeddingProvider:
            return _FakeEmbeddingProvider()

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_embedding_provider] = _override_embedder

        with (
            patch("api.routes.search.search_chunks", return_value=mock_results),
            TestClient(app) as c,
        ):
            resp = c.post("/search", json={"query": "banana quantum bicycle"})

        app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["results"] == []
        assert data["reason"] == "low_confidence"

    def test_mixed_scores_partial_filtering(self) -> None:
        """Only results above threshold survive."""
        high = _make_mock_record(text="relevant chunk", chunk_index=0)
        low = _make_mock_record(text="noise chunk", chunk_index=1)
        mock_results = [(high, 0.75), (low, 0.10)]

        def _override_db():
            yield MagicMock(spec=Session)

        def _override_embedder() -> _FakeEmbeddingProvider:
            return _FakeEmbeddingProvider()

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_embedding_provider] = _override_embedder

        with (
            patch("api.routes.search.search_chunks", return_value=mock_results),
            TestClient(app) as c,
        ):
            resp = c.post("/search", json={"query": "test", "min_score": 0.3})

        app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["text"] == "relevant chunk"
        assert data["reason"] is None

    def test_custom_min_score_override(self) -> None:
        """Client can raise the threshold to be even stricter."""
        record = _make_mock_record()
        mock_results = [(record, 0.45)]

        def _override_db():
            yield MagicMock(spec=Session)

        def _override_embedder() -> _FakeEmbeddingProvider:
            return _FakeEmbeddingProvider()

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_embedding_provider] = _override_embedder

        with (
            patch("api.routes.search.search_chunks", return_value=mock_results),
            TestClient(app) as c,
        ):
            resp = c.post("/search", json={"query": "test", "min_score": 0.5})

        app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["results"] == []
        assert data["reason"] == "low_confidence"
