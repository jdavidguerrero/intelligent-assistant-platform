"""
Tests for core/music_theory/drums.py — drum pattern generator.

Validates:
    - _energy_to_multiplier: range, linearity, edge cases
    - _apply_velocity: clamping, humanize flag
    - _grid_for_bar: fill trigger logic
    - generate_pattern: returns DrumPattern, bar/step ranges,
      velocity ranges, fill activation, energy scaling, seed determinism,
      ghost notes, invalid inputs, all genres
"""

from __future__ import annotations

import random

import pytest

from core.music_theory.drums import (
    _apply_velocity,
    _energy_to_multiplier,
    _grid_for_bar,
    generate_pattern,
)
from core.music_theory.types import DrumHit, DrumPattern

# ---------------------------------------------------------------------------
# _energy_to_multiplier
# ---------------------------------------------------------------------------


class TestEnergyToMultiplier:
    def test_energy_0_is_min(self):
        assert _energy_to_multiplier(0) == pytest.approx(0.50)

    def test_energy_10_is_max(self):
        assert _energy_to_multiplier(10) == pytest.approx(1.00)

    def test_energy_5_is_midpoint(self):
        m = _energy_to_multiplier(5)
        assert 0.50 < m < 1.00

    def test_monotonically_increasing(self):
        vals = [_energy_to_multiplier(e) for e in range(11)]
        assert vals == sorted(vals)

    def test_clamps_below_zero(self):
        # energy < 0 clamped to 0
        assert _energy_to_multiplier(-5) == pytest.approx(0.50)

    def test_clamps_above_10(self):
        # energy > 10 clamped to 10
        assert _energy_to_multiplier(15) == pytest.approx(1.00)


# ---------------------------------------------------------------------------
# _apply_velocity
# ---------------------------------------------------------------------------


class TestApplyVelocity:
    def test_no_humanize_is_deterministic(self):
        rng = random.Random(0)
        v = _apply_velocity(100, 1.0, rng, humanize=False)
        assert v == 100

    def test_multiplier_scales_down(self):
        rng = random.Random(0)
        v = _apply_velocity(100, 0.5, rng, humanize=False)
        assert v == 50

    def test_result_clamped_to_127(self):
        rng = random.Random(0)
        v = _apply_velocity(127, 1.0, rng, humanize=False)
        assert v <= 127

    def test_result_minimum_1(self):
        rng = random.Random(0)
        # Very low base and multiplier
        v = _apply_velocity(1, 0.1, rng, humanize=False)
        assert v >= 1

    def test_humanize_adds_variation(self):
        results = set()
        for seed in range(50):
            rng = random.Random(seed)
            results.add(_apply_velocity(90, 1.0, rng, humanize=True))
        assert len(results) > 1  # variation present


# ---------------------------------------------------------------------------
# _grid_for_bar
# ---------------------------------------------------------------------------


class TestGridForBar:
    def _grids(self):
        base = {"kick": [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]}
        fill = {"kick": [1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0]}
        return base, fill

    def test_non_fill_bar_returns_base(self):
        base, fill = self._grids()
        result = _grid_for_bar(0, 4, base, fill)
        assert result is base

    def test_fill_bar_returns_fill(self):
        # Bar 3 is the last bar of a 4-bar phrase → fill
        base, fill = self._grids()
        result = _grid_for_bar(3, 4, base, fill)
        assert result is fill

    def test_bar_7_triggers_fill(self):
        base, fill = self._grids()
        result = _grid_for_bar(7, 4, base, fill)
        assert result is fill

    def test_bar_4_is_not_fill(self):
        # Bar 4 = first bar of second phrase
        base, fill = self._grids()
        result = _grid_for_bar(4, 4, base, fill)
        assert result is base

    def test_every_n_0_never_fills(self):
        base, fill = self._grids()
        # every_n_bars=0: never fill
        result = _grid_for_bar(3, 0, base, fill)
        assert result is base


# ---------------------------------------------------------------------------
# generate_pattern
# ---------------------------------------------------------------------------


class TestGeneratePattern:
    def test_returns_drum_pattern(self):
        p = generate_pattern(genre="organic house", bars=4, seed=0)
        assert isinstance(p, DrumPattern)

    def test_bars_stored_correctly(self):
        p = generate_pattern(genre="organic house", bars=4, seed=0)
        assert p.bars == 4

    def test_bpm_stored(self):
        p = generate_pattern(bpm=128.0, genre="organic house", bars=4, seed=0)
        assert p.bpm == 128.0

    def test_genre_stored(self):
        p = generate_pattern(genre="deep house", bars=4, seed=0)
        assert p.genre == "deep house"

    def test_steps_per_bar_is_16(self):
        p = generate_pattern(genre="organic house", bars=4, seed=0)
        assert p.steps_per_bar == 16

    def test_hits_is_tuple(self):
        p = generate_pattern(genre="organic house", bars=4, seed=0)
        assert isinstance(p.hits, tuple)

    def test_hits_non_empty(self):
        p = generate_pattern(genre="organic house", bars=4, seed=0)
        assert len(p.hits) > 0

    def test_all_hits_are_drum_hits(self):
        p = generate_pattern(genre="organic house", bars=4, seed=0)
        assert all(isinstance(h, DrumHit) for h in p.hits)

    def test_bar_index_in_range(self):
        p = generate_pattern(genre="organic house", bars=8, seed=0)
        for h in p.hits:
            assert 0 <= h.bar < 8

    def test_step_in_range(self):
        p = generate_pattern(genre="organic house", bars=4, seed=0)
        for h in p.hits:
            assert 0 <= h.step <= 15

    def test_velocity_in_range(self):
        p = generate_pattern(genre="organic house", bars=4, seed=0)
        for h in p.hits:
            assert 1 <= h.velocity <= 127

    def test_seed_deterministic(self):
        p1 = generate_pattern(genre="organic house", bars=4, humanize=True, seed=99)
        p2 = generate_pattern(genre="organic house", bars=4, humanize=True, seed=99)
        assert p1.hits == p2.hits

    def test_different_seeds_different_velocities(self):
        p1 = generate_pattern(genre="organic house", bars=4, humanize=True, seed=1)
        p2 = generate_pattern(genre="organic house", bars=4, humanize=True, seed=2)
        v1 = [h.velocity for h in p1.hits]
        v2 = [h.velocity for h in p2.hits]
        assert v1 != v2

    def test_humanize_false_same_every_time(self):
        p1 = generate_pattern(genre="organic house", bars=4, humanize=False)
        p2 = generate_pattern(genre="organic house", bars=4, humanize=False)
        assert p1.hits == p2.hits

    def test_energy_10_louder_than_energy_3(self):
        p_loud = generate_pattern(genre="organic house", bars=4, energy=10, humanize=False)
        p_soft = generate_pattern(genre="organic house", bars=4, energy=3, humanize=False)
        avg_loud = sum(h.velocity for h in p_loud.hits) / len(p_loud.hits)
        avg_soft = sum(h.velocity for h in p_soft.hits) / len(p_soft.hits)
        assert avg_loud > avg_soft

    def test_fill_activates_on_last_bar_of_phrase(self):
        """Bar 3 (last of 4-bar phrase) should have different hits than bar 2."""
        p = generate_pattern(genre="organic house", bars=4, energy=7, humanize=False, seed=0)
        bar2_kick = {h.step for h in p.hits if h.bar == 2 and h.instrument == "kick"}
        bar3_kick = {h.step for h in p.hits if h.bar == 3 and h.instrument == "kick"}
        # Fill pattern differs from base pattern in organic house
        assert bar2_kick != bar3_kick

    def test_kick_present_in_pattern(self):
        p = generate_pattern(genre="organic house", bars=4, seed=0)
        kick_hits = [h for h in p.hits if h.instrument == "kick"]
        assert len(kick_hits) > 0

    def test_hihat_present_in_pattern(self):
        p = generate_pattern(genre="organic house", bars=4, seed=0)
        hat_hits = [h for h in p.hits if h.instrument in ("hihat_c", "hihat_o")]
        assert len(hat_hits) > 0

    def test_hits_sorted_by_bar_then_step(self):
        p = generate_pattern(genre="organic house", bars=4, seed=0)
        keys = [(h.bar, h.step) for h in p.hits]
        assert keys == sorted(keys)

    def test_bars_invalid_raises(self):
        with pytest.raises(ValueError, match="bars"):
            generate_pattern(genre="organic house", bars=0)

    def test_energy_invalid_raises(self):
        with pytest.raises(ValueError, match="energy"):
            generate_pattern(genre="organic house", bars=4, energy=11)

    def test_energy_negative_raises(self):
        with pytest.raises(ValueError, match="energy"):
            generate_pattern(genre="organic house", bars=4, energy=-1)

    def test_invalid_genre_raises(self):
        with pytest.raises(ValueError, match="Unknown genre"):
            generate_pattern(genre="polka", bars=4)

    def test_all_5_genres_produce_patterns(self):
        from core.music_theory.harmony import available_genres

        for genre in available_genres():
            p = generate_pattern(genre=genre, bars=4, seed=0)
            assert len(p.hits) > 0, f"No hits for {genre}"
            assert p.genre == genre

    def test_afro_house_kick_not_pure_4otf(self):
        """Afro house kick is syncopated — should NOT hit all of steps 0,4,8,12."""
        p = generate_pattern(genre="afro house", bars=1, humanize=False, seed=0)
        kick_steps = {h.step for h in p.hits if h.bar == 0 and h.instrument == "kick"}
        # Afro house template does NOT have 4-on-the-floor (step 4 is absent in bar 0)
        assert 4 not in kick_steps

    def test_ghost_notes_added_when_humanize_energy_high(self):
        """With humanize=True and energy>=3, ghost hi-hats should occasionally appear."""
        # Use many bars to get statistical confidence
        p = generate_pattern(genre="organic house", bars=64, energy=8, humanize=True, seed=42)
        # Look for hihat_c hits on steps where base grid is 0 (odd steps)
        # Base grid: hihat_c hits only on even steps 0,2,4,...14
        # Ghost hits would be on odd steps
        ghost_steps = [h.step for h in p.hits if h.instrument == "hihat_c" and h.step % 2 == 1]
        assert len(ghost_steps) > 0, "Expected ghost hi-hat notes"

    def test_ghost_not_added_when_humanize_false(self):
        """humanize=False should produce no ghost notes on base-grid bars.

        Organic house base hihat_c is 8th notes (even steps only: 0,2,4,...14).
        Fill bars (every 4th) can have odd steps legitimately — exclude them.
        """
        p = generate_pattern(genre="organic house", bars=16, energy=8, humanize=False, seed=42)
        # every_n_bars=4: fill bars are 3, 7, 11, 15
        fill_bars = {3, 7, 11, 15}
        # On non-fill bars, hihat_c base grid only hits even steps
        odd_hihat_non_fill = [
            h
            for h in p.hits
            if h.instrument == "hihat_c" and h.step % 2 == 1 and h.bar not in fill_bars
        ]
        assert len(odd_hihat_non_fill) == 0
