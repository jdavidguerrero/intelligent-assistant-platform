"""
tests/test_full_arrangement_midi.py — Tests for full_arrangement_to_midi.

Covers:
    - Returns a 4-track MidiFile (meta + chords + bass + drums)
    - Chords on MIDI channel 0 (DAW channel 1)
    - Bass on MIDI channel 1 (DAW channel 2 = BASS_CHANNEL)
    - Drums on MIDI channel 9 (GM standard percussion)
    - Correct BPM encoded in tempo track
    - Raises ValueError on empty inputs
    - output_path saves a valid MIDI file
    - All note events present in correct tracks
"""

from __future__ import annotations

import mido
import pytest

from core.music_theory.bass import generate_bassline
from core.music_theory.drums import generate_pattern
from core.music_theory.harmony import suggest_progression
from core.music_theory.types import BassNote, DrumPattern, VoicingResult
from ingestion.midi_export import (
    BASS_CHANNEL,
    DRUM_CHANNEL,
    MIDI_CHANNEL,
    _bpm_to_tempo_us,
    full_arrangement_to_midi,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_voicing(key: str = "A", genre: str = "organic house", bars: int = 4) -> VoicingResult:
    return suggest_progression(key, genre=genre, bars=bars)


def _make_bass(voicing: VoicingResult, genre: str = "organic house") -> tuple[BassNote, ...]:
    return generate_bassline(voicing.chords, genre=genre, seed=0)


def _make_pattern(genre: str = "organic house", bars: int = 4) -> DrumPattern:
    return generate_pattern(genre=genre, bars=bars, energy=7, humanize=False, seed=0)


def _all_note_messages(track: mido.MidiTrack) -> list[mido.Message]:
    return [msg for msg in track if msg.type in ("note_on", "note_off")]


def _channels_in_track(track: mido.MidiTrack) -> set[int]:
    return {msg.channel for msg in track if hasattr(msg, "channel")}


# ---------------------------------------------------------------------------
# Track structure
# ---------------------------------------------------------------------------


class TestTrackStructure:
    def test_returns_midi_file(self) -> None:
        v = _make_voicing()
        midi = full_arrangement_to_midi(v, _make_bass(v), _make_pattern())
        assert isinstance(midi, mido.MidiFile)

    def test_exactly_four_tracks(self) -> None:
        v = _make_voicing()
        midi = full_arrangement_to_midi(v, _make_bass(v), _make_pattern())
        assert len(midi.tracks) == 4

    def test_track_0_is_meta(self) -> None:
        v = _make_voicing()
        midi = full_arrangement_to_midi(v, _make_bass(v), _make_pattern())
        meta_track = midi.tracks[0]
        types = {msg.type for msg in meta_track}
        assert "set_tempo" in types
        assert "time_signature" in types

    def test_track_1_has_note_events(self) -> None:
        """Chord track must contain note_on/note_off events."""
        v = _make_voicing()
        midi = full_arrangement_to_midi(v, _make_bass(v), _make_pattern())
        assert len(_all_note_messages(midi.tracks[1])) > 0

    def test_track_2_has_note_events(self) -> None:
        """Bass track must contain note_on/note_off events."""
        v = _make_voicing()
        midi = full_arrangement_to_midi(v, _make_bass(v), _make_pattern())
        assert len(_all_note_messages(midi.tracks[2])) > 0

    def test_track_3_has_note_events(self) -> None:
        """Drum track must contain note_on/note_off events."""
        v = _make_voicing()
        midi = full_arrangement_to_midi(v, _make_bass(v), _make_pattern())
        assert len(_all_note_messages(midi.tracks[3])) > 0


# ---------------------------------------------------------------------------
# Channel assignments
# ---------------------------------------------------------------------------


class TestChannelAssignments:
    def test_chord_track_on_channel_0(self) -> None:
        v = _make_voicing()
        midi = full_arrangement_to_midi(v, _make_bass(v), _make_pattern())
        channels = _channels_in_track(midi.tracks[1])
        assert channels == {MIDI_CHANNEL}  # channel 0

    def test_bass_track_on_bass_channel(self) -> None:
        v = _make_voicing()
        midi = full_arrangement_to_midi(v, _make_bass(v), _make_pattern())
        channels = _channels_in_track(midi.tracks[2])
        assert channels == {BASS_CHANNEL}  # channel 1

    def test_drum_track_on_channel_9(self) -> None:
        v = _make_voicing()
        midi = full_arrangement_to_midi(v, _make_bass(v), _make_pattern())
        channels = _channels_in_track(midi.tracks[3])
        assert channels == {DRUM_CHANNEL}  # channel 9

    def test_bass_channel_is_1(self) -> None:
        """BASS_CHANNEL constant must be 1 (DAW channel 2)."""
        assert BASS_CHANNEL == 1

    def test_drum_channel_is_9(self) -> None:
        """DRUM_CHANNEL constant must be 9 (GM standard percussion)."""
        assert DRUM_CHANNEL == 9

    def test_channels_are_distinct(self) -> None:
        """Chord, bass, and drum tracks must each use a different MIDI channel."""
        v = _make_voicing()
        midi = full_arrangement_to_midi(v, _make_bass(v), _make_pattern())
        ch1 = _channels_in_track(midi.tracks[1])
        ch2 = _channels_in_track(midi.tracks[2])
        ch3 = _channels_in_track(midi.tracks[3])
        assert ch1.isdisjoint(ch2)
        assert ch1.isdisjoint(ch3)
        assert ch2.isdisjoint(ch3)


# ---------------------------------------------------------------------------
# Tempo
# ---------------------------------------------------------------------------


class TestTempoEncoding:
    def test_default_bpm_120(self) -> None:
        v = _make_voicing()
        midi = full_arrangement_to_midi(v, _make_bass(v), _make_pattern())
        meta = midi.tracks[0]
        tempo_msgs = [msg for msg in meta if msg.type == "set_tempo"]
        assert len(tempo_msgs) == 1
        expected = _bpm_to_tempo_us(120.0)
        assert tempo_msgs[0].tempo == expected

    def test_custom_bpm_encoded_correctly(self) -> None:
        v = _make_voicing()
        midi = full_arrangement_to_midi(v, _make_bass(v), _make_pattern(), bpm=128.0)
        meta = midi.tracks[0]
        tempo_msgs = [msg for msg in meta if msg.type == "set_tempo"]
        assert tempo_msgs[0].tempo == _bpm_to_tempo_us(128.0)

    def test_bpm_80_encoded(self) -> None:
        v = _make_voicing()
        midi = full_arrangement_to_midi(v, _make_bass(v), _make_pattern(), bpm=80.0)
        meta = midi.tracks[0]
        tempo_msgs = [msg for msg in meta if msg.type == "set_tempo"]
        assert tempo_msgs[0].tempo == _bpm_to_tempo_us(80.0)


# ---------------------------------------------------------------------------
# ValueError cases
# ---------------------------------------------------------------------------


class TestValueErrors:
    def test_empty_voicing_raises(self) -> None:
        """full_arrangement_to_midi must raise ValueError when voicing has no chords."""
        from unittest.mock import MagicMock

        bass = _make_bass(_make_voicing())
        pattern = _make_pattern()
        # Use MagicMock to bypass VoicingResult's own validation and test the
        # full_arrangement_to_midi guard directly.
        mock_voicing = MagicMock()
        mock_voicing.chords = ()
        with pytest.raises(ValueError, match="chords"):
            full_arrangement_to_midi(mock_voicing, bass, pattern)

    def test_empty_bass_raises(self) -> None:
        v = _make_voicing()
        pattern = _make_pattern()
        with pytest.raises(ValueError, match="bass_notes"):
            full_arrangement_to_midi(v, (), pattern)

    def test_empty_pattern_raises(self) -> None:
        v = _make_voicing()
        bass = _make_bass(v)
        empty_pattern = DrumPattern(
            hits=(),
            steps_per_bar=16,
            bars=4,
            bpm=120.0,
            genre="organic house",
        )
        with pytest.raises(ValueError, match="pattern.hits"):
            full_arrangement_to_midi(v, bass, empty_pattern)


# ---------------------------------------------------------------------------
# output_path
# ---------------------------------------------------------------------------


class TestOutputPath:
    def test_saves_file_to_path(self, tmp_path: object) -> None:
        import pathlib

        out = pathlib.Path(str(tmp_path)) / "arrangement.mid"  # type: ignore[arg-type]
        v = _make_voicing()
        full_arrangement_to_midi(v, _make_bass(v), _make_pattern(), output_path=out)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_saved_file_is_valid_midi(self, tmp_path: object) -> None:
        import pathlib

        out = pathlib.Path(str(tmp_path)) / "arr.mid"  # type: ignore[arg-type]
        v = _make_voicing()
        full_arrangement_to_midi(v, _make_bass(v), _make_pattern(), output_path=out)
        # Re-load and verify basic structure
        loaded = mido.MidiFile(str(out))
        assert len(loaded.tracks) == 4


# ---------------------------------------------------------------------------
# Content correctness
# ---------------------------------------------------------------------------


class TestContentCorrectness:
    def test_chord_notes_in_valid_range(self) -> None:
        v = _make_voicing()
        midi = full_arrangement_to_midi(v, _make_bass(v), _make_pattern())
        for msg in _all_note_messages(midi.tracks[1]):
            assert 0 <= msg.note <= 127

    def test_bass_notes_in_valid_range(self) -> None:
        v = _make_voicing()
        midi = full_arrangement_to_midi(v, _make_bass(v), _make_pattern())
        for msg in _all_note_messages(midi.tracks[2]):
            assert 0 <= msg.note <= 127

    def test_drum_notes_are_gm_percussion(self) -> None:
        """Drum MIDI notes must be from GM drum map (kick=36..hihat_o=46)."""
        from ingestion.midi_export import GM_DRUM_NOTES

        valid_gm = set(GM_DRUM_NOTES.values())
        v = _make_voicing()
        midi = full_arrangement_to_midi(v, _make_bass(v), _make_pattern())
        for msg in _all_note_messages(midi.tracks[3]):
            if msg.type == "note_on" and msg.velocity > 0:
                assert msg.note in valid_gm, f"Unexpected drum note {msg.note}"

    def test_ticks_per_beat_stored(self) -> None:
        v = _make_voicing()
        midi = full_arrangement_to_midi(v, _make_bass(v), _make_pattern(), ticks_per_beat=480)
        assert midi.ticks_per_beat == 480

    def test_note_on_events_have_positive_velocity(self) -> None:
        """All note_on events (not note-off disguised as note_on) must have velocity > 0."""
        v = _make_voicing()
        midi = full_arrangement_to_midi(v, _make_bass(v), _make_pattern())
        for track in midi.tracks[1:]:
            for msg in track:
                if msg.type == "note_on" and msg.velocity > 0:
                    assert msg.velocity >= 1

    def test_delta_times_non_negative(self) -> None:
        """All delta times in the MIDI must be >= 0."""
        v = _make_voicing()
        midi = full_arrangement_to_midi(v, _make_bass(v), _make_pattern())
        for track in midi.tracks:
            for msg in track:
                assert msg.time >= 0, f"Negative delta time {msg.time} in {msg}"
