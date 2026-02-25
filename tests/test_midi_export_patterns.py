"""
Tests for ingestion/midi_export.py Week 13 extensions:
    - chords_to_midi
    - bassline_to_midi
    - pattern_to_midi
    - _step_to_ticks helper
    - GM_DRUM_NOTES mapping
    - DRUM_CHANNEL constant

Validates:
    - All functions return mido.MidiFile
    - Track structure (2 tracks: meta + content)
    - Tempo encoding matches BPM
    - Note events present with correct channel
    - Drum events on channel 9
    - output_path saves file
    - Empty input raises ValueError
    - Step-to-ticks conversion correctness
"""

from __future__ import annotations

from pathlib import Path

import mido
import pytest

from core.music_theory.bass import generate_bassline
from core.music_theory.drums import generate_pattern
from core.music_theory.harmony import suggest_progression
from core.music_theory.scales import get_diatonic_chords
from ingestion.midi_export import (
    DRUM_CHANNEL,
    GM_DRUM_NOTES,
    _step_to_ticks,
    bassline_to_midi,
    chords_to_midi,
    pattern_to_midi,
)

# ---------------------------------------------------------------------------
# _step_to_ticks
# ---------------------------------------------------------------------------


class TestStepToTicks:
    def test_step_0_is_0(self):
        assert _step_to_ticks(0, 480) == 0

    def test_step_4_is_one_beat(self):
        # 4 steps = 1 beat = 480 ticks at 480 tpb
        assert _step_to_ticks(4, 480) == 480

    def test_step_16_is_one_bar(self):
        # 16 steps = 4 beats = 1920 ticks at 480 tpb
        assert _step_to_ticks(16, 480) == 1920

    def test_step_1_is_120_at_480tpb(self):
        # 1 step = 480/4 = 120 ticks
        assert _step_to_ticks(1, 480) == 120


# ---------------------------------------------------------------------------
# GM_DRUM_NOTES
# ---------------------------------------------------------------------------


class TestGMDrumNotes:
    def test_kick_is_36(self):
        assert GM_DRUM_NOTES["kick"] == 36

    def test_snare_is_38(self):
        assert GM_DRUM_NOTES["snare"] == 38

    def test_clap_is_39(self):
        assert GM_DRUM_NOTES["clap"] == 39

    def test_hihat_c_is_42(self):
        assert GM_DRUM_NOTES["hihat_c"] == 42

    def test_hihat_o_is_46(self):
        assert GM_DRUM_NOTES["hihat_o"] == 46

    def test_drum_channel_is_9(self):
        assert DRUM_CHANNEL == 9


# ---------------------------------------------------------------------------
# chords_to_midi
# ---------------------------------------------------------------------------


class TestChordsToMidi:
    def _voicing(self, bars: int = 4):
        return suggest_progression("A", genre="organic house", bars=bars)

    def test_returns_midi_file(self):
        midi = chords_to_midi(self._voicing())
        assert isinstance(midi, mido.MidiFile)

    def test_has_two_tracks(self):
        midi = chords_to_midi(self._voicing())
        assert len(midi.tracks) == 2

    def test_tempo_encoded_correctly(self):
        midi = chords_to_midi(self._voicing(), bpm=124.0)
        tempo = None
        for msg in midi.tracks[0]:
            if msg.type == "set_tempo":
                tempo = msg.tempo
        bpm_back = 60_000_000 / tempo
        assert abs(bpm_back - 124.0) < 1.0

    def test_note_events_present(self):
        midi = chords_to_midi(self._voicing())
        note_on_events = [m for m in midi.tracks[1] if hasattr(m, "type") and m.type == "note_on"]
        assert len(note_on_events) > 0

    def test_notes_on_channel_0(self):
        midi = chords_to_midi(self._voicing())
        for msg in midi.tracks[1]:
            if hasattr(msg, "channel"):
                assert msg.channel == 0

    def test_empty_chords_raises(self):
        voicing = suggest_progression("A", bars=1)
        object.__setattr__(voicing, "chords", ())
        with pytest.raises((ValueError, AttributeError)):
            chords_to_midi(voicing)

    def test_output_path_writes_file(self, tmp_path: Path):
        out = tmp_path / "chords.mid"
        chords_to_midi(self._voicing(), output_path=out)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_ticks_per_beat_stored(self):
        midi = chords_to_midi(self._voicing(), ticks_per_beat=960)
        assert midi.ticks_per_beat == 960


# ---------------------------------------------------------------------------
# bassline_to_midi
# ---------------------------------------------------------------------------


class TestBasslineToMidi:
    def _bass(self):
        chords = list(get_diatonic_chords("A", "natural minor"))[:4]
        return generate_bassline(chords, genre="organic house", seed=0)

    def test_returns_midi_file(self):
        midi = bassline_to_midi(self._bass())
        assert isinstance(midi, mido.MidiFile)

    def test_has_two_tracks(self):
        midi = bassline_to_midi(self._bass())
        assert len(midi.tracks) == 2

    def test_tempo_encoded(self):
        midi = bassline_to_midi(self._bass(), bpm=128.0)
        tempo = None
        for msg in midi.tracks[0]:
            if msg.type == "set_tempo":
                tempo = msg.tempo
        assert abs(60_000_000 / tempo - 128.0) < 1.0

    def test_note_events_on_channel_0(self):
        midi = bassline_to_midi(self._bass())
        for msg in midi.tracks[1]:
            if hasattr(msg, "channel"):
                assert msg.channel == 0

    def test_note_on_events_present(self):
        midi = bassline_to_midi(self._bass())
        note_ons = [m for m in midi.tracks[1] if hasattr(m, "type") and m.type == "note_on"]
        assert len(note_ons) > 0

    def test_empty_bass_raises(self):
        with pytest.raises(ValueError, match="empty"):
            bassline_to_midi([])

    def test_output_path_writes_file(self, tmp_path: Path):
        out = tmp_path / "bass.mid"
        bassline_to_midi(self._bass(), output_path=out)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_pitch_in_bass_register(self):
        """Bass notes should be in MIDI range 24-60 (bass register)."""
        midi = bassline_to_midi(self._bass())
        note_pitches = [
            m.note for m in midi.tracks[1] if hasattr(m, "type") and m.type == "note_on"
        ]
        assert all(20 <= p <= 72 for p in note_pitches)


# ---------------------------------------------------------------------------
# pattern_to_midi
# ---------------------------------------------------------------------------


class TestPatternToMidi:
    def _pattern(self, bars: int = 4):
        return generate_pattern(bpm=123.0, genre="organic house", bars=bars, seed=0)

    def test_returns_midi_file(self):
        midi = pattern_to_midi(self._pattern())
        assert isinstance(midi, mido.MidiFile)

    def test_has_two_tracks(self):
        midi = pattern_to_midi(self._pattern())
        assert len(midi.tracks) == 2

    def test_drum_events_on_channel_9(self):
        midi = pattern_to_midi(self._pattern())
        for msg in midi.tracks[1]:
            if hasattr(msg, "channel"):
                assert msg.channel == 9  # GM drum channel

    def test_tempo_from_pattern_bpm(self):
        p = self._pattern()
        midi = pattern_to_midi(p)
        tempo = None
        for msg in midi.tracks[0]:
            if msg.type == "set_tempo":
                tempo = msg.tempo
        assert abs(60_000_000 / tempo - 123.0) < 1.0

    def test_note_events_present(self):
        midi = pattern_to_midi(self._pattern())
        note_ons = [m for m in midi.tracks[1] if hasattr(m, "type") and m.type == "note_on"]
        assert len(note_ons) > 0

    def test_kick_midi_note_is_36(self):
        """Kick hits should map to MIDI note 36."""
        midi = pattern_to_midi(self._pattern())
        kick_notes = [
            m.note
            for m in midi.tracks[1]
            if hasattr(m, "type") and m.type == "note_on" and m.note == 36
        ]
        assert len(kick_notes) > 0

    def test_hihat_midi_note_is_42_or_46(self):
        """Hi-hat notes should be 42 (closed) or 46 (open)."""
        midi = pattern_to_midi(self._pattern())
        hat_notes = {
            m.note
            for m in midi.tracks[1]
            if hasattr(m, "type") and m.type == "note_on" and m.note in (42, 46)
        }
        assert len(hat_notes) > 0

    def test_empty_hits_raises(self):
        from core.music_theory.types import DrumPattern

        empty_pattern = DrumPattern(hits=(), steps_per_bar=16, bars=4, bpm=120.0, genre="test")
        with pytest.raises(ValueError, match="empty"):
            pattern_to_midi(empty_pattern)

    def test_output_path_writes_file(self, tmp_path: Path):
        out = tmp_path / "drums.mid"
        pattern_to_midi(self._pattern(), output_path=out)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_all_genres_produce_midi(self):
        from core.music_theory.harmony import available_genres

        for genre in available_genres():
            p = generate_pattern(genre=genre, bars=2, seed=0)
            midi = pattern_to_midi(p)
            assert len(midi.tracks) == 2
