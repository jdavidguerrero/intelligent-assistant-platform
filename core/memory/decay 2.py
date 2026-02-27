"""Memory decay functions — pure, deterministic.

All time-sensitive logic takes `now` as an explicit parameter.
No datetime.now() calls anywhere in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from core.memory.types import DECAY_DAYS, MemoryEntry


@dataclass(frozen=True)
class DecayResult:
    """Result of computing effective weight after decay.

    Attributes:
        effective_weight: float in [0.0, 1.0]. 1.0 = full weight, 0.0 = expired.
        is_expired: True when effective_weight reaches 0.0.
        days_old: Age of the entry in fractional days.
    """

    effective_weight: float
    is_expired: bool
    days_old: float


def compute_decay_weight(entry: MemoryEntry, now: datetime) -> DecayResult:
    """Compute the current effective weight of a memory entry.

    Uses linear decay from 1.0 at day 0 to 0.0 at DECAY_DAYS[type].
    preference and growth entries never decay (DECAY_DAYS=None).
    Pinned entries never decay regardless of type.

    Args:
        entry: The memory entry to evaluate.
        now: Current datetime. Must be timezone-aware.

    Returns:
        DecayResult with effective_weight, is_expired, and days_old.

    Raises:
        ValueError: If now has no timezone info.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware (use datetime.now(UTC))")

    created = datetime.fromisoformat(entry.created_at)
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)

    days_old = (now - created).total_seconds() / 86400.0
    decay_window = DECAY_DAYS.get(entry.memory_type)

    # Never-decaying types (preference, growth) OR pinned entries
    if decay_window is None or entry.pinned:
        return DecayResult(effective_weight=1.0, is_expired=False, days_old=days_old)

    # Linear decay: 1.0 at day 0, 0.0 at day decay_window
    raw_weight = max(0.0, 1.0 - (days_old / decay_window))
    return DecayResult(
        effective_weight=round(raw_weight, 4),
        is_expired=raw_weight == 0.0,
        days_old=days_old,
    )


def filter_active_memories(
    entries: list[MemoryEntry],
    now: datetime,
) -> list[MemoryEntry]:
    """Return only entries that have not yet expired.

    Pure function — no I/O, no side effects.

    Args:
        entries: All memory entries.
        now: Current timezone-aware datetime.

    Returns:
        Entries where compute_decay_weight(entry, now).is_expired == False.
    """
    return [e for e in entries if not compute_decay_weight(e, now).is_expired]
