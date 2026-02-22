"""
Tests for POST /ask/stream endpoint (Server-Sent Events).

Uses mocked dependencies to validate SSE event sequence, content,
and error handling without real API calls or database queries.

Pattern: same FastAPI dependency_overrides approach as test_ask.py.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.deps import (
    get_embedding_breaker,
    get_embedding_provider,
    get_generation_provider,
    get_rate_limiter,
)
from api.main import app
from db.models import ChunkRecord
from infrastructure.circuit_breaker import CircuitBreaker
from infrastructure.rate_limiter import RateLimiter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunk_record(
    text: str = "EQ tips for electronic music production.",
    source_name: str = "mixing.pdf",
    source_path: str = "/data/mixing.pdf",
    chunk_index: int = 0,
    page_number: int | None = 5,
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


def _parse_sse_events(raw_lines: Iterator[str]) -> list[dict]:
    """Parse SSE ``data:`` lines into a list of event dicts."""
    events: list[dict] = []
    for line in raw_lines:
        if isinstance(line, bytes):
            line = line.decode()
        line = line.rstrip("\r\n")
        if line.startswith("data: "):
            payload = line[6:]
            events.append(json.loads(payload))
    return events


def _make_allow_all_breaker() -> CircuitBreaker:
    """Return a circuit breaker that always calls through (no tripping)."""
    return CircuitBreaker(
        name="test-breaker",
        failure_threshold=999,
        reset_timeout_seconds=9999,
    )


def _make_allow_all_limiter() -> RateLimiter:
    """Return a rate limiter that always allows (no Redis needed)."""
    return RateLimiter(max_requests=999, window_seconds=60, redis_url=None)


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestAskStream:
    """Tests for POST /ask/stream (Server-Sent Events endpoint)."""

    @pytest.fixture(autouse=True)
    def _setup_and_teardown(self) -> None:
        """Clear dependency overrides and inject no-op infra before each test."""
        app.dependency_overrides.clear()
        app.dependency_overrides[get_rate_limiter] = lambda: _make_allow_all_limiter()
        app.dependency_overrides[get_embedding_breaker] = lambda: _make_allow_all_breaker()
        yield
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Happy-path: full event sequence
    # ------------------------------------------------------------------

    @patch("api.routes.ask.hybrid_search")
    @patch("api.routes.ask.search_chunks")
    def test_stream_returns_sse_content_type(
        self,
        mock_search: MagicMock,
        mock_hybrid: MagicMock,
    ) -> None:
        """Response must have Content-Type: text/event-stream."""
        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1536]
        mock_embedder.last_cache_hit = False
        app.dependency_overrides[get_embedding_provider] = lambda: mock_embedder

        chunk = _make_chunk_record(text="Sidechain the bass to the kick.")
        mock_search.return_value = [(chunk, 0.85)]
        mock_hybrid.return_value = [(chunk, 0.85)]

        mock_generator = MagicMock()
        mock_generator.generate_stream.return_value = iter(["Sidechain ", "compression ", "tips."])
        app.dependency_overrides[get_generation_provider] = lambda: mock_generator

        client = TestClient(app)
        response = client.post(
            "/ask/stream",
            json={
                "query": "How do I sidechain?",
                "confidence_threshold": 0.58,
                "use_tools": False,
            },
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

    @patch("api.routes.ask.hybrid_search")
    @patch("api.routes.ask.search_chunks")
    def test_stream_emits_correct_event_sequence(
        self,
        mock_search: MagicMock,
        mock_hybrid: MagicMock,
    ) -> None:
        """Events must appear in order: steps → sources → chunks → done."""
        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1536]
        mock_embedder.last_cache_hit = False
        app.dependency_overrides[get_embedding_provider] = lambda: mock_embedder

        chunk = _make_chunk_record(text="Use a compressor with fast attack for pumping.")
        mock_search.return_value = [(chunk, 0.90)]
        mock_hybrid.return_value = [(chunk, 0.90)]

        mock_generator = MagicMock()
        mock_generator.generate_stream.return_value = iter(["Fast ", "attack ", "compressor."])
        app.dependency_overrides[get_generation_provider] = lambda: mock_generator

        client = TestClient(app)
        with client.stream(
            "POST",
            "/ask/stream",
            json={
                "query": "Pumping sidechain effect?",
                "confidence_threshold": 0.58,
                "use_tools": False,
            },
        ) as resp:
            events = _parse_sse_events(resp.iter_lines())

        event_types = [e["type"] for e in events]

        # Steps must come first
        assert event_types[0] == "step"
        # Sources must appear before any chunk
        sources_idx = event_types.index("sources")
        first_chunk_idx = event_types.index("chunk")
        assert sources_idx < first_chunk_idx, "sources must precede first chunk"
        # done must be last
        assert event_types[-1] == "done"
        # At least one chunk
        assert "chunk" in event_types

    @patch("api.routes.ask.hybrid_search")
    @patch("api.routes.ask.search_chunks")
    def test_stream_chunks_form_complete_answer(
        self,
        mock_search: MagicMock,
        mock_hybrid: MagicMock,
    ) -> None:
        """Concatenated chunk content must equal the generated answer."""
        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1536]
        mock_embedder.last_cache_hit = False
        app.dependency_overrides[get_embedding_provider] = lambda: mock_embedder

        chunk = _make_chunk_record(text="Kick drum at 60Hz with fast attack.")
        mock_search.return_value = [(chunk, 0.88)]
        mock_hybrid.return_value = [(chunk, 0.88)]

        expected_answer = "Use 60Hz kick with short decay and fast attack."
        fragments = [
            "Use ",
            "60Hz ",
            "kick ",
            "with ",
            "short ",
            "decay ",
            "and ",
            "fast ",
            "attack.",
        ]
        mock_generator = MagicMock()
        mock_generator.generate_stream.return_value = iter(fragments)
        app.dependency_overrides[get_generation_provider] = lambda: mock_generator

        client = TestClient(app)
        with client.stream(
            "POST",
            "/ask/stream",
            json={
                "query": "How to design a kick drum?",
                "confidence_threshold": 0.58,
                "use_tools": False,
            },
        ) as resp:
            events = _parse_sse_events(resp.iter_lines())

        chunk_events = [e for e in events if e["type"] == "chunk"]
        assembled = "".join(e["content"] for e in chunk_events)
        assert assembled == expected_answer

    @patch("api.routes.ask.hybrid_search")
    @patch("api.routes.ask.search_chunks")
    def test_stream_sources_payload(
        self,
        mock_search: MagicMock,
        mock_hybrid: MagicMock,
    ) -> None:
        """sources event must include source_name and score for each retrieved chunk."""
        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1536]
        mock_embedder.last_cache_hit = False
        app.dependency_overrides[get_embedding_provider] = lambda: mock_embedder

        chunk = _make_chunk_record(
            text="Warm reverb on pads.",
            source_name="deep_house.pdf",
            page_number=7,
        )
        mock_search.return_value = [(chunk, 0.80)]
        mock_hybrid.return_value = [(chunk, 0.80)]

        mock_generator = MagicMock()
        mock_generator.generate_stream.return_value = iter(["Reverb tips."])
        app.dependency_overrides[get_generation_provider] = lambda: mock_generator

        client = TestClient(app)
        with client.stream(
            "POST",
            "/ask/stream",
            json={
                "query": "Reverb for deep house pads?",
                "confidence_threshold": 0.58,
                "use_tools": False,
            },
        ) as resp:
            events = _parse_sse_events(resp.iter_lines())

        sources_events = [e for e in events if e["type"] == "sources"]
        assert len(sources_events) == 1
        sources = sources_events[0]["sources"]
        assert len(sources) == 1
        assert sources[0]["source_name"] == "deep_house.pdf"
        assert sources[0]["page_number"] == 7
        assert isinstance(sources[0]["score"], float)

    @patch("api.routes.ask.hybrid_search")
    @patch("api.routes.ask.search_chunks")
    def test_stream_done_event_has_usage(
        self,
        mock_search: MagicMock,
        mock_hybrid: MagicMock,
    ) -> None:
        """done event must include usage dict with timing fields."""
        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1536]
        mock_embedder.last_cache_hit = False
        app.dependency_overrides[get_embedding_provider] = lambda: mock_embedder

        chunk = _make_chunk_record()
        mock_search.return_value = [(chunk, 0.75)]
        mock_hybrid.return_value = [(chunk, 0.75)]

        mock_generator = MagicMock()
        mock_generator.generate_stream.return_value = iter(["Answer text."])
        app.dependency_overrides[get_generation_provider] = lambda: mock_generator

        client = TestClient(app)
        with client.stream(
            "POST",
            "/ask/stream",
            json={
                "query": "Basic music theory?",
                "confidence_threshold": 0.58,
                "use_tools": False,
            },
        ) as resp:
            events = _parse_sse_events(resp.iter_lines())

        done_events = [e for e in events if e["type"] == "done"]
        assert len(done_events) == 1
        done = done_events[0]
        usage = done["usage"]
        assert "embedding_ms" in usage
        assert "search_ms" in usage
        assert "generation_ms" in usage
        assert "total_ms" in usage
        assert usage["total_ms"] > 0
        assert "citations" in done

    # ------------------------------------------------------------------
    # Error paths
    # ------------------------------------------------------------------

    @patch("api.routes.ask.search_chunks")
    def test_stream_low_confidence_emits_error_event(
        self,
        mock_search: MagicMock,
    ) -> None:
        """Low confidence should emit error event (not HTTP 422)."""
        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1536]
        mock_embedder.last_cache_hit = False
        app.dependency_overrides[get_embedding_provider] = lambda: mock_embedder

        chunk = _make_chunk_record()
        mock_search.return_value = [(chunk, 0.30)]  # below any reasonable threshold

        client = TestClient(app)
        with client.stream(
            "POST",
            "/ask/stream",
            json={
                "query": "Unknown topic question?",
                "confidence_threshold": 0.70,
                "use_tools": False,
            },
        ) as resp:
            assert resp.status_code == 200  # HTTP 200 — errors are in-band
            events = _parse_sse_events(resp.iter_lines())

        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        assert error_events[0]["code"] == "insufficient_knowledge"

    @patch("api.routes.ask.search_chunks")
    def test_stream_no_chunks_emits_error_event(
        self,
        mock_search: MagicMock,
    ) -> None:
        """Empty search results should emit error event."""
        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1536]
        mock_embedder.last_cache_hit = False
        app.dependency_overrides[get_embedding_provider] = lambda: mock_embedder

        mock_search.return_value = []  # no chunks found

        client = TestClient(app)
        with client.stream(
            "POST",
            "/ask/stream",
            json={
                "query": "What is the weather today?",
                "confidence_threshold": 0.58,
                "use_tools": False,
            },
        ) as resp:
            assert resp.status_code == 200
            events = _parse_sse_events(resp.iter_lines())

        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        assert error_events[0]["code"] == "insufficient_knowledge"

    def test_stream_rate_limit_returns_429(self) -> None:
        """Exhausted rate limit must return HTTP 429 before the stream starts."""
        exhausted_limiter = RateLimiter(max_requests=0, window_seconds=60, redis_url=None)
        app.dependency_overrides[get_rate_limiter] = lambda: exhausted_limiter

        client = TestClient(app)
        response = client.post(
            "/ask/stream",
            json={"query": "Some question?", "use_tools": False},
        )
        assert response.status_code == 429

    @patch("api.routes.ask.hybrid_search")
    @patch("api.routes.ask.search_chunks")
    def test_stream_generation_failure_emits_error_event(
        self,
        mock_search: MagicMock,
        mock_hybrid: MagicMock,
    ) -> None:
        """If generator.generate_stream raises mid-stream, error event is emitted."""

        def _failing_stream(_req):  # noqa: ANN001
            yield "First fragment"
            raise RuntimeError("LLM exploded")

        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1536]
        mock_embedder.last_cache_hit = False
        app.dependency_overrides[get_embedding_provider] = lambda: mock_embedder

        chunk = _make_chunk_record()
        mock_search.return_value = [(chunk, 0.80)]
        mock_hybrid.return_value = [(chunk, 0.80)]

        mock_generator = MagicMock()
        mock_generator.generate_stream.side_effect = _failing_stream
        app.dependency_overrides[get_generation_provider] = lambda: mock_generator

        client = TestClient(app)
        with client.stream(
            "POST",
            "/ask/stream",
            json={
                "query": "Explain compression ratios?",
                "confidence_threshold": 0.58,
                "use_tools": False,
            },
        ) as resp:
            events = _parse_sse_events(resp.iter_lines())

        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        assert error_events[0]["code"] == "generation_failed"
        # At least one chunk was yielded before the failure
        chunk_events = [e for e in events if e["type"] == "chunk"]
        assert len(chunk_events) >= 1
