"""
Tests for librosa audio analysis path in analyze_track.

All tests mock librosa to avoid requiring real audio files.
The mock pattern: patch sys.modules["librosa"] for cascade tests,
inject mock directly into private methods for unit tests.
"""

from unittest.mock import MagicMock, patch

import numpy as np

from tools.music.analyze_track import AnalyzeTrack

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_librosa(
    bpm: float = 128.0,
    n_frames: int = 100,
    rms_value: float = 0.1,
) -> MagicMock:
    """Build a mock librosa module with sane defaults."""
    mock = MagicMock()
    # librosa.load → (y, sr)
    mock.load.return_value = (np.zeros(44100 * 5, dtype=np.float32), 44100)
    # librosa.beat.beat_track → (tempo, beat_frames)
    mock.beat.beat_track.return_value = (np.float64(bpm), np.array([]))
    # librosa.feature.chroma_cens → (12, n_frames) uniform distribution
    mock.feature.chroma_cens.return_value = np.ones((12, n_frames)) / 12.0
    # librosa.feature.rms → (1, n_frames) constant RMS
    mock.feature.rms.return_value = np.array([[rms_value] * n_frames])
    return mock


# ---------------------------------------------------------------------------
# Tests for _analyze_with_librosa() private method
# ---------------------------------------------------------------------------


class TestLibrosaDirectMethod:
    """Unit tests for _analyze_with_librosa() cascade guard conditions."""

    def test_returns_none_when_file_not_found(self):
        """Non-existent file → None (falls through to filename parsing)."""
        tool = AnalyzeTrack()
        result = tool._analyze_with_librosa("/nonexistent/track.mp3")
        assert result is None

    def test_returns_none_for_unsupported_extension(self, tmp_path):
        """PDF or other non-audio extension → None."""
        doc = tmp_path / "notes.pdf"
        doc.write_bytes(b"not audio")

        tool = AnalyzeTrack()
        result = tool._analyze_with_librosa(str(doc))
        assert result is None

    def test_returns_none_when_audio_corrupt(self, tmp_path):
        """librosa.load raising an exception → None."""
        audio_file = tmp_path / "corrupt.mp3"
        audio_file.write_bytes(b"this is not valid audio data")

        mock_librosa = _make_mock_librosa()
        mock_librosa.load.side_effect = Exception("no audio backend")

        tool = AnalyzeTrack()
        with patch.dict("sys.modules", {"librosa": mock_librosa}):
            result = tool._analyze_with_librosa(str(audio_file))

        assert result is None

    def test_successful_analysis_returns_dict(self, tmp_path):
        """librosa succeeds → dict with all required keys."""
        audio_file = tmp_path / "track.mp3"
        audio_file.write_bytes(b"fake mp3")

        mock_librosa = _make_mock_librosa(bpm=128.0, rms_value=0.1)
        tool = AnalyzeTrack()

        with patch.dict("sys.modules", {"librosa": mock_librosa}):
            result = tool._analyze_with_librosa(str(audio_file))

        assert result is not None
        assert "bpm" in result
        assert "key" in result
        assert "energy" in result
        assert "duration_analyzed" in result

    def test_bpm_correct_value(self, tmp_path):
        """BPM should be rounded integer matching mocked tempo."""
        audio_file = tmp_path / "track.mp3"
        audio_file.write_bytes(b"fake mp3")

        mock_librosa = _make_mock_librosa(bpm=132.7)
        tool = AnalyzeTrack()

        with patch.dict("sys.modules", {"librosa": mock_librosa}):
            result = tool._analyze_with_librosa(str(audio_file))

        assert result is not None
        assert result["bpm"] == 133  # rounded

    def test_bpm_out_of_range_returns_unknown(self, tmp_path):
        """BPM below 20 → 'unknown'."""
        audio_file = tmp_path / "track.mp3"
        audio_file.write_bytes(b"fake mp3")

        mock_librosa = _make_mock_librosa(bpm=5.0)
        tool = AnalyzeTrack()

        with patch.dict("sys.modules", {"librosa": mock_librosa}):
            result = tool._analyze_with_librosa(str(audio_file))

        assert result is not None
        assert result["bpm"] == "unknown"

    def test_supported_extensions_accepted(self, tmp_path):
        """All supported audio extensions should pass the guard."""
        extensions = [".mp3", ".wav", ".flac", ".aiff", ".ogg"]
        tool = AnalyzeTrack()

        for ext in extensions:
            audio_file = tmp_path / f"track{ext}"
            audio_file.write_bytes(b"fake audio")

            mock_librosa = _make_mock_librosa()
            with patch.dict("sys.modules", {"librosa": mock_librosa}):
                tool._analyze_with_librosa(str(audio_file))

            # The key check: no premature None from extension rejection
            mock_librosa.load.assert_called_once()
            mock_librosa.load.reset_mock()


# ---------------------------------------------------------------------------
# Tests for analyze_audio parameter
# ---------------------------------------------------------------------------


class TestAnalyzeAudioParameter:
    """Test the analyze_audio=False bypass and parameter spec."""

    def test_analyze_audio_false_skips_librosa(self, tmp_path):
        """analyze_audio=False → directly uses filename parsing, no librosa call."""
        audio_file = tmp_path / "track_128bpm.mp3"
        audio_file.write_bytes(b"fake audio")

        tool = AnalyzeTrack()
        result = tool(file_path=str(audio_file), analyze_audio=False)

        assert result.success is True
        assert result.metadata["source"] == "filename_parsing"
        assert result.data["bpm"] == 128

    def test_analyze_audio_defaults_to_true_but_falls_back(self):
        """Default behavior tries audio analysis; non-existent file falls back."""
        tool = AnalyzeTrack()
        # Non-existent file: librosa returns None → filename fallback
        result = tool(file_path="track_128bpm.mp3")
        assert result.success is True
        assert result.metadata["source"] == "filename_parsing"

    def test_tool_has_two_parameters(self):
        """Tool exposes file_path and analyze_audio."""
        tool = AnalyzeTrack()
        names = [p.name for p in tool.parameters]
        assert "file_path" in names
        assert "analyze_audio" in names

    def test_analyze_audio_is_optional_with_default_true(self):
        """analyze_audio must be optional and default True."""
        tool = AnalyzeTrack()
        param = next(p for p in tool.parameters if p.name == "analyze_audio")
        assert param.required is False
        assert param.default is True


# ---------------------------------------------------------------------------
# Tests for key detection algorithm
# ---------------------------------------------------------------------------


class TestKeyDetection:
    """Unit tests for _detect_key_from_audio (Krumhansl-Schmuckler)."""

    def test_c_major_chroma_detected_as_c_major(self):
        """Chroma profile emphasising C-major scale → C major."""
        tool = AnalyzeTrack()

        # C major scale degrees: C D E F G A B → indices 0 2 4 5 7 9 11
        chroma = np.zeros((12, 100))
        for idx in [0, 2, 4, 5, 7, 9, 11]:
            chroma[idx, :] = 1.0

        mock_librosa = MagicMock()
        mock_librosa.feature.chroma_cens.return_value = chroma

        key = tool._detect_key_from_audio(y=np.zeros(44100), sr=44100, librosa=mock_librosa)
        assert key == "C major"

    def test_a_minor_chroma_detected_as_a_minor(self):
        """Chroma weighted by Krumhansl-Schmuckler A-minor profile → A minor."""
        from tools.music.analyze_track import _MINOR_PROFILE

        tool = AnalyzeTrack()

        # Feed the exact K-S minor profile rotated to root A (index 9).
        # This is the ground-truth input that must produce "A minor".
        a_minor_profile = np.roll(np.array(_MINOR_PROFILE), 9)
        chroma = np.tile(a_minor_profile[:, np.newaxis], (1, 100))

        mock_librosa = MagicMock()
        mock_librosa.feature.chroma_cens.return_value = chroma

        key = tool._detect_key_from_audio(y=np.zeros(44100), sr=44100, librosa=mock_librosa)
        assert key == "A minor"

    def test_returns_valid_key_string(self):
        """Should always return a string containing 'major' or 'minor'."""
        tool = AnalyzeTrack()

        mock_librosa = MagicMock()
        mock_librosa.feature.chroma_cens.return_value = np.random.rand(12, 50)

        key = tool._detect_key_from_audio(y=np.zeros(22050), sr=22050, librosa=mock_librosa)

        assert isinstance(key, str)
        assert "major" in key or "minor" in key

    def test_flat_chroma_still_returns_a_key(self):
        """Uniform chroma (no tonal centre) still picks the closest match."""
        tool = AnalyzeTrack()

        mock_librosa = MagicMock()
        mock_librosa.feature.chroma_cens.return_value = np.ones((12, 100)) / 12.0

        key = tool._detect_key_from_audio(y=np.zeros(44100), sr=44100, librosa=mock_librosa)

        assert isinstance(key, str)
        assert "major" in key or "minor" in key


# ---------------------------------------------------------------------------
# Tests for energy computation
# ---------------------------------------------------------------------------


class TestEnergyComputation:
    """Unit tests for _compute_energy RMS normalization."""

    def test_high_rms_maps_to_high_energy(self):
        """RMS ≈ 0.3 (heavy club track) → energy ≥ 7."""
        tool = AnalyzeTrack()
        mock_librosa = MagicMock()
        mock_librosa.feature.rms.return_value = np.array([[0.3] * 100])

        energy = tool._compute_energy(y=np.zeros(44100), librosa=mock_librosa)

        assert isinstance(energy, int)
        assert energy >= 7

    def test_low_rms_maps_to_low_energy(self):
        """RMS ≈ 0.003 (quiet ambient) → energy ≤ 3."""
        tool = AnalyzeTrack()
        mock_librosa = MagicMock()
        mock_librosa.feature.rms.return_value = np.array([[0.003] * 100])

        energy = tool._compute_energy(y=np.zeros(44100), librosa=mock_librosa)

        assert isinstance(energy, int)
        assert energy <= 3

    def test_zero_rms_returns_unknown(self):
        """Complete silence (RMS = 0) → 'unknown'."""
        tool = AnalyzeTrack()
        mock_librosa = MagicMock()
        mock_librosa.feature.rms.return_value = np.array([[0.0] * 100])

        energy = tool._compute_energy(y=np.zeros(44100), librosa=mock_librosa)

        assert energy == "unknown"

    def test_energy_always_in_0_10_range(self):
        """Extreme RMS values clamp to [0, 10]."""
        tool = AnalyzeTrack()
        mock_librosa = MagicMock()

        for extreme_rms in [0.0001, 99.0]:
            mock_librosa.feature.rms.return_value = np.array([[extreme_rms] * 100])
            energy = tool._compute_energy(y=np.zeros(44100), librosa=mock_librosa)
            if isinstance(energy, int):
                assert 0 <= energy <= 10


# ---------------------------------------------------------------------------
# Tests for full cascade integration
# ---------------------------------------------------------------------------


class TestCascadeFallback:
    """Integration tests for the two-level cascade."""

    def test_nonexistent_file_falls_back_to_filename(self):
        """File not on disk → filename parsing, metadata source = 'filename_parsing'."""
        tool = AnalyzeTrack()
        result = tool(file_path="track_128bpm_Aminor.mp3")

        assert result.success is True
        assert result.metadata["source"] == "filename_parsing"
        assert result.data["bpm"] == 128
        assert result.data["key"] == "A minor"

    def test_librosa_returns_none_falls_back(self, tmp_path):
        """Corrupt audio → librosa returns None → filename fallback."""
        audio_file = tmp_path / "track_128bpm.mp3"
        audio_file.write_bytes(b"garbage")

        mock_librosa = _make_mock_librosa()
        mock_librosa.load.side_effect = Exception("decode error")

        tool = AnalyzeTrack()
        with patch.dict("sys.modules", {"librosa": mock_librosa}):
            result = tool(file_path=str(audio_file))

        assert result.success is True
        assert result.metadata["source"] == "filename_parsing"
        assert result.data["bpm"] == 128  # from filename

    def test_audio_analysis_source_when_librosa_succeeds(self, tmp_path):
        """Successful librosa → metadata source = 'audio_analysis'."""
        audio_file = tmp_path / "track.mp3"
        audio_file.write_bytes(b"fake mp3")

        mock_librosa = _make_mock_librosa(bpm=130.0, rms_value=0.12)
        tool = AnalyzeTrack()

        with patch.dict("sys.modules", {"librosa": mock_librosa}):
            result = tool(file_path=str(audio_file))

        assert result.success is True
        assert result.metadata["source"] == "audio_analysis"
        assert result.metadata["method"] == "librosa"
        assert result.data["bpm"] == 130

    def test_duration_analyzed_in_metadata(self, tmp_path):
        """Successful librosa analysis includes duration_analyzed in metadata."""
        audio_file = tmp_path / "track.mp3"
        audio_file.write_bytes(b"fake mp3")

        mock_librosa = _make_mock_librosa()
        tool = AnalyzeTrack()

        with patch.dict("sys.modules", {"librosa": mock_librosa}):
            result = tool(file_path=str(audio_file))

        assert result.success is True
        assert "duration_analyzed" in result.metadata
        assert isinstance(result.metadata["duration_analyzed"], float)

    def test_audio_analysis_confidence_high_when_all_fields_found(self, tmp_path):
        """librosa finds BPM + key + energy → confidence 'high'."""
        audio_file = tmp_path / "track.mp3"
        audio_file.write_bytes(b"fake mp3")

        # Use C-major chroma so key is deterministically found
        chroma = np.zeros((12, 100))
        for idx in [0, 2, 4, 5, 7, 9, 11]:
            chroma[idx, :] = 1.0

        mock_librosa = _make_mock_librosa(bpm=128.0, rms_value=0.1)
        mock_librosa.feature.chroma_cens.return_value = chroma

        tool = AnalyzeTrack()
        with patch.dict("sys.modules", {"librosa": mock_librosa}):
            result = tool(file_path=str(audio_file))

        assert result.success is True
        assert result.data["confidence"] == "high"
