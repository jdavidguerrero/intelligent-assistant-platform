"""Model tier constants and tier selection for musical task routing.

Three tiers:
  TIER_FAST     — gpt-4o-mini (OpenAI). Cheap, fast. For factual lookups.
  TIER_STANDARD — gpt-4o (OpenAI). Powerful. For creative synthesis.
  TIER_LOCAL    — claude-haiku-4 (Anthropic). Cross-provider redundancy.
                  Routes realtime queries; also acts as fallback if OpenAI is down.

This module is core/ pure: no I/O, no env vars, no imports from other layers.
"""

from __future__ import annotations

from core.routing.types import ClassificationResult, ModelTier, TaskType

# ---------------------------------------------------------------------------
# Tier constants
# ---------------------------------------------------------------------------

TIER_FAST: ModelTier = ModelTier(
    name="fast",
    provider="openai",
    model="gpt-4o-mini",
    temperature=0.3,  # low temp for factual precision
    max_tokens=1024,
)
"""Tier 1 — gpt-4o-mini. Optimised for factual musical lookups.

Cost: $0.15 / $0.60 per million tokens (input / output).
Use for: key signatures, BPM ranges, technique definitions, chord names.
"""

TIER_STANDARD: ModelTier = ModelTier(
    name="standard",
    provider="openai",
    model="gpt-4o",
    temperature=0.7,
    max_tokens=2048,
)
"""Tier 2 — gpt-4o. Full-capability model for creative musical tasks.

Cost: $2.50 / $10.00 per million tokens (input / output).
Use for: practice plans, arrangement analysis, personalised advice.
"""

TIER_LOCAL: ModelTier = ModelTier(
    name="local",
    provider="anthropic",
    model="claude-haiku-4-20250514",
    temperature=0.5,
    max_tokens=1024,
)
"""Tier 3 — claude-haiku-4 (Anthropic). Cross-provider redundancy tier.

Cost: $0.80 / $4.00 per million tokens (input / output).
Use for: realtime queries; fallback when OpenAI tiers are unavailable.
The different provider ensures availability even during OpenAI outages.
"""

# ---------------------------------------------------------------------------
# Routing table
# ---------------------------------------------------------------------------

_ROUTING_TABLE: dict[TaskType, ModelTier] = {
    "factual": TIER_FAST,
    "creative": TIER_STANDARD,
    "realtime": TIER_LOCAL,
}


def select_tier(classification: ClassificationResult) -> ModelTier:
    """Map a ClassificationResult to the appropriate ModelTier.

    Args:
        classification: Result from classify_musical_task().

    Returns:
        The ModelTier that should handle this task.
    """
    return _ROUTING_TABLE[classification.task_type]
