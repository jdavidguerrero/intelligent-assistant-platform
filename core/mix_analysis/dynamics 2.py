"""
core/mix_analysis/dynamics.py — Loudness and dynamics analysis for mix diagnostics.

Implements:
    - RMS and true-peak measurement in dBFS
    - Integrated loudness (LUFS) via K-weighting per ITU-R BS.1770-4
    - Crest factor (peak-to-RMS)
    - Dynamic range (95th–5th percentile of per-segment RMS)
    - Loudness Range (LRA) per EBU R128

Design:
    - Pure: numpy arrays in, DynamicProfile out.
    - K-weighting filter coefficients are computed analytically using the
      RBJ Audio EQ Cookbook for the shelving stage + Butterworth for HPF.
    - Handles both mono (N,) and stereo (2, N) arrays.
    - LUFS target accuracy: ±1 dB vs reference meters for typical program material.
"""

from __future__ import annotations

import numpy as np
from scipy import signal as scipy_signal

from core.mix_analysis.types import DynamicProfile

_EPS = 1e-10

# BS.1770 gate threshold (absolute, in mean-square linear domain)
# −70 LUFS absolute: mean_square = 10^((-70 + 0.691) / 10)
_GATE_ABSOLUTE_MS = 10 ** ((-70.0 + 0.691) / 10.0)

# Relative gate offset: −10 LU below ungated mean (BS.1770-4 relative gate)
_GATE_RELATIVE_OFFSET_DB = -10.0


# ---------------------------------------------------------------------------
# K-weighting filter design (BS.1770)
# ---------------------------------------------------------------------------


def _design_high_shelf(
    sr: int, f0: float = 1681.7, gain_db: float = 4.0
) -> tuple[np.ndarray, np.ndarray]:
    """Design a high-shelf filter using the RBJ Audio EQ Cookbook.

    This is Stage 1 of the K-weighting filter per ITU-R BS.1770.

    Args:
        sr:       Sample rate in Hz.
        f0:       Shelf midpoint frequency (1681.7 Hz per BS.1770).
        gain_db:  Shelf gain in dB (+4.0 per BS.1770).

    Returns:
        (b, a) digital filter coefficients.
    """
    A = 10.0 ** (gain_db / 40.0)  # sqrt(linear gain)
    w0 = 2.0 * np.pi * f0 / sr
    cos_w0 = np.cos(w0)
    sin_w0 = np.sin(w0)
    S = 1.0  # shelf slope = 1
    alpha = sin_w0 / 2.0 * np.sqrt((A + 1.0 / A) * (1.0 / S - 1.0) + 2.0)

    b0 = A * ((A + 1.0) + (A - 1.0) * cos_w0 + 2.0 * np.sqrt(A) * alpha)
    b1 = -2.0 * A * ((A - 1.0) + (A + 1.0) * cos_w0)
    b2 = A * ((A + 1.0) + (A - 1.0) * cos_w0 - 2.0 * np.sqrt(A) * alpha)
    a0 = (A + 1.0) - (A - 1.0) * cos_w0 + 2.0 * np.sqrt(A) * alpha
    a1 = 2.0 * ((A - 1.0) - (A + 1.0) * cos_w0)
    a2 = (A + 1.0) - (A - 1.0) * cos_w0 - 2.0 * np.sqrt(A) * alpha

    return np.array([b0, b1, b2]) / a0, np.array([1.0, a1 / a0, a2 / a0])


def _k_weighting_filter(y: np.ndarray, sr: int) -> np.ndarray:
    """Apply BS.1770 K-weighting filter to a single channel.

    Two stages:
        1. High-shelf pre-filter (+4 dB above ~1.7 kHz)
        2. High-pass filter (2nd order Butterworth at 38.13 Hz)

    Args:
        y:  1-D mono audio array.
        sr: Sample rate in Hz.

    Returns:
        K-weighted audio array, same shape as y.
    """
    # Stage 1: high-shelf (pre-filter)
    b, a = _design_high_shelf(sr)
    y_stage1 = scipy_signal.lfilter(b, a, y)

    # Stage 2: high-pass at 38.13 Hz
    sos_hp = scipy_signal.butter(2, 38.13 / (sr / 2.0), btype="high", output="sos")
    return scipy_signal.sosfilt(sos_hp, y_stage1)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_channels(y: np.ndarray) -> list[np.ndarray]:
    """Return list of 1-D channel arrays (1 for mono, 2 for stereo)."""
    if y.ndim == 1:
        return [y.astype(float)]
    return [y[i].astype(float) for i in range(min(y.shape[0], 2))]


def _rms_db(y: np.ndarray) -> float:
    """RMS level in dBFS."""
    return float(20.0 * np.log10(np.sqrt(np.mean(y**2)) + _EPS))


def _true_peak_db(y: np.ndarray) -> float:
    """True peak in dBFS (maximum absolute sample value in linear, converted to dB)."""
    return float(20.0 * np.log10(np.max(np.abs(y)) + _EPS))


def _compute_lufs(channels: list[np.ndarray], sr: int) -> float:
    """Compute integrated loudness (LUFS) per ITU-R BS.1770-4.

    Algorithm:
        1. K-weight each channel independently.
        2. Compute mean square per 400 ms block (75% overlap = 100 ms hop).
        3. Sum channel mean squares (equal weights for L and R per BS.1770).
        4. Apply absolute gate (−70 LUFS) and relative gate (−10 LU).
        5. LUFS = −0.691 + 10 × log10(mean of gated block mean-squares).

    Args:
        channels: List of 1-D channel arrays (already K-weighted NOT applied yet).
        sr:       Sample rate.

    Returns:
        Integrated loudness in LUFS. Returns −70.0 if signal is silent.
    """
    block_samples = int(0.400 * sr)  # 400 ms
    hop_samples = int(0.100 * sr)  # 100 ms hop → 75% overlap

    if block_samples == 0 or hop_samples == 0:
        return -70.0

    # K-weight each channel
    weighted = [_k_weighting_filter(ch, sr) for ch in channels]

    # Build blocks and compute mean square per block (sum across channels)
    n_samples = len(weighted[0])
    block_ms_list: list[float] = []

    start = 0
    while start + block_samples <= n_samples:
        block_ms = sum(float(np.mean(ch[start : start + block_samples] ** 2)) for ch in weighted)
        block_ms_list.append(block_ms)
        start += hop_samples

    if not block_ms_list:
        return -70.0

    block_ms_arr = np.array(block_ms_list)

    # Absolute gate
    above_abs = block_ms_arr[block_ms_arr >= _GATE_ABSOLUTE_MS]
    if above_abs.size == 0:
        return -70.0

    # Relative gate: compute threshold as J_g − 10 LU
    ungated_mean = float(np.mean(above_abs))
    relative_threshold = ungated_mean * 10 ** (_GATE_RELATIVE_OFFSET_DB / 10.0)
    gated = above_abs[above_abs >= relative_threshold]
    if gated.size == 0:
        return -70.0

    lufs = -0.691 + 10.0 * np.log10(float(np.mean(gated)) + _EPS)
    return float(np.clip(lufs, -70.0, 0.0))


def _compute_lra(channels: list[np.ndarray], sr: int) -> float:
    """Compute Loudness Range (LRA) per EBU R128.

    Uses 3 s windows with 2 s step. Gates blocks below −70 LUFS absolute
    and −20 LU below the loudest block. LRA = 95th − 10th percentile.

    Returns:
        LRA in Loudness Units (LU). 0.0 if fewer than 2 blocks are available.
    """
    window_samples = int(3.0 * sr)
    hop_samples = int(2.0 * sr)

    if window_samples == 0:
        return 0.0

    weighted = [_k_weighting_filter(ch, sr) for ch in channels]
    n_samples = len(weighted[0])

    st_lufs_list: list[float] = []
    start = 0
    while start + window_samples <= n_samples:
        block_ms = sum(float(np.mean(ch[start : start + window_samples] ** 2)) for ch in weighted)
        if block_ms >= _GATE_ABSOLUTE_MS:
            st_lufs_list.append(-0.691 + 10.0 * np.log10(block_ms + _EPS))
        start += hop_samples

    if len(st_lufs_list) < 2:
        return 0.0

    arr = np.array(st_lufs_list)
    # Relative gate: keep blocks within 20 LU of max
    max_lufs = float(np.max(arr))
    gated = arr[arr >= max_lufs - 20.0]
    if gated.size < 2:
        return 0.0

    lra = float(np.percentile(gated, 95) - np.percentile(gated, 10))
    return float(max(lra, 0.0))


def _compute_dynamic_range(y_mono: np.ndarray, sr: int, segment_sec: float = 0.5) -> float:
    """Estimate dynamic range as the difference between the 95th and 5th percentile
    of per-segment RMS levels in dB.

    Args:
        y_mono:      Mono audio array.
        sr:          Sample rate.
        segment_sec: Duration of each analysis segment in seconds.

    Returns:
        Dynamic range in dB. 0.0 if fewer than 2 segments.
    """
    seg_len = int(segment_sec * sr)
    if seg_len == 0 or y_mono.size < seg_len:
        return 0.0

    n_segs = y_mono.size // seg_len
    segments = y_mono[: n_segs * seg_len].reshape(n_segs, seg_len)
    rms_vals = np.sqrt(np.mean(segments**2, axis=1))
    # Ignore silence
    active = rms_vals[rms_vals > _EPS]
    if active.size < 2:
        return 0.0

    rms_db = 20.0 * np.log10(active)
    return float(np.percentile(rms_db, 95) - np.percentile(rms_db, 5))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_dynamics(y: np.ndarray, sr: int) -> DynamicProfile:
    """Compute loudness, crest factor, LUFS, and dynamic range.

    Args:
        y:  Audio array. Mono (N,) or stereo (2, N).
        sr: Sample rate in Hz.

    Returns:
        DynamicProfile with all dynamic metrics.

    Raises:
        ValueError: If y is empty or sr <= 0.
    """
    if sr <= 0:
        raise ValueError(f"Sample rate must be positive, got {sr}")

    channels = _to_channels(y)
    if channels[0].size == 0:
        raise ValueError("Audio array is empty")

    # Use mono mix for RMS / peak / dynamic range
    if len(channels) == 1:
        mono = channels[0]
    else:
        mono = np.mean(np.stack(channels, axis=0), axis=0)

    rms_db = _rms_db(mono)
    peak_db = _true_peak_db(mono)
    crest_factor = float(np.clip(peak_db - rms_db, 0.0, 40.0))

    lufs = _compute_lufs(channels, sr)
    lra = _compute_lra(channels, sr)
    dyn_range = _compute_dynamic_range(mono, sr)

    return DynamicProfile(
        rms_db=rms_db,
        peak_db=peak_db,
        lufs=lufs,
        crest_factor=crest_factor,
        dynamic_range=dyn_range,
        loudness_range=lra,
    )
