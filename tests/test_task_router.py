"""Tests for ingestion/router.py — TaskRouter with fallback chain.

Tests cover:
- Correct tier selection per task type (factual→fast, creative→standard, realtime→local)
- Tier temperature applied to GenerationRequest
- Fallback chain: primary tier fails → next tier used, fallback=True
- All tiers fail → RuntimeError raised
- RoutingDecision fields: tier_used, fallback, attempts, confidence
- generate() protocol method extracts query from last user message
- generate_with_decision() returns (response, decision) tuple
- generate_stream() delegates to selected tier with fallback
- _extract_query_from_request() strips build_user_prompt() wrapper
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.generation.base import GenerationProvider, GenerationRequest, GenerationResponse, Message
from ingestion.router import RoutingDecision, TaskRouter, _extract_query_from_request

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_response(content: str = "answer", model: str = "gpt-4o-mini") -> GenerationResponse:
    """Build a GenerationResponse for mock use."""
    return GenerationResponse(
        content=content,
        model=model,
        usage_input_tokens=100,
        usage_output_tokens=50,
    )


def _make_provider(
    content: str = "answer",
    model: str = "gpt-4o-mini",
    fail: bool = False,
) -> MagicMock:
    """Create a mock GenerationProvider."""
    provider = MagicMock(spec=GenerationProvider)
    if fail:
        provider.generate.side_effect = RuntimeError("provider unavailable")
        provider.generate_stream.side_effect = RuntimeError("provider unavailable")
    else:
        provider.generate.return_value = _make_response(content, model)
        provider.generate_stream.return_value = iter([content])
    return provider


@pytest.fixture()
def mock_fast() -> MagicMock:
    return _make_provider(content="factual answer", model="gpt-4o-mini")


@pytest.fixture()
def mock_standard() -> MagicMock:
    return _make_provider(content="creative answer", model="gpt-4o")


@pytest.fixture()
def mock_local() -> MagicMock:
    return _make_provider(content="realtime answer", model="claude-haiku-4-20250514")


@pytest.fixture()
def router(mock_fast, mock_standard, mock_local) -> TaskRouter:
    return TaskRouter(fast=mock_fast, standard=mock_standard, local=mock_local)


def _request(query: str = "test query") -> GenerationRequest:
    """Build a minimal GenerationRequest with one user message."""
    return GenerationRequest(
        messages=(Message(role="user", content=query),),
        temperature=0.7,
        max_tokens=2048,
    )


def _wrapped_request(query: str) -> GenerationRequest:
    """Simulate the build_user_prompt() wrapper that ask.py adds."""
    wrapped = f"## Context\nSome context here.\n\n## Question\n{query}"
    return GenerationRequest(
        messages=(Message(role="user", content=wrapped),),
        temperature=0.7,
        max_tokens=2048,
    )


# ---------------------------------------------------------------------------
# Tier selection
# ---------------------------------------------------------------------------


class TestTierSelection:
    def test_factual_query_uses_fast_tier(self, router: TaskRouter, mock_fast: MagicMock) -> None:
        """Factual queries route to the fast (gpt-4o-mini) tier."""
        response, decision = router.route("What is sidechain compression?", _request())
        mock_fast.generate.assert_called_once()
        assert decision.tier_used == "fast"
        assert decision.task_type == "factual"
        assert decision.fallback is False

    def test_creative_query_uses_standard_tier(
        self, router: TaskRouter, mock_standard: MagicMock
    ) -> None:
        """Creative queries route to the standard (gpt-4o) tier."""
        response, decision = router.route(
            "Analyze my practice sessions and suggest a 2-week plan", _request()
        )
        mock_standard.generate.assert_called_once()
        assert decision.tier_used == "standard"
        assert decision.task_type == "creative"
        assert decision.fallback is False

    def test_realtime_query_uses_local_tier(
        self, router: TaskRouter, mock_local: MagicMock
    ) -> None:
        """Realtime queries route to the local (claude-haiku) tier."""
        response, decision = router.route(
            "Detect the BPM of the track playing right now", _request()
        )
        mock_local.generate.assert_called_once()
        assert decision.tier_used == "local"
        assert decision.task_type == "realtime"
        assert decision.fallback is False

    def test_routing_decision_has_confidence(self, router: TaskRouter) -> None:
        """RoutingDecision.confidence is in [0.0, 1.0]."""
        _, decision = router.route("What is reverb?", _request())
        assert 0.0 <= decision.confidence <= 1.0


# ---------------------------------------------------------------------------
# Tier temperature applied to GenerationRequest
# ---------------------------------------------------------------------------


class TestTierTemperatureOverride:
    def test_factual_uses_low_temperature(self, router: TaskRouter, mock_fast: MagicMock) -> None:
        """Factual tier (fast) applies temperature=0.3 to the request."""
        router.route("What BPM range is house music?", _request())
        actual_request: GenerationRequest = mock_fast.generate.call_args[0][0]
        assert actual_request.temperature == 0.3

    def test_creative_uses_high_temperature(
        self, router: TaskRouter, mock_standard: MagicMock
    ) -> None:
        """Creative tier (standard) applies temperature=0.7 to the request."""
        router.route("Suggest a practice schedule for this week", _request())
        actual_request: GenerationRequest = mock_standard.generate.call_args[0][0]
        assert actual_request.temperature == 0.7

    def test_realtime_uses_medium_temperature(
        self, router: TaskRouter, mock_local: MagicMock
    ) -> None:
        """Realtime tier (local) applies temperature=0.5 to the request."""
        router.route("Detect the key right now", _request())
        actual_request: GenerationRequest = mock_local.generate.call_args[0][0]
        assert actual_request.temperature == 0.5

    def test_tier_max_tokens_applied(self, router: TaskRouter, mock_fast: MagicMock) -> None:
        """Factual tier (fast) applies max_tokens=1024 to the request."""
        router.route("What is reverb?", _request())
        actual_request: GenerationRequest = mock_fast.generate.call_args[0][0]
        assert actual_request.max_tokens == 1024


# ---------------------------------------------------------------------------
# Fallback chain
# ---------------------------------------------------------------------------


class TestFallbackChain:
    def test_factual_falls_back_to_local_when_fast_fails(
        self,
        mock_standard: MagicMock,
        mock_local: MagicMock,
    ) -> None:
        """factual: fast fails → local used (fallback=True)."""
        failing_fast = _make_provider(fail=True)
        router = TaskRouter(fast=failing_fast, standard=mock_standard, local=mock_local)

        response, decision = router.route("What is reverb?", _request())

        failing_fast.generate.assert_called_once()
        mock_local.generate.assert_called_once()
        mock_standard.generate.assert_not_called()
        assert decision.tier_used == "local"
        assert decision.fallback is True
        assert decision.attempts == 2

    def test_factual_falls_back_to_standard_when_fast_and_local_fail(
        self,
        mock_standard: MagicMock,
    ) -> None:
        """factual: fast fails, local fails → standard used (fallback=True)."""
        failing_fast = _make_provider(fail=True)
        failing_local = _make_provider(fail=True)
        router = TaskRouter(fast=failing_fast, standard=mock_standard, local=failing_local)

        response, decision = router.route("What is EQ?", _request())

        assert decision.tier_used == "standard"
        assert decision.fallback is True
        assert decision.attempts == 3

    def test_creative_falls_back_to_fast_when_standard_fails(
        self,
        mock_fast: MagicMock,
        mock_local: MagicMock,
    ) -> None:
        """creative: standard fails → fast used (fallback=True)."""
        failing_standard = _make_provider(fail=True)
        router = TaskRouter(fast=mock_fast, standard=failing_standard, local=mock_local)

        response, decision = router.route(
            "Analyze my sessions and suggest improvements", _request()
        )

        mock_fast.generate.assert_called_once()
        mock_local.generate.assert_not_called()
        assert decision.tier_used == "fast"
        assert decision.fallback is True

    def test_realtime_falls_back_to_fast_when_local_fails(
        self,
        mock_fast: MagicMock,
        mock_standard: MagicMock,
    ) -> None:
        """realtime: local fails → fast used (fallback=True)."""
        failing_local = _make_provider(fail=True)
        router = TaskRouter(fast=mock_fast, standard=mock_standard, local=failing_local)

        response, decision = router.route("Detect the BPM right now", _request())

        mock_fast.generate.assert_called_once()
        mock_standard.generate.assert_not_called()
        assert decision.tier_used == "fast"
        assert decision.fallback is True

    def test_all_tiers_fail_raises_runtime_error(self) -> None:
        """If all tiers in the fallback chain fail, raise RuntimeError."""
        router = TaskRouter(
            fast=_make_provider(fail=True),
            standard=_make_provider(fail=True),
            local=_make_provider(fail=True),
        )
        with pytest.raises(RuntimeError, match="All tiers exhausted"):
            router.route("What is reverb?", _request())

    def test_openai_down_fallback_to_haiku_for_factual(
        self,
        mock_local: MagicMock,
    ) -> None:
        """Cross-provider: both OpenAI tiers fail → Anthropic Haiku handles the query."""
        router = TaskRouter(
            fast=_make_provider(fail=True),
            standard=_make_provider(fail=True),
            local=mock_local,
        )
        response, decision = router.route("What is sidechain compression?", _request())

        mock_local.generate.assert_called_once()
        assert decision.tier_used == "local"
        assert decision.fallback is True


# ---------------------------------------------------------------------------
# GenerationProvider protocol
# ---------------------------------------------------------------------------


class TestGenerationProviderProtocol:
    def test_generate_extracts_query_and_routes(
        self, router: TaskRouter, mock_fast: MagicMock
    ) -> None:
        """generate() extracts query from last user message and routes correctly."""
        response = router.generate(_request("What is a compressor?"))
        mock_fast.generate.assert_called_once()
        assert response.content == "factual answer"

    def test_generate_with_decision_returns_tuple(self, router: TaskRouter) -> None:
        """generate_with_decision() returns (GenerationResponse, RoutingDecision)."""
        response, decision = router.generate_with_decision(_request("What is reverb?"))
        assert isinstance(decision, RoutingDecision)
        assert response.content is not None

    def test_generate_with_wrapped_prompt_strips_question_marker(
        self, router: TaskRouter, mock_standard: MagicMock
    ) -> None:
        """generate() correctly strips '## Question\\n' wrapper from build_user_prompt()."""
        # build_user_prompt() wraps: "## Context\n...\n\n## Question\n<raw_query>"
        # With a creative raw query, standard tier should be selected.
        req = _wrapped_request("Analyze my practice sessions and suggest improvements")
        router.generate(req)
        mock_standard.generate.assert_called_once()


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


class TestStreamingFallback:
    def test_generate_stream_routes_factual_to_fast(
        self, router: TaskRouter, mock_fast: MagicMock
    ) -> None:
        """Streaming: factual query streams from fast tier."""
        chunks = list(router.generate_stream(_request("What is reverb?")))
        mock_fast.generate_stream.assert_called_once()
        assert chunks == ["factual answer"]

    def test_generate_stream_falls_back_on_failure(
        self,
        mock_standard: MagicMock,
        mock_local: MagicMock,
    ) -> None:
        """Streaming: if primary stream tier fails, next tier in chain is used."""
        failing_fast = MagicMock(spec=GenerationProvider)
        failing_fast.generate_stream.side_effect = RuntimeError("stream failed")
        router = TaskRouter(fast=failing_fast, standard=mock_standard, local=mock_local)

        # Factual fallback chain: fast → local → standard
        chunks = list(router.generate_stream(_request("What is EQ?")))
        mock_local.generate_stream.assert_called_once()
        assert chunks == ["realtime answer"]

    def test_generate_stream_all_fail_raises(self) -> None:
        """Streaming: all tiers fail → RuntimeError."""
        router = TaskRouter(
            fast=_make_provider(fail=True),
            standard=_make_provider(fail=True),
            local=_make_provider(fail=True),
        )
        with pytest.raises(RuntimeError, match="All streaming tiers exhausted"):
            list(router.generate_stream(_request("What is reverb?")))


# ---------------------------------------------------------------------------
# _extract_query_from_request helper
# ---------------------------------------------------------------------------


class TestExtractQueryFromRequest:
    def test_plain_user_message(self) -> None:
        """Returns the content of the last user message."""
        req = GenerationRequest(
            messages=(Message(role="user", content="What is EQ?"),),
            temperature=0.7,
            max_tokens=1024,
        )
        assert _extract_query_from_request(req) == "What is EQ?"

    def test_strips_build_user_prompt_wrapper(self) -> None:
        """Strips the '## Context\\n...\\n\\n## Question\\n' wrapper."""
        wrapped = "## Context\nSome context.\n\n## Question\nWhat is reverb?"
        req = GenerationRequest(
            messages=(Message(role="user", content=wrapped),),
            temperature=0.7,
            max_tokens=1024,
        )
        assert _extract_query_from_request(req) == "What is reverb?"

    def test_returns_last_user_message_when_multiple(self) -> None:
        """Returns the LAST user message, not the first."""
        req = GenerationRequest(
            messages=(
                Message(role="system", content="System prompt."),
                Message(role="user", content="First question."),
                Message(role="assistant", content="Answer."),
                Message(role="user", content="Second question."),
            ),
            temperature=0.7,
            max_tokens=1024,
        )
        assert _extract_query_from_request(req) == "Second question."

    def test_fallback_for_no_user_message(self) -> None:
        """Falls back to first message content when no user message exists."""
        req = GenerationRequest(
            messages=(Message(role="system", content="System only."),),
            temperature=0.7,
            max_tokens=1024,
        )
        result = _extract_query_from_request(req)
        assert result == "System only."

    def test_empty_query_fallback(self) -> None:
        """Returns 'unknown query' when all messages are empty."""
        req = GenerationRequest(
            messages=(Message(role="user", content="   "),),
            temperature=0.7,
            max_tokens=1024,
        )
        assert _extract_query_from_request(req) == "unknown query"


# ---------------------------------------------------------------------------
# RoutingDecision invariants
# ---------------------------------------------------------------------------


class TestRoutingDecisionInvariants:
    def test_routing_decision_is_frozen(self, router: TaskRouter) -> None:
        """RoutingDecision is a frozen dataclass — immutable after creation."""
        _, decision = router.route("What is EQ?", _request())
        with pytest.raises((AttributeError, TypeError)):
            decision.tier_used = "standard"  # type: ignore[misc]

    def test_primary_tier_has_fallback_false(self, router: TaskRouter) -> None:
        """When the primary tier succeeds, fallback=False."""
        _, decision = router.route("What is reverb?", _request())
        assert decision.fallback is False
        assert decision.attempts == 1

    def test_empty_query_defaults_to_creative_tier(
        self, router: TaskRouter, mock_standard: MagicMock
    ) -> None:
        """Empty query ValueError is caught internally → defaults to creative tier."""
        # The router wraps empty-query ValueError from classify_musical_task
        # by defaulting to creative.  We pass a non-empty request but an empty
        # query string to route() (the two args are independent).
        req = _request("Some context prompt")
        # Should not raise — router handles the ValueError from classify_musical_task
        response, decision = router.route("", req)
        assert decision.task_type == "creative"
        mock_standard.generate.assert_called_once()
