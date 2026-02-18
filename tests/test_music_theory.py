"""
Tests for tools.music.theory module.

Verifies note normalization, MIDI conversion, scale/chord construction,
diatonic chord generation, and chord name parsing are correct and deterministic.
"""

import pytest

from tools.music.theory import (
    build_chord_midi,
    build_diatonic_chords,
    build_scale,
    midi_to_note,
    normalize_note,
    note_to_midi,
    parse_chord_name,
)

# ---------------------------------------------------------------------------
# TestNormalizeNote
# ---------------------------------------------------------------------------


class TestNormalizeNote:
    """Normalize note names to sharp notation."""

    def test_sharp_passthrough(self) -> None:
        assert normalize_note("C#") == "C#"

    def test_flat_to_sharp_bb(self) -> None:
        assert normalize_note("Bb") == "A#"

    def test_flat_to_sharp_eb(self) -> None:
        assert normalize_note("Eb") == "D#"

    def test_flat_to_sharp_db(self) -> None:
        assert normalize_note("Db") == "C#"

    def test_flat_to_sharp_gb(self) -> None:
        assert normalize_note("Gb") == "F#"

    def test_flat_to_sharp_ab(self) -> None:
        assert normalize_note("Ab") == "G#"

    def test_lowercase_natural(self) -> None:
        assert normalize_note("a") == "A"

    def test_lowercase_sharp(self) -> None:
        assert normalize_note("c#") == "C#"

    def test_whitespace_stripped(self) -> None:
        assert normalize_note("  G  ") == "G"

    def test_natural_notes_unchanged(self) -> None:
        for note in ("C", "D", "E", "F", "G", "A", "B"):
            assert normalize_note(note) == note

    def test_unknown_note_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown note"):
            normalize_note("X")

    def test_empty_string_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown note"):
            normalize_note("")

    def test_invalid_flat_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown note"):
            normalize_note("Hb")

    def test_double_sharp_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown note"):
            normalize_note("C##")


# ---------------------------------------------------------------------------
# TestNoteToMidi
# ---------------------------------------------------------------------------


class TestNoteToMidi:
    """Convert note + octave to MIDI pitch number."""

    def test_a4_is_69(self) -> None:
        assert note_to_midi("A", 4) == 69

    def test_c4_is_60(self) -> None:
        assert note_to_midi("C", 4) == 60

    def test_c5_is_72(self) -> None:
        assert note_to_midi("C", 5) == 72

    def test_middle_c_default_octave(self) -> None:
        # Default voicing octave is 4
        assert note_to_midi("C") == 60

    def test_flat_input_normalized(self) -> None:
        # Bb4 == A#4 == MIDI 70
        assert note_to_midi("Bb", 4) == note_to_midi("A#", 4)

    def test_b4_is_71(self) -> None:
        assert note_to_midi("B", 4) == 71

    def test_octave_zero_c(self) -> None:
        # C0 = (0+1)*12 + 0 = 12
        assert note_to_midi("C", 0) == 12

    def test_octave_negative_one_c(self) -> None:
        # C-1 = (−1+1)*12 + 0 = 0 — MIDI boundary
        assert note_to_midi("C", -1) == 0

    def test_out_of_range_raises_value_error(self) -> None:
        # octave=10 → C10 = 11*12 = 132 > 127
        with pytest.raises(ValueError, match="out of range"):
            note_to_midi("C", 10)

    def test_invalid_note_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown note"):
            note_to_midi("Z", 4)


# ---------------------------------------------------------------------------
# TestMidiToNote
# ---------------------------------------------------------------------------


class TestMidiToNote:
    """Convert MIDI pitch number to (note_name, octave)."""

    def test_69_is_a4(self) -> None:
        assert midi_to_note(69) == ("A", 4)

    def test_60_is_c4(self) -> None:
        assert midi_to_note(60) == ("C", 4)

    def test_72_is_c5(self) -> None:
        assert midi_to_note(72) == ("C", 5)

    def test_0_is_c_neg1(self) -> None:
        assert midi_to_note(0) == ("C", -1)

    def test_127_is_g9(self) -> None:
        note, octave = midi_to_note(127)
        assert note == "G"
        assert octave == 9

    def test_out_of_range_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            midi_to_note(-1)

    def test_out_of_range_high_raises(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            midi_to_note(128)

    def test_roundtrip_note_to_midi_to_note(self) -> None:
        for midi in (0, 21, 60, 69, 93, 127):
            note, octave = midi_to_note(midi)
            assert note_to_midi(note, octave) == midi

    def test_sharp_notation_used(self) -> None:
        # MIDI 61 = C#4 (sharps preferred, not Db)
        note, octave = midi_to_note(61)
        assert note == "C#"
        assert octave == 4


# ---------------------------------------------------------------------------
# TestBuildScale
# ---------------------------------------------------------------------------


class TestBuildScale:
    """Build a diatonic scale from root + mode."""

    def test_a_natural_minor(self) -> None:
        scale = build_scale("A", "natural minor")
        assert scale == ["A", "B", "C", "D", "E", "F", "G"]

    def test_c_major(self) -> None:
        scale = build_scale("C", "major")
        assert scale == ["C", "D", "E", "F", "G", "A", "B"]

    def test_natural_minor_has_7_notes(self) -> None:
        assert len(build_scale("D", "natural minor")) == 7

    def test_major_has_7_notes(self) -> None:
        assert len(build_scale("G", "major")) == 7

    def test_pentatonic_minor_has_5_notes(self) -> None:
        assert len(build_scale("A", "pentatonic minor")) == 5

    def test_pentatonic_major_has_5_notes(self) -> None:
        assert len(build_scale("C", "pentatonic major")) == 5

    def test_flat_root_normalized(self) -> None:
        # Bb natural minor = A# natural minor
        bb_scale = build_scale("Bb", "natural minor")
        asharp_scale = build_scale("A#", "natural minor")
        assert bb_scale == asharp_scale

    def test_all_notes_in_chromatic(self) -> None:
        from tools.music.theory import NOTE_NAMES

        scale = build_scale("E", "major")
        for note in scale:
            assert note in NOTE_NAMES

    def test_unknown_mode_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown mode"):
            build_scale("C", "nonsense_mode")

    def test_unknown_root_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown note"):
            build_scale("Z", "major")

    def test_dorian_mode(self) -> None:
        # D dorian: D E F G A B C
        scale = build_scale("D", "dorian")
        assert scale[0] == "D"
        assert len(scale) == 7

    def test_harmonic_minor(self) -> None:
        # A harmonic minor: A B C D E F G#
        scale = build_scale("A", "harmonic minor")
        assert scale == ["A", "B", "C", "D", "E", "F", "G#"]


# ---------------------------------------------------------------------------
# TestBuildChordMidi
# ---------------------------------------------------------------------------


class TestBuildChordMidi:
    """Build MIDI note list for a chord."""

    def test_am_triad(self) -> None:
        # A4 minor = [69, 72, 76]
        midi_notes = build_chord_midi("A", "minor", 4)
        assert midi_notes == [69, 72, 76]

    def test_cmaj_triad(self) -> None:
        # C4 major = [60, 64, 67]
        midi_notes = build_chord_midi("C", "major", 4)
        assert midi_notes == [60, 64, 67]

    def test_cmaj7_has_4_notes(self) -> None:
        midi_notes = build_chord_midi("C", "maj7", 4)
        assert len(midi_notes) == 4

    def test_cmaj7_intervals(self) -> None:
        # C major7 = [60, 64, 67, 71]
        midi_notes = build_chord_midi("C", "maj7", 4)
        assert midi_notes == [60, 64, 67, 71]

    def test_min9_has_5_notes(self) -> None:
        midi_notes = build_chord_midi("A", "min9", 4)
        assert len(midi_notes) == 5

    def test_flat_root_normalized(self) -> None:
        # Bb minor == A# minor
        bb = build_chord_midi("Bb", "minor", 4)
        asharp = build_chord_midi("A#", "minor", 4)
        assert bb == asharp

    def test_dim_triad_intervals(self) -> None:
        # C dim = [60, 63, 66]
        midi_notes = build_chord_midi("C", "dim", 4)
        assert midi_notes == [60, 63, 66]

    def test_unknown_quality_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown chord quality"):
            build_chord_midi("C", "notachord", 4)

    def test_unknown_root_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown note"):
            build_chord_midi("Z", "major", 4)

    def test_default_octave_is_4(self) -> None:
        # Default voicing octave is 4
        assert build_chord_midi("A", "minor") == build_chord_midi("A", "minor", 4)

    def test_different_octaves_produce_different_midi(self) -> None:
        oct3 = build_chord_midi("C", "major", 3)
        oct5 = build_chord_midi("C", "major", 5)
        assert oct3[0] < oct5[0]
        # Exactly one octave = 12 semitones apart
        assert oct5[0] - oct3[0] == 24


# ---------------------------------------------------------------------------
# TestBuildDiatonicChords
# ---------------------------------------------------------------------------


class TestBuildDiatonicChords:
    """Build the full diatonic chord set for a key."""

    REQUIRED_KEYS = {"degree", "roman", "root", "quality", "name", "midi_notes"}

    def test_returns_7_chords_for_7_note_scale(self) -> None:
        chords = build_diatonic_chords("A", "natural minor", "triads")
        assert len(chords) == 7

    def test_each_chord_has_required_keys(self) -> None:
        chords = build_diatonic_chords("C", "major", "triads")
        for chord in chords:
            assert self.REQUIRED_KEYS.issubset(chord.keys())

    def test_degrees_are_zero_indexed(self) -> None:
        chords = build_diatonic_chords("A", "natural minor", "triads")
        degrees = [c["degree"] for c in chords]
        assert degrees == list(range(7))

    def test_first_degree_a_minor_is_minor(self) -> None:
        chords = build_diatonic_chords("A", "natural minor", "triads")
        assert chords[0]["quality"] == "minor"

    def test_first_degree_c_major_is_major(self) -> None:
        chords = build_diatonic_chords("C", "major", "triads")
        assert chords[0]["quality"] == "major"

    def test_first_degree_root_matches_key(self) -> None:
        chords = build_diatonic_chords("A", "natural minor", "triads")
        assert chords[0]["root"] == "A"

    def test_roman_numeral_present_and_nonempty(self) -> None:
        chords = build_diatonic_chords("A", "natural minor", "triads")
        for chord in chords:
            assert isinstance(chord["roman"], str)
            assert len(chord["roman"]) > 0

    def test_midi_notes_is_list_of_ints(self) -> None:
        chords = build_diatonic_chords("C", "major", "triads")
        for chord in chords:
            assert isinstance(chord["midi_notes"], list)
            assert all(isinstance(n, int) for n in chord["midi_notes"])

    def test_triads_have_3_midi_notes(self) -> None:
        chords = build_diatonic_chords("A", "natural minor", "triads")
        for chord in chords:
            # dim triad also has 3 notes; all triads in diatonic_qualities
            # map to 3-note chords under "triads" voicing
            assert len(chord["midi_notes"]) == 3

    def test_extended_voicing_upgrades_minor_to_min7(self) -> None:
        chords = build_diatonic_chords("A", "natural minor", "extended")
        # Degree 0 (i) is minor — should be upgraded to min7
        assert chords[0]["quality"] == "min7"

    def test_extended_voicing_upgrades_major_to_maj7(self) -> None:
        chords = build_diatonic_chords("C", "major", "extended")
        # Degree 0 (I) is major — should be upgraded to maj7
        assert chords[0]["quality"] == "maj7"

    def test_seventh_voicing_upgrades_minor_to_min7(self) -> None:
        chords = build_diatonic_chords("A", "natural minor", "seventh")
        assert chords[0]["quality"] == "min7"

    def test_name_field_is_nonempty_string(self) -> None:
        chords = build_diatonic_chords("G", "major", "triads")
        for chord in chords:
            assert isinstance(chord["name"], str)
            assert len(chord["name"]) > 0

    def test_major_scale_c_roman_numerals(self) -> None:
        chords = build_diatonic_chords("C", "major", "triads")
        romans = [c["roman"] for c in chords]
        assert romans[0] == "I"
        assert romans[1] == "ii"
        assert romans[4] == "V"

    def test_natural_minor_a_roman_numerals(self) -> None:
        chords = build_diatonic_chords("A", "natural minor", "triads")
        assert chords[0]["roman"] == "i"
        assert chords[1]["roman"] == "ii°"

    def test_returns_5_chords_for_pentatonic_minor(self) -> None:
        # Pentatonic minor has 5 scale degrees but is NOT in DIATONIC_QUALITIES,
        # so it falls back to natural minor qualities (zip with strict=False stops
        # at shorter sequence)
        chords = build_diatonic_chords("A", "pentatonic minor", "triads")
        assert len(chords) == 5


# ---------------------------------------------------------------------------
# TestParseChordName
# ---------------------------------------------------------------------------


class TestParseChordName:
    """Parse chord name string to (root, quality_key)."""

    def test_am_returns_a_minor(self) -> None:
        root, quality = parse_chord_name("Am")
        assert root == "A"
        assert quality == "minor"

    def test_cmaj7_returns_c_maj7(self) -> None:
        root, quality = parse_chord_name("Cmaj7")
        assert root == "C"
        assert quality == "maj7"

    def test_bb7_returns_asharp_dom7(self) -> None:
        root, quality = parse_chord_name("Bb7")
        assert root == "A#"
        assert quality == "dom7"

    def test_fsharp_m9_returns_fsharp_min9(self) -> None:
        root, quality = parse_chord_name("F#m9")
        assert root == "F#"
        assert quality == "min9"

    def test_bare_root_is_major(self) -> None:
        root, quality = parse_chord_name("C")
        assert root == "C"
        assert quality == "major"

    def test_dsharp_bare_is_major(self) -> None:
        root, quality = parse_chord_name("D#")
        assert root == "D#"
        assert quality == "major"

    def test_dim_suffix(self) -> None:
        root, quality = parse_chord_name("Bdim")
        assert root == "B"
        assert quality == "dim"

    def test_aug_suffix(self) -> None:
        root, quality = parse_chord_name("Caug")
        assert root == "C"
        assert quality == "aug"

    def test_sus2_suffix(self) -> None:
        root, quality = parse_chord_name("Gsus2")
        assert root == "G"
        assert quality == "sus2"

    def test_sus4_suffix(self) -> None:
        root, quality = parse_chord_name("Dsus4")
        assert root == "D"
        assert quality == "sus4"

    def test_m7_suffix_maps_to_min7(self) -> None:
        root, quality = parse_chord_name("Am7")
        assert root == "A"
        assert quality == "min7"

    def test_9_suffix_maps_to_dom9(self) -> None:
        root, quality = parse_chord_name("G9")
        assert root == "G"
        assert quality == "dom9"

    def test_add9_suffix(self) -> None:
        root, quality = parse_chord_name("Cadd9")
        assert root == "C"
        assert quality == "add9"

    def test_flat_root_normalized_to_sharp(self) -> None:
        root, quality = parse_chord_name("Ebm")
        assert root == "D#"
        assert quality == "minor"

    def test_empty_string_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Empty chord name"):
            parse_chord_name("")

    def test_whitespace_only_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Empty chord name"):
            parse_chord_name("   ")

    def test_unrecognized_suffix_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unrecognized chord suffix"):
            parse_chord_name("Cxyz")

    def test_invalid_root_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown note"):
            parse_chord_name("Xm")

    def test_min_suffix_maps_to_minor(self) -> None:
        root, quality = parse_chord_name("Emin")
        assert root == "E"
        assert quality == "minor"

    def test_dim7_suffix(self) -> None:
        root, quality = parse_chord_name("Bdim7")
        assert root == "B"
        assert quality == "dim7"

    def test_maj9_suffix(self) -> None:
        root, quality = parse_chord_name("Cmaj9")
        assert root == "C"
        assert quality == "maj9"
