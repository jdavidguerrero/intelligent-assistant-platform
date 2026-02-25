"""
Integration tests for Week 13 — Bass + Drums + suggest_progression + MIDI export.

Tests the complete pipeline:
    melody → chords → bass → drums → 3 MIDI files

Also validates:
    - All 5 genres × 2 keys produce valid output
    - __init__ exports for Week 13 additions
    - Round-trip: generate → export → MIDI structure valid
    - suggest_progression integrates with bass + drums
    - DrumPattern + VoicingResult frozen invariants hold after full pipeline
"""

from __future__ import annotations

from pathlib import Path

import mido
import pytest

from core.music_theory import (
    DRUM_INSTRUMENTS,
    BassNote,
    DrumHit,
    DrumPattern,
    VoicingResult,
    available_genres,
    generate_bassline,
    generate_pattern,
    get_diatonic_chords,
    suggest_progression,
)
from ingestion.midi_export import (
    DRUM_CHANNEL,
    bassline_to_midi,
    chords_to_midi,
    pattern_to_midi,
)

# ---------------------------------------------------------------------------
# __init__ exports — Week 13 additions
# ---------------------------------------------------------------------------


class TestWeek13Exports:
    def test_bass_note_importable(self):
        assert BassNote is not None

    def test_drum_hit_importable(self):
        assert DrumHit is not None

    def test_drum_pattern_importable(self):
        assert DrumPattern is not None

    def test_drum_instruments_importable(self):
        assert DRUM_INSTRUMENTS is not None
        assert isinstance(DRUM_INSTRUMENTS, frozenset)

    def test_generate_bassline_importable(self):
        from core.music_theory import generate_bassline as gb

        assert callable(gb)

    def test_generate_pattern_importable(self):
        from core.music_theory import generate_pattern as gp

        assert callable(gp)

    def test_suggest_progression_importable(self):
        from core.music_theory import suggest_progression as sp

        assert callable(sp)


# ---------------------------------------------------------------------------
# Full pipeline: chords → bass → drums → 3 MIDI files
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """melody → chords → bass → drums → MIDI export pipeline."""

    def _run_pipeline(self, key_root: str, genre: str, tmp_path: Path) -> dict:
        bpm = 123.0
        bars = 4

        # 1. Suggest progression (no melody needed)
        voicing = suggest_progression(key_root, genre=genre, bars=bars)
        assert isinstance(voicing, VoicingResult)
        assert len(voicing.chords) == bars

        # 2. Generate bass line from chords
        bass = generate_bassline(
            voicing.chords,
            genre=genre,
            bars=bars,
            humanize=True,
            seed=42,
        )
        assert isinstance(bass, tuple)
        assert all(isinstance(n, BassNote) for n in bass)

        # 3. Generate drum pattern
        pattern = generate_pattern(
            bpm=bpm,
            genre=genre,
            bars=bars,
            energy=7,
            humanize=True,
            seed=42,
        )
        assert isinstance(pattern, DrumPattern)

        # 4. Export all 3 to MIDI
        chord_midi = chords_to_midi(voicing, bpm=bpm, output_path=tmp_path / "chords.mid")
        bass_midi = bassline_to_midi(bass, bpm=bpm, output_path=tmp_path / "bass.mid")
        drums_midi = pattern_to_midi(pattern, output_path=tmp_path / "drums.mid")

        return {
            "voicing": voicing,
            "bass": bass,
            "pattern": pattern,
            "chord_midi": chord_midi,
            "bass_midi": bass_midi,
            "drums_midi": drums_midi,
        }

    def test_full_pipeline_a_minor_organic_house(self, tmp_path: Path):
        result = self._run_pipeline("A", "organic house", tmp_path)
        assert isinstance(result["chord_midi"], mido.MidiFile)
        assert isinstance(result["bass_midi"], mido.MidiFile)
        assert isinstance(result["drums_midi"], mido.MidiFile)

    def test_midi_files_written_to_disk(self, tmp_path: Path):
        self._run_pipeline("A", "organic house", tmp_path)
        assert (tmp_path / "chords.mid").exists()
        assert (tmp_path / "bass.mid").exists()
        assert (tmp_path / "drums.mid").exists()

    def test_all_midi_files_non_empty(self, tmp_path: Path):
        self._run_pipeline("C", "deep house", tmp_path)
        for name in ("chords.mid", "bass.mid", "drums.mid"):
            assert (tmp_path / name).stat().st_size > 0

    def test_drum_midi_channel_9(self, tmp_path: Path):
        result = self._run_pipeline("A", "melodic techno", tmp_path)
        drum_channels = {
            msg.channel for msg in result["drums_midi"].tracks[1] if hasattr(msg, "channel")
        }
        assert drum_channels == {DRUM_CHANNEL}

    def test_chord_midi_channel_0(self, tmp_path: Path):
        result = self._run_pipeline("A", "organic house", tmp_path)
        chord_channels = {
            msg.channel for msg in result["chord_midi"].tracks[1] if hasattr(msg, "channel")
        }
        assert chord_channels == {0}


# ---------------------------------------------------------------------------
# All genres × 2 keys
# ---------------------------------------------------------------------------


class TestAllGenresAndKeys:
    @pytest.mark.parametrize("genre", available_genres())
    @pytest.mark.parametrize("key_root", ["A", "C"])
    def test_pipeline_runs_for_all_genres_and_keys(self, genre: str, key_root: str, tmp_path: Path):
        voicing = suggest_progression(key_root, genre=genre, bars=4)
        bass = generate_bassline(voicing.chords, genre=genre, seed=0)
        pattern = generate_pattern(genre=genre, bars=4, seed=0)

        chord_midi = chords_to_midi(voicing, bpm=120.0)
        bass_midi = bassline_to_midi(bass, bpm=120.0)
        drums_midi = pattern_to_midi(pattern)

        assert isinstance(chord_midi, mido.MidiFile)
        assert isinstance(bass_midi, mido.MidiFile)
        assert isinstance(drums_midi, mido.MidiFile)


# ---------------------------------------------------------------------------
# Temporal alignment: all 3 MIDIs same bar count
# ---------------------------------------------------------------------------


class TestTemporalAlignment:
    def test_chord_and_bass_span_same_bars(self):
        bars = 4
        voicing = suggest_progression("A", genre="organic house", bars=bars)
        bass = generate_bassline(voicing.chords, genre="organic house", bars=bars, seed=0)
        # Bass: max bar index + 1 == bars
        assert max(n.bar for n in bass) + 1 == bars

    def test_drum_pattern_bars_match(self):
        bars = 8
        pattern = generate_pattern(genre="organic house", bars=bars, seed=0)
        assert pattern.bars == bars
        assert max(h.bar for h in pattern.hits) + 1 == bars

    def test_voicing_chord_count_matches_bars(self):
        bars = 4
        voicing = suggest_progression("A", bars=bars)
        assert len(voicing.chords) == bars


# ---------------------------------------------------------------------------
# Immutability throughout pipeline
# ---------------------------------------------------------------------------


class TestImmutability:
    def test_bass_notes_are_frozen(self):
        chords = list(get_diatonic_chords("A", "natural minor"))[:4]
        bass = generate_bassline(chords, genre="organic house", seed=0)
        with pytest.raises((TypeError, AttributeError)):
            bass[0].pitch_midi = 99  # type: ignore[misc]

    def test_drum_hits_are_frozen(self):
        pattern = generate_pattern(genre="organic house", bars=1, seed=0)
        with pytest.raises((TypeError, AttributeError)):
            pattern.hits[0].velocity = 99  # type: ignore[misc]

    def test_drum_pattern_is_frozen(self):
        pattern = generate_pattern(genre="organic house", bars=1, seed=0)
        with pytest.raises((TypeError, AttributeError)):
            pattern.bars = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Regression: Week 12 APIs still work
# ---------------------------------------------------------------------------


class TestWeek12Regression:
    def test_melody_to_chords_still_works(self):
        from core.music_theory import melody_to_chords

        result = melody_to_chords([], key_root="A", bars=4)
        assert isinstance(result, VoicingResult)

    def test_optimize_voice_leading_still_works(self):
        from core.music_theory import VoicedChord, optimize_voice_leading

        chords = get_diatonic_chords("A", "natural minor")[:4]
        voiced = optimize_voice_leading(chords)
        assert all(isinstance(v, VoicedChord) for v in voiced)

    def test_notes_to_midi_still_works(self):
        from core.audio.types import Note
        from ingestion.midi_export import notes_to_midi

        notes = [Note(pitch_midi=69, pitch_name="A4", onset_sec=0.0, duration_sec=0.5, velocity=80)]
        midi = notes_to_midi(notes, bpm=120.0)
        assert isinstance(midi, mido.MidiFile)
