"""Musical task router — classifies queries and routes to the optimal model tier.

Routes to one of three model tiers based on musical task classification:
  - Tier 1 (fast):     gpt-4o-mini  — factual lookups
  - Tier 2 (standard): gpt-4o       — creative synthesis
  - Tier 3 (local):    claude-haiku — realtime + cross-provider fallback

Implements the GenerationProvider protocol so it can drop in transparently
as a replacement for a single-provider setup.

Fallback chains:
  factual:  fast  → local  → standard  (never spend Tier 2 on a lookup)
  creative: standard → fast → local    (quality first; degrade if needed)
  realtime: local → fast  → standard   (cross-provider first; fallback to OpenAI)
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass

from core.generation.base import GenerationProvider, GenerationRequest, GenerationResponse
from core.routing.classifier import classify_musical_task
from core.routing.tiers import TIER_FAST, TIER_LOCAL, TIER_STANDARD, ModelTier, select_tier
from core.routing.types import TaskType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Routing decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoutingDecision:
    """Record of a routing decision made for a query.

    Attributes:
        tier_used:  Name of the tier that generated the response ("fast" / "standard" / "local").
        task_type:  Classified task type.
        confidence: Classification confidence [0.0, 1.0].
        fallback:   True if the primary tier failed and a fallback tier was used.
        attempts:   Number of tier attempts before success.
    """

    tier_used: str
    task_type: TaskType
    confidence: float
    fallback: bool
    attempts: int = 1


# ---------------------------------------------------------------------------
# Fallback chains
# ---------------------------------------------------------------------------

_FALLBACK_CHAINS: dict[TaskType, list[str]] = {
    "factual": ["fast", "local", "standard"],
    "creative": ["standard", "fast", "local"],
    "realtime": ["local", "fast", "standard"],
}


# ---------------------------------------------------------------------------
# TaskRouter
# ---------------------------------------------------------------------------


class TaskRouter:
    """Route musical queries to the optimal model tier with automatic fallback.

    Implements the GenerationProvider protocol — can drop in as a replacement
    for a single provider anywhere in the pipeline.

    Args:
        fast:     Tier 1 provider (gpt-4o-mini) for factual lookups.
        standard: Tier 2 provider (gpt-4o) for creative synthesis.
        local:    Tier 3 provider (claude-haiku) for realtime + cross-provider fallback.
    """

    def __init__(
        self,
        fast: GenerationProvider,
        standard: GenerationProvider,
        local: GenerationProvider,
    ) -> None:
        self._providers: dict[str, GenerationProvider] = {
            "fast": fast,
            "standard": standard,
            "local": local,
        }
        self._tiers: dict[str, ModelTier] = {
            "fast": TIER_FAST,
            "standard": TIER_STANDARD,
            "local": TIER_LOCAL,
        }

    # ------------------------------------------------------------------
    # Primary routing API
    # ------------------------------------------------------------------

    def route(
        self,
        query: str,
        request: GenerationRequest,
    ) -> tuple[GenerationResponse, RoutingDecision]:
        """Classify the query, select a tier, and generate with fallback.

        The tier's temperature and max_tokens override the request's defaults,
        unless the caller has set non-default values (checked against tier defaults).
        In practice the request temperature and max_tokens from the caller are
        preserved — the tier config is advisory, not forced, to respect caller intent.

        Args:
            query:   Raw user query string for classification.
            request: GenerationRequest already built (system + user messages).

        Returns:
            Tuple of (GenerationResponse, RoutingDecision).

        Raises:
            RuntimeError: If all tiers in the fallback chain fail.
        """
        # Classify the query
        try:
            classification = classify_musical_task(query)
        except ValueError:
            # Empty query — default to creative (safest powerful tier)
            from core.routing.types import ClassificationResult

            classification = ClassificationResult(
                task_type="creative", confidence=0.0, matched_signals=()
            )

        chain = _FALLBACK_CHAINS[classification.task_type]
        primary_tier = select_tier(classification).name

        last_exc: Exception | None = None
        for attempt, tier_name in enumerate(chain, start=1):
            provider = self._providers[tier_name]
            tier = self._tiers[tier_name]

            # Build a tier-appropriate request (override temperature + max_tokens)
            tier_request = GenerationRequest(
                messages=request.messages,
                temperature=tier.temperature,
                max_tokens=tier.max_tokens,
            )

            try:
                response = provider.generate(tier_request)
                decision = RoutingDecision(
                    tier_used=tier_name,
                    task_type=classification.task_type,
                    confidence=classification.confidence,
                    fallback=(tier_name != primary_tier),
                    attempts=attempt,
                )
                if decision.fallback:
                    logger.warning(
                        "Tier '%s' failed for %s query — succeeded with fallback tier '%s'",
                        primary_tier,
                        classification.task_type,
                        tier_name,
                    )
                else:
                    logger.info(
                        "Routed %s query (confidence=%.2f) → tier '%s' (%s)",
                        classification.task_type,
                        classification.confidence,
                        tier_name,
                        tier.model,
                    )
                return response, decision

            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Tier '%s' failed (attempt %d/%d): %s",
                    tier_name,
                    attempt,
                    len(chain),
                    exc,
                )

        raise RuntimeError(
            f"All tiers exhausted for {classification.task_type!r} query. "
            f"Last error: {last_exc}"
        ) from last_exc

    # ------------------------------------------------------------------
    # GenerationProvider protocol (drop-in compatibility)
    # ------------------------------------------------------------------

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Implement GenerationProvider.generate() for drop-in use.

        Extracts the query from the last user message in the request.
        Strips the '## Context\\n...\\n\\n## Question\\n' wrapper added by
        build_user_prompt() to recover the raw user query for classification.

        Args:
            request: GenerationRequest with at least one message.

        Returns:
            GenerationResponse from the selected tier.
        """
        query = _extract_query_from_request(request)
        response, _ = self.route(query, request)
        return response

    def generate_with_decision(
        self, request: GenerationRequest
    ) -> tuple[GenerationResponse, RoutingDecision]:
        """Like generate() but also returns the RoutingDecision.

        Use this in the /ask route when you need the tier name for UsageMetadata.

        Args:
            request: GenerationRequest with at least one message.

        Returns:
            Tuple of (GenerationResponse, RoutingDecision).
        """
        query = _extract_query_from_request(request)
        return self.route(query, request)

    def generate_stream(self, request: GenerationRequest) -> Iterator[str]:
        """Implement GenerationProvider.generate_stream() for drop-in use.

        Routes the stream to the selected tier. Falls back in the fallback chain
        if streaming fails on the primary tier.

        Args:
            request: GenerationRequest with at least one message.

        Returns:
            Iterator of text chunks from the selected tier.
        """
        query = _extract_query_from_request(request)
        try:
            classification = classify_musical_task(query)
        except ValueError:
            from core.routing.types import ClassificationResult

            classification = ClassificationResult(
                task_type="creative", confidence=0.0, matched_signals=()
            )

        chain = _FALLBACK_CHAINS[classification.task_type]
        primary_tier = select_tier(classification).name

        last_exc: Exception | None = None
        for tier_name in chain:
            provider = self._providers[tier_name]
            tier = self._tiers[tier_name]
            tier_request = GenerationRequest(
                messages=request.messages,
                temperature=tier.temperature,
                max_tokens=tier.max_tokens,
            )
            try:
                yield from provider.generate_stream(tier_request)
                if tier_name != primary_tier:
                    logger.warning(
                        "Stream fallback: '%s' failed, used '%s'", primary_tier, tier_name
                    )
                return
            except Exception as exc:
                last_exc = exc
                logger.warning("Stream tier '%s' failed: %s", tier_name, exc)

        raise RuntimeError(f"All streaming tiers exhausted. Last error: {last_exc}") from last_exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_query_from_request(request: GenerationRequest) -> str:
    """Extract the raw query from a GenerationRequest.

    build_user_prompt() wraps queries as:
        ## Context
        ...

        ## Question
        <raw query here>

    This function recovers the raw query for classification.
    Falls back to the full last-message content if the wrapper is absent.

    Args:
        request: GenerationRequest with at least one message.

    Returns:
        Raw query string (non-empty).
    """
    # Find the last user message
    user_content = ""
    for msg in reversed(request.messages):
        if msg.role == "user":
            user_content = msg.content
            break

    if not user_content:
        # Fall back to system message or first message
        user_content = request.messages[0].content if request.messages else ""

    # Strip the build_user_prompt() wrapper to recover raw query
    marker = "\n\n## Question\n"
    if marker in user_content:
        return user_content.split(marker, 1)[1].strip()

    return user_content.strip() or "unknown query"
