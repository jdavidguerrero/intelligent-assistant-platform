"""
Tests for core/audio/features.py — pure DSP feature extraction.

All tests mock librosa via patch.dict("sys.modules", ...) or direct injection.
No real audio files required.

Test pattern from tests/test_analyze_track_audio.py:
    mock = MagicMock()
    mock.load.return_value = (np.zeros(...), 44100)
    with patch.dict("sys.modules", {"librosa": mock}):
        ...
"""

from unittest.mock import MagicMock

import numpy as np
import pytest

from core.audio.features import (
    analyze_sample,
    extract_beat_frames,
    extract_bpm,
    extract_chroma,
    extract_energy_profile,
    extract_key,
    extract_onsets,
    separate_hpss,
)
from core.audio.types import Key, Note, SampleAnalysis, SpectralFeatures

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _make_mock_librosa(
    bpm: float = 128.0,
    n_frames: int = 100,
    rms: float = 0.1,
) -> MagicMock:
    """Build a mock librosa module with sane defaults for testing."""
    mock = MagicMock()
    n_samples = 44100 * 5
    y_zero = np.zeros(n_samples, dtype=np.float32)

    # librosa.load
    mock.load.return_value = (y_zero, 44100)

    # librosa.beat.beat_track → (tempo, beat_frames)
    mock.beat.beat_track.return_value = (
        np.float64(bpm),
        np.array([0, 22, 44, 66]),
    )

    # librosa.feature.chroma_cqt → (12, n_frames) uniform
    mock.feature.chroma_cqt.return_value = np.ones((12, n_frames)) / 12.0

    # librosa.feature.rms → (1, n_frames) constant
    mock.feature.rms.return_value = np.array([[rms] * n_frames])

    # librosa.effects.hpss → (harmonic, percussive)
    mock.effects.hpss.return_value = (y_zero.copy(), y_zero.copy())

    # librosa.onset.onset_detect → frame indices
    mock.onset.onset_detect.return_value = np.array([10, 20, 30, 40])

    # librosa.frames_to_time → convert frames to seconds
    mock.frames_to_time.side_effect = lambda frames, sr=44100: (
        np.array([f * 512 / sr for f in frames])
        if hasattr(frames, "__len__")
        else float(frames) * 512 / sr
    )

    return mock


def _make_a_minor_chroma() -> np.ndarray:
    """Return a chroma vector strongly weighted for A minor (K-S)."""
    from core.audio.features import _MINOR_PROFILE

    minor_arr = np.array(_MINOR_PROFILE)
    return np.roll(minor_arr, 9)  # root A = index 9


def _make_c_major_chroma() -> np.ndarray:
    """Return a chroma vector with C major scale degrees emphasized."""
    chroma = np.zeros(12)
    for idx in [0, 2, 4, 5, 7, 9, 11]:  # C D E F G A B
        chroma[idx] = 1.0
    return chroma


# ---------------------------------------------------------------------------
# separate_hpss
# ---------------------------------------------------------------------------


class TestSeparateHpss:
    def test_returns_two_arrays(self):
        """HPSS returns (harmonic, percussive) tuple."""
        y = np.zeros(44100, dtype=np.float32)
        mock = _make_mock_librosa()
        y_h, y_p = separate_hpss(y, 44100, librosa=mock)
        assert y_h is not None
        assert y_p is not None

    def test_calls_librosa_effects_hpss(self):
        """separate_hpss delegates to librosa.effects.hpss."""
        y = np.zeros(44100, dtype=np.float32)
        mock = _make_mock_librosa()
        separate_hpss(y, 44100, librosa=mock)
        mock.effects.hpss.assert_called_once_with(y)

    def test_returns_arrays_same_shape(self):
        """Harmonic and percussive have same shape as input."""
        n = 44100 * 5  # matches _make_mock_librosa default
        y = np.zeros(n, dtype=np.float32)
        mock = _make_mock_librosa()
        y_h, y_p = separate_hpss(y, 44100, librosa=mock)
        assert y_h.shape == y.shape
        assert y_p.shape == y.shape


# ---------------------------------------------------------------------------
# extract_chroma
# ---------------------------------------------------------------------------


class TestExtractChroma:
    def test_returns_12_element_array(self):
        """Chroma mean has exactly 12 elements."""
        y = np.zeros(44100, dtype=np.float32)
        mock = _make_mock_librosa()
        chroma = extract_chroma(y, 44100, librosa=mock)
        assert chroma.shape == (12,)

    def test_with_harmonic_calls_hpss_first(self):
        """use_harmonic=True → HPSS called before chroma_cqt."""
        y = np.zeros(44100, dtype=np.float32)
        mock = _make_mock_librosa()
        extract_chroma(y, 44100, librosa=mock, use_harmonic=True)
        mock.effects.hpss.assert_called_once()

    def test_without_harmonic_skips_hpss(self):
        """use_harmonic=False → HPSS NOT called."""
        y = np.zeros(44100, dtype=np.float32)
        mock = _make_mock_librosa()
        extract_chroma(y, 44100, librosa=mock, use_harmonic=False)
        mock.effects.hpss.assert_not_called()

    def test_chroma_values_are_floats(self):
        """Chroma mean contains float values."""
        y = np.zeros(44100, dtype=np.float32)
        mock = _make_mock_librosa()
        chroma = extract_chroma(y, 44100, librosa=mock, use_harmonic=False)
        assert chroma.dtype in [np.float32, np.float64]


# ---------------------------------------------------------------------------
# extract_key
# ---------------------------------------------------------------------------


class TestExtractKey:
    def test_returns_key_object(self):
        """extract_key returns a Key instance."""
        chroma = np.ones(12) / 12.0
        key = extract_key(chroma)
        assert isinstance(key, Key)

    def test_a_minor_profile_detected_as_a_minor(self):
        """K-S A minor profile → 'A minor'."""
        chroma = _make_a_minor_chroma()
        key = extract_key(chroma)
        assert key.mode == "minor"
        assert key.root == "A"
        assert key.label == "A minor"

    def test_c_major_scale_detected_as_c_major(self):
        """C major scale degrees emphasized → C major."""
        chroma = _make_c_major_chroma()
        key = extract_key(chroma)
        assert key.label == "C major"

    def test_confidence_in_valid_range(self):
        """Confidence is always in [0.0, 1.0]."""
        for _ in range(10):
            chroma = np.random.rand(12)
            key = extract_key(chroma)
            assert 0.0 <= key.confidence <= 1.0

    def test_mode_is_major_or_minor(self):
        """mode field is always 'major' or 'minor'."""
        chroma = np.random.rand(12)
        key = extract_key(chroma)
        assert key.mode in {"major", "minor"}

    def test_flat_chroma_still_returns_key(self):
        """Uniform chroma (no tonal centre) still returns some key."""
        chroma = np.ones(12) / 12.0
        key = extract_key(chroma)
        assert isinstance(key, Key)
        assert "major" in key.label or "minor" in key.label

    def test_raises_on_wrong_shape(self):
        """ValueError if chroma_mean is not shape (12,)."""
        with pytest.raises(ValueError, match="shape.*12"):
            extract_key(np.zeros(11))

    def test_raises_on_2d_input(self):
        """ValueError if chroma_mean is 2D."""
        with pytest.raises(ValueError, match="shape.*12"):
            extract_key(np.zeros((12, 10)))

    def test_minor_key_uses_flat_notation(self):
        """Bb minor uses 'Bb' not 'A#'."""
        from core.audio.features import _MINOR_PROFILE

        # A# minor = index 10 → should use Bb
        minor_arr = np.array(_MINOR_PROFILE)
        chroma = np.roll(minor_arr, 10)  # root A# = index 10
        key = extract_key(chroma)
        # Should be Bb minor, not A# minor
        if key.mode == "minor":
            assert key.root != "A#", "A# should be enharmonically spelled as Bb"

    def test_high_confidence_for_strong_tonal_signal(self):
        """K-S profile input gives high confidence."""
        chroma = _make_a_minor_chroma()
        key = extract_key(chroma)
        assert key.confidence > 0.5


# ---------------------------------------------------------------------------
# extract_bpm
# ---------------------------------------------------------------------------


class TestExtractBpm:
    def test_returns_bpm_float(self):
        """extract_bpm returns a float."""
        y = np.zeros(44100, dtype=np.float32)
        mock = _make_mock_librosa(bpm=128.0)
        bpm = extract_bpm(y, 44100, librosa=mock)
        assert isinstance(bpm, float)
        assert bpm == pytest.approx(128.0)

    def test_out_of_range_returns_zero(self):
        """BPM below 20 → 0.0 (invalid)."""
        y = np.zeros(44100, dtype=np.float32)
        mock = _make_mock_librosa(bpm=5.0)
        bpm = extract_bpm(y, 44100, librosa=mock)
        assert bpm == 0.0

    def test_exception_returns_zero(self):
        """librosa.beat.beat_track raising → returns 0.0, no exception."""
        y = np.zeros(44100, dtype=np.float32)
        mock = _make_mock_librosa()
        mock.beat.beat_track.side_effect = RuntimeError("no rhythm")
        bpm = extract_bpm(y, 44100, librosa=mock)
        assert bpm == 0.0

    def test_valid_range_accepted(self):
        """Any BPM in [20, 300] is returned as-is."""
        y = np.zeros(44100, dtype=np.float32)
        for expected_bpm in [20.0, 90.0, 128.0, 174.0, 300.0]:
            mock = _make_mock_librosa(bpm=expected_bpm)
            bpm = extract_bpm(y, 44100, librosa=mock)
            assert bpm == pytest.approx(expected_bpm)


# ---------------------------------------------------------------------------
# extract_energy_profile
# ---------------------------------------------------------------------------


class TestExtractEnergyProfile:
    def test_returns_integer(self):
        """Energy level is an integer."""
        y = np.zeros(44100, dtype=np.float32)
        mock = _make_mock_librosa(rms=0.1)
        energy = extract_energy_profile(y, librosa=mock)
        assert isinstance(energy, int)

    def test_in_valid_range(self):
        """Energy level is always in [0, 10]."""
        y = np.zeros(44100, dtype=np.float32)
        for rms_val in [0.001, 0.01, 0.05, 0.1, 0.3, 0.5]:
            mock = _make_mock_librosa(rms=rms_val)
            energy = extract_energy_profile(y, librosa=mock)
            assert 0 <= energy <= 10, f"Energy {energy} out of range for RMS {rms_val}"

    def test_high_rms_gives_high_energy(self):
        """RMS=0.3 (heavy club track) → energy ≥ 7."""
        y = np.zeros(44100, dtype=np.float32)
        mock = _make_mock_librosa(rms=0.3)
        energy = extract_energy_profile(y, librosa=mock)
        assert energy >= 7

    def test_low_rms_gives_low_energy(self):
        """RMS=0.003 (ambient) → energy ≤ 3."""
        y = np.zeros(44100, dtype=np.float32)
        mock = _make_mock_librosa(rms=0.003)
        energy = extract_energy_profile(y, librosa=mock)
        assert energy <= 3

    def test_zero_rms_returns_zero(self):
        """Complete silence (RMS=0) → 0."""
        y = np.zeros(44100, dtype=np.float32)
        mock = _make_mock_librosa(rms=0.0)
        energy = extract_energy_profile(y, librosa=mock)
        assert energy == 0


# ---------------------------------------------------------------------------
# extract_onsets
# ---------------------------------------------------------------------------


class TestExtractOnsets:
    def test_returns_tuple(self):
        """extract_onsets returns a tuple."""
        y = np.zeros(44100, dtype=np.float32)
        mock = _make_mock_librosa()
        onsets = extract_onsets(y, 44100, librosa=mock)
        assert isinstance(onsets, tuple)

    def test_calls_onset_detect(self):
        """onset_detect is called with percussive signal."""
        y = np.ones(44100, dtype=np.float32)
        mock = _make_mock_librosa()
        extract_onsets(y, 44100, librosa=mock)
        mock.onset.onset_detect.assert_called_once()

    def test_exception_returns_empty_tuple(self):
        """librosa.onset.onset_detect raising → empty tuple."""
        y = np.zeros(44100, dtype=np.float32)
        mock = _make_mock_librosa()
        mock.onset.onset_detect.side_effect = RuntimeError("onset error")
        onsets = extract_onsets(y, 44100, librosa=mock)
        assert onsets == ()

    def test_onsets_are_floats(self):
        """All onset times are floats in seconds."""
        y = np.zeros(44100, dtype=np.float32)
        mock = _make_mock_librosa()
        onsets = extract_onsets(y, 44100, librosa=mock)
        for t in onsets:
            assert isinstance(t, float)

    def test_onsets_sorted(self):
        """Onset times are sorted ascending."""
        y = np.zeros(44100, dtype=np.float32)
        mock = _make_mock_librosa()
        onsets = extract_onsets(y, 44100, librosa=mock)
        assert list(onsets) == sorted(onsets)


# ---------------------------------------------------------------------------
# extract_beat_frames
# ---------------------------------------------------------------------------


class TestExtractBeatFrames:
    def test_returns_tuple_of_ints(self):
        """Beat frames are integers in a tuple."""
        y = np.zeros(44100, dtype=np.float32)
        mock = _make_mock_librosa()
        frames = extract_beat_frames(y, 44100, librosa=mock)
        assert isinstance(frames, tuple)
        for f in frames:
            assert isinstance(f, int)

    def test_exception_returns_empty_tuple(self):
        """beat_track raising → empty tuple."""
        y = np.zeros(44100, dtype=np.float32)
        mock = _make_mock_librosa()
        mock.beat.beat_track.side_effect = RuntimeError("tracking error")
        frames = extract_beat_frames(y, 44100, librosa=mock)
        assert frames == ()

    def test_bpm_prior_passed_to_beat_track(self):
        """When bpm is provided, it is forwarded to beat_track."""
        y = np.zeros(44100, dtype=np.float32)
        mock = _make_mock_librosa()
        extract_beat_frames(y, 44100, librosa=mock, bpm=128.0)
        call_kwargs = mock.beat.beat_track.call_args[1]
        assert "bpm" in call_kwargs
        assert call_kwargs["bpm"] == 128.0

    def test_zero_bpm_not_forwarded(self):
        """bpm=0.0 is treated as 'no prior' — not forwarded."""
        y = np.zeros(44100, dtype=np.float32)
        mock = _make_mock_librosa()
        extract_beat_frames(y, 44100, librosa=mock, bpm=0.0)
        call_kwargs = mock.beat.beat_track.call_args[1]
        assert "bpm" not in call_kwargs


# ---------------------------------------------------------------------------
# analyze_sample (integration)
# ---------------------------------------------------------------------------


class TestAnalyzeSample:
    def test_returns_sample_analysis(self):
        """analyze_sample returns a SampleAnalysis instance."""
        y = np.zeros(44100 * 5, dtype=np.float32)
        mock = _make_mock_librosa(bpm=128.0, rms=0.1)
        result = analyze_sample(y, 44100, librosa=mock)
        assert isinstance(result, SampleAnalysis)

    def test_duration_computed_from_signal(self):
        """duration_sec = len(y) / sr."""
        n = 44100 * 3
        y = np.zeros(n, dtype=np.float32)
        mock = _make_mock_librosa()
        result = analyze_sample(y, 44100, librosa=mock)
        assert result.duration_sec == pytest.approx(3.0)

    def test_sample_rate_preserved(self):
        """sample_rate stored in result."""
        y = np.zeros(22050 * 5, dtype=np.float32)
        mock = _make_mock_librosa()
        result = analyze_sample(y, 22050, librosa=mock)
        assert result.sample_rate == 22050

    def test_bpm_populated(self):
        """BPM extracted from beat tracking."""
        y = np.zeros(44100 * 5, dtype=np.float32)
        mock = _make_mock_librosa(bpm=174.0)
        result = analyze_sample(y, 44100, librosa=mock)
        assert result.bpm == pytest.approx(174.0)

    def test_key_populated(self):
        """Key is detected and stored."""
        y = np.zeros(44100 * 5, dtype=np.float32)
        mock = _make_mock_librosa()
        result = analyze_sample(y, 44100, librosa=mock)
        assert isinstance(result.key, Key)
        assert result.key.mode in {"major", "minor"}

    def test_energy_in_valid_range(self):
        """Energy is 0–10."""
        y = np.zeros(44100 * 5, dtype=np.float32)
        mock = _make_mock_librosa(rms=0.1)
        result = analyze_sample(y, 44100, librosa=mock)
        assert 0 <= result.energy <= 10

    def test_spectral_is_populated(self):
        """SpectralFeatures is not None after analyze_sample."""
        y = np.zeros(44100 * 5, dtype=np.float32)
        mock = _make_mock_librosa()
        result = analyze_sample(y, 44100, librosa=mock)
        assert result.spectral is not None
        assert isinstance(result.spectral, SpectralFeatures)

    def test_chroma_has_12_elements(self):
        """spectral.chroma has 12 pitch class values."""
        y = np.zeros(44100 * 5, dtype=np.float32)
        mock = _make_mock_librosa()
        result = analyze_sample(y, 44100, librosa=mock)
        assert len(result.spectral.chroma) == 12

    def test_notes_empty_without_melody_fn(self):
        """Notes tuple is empty when detect_melody_fn not provided."""
        y = np.zeros(44100 * 5, dtype=np.float32)
        mock = _make_mock_librosa()
        result = analyze_sample(y, 44100, librosa=mock)
        assert result.notes == ()

    def test_notes_populated_with_melody_fn(self):
        """Notes are populated when detect_melody_fn is provided."""
        y = np.zeros(44100 * 5, dtype=np.float32)
        mock = _make_mock_librosa()

        sample_notes = [
            Note(pitch_midi=69, pitch_name="A4", onset_sec=0.0, duration_sec=0.5, velocity=80),
        ]

        def fake_melody(y, sr, *, librosa):
            return sample_notes

        result = analyze_sample(y, 44100, librosa=mock, detect_melody_fn=fake_melody)
        assert len(result.notes) == 1
        assert result.notes[0].pitch_midi == 69

    def test_melody_fn_exception_does_not_crash(self):
        """If detect_melody_fn raises, analyze_sample still returns results."""
        y = np.zeros(44100 * 5, dtype=np.float32)
        mock = _make_mock_librosa()

        def broken_melody(y, sr, *, librosa):
            raise RuntimeError("pyin failed")

        result = analyze_sample(y, 44100, librosa=mock, detect_melody_fn=broken_melody)
        assert isinstance(result, SampleAnalysis)
        assert result.notes == ()
