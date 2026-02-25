"""
ingestion/audio_loader.py — File I/O boundary for audio loading.

This is the ONLY module in the audio pipeline that reads files from disk.
Everything downstream (core/audio/features.py, core/audio/melody.py) takes
pre-loaded (y, sr) arrays — never file paths.

Usage:
    from ingestion.audio_loader import load_audio
    y, sr = load_audio("/path/to/track.mp3", duration=30.0)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    pass

# Supported audio file extensions (must be loadable by librosa / soundfile)
AUDIO_EXTENSIONS: frozenset[str] = frozenset(
    {".mp3", ".wav", ".flac", ".aiff", ".aif", ".ogg", ".m4a", ".opus"}
)

# Default: load only the first N seconds to avoid OOM on full-length tracks
DEFAULT_DURATION: float = 30.0


def load_audio(
    path: str | Path,
    *,
    duration: float = DEFAULT_DURATION,
    sr: int | None = None,
    mono: bool = True,
) -> tuple[np.ndarray, int]:
    """Load an audio file and return (y, sr).

    This is the I/O boundary — the only function in the audio pipeline
    that touches the filesystem. All downstream functions operate on
    the returned numpy array.

    Args:
        path: Absolute or relative path to an audio file.
              Supported formats: mp3, wav, flac, aiff, ogg, m4a, opus.
        duration: Maximum seconds to load. Prevents OOM on long tracks.
                  Pass None to load the entire file (use with caution).
        sr: Target sample rate in Hz. None preserves the native rate.
        mono: Mix down to mono when True (default). Stereo files become
              a single-channel float32 array.

    Returns:
        (y, sr) — float32 numpy array of audio samples and sample rate.

    Raises:
        FileNotFoundError: File does not exist at the given path.
        ValueError: File extension is not a supported audio format.
        RuntimeError: librosa/soundfile could not decode the file
                      (corrupted, truncated, DRM-protected, etc.).
    """
    import librosa  # deferred to allow testing without audio backend

    file_path = Path(path)

    if not file_path.exists():
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    if file_path.suffix.lower() not in AUDIO_EXTENSIONS:
        raise ValueError(
            f"Unsupported audio format {file_path.suffix!r}. "
            f"Supported: {sorted(AUDIO_EXTENSIONS)}"
        )

    try:
        y, loaded_sr = librosa.load(
            file_path,
            sr=sr,
            mono=mono,
            duration=duration,
            offset=0.0,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Failed to decode audio file {file_path.name!r}: {exc}"
        ) from exc

    return y, int(loaded_sr)
