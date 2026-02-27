"""
Tests for ingestion/audio_loader.py — file I/O boundary.

All tests mock librosa.load() via patch.dict("sys.modules", ...) to avoid
requiring real audio files or audio backend.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from ingestion.audio_loader import AUDIO_EXTENSIONS, DEFAULT_DURATION, load_audio

# ---------------------------------------------------------------------------
# Mock helper
# ---------------------------------------------------------------------------


def _make_mock_librosa(sr: int = 44100, n_samples: int = 44100 * 5) -> MagicMock:
    """Return a mock librosa module that simulates a successful load."""
    mock = MagicMock()
    y = np.zeros(n_samples, dtype=np.float32)
    mock.load.return_value = (y, sr)
    return mock


# ---------------------------------------------------------------------------
# Error conditions
# ---------------------------------------------------------------------------


class TestLoadAudioErrors:
    def test_raises_file_not_found(self):
        """Non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="not found"):
            load_audio("/nonexistent/track.mp3")

    def test_raises_value_error_for_unsupported_extension(self, tmp_path):
        """PDF or unsupported format raises ValueError."""
        doc = tmp_path / "notes.pdf"
        doc.write_bytes(b"not audio")
        with pytest.raises(ValueError, match="Unsupported audio format"):
            load_audio(doc)

    def test_raises_value_error_for_txt_file(self, tmp_path):
        """.txt raises ValueError even if file exists."""
        txt = tmp_path / "lyrics.txt"
        txt.write_text("some text")
        with pytest.raises(ValueError, match="Unsupported"):
            load_audio(txt)

    def test_raises_runtime_error_on_librosa_failure(self, tmp_path):
        """librosa.load() raising an exception → RuntimeError."""
        audio_file = tmp_path / "corrupt.mp3"
        audio_file.write_bytes(b"not valid audio data")

        mock_librosa = _make_mock_librosa()
        mock_librosa.load.side_effect = Exception("decode error")

        with patch.dict("sys.modules", {"librosa": mock_librosa}):
            with pytest.raises(RuntimeError, match="Failed to decode"):
                load_audio(audio_file)


# ---------------------------------------------------------------------------
# Successful loading
# ---------------------------------------------------------------------------


class TestLoadAudioSuccess:
    def test_returns_y_and_sr(self, tmp_path):
        """Successful load returns (y, sr) tuple."""
        audio_file = tmp_path / "track.mp3"
        audio_file.write_bytes(b"fake mp3")

        mock_librosa = _make_mock_librosa(sr=44100, n_samples=44100 * 5)
        with patch.dict("sys.modules", {"librosa": mock_librosa}):
            y, sr = load_audio(audio_file)

        assert isinstance(y, np.ndarray)
        assert isinstance(sr, int)
        assert sr == 44100

    def test_sr_is_int_not_numpy_int(self, tmp_path):
        """Sample rate returned as Python int, not numpy integer."""
        audio_file = tmp_path / "track.wav"
        audio_file.write_bytes(b"fake wav")

        mock_librosa = _make_mock_librosa(sr=22050)
        with patch.dict("sys.modules", {"librosa": mock_librosa}):
            _, sr = load_audio(audio_file)

        assert type(sr) is int

    def test_passes_duration_to_librosa(self, tmp_path):
        """duration parameter is forwarded to librosa.load()."""
        audio_file = tmp_path / "track.flac"
        audio_file.write_bytes(b"fake flac")

        mock_librosa = _make_mock_librosa()
        with patch.dict("sys.modules", {"librosa": mock_librosa}):
            load_audio(audio_file, duration=15.0)

        call_kwargs = mock_librosa.load.call_args[1]
        assert call_kwargs["duration"] == 15.0

    def test_default_duration_is_30(self, tmp_path):
        """Default duration is DEFAULT_DURATION (30 seconds)."""
        audio_file = tmp_path / "track.mp3"
        audio_file.write_bytes(b"fake")

        mock_librosa = _make_mock_librosa()
        with patch.dict("sys.modules", {"librosa": mock_librosa}):
            load_audio(audio_file)

        call_kwargs = mock_librosa.load.call_args[1]
        assert call_kwargs["duration"] == DEFAULT_DURATION

    def test_accepts_string_path(self, tmp_path):
        """Path can be a plain string."""
        audio_file = tmp_path / "track.mp3"
        audio_file.write_bytes(b"fake")

        mock_librosa = _make_mock_librosa()
        with patch.dict("sys.modules", {"librosa": mock_librosa}):
            y, sr = load_audio(str(audio_file))

        assert y is not None


# ---------------------------------------------------------------------------
# Extension coverage
# ---------------------------------------------------------------------------


class TestAudioExtensions:
    def test_audio_extensions_constant_is_frozenset(self):
        """AUDIO_EXTENSIONS is a frozenset."""
        assert isinstance(AUDIO_EXTENSIONS, frozenset)

    def test_common_formats_supported(self):
        """All common audio formats are in AUDIO_EXTENSIONS."""
        for ext in [".mp3", ".wav", ".flac", ".aiff", ".ogg", ".m4a"]:
            assert ext in AUDIO_EXTENSIONS, f"{ext} missing from AUDIO_EXTENSIONS"

    def test_all_extensions_are_lowercase(self):
        """All extensions are lowercase for case-insensitive comparison."""
        for ext in AUDIO_EXTENSIONS:
            assert ext == ext.lower(), f"Extension {ext!r} is not lowercase"

    @pytest.mark.parametrize("ext", [".mp3", ".wav", ".flac", ".ogg"])
    def test_supported_extension_calls_librosa(self, tmp_path, ext):
        """Each supported extension passes the guard and calls librosa.load."""
        audio_file = tmp_path / f"track{ext}"
        audio_file.write_bytes(b"fake audio")

        mock_librosa = _make_mock_librosa()
        with patch.dict("sys.modules", {"librosa": mock_librosa}):
            load_audio(audio_file)

        mock_librosa.load.assert_called_once()
