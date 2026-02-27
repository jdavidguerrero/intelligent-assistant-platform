"""Core types for musical task routing.

All types are frozen dataclasses — immutable value objects.
No I/O, no imports from db/, api/, or ingestion/.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Three musical task types that drive model tier selection.
# factual:  Knowledge lookups — key signatures, BPM ranges, technique definitions.
# creative: Synthesis tasks — practice plans, arrangement analysis, improvement advice.
# realtime: Live-assist tasks — beat detection, pattern recognition, monitoring.
TaskType = Literal["factual", "creative", "realtime"]


@dataclass(frozen=True)
class ModelTier:
    """Configuration for a model tier (fast / standard / local).

    Attributes:
        name:        Tier identifier — "fast" | "standard" | "local".
        provider:    Backend provider — "openai" | "anthropic".
        model:       Model identifier string (e.g. "gpt-4o-mini").
        temperature: Sampling temperature. Lower = more deterministic (factual).
        max_tokens:  Maximum tokens to generate. Smaller for fast/cheap tiers.
    """

    name: str
    provider: str
    model: str
    temperature: float
    max_tokens: int

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name must be non-empty")
        if self.provider not in {"openai", "anthropic", "ollama"}:
            raise ValueError(f"provider must be openai|anthropic|ollama, got {self.provider!r}")
        if not self.model:
            raise ValueError("model must be non-empty")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(f"temperature must be in [0.0, 2.0], got {self.temperature}")
        if self.max_tokens < 1:
            raise ValueError(f"max_tokens must be >= 1, got {self.max_tokens}")


@dataclass(frozen=True)
class ClassificationResult:
    """Result of classifying a musical query.

    Attributes:
        task_type:       Classified task type.
        confidence:      Score in [0.0, 1.0]. Higher = more signal matches.
                         confidence = n_matches / (n_matches + 1).
        matched_signals: Tuple of regex patterns that fired during classification.
    """

    task_type: TaskType
    confidence: float
    matched_signals: tuple[str, ...]

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")
