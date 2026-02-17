"""
Tests for POST /ask endpoint.

Uses mocked dependencies (embedder, search, generator) to test the
full pipeline without real API calls or database queries.

Uses FastAPI dependency_overrides pattern for proper injection mocking.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.deps import get_embedding_provider, get_generation_provider
from api.main import app
from core.generation.base import GenerationResponse
from db.models import ChunkRecord


def _make_chunk_record(
    text: str = "Sample chunk about EQ.",
    source_name: str = "mixing.pdf",
    source_path: str = "/data/mixing.pdf",
    chunk_index: int = 0,
    page_number: int | None = 42,
) -> ChunkRecord:
    """Factory for test chunk records."""
    record = ChunkRecord(
        doc_id="test-doc",
        source_path=source_path,
        source_name=source_name,
        chunk_index=chunk_index,
        text=text,
        token_start=0,
        token_end=100,
        embedding=[0.1] * 1536,
        page_number=page_number,
    )
    return record


class TestAskEndpoint:
    """Test POST /ask with mocked dependencies."""

    @pytest.fixture(autouse=True)
    def _setup_and_teardown(self) -> None:
        """Clear dependency overrides before and after each test."""
        app.dependency_overrides.clear()
        yield
        app.dependency_overrides.clear()

    @patch("api.routes.ask.search_chunks")
    def test_successful_ask_with_citations(
        self,
        mock_search: MagicMock,
    ) -> None:
        # Setup mocks
        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1536]
        app.dependency_overrides[get_embedding_provider] = lambda: mock_embedder

        chunk1 = _make_chunk_record(text="Cut at 300Hz for clarity.", source_name="mixing.pdf")
        chunk2 = _make_chunk_record(
            text="Boost at 5kHz for presence.",
            source_name="mastering.pdf",
            chunk_index=1,
            page_number=12,
        )
        mock_search.return_value = [(chunk1, 0.92), (chunk2, 0.85)]

        mock_generator = MagicMock()
        mock_generator.generate.return_value = GenerationResponse(
            content="To EQ vocals, cut at 300Hz [1] and boost at 5kHz [2].",
            model="gpt-4o",
            usage_input_tokens=500,
            usage_output_tokens=50,
        )
        app.dependency_overrides[get_generation_provider] = lambda: mock_generator

        client = TestClient(app)

        # Execute
        response = client.post("/ask", json={"query": "How to EQ vocals?"})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "How to EQ vocals?"
        assert "300Hz" in data["answer"]
        assert "[1]" in data["answer"]
        assert "[2]" in data["answer"]
        assert len(data["sources"]) == 2
        assert data["sources"][0]["source_name"] == "mixing.pdf"
        assert data["sources"][0]["page_number"] == 42
        assert data["citations"] == [1, 2]
        assert data["reason"] is None
        assert data["warnings"] == []
        assert data["usage"]["input_tokens"] == 500
        assert data["usage"]["output_tokens"] == 50
        assert data["usage"]["model"] == "gpt-4o"

    @patch("api.routes.ask.search_chunks")
    def test_low_confidence_rejected(
        self,
        mock_search: MagicMock,
    ) -> None:
        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1536]
        app.dependency_overrides[get_embedding_provider] = lambda: mock_embedder

        # All chunks have low scores
        chunk = _make_chunk_record()
        mock_search.return_value = [(chunk, 0.45)]

        client = TestClient(app)
        response = client.post(
            "/ask",
            json={"query": "How to make dubstep wobbles?", "confidence_threshold": 0.7},
        )

        assert response.status_code == 422
        data = response.json()
        assert "insufficient_knowledge" in data["detail"]["reason"]

    @patch("api.routes.ask.search_chunks")
    def test_invalid_citations_warning(
        self,
        mock_search: MagicMock,
    ) -> None:
        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1536]
        app.dependency_overrides[get_embedding_provider] = lambda: mock_embedder

        chunk = _make_chunk_record()
        mock_search.return_value = [(chunk, 0.92)]

        # LLM cites [5] but only 1 source was provided
        mock_generator = MagicMock()
        mock_generator.generate.return_value = GenerationResponse(
            content="Use this technique [5].",
            model="gpt-4o",
            usage_input_tokens=100,
            usage_output_tokens=20,
        )
        app.dependency_overrides[get_generation_provider] = lambda: mock_generator

        client = TestClient(app)
        response = client.post("/ask", json={"query": "How to compress?"})

        assert response.status_code == 200
        data = response.json()
        assert data["reason"] == "invalid_citations"
        assert "invalid_citations" in data["warnings"]

    @patch("api.routes.ask.search_chunks")
    def test_embedding_failure_returns_500(
        self,
        mock_search: MagicMock,
    ) -> None:
        mock_embedder = MagicMock()
        mock_embedder.embed_texts.side_effect = Exception("API error")
        app.dependency_overrides[get_embedding_provider] = lambda: mock_embedder

        client = TestClient(app)
        response = client.post("/ask", json={"query": "test"})

        assert response.status_code == 500
        assert "embed" in response.json()["detail"].lower()

    @patch("api.routes.ask.search_chunks")
    def test_search_failure_returns_500(
        self,
        mock_search: MagicMock,
    ) -> None:
        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1536]
        app.dependency_overrides[get_embedding_provider] = lambda: mock_embedder

        mock_search.side_effect = Exception("DB error")

        client = TestClient(app)
        response = client.post("/ask", json={"query": "test"})

        assert response.status_code == 500
        assert "search" in response.json()["detail"].lower()

    @patch("api.routes.ask.search_chunks")
    def test_generation_failure_returns_500(
        self,
        mock_search: MagicMock,
    ) -> None:
        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1536]
        app.dependency_overrides[get_embedding_provider] = lambda: mock_embedder

        chunk = _make_chunk_record()
        mock_search.return_value = [(chunk, 0.92)]

        mock_generator = MagicMock()
        mock_generator.generate.side_effect = RuntimeError("LLM timeout")
        app.dependency_overrides[get_generation_provider] = lambda: mock_generator

        client = TestClient(app)
        response = client.post("/ask", json={"query": "test"})

        assert response.status_code == 500
        assert "generation" in response.json()["detail"].lower()

    def test_empty_query_rejected(self) -> None:
        client = TestClient(app)
        response = client.post("/ask", json={"query": ""})
        assert response.status_code == 422

    def test_whitespace_only_query_rejected(self) -> None:
        client = TestClient(app)
        response = client.post("/ask", json={"query": "   "})
        assert response.status_code == 422

    @patch("api.routes.ask.search_chunks")
    def test_custom_parameters(
        self,
        mock_search: MagicMock,
    ) -> None:
        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1536]
        app.dependency_overrides[get_embedding_provider] = lambda: mock_embedder

        chunk = _make_chunk_record()
        mock_search.return_value = [(chunk, 0.92)]

        mock_generator = MagicMock()
        mock_generator.generate.return_value = GenerationResponse(
            content="Answer [1].",
            model="gpt-4o",
            usage_input_tokens=100,
            usage_output_tokens=20,
        )
        app.dependency_overrides[get_generation_provider] = lambda: mock_generator

        client = TestClient(app)
        response = client.post(
            "/ask",
            json={
                "query": "test",
                "temperature": 0.3,
                "max_tokens": 500,
                "top_k": 10,
                "confidence_threshold": 0.6,
            },
        )

        assert response.status_code == 200

        # Verify generate was called with custom params
        call_args = mock_generator.generate.call_args[0][0]
        assert call_args.temperature == 0.3
        assert call_args.max_tokens == 500

    @patch("api.routes.ask.search_chunks")
    def test_no_results_returns_422(
        self,
        mock_search: MagicMock,
    ) -> None:
        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1536]
        app.dependency_overrides[get_embedding_provider] = lambda: mock_embedder

        mock_search.return_value = []  # No results

        client = TestClient(app)
        response = client.post("/ask", json={"query": "test"})

        assert response.status_code == 422
        data = response.json()
        assert "insufficient_knowledge" in data["detail"]["reason"]
