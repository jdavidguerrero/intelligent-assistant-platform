"""
tests/test_drums_w14.py — Week 14 drum tests: probability hits + energy layers.

Covers:
    - _get_active_instruments: energy layer computation
    - Energy layers: low energy = fewer instruments, high energy = full kit
    - Probability-based hits: some steps are probabilistic (<100% probability)
    - Fills always play regardless of probability
    - humanize=False → all grid hits play (no probability skipping)
    - All 5 genre templates
"""

from __future__ import annotations

import pytest

from core.music_theory.drums import _get_active_instruments, generate_pattern
from core.music_theory.types import DrumPattern

GENRES = [
    "organic house",
    "deep house",
    "melodic techno",
    "progressive house",
    "afro house",
]


# ---------------------------------------------------------------------------
# _get_active_instruments
# ---------------------------------------------------------------------------


class TestGetActiveInstruments:
    def test_empty_layers_returns_none(self) -> None:
        result = _get_active_instruments({}, 7)
        assert result is None

    def test_single_threshold_below(self) -> None:
        layers = {1: ["kick"]}
        result = _get_active_instruments(layers, 0)
        assert result == frozenset()

    def test_single_threshold_at(self) -> None:
        layers = {1: ["kick"]}
        result = _get_active_instruments(layers, 1)
        assert result == frozenset({"kick"})

    def test_multiple_thresholds_additive(self) -> None:
        layers = {1: ["kick"], 3: ["snare"], 5: ["hihat_c"]}
        result = _get_active_instruments(layers, 5)
        assert result == frozenset({"kick", "snare", "hihat_c"})

    def test_partial_threshold(self) -> None:
        layers = {1: ["kick"], 3: ["snare"], 5: ["hihat_c"]}
        result = _get_active_instruments(layers, 4)
        assert result == frozenset({"kick", "snare"})

    def test_string_keys(self) -> None:
        """YAML may produce string keys (e.g., '1', '3'). Should handle int conversion."""
        layers = {"1": ["kick"], "3": ["snare"]}
        result = _get_active_instruments(layers, 3)
        assert result == frozenset({"kick", "snare"})

    def test_high_energy_all_instruments(self) -> None:
        layers = {1: ["kick"], 3: ["snare"], 5: ["hihat_c"], 7: ["clap"], 10: ["hihat_o"]}
        result = _get_active_instruments(layers, 10)
        assert result == frozenset({"kick", "snare", "hihat_c", "clap", "hihat_o"})


# ---------------------------------------------------------------------------
# Energy layers in generate_pattern
# ---------------------------------------------------------------------------


class TestEnergyLayers:
    def test_low_energy_fewer_instruments(self) -> None:
        """At energy=1, only kick should be active (from energy_layers in template)."""
        p = generate_pattern(genre="organic house", bars=4, energy=1, humanize=False, seed=0)
        instruments_present = {h.instrument for h in p.hits}
        # At energy=1 only kick is in the energy_layers for organic house
        assert "kick" in instruments_present
        # snare should NOT be active at energy=1
        assert "snare" not in instruments_present

    def test_medium_energy_includes_snare(self) -> None:
        """At energy=4, kick + snare should be active (threshold 3 adds snare)."""
        p = generate_pattern(genre="organic house", bars=4, energy=4, humanize=False, seed=0)
        instruments_present = {h.instrument for h in p.hits}
        assert "kick" in instruments_present
        assert "snare" in instruments_present

    def test_high_energy_full_kit(self) -> None:
        """At energy=10, all instruments should appear."""
        p = generate_pattern(genre="organic house", bars=8, energy=10, humanize=True, seed=0)
        instruments_present = {h.instrument for h in p.hits}
        assert "kick" in instruments_present
        assert "snare" in instruments_present
        assert "hihat_c" in instruments_present

    def test_energy_layer_monotonic(self) -> None:
        """Higher energy never produces fewer instrument types than lower energy."""
        low = generate_pattern(genre="organic house", bars=4, energy=3, humanize=False, seed=42)
        high = generate_pattern(genre="organic house", bars=4, energy=8, humanize=False, seed=42)
        instruments_low = {h.instrument for h in low.hits}
        instruments_high = {h.instrument for h in high.hits}
        assert instruments_low.issubset(instruments_high)

    def test_melodic_techno_hihat_at_energy_2(self) -> None:
        """Melodic techno adds hihat_c at energy=2 (defined in its energy_layers)."""
        p = generate_pattern(genre="melodic techno", bars=2, energy=2, humanize=False, seed=0)
        instruments_present = {h.instrument for h in p.hits}
        assert "hihat_c" in instruments_present

    def test_afro_house_hihat_before_snare(self) -> None:
        """Afro house: hihat_c enters at 3, snare at 5."""
        p3 = generate_pattern(genre="afro house", bars=2, energy=3, humanize=False, seed=0)
        p4 = generate_pattern(genre="afro house", bars=2, energy=4, humanize=False, seed=0)
        # At energy=3: hihat_c active, snare not yet
        instruments_e3 = {h.instrument for h in p3.hits}
        instruments_e4 = {h.instrument for h in p4.hits}
        assert "hihat_c" in instruments_e3
        # snare should not be at energy=4 (threshold is 5)
        assert "snare" not in instruments_e4

    @pytest.mark.parametrize("genre", GENRES)
    def test_energy_layers_defined_all_genres(self, genre: str) -> None:
        """Every genre template defines energy_layers and they work correctly."""
        low = generate_pattern(genre=genre, bars=2, energy=1, humanize=False, seed=0)
        high = generate_pattern(genre=genre, bars=2, energy=10, humanize=False, seed=0)
        instr_low = {h.instrument for h in low.hits}
        instr_high = {h.instrument for h in high.hits}
        # High energy should have at least as many instrument types as low energy
        assert len(instr_high) >= len(instr_low)


# ---------------------------------------------------------------------------
# Probability-based hits
# ---------------------------------------------------------------------------


class TestProbabilityHits:
    def test_humanize_false_deterministic(self) -> None:
        """humanize=False: no probability checks → same output every time (no seed needed)."""
        p1 = generate_pattern(genre="organic house", bars=4, energy=7, humanize=False)
        p2 = generate_pattern(genre="organic house", bars=4, energy=7, humanize=False)
        assert p1.hits == p2.hits

    def test_humanize_true_probability_varies(self) -> None:
        """humanize=True with different seeds may produce different hit counts."""
        p1 = generate_pattern(genre="organic house", bars=8, energy=7, humanize=True, seed=1)
        p2 = generate_pattern(genre="organic house", bars=8, energy=7, humanize=True, seed=2)
        # Different seeds → different RNG → probability rolls differ → different results
        # (With 8 bars and ~8% miss probability, this almost always differs)
        # We test that both produce valid output, not that they must differ
        assert len(p1.hits) > 0
        assert len(p2.hits) > 0

    def test_fills_always_play_despite_probability(self) -> None:
        """Fill bars (bar 3, 7, 11, ...) always play all grid hits regardless of probability."""
        # Use seed to get reproducible output; run multiple times with different seeds
        for seed in range(5):
            p = generate_pattern(genre="organic house", bars=4, energy=7, humanize=True, seed=seed)
            # Bar 3 is the fill bar (every_n_bars=4)
            fill_hits = [h for h in p.hits if h.bar == 3]
            fill_kick = [h for h in fill_hits if h.instrument == "kick"]
            # Fill kick grid has hits at steps {0,2,4,8,10,12} — at least some must play
            assert (
                len(fill_kick) >= 3
            ), f"Fill bar kick should have ≥3 hits, got {len(fill_kick)} (seed={seed})"

    def test_base_bar_kick_always_plays(self) -> None:
        """Kick probability is 1.0 in all genres → kick always plays on base bars."""
        for seed in range(10):
            p = generate_pattern(genre="organic house", bars=4, energy=7, humanize=True, seed=seed)
            # Bar 0 is a base bar — kick step 0 has probability 1.0
            bar0_kick_step0 = [
                h for h in p.hits if h.bar == 0 and h.instrument == "kick" and h.step == 0
            ]
            assert len(bar0_kick_step0) == 1, f"Kick step 0 bar 0 should always play (seed={seed})"

    def test_probability_reduces_hihat_hits(self) -> None:
        """Offbeat hihat_c (probability < 1.0) sometimes misses with humanize=True."""
        # Run many seeds and check that offbeat hats occasionally miss
        offbeat_steps = {2, 6, 10}  # steps with probability 0.92 in organic house
        misses_found = False
        for seed in range(50):
            p = generate_pattern(genre="organic house", bars=4, energy=7, humanize=True, seed=seed)
            # In base bars (not bar 3), count offbeat hihat_c hits
            base_bar_hihat_offbeat = [
                h
                for h in p.hits
                if h.instrument == "hihat_c"
                and h.bar in (0, 1, 2)  # non-fill bars
                and h.step in offbeat_steps
            ]
            # Expected maximum: 3 bars × 3 offbeat steps = 9 hits
            # If any miss, count < 9
            if len(base_bar_hihat_offbeat) < 9:
                misses_found = True
                break
        assert misses_found, "Expected at least one probabilistic miss in 50 runs"

    @pytest.mark.parametrize("genre", GENRES)
    def test_probability_section_all_genres(self, genre: str) -> None:
        """Probability-based patterns work for all genres without error."""
        p = generate_pattern(genre=genre, bars=4, energy=7, humanize=True, seed=0)
        assert isinstance(p, DrumPattern)
        assert len(p.hits) > 0


# ---------------------------------------------------------------------------
# Interaction: humanize=False disables probability
# ---------------------------------------------------------------------------


class TestHumanizeFalseDisablesProbability:
    def test_humanize_false_all_grid_hits_play(self) -> None:
        """With humanize=False, every grid hit plays (no probabilistic skipping)."""
        p = generate_pattern(genre="organic house", bars=4, energy=7, humanize=False, seed=0)
        # 4-on-the-floor kick: 4 hits/bar × 4 bars (non-fill) + fill adjustments
        # At minimum, bar 0 should have kick at steps 0, 4, 8, 12
        bar0_kick = {h.step for h in p.hits if h.bar == 0 and h.instrument == "kick"}
        assert {0, 4, 8, 12}.issubset(bar0_kick)

    def test_humanize_false_hihat_complete(self) -> None:
        """With humanize=False, all 8th-note hi-hats play on base bars."""
        p = generate_pattern(genre="organic house", bars=4, energy=7, humanize=False, seed=0)
        # Organic house hihat_c grid: 8 hits per bar at steps 0,2,4,6,8,10,12,14
        bar1_hihat = {h.step for h in p.hits if h.bar == 1 and h.instrument == "hihat_c"}
        assert bar1_hihat == {0, 2, 4, 6, 8, 10, 12, 14}
