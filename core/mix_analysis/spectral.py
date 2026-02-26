"""
core/mix_analysis/spectral.py — Frequency-domain analysis for mix diagnostics.

Provides 7-band spectral balance analysis using Butterworth bandpass filters,
plus spectral centroid, tilt, and flatness.

Design:
    - All functions are pure: (y: np.ndarray, sr: int) → structured data.
    - scipy and numpy are treated as pure computation libraries (no I/O).
    - Bandpass filters use SOS representation for numerical stability at
      extreme frequencies (sub-bass 20 Hz, air 20 kHz).
    - Mix to mono before frequency analysis (stereo width is stereo.py's job).
"""

from __future__ import annotations

import numpy as np
from scipy import signal as scipy_signal
from scipy import stats as scipy_stats

from core.mix_analysis.types import BAND_EDGES, BandProfile, FrequencyProfile

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EPS = 1e-10  # small value to prevent log(0)
_N_FFT = 4096  # FFT size for centroid/tilt/flatness
_FILTER_ORDER = 4  # Butterworth filter order for band splitting


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_mono(y: np.ndarray) -> np.ndarray:
    """Mix stereo or multi-channel array to mono.

    Args:
        y: Audio array. Shape (N,) for mono or (C, N) for multi-channel.

    Returns:
        1-D mono array of shape (N,).
    """
    if y.ndim == 1:
        return y
    # Average across channel axis (first axis when shape is (C, N))
    return np.mean(y, axis=0)


def _band_rms(y: np.ndarray, sr: int, low_hz: float, high_hz: float) -> float:
    """Compute RMS energy of a bandpass-filtered signal.

    Uses a 4th-order Butterworth filter in SOS form for numerical stability.
    Returns 0.0 if the frequency range is not representable at the given sample rate.

    Args:
        y:       Mono audio array.
        sr:      Sample rate in Hz.
        low_hz:  Lower cutoff frequency in Hz.
        high_hz: Upper cutoff frequency in Hz.

    Returns:
        RMS value (linear, not dB) of the filtered signal.
    """
    nyquist = sr / 2.0
    # Clamp to valid range — avoid instability at DC or Nyquist
    lo = max(low_hz, 10.0) / nyquist
    hi = min(high_hz, nyquist * 0.995) / nyquist

    if hi <= lo or lo >= 1.0 or hi <= 0.0:
        return 0.0

    # Reduce order for very narrow or very low bands to avoid instability
    order = 2 if (lo < 0.005 or hi > 0.9 or (hi - lo) < 0.02) else _FILTER_ORDER
    try:
        sos = scipy_signal.butter(order, [lo, hi], btype="bandpass", output="sos")
        filtered = scipy_signal.sosfilt(sos, y)
    except Exception:
        return 0.0

    return float(np.sqrt(np.mean(filtered**2)))


def _rms_to_db(rms: float) -> float:
    """Convert linear RMS to dBFS."""
    return 20.0 * np.log10(rms + _EPS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_frequency_balance(y: np.ndarray, sr: int) -> FrequencyProfile:
    """Compute 7-band frequency balance and spectral shape metrics.

    Bands (Hz): sub(20–60), low(60–200), low_mid(200–500), mid(500–2k),
    high_mid(2k–6k), high(6k–12k), air(12k–20k).

    Band levels are expressed in dB *relative to the overall RMS*, so 0.0 means
    a band has the same energy as the whole signal.

    Args:
        y:  Audio array. Mono (N,) or stereo (2, N) — mixed to mono internally.
        sr: Sample rate in Hz.

    Returns:
        FrequencyProfile with per-band relative levels and spectral metrics.

    Raises:
        ValueError: If y is empty or sr <= 0.
    """
    if sr <= 0:
        raise ValueError(f"Sample rate must be positive, got {sr}")
    mono = _to_mono(y)
    if mono.size == 0:
        raise ValueError("Audio array is empty")

    # --- Overall RMS ---
    overall_rms = float(np.sqrt(np.mean(mono**2)))
    overall_rms_db = _rms_to_db(overall_rms)

    # --- Per-band RMS (relative to overall) ---
    band_values: dict[str, float] = {}
    for band_name, (lo, hi) in BAND_EDGES.items():
        rms = _band_rms(mono, sr, lo, hi)
        band_db = _rms_to_db(rms)
        # Express relative to overall RMS; if band is silent, floor at -60 dB rel
        relative_db = band_db - overall_rms_db if overall_rms > _EPS else -60.0
        band_values[band_name] = float(np.clip(relative_db, -60.0, 20.0))

    bands = BandProfile(**band_values)

    # --- Spectral centroid, tilt, flatness from FFT ---
    centroid, tilt, flatness = _spectral_shape(mono, sr)

    return FrequencyProfile(
        bands=bands,
        spectral_centroid=centroid,
        spectral_tilt=tilt,
        spectral_flatness=flatness,
        overall_rms_db=overall_rms_db,
    )


def _spectral_shape(mono: np.ndarray, sr: int) -> tuple[float, float, float]:
    """Compute spectral centroid, tilt, and flatness from the FFT magnitude.

    Args:
        mono: Mono audio array.
        sr:   Sample rate in Hz.

    Returns:
        (centroid_hz, tilt_db_per_octave, flatness_0_to_1)
    """
    n = min(_N_FFT, len(mono))
    # Zero-pad to next power of 2 for efficiency
    n_fft = 1 << (n - 1).bit_length() if n > 1 else 512
    n_fft = max(n_fft, 512)

    # Apply Hann window to reduce spectral leakage
    windowed = (
        mono[:n_fft] * np.hanning(n_fft)
        if len(mono) >= n_fft
        else (np.concatenate([mono, np.zeros(n_fft - len(mono))]) * np.hanning(n_fft))
    )
    magnitudes = np.abs(np.fft.rfft(windowed))  # shape: (n_fft//2 + 1,)
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)  # Hz per bin

    # --- Centroid: weighted mean frequency ---
    centroid = float(np.sum(freqs * magnitudes) / (np.sum(magnitudes) + _EPS))

    # --- Tilt: linear regression of log-magnitude vs log-frequency ---
    # Only use bins in [20 Hz, Nyquist*0.95] to exclude DC and near-Nyquist
    valid = (freqs >= 20.0) & (freqs <= sr / 2 * 0.95) & (magnitudes > _EPS)
    tilt = 0.0
    if valid.sum() >= 4:
        log_freqs = np.log2(freqs[valid])
        log_mags_db = 20.0 * np.log10(magnitudes[valid] + _EPS)
        slope, _, _, _, _ = scipy_stats.linregress(log_freqs, log_mags_db)
        tilt = float(slope)  # dB per octave

    # --- Flatness: geometric mean / arithmetic mean (Wiener entropy) ---
    mag_valid = magnitudes[magnitudes > _EPS]
    if mag_valid.size > 0:
        log_mean = np.exp(np.mean(np.log(mag_valid)))
        arith_mean = np.mean(mag_valid)
        flatness = float(np.clip(log_mean / (arith_mean + _EPS), 0.0, 1.0))
    else:
        flatness = 0.0

    return centroid, tilt, flatness
