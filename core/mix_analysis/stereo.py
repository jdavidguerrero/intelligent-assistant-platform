"""
core/mix_analysis/stereo.py — Stereo image analysis for mix diagnostics.

Measures stereo width, L-R correlation, mid-side balance, per-band stereo
content, and detects phase cancellation issues.

Design:
    - Pure: stereo array (2, N) + sr → StereoImage.
    - Mono input (1-D or (1, N)) returns a StereoImage with is_mono=True
      and all width/correlation fields at their "mono" sentinel values.
    - Per-band analysis uses the same bandpass filters as spectral.py.
"""

from __future__ import annotations

import numpy as np
from scipy import signal as scipy_signal

from core.mix_analysis.types import BAND_EDGES, BandProfile, StereoImage

_EPS = 1e-10
_FILTER_ORDER = 4


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _pearson_correlation(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson correlation coefficient between two 1-D arrays.

    Returns 1.0 if either array has zero variance (e.g. silence).
    """
    if a.size == 0 or b.size == 0:
        return 1.0
    # Compute correlation matrix
    std_a = float(np.std(a))
    std_b = float(np.std(b))
    if std_a < _EPS or std_b < _EPS:
        return 1.0
    cov = float(np.mean((a - np.mean(a)) * (b - np.mean(b))))
    return float(np.clip(cov / (std_a * std_b), -1.0, 1.0))


def _bandpass(y: np.ndarray, sr: int, low_hz: float, high_hz: float) -> np.ndarray:
    """Apply Butterworth bandpass filter. Returns zeros on failure."""
    nyquist = sr / 2.0
    lo = max(low_hz, 10.0) / nyquist
    hi = min(high_hz, nyquist * 0.995) / nyquist
    if hi <= lo or lo >= 1.0:
        return np.zeros_like(y)
    order = 2 if (lo < 0.005 or hi > 0.9 or (hi - lo) < 0.02) else _FILTER_ORDER
    try:
        sos = scipy_signal.butter(order, [lo, hi], btype="bandpass", output="sos")
        return scipy_signal.sosfilt(sos, y)
    except Exception:
        return np.zeros_like(y)


def _band_width(
    left: np.ndarray, right: np.ndarray, sr: int, low_hz: float, high_hz: float
) -> float:
    """Stereo width for a single frequency band.

    Width = 1 - |correlation(L_band, R_band)|.
    Returns 0.0 if the band is inaudible at the given sample rate.
    """
    l_filt = _bandpass(left, sr, low_hz, high_hz)
    r_filt = _bandpass(right, sr, low_hz, high_hz)
    # Skip band if both filtered signals are essentially silent
    if np.sqrt(np.mean(l_filt**2)) < _EPS and np.sqrt(np.mean(r_filt**2)) < _EPS:
        return 0.0
    corr = _pearson_correlation(l_filt, r_filt)
    return float(np.clip(1.0 - abs(corr), 0.0, 1.0))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_stereo_image(y: np.ndarray, sr: int) -> StereoImage:
    """Measure stereo width, correlation, mid-side balance, and per-band width.

    Args:
        y:  Audio array. Shape (N,) or (1, N) for mono; (2, N) for stereo.
        sr: Sample rate in Hz.

    Returns:
        StereoImage. When input is mono, `is_mono=True` and all width
        measurements are 0.0 (correlation is 1.0).

    Raises:
        ValueError: If y has more than 2 channels, or sr <= 0, or array is empty.
    """
    if sr <= 0:
        raise ValueError(f"Sample rate must be positive, got {sr}")

    # --- Handle mono input ---
    is_stereo = y.ndim == 2 and y.shape[0] >= 2
    if not is_stereo:
        # Mono: return early with sentinel values
        zero_bands = BandProfile(
            sub=0.0,
            low=0.0,
            low_mid=0.0,
            mid=0.0,
            high_mid=0.0,
            high=0.0,
            air=0.0,
        )
        return StereoImage(
            width=0.0,
            lr_correlation=1.0,
            mid_side_ratio=0.0,
            band_widths=zero_bands,
            is_mono=True,
        )

    if y.ndim == 2 and y.shape[0] > 2:
        raise ValueError(f"Expected mono or stereo (1–2 channels), got {y.shape[0]} channels")
    if y.shape[1] == 0:
        raise ValueError("Audio array is empty")

    left = y[0].astype(float)
    right = y[1].astype(float)

    # --- Overall L-R correlation and width ---
    lr_corr = _pearson_correlation(left, right)
    width = float(np.clip(1.0 - abs(lr_corr), 0.0, 1.0))

    # --- Mid-side decomposition ---
    mid = (left + right) / 2.0
    side = (left - right) / 2.0
    rms_mid = float(np.sqrt(np.mean(mid**2)))
    rms_side = float(np.sqrt(np.mean(side**2)))
    if rms_side < _EPS:
        # Mono-compatible mix: no side energy → very high mid-side ratio
        mid_side_ratio = 40.0
    elif rms_mid < _EPS:
        # Fully wide / phase-inverted: no mid energy → very negative ratio
        mid_side_ratio = -40.0
    else:
        mid_side_ratio = float(20.0 * np.log10(rms_mid / rms_side))

    # --- Per-band stereo width ---
    bw = {}
    for band_name, (lo, hi) in BAND_EDGES.items():
        bw[band_name] = _band_width(left, right, sr, lo, hi)

    band_widths = BandProfile(**bw)

    return StereoImage(
        width=width,
        lr_correlation=lr_corr,
        mid_side_ratio=mid_side_ratio,
        band_widths=band_widths,
        is_mono=False,
    )
