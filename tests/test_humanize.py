"""
tests/test_humanize.py — Tests for core/music_theory/humanize.py

Covers:
    - _bpm_to_ticks_per_ms: unit conversion helper
    - humanize_timing: tick_offset assignment, range, seed, edge cases
    - humanize_velocity: velocity variation, clamping, both BassNote and DrumHit
    - add_ghost_notes: ghost hit creation, position exclusion, probability, seed
"""

from __future__ import annotations

import pytest

from core.music_theory.humanize import (
    _bpm_to_ticks_per_ms,
    add_ghost_notes,
    humanize_timing,
    humanize_velocity,
)
from core.music_theory.types import BassNote, DrumHit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bass(pitch: int = 45, step: int = 0, dur: int = 4, vel: int = 100, bar: int = 0) -> BassNote:
    return BassNote(pitch_midi=pitch, step=step, duration_steps=dur, velocity=vel, bar=bar)


def _hit(inst: str = "kick", step: int = 0, vel: int = 110, bar: int = 0) -> DrumHit:
    return DrumHit(instrument=inst, step=step, velocity=vel, bar=bar)


def _bass_seq(n: int = 4, vel: int = 100) -> tuple[BassNote, ...]:
    """Build n BassNote objects, cycling through steps 0,4,8,12 across bars."""
    return tuple(_bass(step=(i % 4) * 4, vel=vel, bar=i // 4) for i in range(n))


# ---------------------------------------------------------------------------
# _bpm_to_ticks_per_ms
# ---------------------------------------------------------------------------


class TestBpmToTicksPerMs:
    def test_120bpm_480tpb(self) -> None:
        result = _bpm_to_ticks_per_ms(120.0, 480)
        assert abs(result - 0.96) < 0.001

    def test_120bpm_960tpb(self) -> None:
        result = _bpm_to_ticks_per_ms(120.0, 960)
        assert abs(result - 1.92) < 0.001

    def test_60bpm_480tpb(self) -> None:
        result = _bpm_to_ticks_per_ms(60.0, 480)
        assert abs(result - 0.48) < 0.001

    def test_140bpm_480tpb_greater_than_120(self) -> None:
        r120 = _bpm_to_ticks_per_ms(120.0, 480)
        r140 = _bpm_to_ticks_per_ms(140.0, 480)
        assert r140 > r120


# ---------------------------------------------------------------------------
# humanize_timing
# ---------------------------------------------------------------------------


class TestHumanizeTiming:
    def test_returns_tuple_of_bass_notes(self) -> None:
        notes = _bass_seq(3)
        result = humanize_timing(notes, jitter_ms=5.0, bpm=120.0, seed=0)
        assert isinstance(result, tuple)
        assert all(isinstance(n, BassNote) for n in result)

    def test_length_preserved(self) -> None:
        notes = _bass_seq(6)
        result = humanize_timing(notes, jitter_ms=5.0, bpm=120.0, seed=42)
        assert len(result) == len(notes)

    def test_tick_offset_set(self) -> None:
        notes = _bass_seq(4)
        result = humanize_timing(notes, jitter_ms=5.0, bpm=120.0, seed=1)
        assert all(isinstance(n.tick_offset, int) for n in result)

    def test_tick_offset_within_range(self) -> None:
        """At 120 BPM, 480 tpb: 5ms → max_ticks = round(5 × 0.96) = 5"""
        notes = _bass_seq(20)
        result = humanize_timing(notes, jitter_ms=5.0, bpm=120.0, seed=7)
        for n in result:
            assert abs(n.tick_offset) <= 5

    def test_zero_jitter_returns_unchanged(self) -> None:
        notes = _bass_seq(4)
        result = humanize_timing(notes, jitter_ms=0.0, bpm=120.0, seed=0)
        assert all(n.tick_offset == 0 for n in result)

    def test_deterministic_with_seed(self) -> None:
        notes = _bass_seq(8)
        r1 = humanize_timing(notes, jitter_ms=5.0, bpm=120.0, seed=99)
        r2 = humanize_timing(notes, jitter_ms=5.0, bpm=120.0, seed=99)
        assert r1 == r2

    def test_different_seeds_different_offsets(self) -> None:
        notes = _bass_seq(8)
        r1 = humanize_timing(notes, jitter_ms=5.0, bpm=120.0, seed=1)
        r2 = humanize_timing(notes, jitter_ms=5.0, bpm=120.0, seed=2)
        offsets1 = [n.tick_offset for n in r1]
        offsets2 = [n.tick_offset for n in r2]
        assert offsets1 != offsets2

    def test_negative_jitter_raises(self) -> None:
        with pytest.raises(ValueError, match="jitter_ms"):
            humanize_timing(_bass_seq(2), jitter_ms=-1.0)

    def test_empty_sequence_returns_empty(self) -> None:
        result = humanize_timing((), jitter_ms=5.0, bpm=120.0)
        assert result == ()

    def test_pitch_velocity_bar_step_unchanged(self) -> None:
        orig = _bass(pitch=45, step=0, dur=4, vel=100, bar=2)
        (result,) = humanize_timing((orig,), jitter_ms=5.0, bpm=120.0, seed=0)
        assert result.pitch_midi == 45
        assert result.step == 0
        assert result.duration_steps == 4
        assert result.velocity == 100
        assert result.bar == 2

    def test_larger_jitter_larger_max_offset(self) -> None:
        notes = _bass_seq(30)
        r_small = humanize_timing(notes, jitter_ms=1.0, bpm=120.0, seed=5)
        r_large = humanize_timing(notes, jitter_ms=15.0, bpm=120.0, seed=5)
        max_small = max(abs(n.tick_offset) for n in r_small)
        max_large = max(abs(n.tick_offset) for n in r_large)
        assert max_large >= max_small

    def test_high_bpm_more_ticks_per_ms(self) -> None:
        """Higher BPM → more ticks per ms → larger max_ticks for same jitter_ms."""
        notes = _bass_seq(30)
        r_slow = humanize_timing(notes, jitter_ms=5.0, bpm=80.0, seed=3)
        r_fast = humanize_timing(notes, jitter_ms=5.0, bpm=160.0, seed=3)
        max_slow = max(abs(n.tick_offset) for n in r_slow)
        max_fast = max(abs(n.tick_offset) for n in r_fast)
        assert max_fast >= max_slow


# ---------------------------------------------------------------------------
# humanize_velocity
# ---------------------------------------------------------------------------


class TestHumanizeVelocity:
    def test_returns_tuple(self) -> None:
        result = humanize_velocity(_bass_seq(3), variation=10, seed=0)
        assert isinstance(result, tuple)

    def test_length_preserved(self) -> None:
        notes = _bass_seq(6)
        result = humanize_velocity(notes, variation=10, seed=0)
        assert len(result) == len(notes)

    def test_works_with_bass_note(self) -> None:
        notes = (_bass(vel=100),)
        result = humanize_velocity(notes, variation=12, seed=0)
        assert isinstance(result[0], BassNote)

    def test_works_with_drum_hit(self) -> None:
        hits = (_hit(vel=110),)
        result = humanize_velocity(hits, variation=10, seed=0)
        assert isinstance(result[0], DrumHit)

    def test_variation_zero_returns_same_velocities(self) -> None:
        notes = _bass_seq(4, vel=100)
        result = humanize_velocity(notes, variation=0, seed=0)
        assert all(n.velocity == 100 for n in result)

    def test_variation_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="variation"):
            humanize_velocity(_bass_seq(2), variation=-1)

    def test_velocity_clamped_above(self) -> None:
        notes = (_bass(vel=127),)
        for seed in range(20):
            result = humanize_velocity(notes, variation=20, seed=seed)
            assert result[0].velocity <= 127

    def test_velocity_clamped_below(self) -> None:
        notes = (_bass(vel=1),)
        for seed in range(20):
            result = humanize_velocity(notes, variation=20, seed=seed)
            assert result[0].velocity >= 1

    def test_deterministic_with_seed(self) -> None:
        notes = _bass_seq(8, vel=80)
        r1 = humanize_velocity(notes, variation=12, seed=42)
        r2 = humanize_velocity(notes, variation=12, seed=42)
        assert r1 == r2

    def test_different_seeds_produce_different_velocities(self) -> None:
        notes = _bass_seq(10, vel=80)
        r1 = humanize_velocity(notes, variation=12, seed=1)
        r2 = humanize_velocity(notes, variation=12, seed=2)
        vels1 = [n.velocity for n in r1]
        vels2 = [n.velocity for n in r2]
        assert vels1 != vels2

    def test_empty_sequence(self) -> None:
        result = humanize_velocity((), variation=10)
        assert result == ()

    def test_step_and_pitch_unchanged(self) -> None:
        orig = _bass(pitch=45, step=4, dur=2, vel=100, bar=1)
        (result,) = humanize_velocity((orig,), variation=15, seed=0)
        assert result.pitch_midi == 45
        assert result.step == 4
        assert result.duration_steps == 2
        assert result.bar == 1


# ---------------------------------------------------------------------------
# add_ghost_notes
# ---------------------------------------------------------------------------


class TestAddGhostNotes:
    def _hihat_bar(self) -> tuple[DrumHit, ...]:
        """Hi-hat only on even steps (0,2,4,...,14)."""
        return tuple(
            DrumHit(instrument="hihat_c", step=s * 2, velocity=72, bar=0)
            for s in range(8)
        )

    def test_returns_tuple_of_drum_hits(self) -> None:
        hits = self._hihat_bar()
        result = add_ghost_notes(hits, probability=0.5, bars=1, seed=0)
        assert isinstance(result, tuple)
        assert all(isinstance(h, DrumHit) for h in result)

    def test_probability_zero_returns_original(self) -> None:
        hits = self._hihat_bar()
        result = add_ghost_notes(hits, probability=0.0, bars=1)
        assert result == hits

    def test_probability_one_fills_all_empty_steps(self) -> None:
        """With probability=1.0, every silent step for the given instrument gets a ghost note."""
        hits = (DrumHit(instrument="hihat_c", step=0, velocity=72, bar=0),)
        result = add_ghost_notes(
            hits,
            probability=1.0,
            instruments=frozenset({"hihat_c"}),  # limit to hihat_c only
            bars=1,
            steps_per_bar=4,
            seed=0,
        )
        # Original 1 hit + 3 ghost hits on steps 1,2,3
        ghost_hits = [h for h in result if h not in hits]
        assert len(ghost_hits) == 3

    def test_ghost_hits_on_silent_steps_only(self) -> None:
        """Ghost notes for hihat_c never overlap with existing hihat_c hits."""
        hits = self._hihat_bar()  # hihat_c on even steps 0,2,4,...,14
        occupied_steps = {h.step for h in hits}
        # Limit to hihat_c so we can verify no overlap for that instrument
        result = add_ghost_notes(
            hits, probability=1.0, instruments=frozenset({"hihat_c"}), bars=1, seed=0
        )
        ghost_hits = [h for h in result if h not in set(hits)]
        ghost_steps = {h.step for h in ghost_hits}
        assert ghost_steps.isdisjoint(occupied_steps)

    def test_ghost_instrument_matches_target(self) -> None:
        hits = (DrumHit(instrument="hihat_c", step=0, velocity=72, bar=0),)
        result = add_ghost_notes(
            hits,
            probability=1.0,
            instruments=frozenset({"hihat_c"}),
            bars=1,
            steps_per_bar=4,
        )
        for h in result:
            assert h.instrument == "hihat_c"

    def test_velocity_within_range(self) -> None:
        hits = ()
        result = add_ghost_notes(
            hits,
            probability=1.0,
            velocity_range=(10, 30),
            bars=1,
            steps_per_bar=16,
            seed=0,
        )
        assert all(10 <= h.velocity <= 30 for h in result)

    def test_invalid_probability_raises(self) -> None:
        with pytest.raises(ValueError, match="probability"):
            add_ghost_notes((), probability=1.5)

    def test_invalid_velocity_range_raises(self) -> None:
        with pytest.raises(ValueError, match="velocity_range"):
            add_ghost_notes((), probability=0.5, velocity_range=(30, 10))

    def test_sorted_by_bar_step(self) -> None:
        hits = (DrumHit(instrument="hihat_c", step=0, velocity=72, bar=0),)
        result = add_ghost_notes(hits, probability=1.0, bars=2, steps_per_bar=4, seed=0)
        keys = [(h.bar, h.step) for h in result]
        assert keys == sorted(keys)

    def test_deterministic_with_seed(self) -> None:
        hits = self._hihat_bar()
        r1 = add_ghost_notes(hits, probability=0.3, bars=2, seed=77)
        r2 = add_ghost_notes(hits, probability=0.3, bars=2, seed=77)
        assert r1 == r2

    def test_custom_instruments_parameter(self) -> None:
        """Only specified instruments get ghost notes."""
        hits = (DrumHit(instrument="kick", step=0, velocity=110, bar=0),)
        result = add_ghost_notes(
            hits,
            probability=1.0,
            instruments=frozenset({"hihat_o"}),
            bars=1,
            steps_per_bar=4,
        )
        ghost_hits = [h for h in result if h not in set(hits)]
        assert all(h.instrument == "hihat_o" for h in ghost_hits)

    def test_bars_parameter_bounds_ghost_search(self) -> None:
        """Ghost notes are only added within the specified bar range."""
        hits = ()
        result = add_ghost_notes(
            hits,
            probability=1.0,
            bars=2,
            steps_per_bar=4,
            seed=0,
        )
        assert all(h.bar < 2 for h in result)

    def test_empty_input_with_probability_one(self) -> None:
        result = add_ghost_notes(
            (),
            probability=1.0,
            bars=1,
            steps_per_bar=4,
            seed=0,
        )
        assert len(result) > 0  # Ghost notes added on all empty steps
