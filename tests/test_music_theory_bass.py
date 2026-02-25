"""
Tests for core/music_theory/bass.py — bassline generator.

Validates:
    - _get_root_midi: correct MIDI pitch for note + octave
    - _select_bass_pattern: by style, fallback, missing patterns
    - generate_bassline: empty input, bar count, pitch range, velocity range,
      step range, determinism (seed), humanize=False, style selection,
      invalid genre, bars override, chord wrapping
"""

from __future__ import annotations

import pytest

from core.music_theory.bass import (
    _get_root_midi,
    _select_bass_pattern,
    generate_bassline,
)
from core.music_theory.scales import get_diatonic_chords
from core.music_theory.types import BassNote

# ---------------------------------------------------------------------------
# _get_root_midi
# ---------------------------------------------------------------------------


class TestGetRootMidi:
    def test_a2_is_45(self):
        # A2: (2+1)*12 + 9 = 36 + 9 = 45
        assert _get_root_midi("A", 2) == 45

    def test_c2_is_36(self):
        # C2: (2+1)*12 + 0 = 36
        assert _get_root_midi("C", 2) == 36

    def test_e2_is_40(self):
        # E2: (2+1)*12 + 4 = 40
        assert _get_root_midi("E", 2) == 40

    def test_octave_4_a_is_69(self):
        # A4 = MIDI 69
        assert _get_root_midi("A", 4) == 69

    def test_flat_note_resolved(self):
        # Bb = A# = pitch class 10; Bb2 = 36 + 10 = 46
        assert _get_root_midi("Bb", 2) == 46

    def test_sharp_note(self):
        # C#2: (3)*12 + 1 = 37
        assert _get_root_midi("C#", 2) == 37

    def test_low_octave_clamped(self):
        # Very low octave — still valid MIDI
        result = _get_root_midi("C", 0)
        assert 0 <= result <= 127

    def test_high_octave_clamped(self):
        # Very high note — clamped to 127
        result = _get_root_midi("B", 9)
        assert result <= 127


# ---------------------------------------------------------------------------
# _select_bass_pattern
# ---------------------------------------------------------------------------


class TestSelectBassPattern:
    def _make_template(self, styles: list[str]) -> dict:
        return {
            "genre": "test genre",
            "bass_patterns": [
                {"style": s, "base_octave": 2, "notes": [[0, 0, 4, 100]]} for s in styles
            ],
        }

    def test_finds_root_style(self):
        t = self._make_template(["root", "walk"])
        p = _select_bass_pattern(t, "root")
        assert p["style"] == "root"

    def test_finds_walk_style(self):
        t = self._make_template(["root", "walk"])
        p = _select_bass_pattern(t, "walk")
        assert p["style"] == "walk"

    def test_fallback_to_first_when_style_missing(self):
        t = self._make_template(["root", "walk"])
        p = _select_bass_pattern(t, "nonexistent")
        assert p["style"] == "root"

    def test_no_bass_patterns_raises(self):
        with pytest.raises(ValueError, match="bass_patterns"):
            _select_bass_pattern({"genre": "x", "bass_patterns": []}, "root")

    def test_missing_key_raises(self):
        with pytest.raises(ValueError, match="bass_patterns"):
            _select_bass_pattern({"genre": "x"}, "root")

    def test_single_pattern_always_returned(self):
        t = self._make_template(["walk"])
        p = _select_bass_pattern(t, "root")  # root not present → first
        assert p["style"] == "walk"


# ---------------------------------------------------------------------------
# generate_bassline
# ---------------------------------------------------------------------------


class TestGenerateBassline:
    def _am_chords(self, n: int = 4) -> list:
        return list(get_diatonic_chords("A", "natural minor"))[:n]

    def test_empty_chords_returns_empty_tuple(self):
        result = generate_bassline([], genre="organic house")
        assert result == ()

    def test_returns_tuple(self):
        result = generate_bassline(self._am_chords(), genre="organic house", seed=0)
        assert isinstance(result, tuple)

    def test_all_elements_are_bass_notes(self):
        result = generate_bassline(self._am_chords(), genre="organic house", seed=0)
        assert all(isinstance(n, BassNote) for n in result)

    def test_bar_count_matches_chords(self):
        chords = self._am_chords(4)
        result = generate_bassline(chords, genre="organic house", seed=0)
        bars_in_result = {n.bar for n in result}
        assert max(bars_in_result) == 3  # 0-indexed, 4 bars

    def test_bars_override(self):
        chords = self._am_chords(2)
        # Request 8 bars from 2-chord sequence (wrapping)
        result = generate_bassline(chords, genre="organic house", bars=8, seed=0)
        bars_in_result = {n.bar for n in result}
        assert max(bars_in_result) == 7

    def test_chord_wrapping(self):
        """bars > len(chords) → chords wrap via modulo."""
        chords = self._am_chords(2)
        result = generate_bassline(chords, genre="organic house", bars=4, seed=0)
        # Bar 2 uses chord 0, bar 3 uses chord 1
        bar0_pitches = {n.pitch_midi for n in result if n.bar == 0}
        bar2_pitches = {n.pitch_midi for n in result if n.bar == 2}
        assert bar0_pitches == bar2_pitches  # same chord, same pitches

    def test_pitch_midi_within_valid_range(self):
        result = generate_bassline(self._am_chords(), genre="organic house", seed=0)
        for n in result:
            assert 0 <= n.pitch_midi <= 127

    def test_step_within_valid_range(self):
        result = generate_bassline(self._am_chords(), genre="organic house", seed=0)
        for n in result:
            assert 0 <= n.step <= 15

    def test_velocity_within_valid_range(self):
        result = generate_bassline(self._am_chords(), genre="organic house", seed=0)
        for n in result:
            assert 1 <= n.velocity <= 127

    def test_duration_steps_within_valid_range(self):
        result = generate_bassline(self._am_chords(), genre="organic house", seed=0)
        for n in result:
            assert 1 <= n.duration_steps <= 16

    def test_bar_index_non_negative(self):
        result = generate_bassline(self._am_chords(), genre="organic house", seed=0)
        for n in result:
            assert n.bar >= 0

    def test_seed_produces_deterministic_output(self):
        chords = self._am_chords()
        r1 = generate_bassline(chords, genre="organic house", humanize=True, seed=42)
        r2 = generate_bassline(chords, genre="organic house", humanize=True, seed=42)
        assert r1 == r2

    def test_different_seeds_produce_different_velocities(self):
        chords = self._am_chords()
        r1 = generate_bassline(chords, genre="organic house", humanize=True, seed=1)
        r2 = generate_bassline(chords, genre="organic house", humanize=True, seed=999)
        velocities1 = [n.velocity for n in r1]
        velocities2 = [n.velocity for n in r2]
        assert velocities1 != velocities2  # with high probability

    def test_humanize_false_gives_consistent_velocity(self):
        chords = self._am_chords()
        r1 = generate_bassline(chords, genre="organic house", humanize=False)
        r2 = generate_bassline(chords, genre="organic house", humanize=False)
        velocities1 = [n.velocity for n in r1]
        velocities2 = [n.velocity for n in r2]
        assert velocities1 == velocities2

    def test_root_style_selected(self):
        """Root style returns notes — no assertion on specific pitches as
        genre wrapping handles transposition, but count must be non-zero."""
        chords = self._am_chords(1)
        result = generate_bassline(chords, genre="organic house", style="root", seed=0)
        assert len(result) > 0

    def test_walk_style_selected(self):
        chords = self._am_chords(1)
        result = generate_bassline(chords, genre="organic house", style="walk", seed=0)
        assert len(result) > 0

    def test_a_minor_root_in_bar0_is_a2(self):
        """Am chord: root = A, base_octave=2 → MIDI 45."""
        chords = self._am_chords(1)
        result = generate_bassline(
            chords, genre="organic house", style="root", humanize=False, seed=0
        )
        # Step 0 note should be A2 = 45 (semitone_offset=0 in root style)
        step0 = [n for n in result if n.step == 0 and n.bar == 0]
        assert len(step0) == 1
        assert step0[0].pitch_midi == 45

    def test_fifth_offset_correct(self):
        """Root A2=45, fifth offset=7 → MIDI 52 (E2)."""
        chords = self._am_chords(1)
        result = generate_bassline(
            chords, genre="organic house", style="root", humanize=False, seed=0
        )
        # Step 6 note has semitone_offset=7 in organic house root pattern
        step6 = [n for n in result if n.step == 6 and n.bar == 0]
        assert len(step6) == 1
        assert step6[0].pitch_midi == 45 + 7  # 52 = E2

    def test_invalid_genre_raises(self):
        chords = self._am_chords()
        with pytest.raises(ValueError, match="Unknown genre"):
            generate_bassline(chords, genre="bebop jazz")

    def test_all_5_genres_work(self):
        from core.music_theory.harmony import available_genres

        chords = self._am_chords(4)
        for genre in available_genres():
            result = generate_bassline(chords, genre=genre, seed=0)
            assert len(result) > 0, f"Empty bassline for {genre}"

    def test_notes_are_frozen(self):
        """BassNote is frozen — mutation raises TypeError."""
        chords = self._am_chords(1)
        result = generate_bassline(chords, genre="organic house", seed=0)
        with pytest.raises((TypeError, AttributeError)):
            result[0].pitch_midi = 99  # type: ignore[misc]

    def test_c_major_root_in_bar0_is_c2(self):
        """C major chord: root = C, base_octave=2 → MIDI 36."""
        chords = list(get_diatonic_chords("C", "major"))[:1]
        result = generate_bassline(
            chords, genre="organic house", style="root", humanize=False, seed=0
        )
        step0 = [n for n in result if n.step == 0 and n.bar == 0]
        assert step0[0].pitch_midi == 36  # C2
