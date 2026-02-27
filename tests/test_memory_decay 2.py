"""Tests for core/memory/decay.py"""

from datetime import UTC, datetime, timedelta

import pytest

from core.memory.decay import compute_decay_weight, filter_active_memories
from core.memory.types import MemoryEntry

FROZEN_NOW = datetime(2026, 2, 21, 12, 0, 0, tzinfo=UTC)


def _make_entry(
    memory_type: str = "session",
    days_ago: float = 0.0,
    pinned: bool = False,
) -> MemoryEntry:
    created = FROZEN_NOW - timedelta(days=days_ago)
    return MemoryEntry(
        memory_id="test-id",
        memory_type=memory_type,  # type: ignore[arg-type]
        content="test content",
        created_at=created.isoformat(),
        updated_at=created.isoformat(),
        pinned=pinned,
    )


class TestComputeDecayWeight:
    def test_preference_always_full_weight(self) -> None:
        e = _make_entry("preference", days_ago=100)
        result = compute_decay_weight(e, FROZEN_NOW)
        assert result.effective_weight == 1.0
        assert result.is_expired is False

    def test_growth_always_full_weight(self) -> None:
        e = _make_entry("growth", days_ago=200)
        result = compute_decay_weight(e, FROZEN_NOW)
        assert result.effective_weight == 1.0
        assert result.is_expired is False

    def test_session_fresh_near_full_weight(self) -> None:
        e = _make_entry("session", days_ago=1)
        result = compute_decay_weight(e, FROZEN_NOW)
        assert result.effective_weight > 0.9
        assert result.is_expired is False

    def test_session_half_decayed_at_15_days(self) -> None:
        e = _make_entry("session", days_ago=15)
        result = compute_decay_weight(e, FROZEN_NOW)
        assert abs(result.effective_weight - 0.5) < 0.05
        assert result.is_expired is False

    def test_session_expired_at_30_days(self) -> None:
        e = _make_entry("session", days_ago=30)
        result = compute_decay_weight(e, FROZEN_NOW)
        assert result.effective_weight == 0.0
        assert result.is_expired is True

    def test_session_expired_beyond_30_days(self) -> None:
        e = _make_entry("session", days_ago=45)
        result = compute_decay_weight(e, FROZEN_NOW)
        assert result.effective_weight == 0.0
        assert result.is_expired is True

    def test_creative_expires_at_14_days(self) -> None:
        e = _make_entry("creative", days_ago=14)
        result = compute_decay_weight(e, FROZEN_NOW)
        assert result.effective_weight == 0.0
        assert result.is_expired is True

    def test_creative_half_decayed_at_7_days(self) -> None:
        e = _make_entry("creative", days_ago=7)
        result = compute_decay_weight(e, FROZEN_NOW)
        assert abs(result.effective_weight - 0.5) < 0.05

    def test_pinned_session_never_decays(self) -> None:
        e = _make_entry("session", days_ago=60, pinned=True)
        result = compute_decay_weight(e, FROZEN_NOW)
        assert result.effective_weight == 1.0
        assert result.is_expired is False

    def test_pinned_creative_never_decays(self) -> None:
        e = _make_entry("creative", days_ago=30, pinned=True)
        result = compute_decay_weight(e, FROZEN_NOW)
        assert result.effective_weight == 1.0
        assert result.is_expired is False

    def test_naive_datetime_raises(self) -> None:
        e = _make_entry("session")
        naive_now = datetime(2026, 2, 21, 12, 0, 0)  # no tzinfo
        with pytest.raises(ValueError, match="timezone-aware"):
            compute_decay_weight(e, naive_now)

    def test_days_old_is_positive_for_old_entry(self) -> None:
        e = _make_entry("session", days_ago=10)
        result = compute_decay_weight(e, FROZEN_NOW)
        assert abs(result.days_old - 10.0) < 0.01


class TestFilterActiveMemories:
    def test_returns_only_non_expired(self) -> None:
        fresh = _make_entry("session", days_ago=1)
        expired = _make_entry("session", days_ago=31)
        active = filter_active_memories([fresh, expired], FROZEN_NOW)
        assert active == [fresh]

    def test_empty_list_returns_empty(self) -> None:
        assert filter_active_memories([], FROZEN_NOW) == []

    def test_all_active_returns_all(self) -> None:
        entries = [_make_entry("preference", days_ago=100), _make_entry("growth", days_ago=200)]
        assert filter_active_memories(entries, FROZEN_NOW) == entries

    def test_pinned_expired_session_still_returned(self) -> None:
        pinned = _make_entry("session", days_ago=60, pinned=True)
        active = filter_active_memories([pinned], FROZEN_NOW)
        assert active == [pinned]
