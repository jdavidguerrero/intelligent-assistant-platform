"""
core/mix_analysis/mastering.py — Mastering-grade loudness and readiness analysis.

Extends dynamics.py with:
    - LUFS momentary (400 ms, no gating) — loudest instant
    - LUFS short-term max (3 s, no gating) — loudest section
    - True peak with 4x oversampling (BS.1770 / ITU-R BS.1771)
    - Inter-sample peak count (potential D/A clipping)
    - Section-based crest factor (intro / build / drop / outro)
    - Spectral balance label (dark → bright)
    - Master readiness score 0–100 with issue list

Design:
    - Pure: numpy arrays + sr → MasterAnalysis.
    - Reuses _k_weighting_filter from dynamics.py (same K-weighting).
    - 4x oversampling uses scipy.signal.resample_poly (O(N), efficient
      for integer upsample ratios vs. scipy.signal.resample which uses FFT).
"""

from __future__ import annotations

import numpy as np
from scipy.signal import resample_poly

from core.mix_analysis._genre_loader import load_genre_target
from core.mix_analysis.dynamics import _k_weighting_filter
from core.mix_analysis.spectral import analyze_frequency_balance
from core.mix_analysis.types import MasterAnalysis, SectionDynamics

_EPS = 1e-10
_GATE_ABSOLUTE_MS = 10 ** ((-70.0 + 0.691) / 10.0)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_channels(y: np.ndarray) -> list[np.ndarray]:
    """Return list of 1-D channel arrays (1 for mono, 2 for stereo)."""
    if y.ndim == 1:
        return [y.astype(float)]
    return [y[i].astype(float) for i in range(min(y.shape[0], 2))]


def _to_mono(y: np.ndarray) -> np.ndarray:
    if y.ndim == 1:
        return y.astype(float)
    return np.mean(y, axis=0).astype(float)


def _lufs_momentary(channels: list[np.ndarray], sr: int) -> float:
    """Maximum momentary LUFS (400 ms windows, 75% overlap, NO gating).

    Unlike integrated LUFS, momentary does not apply the absolute or relative
    gates — it reports the loudest 400 ms instant in the file.

    Returns:
        Maximum momentary LUFS value. −70.0 if silent.
    """
    block_samples = int(0.400 * sr)
    hop_samples = int(0.100 * sr)
    if block_samples == 0:
        return -70.0

    weighted = [_k_weighting_filter(ch, sr) for ch in channels]
    n = len(weighted[0])
    max_lufs = -70.0

    start = 0
    while start + block_samples <= n:
        ms = sum(float(np.mean(ch[start : start + block_samples] ** 2)) for ch in weighted)
        if ms > _EPS:
            lufs = -0.691 + 10.0 * np.log10(ms)
            if lufs > max_lufs:
                max_lufs = lufs
        start += hop_samples

    return float(np.clip(max_lufs, -70.0, 0.0))


def _lufs_short_term_max(channels: list[np.ndarray], sr: int) -> float:
    """Maximum short-term LUFS (3 s windows, 1 s hop, NO gating)."""
    window_samples = int(3.0 * sr)
    hop_samples = int(1.0 * sr)
    if window_samples == 0:
        return -70.0

    weighted = [_k_weighting_filter(ch, sr) for ch in channels]
    n = len(weighted[0])
    max_lufs = -70.0

    start = 0
    while start + window_samples <= n:
        ms = sum(float(np.mean(ch[start : start + window_samples] ** 2)) for ch in weighted)
        if ms > _EPS:
            lufs = -0.691 + 10.0 * np.log10(ms)
            if lufs > max_lufs:
                max_lufs = lufs
        start += hop_samples

    return float(np.clip(max_lufs, -70.0, 0.0))


def _true_peak(mono: np.ndarray) -> float:
    """True peak with 4x oversampling (ITU-R BS.1770 / BS.1771).

    4x interpolation catches inter-sample peaks that occur between digital
    samples on D/A conversion — these can exceed 0 dBFS even when all
    samples are below 0 dBFS.

    Uses scipy.signal.resample_poly (polyphase, O(N)) for efficiency.

    Returns:
        True peak in dBFS (always <= 0 is not guaranteed — can be positive
        if inter-sample peaks exist).
    """
    if mono.size == 0:
        return -96.0
    try:
        y_4x = resample_poly(mono, up=4, down=1)
    except Exception:
        y_4x = mono
    peak = float(np.max(np.abs(y_4x)))
    return float(20.0 * np.log10(peak + _EPS))


def _count_inter_sample_peaks(mono: np.ndarray, ceiling_db: float = -0.5) -> int:
    """Count frames where the 4x-oversampled peak exceeds the sample-domain peak.

    A high count indicates the master may clip after D/A conversion even if
    all original samples are below 0 dBFS.

    Args:
        mono:        Mono audio array.
        ceiling_db:  Inter-sample peak warning threshold in dBFS.

    Returns:
        Number of 4x-oversampled frames that exceed the ceiling.
    """
    ceiling_linear = 10 ** (ceiling_db / 20.0)
    if mono.size == 0:
        return 0
    try:
        y_4x = resample_poly(mono, up=4, down=1)
    except Exception:
        return 0
    # Count 4x samples that exceed the original-domain ceiling
    return int(np.sum(np.abs(y_4x) > ceiling_linear))


def _section_dynamics(mono: np.ndarray, sr: int) -> tuple[SectionDynamics, ...]:
    """Compute crest factor for 4 equal sections of the track.

    Labels: intro (0–25%), build (25–50%), drop (50–75%), outro (75–100%).
    """
    n = len(mono)
    labels = ("intro", "build", "drop", "outro")
    sections: list[SectionDynamics] = []
    quarter = n // 4

    for i, label in enumerate(labels):
        seg = mono[i * quarter : (i + 1) * quarter]
        if seg.size == 0:
            sections.append(
                SectionDynamics(
                    label=label, start_sec=0.0, rms_db=-60.0, peak_db=-60.0, crest_factor=0.0
                )
            )
            continue

        rms = float(np.sqrt(np.mean(seg**2)))
        peak = float(np.max(np.abs(seg)))
        rms_db = float(20.0 * np.log10(rms + _EPS))
        peak_db = float(20.0 * np.log10(peak + _EPS))
        crest = float(np.clip(peak_db - rms_db, 0.0, 40.0))
        start_sec = float(i * quarter) / sr

        sections.append(
            SectionDynamics(
                label=label,
                start_sec=start_sec,
                rms_db=rms_db,
                peak_db=peak_db,
                crest_factor=crest,
            )
        )

    return tuple(sections)


def _spectral_balance_label(tilt: float, genre: str) -> str:
    """Map spectral tilt to a descriptive balance label.

    Tilt (dB/octave) thresholds are genre-informed:
    - Organic house target: ~-4 to -6 dB/oct → 'neutral'
    - Below -7 → dark; above -2 → bright
    """
    if tilt < -7.0:
        return "dark"
    elif tilt < -5.5:
        return "slightly dark"
    elif tilt < -2.5:
        return "neutral"
    elif tilt < -1.0:
        return "slightly bright"
    else:
        return "bright"


def _readiness_score(
    lufs: float,
    true_peak: float,
    crest: float,
    inter_sample: int,
    tilt: float,
    genre: str,
) -> tuple[float, tuple[str, ...]]:
    """Compute master readiness score (0–100) and list of issues.

    Deducts points for each criterion that fails the genre target:
        - LUFS out of target range: -15 points
        - True peak > -1.0 dBTP: -20 points
        - Crest factor below genre minimum: -15 points
        - Inter-sample peaks > 100: -10 points
        - Spectral imbalance: -10 points

    Args:
        lufs:          Integrated LUFS.
        true_peak:     True peak in dBFS.
        crest:         Crest factor in dB.
        inter_sample:  Count of inter-sample peaks.
        tilt:          Spectral tilt (dB/octave).
        genre:         Genre name.

    Returns:
        (score, issues_tuple)
    """
    targets = load_genre_target(genre)
    dyn_targets = targets["dynamics"]
    lufs_min = float(dyn_targets["lufs_min"])
    lufs_max = float(dyn_targets["lufs_max"])
    crest_min = float(dyn_targets["crest_min"])

    score = 100.0
    issues: list[str] = []

    # LUFS range
    if lufs < lufs_min:
        deficit = lufs_min - lufs
        score -= min(15.0, deficit * 3.0)
        issues.append(
            f"LUFS {lufs:.1f} is {deficit:.1f} LU below target minimum "
            f"({lufs_min} LUFS). Increase master output."
        )
    elif lufs > lufs_max:
        excess = lufs - lufs_max
        score -= min(15.0, excess * 3.0)
        issues.append(
            f"LUFS {lufs:.1f} is {excess:.1f} LU above target maximum "
            f"({lufs_max} LUFS). Reduce master limiter ceiling."
        )

    # True peak
    if true_peak > -1.0:
        excess = true_peak + 1.0
        score -= min(20.0, 10.0 + excess * 5.0)
        issues.append(
            f"True peak {true_peak:.1f} dBTP exceeds −1.0 dBTP ceiling. "
            "Reduce limiter output ceiling."
        )
    elif true_peak > -0.3:
        score -= 5.0
        issues.append(
            f"True peak {true_peak:.1f} dBTP is close to ceiling. "
            "Acceptable but leaves no safety margin."
        )

    # Crest factor
    if crest < crest_min:
        deficit = crest_min - crest
        score -= min(15.0, deficit * 3.0)
        issues.append(
            f"Crest factor {crest:.1f} dB below {genre} minimum ({crest_min} dB). "
            "Mix sounds over-compressed. Increase attack time on master compressor."
        )

    # Inter-sample peaks
    if inter_sample > 500:
        score -= 10.0
        issues.append(
            f"{inter_sample} inter-sample peaks detected. "
            "Potential clipping after D/A conversion. Reduce true peak to −1.5 dBTP."
        )
    elif inter_sample > 100:
        score -= 5.0
        issues.append(
            f"{inter_sample} inter-sample peaks detected. "
            "Consider reducing ceiling to −1.5 dBTP for safety."
        )

    # Spectral balance
    balance = _spectral_balance_label(tilt, genre)
    if balance in ("dark", "bright"):
        score -= 10.0
        issues.append(
            f"Spectral balance is '{balance}' (tilt {tilt:.1f} dB/oct). "
            "Check EQ on the master bus."
        )
    elif balance in ("slightly dark", "slightly bright"):
        score -= 3.0
        issues.append(f"Spectral balance is '{balance}' — minor EQ adjustment may help.")

    score = round(float(np.clip(score, 0.0, 100.0)), 1)
    return score, tuple(issues)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_master(y: np.ndarray, sr: int, genre: str = "organic house") -> MasterAnalysis:
    """Mastering-grade loudness and readiness analysis.

    Computes three LUFS windows (integrated / short-term-max / momentary-max),
    true peak with 4x oversampling, inter-sample peak count, per-section
    dynamics, spectral balance, and a readiness score 0–100.

    Args:
        y:     Audio array. Mono (N,) or stereo (2, N).
        sr:    Sample rate in Hz.
        genre: Genre name for target comparison.

    Returns:
        MasterAnalysis with all mastering metrics.

    Raises:
        ValueError: If y is empty, sr <= 0, or genre is unknown.
    """
    if sr <= 0:
        raise ValueError(f"Sample rate must be positive, got {sr}")

    channels = _to_channels(y)
    if channels[0].size == 0:
        raise ValueError("Audio array is empty")

    mono = _to_mono(y)

    # --- LUFS windows ---
    from core.mix_analysis.dynamics import _compute_lufs  # local import to avoid circular

    lufs_integrated = _compute_lufs(channels, sr)
    lufs_st_max = _lufs_short_term_max(channels, sr)
    lufs_mom_max = _lufs_momentary(channels, sr)

    # --- True peak and inter-sample peaks ---
    tp_db = _true_peak(mono)
    isp_count = _count_inter_sample_peaks(mono)

    # --- Crest factor ---
    rms_linear = float(np.sqrt(np.mean(mono**2)))
    peak_linear = float(np.max(np.abs(mono)))
    rms_db = 20.0 * np.log10(rms_linear + _EPS)
    peak_db_sample = 20.0 * np.log10(peak_linear + _EPS)
    crest_factor = float(np.clip(peak_db_sample - rms_db, 0.0, 40.0))

    # --- Spectral balance ---
    fp = analyze_frequency_balance(mono, sr)
    balance = _spectral_balance_label(fp.spectral_tilt, genre)

    # --- Section dynamics ---
    sections = _section_dynamics(mono, sr)

    # --- Readiness score ---
    score, issues = _readiness_score(
        lufs_integrated, tp_db, crest_factor, isp_count, fp.spectral_tilt, genre
    )

    return MasterAnalysis(
        lufs_integrated=lufs_integrated,
        lufs_short_term_max=lufs_st_max,
        lufs_momentary_max=lufs_mom_max,
        true_peak_db=tp_db,
        inter_sample_peaks=isp_count,
        crest_factor=crest_factor,
        sections=sections,
        spectral_balance=balance,
        readiness_score=score,
        issues=issues,
    )
