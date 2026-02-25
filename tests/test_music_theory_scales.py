"""
Tests for core/music_theory/scales.py — pure scale and diatonic chord functions.

Validates:
    - normalize_note, note_to_pitch_class, pitch_class_to_note
    - get_scale_notes: correct notes for all major/minor keys
    - get_pitch_classes: correct frozensets
    - get_diatonic_chords: correct names, qualities, roman numerals
    - build_chord_midi: correct MIDI pitches, octave anchoring
    - Error handling: bad root, bad mode, bad voicing
"""

import pytest

from core.music_theory.scales import (
    CHORD_INTERVALS,
    DIATONIC_QUALITIES,
    NOTE_NAMES,
    ROMAN_NUMERALS,
    SCALE_FORMULAS,
    build_chord_midi,
    get_diatonic_chords,
    get_pitch_classes,
    get_scale_notes,
    normalize_note,
    note_to_pitch_class,
    pitch_class_to_note,
)
from core.music_theory.types import Chord

# ---------------------------------------------------------------------------
# normalize_note
# ---------------------------------------------------------------------------


class TestNormalizeNote:
    def test_lowercase_becomes_capitalized(self):
        assert normalize_note("a") == "A"
        assert normalize_note("c#") == "C#"

    def test_flat_converts_to_sharp(self):
        assert normalize_note("Bb") == "A#"
        assert normalize_note("Eb") == "D#"
        assert normalize_note("Ab") == "G#"
        assert normalize_note("Db") == "C#"
        assert normalize_note("Gb") == "F#"

    def test_sharp_returns_unchanged(self):
        assert normalize_note("C#") == "C#"
        assert normalize_note("F#") == "F#"

    def test_natural_notes(self):
        for note in ("C", "D", "E", "F", "G", "A", "B"):
            assert normalize_note(note) == note

    def test_unknown_note_raises(self):
        with pytest.raises(ValueError, match="Unknown note"):
            normalize_note("H")
        with pytest.raises(ValueError, match="Unknown note"):
            normalize_note("X#")


# ---------------------------------------------------------------------------
# note_to_pitch_class / pitch_class_to_note
# ---------------------------------------------------------------------------


class TestPitchClassConversions:
    def test_c_is_0(self):
        assert note_to_pitch_class("C") == 0

    def test_a_is_9(self):
        assert note_to_pitch_class("A") == 9

    def test_flat_converts_before_lookup(self):
        assert note_to_pitch_class("Bb") == note_to_pitch_class("A#")

    def test_pitch_class_to_note_round_trip(self):
        for pc in range(12):
            note = pitch_class_to_note(pc)
            assert note_to_pitch_class(note) == pc

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError):
            pitch_class_to_note(-1)
        with pytest.raises(ValueError):
            pitch_class_to_note(12)


# ---------------------------------------------------------------------------
# get_scale_notes
# ---------------------------------------------------------------------------


class TestGetScaleNotes:
    def test_a_natural_minor(self):
        notes = get_scale_notes("A", "natural minor")
        assert notes == ("A", "B", "C", "D", "E", "F", "G")

    def test_c_major(self):
        notes = get_scale_notes("C", "major")
        assert notes == ("C", "D", "E", "F", "G", "A", "B")

    def test_d_dorian(self):
        notes = get_scale_notes("D", "dorian")
        # D dorian = D E F G A B C
        assert notes[0] == "D"
        assert len(notes) == 7

    def test_flat_root_normalized(self):
        # Bb = A# — same notes regardless of spelling
        notes_bb = get_scale_notes("Bb", "natural minor")
        notes_as = get_scale_notes("A#", "natural minor")
        assert notes_bb == notes_as

    def test_returns_7_notes_for_diatonic(self):
        for mode in ("major", "natural minor", "dorian", "harmonic minor"):
            notes = get_scale_notes("C", mode)
            assert len(notes) == 7, f"Expected 7 notes for {mode}, got {len(notes)}"

    def test_returns_5_notes_for_pentatonic(self):
        notes = get_scale_notes("A", "pentatonic minor")
        assert len(notes) == 5

    def test_all_notes_are_valid_pitch_names(self):
        notes = get_scale_notes("F#", "major")
        for n in notes:
            assert n in NOTE_NAMES, f"{n} not in NOTE_NAMES"

    def test_unknown_root_raises(self):
        with pytest.raises(ValueError):
            get_scale_notes("X", "major")

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError):
            get_scale_notes("C", "japanese")

    def test_known_major_keys(self):
        """Spot-check well-known major scales."""
        g_major = get_scale_notes("G", "major")
        assert "F#" in g_major  # G major has F#

        f_major = get_scale_notes("F", "major")
        assert "A#" in f_major  # F major has Bb (stored as A#)


# ---------------------------------------------------------------------------
# get_pitch_classes
# ---------------------------------------------------------------------------


class TestGetPitchClasses:
    def test_c_major_pitch_classes(self):
        pcs = get_pitch_classes("C", "major")
        # C=0 D=2 E=4 F=5 G=7 A=9 B=11
        assert pcs == frozenset({0, 2, 4, 5, 7, 9, 11})

    def test_a_natural_minor_pitch_classes(self):
        pcs = get_pitch_classes("A", "natural minor")
        # A=9 B=11 C=0 D=2 E=4 F=5 G=7 — same pitch classes as C major
        assert pcs == frozenset({9, 11, 0, 2, 4, 5, 7})

    def test_returns_frozenset(self):
        pcs = get_pitch_classes("D", "dorian")
        assert isinstance(pcs, frozenset)

    def test_no_duplicate_pitch_classes(self):
        pcs = get_pitch_classes("G", "major")
        notes = get_scale_notes("G", "major")
        # frozenset deduplication — length should match if no accidental collision
        assert len(pcs) == len(notes)

    def test_all_values_in_range(self):
        pcs = get_pitch_classes("F#", "natural minor")
        for pc in pcs:
            assert 0 <= pc <= 11


# ---------------------------------------------------------------------------
# build_chord_midi
# ---------------------------------------------------------------------------


class TestBuildChordMidi:
    def test_a_minor_triad_default_octave(self):
        # A4 = MIDI 69, A minor = A C E = 69, 72, 76
        midi = build_chord_midi("A", "minor", octave=4)
        assert midi == (69, 72, 76)

    def test_c_major_triad(self):
        # C4 = 60, major = 0, 4, 7 → 60, 64, 67
        midi = build_chord_midi("C", "major", octave=4)
        assert midi == (60, 64, 67)

    def test_f_maj7_octave4(self):
        # F4 = 65, maj7 = 0, 4, 7, 11 → 65, 69, 72, 76
        midi = build_chord_midi("F", "maj7", octave=4)
        assert midi == (65, 69, 72, 76)

    def test_returns_tuple(self):
        midi = build_chord_midi("C", "major")
        assert isinstance(midi, tuple)

    def test_octave_shifts_all_notes(self):
        midi_4 = build_chord_midi("C", "major", octave=4)
        midi_5 = build_chord_midi("C", "major", octave=5)
        for p4, p5 in zip(midi_4, midi_5, strict=False):
            assert p5 == p4 + 12

    def test_unknown_quality_raises(self):
        with pytest.raises(ValueError, match="quality"):
            build_chord_midi("C", "powerchord")

    def test_unknown_root_raises(self):
        with pytest.raises(ValueError):
            build_chord_midi("H", "major")


# ---------------------------------------------------------------------------
# get_diatonic_chords
# ---------------------------------------------------------------------------


class TestGetDiatonicChords:
    def test_a_natural_minor_names(self):
        chords = get_diatonic_chords("A", "natural minor", voicing="triads")
        names = [c.name for c in chords]
        assert names == ["Am", "Bdim", "C", "Dm", "Em", "F", "G"]

    def test_c_major_names(self):
        chords = get_diatonic_chords("C", "major", voicing="triads")
        names = [c.name for c in chords]
        assert names == ["C", "Dm", "Em", "F", "G", "Am", "Bdim"]

    def test_natural_minor_roman_numerals(self):
        chords = get_diatonic_chords("A", "natural minor")
        romans = [c.roman for c in chords]
        assert romans == ["i", "ii°", "III", "iv", "v", "VI", "VII"]

    def test_major_roman_numerals(self):
        chords = get_diatonic_chords("C", "major")
        romans = [c.roman for c in chords]
        assert romans == ["I", "ii", "iii", "IV", "V", "vi", "vii°"]

    def test_returns_7_chords(self):
        chords = get_diatonic_chords("D", "natural minor")
        assert len(chords) == 7

    def test_returns_tuple_of_chord_objects(self):
        chords = get_diatonic_chords("A", "natural minor")
        assert isinstance(chords, tuple)
        for c in chords:
            assert isinstance(c, Chord)

    def test_degrees_are_0_to_6(self):
        chords = get_diatonic_chords("A", "natural minor")
        degrees = [c.degree for c in chords]
        assert degrees == [0, 1, 2, 3, 4, 5, 6]

    def test_extended_voicing_upgrades_triads(self):
        chords = get_diatonic_chords("A", "natural minor", voicing="extended")
        # i → min7, VI → maj7
        assert chords[0].quality == "min7"  # Am → Am7
        assert chords[5].quality == "maj7"  # F → Fmaj7

    def test_seventh_voicing(self):
        chords = get_diatonic_chords("C", "major", voicing="seventh")
        assert chords[0].quality == "maj7"  # I → Imaj7
        assert chords[1].quality == "min7"  # ii → iim7

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="mode"):
            get_diatonic_chords("A", "japanese")

    def test_unknown_voicing_raises(self):
        with pytest.raises(ValueError, match="voicing"):
            get_diatonic_chords("A", "natural minor", voicing="open")

    def test_midi_notes_non_empty(self):
        chords = get_diatonic_chords("A", "natural minor")
        for c in chords:
            assert len(c.midi_notes) >= 3  # at least a triad

    def test_flat_root_supported(self):
        # Bb minor = A# minor
        chords_bb = get_diatonic_chords("Bb", "natural minor")
        chords_as = get_diatonic_chords("A#", "natural minor")
        assert chords_bb == chords_as

    @pytest.mark.parametrize("root", ["C", "D", "E", "F", "G", "A", "B"])
    def test_all_natural_roots_work(self, root):
        chords = get_diatonic_chords(root, "major")
        assert len(chords) == 7

    @pytest.mark.parametrize("root", ["C#", "D#", "F#", "G#", "A#"])
    def test_sharp_roots_work(self, root):
        chords = get_diatonic_chords(root, "natural minor")
        assert len(chords) == 7


# ---------------------------------------------------------------------------
# Constants sanity checks
# ---------------------------------------------------------------------------


class TestConstants:
    def test_note_names_has_12(self):
        assert len(NOTE_NAMES) == 12

    def test_chord_intervals_all_start_at_0(self):
        for quality, intervals in CHORD_INTERVALS.items():
            assert intervals[0] == 0, f"{quality} should start at 0"

    def test_scale_formulas_all_start_at_0(self):
        for mode, formula in SCALE_FORMULAS.items():
            assert formula[0] == 0, f"{mode} should start at 0"

    def test_diatonic_qualities_has_7_degrees(self):
        for mode, qualities in DIATONIC_QUALITIES.items():
            assert len(qualities) == 7, f"{mode} should have 7 degrees"

    def test_roman_numerals_has_7_degrees(self):
        for mode, romans in ROMAN_NUMERALS.items():
            assert len(romans) == 7, f"{mode} should have 7 roman numerals"
