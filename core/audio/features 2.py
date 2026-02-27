"""
core/audio/features.py — Pure DSP feature extraction from audio signals.

All functions accept (y: np.ndarray, sr: int) and return structured data.
`librosa` is always injected as a parameter — never imported at module top —
so this module is testable without installing the audio stack.

Design:
    - `separate_hpss()` separates harmonic and percussive content first.
      All downstream features benefit from this: key detection uses the
      harmonic signal, onset detection uses the percussive signal.
    - `extract_key()` is pure numpy — no librosa dependency. It takes a
      pre-computed chroma_mean vector and runs Krumhansl-Schmuckler.
    - `analyze_sample()` is the high-level aggregator. It wires all the
      individual extractors together. Pass `detect_melody_fn` to include
      melody notes in the result.

Krumhansl-Schmuckler profiles (1990):
    Psychoacoustic salience weights for each of 12 pitch classes
    relative to a tonal centre. Pearson correlation against all 24
    key templates (12 major + 12 minor) selects the best match.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import numpy as np

from core.audio.types import Key, Note, SampleAnalysis, SpectralFeatures

# ---------------------------------------------------------------------------
# Krumhansl-Schmuckler profiles (1990)
# Starting from C — 12-element salience weights
# ---------------------------------------------------------------------------

_MAJOR_PROFILE: tuple[float, ...] = (
    6.35,
    2.23,
    3.48,
    2.33,
    4.38,
    4.09,
    2.52,
    5.19,
    2.39,
    3.66,
    2.29,
    2.88,
)
_MINOR_PROFILE: tuple[float, ...] = (
    6.33,
    2.68,
    3.52,
    5.38,
    2.60,
    3.53,
    2.54,
    4.75,
    3.98,
    2.69,
    3.34,
    3.17,
)

# Chromatic note names (sharps notation)
_NOTE_NAMES: tuple[str, ...] = (
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "A#",
    "B",
)

# Preferred flat spellings for minor keys
_ENHARMONIC_MINOR: dict[str, str] = {
    "A#": "Bb",
    "D#": "Eb",
    "G#": "Ab",
}

# RMS log-scale normalization bounds (same as tools/music/analyze_track.py)
_LOG_MIN: float = -3.0  # log10(0.001) — very quiet
_LOG_MAX: float = -0.3  # log10(0.5)   — loud club track


# ---------------------------------------------------------------------------
# HPSS — Harmonic-Percussive Source Separation
# ---------------------------------------------------------------------------


def separate_hpss(
    y: np.ndarray,
    sr: int,
    *,
    librosa: Any,
) -> tuple[np.ndarray, np.ndarray]:
    """Separate audio into harmonic and percussive components (HPSS).

    Harmonic signal: tonal content (melody, chords, bass).
    Percussive signal: transient content (drums, snares, percussion).

    Using the harmonic signal for key/chroma and the percussive signal
    for onset detection significantly improves accuracy of both.

    Args:
        y: Audio time series (mono, float32)
        sr: Sample rate in Hz (unused by HPSS but kept for API consistency)
        librosa: Injected librosa module

    Returns:
        (y_harmonic, y_percussive) — both same shape as y
    """
    y_harmonic, y_percussive = librosa.effects.hpss(y)
    return y_harmonic, y_percussive


# ---------------------------------------------------------------------------
# Chroma extraction
# ---------------------------------------------------------------------------


def extract_chroma(
    y: np.ndarray,
    sr: int,
    *,
    librosa: Any,
    use_harmonic: bool = True,
) -> np.ndarray:
    """Extract mean CQT-based chromagram from audio.

    Computes a Constant-Q Transform chromagram and averages over time
    to produce a 12-element pitch class distribution.

    CQT chromagram is preferred over STFT-based for key detection:
    it has logarithmic frequency resolution that aligns with musical
    pitch perception.

    Args:
        y: Audio time series (mono, float32)
        sr: Sample rate in Hz
        librosa: Injected librosa module
        use_harmonic: If True, separate HPSS first for cleaner chroma.
                      Default True.

    Returns:
        np.ndarray of shape (12,) — mean pitch class energies.
        Values are not normalized (raw chroma energy).
    """
    y_input = y
    if use_harmonic:
        y_harmonic, _ = separate_hpss(y, sr, librosa=librosa)
        y_input = y_harmonic

    chroma = librosa.feature.chroma_cqt(y=y_input, sr=sr)
    return np.mean(chroma, axis=1)  # shape (12,)


# ---------------------------------------------------------------------------
# Key detection — pure numpy, no librosa
# ---------------------------------------------------------------------------


def extract_key(chroma_mean: np.ndarray) -> Key:
    """Detect musical key using Krumhansl-Schmuckler profiles.

    Pearson-correlates the 12-element chroma distribution against all
    24 key templates (12 major + 12 minor, each rotated to align with
    a different root). The best correlation wins.

    This function has NO librosa dependency — it is pure numpy.

    Args:
        chroma_mean: np.ndarray of shape (12,) — pitch class distribution.
                     Typically the output of extract_chroma().

    Returns:
        Key with root, mode, and confidence (best Pearson r).
        Confidence 0.0 is returned for flat/silent chroma input.

    Raises:
        ValueError: If chroma_mean is not shape (12,).
    """
    if chroma_mean.shape != (12,):
        raise ValueError(f"chroma_mean must have shape (12,), got {chroma_mean.shape}")

    best_score: float = -2.0  # Pearson r ∈ [-1, 1]
    best_root: str = "C"
    best_mode: str = "major"

    major_arr = np.array(_MAJOR_PROFILE)
    minor_arr = np.array(_MINOR_PROFILE)

    for root_idx in range(12):
        major_profile = np.roll(major_arr, root_idx)
        minor_profile = np.roll(minor_arr, root_idx)

        # errstate suppresses RuntimeWarning when chroma has zero variance
        # (flat/silent input → NaN → nan_to_num → 0.0)
        with np.errstate(invalid="ignore"):
            major_r = float(np.nan_to_num(np.corrcoef(chroma_mean, major_profile)[0, 1]))
            minor_r = float(np.nan_to_num(np.corrcoef(chroma_mean, minor_profile)[0, 1]))

        if major_r > best_score:
            best_score = major_r
            best_root = _NOTE_NAMES[root_idx]
            best_mode = "major"

        if minor_r > best_score:
            best_score = minor_r
            # Prefer flat notation for certain minor keys
            best_root = _ENHARMONIC_MINOR.get(_NOTE_NAMES[root_idx], _NOTE_NAMES[root_idx])
            best_mode = "minor"

    confidence = max(0.0, min(1.0, best_score))
    return Key(root=best_root, mode=best_mode, confidence=confidence)


# ---------------------------------------------------------------------------
# BPM extraction
# ---------------------------------------------------------------------------


def extract_bpm(
    y: np.ndarray,
    sr: int,
    *,
    librosa: Any,
) -> float:
    """Estimate tempo (BPM) via beat tracking.

    Uses librosa.beat.beat_track() on the full signal. For cleaner
    results, pass the percussive component from separate_hpss().

    Args:
        y: Audio time series (mono, float32)
        sr: Sample rate in Hz
        librosa: Injected librosa module

    Returns:
        BPM as float. Returns 0.0 if detection fails or result is
        outside the realistic range [20, 300].
    """
    try:
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(tempo)
        if 20.0 <= bpm <= 300.0:
            return bpm
        return 0.0
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Energy level
# ---------------------------------------------------------------------------


def extract_energy_profile(
    y: np.ndarray,
    *,
    librosa: Any,
) -> int:
    """Compute perceptual energy level (0–10) from RMS.

    Uses log10 normalization over the range [0.001, 0.5] RMS to map
    to [0, 10]. This matches the formula in tools/music/analyze_track.py
    for consistent energy reporting across both pipelines.

    Args:
        y: Audio time series (mono, float32)
        librosa: Injected librosa module

    Returns:
        Integer 0–10. Returns 0 for silence (RMS ≤ 0).
    """
    try:
        rms_frames = librosa.feature.rms(y=y)
        rms_mean = float(np.mean(rms_frames))
    except Exception:
        return 0

    if rms_mean <= 0.0:
        return 0

    log_rms = math.log10(max(rms_mean, 1e-6))
    normalized = (log_rms - _LOG_MIN) / (_LOG_MAX - _LOG_MIN)
    return int(round(max(0.0, min(10.0, normalized * 10.0))))


# ---------------------------------------------------------------------------
# Onset detection
# ---------------------------------------------------------------------------


def extract_onsets(
    y_percussive: np.ndarray,
    sr: int,
    *,
    librosa: Any,
) -> tuple[float, ...]:
    """Detect note onset times from percussive signal.

    Onset strength function + peak picking on the percussive component.
    Using the percussive signal reduces false positives from tonal attacks.

    Args:
        y_percussive: Percussive component (from separate_hpss())
        sr: Sample rate in Hz
        librosa: Injected librosa module

    Returns:
        Sorted tuple of onset times in seconds.
        Empty tuple if detection fails or no onsets found.
    """
    try:
        onset_frames = librosa.onset.onset_detect(
            y=y_percussive,
            sr=sr,
            units="frames",
        )
        onset_times = librosa.frames_to_time(onset_frames, sr=sr)
        return tuple(sorted(float(t) for t in onset_times))
    except Exception:
        return ()


# ---------------------------------------------------------------------------
# Beat frames
# ---------------------------------------------------------------------------


def extract_beat_frames(
    y: np.ndarray,
    sr: int,
    *,
    librosa: Any,
    bpm: float | None = None,
) -> tuple[int, ...]:
    """Detect beat frame positions.

    Args:
        y: Audio time series (mono, float32)
        sr: Sample rate in Hz
        librosa: Injected librosa module
        bpm: Optional prior BPM to guide beat tracking. If None,
             beat_track() estimates it from the signal.

    Returns:
        Sorted tuple of beat frame indices.
        Empty tuple if detection fails.
    """
    try:
        kwargs: dict[str, Any] = {"y": y, "sr": sr}
        if bpm is not None and bpm > 0:
            kwargs["bpm"] = bpm
        _, beat_frames = librosa.beat.beat_track(**kwargs)
        return tuple(int(f) for f in beat_frames)
    except Exception:
        return ()


# ---------------------------------------------------------------------------
# Full analysis aggregator
# ---------------------------------------------------------------------------


def analyze_sample(
    y: np.ndarray,
    sr: int,
    *,
    librosa: Any,
    detect_melody_fn: Callable[..., list[Note]] | None = None,
) -> SampleAnalysis:
    """Full sample analysis pipeline.

    Runs all feature extractors in order and assembles a SampleAnalysis.
    This is the primary entry point for callers who want all features.

    Pipeline:
        1. HPSS → y_harmonic, y_percussive
        2. extract_bpm(y, sr)
        3. extract_chroma(y_harmonic, sr) → chroma_mean
        4. extract_key(chroma_mean) → Key
        5. extract_onsets(y_percussive, sr)
        6. extract_beat_frames(y, sr, bpm)
        7. extract_energy_profile(y)
        8. detect_melody_fn(y_harmonic, sr) if provided → notes

    Args:
        y: Audio time series (mono, float32)
        sr: Sample rate in Hz
        librosa: Injected librosa module
        detect_melody_fn: Optional callable (y, sr, *, librosa) → list[Note].
                          Pass core.audio.melody.detect_melody to include
                          melody detection. None = skip (notes=[]).

    Returns:
        SampleAnalysis with all extracted features populated.
    """
    duration_sec = float(len(y)) / float(sr)

    # Step 1: HPSS
    y_harmonic, y_percussive = separate_hpss(y, sr, librosa=librosa)

    # Step 2: BPM
    bpm = extract_bpm(y, sr, librosa=librosa)

    # Step 3+4: Chroma → Key
    chroma_mean = extract_chroma(y_harmonic, sr, librosa=librosa, use_harmonic=False)
    key = extract_key(chroma_mean)

    # Step 5: Onsets
    onsets_sec = extract_onsets(y_percussive, sr, librosa=librosa)

    # Step 6: Beat frames
    beat_frames = extract_beat_frames(y, sr, librosa=librosa, bpm=bpm if bpm > 0 else None)

    # Step 7: Energy
    energy = extract_energy_profile(y, librosa=librosa)

    spectral = SpectralFeatures(
        chroma=tuple(float(c) for c in chroma_mean),
        rms=float(np.mean(librosa.feature.rms(y=y))),
        onsets_sec=onsets_sec,
        tempo=bpm,
        beat_frames=beat_frames,
    )

    # Step 8: Optional melody detection
    notes: tuple[Note, ...] = ()
    if detect_melody_fn is not None:
        try:
            detected = detect_melody_fn(y_harmonic, sr, librosa=librosa)
            notes = tuple(detected)
        except Exception:
            pass  # melody detection is best-effort

    return SampleAnalysis(
        bpm=bpm,
        key=key,
        energy=energy,
        duration_sec=duration_sec,
        sample_rate=sr,
        notes=notes,
        spectral=spectral,
    )
