"""
core/mix_analysis/transients.py — Transient analysis for mix diagnostics.

Measures transient density (onsets/sec), attack sharpness, and the ratio
of time spent in attack vs. sustain phases.

Design:
    - Pure: numpy array + sr → TransientProfile.
    - Spectral flux onset detection is used (no librosa dependency).
    - Handles both mono (N,) and stereo (2, N) inputs.
"""

from __future__ import annotations

import numpy as np

from core.mix_analysis.types import TransientProfile

_EPS = 1e-10


# ---------------------------------------------------------------------------
# Onset detection via spectral flux
# ---------------------------------------------------------------------------


def _spectral_flux_onsets(
    y: np.ndarray,
    sr: int,
    n_fft: int = 2048,
    hop: int = 512,
    threshold_factor: float = 1.5,
    min_gap_sec: float = 0.05,
) -> np.ndarray:
    """Detect onset times (seconds) using half-wave rectified spectral flux.

    Spectral flux = sum of positive magnitude differences between consecutive
    STFT frames. Peaks above the adaptive threshold are marked as onsets.

    Args:
        y:                Mono 1-D audio array.
        sr:               Sample rate in Hz.
        n_fft:            FFT size.
        hop:              Hop length between frames in samples.
        threshold_factor: Multiplier on the local mean for peak picking.
        min_gap_sec:      Minimum time between consecutive onsets (s).

    Returns:
        Sorted array of onset times in seconds.
    """
    if y.size < n_fft:
        return np.array([], dtype=float)

    # Build windowed STFT frames
    window = np.hanning(n_fft)
    frames: list[np.ndarray] = []
    for start in range(0, len(y) - n_fft + 1, hop):
        frame = y[start : start + n_fft] * window
        frames.append(np.abs(np.fft.rfft(frame)))

    if len(frames) < 2:
        return np.array([], dtype=float)

    mag = np.stack(frames, axis=1)  # shape (freq_bins, n_frames)

    # Half-wave rectified spectral flux: sum of positive differences
    diff = np.diff(mag, axis=1)  # shape (freq_bins, n_frames-1)
    flux = np.sum(np.maximum(diff, 0.0), axis=0)  # shape (n_frames-1,)

    # Adaptive threshold: local mean × factor (window of ~0.2 s)
    win_frames = max(1, int(0.2 * sr / hop))
    kernel = np.ones(win_frames) / win_frames
    local_mean = np.convolve(flux, kernel, mode="same")
    threshold = local_mean * threshold_factor

    # Peak picking: flux > threshold and local maximum
    is_peak = (flux > threshold) & (
        np.concatenate([[False], flux[1:] > flux[:-1]])
        | np.concatenate([flux[:-1] > flux[1:], [False]])
    )

    onset_frames = np.where(is_peak)[0] + 1  # +1 because flux is diff of frames

    # Convert to seconds
    onset_times = onset_frames * hop / float(sr)

    # Enforce minimum gap between onsets
    if onset_times.size == 0:
        return onset_times
    min_gap = min_gap_sec
    filtered: list[float] = [float(onset_times[0])]
    for t in onset_times[1:]:
        if t - filtered[-1] >= min_gap:
            filtered.append(float(t))
    return np.array(filtered)


# ---------------------------------------------------------------------------
# Attack sharpness
# ---------------------------------------------------------------------------


def _attack_sharpness(y: np.ndarray, sr: int, onset_times: np.ndarray) -> tuple[float, float]:
    """Estimate attack sharpness and attack ratio from onset times.

    For each detected onset, measure how quickly the RMS energy rises from
    onset to peak within a short window (up to 50 ms look-ahead).

    Args:
        y:            Mono audio array.
        sr:           Sample rate.
        onset_times:  Sorted onset times in seconds.

    Returns:
        (sharpness, attack_ratio) where:
            sharpness   = mean fraction of rise achieved in first 10% of window
            attack_ratio = fraction of total signal duration near onset regions
    """
    if onset_times.size == 0:
        return 0.5, 0.0  # neutral defaults when no onsets found

    window_sec = 0.05  # 50 ms analysis window
    window_samples = int(window_sec * sr)
    rise_fracs: list[float] = []
    total_attack_samples = 0

    for t in onset_times:
        start = int(t * sr)
        end = min(start + window_samples, len(y))
        if end <= start:
            continue

        segment = np.abs(y[start:end])
        if segment.size < 4:
            continue

        peak_idx = int(np.argmax(segment))
        peak_val = float(segment[peak_idx])
        if peak_val < _EPS:
            continue

        # How much energy (fraction of peak) is reached in first 10% of window?
        early_end = max(1, int(0.1 * len(segment)))
        early_peak = float(np.max(segment[:early_end]))
        rise_fracs.append(min(early_peak / peak_val, 1.0))

        # Attack window = samples from onset to peak
        total_attack_samples += peak_idx

    sharpness = float(np.mean(rise_fracs)) if rise_fracs else 0.5
    total_dur = float(len(y))
    attack_ratio = float(np.clip(total_attack_samples / (total_dur + _EPS), 0.0, 1.0))
    return sharpness, attack_ratio


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_transients(y: np.ndarray, sr: int) -> TransientProfile:
    """Compute transient density, attack sharpness, and attack ratio.

    Args:
        y:  Audio array. Mono (N,) or stereo (2, N).
        sr: Sample rate in Hz.

    Returns:
        TransientProfile.

    Raises:
        ValueError: If y is empty or sr <= 0.
    """
    if sr <= 0:
        raise ValueError(f"Sample rate must be positive, got {sr}")

    # Mix to mono
    if y.ndim == 2:
        mono = np.mean(y, axis=0).astype(float)
    else:
        mono = y.astype(float)

    if mono.size == 0:
        raise ValueError("Audio array is empty")

    duration_sec = float(len(mono)) / sr

    # Detect onsets
    onsets = _spectral_flux_onsets(mono, sr)
    density = float(onsets.size) / duration_sec if duration_sec > 0 else 0.0

    sharpness, attack_ratio = _attack_sharpness(mono, sr, onsets)

    return TransientProfile(
        density=float(np.clip(density, 0.0, 100.0)),
        sharpness=float(np.clip(sharpness, 0.0, 1.0)),
        attack_ratio=float(np.clip(attack_ratio, 0.0, 1.0)),
    )
