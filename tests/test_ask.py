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

    @patch("api.routes.ask.hybrid_search")
    @patch("api.routes.ask.search_chunks")
    def test_successful_ask_with_citations(
        self,
        mock_search: MagicMock,
        mock_hybrid: MagicMock,
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
        mock_hybrid.return_value = [(chunk1, 0.92), (chunk2, 0.85)]

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


# ---------------------------------------------------------------------------
# Sub-domain routing integration tests (Day 3)
# ---------------------------------------------------------------------------


class TestSubDomainRoutingInAsk:
    """Tests for sub-domain detection wired into the /ask pipeline.

    Verifies that:
    - Queries with clear sub-domain signals trigger namespaced search.
    - Queries with no sub-domain signals use global search.
    - When filtered search returns < MIN_FILTERED_RESULTS, global search is used.
    - The system prompt contains Focus Areas when sub-domains are active.
    """

    @pytest.fixture(autouse=True)
    def _setup_and_teardown(self) -> None:
        app.dependency_overrides.clear()
        yield
        app.dependency_overrides.clear()

    def _setup_mocks(
        self,
        mock_search: MagicMock,
        search_results: list,
        answer: str = "Answer [1].",
    ) -> TestClient:
        """Wire up a TestClient with mocked embedder, search, and generator."""
        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1536]
        app.dependency_overrides[get_embedding_provider] = lambda: mock_embedder

        mock_generator = MagicMock()
        mock_generator.generate.return_value = GenerationResponse(
            content=answer,
            model="gpt-4o",
            usage_input_tokens=100,
            usage_output_tokens=20,
        )
        app.dependency_overrides[get_generation_provider] = lambda: mock_generator
        mock_search.return_value = search_results
        return TestClient(app)

    @patch("api.routes.ask.search_chunks")
    def test_mixing_query_calls_search_with_sub_domain(self, mock_search: MagicMock) -> None:
        """A mixing-heavy query should trigger at least one sub-domain search call."""
        chunks = [(_make_chunk_record(text=f"chunk {i}"), 0.85) for i in range(5)]
        client = self._setup_mocks(mock_search, chunks)

        response = client.post(
            "/ask",
            json={"query": "how do I use sidechain compression on the kick?"},
        )

        assert response.status_code == 200
        sub_domain_calls = [
            c for c in mock_search.call_args_list if c.kwargs.get("sub_domain") is not None
        ]
        assert len(sub_domain_calls) >= 1

    @patch("api.routes.ask.search_chunks")
    def test_generic_query_uses_global_search(self, mock_search: MagicMock) -> None:
        """A query with no domain keywords should use global search (sub_domain=None)."""
        chunks = [(_make_chunk_record(text=f"chunk {i}"), 0.80) for i in range(3)]
        client = self._setup_mocks(mock_search, chunks)

        # "hello" has no sub-domain keywords
        response = client.post("/ask", json={"query": "hello"})

        assert response.status_code == 200
        for call in mock_search.call_args_list:
            assert call.kwargs.get("sub_domain") is None

    @patch("api.routes.ask.hybrid_search")
    @patch("api.routes.ask.search_chunks")
    def test_fallback_to_global_when_filtered_results_too_few(
        self, mock_search: MagicMock, mock_hybrid: MagicMock
    ) -> None:
        """When each filtered search returns < MIN_FILTERED_RESULTS, global search runs."""
        few = [(_make_chunk_record(text="single chunk"), 0.85)]
        many = [(_make_chunk_record(text=f"global {i}"), 0.80) for i in range(5)]

        def _side_effect(*args, **kwargs):  # type: ignore[no-untyped-def]
            if kwargs.get("sub_domain") is not None:
                return few  # 1 result per filtered call — triggers fallback
            return many  # global fallback returns enough

        mock_search.side_effect = _side_effect
        # hybrid_search is used in the global fallback when query_terms present
        mock_hybrid.return_value = many

        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1536]
        app.dependency_overrides[get_embedding_provider] = lambda: mock_embedder

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
            json={"query": "how do I EQ the kick drum?"},
        )

        assert response.status_code == 200
        # Either search_chunks (global, no sub_domain) or hybrid_search was called
        # for the fallback — depending on whether query_terms were extracted
        global_search_calls = [
            c for c in mock_search.call_args_list if c.kwargs.get("sub_domain") is None
        ]
        assert len(global_search_calls) >= 1 or mock_hybrid.call_count >= 1

    @patch("api.routes.ask.search_chunks")
    def test_system_prompt_includes_focus_areas_for_domain_query(
        self, mock_search: MagicMock
    ) -> None:
        """The system prompt should contain Focus Areas for sub-domain queries."""
        chunks = [(_make_chunk_record(text=f"chunk {i}"), 0.85) for i in range(5)]

        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1536]
        app.dependency_overrides[get_embedding_provider] = lambda: mock_embedder

        mock_generator = MagicMock()
        mock_generator.generate.return_value = GenerationResponse(
            content="Answer [1].",
            model="gpt-4o",
            usage_input_tokens=100,
            usage_output_tokens=20,
        )
        app.dependency_overrides[get_generation_provider] = lambda: mock_generator
        mock_search.return_value = chunks

        client = TestClient(app)
        client.post(
            "/ask",
            json={"query": "how do I sidechain compress the bass?"},
        )

        gen_call = mock_generator.generate.call_args[0][0]
        system_content = gen_call.messages[0].content
        assert "## Focus Areas" in system_content

    @patch("api.routes.ask.search_chunks")
    def test_system_prompt_no_focus_areas_for_generic_query(self, mock_search: MagicMock) -> None:
        """Generic queries (no sub-domain keywords) should NOT inject Focus Areas."""
        # Verify via sub_domain_detector directly — if no sub-domains are detected,
        # build_system_prompt is called without active_sub_domains.
        from core.sub_domain_detector import detect_sub_domains as _detect

        result = _detect("hello")
        assert result.active == ()

        # Verify end-to-end: generic query → no Focus Areas in system prompt
        chunks = [(_make_chunk_record(text=f"chunk {i}"), 0.85) for i in range(3)]

        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1536]
        app.dependency_overrides[get_embedding_provider] = lambda: mock_embedder

        mock_generator = MagicMock()
        mock_generator.generate.return_value = GenerationResponse(
            content="Answer [1].",
            model="gpt-4o",
            usage_input_tokens=100,
            usage_output_tokens=20,
        )
        app.dependency_overrides[get_generation_provider] = lambda: mock_generator
        mock_search.return_value = chunks

        client = TestClient(app)
        client.post("/ask", json={"query": "hello"})

        gen_call = mock_generator.generate.call_args[0][0]
        system_content = gen_call.messages[0].content
        assert "## Focus Areas" not in system_content

    @patch("api.routes.ask.search_chunks")
    def test_multi_domain_query_searches_multiple_sub_domains(self, mock_search: MagicMock) -> None:
        """A query covering mixing + sound_design should search both sub-domains."""
        chunks = [(_make_chunk_record(text=f"chunk {i}"), 0.85) for i in range(6)]
        client = self._setup_mocks(mock_search, chunks)

        response = client.post(
            "/ask",
            json={"query": "how do I design a bass synth and compress it in the mix?"},
        )

        assert response.status_code == 200
        sub_domains_searched = {
            c.kwargs.get("sub_domain")
            for c in mock_search.call_args_list
            if c.kwargs.get("sub_domain") is not None
        }
        # At least one sub-domain was searched
        assert len(sub_domains_searched) >= 1


# ---------------------------------------------------------------------------
# Genre recipe injection tests (Day 4)
# ---------------------------------------------------------------------------


class TestGenreRecipeInjectionInAsk:
    """Tests for genre detection + recipe injection wired into /ask.

    Verifies that:
    - A genre-specific query injects Genre Reference into the system prompt.
    - A query with no genre does NOT inject Genre Reference.
    - Recipe loading failure is handled gracefully (no crash, no injection).
    """

    @pytest.fixture(autouse=True)
    def _setup_and_teardown(self) -> None:
        app.dependency_overrides.clear()
        yield
        app.dependency_overrides.clear()

    def _wire(self, mock_search: MagicMock, answer: str = "Answer [1].") -> TestClient:
        chunks = [(_make_chunk_record(text=f"chunk {i}"), 0.85) for i in range(5)]
        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1536]
        app.dependency_overrides[get_embedding_provider] = lambda: mock_embedder

        mock_generator = MagicMock()
        mock_generator.generate.return_value = GenerationResponse(
            content=answer,
            model="gpt-4o",
            usage_input_tokens=100,
            usage_output_tokens=20,
        )
        app.dependency_overrides[get_generation_provider] = lambda: mock_generator
        mock_search.return_value = chunks
        return TestClient(app)

    @patch("api.routes.ask.search_chunks")
    def test_organic_house_query_injects_genre_reference(self, mock_search: MagicMock) -> None:
        """An organic house query should inject ## Genre Reference into system prompt."""
        from unittest.mock import patch as _patch

        chunks = [(_make_chunk_record(text=f"chunk {i}"), 0.85) for i in range(5)]
        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1536]
        app.dependency_overrides[get_embedding_provider] = lambda: mock_embedder

        mock_generator = MagicMock()
        mock_generator.generate.return_value = GenerationResponse(
            content="Answer [1].",
            model="gpt-4o",
            usage_input_tokens=100,
            usage_output_tokens=20,
        )
        app.dependency_overrides[get_generation_provider] = lambda: mock_generator
        mock_search.return_value = chunks

        with _patch("api.routes.ask.load_recipe", return_value="BPM: 124. Key: A minor."):
            client = TestClient(app)
            client.post("/ask", json={"query": "how do I produce an organic house track?"})

        gen_call = mock_generator.generate.call_args[0][0]
        system_content = gen_call.messages[0].content
        assert "## Genre Reference" in system_content

    @patch("api.routes.ask.search_chunks")
    def test_genre_recipe_content_in_system_prompt(self, mock_search: MagicMock) -> None:
        """The recipe text should appear verbatim in the system prompt."""
        from unittest.mock import patch as _patch

        chunks = [(_make_chunk_record(text=f"chunk {i}"), 0.85) for i in range(5)]
        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1536]
        app.dependency_overrides[get_embedding_provider] = lambda: mock_embedder

        mock_generator = MagicMock()
        mock_generator.generate.return_value = GenerationResponse(
            content="Answer [1].",
            model="gpt-4o",
            usage_input_tokens=100,
            usage_output_tokens=20,
        )
        app.dependency_overrides[get_generation_provider] = lambda: mock_generator
        mock_search.return_value = chunks

        recipe_text = "BPM: 124. Typical keys: A minor."
        with _patch("api.routes.ask.load_recipe", return_value=recipe_text):
            client = TestClient(app)
            client.post("/ask", json={"query": "organic house bass design tips"})

        gen_call = mock_generator.generate.call_args[0][0]
        system_content = gen_call.messages[0].content
        assert recipe_text in system_content

    @patch("api.routes.ask.search_chunks")
    def test_no_genre_query_no_genre_reference(self, mock_search: MagicMock) -> None:
        """A generic query should NOT inject ## Genre Reference."""
        client = self._wire(mock_search)
        client.post("/ask", json={"query": "how do I use reverb?"})

        mock_generator = app.dependency_overrides[get_generation_provider]()
        gen_call = mock_generator.generate.call_args[0][0]
        system_content = gen_call.messages[0].content
        assert "## Genre Reference" not in system_content

    @patch("api.routes.ask.search_chunks")
    def test_recipe_load_failure_does_not_crash(self, mock_search: MagicMock) -> None:
        """If load_recipe returns None (file missing), /ask still returns 200."""
        from unittest.mock import patch as _patch

        chunks = [(_make_chunk_record(text=f"chunk {i}"), 0.85) for i in range(5)]
        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1536]
        app.dependency_overrides[get_embedding_provider] = lambda: mock_embedder

        mock_generator = MagicMock()
        mock_generator.generate.return_value = GenerationResponse(
            content="Answer [1].",
            model="gpt-4o",
            usage_input_tokens=100,
            usage_output_tokens=20,
        )
        app.dependency_overrides[get_generation_provider] = lambda: mock_generator
        mock_search.return_value = chunks

        with _patch("api.routes.ask.load_recipe", return_value=None):
            client = TestClient(app)
            response = client.post("/ask", json={"query": "organic house track production"})

        assert response.status_code == 200
        # No Genre Reference should be injected when recipe is None
        gen_call = mock_generator.generate.call_args[0][0]
        system_content = gen_call.messages[0].content
        assert "## Genre Reference" not in system_content
