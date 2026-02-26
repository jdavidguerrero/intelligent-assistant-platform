"""
Tests for ingestion/audio_engine.py — AudioAnalysisEngine and FullComposition.

All tests use injected mock librosa so they run without an audio backend.
File I/O is eliminated via patch("ingestion.audio_engine.load_audio").

Test organisation:
    TestFullCompositionDataclass  — FullComposition field access and defaults
    TestAudioAnalysisEngineInit   — constructor and lazy-import behaviour
    TestAnalyzeSample             — Stage 1: spectral feature extraction
    TestExtractMelody             — Stage 2: pYIN melody pipeline
    TestMelodyToHarmony           — Stage 3: harmony generation
    TestGenerateBass              — Stage 4: bassline generation
    TestGenerateDrums             — Stage 5: drum pattern generation
    TestFullPipeline              — end-to-end integration with patched I/O
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from core.audio.types import Key, Note, SampleAnalysis, SpectralFeatures
from core.music_theory.types import BassNote, DrumPattern, VoicingResult
from ingestion.audio_engine import AudioAnalysisEngine, FullComposition

# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------


def _make_mock_librosa(bpm: float = 128.0, n_frames: int = 100) -> MagicMock:
    """Mock librosa for testing without audio backend.

    Returns a MagicMock configured with the standard return values that all
    AudioAnalysisEngine methods expect from librosa.
    """
    mock = MagicMock()

    y_harmonic = np.zeros(44100 * 5, dtype=np.float32)
    y_percussive = np.zeros(44100 * 5, dtype=np.float32)
    mock.effects.hpss.return_value = (y_harmonic, y_percussive)

    mock.beat.beat_track.return_value = (
        np.float64(bpm),
        np.array([10, 20, 30]),
    )

    # 12xN chroma — A (index 9) and E (index 4) and A (index 0 wrap) are strong
    chroma_row = [0.5, 0.1, 0.1, 0.1, 0.5, 0.1, 0.1, 0.5, 0.1, 0.1, 0.1, 0.1]
    mock.feature.chroma_cqt.return_value = np.tile(
        chroma_row,
        (1, n_frames),
    ).reshape(12, n_frames)

    mock.feature.rms.return_value = np.array([[0.1] * n_frames])

    mock.onset.onset_detect.return_value = np.array([0, 10, 20])

    mock.frames_to_time.return_value = np.linspace(0, 5, n_frames)

    # pYIN — 440 Hz (A4) voiced for all frames
    mock.pyin.return_value = (
        np.full(n_frames, 440.0, dtype=np.float64),  # f0_hz
        np.ones(n_frames, dtype=bool),  # voiced_flag
        np.ones(n_frames, dtype=np.float64),  # voiced_probs
    )

    return mock


def _make_audio() -> tuple[np.ndarray, int]:
    """Create a simple synthetic audio array (5 s at 44100 Hz)."""
    sr = 44100
    y = np.zeros(sr * 5, dtype=np.float32)
    return y, sr


def _fake_load_audio(
    _path: str | Path,
    *,
    duration: float = 30.0,
) -> tuple[np.ndarray, int]:
    """Replacement for load_audio that returns synthetic audio without I/O."""
    return _make_audio()


# ---------------------------------------------------------------------------
# TestFullCompositionDataclass
# ---------------------------------------------------------------------------


class TestFullCompositionDataclass:
    """FullComposition is a regular (mutable) dataclass with two optional fields."""

    def _make_composition(self) -> FullComposition:
        """Return a minimal but fully valid FullComposition for field tests."""
        from core.music_theory.harmony import suggest_progression

        sr = 44100
        duration_sec = 5.0
        analysis = SampleAnalysis(
            bpm=128.0,
            key=Key(root="A", mode="minor", confidence=0.9),
            energy=7,
            duration_sec=duration_sec,
            sample_rate=sr,
            notes=(),
            spectral=SpectralFeatures(
                chroma=tuple([0.0] * 12),
                rms=0.1,
                onsets_sec=(),
                tempo=128.0,
                beat_frames=(),
            ),
        )
        voicing = suggest_progression("A", genre="organic house", bars=4)
        return FullComposition(
            analysis=analysis,
            melody_notes=(),
            voicing=voicing,
            bass_notes=(),
            drum_pattern=DrumPattern(
                hits=(),
                steps_per_bar=16,
                bars=4,
                bpm=128.0,
                genre="organic house",
            ),
            bpm=128.0,
            genre="organic house",
            bars=4,
        )

    def test_full_composition_fields_accessible(self) -> None:
        """Each required field is readable after construction."""
        comp = self._make_composition()

        assert isinstance(comp.analysis, SampleAnalysis)
        assert isinstance(comp.melody_notes, tuple)
        assert isinstance(comp.voicing, VoicingResult)
        assert isinstance(comp.bass_notes, tuple)
        assert isinstance(comp.drum_pattern, DrumPattern)
        assert comp.bpm == 128.0
        assert comp.genre == "organic house"
        assert comp.bars == 4

    def test_full_composition_midi_paths_defaults_to_empty(self) -> None:
        """midi_paths defaults to an empty dict when not supplied."""
        comp = self._make_composition()
        assert comp.midi_paths == {}

    def test_full_composition_processing_time_defaults_to_zero(self) -> None:
        """processing_time_ms defaults to 0.0 when not supplied."""
        comp = self._make_composition()
        assert comp.processing_time_ms == 0.0

    def test_full_composition_is_mutable(self) -> None:
        """FullComposition is NOT frozen — its fields can be reassigned."""
        comp = self._make_composition()
        comp.bpm = 140.0
        assert comp.bpm == 140.0


# ---------------------------------------------------------------------------
# TestAudioAnalysisEngineInit
# ---------------------------------------------------------------------------


class TestAudioAnalysisEngineInit:
    """AudioAnalysisEngine construction and librosa lazy-import behaviour."""

    def test_init_without_librosa_stores_none(self) -> None:
        """Default construction leaves _librosa as None (lazy import deferred)."""
        engine = AudioAnalysisEngine()
        assert engine._librosa is None

    def test_init_with_injected_librosa(self) -> None:
        """Injected librosa is stored as-is, without importing real librosa."""
        mock_lib = _make_mock_librosa()
        engine = AudioAnalysisEngine(librosa=mock_lib)
        assert engine._librosa is mock_lib

    def test_get_librosa_returns_injected(self) -> None:
        """_get_librosa() returns the injected mock without importing."""
        mock_lib = _make_mock_librosa()
        engine = AudioAnalysisEngine(librosa=mock_lib)
        assert engine._get_librosa() is mock_lib


# ---------------------------------------------------------------------------
# TestAnalyzeSample
# ---------------------------------------------------------------------------


class TestAnalyzeSample:
    """Stage 1: analyze_sample() — spectral feature extraction from audio."""

    def test_analyze_sample_returns_sample_analysis(self) -> None:
        """Result is a SampleAnalysis instance."""
        mock_lib = _make_mock_librosa()
        engine = AudioAnalysisEngine(librosa=mock_lib)

        with patch("ingestion.audio_engine.load_audio", side_effect=_fake_load_audio):
            result = engine.analyze_sample("/fake/track.wav")

        assert isinstance(result, SampleAnalysis)

    def test_analyze_sample_bpm_matches_mock(self) -> None:
        """BPM in result matches the value returned by the mock beat tracker."""
        mock_lib = _make_mock_librosa(bpm=128.0)
        engine = AudioAnalysisEngine(librosa=mock_lib)

        with patch("ingestion.audio_engine.load_audio", side_effect=_fake_load_audio):
            result = engine.analyze_sample("/fake/track.wav")

        assert result.bpm == pytest.approx(128.0, abs=1.0)

    def test_analyze_sample_key_has_root_and_mode(self) -> None:
        """Detected key has a non-empty root and a valid mode string."""
        mock_lib = _make_mock_librosa()
        engine = AudioAnalysisEngine(librosa=mock_lib)

        with patch("ingestion.audio_engine.load_audio", side_effect=_fake_load_audio):
            result = engine.analyze_sample("/fake/track.wav")

        assert isinstance(result.key.root, str)
        assert len(result.key.root) >= 1
        assert result.key.mode in {"major", "minor"}

    def test_analyze_sample_energy_in_range(self) -> None:
        """Energy level is an integer in [0, 10]."""
        mock_lib = _make_mock_librosa()
        engine = AudioAnalysisEngine(librosa=mock_lib)

        with patch("ingestion.audio_engine.load_audio", side_effect=_fake_load_audio):
            result = engine.analyze_sample("/fake/track.wav")

        assert 0 <= result.energy <= 10

    def test_analyze_sample_without_melody_empty_notes(self) -> None:
        """include_melody=False (default) leaves result.notes as an empty tuple."""
        mock_lib = _make_mock_librosa()
        engine = AudioAnalysisEngine(librosa=mock_lib)

        with patch("ingestion.audio_engine.load_audio", side_effect=_fake_load_audio):
            result = engine.analyze_sample("/fake/track.wav", include_melody=False)

        assert result.notes == ()

    def test_analyze_sample_with_melody_has_notes(self) -> None:
        """include_melody=True triggers pYIN and populates result.notes."""
        mock_lib = _make_mock_librosa(bpm=128.0, n_frames=100)
        engine = AudioAnalysisEngine(librosa=mock_lib)

        with patch("ingestion.audio_engine.load_audio", side_effect=_fake_load_audio):
            result = engine.analyze_sample("/fake/track.wav", include_melody=True)

        # pyin returns voiced frames at 440 Hz — at least one Note expected
        assert len(result.notes) >= 1

    def test_analyze_sample_file_not_found(self) -> None:
        """FileNotFoundError from load_audio propagates to the caller."""
        mock_lib = _make_mock_librosa()
        engine = AudioAnalysisEngine(librosa=mock_lib)

        def _raise_fnf(path: str | Path, **kwargs: object) -> tuple[np.ndarray, int]:
            raise FileNotFoundError(f"No such file: {path}")

        with patch("ingestion.audio_engine.load_audio", side_effect=_raise_fnf):
            with pytest.raises(FileNotFoundError):
                engine.analyze_sample("/nonexistent/track.wav")

    def test_analyze_sample_duration_in_result(self) -> None:
        """duration_sec equals len(y) / sr from the loaded audio."""
        y, sr = _make_audio()  # 5 s at 44100 Hz
        expected_duration = len(y) / sr

        mock_lib = _make_mock_librosa()
        engine = AudioAnalysisEngine(librosa=mock_lib)

        with patch("ingestion.audio_engine.load_audio", side_effect=_fake_load_audio):
            result = engine.analyze_sample("/fake/track.wav")

        assert result.duration_sec == pytest.approx(expected_duration, abs=0.1)


# ---------------------------------------------------------------------------
# TestExtractMelody
# ---------------------------------------------------------------------------


class TestExtractMelody:
    """Stage 2: extract_melody() — pYIN-based monophonic note detection."""

    def test_extract_melody_returns_list(self) -> None:
        """Return type is a list (not a tuple)."""
        mock_lib = _make_mock_librosa()
        engine = AudioAnalysisEngine(librosa=mock_lib)

        with patch("ingestion.audio_engine.load_audio", side_effect=_fake_load_audio):
            result = engine.extract_melody("/fake/track.wav")

        assert isinstance(result, list)

    def test_extract_melody_notes_sorted_by_onset(self) -> None:
        """All notes are sorted by onset_sec in ascending order."""
        mock_lib = _make_mock_librosa()
        engine = AudioAnalysisEngine(librosa=mock_lib)

        with patch("ingestion.audio_engine.load_audio", side_effect=_fake_load_audio):
            notes = engine.extract_melody("/fake/track.wav")

        onsets = [n.onset_sec for n in notes]
        assert onsets == sorted(onsets)

    def test_extract_melody_pitches_in_valid_range(self) -> None:
        """Every detected Note has a MIDI pitch in [0, 127]."""
        mock_lib = _make_mock_librosa()
        engine = AudioAnalysisEngine(librosa=mock_lib)

        with patch("ingestion.audio_engine.load_audio", side_effect=_fake_load_audio):
            notes = engine.extract_melody("/fake/track.wav")

        for note in notes:
            assert 0 <= note.pitch_midi <= 127, f"pitch_midi {note.pitch_midi} out of [0, 127]"

    def test_extract_melody_empty_when_no_voice(self) -> None:
        """All voiced_flag=False from pyin → empty note list returned."""
        mock_lib = _make_mock_librosa()
        n_frames = 100
        # Override pyin to return no voiced frames
        mock_lib.pyin.return_value = (
            np.full(n_frames, 440.0, dtype=np.float64),
            np.zeros(n_frames, dtype=bool),  # no voiced frames
            np.zeros(n_frames, dtype=np.float64),
        )
        mock_lib.frames_to_time.return_value = np.linspace(0, 5, n_frames)
        engine = AudioAnalysisEngine(librosa=mock_lib)

        with patch("ingestion.audio_engine.load_audio", side_effect=_fake_load_audio):
            notes = engine.extract_melody("/fake/track.wav")

        assert notes == []

    def test_extract_melody_delegates_to_detect_melody(self) -> None:
        """librosa.pyin is called during extract_melody (verifies pYIN delegation)."""
        mock_lib = _make_mock_librosa()
        engine = AudioAnalysisEngine(librosa=mock_lib)

        with patch("ingestion.audio_engine.load_audio", side_effect=_fake_load_audio):
            engine.extract_melody("/fake/track.wav")

        assert mock_lib.pyin.called


# ---------------------------------------------------------------------------
# TestMelodyToHarmony
# ---------------------------------------------------------------------------


class TestMelodyToHarmony:
    """Stage 3: melody_to_harmony() — chord progression from notes or key alone."""

    def _make_notes(self, pitches: list[int]) -> list[Note]:
        """Build a list of Note objects at regular 0.5 s intervals."""
        return [
            Note(
                pitch_midi=p,
                pitch_name=f"N{p}",
                onset_sec=i * 0.5,
                duration_sec=0.4,
                velocity=80,
            )
            for i, p in enumerate(pitches)
        ]

    def test_melody_to_harmony_with_notes(self) -> None:
        """With melody notes provided, returns a VoicingResult."""
        engine = AudioAnalysisEngine()
        notes = self._make_notes([69, 71, 72, 74])  # A, B, C, D — A minor territory

        result = engine.melody_to_harmony(
            notes,
            key_root="A",
            key_mode="natural minor",
            genre="organic house",
            bars=4,
        )

        assert isinstance(result, VoicingResult)

    def test_melody_to_harmony_empty_notes_falls_back(self) -> None:
        """Empty notes list falls back to suggest_progression — still returns VoicingResult."""
        engine = AudioAnalysisEngine()

        result = engine.melody_to_harmony(
            [],
            key_root="A",
            key_mode="natural minor",
            genre="organic house",
            bars=4,
        )

        assert isinstance(result, VoicingResult)
        assert len(result.chords) == 4

    def test_melody_to_harmony_key_root_passed(self) -> None:
        """key_root is correctly threaded into the VoicingResult."""
        engine = AudioAnalysisEngine()

        result = engine.melody_to_harmony(
            [],
            key_root="A",
            genre="organic house",
            bars=4,
        )

        assert result.key_root == "A"

    def test_melody_to_harmony_bars_match(self) -> None:
        """Number of bars in result matches the bars argument."""
        engine = AudioAnalysisEngine()

        result = engine.melody_to_harmony(
            [],
            key_root="C",
            genre="organic house",
            bars=4,
        )

        assert result.bars == 4


# ---------------------------------------------------------------------------
# TestGenerateBass
# ---------------------------------------------------------------------------


class TestGenerateBass:
    """Stage 4: generate_bass() — rhythmic bass line from chord sequence."""

    def _get_chords(self) -> tuple:
        """Build a VoicingResult and extract its chords."""
        from core.music_theory.harmony import suggest_progression

        voicing = suggest_progression("A", genre="organic house", bars=4)
        return voicing.chords

    def test_generate_bass_returns_tuple_of_bass_notes(self) -> None:
        """Result is a tuple and every element is a BassNote."""
        engine = AudioAnalysisEngine()
        chords = self._get_chords()

        result = engine.generate_bass(chords, genre="organic house", bars=4, seed=42)

        assert isinstance(result, tuple)
        for note in result:
            assert isinstance(note, BassNote)

    def test_generate_bass_with_humanize_false(self) -> None:
        """humanize=False still returns a tuple of BassNote objects."""
        engine = AudioAnalysisEngine()
        chords = self._get_chords()

        result = engine.generate_bass(
            chords,
            genre="organic house",
            bars=4,
            humanize=False,
            seed=42,
        )

        assert isinstance(result, tuple)
        assert len(result) > 0

    def test_generate_bass_with_humanize_true(self) -> None:
        """humanize=True applies micro-timing and velocity variation."""
        engine = AudioAnalysisEngine()
        chords = self._get_chords()

        result = engine.generate_bass(
            chords,
            genre="organic house",
            bars=4,
            humanize=True,
            seed=42,
        )

        assert isinstance(result, tuple)
        assert len(result) > 0

    def test_generate_bass_seed_deterministic(self) -> None:
        """Same seed produces identical bass notes."""
        engine = AudioAnalysisEngine()
        chords = self._get_chords()

        result_a = engine.generate_bass(chords, genre="organic house", bars=4, seed=99)
        result_b = engine.generate_bass(chords, genre="organic house", bars=4, seed=99)

        assert result_a == result_b


# ---------------------------------------------------------------------------
# TestGenerateDrums
# ---------------------------------------------------------------------------


class TestGenerateDrums:
    """Stage 5: generate_drums() — genre-template drum pattern."""

    def test_generate_drums_returns_drum_pattern(self) -> None:
        """Result is a DrumPattern instance."""
        engine = AudioAnalysisEngine()

        result = engine.generate_drums(
            genre="organic house",
            energy=7,
            bars=4,
            bpm=128.0,
            seed=0,
        )

        assert isinstance(result, DrumPattern)

    def test_generate_drums_genre_stored(self) -> None:
        """DrumPattern.genre matches the requested genre."""
        engine = AudioAnalysisEngine()

        result = engine.generate_drums(
            genre="organic house",
            energy=5,
            bars=4,
            bpm=120.0,
            seed=0,
        )

        assert result.genre == "organic house"

    def test_generate_drums_bars_match(self) -> None:
        """DrumPattern.bars matches the requested bar count."""
        engine = AudioAnalysisEngine()

        result = engine.generate_drums(
            genre="organic house",
            energy=5,
            bars=4,
            bpm=120.0,
            seed=0,
        )

        assert result.bars == 4

    def test_generate_drums_energy_7_has_hits(self) -> None:
        """energy=7 produces at least one DrumHit."""
        engine = AudioAnalysisEngine()

        result = engine.generate_drums(
            genre="organic house",
            energy=7,
            bars=4,
            bpm=128.0,
            seed=0,
        )

        assert len(result.hits) > 0


# ---------------------------------------------------------------------------
# TestFullPipeline
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """End-to-end: full_pipeline() wires all five stages together."""

    def test_full_pipeline_returns_full_composition(self) -> None:
        """full_pipeline() returns a FullComposition."""
        mock_lib = _make_mock_librosa(bpm=128.0)
        engine = AudioAnalysisEngine(librosa=mock_lib)

        with patch("ingestion.audio_engine.load_audio", side_effect=_fake_load_audio):
            result = engine.full_pipeline(
                "/fake/track.wav",
                genre="organic house",
                bars=4,
                seed=42,
            )

        assert isinstance(result, FullComposition)

    def test_full_pipeline_bpm_from_detection(self) -> None:
        """When bpm override is None, composition.bpm comes from audio analysis."""
        mock_lib = _make_mock_librosa(bpm=128.0)
        engine = AudioAnalysisEngine(librosa=mock_lib)

        with patch("ingestion.audio_engine.load_audio", side_effect=_fake_load_audio):
            result = engine.full_pipeline(
                "/fake/track.wav",
                genre="organic house",
                bars=4,
                bpm=None,
                seed=0,
            )

        assert result.bpm == pytest.approx(128.0, abs=1.0)

    def test_full_pipeline_bpm_override(self) -> None:
        """When bpm=140.0 is passed, composition.bpm is 140.0 regardless of detected BPM."""
        mock_lib = _make_mock_librosa(bpm=128.0)
        engine = AudioAnalysisEngine(librosa=mock_lib)

        with patch("ingestion.audio_engine.load_audio", side_effect=_fake_load_audio):
            result = engine.full_pipeline(
                "/fake/track.wav",
                genre="organic house",
                bars=4,
                bpm=140.0,
                seed=0,
            )

        assert result.bpm == pytest.approx(140.0)

    def test_full_pipeline_midi_paths_empty_without_output_dir(self) -> None:
        """No MIDI files are written when output_dir is None; midi_paths is empty."""
        mock_lib = _make_mock_librosa()
        engine = AudioAnalysisEngine(librosa=mock_lib)

        with patch("ingestion.audio_engine.load_audio", side_effect=_fake_load_audio):
            result = engine.full_pipeline(
                "/fake/track.wav",
                genre="organic house",
                bars=4,
                output_dir=None,
                seed=0,
            )

        assert result.midi_paths == {}

    def test_full_pipeline_midi_paths_written_with_output_dir(
        self,
        tmp_path: Path,
    ) -> None:
        """With output_dir provided, midi_paths contains the 'arrangement' key."""
        mock_lib = _make_mock_librosa()
        engine = AudioAnalysisEngine(librosa=mock_lib)

        with patch("ingestion.audio_engine.load_audio", side_effect=_fake_load_audio):
            result = engine.full_pipeline(
                "/fake/track.wav",
                genre="organic house",
                bars=4,
                output_dir=str(tmp_path),
                seed=0,
            )

        assert "arrangement" in result.midi_paths
        assert Path(result.midi_paths["arrangement"]).exists()
