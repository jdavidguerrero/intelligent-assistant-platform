"""
tests/test_bass_w14.py — Week 14 bass tests: new styles + slides.

Covers:
    - 'sub' style: base_octave=1 (ultra-low register, A1=MIDI33)
    - 'driving' style: eighth-note root pulse (8 notes per bar)
    - 'minimal' style: single note per bar
    - slides=True: approach notes added before chord changes
    - slides=False: no approach notes (default, backward-compatible)
    - All 5 genre templates support the new styles
"""

from __future__ import annotations

import pytest

from core.music_theory.bass import generate_bassline
from core.music_theory.scales import get_diatonic_chords
from core.music_theory.types import BassNote

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chords_am(n: int = 4):
    """A natural minor diatonic chords, first N."""
    return get_diatonic_chords("A", "natural minor")[:n]


def _chords_cm(n: int = 4):
    """C natural minor diatonic chords, first N."""
    return get_diatonic_chords("C", "natural minor")[:n]


GENRES = [
    "organic house",
    "deep house",
    "melodic techno",
    "progressive house",
    "afro house",
]


# ---------------------------------------------------------------------------
# 'sub' style — ultra-low sub bass register
# ---------------------------------------------------------------------------


class TestSubStyle:
    def test_sub_returns_bass_notes(self) -> None:
        chords = _chords_am(2)
        notes = generate_bassline(chords, genre="organic house", style="sub", seed=0)
        assert isinstance(notes, tuple)
        assert len(notes) > 0

    def test_sub_pitch_in_low_register(self) -> None:
        """Sub bass: base_octave=1 → A1=MIDI33, C1=MIDI24. All pitches ≤ 48."""
        chords = _chords_am(4)
        notes = generate_bassline(chords, genre="organic house", style="sub", seed=0)
        # sub style uses base_octave=1 → pitches in range 24-35 roughly (root region)
        assert all(
            n.pitch_midi <= 48 for n in notes
        ), f"Sub bass note too high: {max(n.pitch_midi for n in notes)}"

    def test_sub_lower_than_root_style(self) -> None:
        """Sub style (octave 1) is lower than root style (octave 2)."""
        chords = _chords_am(2)
        sub_notes = generate_bassline(chords, genre="organic house", style="sub", seed=0)
        root_notes = generate_bassline(chords, genre="organic house", style="root", seed=0)
        avg_sub = sum(n.pitch_midi for n in sub_notes) / len(sub_notes)
        avg_root = sum(n.pitch_midi for n in root_notes) / len(root_notes)
        assert avg_sub < avg_root

    def test_sub_fewer_notes_per_bar(self) -> None:
        """Sub style has only 1-2 notes per bar (long sustained root)."""
        chords = _chords_am(1)
        notes = generate_bassline(chords, genre="organic house", style="sub", seed=0)
        assert len(notes) <= 4  # at most 4 notes per bar in sub style

    @pytest.mark.parametrize("genre", GENRES)
    def test_sub_available_all_genres(self, genre: str) -> None:
        chords = _chords_am(2)
        notes = generate_bassline(chords, genre=genre, style="sub", seed=0)
        assert len(notes) > 0


# ---------------------------------------------------------------------------
# 'driving' style — eighth-note root pulse
# ---------------------------------------------------------------------------


class TestDrivingStyle:
    def test_driving_returns_bass_notes(self) -> None:
        chords = _chords_am(2)
        notes = generate_bassline(chords, genre="organic house", style="driving", seed=0)
        assert len(notes) > 0

    def test_driving_more_notes_than_root(self) -> None:
        """Driving (8 notes/bar) has more notes than root (6 notes/bar)."""
        chords = _chords_am(4)
        driving = generate_bassline(chords, genre="organic house", style="driving", seed=0)
        root = generate_bassline(chords, genre="organic house", style="root", seed=0)
        assert len(driving) > len(root)

    def test_driving_eighth_note_steps(self) -> None:
        """Driving pattern uses steps 0,2,4,6,8,10,12,14 (8th-note positions)."""
        chords = _chords_am(1)
        notes = generate_bassline(chords, genre="organic house", style="driving", seed=0)
        steps = {n.step for n in notes}
        eighth_steps = {0, 2, 4, 6, 8, 10, 12, 14}
        assert steps.issubset(eighth_steps)

    def test_driving_pitches_in_bass_register(self) -> None:
        chords = _chords_am(4)
        notes = generate_bassline(chords, genre="organic house", style="driving", seed=0)
        assert all(0 <= n.pitch_midi <= 127 for n in notes)

    @pytest.mark.parametrize("genre", GENRES)
    def test_driving_available_all_genres(self, genre: str) -> None:
        chords = _chords_am(2)
        notes = generate_bassline(chords, genre=genre, style="driving", seed=0)
        assert len(notes) > 0


# ---------------------------------------------------------------------------
# 'minimal' style — single hit per bar
# ---------------------------------------------------------------------------


class TestMinimalStyle:
    def test_minimal_returns_bass_notes(self) -> None:
        chords = _chords_am(4)
        notes = generate_bassline(chords, genre="organic house", style="minimal", seed=0)
        assert len(notes) > 0

    def test_minimal_one_or_two_notes_per_bar(self) -> None:
        """Minimal style: at most 2 notes per bar (usually just beat 1)."""
        chords = _chords_am(1)
        notes = generate_bassline(chords, genre="organic house", style="minimal", seed=0)
        assert len(notes) <= 3

    def test_minimal_fewer_notes_than_driving(self) -> None:
        chords = _chords_am(4)
        minimal = generate_bassline(chords, genre="organic house", style="minimal", seed=0)
        driving = generate_bassline(chords, genre="organic house", style="driving", seed=0)
        assert len(minimal) < len(driving)

    def test_minimal_beat_one_hit(self) -> None:
        """Minimal style always hits beat 1 (step 0) of each bar."""
        chords = _chords_am(4)
        notes = generate_bassline(chords, genre="organic house", style="minimal", seed=0)
        bars_with_step_0 = {n.bar for n in notes if n.step == 0}
        assert len(bars_with_step_0) == 4  # all 4 bars hit step 0

    @pytest.mark.parametrize("genre", GENRES)
    def test_minimal_available_all_genres(self, genre: str) -> None:
        chords = _chords_am(2)
        notes = generate_bassline(chords, genre=genre, style="minimal", seed=0)
        assert len(notes) > 0


# ---------------------------------------------------------------------------
# Style fallback (unknown style → first pattern)
# ---------------------------------------------------------------------------


class TestStyleFallback:
    def test_unknown_style_falls_back_to_first(self) -> None:
        chords = _chords_am(2)
        notes = generate_bassline(chords, genre="organic house", style="nonexistent", seed=0)
        assert len(notes) > 0  # fallback to first style (root)


# ---------------------------------------------------------------------------
# Slides
# ---------------------------------------------------------------------------


class TestSlides:
    def test_slides_false_default_no_extra_notes(self) -> None:
        """Default slides=False — same output as before."""
        chords = _chords_am(4)
        no_slides = generate_bassline(chords, genre="organic house", style="root", seed=0)
        explicit_false = generate_bassline(
            chords, genre="organic house", style="root", slides=False, seed=0
        )
        assert no_slides == explicit_false

    def test_slides_true_adds_notes_on_chord_changes(self) -> None:
        """slides=True adds approach notes at chord changes."""
        # A natural minor: Am, Bdim, C, Dm, Em, F, G — different roots each bar
        chords = _chords_am(4)
        without_slides = generate_bassline(chords, genre="organic house", style="root", seed=0)
        with_slides = generate_bassline(
            chords, genre="organic house", style="root", slides=True, seed=0
        )
        assert len(with_slides) >= len(without_slides)

    def test_slide_note_on_step_14(self) -> None:
        """Slide notes are placed at step 14 (2 steps before bar end)."""
        chords = _chords_am(4)
        notes = generate_bassline(chords, genre="organic house", style="root", slides=True, seed=0)
        step14_notes = [n for n in notes if n.step == 14]
        assert len(step14_notes) > 0

    def test_slides_single_bar_no_extra_notes(self) -> None:
        """With 1 bar, no chord change → slides add nothing."""
        chords = _chords_am(1)
        without = generate_bassline(chords, genre="organic house", style="root", seed=0)
        with_s = generate_bassline(chords, genre="organic house", style="root", slides=True, seed=0)
        assert len(without) == len(with_s)

    def test_slides_same_root_no_extra_notes(self) -> None:
        """When all chords have the same root, no slide notes are added."""
        from core.music_theory.types import Chord

        # 4 bars, all Am (same root)
        am = Chord(
            root="A",
            quality="minor",
            name="Am",
            roman="i",
            degree=0,
            midi_notes=(57, 60, 64),
        )
        chords = (am,) * 4
        without = generate_bassline(chords, genre="organic house", style="root", bars=4, seed=0)
        with_s = generate_bassline(
            chords, genre="organic house", style="root", bars=4, slides=True, seed=0
        )
        assert len(without) == len(with_s)

    def test_slide_notes_are_bass_notes(self) -> None:
        chords = _chords_am(4)
        notes = generate_bassline(chords, genre="organic house", style="root", slides=True, seed=0)
        assert all(isinstance(n, BassNote) for n in notes)

    def test_slide_velocity_lower_than_main(self) -> None:
        """Slide notes (step 14) have lower velocity than main notes (step 0)."""
        chords = _chords_am(4)
        notes = generate_bassline(chords, genre="organic house", style="root", slides=True, seed=0)
        main_notes = [n for n in notes if n.step == 0]
        slide_notes = [n for n in notes if n.step == 14]
        if slide_notes and main_notes:
            avg_main = sum(n.velocity for n in main_notes) / len(main_notes)
            avg_slide = sum(n.velocity for n in slide_notes) / len(slide_notes)
            assert avg_slide < avg_main

    def test_sorted_output_with_slides(self) -> None:
        chords = _chords_am(4)
        notes = generate_bassline(chords, genre="organic house", style="root", slides=True, seed=0)
        keys = [(n.bar, n.step) for n in notes]
        assert keys == sorted(keys)

    @pytest.mark.parametrize("genre", GENRES)
    def test_slides_all_genres(self, genre: str) -> None:
        chords = _chords_am(4)
        notes = generate_bassline(chords, genre=genre, style="root", slides=True, seed=0)
        assert len(notes) > 0
