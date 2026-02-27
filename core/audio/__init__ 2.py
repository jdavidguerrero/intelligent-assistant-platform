"""
core/audio — Pure audio analysis module.

Provides DSP functions for extracting musical features from audio signals.
All functions are pure: they take (y: np.ndarray, sr: int) and return
structured data. No file I/O — that lives in ingestion/audio_loader.py.

Architecture note:
    numpy and librosa are DSP-pure libraries (no I/O, no side effects).
    Their use in core/audio/ mirrors tiktoken's use in core/chunking.py.
    librosa is always injected as a parameter — never imported at module top —
    so tests can mock it without installing the full audio stack.

Public API:
    Types:      Note, Key, SampleAnalysis, SpectralFeatures
    Features:   analyze_sample
    Melody:     detect_melody
"""

from core.audio.types import Key, Note, SampleAnalysis, SpectralFeatures

__all__ = [
    "Note",
    "Key",
    "SampleAnalysis",
    "SpectralFeatures",
]
