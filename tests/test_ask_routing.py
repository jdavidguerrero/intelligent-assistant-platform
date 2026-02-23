"""Tests for POST /ask with USE_ROUTING=true (multi-model task routing).

Verifies that when the USE_ROUTING env var is set:
- The task_router dependency is injected (non-None)
- The response UsageMetadata includes tier and cost_usd fields
- Factual queries report tier="fast" (gpt-4o-mini used)
- Creative queries report tier="standard" (gpt-4o used)
- Realtime queries report tier="local" (claude-haiku used)
- Fallback is recorded correctly when primary tier fails
- When USE_ROUTING is unset/false, tier="" and cost_usd=0.0 (backward-compat)

All tests mock the router and generation providers to avoid real API calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.deps import (
    get_generation_provider,
    get_memory_store,
    get_rate_limiter,
    get_response_cache,
    get_task_router_optional,
)
from api.main import app
from core.generation.base import GenerationResponse
from db.models import ChunkRecord
from infrastructure.cache import ResponseCache
from infrastructure.rate_limiter import RateLimiter
from ingestion.router import RoutingDecision, TaskRouter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunk_record(
    text: str = "Sidechain compression is a technique...",
    source_name: str = "mixing.pdf",
    source_path: str = "/data/mixing.pdf",
    chunk_index: int = 0,
    page_number: int | None = 12,
) -> ChunkRecord:
    """Factory for test ChunkRecord objects."""
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


def _gen_response(
    content: str = "Sidechain compression is [1].",
    model: str = "gpt-4o-mini",
    input_tokens: int = 200,
    output_tokens: int = 80,
) -> GenerationResponse:
    """Build a GenerationResponse for mock use."""
    return GenerationResponse(
        content=content,
        model=model,
        usage_input_tokens=input_tokens,
        usage_output_tokens=output_tokens,
    )


def _routing_decision(
    tier_used: str = "fast",
    task_type: str = "factual",  # type: ignore[assignment]
    confidence: float = 0.5,
    fallback: bool = False,
    attempts: int = 1,
) -> RoutingDecision:
    """Build a RoutingDecision for mock use."""
    return RoutingDecision(
        tier_used=tier_used,
        task_type=task_type,  # type: ignore[arg-type]
        confidence=confidence,
        fallback=fallback,
        attempts=attempts,
    )


def _make_task_router(
    tier: str = "fast",
    model: str = "gpt-4o-mini",
    fallback: bool = False,
    task_type: str = "factual",
    input_tokens: int = 200,
    output_tokens: int = 80,
) -> MagicMock:
    """Create a mock TaskRouter that returns predictable (response, decision) pairs."""
    mock_router = MagicMock(spec=TaskRouter)
    resp = _gen_response(model=model, input_tokens=input_tokens, output_tokens=output_tokens)
    decision = _routing_decision(tier_used=tier, task_type=task_type, fallback=fallback)
    mock_router.generate_with_decision.return_value = (resp, decision)
    mock_router.generate.return_value = resp
    return mock_router


# ---------------------------------------------------------------------------
# Base fixture
# ---------------------------------------------------------------------------


class TestAskWithRouting:
    """POST /ask tests with USE_ROUTING=true."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        """Inject no-op infra + clear overrides before/after each test."""
        app.dependency_overrides.clear()

        # No-op ResponseCache
        noop_cache = ResponseCache.__new__(ResponseCache)
        noop_cache._client = None
        noop_cache._ttl = 86400
        app.dependency_overrides[get_response_cache] = lambda: noop_cache

        # Allow-all RateLimiter
        noop_limiter = RateLimiter.__new__(RateLimiter)
        noop_limiter._client = None
        noop_limiter._max = 30
        noop_limiter._window = 60
        app.dependency_overrides[get_rate_limiter] = lambda: noop_limiter

        # No-op MemoryStore
        noop_memory = MagicMock()
        noop_memory.search_relevant.return_value = []
        noop_memory.create_entry.return_value = MagicMock()
        noop_memory.save.return_value = None
        app.dependency_overrides[get_memory_store] = lambda: noop_memory

        yield
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Tier recorded in UsageMetadata
    # ------------------------------------------------------------------

    @patch.dict("os.environ", {"USE_ROUTING": "true"})
    @patch("api.routes.ask.hybrid_search")
    @patch("api.routes.ask.search_chunks")
    def test_factual_query_records_fast_tier(
        self,
        mock_search_chunks,
        mock_hybrid_search,
    ) -> None:
        """Factual queries → tier='fast' and cost_usd > 0 in UsageMetadata."""
        chunk = _make_chunk_record()
        mock_search_chunks.return_value = [(chunk, 0.85)]
        mock_hybrid_search.return_value = [(chunk, 0.85)]

        mock_router = _make_task_router(
            tier="fast",
            model="gpt-4o-mini",
            task_type="factual",
            input_tokens=200,
            output_tokens=80,
        )
        # Also override the fallback generator (not used when router active)
        app.dependency_overrides[get_task_router_optional] = lambda: mock_router

        mock_generator = MagicMock()
        mock_generator.generate.return_value = _gen_response()
        app.dependency_overrides[get_generation_provider] = lambda: mock_generator

        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/ask",
            json={
                "query": "What is sidechain compression?",
                "use_tools": False,
                "confidence_threshold": 0.5,
            },
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["usage"]["tier"] == "fast"
        # cost_usd > 0 because gpt-4o-mini has a non-zero cost and tokens > 0
        assert data["usage"]["cost_usd"] > 0.0

    @patch.dict("os.environ", {"USE_ROUTING": "true"})
    @patch("api.routes.ask.hybrid_search")
    @patch("api.routes.ask.search_chunks")
    def test_creative_query_records_standard_tier(
        self,
        mock_search_chunks,
        mock_hybrid_search,
    ) -> None:
        """Creative queries → tier='standard' and cost_usd > 0 in UsageMetadata."""
        chunk = _make_chunk_record()
        mock_search_chunks.return_value = [(chunk, 0.85)]
        mock_hybrid_search.return_value = [(chunk, 0.85)]

        mock_router = _make_task_router(
            tier="standard",
            model="gpt-4o",
            task_type="creative",
            input_tokens=300,
            output_tokens=150,
        )
        app.dependency_overrides[get_task_router_optional] = lambda: mock_router

        mock_generator = MagicMock()
        app.dependency_overrides[get_generation_provider] = lambda: mock_generator

        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/ask",
            json={
                "query": "Analyze my practice sessions and suggest a 2-week plan",
                "use_tools": False,
                "confidence_threshold": 0.5,
            },
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["usage"]["tier"] == "standard"
        assert data["usage"]["cost_usd"] > 0.0

    @patch.dict("os.environ", {"USE_ROUTING": "true"})
    @patch("api.routes.ask.hybrid_search")
    @patch("api.routes.ask.search_chunks")
    def test_realtime_query_records_local_tier(
        self,
        mock_search_chunks,
        mock_hybrid_search,
    ) -> None:
        """Realtime queries → tier='local' and cost_usd > 0 in UsageMetadata."""
        chunk = _make_chunk_record()
        mock_search_chunks.return_value = [(chunk, 0.85)]
        mock_hybrid_search.return_value = [(chunk, 0.85)]

        mock_router = _make_task_router(
            tier="local",
            model="claude-haiku-4-20250514",
            task_type="realtime",
            input_tokens=150,
            output_tokens=60,
        )
        app.dependency_overrides[get_task_router_optional] = lambda: mock_router

        mock_generator = MagicMock()
        app.dependency_overrides[get_generation_provider] = lambda: mock_generator

        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/ask",
            json={
                "query": "Detect the BPM of the track playing right now",
                "use_tools": False,
                "confidence_threshold": 0.5,
            },
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["usage"]["tier"] == "local"
        assert data["usage"]["cost_usd"] > 0.0

    # ------------------------------------------------------------------
    # Backward compatibility — routing disabled
    # ------------------------------------------------------------------

    @patch.dict("os.environ", {"USE_ROUTING": "false"})
    @patch("api.routes.ask.hybrid_search")
    @patch("api.routes.ask.search_chunks")
    def test_no_routing_tier_is_empty_string(
        self,
        mock_search_chunks,
        mock_hybrid_search,
    ) -> None:
        """When USE_ROUTING=false, tier='' and cost_usd=0.0 (backward-compat)."""
        chunk = _make_chunk_record()
        mock_search_chunks.return_value = [(chunk, 0.85)]
        mock_hybrid_search.return_value = [(chunk, 0.85)]

        mock_generator = MagicMock()
        mock_generator.generate.return_value = _gen_response(
            content="Sidechain compression is [1].", model="gpt-4o"
        )
        app.dependency_overrides[get_generation_provider] = lambda: mock_generator
        # task_router_optional returns None when USE_ROUTING != "true"
        app.dependency_overrides[get_task_router_optional] = lambda: None

        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/ask",
            json={
                "query": "What is sidechain compression?",
                "use_tools": False,
                "confidence_threshold": 0.5,
            },
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["usage"]["tier"] == ""
        assert data["usage"]["cost_usd"] == 0.0

    # ------------------------------------------------------------------
    # Fallback recorded in tier
    # ------------------------------------------------------------------

    @patch.dict("os.environ", {"USE_ROUTING": "true"})
    @patch("api.routes.ask.hybrid_search")
    @patch("api.routes.ask.search_chunks")
    def test_fallback_tier_still_recorded(
        self,
        mock_search_chunks,
        mock_hybrid_search,
    ) -> None:
        """When the router uses a fallback tier, that tier is recorded correctly."""
        chunk = _make_chunk_record()
        mock_search_chunks.return_value = [(chunk, 0.85)]
        mock_hybrid_search.return_value = [(chunk, 0.85)]

        # Router fell back from "fast" to "local"
        mock_router = _make_task_router(
            tier="local",
            model="claude-haiku-4-20250514",
            task_type="factual",
            fallback=True,
            input_tokens=150,
            output_tokens=60,
        )
        app.dependency_overrides[get_task_router_optional] = lambda: mock_router
        app.dependency_overrides[get_generation_provider] = lambda: MagicMock()

        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/ask",
            json={
                "query": "What is reverb?",
                "use_tools": False,
                "confidence_threshold": 0.5,
            },
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["usage"]["tier"] == "local"
        assert data["usage"]["cost_usd"] > 0.0

    # ------------------------------------------------------------------
    # Schema — cost_usd and tier fields always present in response
    # ------------------------------------------------------------------

    @patch.dict("os.environ", {"USE_ROUTING": "false"})
    @patch("api.routes.ask.hybrid_search")
    @patch("api.routes.ask.search_chunks")
    def test_cost_usd_and_tier_always_in_response_schema(
        self,
        mock_search_chunks,
        mock_hybrid_search,
    ) -> None:
        """cost_usd and tier are always present in UsageMetadata, even without routing."""
        chunk = _make_chunk_record()
        mock_search_chunks.return_value = [(chunk, 0.85)]
        mock_hybrid_search.return_value = [(chunk, 0.85)]

        mock_generator = MagicMock()
        mock_generator.generate.return_value = _gen_response(
            content="EQ stands for equalizer. [1]", model="gpt-4o"
        )
        app.dependency_overrides[get_generation_provider] = lambda: mock_generator
        app.dependency_overrides[get_task_router_optional] = lambda: None

        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/ask",
            json={
                "query": "What does EQ stand for?",
                "use_tools": False,
                "confidence_threshold": 0.5,
            },
        )

        assert resp.status_code == 200, resp.text
        usage = resp.json()["usage"]
        assert "cost_usd" in usage
        assert "tier" in usage
