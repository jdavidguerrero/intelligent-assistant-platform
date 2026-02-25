"""
Tests for core/music_theory/harmony.py — melody harmonization engine.

Validates:
    - _load_template: all 5 genre templates load and have required keys
    - available_genres: returns correct list
    - _overlap_score: pitch class counting
    - _segment_notes_by_bar: bar segmentation logic
    - melody_to_chords: full pipeline, error handling, voicing overrides
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from core.music_theory.harmony import (
    _extract_preferred_degrees,
    _load_template,
    _overlap_score,
    _segment_notes_by_bar,
    available_genres,
    melody_to_chords,
)
from core.music_theory.scales import get_diatonic_chords
from core.music_theory.types import VoicingResult

# ---------------------------------------------------------------------------
# Fake Note for testing (mirrors core.audio.types.Note interface)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FakeNote:
    pitch_midi: int
    onset_sec: float
    duration_sec: float = 0.5
    pitch_name: str = ""
    velocity: int = 80


# ---------------------------------------------------------------------------
# _load_template
# ---------------------------------------------------------------------------


class TestLoadTemplate:
    def test_all_five_genres_load(self):
        for genre in available_genres():
            template = _load_template(genre)
            assert isinstance(template, dict)

    def test_template_has_required_keys(self):
        t = _load_template("organic house")
        for key in ("genre", "voicing", "progressions"):
            assert key in t, f"Template missing key: {key}"

    def test_progressions_have_degrees_and_weight(self):
        t = _load_template("organic house")
        for prog in t["progressions"]:
            assert "degrees" in prog
            assert "weight" in prog
            assert isinstance(prog["degrees"], list)

    def test_unknown_genre_raises(self):
        with pytest.raises(ValueError, match="Unknown genre"):
            _load_template("jazz")

    def test_organic_house_voicing_is_extended(self):
        t = _load_template("organic house")
        assert t["voicing"] == "extended"

    def test_afro_house_voicing_is_triads(self):
        t = _load_template("afro house")
        assert t["voicing"] == "triads"

    def test_deep_house_default_mode_is_minor(self):
        t = _load_template("deep house")
        assert "natural minor" in t.get("default_mode", "natural minor")

    def test_caching_returns_same_object(self):
        t1 = _load_template("organic house")
        t2 = _load_template("organic house")
        assert t1 is t2  # lru_cache returns identical object


# ---------------------------------------------------------------------------
# available_genres
# ---------------------------------------------------------------------------


class TestAvailableGenres:
    def test_returns_list(self):
        assert isinstance(available_genres(), list)

    def test_contains_expected_genres(self):
        genres = available_genres()
        for expected in (
            "organic house",
            "deep house",
            "melodic techno",
            "progressive house",
            "afro house",
        ):
            assert expected in genres, f"{expected} not in available_genres()"

    def test_returns_5_genres(self):
        assert len(available_genres()) == 5


# ---------------------------------------------------------------------------
# _overlap_score
# ---------------------------------------------------------------------------


class TestOverlapScore:
    def test_full_overlap(self):
        # A minor chord has pitch classes {9, 0, 4} (A, C, E)
        chords = get_diatonic_chords("A", "natural minor")
        am = chords[0]  # degree 0 = Am
        melody_pcs = frozenset(p % 12 for p in am.midi_notes)
        score = _overlap_score(melody_pcs, am)
        assert score == len(melody_pcs)

    def test_no_overlap(self):
        chords = get_diatonic_chords("C", "major")
        c_major = chords[0]  # C E G
        # F# is not in C major chord
        score = _overlap_score(frozenset({6}), c_major)
        assert score == 0

    def test_partial_overlap(self):
        chords = get_diatonic_chords("A", "natural minor")
        am = chords[0]  # A C E
        # A (9) is in Am, F# is not
        score = _overlap_score(frozenset({9, 6}), am)
        assert score == 1

    def test_empty_melody_returns_zero(self):
        chords = get_diatonic_chords("A", "natural minor")
        score = _overlap_score(frozenset(), chords[0])
        assert score == 0


# ---------------------------------------------------------------------------
# _segment_notes_by_bar
# ---------------------------------------------------------------------------


class TestSegmentNotesByBar:
    def test_single_bar(self):
        notes = [_FakeNote(pitch_midi=69, onset_sec=0.0)]  # A4
        segments = _segment_notes_by_bar(notes, bars=1, total_duration_sec=4.0)
        assert len(segments) == 1
        assert 9 in segments[0]  # A = pitch class 9

    def test_two_bars_split_evenly(self):
        # Bar 0: A (onset 0.0), Bar 1: C (onset 2.0)
        notes = [
            _FakeNote(pitch_midi=69, onset_sec=0.0),  # A = pc 9
            _FakeNote(pitch_midi=60, onset_sec=2.0),  # C = pc 0
        ]
        segments = _segment_notes_by_bar(notes, bars=2, total_duration_sec=4.0)
        assert 9 in segments[0]  # A in bar 0
        assert 0 in segments[1]  # C in bar 1

    def test_empty_notes_returns_empty_frozensets(self):
        segments = _segment_notes_by_bar([], bars=4, total_duration_sec=8.0)
        assert len(segments) == 4
        for seg in segments:
            assert isinstance(seg, frozenset)
            assert len(seg) == 0

    def test_note_at_bar_boundary_goes_to_later_bar(self):
        # Bar duration = 2.0s. Onset at exactly 2.0 goes to bar 1.
        notes = [_FakeNote(pitch_midi=60, onset_sec=2.0)]
        segments = _segment_notes_by_bar(notes, bars=2, total_duration_sec=4.0)
        assert 0 in segments[1]  # C in bar 1

    def test_multiple_notes_same_bar(self):
        notes = [
            _FakeNote(pitch_midi=69, onset_sec=0.1),  # A
            _FakeNote(pitch_midi=72, onset_sec=0.5),  # C (up octave)
            _FakeNote(pitch_midi=76, onset_sec=0.9),  # E
        ]
        segments = _segment_notes_by_bar(notes, bars=1, total_duration_sec=2.0)
        # All 3 notes should be in bar 0
        assert len(segments[0]) == 3  # A, C, E = pcs 9, 0, 4

    def test_pitch_classes_are_mod12(self):
        # MIDI 81 = A5 = pitch class 9 (same as A4=69)
        notes = [_FakeNote(pitch_midi=81, onset_sec=0.0)]
        segments = _segment_notes_by_bar(notes, bars=1, total_duration_sec=2.0)
        assert 9 in segments[0]  # pc 9, not 81


# ---------------------------------------------------------------------------
# melody_to_chords
# ---------------------------------------------------------------------------


class TestMelodyToChords:
    def test_returns_voicing_result(self):
        result = melody_to_chords([], key_root="A")
        assert isinstance(result, VoicingResult)

    def test_empty_notes_returns_tonic_chords(self):
        """Empty melody → all chords fall back to tonic."""
        result = melody_to_chords([], key_root="A", bars=4)
        assert all(c.degree == 0 for c in result.chords)

    def test_bars_count_matches_output_chords(self):
        notes = [_FakeNote(pitch_midi=69, onset_sec=float(i)) for i in range(8)]
        result = melody_to_chords(notes, key_root="A", bars=8, total_duration_sec=16.0)
        assert len(result.chords) == 8

    def test_key_root_preserved_in_result(self):
        result = melody_to_chords([], key_root="C")
        assert result.key_root == "C"

    def test_genre_preserved_in_result(self):
        result = melody_to_chords([], key_root="A", genre="deep house")
        assert result.genre == "deep house"

    def test_key_mode_preserved_in_result(self):
        result = melody_to_chords([], key_root="A", key_mode="dorian", genre="afro house")
        assert result.key_mode == "dorian"

    def test_roman_labels_match_chords(self):
        result = melody_to_chords([], key_root="A", bars=4)
        assert result.roman_labels == tuple(c.roman for c in result.chords)

    def test_all_chords_are_diatonic(self):
        """All returned chords must be from the diatonic set."""
        notes = [
            _FakeNote(pitch_midi=69, onset_sec=0.0),
            _FakeNote(pitch_midi=72, onset_sec=2.0),
        ]
        result = melody_to_chords(notes, key_root="A", bars=4, total_duration_sec=8.0)
        diatonic = get_diatonic_chords("A", "natural minor", voicing="extended")
        diatonic_degrees = {c.degree for c in diatonic}
        for chord in result.chords:
            assert chord.degree in diatonic_degrees

    def test_voicing_override_applied(self):
        """Passing voicing='triads' overrides genre template default."""
        result = melody_to_chords([], key_root="A", genre="organic house", voicing="triads")
        # organic house default = extended; override to triads
        for chord in result.chords:
            assert chord.quality in ("minor", "major", "dim", "aug")

    def test_invalid_genre_raises(self):
        with pytest.raises(ValueError, match="Unknown genre"):
            melody_to_chords([], key_root="A", genre="jazz fusion")

    def test_invalid_bars_raises(self):
        with pytest.raises(ValueError, match="bars"):
            melody_to_chords([], key_root="A", bars=0)

    def test_chord_names_are_non_empty_strings(self):
        result = melody_to_chords([], key_root="C", genre="deep house", bars=4)
        for name in result.chord_names:
            assert isinstance(name, str)
            assert len(name) > 0

    def test_a_minor_melody_harmonizes_to_a_minor_chord(self):
        """Notes A C E in bar 0 → Am chord."""
        # A=69, C=72, E=76 — all in Am
        notes = [
            _FakeNote(pitch_midi=69, onset_sec=0.0),
            _FakeNote(pitch_midi=72, onset_sec=0.5),
            _FakeNote(pitch_midi=76, onset_sec=1.0),
        ]
        result = melody_to_chords(notes, key_root="A", bars=1, total_duration_sec=2.0)
        # The chord should have degree 0 (Am) with highest overlap
        assert result.chords[0].degree == 0

    def test_all_genres_work(self):
        for genre in available_genres():
            result = melody_to_chords([], key_root="A", genre=genre, bars=4)
            assert len(result.chords) == 4

    def test_total_duration_inferred_from_notes(self):
        """total_duration_sec=None → inferred from last note offset."""
        notes = [_FakeNote(pitch_midi=69, onset_sec=7.0, duration_sec=1.0)]
        # Last note ends at 8.0 → 4 bars of 2 sec each
        result = melody_to_chords(notes, key_root="A", bars=4)
        assert len(result.chords) == 4

    def test_flat_key_root_supported(self):
        result = melody_to_chords([], key_root="Bb", genre="deep house", bars=4)
        assert result.key_root == "Bb"


# ---------------------------------------------------------------------------
# _extract_preferred_degrees
# ---------------------------------------------------------------------------


class TestExtractPreferredDegrees:
    def test_returns_list_of_ints(self):
        template = _load_template("organic house")
        degrees = _extract_preferred_degrees(template)
        assert isinstance(degrees, list)
        assert all(isinstance(d, int) for d in degrees)

    def test_no_progressions_returns_all_degrees(self):
        template = {"progressions": []}
        degrees = _extract_preferred_degrees(template)
        assert sorted(degrees) == list(range(7))

    def test_weighted_degree_appears_first(self):
        """Degree with highest weight × inverse_position score ranks first."""
        template = {
            "progressions": [
                {"degrees": [0, 5, 2, 6], "weight": 4},  # 0 appears first
                {"degrees": [1, 0, 3], "weight": 1},
            ]
        }
        degrees = _extract_preferred_degrees(template)
        # Degree 0 has score 4×1 + 1×0.5 = 4.5 — should rank first
        assert degrees[0] == 0
