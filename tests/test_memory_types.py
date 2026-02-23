"""Tests for core/memory/types.py"""

from dataclasses import FrozenInstanceError

import pytest

from core.memory.types import DECAY_DAYS, MemoryEntry


class TestMemoryEntry:
    def test_valid_preference_entry(self) -> None:
        e = MemoryEntry(
            memory_id="abc-123",
            memory_type="preference",
            content="I prefer A minor",
            created_at="2026-02-21T12:00:00+00:00",
            updated_at="2026-02-21T12:00:00+00:00",
        )
        assert e.memory_type == "preference"
        assert e.content == "I prefer A minor"
        assert e.pinned is False
        assert e.tags == ()
        assert e.source == "auto"

    def test_all_four_types_accepted(self) -> None:
        for mt in ("preference", "session", "growth", "creative"):
            e = MemoryEntry(
                memory_id="x",
                memory_type=mt,  # type: ignore[arg-type]
                content="test",
                created_at="2026-02-21T12:00:00+00:00",
                updated_at="2026-02-21T12:00:00+00:00",
            )
            assert e.memory_type == mt

    def test_invalid_type_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="memory_type must be one of"):
            MemoryEntry(
                memory_id="x",
                memory_type="unknown",  # type: ignore[arg-type]
                content="test",
                created_at="2026-02-21T12:00:00+00:00",
                updated_at="2026-02-21T12:00:00+00:00",
            )

    def test_empty_content_raises(self) -> None:
        with pytest.raises(ValueError, match="content must not be empty"):
            MemoryEntry(
                memory_id="x",
                memory_type="session",
                content="   ",
                created_at="2026-02-21T12:00:00+00:00",
                updated_at="2026-02-21T12:00:00+00:00",
            )

    def test_content_too_long_raises(self) -> None:
        with pytest.raises(ValueError, match="<= 2000"):
            MemoryEntry(
                memory_id="x",
                memory_type="session",
                content="x" * 2001,
                created_at="2026-02-21T12:00:00+00:00",
                updated_at="2026-02-21T12:00:00+00:00",
            )

    def test_content_exactly_2000_chars_accepted(self) -> None:
        e = MemoryEntry(
            memory_id="x",
            memory_type="session",
            content="x" * 2000,
            created_at="2026-02-21T12:00:00+00:00",
            updated_at="2026-02-21T12:00:00+00:00",
        )
        assert len(e.content) == 2000

    def test_empty_memory_id_raises(self) -> None:
        with pytest.raises(ValueError, match="memory_id must not be empty"):
            MemoryEntry(
                memory_id="  ",
                memory_type="preference",
                content="test",
                created_at="2026-02-21T12:00:00+00:00",
                updated_at="2026-02-21T12:00:00+00:00",
            )

    def test_frozen_cannot_mutate(self) -> None:
        e = MemoryEntry(
            memory_id="x",
            memory_type="preference",
            content="test",
            created_at="2026-02-21T12:00:00+00:00",
            updated_at="2026-02-21T12:00:00+00:00",
        )
        with pytest.raises(FrozenInstanceError):
            e.content = "changed"  # type: ignore[misc]


class TestDecayDaysConstants:
    def test_preference_never_decays(self) -> None:
        assert DECAY_DAYS["preference"] is None

    def test_growth_never_decays(self) -> None:
        assert DECAY_DAYS["growth"] is None

    def test_session_decays_at_30_days(self) -> None:
        assert DECAY_DAYS["session"] == 30

    def test_creative_decays_at_14_days(self) -> None:
        assert DECAY_DAYS["creative"] == 14

    def test_all_four_types_present(self) -> None:
        assert set(DECAY_DAYS.keys()) == {"preference", "session", "growth", "creative"}
