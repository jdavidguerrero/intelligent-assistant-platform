"""
Tests for core/audio/melody.py — pYIN melody detection pipeline.

Tests cover:
    - Pure utility functions (_hz_to_midi, _midi_to_name, _group_voiced_frames)
    - detect_melody() integration with mock pYIN
    - Edge cases: silence, very short notes, polyphonic hints, no voiced frames
"""

from unittest.mock import MagicMock

import numpy as np
import pytest

from core.audio.melody import (
    _group_voiced_frames,
    _hz_to_midi,
    _midi_to_name,
    detect_melody,
)
from core.audio.types import Note

# ---------------------------------------------------------------------------
# _hz_to_midi
# ---------------------------------------------------------------------------


class TestHzToMidi:
    def test_a4_is_69(self):
        """A4 = 440 Hz = MIDI 69 by definition."""
        assert _hz_to_midi(440.0) == 69

    def test_c4_is_60(self):
        """C4 = 261.63 Hz = MIDI 60."""
        assert _hz_to_midi(261.63) == 60

    def test_c5_is_72(self):
        """C5 = 523.25 Hz = MIDI 72."""
        assert _hz_to_midi(523.25) == 72

    def test_a3_is_57(self):
        """A3 = 220.0 Hz = MIDI 57."""
        assert _hz_to_midi(220.0) == 57

    def test_clamps_to_127(self):
        """Very high frequency is clamped to 127."""
        result = _hz_to_midi(100000.0)
        assert result == 127

    def test_clamps_to_0(self):
        """Very low frequency is clamped to 0."""
        result = _hz_to_midi(0.001)
        assert result == 0

    def test_raises_on_zero_hz(self):
        """Hz = 0 raises ValueError."""
        with pytest.raises(ValueError, match="Hz must be > 0"):
            _hz_to_midi(0.0)

    def test_raises_on_negative_hz(self):
        """Negative Hz raises ValueError."""
        with pytest.raises(ValueError, match="Hz must be > 0"):
            _hz_to_midi(-440.0)

    def test_returns_int(self):
        """Return type is int."""
        assert isinstance(_hz_to_midi(440.0), int)


# ---------------------------------------------------------------------------
# _midi_to_name
# ---------------------------------------------------------------------------


class TestMidiToName:
    def test_a4(self):
        """MIDI 69 → 'A4'."""
        assert _midi_to_name(69) == "A4"

    def test_c4(self):
        """MIDI 60 → 'C4'."""
        assert _midi_to_name(60) == "C4"

    def test_c5(self):
        """MIDI 72 → 'C5'."""
        assert _midi_to_name(72) == "C5"

    def test_c_sharp_4(self):
        """MIDI 61 → 'C#4'."""
        assert _midi_to_name(61) == "C#4"

    def test_a0_lowest_piano(self):
        """MIDI 21 → 'A0'."""
        assert _midi_to_name(21) == "A0"

    def test_returns_string(self):
        """Return type is string."""
        assert isinstance(_midi_to_name(60), str)

    def test_all_midi_return_strings(self):
        """All valid MIDI numbers return a non-empty string."""
        for midi in range(128):
            name = _midi_to_name(midi)
            assert isinstance(name, str)
            assert len(name) > 0


# ---------------------------------------------------------------------------
# _group_voiced_frames
# ---------------------------------------------------------------------------


class TestGroupVoicedFrames:
    def _make_inputs(
        self,
        voiced_pattern: list[bool],
        hz: float = 440.0,
        sr: int = 44100,
        hop_length: int = 512,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        n = len(voiced_pattern)
        f0_hz = np.array([hz if v else np.nan for v in voiced_pattern])
        voiced_flag = np.array(voiced_pattern)
        frame_times = np.array([i * hop_length / sr for i in range(n)])
        return f0_hz, voiced_flag, frame_times

    def test_all_voiced_returns_one_segment(self):
        """Continuous voiced signal → single segment."""
        # 100 voiced frames ≈ 1.16 seconds at 44100/512
        f0, vf, ft = self._make_inputs([True] * 100)
        segments = _group_voiced_frames(f0, vf, ft, min_duration_sec=0.05)
        assert len(segments) == 1
        assert segments[0] == (0, 99)

    def test_all_silent_returns_empty(self):
        """All unvoiced → empty list."""
        f0, vf, ft = self._make_inputs([False] * 50)
        segments = _group_voiced_frames(f0, vf, ft, min_duration_sec=0.05)
        assert segments == []

    def test_gap_splits_into_two_segments(self):
        """Voiced–gap–voiced → 2 segments."""
        pattern = [True] * 50 + [False] * 10 + [True] * 50
        f0, vf, ft = self._make_inputs(pattern)
        segments = _group_voiced_frames(f0, vf, ft, min_duration_sec=0.05)
        assert len(segments) == 2

    def test_short_segment_filtered(self):
        """Segment shorter than min_duration_sec is discarded."""
        # 2 voiced frames ≈ 23 ms — below 50 ms threshold
        pattern = [True] * 2
        f0, vf, ft = self._make_inputs(pattern)
        segments = _group_voiced_frames(f0, vf, ft, min_duration_sec=0.05)
        assert segments == []

    def test_nan_f0_treated_as_unvoiced(self):
        """NaN in f0 → treated as unvoiced even if voiced_flag is True."""
        n = 50
        f0_hz = np.array([440.0] * 25 + [np.nan] * 25)
        voiced_flag = np.ones(n, dtype=bool)  # all True
        frame_times = np.array([i * 512 / 44100 for i in range(n)])
        segments = _group_voiced_frames(f0_hz, voiced_flag, frame_times, 0.05)
        # NaN frames break the segment at frame 25
        assert len(segments) == 1
        assert segments[0][0] == 0
        assert segments[0][1] == 24

    def test_segments_sorted_by_start(self):
        """Segments are returned in ascending order."""
        pattern = [True] * 30 + [False] * 5 + [True] * 30 + [False] * 5 + [True] * 30
        f0, vf, ft = self._make_inputs(pattern)
        segments = _group_voiced_frames(f0, vf, ft, min_duration_sec=0.05)
        starts = [s[0] for s in segments]
        assert starts == sorted(starts)


# ---------------------------------------------------------------------------
# detect_melody — mock pYIN integration
# ---------------------------------------------------------------------------


def _make_pyin_mock(
    n_frames: int = 200,
    hz: float = 440.0,
    voiced_fraction: float = 0.8,
    sr: int = 44100,
    hop_length: int = 512,
) -> MagicMock:
    """Build a mock librosa with controlled pYIN output."""
    mock = MagicMock()

    n_voiced = int(n_frames * voiced_fraction)
    f0 = np.array([hz] * n_voiced + [np.nan] * (n_frames - n_voiced), dtype=np.float64)
    voiced_flag = np.array([True] * n_voiced + [False] * (n_frames - n_voiced))
    voiced_probs = np.where(voiced_flag, 0.9, 0.1)

    mock.pyin.return_value = (f0, voiced_flag, voiced_probs)
    mock.frames_to_time.side_effect = lambda frames, sr, hop_length: (
        np.array([f * hop_length / sr for f in frames])
    )
    mock.feature.rms.return_value = np.array([[0.1] * 10])

    return mock


class TestDetectMelody:
    def test_returns_list(self):
        """detect_melody always returns a list."""
        y = np.zeros(44100 * 5, dtype=np.float32)
        mock = _make_pyin_mock()
        result = detect_melody(y, 44100, librosa=mock)
        assert isinstance(result, list)

    def test_silent_audio_returns_empty(self):
        """No voiced frames → empty list."""
        y = np.zeros(44100 * 5, dtype=np.float32)
        mock = _make_pyin_mock(voiced_fraction=0.0)
        result = detect_melody(y, 44100, librosa=mock)
        assert result == []

    def test_single_sustained_note_detected(self):
        """Continuous voiced signal at 440 Hz → at least one A4 note."""
        y = np.zeros(44100 * 5, dtype=np.float32)
        mock = _make_pyin_mock(n_frames=200, hz=440.0, voiced_fraction=1.0)
        result = detect_melody(y, 44100, librosa=mock)
        assert len(result) >= 1
        # All notes should be A4 (MIDI 69)
        for note in result:
            assert note.pitch_midi == 69
            assert note.pitch_name == "A4"

    def test_notes_sorted_by_onset(self):
        """Notes in result are sorted by onset_sec."""
        y = np.zeros(44100 * 5, dtype=np.float32)
        mock = _make_pyin_mock()
        result = detect_melody(y, 44100, librosa=mock)
        onsets = [n.onset_sec for n in result]
        assert onsets == sorted(onsets)

    def test_velocity_in_valid_range(self):
        """All detected notes have velocity in [0, 127]."""
        y = np.zeros(44100 * 5, dtype=np.float32)
        mock = _make_pyin_mock()
        result = detect_melody(y, 44100, librosa=mock)
        for note in result:
            assert 0 <= note.velocity <= 127, f"Velocity {note.velocity} out of range"

    def test_duration_positive(self):
        """All detected notes have duration_sec > 0."""
        y = np.zeros(44100 * 5, dtype=np.float32)
        mock = _make_pyin_mock()
        result = detect_melody(y, 44100, librosa=mock)
        for note in result:
            assert note.duration_sec > 0.0, f"Non-positive duration: {note.duration_sec}"

    def test_onset_sec_non_negative(self):
        """All onset times are ≥ 0."""
        y = np.zeros(44100 * 5, dtype=np.float32)
        mock = _make_pyin_mock()
        result = detect_melody(y, 44100, librosa=mock)
        for note in result:
            assert note.onset_sec >= 0.0

    def test_all_notes_are_note_objects(self):
        """All items in result are Note instances."""
        y = np.zeros(44100 * 5, dtype=np.float32)
        mock = _make_pyin_mock()
        result = detect_melody(y, 44100, librosa=mock)
        for item in result:
            assert isinstance(item, Note)

    def test_pyin_exception_returns_empty(self):
        """pYIN raising an exception → empty list (no crash)."""
        y = np.zeros(44100 * 5, dtype=np.float32)
        mock = MagicMock()
        mock.pyin.side_effect = RuntimeError("pyin failed")
        result = detect_melody(y, 44100, librosa=mock)
        assert result == []

    def test_empty_f0_returns_empty(self):
        """Empty pYIN output → empty list."""
        y = np.zeros(44100 * 5, dtype=np.float32)
        mock = MagicMock()
        mock.pyin.return_value = (np.array([]), np.array([]), np.array([]))
        mock.frames_to_time.return_value = np.array([])
        result = detect_melody(y, 44100, librosa=mock)
        assert result == []

    def test_short_notes_filtered(self):
        """Notes shorter than MIN_NOTE_DURATION_SEC are discarded."""
        y = np.zeros(44100 * 5, dtype=np.float32)
        sr = 44100

        # 2 voiced frames → duration ≈ 2 × 512/44100 ≈ 23 ms < 50 ms
        f0 = np.array([440.0, 440.0], dtype=np.float64)
        voiced_flag = np.array([True, True])
        voiced_probs = np.array([0.9, 0.9])

        mock = MagicMock()
        mock.pyin.return_value = (f0, voiced_flag, voiced_probs)
        mock.frames_to_time.side_effect = lambda frames, sr, hop_length: (
            np.array([f * hop_length / sr for f in frames])
        )
        mock.feature.rms.return_value = np.array([[0.1]])

        result = detect_melody(y, sr, librosa=mock)
        # 2 frames at 512/44100 ≈ 23 ms — below 50 ms threshold
        assert result == []

    def test_multiple_notes_from_gap_in_voiced_frames(self):
        """Gap in voiced frames → multiple distinct notes."""
        y = np.zeros(44100 * 5, dtype=np.float32)
        sr = 44100

        # Two 50-frame voiced regions separated by 20 unvoiced frames
        # Duration: 50 × 512/44100 ≈ 0.58 s each — well above threshold
        n_voiced = 50
        n_gap = 20

        f0 = np.array(
            [440.0] * n_voiced + [np.nan] * n_gap + [523.25] * n_voiced,
            dtype=np.float64,
        )
        voiced_flag = np.array([True] * n_voiced + [False] * n_gap + [True] * n_voiced)
        voiced_probs = np.where(voiced_flag, 0.9, 0.1)

        mock = MagicMock()
        mock.pyin.return_value = (f0, voiced_flag, voiced_probs)
        mock.frames_to_time.side_effect = lambda frames, sr, hop_length: (
            np.array([f * hop_length / sr for f in frames])
        )
        mock.feature.rms.return_value = np.array([[0.1] * 20])

        result = detect_melody(y, sr, librosa=mock)
        assert len(result) == 2
        assert result[0].pitch_midi == 69  # A4 = 440 Hz
        assert result[1].pitch_midi == 72  # C5 = 523.25 Hz

    def test_pitch_midi_in_valid_range(self):
        """All detected MIDI pitches are in [0, 127]."""
        y = np.zeros(44100 * 5, dtype=np.float32)
        mock = _make_pyin_mock()
        result = detect_melody(y, 44100, librosa=mock)
        for note in result:
            assert 0 <= note.pitch_midi <= 127
