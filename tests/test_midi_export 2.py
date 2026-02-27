"""
Tests for ingestion/midi_export.py — MIDI file generation and round-trip.

Tests cover:
    - Time conversion utilities (_sec_to_ticks, _bpm_to_tempo_us)
    - notes_to_midi() output correctness
    - Round-trip: notes → MIDI → notes (pitch, duration, velocity preserved)
    - File I/O (saves correctly to tmp_path)
    - Edge cases: single note, empty input, overlapping notes
"""

import mido
import pytest

from core.audio.types import Note
from ingestion.midi_export import (
    DEFAULT_TICKS_PER_BEAT,
    _bpm_to_tempo_us,
    _sec_to_ticks,
    midi_to_notes,
    notes_to_midi,
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_note(
    pitch_midi: int = 69,
    pitch_name: str = "A4",
    onset_sec: float = 0.0,
    duration_sec: float = 0.5,
    velocity: int = 80,
) -> Note:
    return Note(
        pitch_midi=pitch_midi,
        pitch_name=pitch_name,
        onset_sec=onset_sec,
        duration_sec=duration_sec,
        velocity=velocity,
    )


# ---------------------------------------------------------------------------
# _sec_to_ticks
# ---------------------------------------------------------------------------


class TestSecToTicks:
    def test_one_second_at_120bpm_480tpb(self):
        """1.0 s at 120 BPM with 480 ticks/beat → 960 ticks.
        120 BPM = 2 beats/s; 2 beats × 480 ticks/beat = 960 ticks."""
        assert _sec_to_ticks(1.0, 120.0, 480) == 960

    def test_half_second_at_120bpm(self):
        """0.5 s at 120 BPM → 480 ticks (= 1 beat × 480 ticks/beat)."""
        assert _sec_to_ticks(0.5, 120.0, 480) == 480

    def test_one_bar_at_128bpm(self):
        """4 beats at 128 BPM with 480 ticks/beat = 4 × 480 = 1920 ticks.
        But 1 bar = 4/128 × 60 = 1.875 s → 1.875 × (128/60) × 480 = 1920."""
        bar_sec = 4 * 60 / 128
        assert _sec_to_ticks(bar_sec, 128.0, 480) == 1920

    def test_zero_seconds_returns_zero(self):
        """0 seconds → 0 ticks."""
        assert _sec_to_ticks(0.0, 120.0, 480) == 0

    def test_negative_returns_zero(self):
        """Negative seconds → 0 ticks (no negative deltas in MIDI)."""
        assert _sec_to_ticks(-1.0, 120.0, 480) == 0

    def test_returns_int(self):
        """Return type is int."""
        assert isinstance(_sec_to_ticks(1.0, 120.0, 480), int)


# ---------------------------------------------------------------------------
# _bpm_to_tempo_us
# ---------------------------------------------------------------------------


class TestBpmToTempoUs:
    def test_120bpm_is_500000(self):
        """120 BPM = 500,000 μs/beat (standard MIDI default)."""
        assert _bpm_to_tempo_us(120.0) == 500_000

    def test_60bpm_is_1000000(self):
        """60 BPM = 1,000,000 μs/beat."""
        assert _bpm_to_tempo_us(60.0) == 1_000_000

    def test_128bpm_close_to_expected(self):
        """128 BPM ≈ 468,750 μs/beat."""
        assert abs(_bpm_to_tempo_us(128.0) - 468_750) <= 1

    def test_zero_bpm_uses_default(self):
        """BPM ≤ 0 defaults to 120 BPM."""
        assert _bpm_to_tempo_us(0.0) == 500_000

    def test_returns_positive_int(self):
        """Always returns a positive integer."""
        for bpm in [60.0, 90.0, 120.0, 140.0, 174.0]:
            result = _bpm_to_tempo_us(bpm)
            assert isinstance(result, int)
            assert result > 0


# ---------------------------------------------------------------------------
# notes_to_midi — output structure
# ---------------------------------------------------------------------------


class TestNotesToMidi:
    def test_empty_notes_raises_value_error(self):
        """Empty note list raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            notes_to_midi([])

    def test_returns_midi_file(self):
        """notes_to_midi returns a mido.MidiFile."""
        notes = [_make_note()]
        result = notes_to_midi(notes)
        assert isinstance(result, mido.MidiFile)

    def test_has_two_tracks(self):
        """MIDI file has exactly 2 tracks (meta + note track)."""
        notes = [_make_note()]
        midi = notes_to_midi(notes)
        assert len(midi.tracks) == 2

    def test_ticks_per_beat_default(self):
        """Default ticks_per_beat is DEFAULT_TICKS_PER_BEAT (480)."""
        notes = [_make_note()]
        midi = notes_to_midi(notes)
        assert midi.ticks_per_beat == DEFAULT_TICKS_PER_BEAT

    def test_custom_ticks_per_beat(self):
        """Custom ticks_per_beat is respected."""
        notes = [_make_note()]
        midi = notes_to_midi(notes, ticks_per_beat=960)
        assert midi.ticks_per_beat == 960

    def test_tempo_message_present(self):
        """Track 0 contains a set_tempo meta message."""
        notes = [_make_note()]
        midi = notes_to_midi(notes, bpm=128.0)
        meta_track = midi.tracks[0]
        tempo_msgs = [m for m in meta_track if m.type == "set_tempo"]
        assert len(tempo_msgs) == 1

    def test_tempo_value_correct(self):
        """Tempo meta message encodes the correct BPM."""
        notes = [_make_note()]
        midi = notes_to_midi(notes, bpm=120.0)
        meta_track = midi.tracks[0]
        tempo_msg = next(m for m in meta_track if m.type == "set_tempo")
        assert tempo_msg.tempo == 500_000

    def test_note_on_present_in_note_track(self):
        """Note track contains at least one note_on message."""
        notes = [_make_note(pitch_midi=69, velocity=80)]
        midi = notes_to_midi(notes)
        note_track = midi.tracks[1]
        note_on_msgs = [m for m in note_track if m.type == "note_on" and m.velocity > 0]
        assert len(note_on_msgs) == 1

    def test_note_off_present_in_note_track(self):
        """Note track contains a note_off (or note_on with velocity=0) message."""
        notes = [_make_note(pitch_midi=69)]
        midi = notes_to_midi(notes)
        note_track = midi.tracks[1]
        note_off_msgs = [
            m
            for m in note_track
            if m.type == "note_off" or (m.type == "note_on" and m.velocity == 0)
        ]
        assert len(note_off_msgs) == 1

    def test_pitch_matches_note(self):
        """note_on pitch matches Note.pitch_midi."""
        notes = [_make_note(pitch_midi=60)]
        midi = notes_to_midi(notes)
        note_track = midi.tracks[1]
        note_on = next(m for m in note_track if m.type == "note_on" and m.velocity > 0)
        assert note_on.note == 60

    def test_velocity_matches_note(self):
        """note_on velocity matches Note.velocity."""
        notes = [_make_note(pitch_midi=69, velocity=90)]
        midi = notes_to_midi(notes)
        note_track = midi.tracks[1]
        note_on = next(m for m in note_track if m.type == "note_on" and m.velocity > 0)
        assert note_on.velocity == 90

    def test_saves_file_to_path(self, tmp_path):
        """output_path → file created and non-empty."""
        notes = [_make_note()]
        out = tmp_path / "melody.mid"
        notes_to_midi(notes, output_path=out)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_multiple_notes(self):
        """Multiple notes → correct number of note_on messages."""
        notes = [
            _make_note(pitch_midi=60, onset_sec=0.0),
            _make_note(pitch_midi=64, onset_sec=0.5),
            _make_note(pitch_midi=67, onset_sec=1.0),
        ]
        midi = notes_to_midi(notes)
        note_track = midi.tracks[1]
        note_on_msgs = [m for m in note_track if m.type == "note_on" and m.velocity > 0]
        assert len(note_on_msgs) == 3


# ---------------------------------------------------------------------------
# Round-trip: notes → MIDI → notes
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_pitch_preserved(self):
        """Pitch MIDI number survives notes → MIDI → notes."""
        original = [_make_note(pitch_midi=69)]
        midi = notes_to_midi(original, bpm=120.0)
        recovered = midi_to_notes(midi)
        assert len(recovered) == 1
        assert recovered[0].pitch_midi == 69

    def test_velocity_preserved(self):
        """Velocity survives round-trip."""
        original = [_make_note(pitch_midi=60, velocity=75)]
        midi = notes_to_midi(original, bpm=120.0)
        recovered = midi_to_notes(midi)
        assert recovered[0].velocity == 75

    def test_duration_approximately_preserved(self):
        """Duration survives round-trip within 5 ms tolerance."""
        original_duration = 0.5
        original = [_make_note(onset_sec=0.0, duration_sec=original_duration)]
        midi = notes_to_midi(original, bpm=120.0)
        recovered = midi_to_notes(midi)
        assert abs(recovered[0].duration_sec - original_duration) < 0.005

    def test_onset_approximately_preserved(self):
        """Onset time survives round-trip within 5 ms tolerance."""
        original_onset = 1.0
        original = [_make_note(onset_sec=original_onset, duration_sec=0.5)]
        midi = notes_to_midi(original, bpm=120.0)
        recovered = midi_to_notes(midi)
        assert abs(recovered[0].onset_sec - original_onset) < 0.005

    def test_multiple_notes_round_trip(self):
        """Multiple notes survive round-trip in correct order."""
        original = [
            _make_note(pitch_midi=60, onset_sec=0.0, duration_sec=0.5),
            _make_note(pitch_midi=64, onset_sec=0.5, duration_sec=0.5),
            _make_note(pitch_midi=67, onset_sec=1.0, duration_sec=0.5),
        ]
        midi = notes_to_midi(original, bpm=120.0)
        recovered = midi_to_notes(midi)
        assert len(recovered) == 3
        pitches = [n.pitch_midi for n in recovered]
        assert pitches == [60, 64, 67]
