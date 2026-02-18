"""
tests/test_midi.py — Unit tests for core/midi.py

Tests cover:
- parse_chord_name: root/quality splitting, enharmonics, edge cases
- resolve_chord: MIDI pitch calculation, all qualities, octave variants
- chords_to_midi_notes: list conversion, ordering, duration, velocity
- total_clip_beats: length calculation
- Error paths: unknown roots, empty lists, bad params
"""

from __future__ import annotations

import pytest

from core.midi import (
    ChordVoicing,
    MidiNote,
    chords_to_midi_notes,
    parse_chord_name,
    resolve_chord,
    total_clip_beats,
)

# ---------------------------------------------------------------------------
# parse_chord_name
# ---------------------------------------------------------------------------


class TestParseChordName:
    def test_single_letter_major(self) -> None:
        root, quality = parse_chord_name("C")
        assert root == "C"
        assert quality == "maj"

    def test_single_letter_minor(self) -> None:
        root, quality = parse_chord_name("Am")
        assert root == "A"
        assert quality == "m"

    def test_sharp_root(self) -> None:
        root, quality = parse_chord_name("C#m")
        assert root == "C#"
        assert quality == "m"

    def test_flat_root(self) -> None:
        root, quality = parse_chord_name("Bbmaj7")
        assert root == "Bb"
        assert quality == "maj7"

    def test_maj7_quality(self) -> None:
        root, quality = parse_chord_name("Fmaj7")
        assert root == "F"
        assert quality == "maj7"

    def test_dominant_7(self) -> None:
        root, quality = parse_chord_name("G7")
        assert root == "G"
        assert quality == "7"

    def test_m7(self) -> None:
        root, quality = parse_chord_name("Dm7")
        assert root == "D"
        assert quality == "m7"

    def test_dim(self) -> None:
        root, quality = parse_chord_name("Bdim")
        assert root == "B"
        assert quality == "dim"

    def test_sus4(self) -> None:
        root, quality = parse_chord_name("Gsus4")
        assert root == "G"
        assert quality == "sus4"

    def test_sus2(self) -> None:
        root, quality = parse_chord_name("Dsus2")
        assert root == "D"
        assert quality == "sus2"

    def test_add9(self) -> None:
        root, quality = parse_chord_name("Cadd9")
        assert root == "C"
        assert quality == "add9"

    def test_enharmonic_db(self) -> None:
        root, quality = parse_chord_name("Dbm")
        assert root == "Db"
        assert quality == "m"

    def test_enharmonic_gb(self) -> None:
        root, quality = parse_chord_name("Gbmaj7")
        assert root == "Gb"
        assert quality == "maj7"

    def test_strips_whitespace(self) -> None:
        root, quality = parse_chord_name("  Em  ")
        assert root == "E"
        assert quality == "m"

    def test_f_sharp_alone(self) -> None:
        root, quality = parse_chord_name("F#")
        assert root == "F#"
        assert quality == "maj"

    def test_unknown_root_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse chord name"):
            parse_chord_name("Xm7")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_chord_name("")


# ---------------------------------------------------------------------------
# resolve_chord
# ---------------------------------------------------------------------------


class TestResolveChord:
    # --- A minor: root=69, minor triad [0,3,7] → 69,72,76
    def test_a_minor_pitches(self) -> None:
        v = resolve_chord("Am")
        assert v.root == "A"
        assert v.quality == "m"
        assert v.pitches == (69, 72, 76)

    def test_c_major_pitches(self) -> None:
        v = resolve_chord("C")
        # C4=60, major [0,4,7] → 60,64,67
        assert v.pitches == (60, 64, 67)

    def test_g_major_pitches(self) -> None:
        v = resolve_chord("G")
        # G4=67, major [0,4,7] → 67,71,74
        assert v.pitches == (67, 71, 74)

    def test_f_major_pitches(self) -> None:
        v = resolve_chord("F")
        # F4=65, major [0,4,7] → 65,69,72
        assert v.pitches == (65, 69, 72)

    def test_am7_pitches(self) -> None:
        v = resolve_chord("Am7")
        # A4=69, m7 [0,3,7,10] → 69,72,76,79
        assert v.pitches == (69, 72, 76, 79)

    def test_fmaj7_pitches(self) -> None:
        v = resolve_chord("Fmaj7")
        # F4=65, maj7 [0,4,7,11] → 65,69,72,76
        assert v.pitches == (65, 69, 72, 76)

    def test_c_sharp_minor(self) -> None:
        v = resolve_chord("C#m")
        # C#4=61, m [0,3,7] → 61,64,68
        assert v.pitches == (61, 64, 68)

    def test_bb_major(self) -> None:
        v = resolve_chord("Bb")
        # Bb4=70, major [0,4,7] → 70,74,77
        assert v.pitches == (70, 74, 77)

    def test_dim_chord(self) -> None:
        v = resolve_chord("Bdim")
        # B4=71, dim [0,3,6] → 71,74,77
        assert v.pitches == (71, 74, 77)

    def test_aug_chord(self) -> None:
        v = resolve_chord("Caug")
        # C4=60, aug [0,4,8] → 60,64,68
        assert v.pitches == (60, 64, 68)

    def test_sus2_chord(self) -> None:
        v = resolve_chord("Dsus2")
        # D4=62, sus2 [0,2,7] → 62,64,69
        assert v.pitches == (62, 64, 69)

    def test_sus4_chord(self) -> None:
        v = resolve_chord("Gsus4")
        # G4=67, sus4 [0,5,7] → 67,72,74
        assert v.pitches == (67, 72, 74)

    def test_dominant_7(self) -> None:
        v = resolve_chord("G7")
        # G4=67, dom7 [0,4,7,10] → 67,71,74,77
        assert v.pitches == (67, 71, 74, 77)

    def test_m7b5(self) -> None:
        v = resolve_chord("Bm7b5")
        # B4=71, m7b5 [0,3,6,10] → 71,74,77,81
        assert v.pitches == (71, 74, 77, 81)

    def test_dim7(self) -> None:
        v = resolve_chord("Cdim7")
        # C4=60, dim7 [0,3,6,9] → 60,63,66,69
        assert v.pitches == (60, 63, 66, 69)

    def test_add9(self) -> None:
        v = resolve_chord("Cadd9")
        # C4=60, add9 [0,4,7,14] → 60,64,67,74
        assert v.pitches == (60, 64, 67, 74)

    def test_9_chord(self) -> None:
        v = resolve_chord("C9")
        # C4=60, 9 [0,4,7,10,14] → 60,64,67,70,74
        assert v.pitches == (60, 64, 67, 70, 74)

    def test_octave_3(self) -> None:
        v = resolve_chord("Am", octave=3)
        # A3 = 60 + (3-4)*12 + 9 = 60 - 12 + 9 = 57
        assert v.pitches[0] == 57

    def test_octave_5(self) -> None:
        v = resolve_chord("Am", octave=5)
        # A5 = 60 + (5-4)*12 + 9 = 60 + 12 + 9 = 81
        assert v.pitches[0] == 81

    def test_pitches_ascending(self) -> None:
        for chord_name in ["Am7", "Cmaj7", "Fmaj7", "G7", "Bdim"]:
            v = resolve_chord(chord_name)
            assert list(v.pitches) == sorted(v.pitches), f"{chord_name} not ascending"

    def test_name_preserved(self) -> None:
        v = resolve_chord("Am7")
        assert v.name == "Am7"

    def test_returns_chord_voicing(self) -> None:
        v = resolve_chord("C")
        assert isinstance(v, ChordVoicing)

    def test_unknown_quality_defaults_to_major(self) -> None:
        # Weird quality falls back to major triad
        v = resolve_chord("Cxyz")
        assert v.pitches == (60, 64, 67)

    def test_pitches_cap_at_127(self) -> None:
        # Very high octave — all pitches must be ≤ 127
        v = resolve_chord("B", octave=9)
        assert all(p <= 127 for p in v.pitches)

    def test_enharmonic_db_equals_cs(self) -> None:
        db = resolve_chord("Db")
        cs = resolve_chord("C#")
        # Enharmonics: same MIDI pitches
        assert db.pitches == cs.pitches

    def test_enharmonic_gb_equals_fs(self) -> None:
        gb = resolve_chord("Gbm")
        fs = resolve_chord("F#m")
        assert gb.pitches == fs.pitches


# ---------------------------------------------------------------------------
# chords_to_midi_notes
# ---------------------------------------------------------------------------


class TestChordsToMidiNotes:
    def test_basic_am_f_c_g(self) -> None:
        notes = chords_to_midi_notes(["Am", "F", "C", "G"])
        # Am=3 notes, F=3, C=3, G=3 → 12 total
        assert len(notes) == 12

    def test_total_beats(self) -> None:
        notes = chords_to_midi_notes(["Am", "F"], beats_per_chord=4.0)
        # 2 chords × 4 beats = 8 beats total, last note ends at beat 4+dur
        assert notes[0].start_beat == 0.0
        # Second chord starts at beat 4
        second_chord_notes = [n for n in notes if n.start_beat == 4.0]
        assert len(second_chord_notes) == 3  # F major triad

    def test_sorted_by_start_then_pitch(self) -> None:
        notes = chords_to_midi_notes(["Am", "F", "C", "G"])
        for i in range(len(notes) - 1):
            a, b = notes[i], notes[i + 1]
            assert (a.start_beat, a.pitch) <= (b.start_beat, b.pitch)

    def test_default_velocity(self) -> None:
        notes = chords_to_midi_notes(["Am"])
        assert all(n.velocity == 90 for n in notes)

    def test_custom_velocity(self) -> None:
        notes = chords_to_midi_notes(["Am"], velocity=64)
        assert all(n.velocity == 64 for n in notes)

    def test_default_duration_ratio(self) -> None:
        notes = chords_to_midi_notes(["Am"], beats_per_chord=4.0, note_duration_ratio=0.9)
        expected_dur = 4.0 * 0.9
        assert all(abs(n.duration_beats - expected_dur) < 1e-9 for n in notes)

    def test_custom_beats_per_chord(self) -> None:
        notes = chords_to_midi_notes(["Am", "F"], beats_per_chord=2.0)
        starts = sorted({n.start_beat for n in notes})
        assert starts == [0.0, 2.0]

    def test_single_chord(self) -> None:
        notes = chords_to_midi_notes(["Am7"])
        # Am7 = 4 notes
        assert len(notes) == 4
        assert all(n.start_beat == 0.0 for n in notes)

    def test_returns_midi_note_instances(self) -> None:
        notes = chords_to_midi_notes(["C"])
        assert all(isinstance(n, MidiNote) for n in notes)

    def test_empty_list_raises(self) -> None:
        with pytest.raises(ValueError, match="chord_names must not be empty"):
            chords_to_midi_notes([])

    def test_invalid_velocity_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="velocity must be in"):
            chords_to_midi_notes(["Am"], velocity=0)

    def test_invalid_velocity_128_raises(self) -> None:
        with pytest.raises(ValueError, match="velocity must be in"):
            chords_to_midi_notes(["Am"], velocity=128)

    def test_invalid_duration_ratio_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="note_duration_ratio must be in"):
            chords_to_midi_notes(["Am"], note_duration_ratio=0.0)

    def test_invalid_duration_ratio_above_one_raises(self) -> None:
        with pytest.raises(ValueError, match="note_duration_ratio must be in"):
            chords_to_midi_notes(["Am"], note_duration_ratio=1.01)

    def test_duration_ratio_exactly_one_ok(self) -> None:
        notes = chords_to_midi_notes(["Am"], note_duration_ratio=1.0)
        assert all(n.duration_beats == 4.0 for n in notes)

    def test_am_pitches_in_notes(self) -> None:
        notes = chords_to_midi_notes(["Am"])
        pitches = {n.pitch for n in notes}
        assert pitches == {69, 72, 76}  # A4, C5, E5

    def test_start_beats_correct_for_8_chords(self) -> None:
        chords = ["Am", "F", "C", "G", "Am", "F", "C", "G"]
        notes = chords_to_midi_notes(chords, beats_per_chord=4.0)
        expected_starts = {i * 4.0 for i in range(8)}
        actual_starts = {n.start_beat for n in notes}
        assert actual_starts == expected_starts

    def test_7th_chord_produces_4_notes(self) -> None:
        notes = chords_to_midi_notes(["Am7"])
        assert len(notes) == 4

    def test_9th_chord_produces_5_notes(self) -> None:
        notes = chords_to_midi_notes(["Am9"])
        assert len(notes) == 5


# ---------------------------------------------------------------------------
# total_clip_beats
# ---------------------------------------------------------------------------


class TestTotalClipBeats:
    def test_4_chords_default(self) -> None:
        assert total_clip_beats(["Am", "F", "C", "G"]) == 16.0

    def test_8_chords_default(self) -> None:
        assert total_clip_beats(["Am"] * 8) == 32.0

    def test_custom_beats_per_chord(self) -> None:
        assert total_clip_beats(["Am", "F"], beats_per_chord=2.0) == 4.0

    def test_single_chord(self) -> None:
        assert total_clip_beats(["Am"]) == 4.0

    def test_empty_list(self) -> None:
        assert total_clip_beats([]) == 0.0

    def test_half_bar_chords(self) -> None:
        # 2 beats per chord × 4 chords = 8 beats
        assert total_clip_beats(["Am", "F", "C", "G"], beats_per_chord=2.0) == 8.0
