"""Sub-domain definitions for the music domain."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MusicSubDomain = Literal[
    "sound_design",
    "arrangement",
    "mixing",
    "genre_analysis",
    "live_performance",
    "practice",
]

MUSIC_SUB_DOMAINS: tuple[str, ...] = (
    "sound_design",
    "arrangement",
    "mixing",
    "genre_analysis",
    "live_performance",
    "practice",
)


@dataclass(frozen=True)
class SubDomainTag:
    """Sub-domain classification for a knowledge chunk."""

    sub_domain: str
    confidence: float
    method: Literal["path", "keyword", "manual"]

    def __post_init__(self) -> None:
        """Validate sub_domain and confidence values."""
        if self.sub_domain not in MUSIC_SUB_DOMAINS:
            raise ValueError(
                f"sub_domain must be one of {MUSIC_SUB_DOMAINS}, got {self.sub_domain!r}"
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")
