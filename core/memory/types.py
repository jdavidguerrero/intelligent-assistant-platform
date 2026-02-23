"""Musical memory types — pure value objects.

These are the core data contracts for the memory system.
No I/O, no datetime.now(), no imports from db/ or ingestion/.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MemoryType = Literal["preference", "session", "growth", "creative"]

DECAY_DAYS: dict[str, int | None] = {
    "preference": None,  # never decays
    "growth": None,  # never decays
    "session": 30,
    "creative": 14,
}


@dataclass(frozen=True)
class MemoryEntry:
    """A single persisted musical memory.

    Attributes:
        memory_id: UUID4 string, stable identity.
        memory_type: One of preference | session | growth | creative.
        content: Free-text content (max 2000 chars).
        created_at: ISO-8601 UTC datetime string.
        updated_at: ISO-8601 UTC datetime string.
        pinned: If True, never decays regardless of memory_type.
        tags: Keyword tags for display and filtering.
        source: How created — "auto" (extracted) or "manual" (user).
    """

    memory_id: str
    memory_type: MemoryType
    content: str
    created_at: str
    updated_at: str
    pinned: bool = False
    tags: tuple[str, ...] = ()
    source: str = "auto"

    def __post_init__(self) -> None:
        allowed: set[str] = {"preference", "session", "growth", "creative"}
        if self.memory_type not in allowed:
            raise ValueError(
                f"memory_type must be one of {sorted(allowed)}, got {self.memory_type!r}"
            )
        if not self.content.strip():
            raise ValueError("content must not be empty")
        if len(self.content) > 2000:
            raise ValueError(f"content must be <= 2000 characters, got {len(self.content)}")
        if not self.memory_id.strip():
            raise ValueError("memory_id must not be empty")
