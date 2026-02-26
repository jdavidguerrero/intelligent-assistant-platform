"""
core/mix_analysis/types.py — Frozen data types for mix analysis results.

All types are frozen dataclasses — immutable value objects that are safe
to pass between layers, cache, and include in other frozen types.

Design:
    - No I/O, no side effects, no state.
    - Per-band data is stored as a dedicated frozen BandProfile dataclass
      to avoid mutable dict fields and maintain hashability.
    - Severity scores are 0–10 floats (not ints) for fractional granularity.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Band names constant — canonical ordering used across all modules
# ---------------------------------------------------------------------------

BAND_NAMES: tuple[str, ...] = (
    "sub",  # 20–60 Hz
    "low",  # 60–200 Hz
    "low_mid",  # 200–500 Hz
    "mid",  # 500–2 000 Hz
    "high_mid",  # 2 000–6 000 Hz
    "high",  # 6 000–12 000 Hz
    "air",  # 12 000–20 000 Hz
)

# Hz boundaries for each band (inclusive lower, exclusive upper)
BAND_EDGES: dict[str, tuple[float, float]] = {
    "sub": (20.0, 60.0),
    "low": (60.0, 200.0),
    "low_mid": (200.0, 500.0),
    "mid": (500.0, 2000.0),
    "high_mid": (2000.0, 6000.0),
    "high": (6000.0, 12000.0),
    "air": (12000.0, 20000.0),
}


# ---------------------------------------------------------------------------
# Per-band data container
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BandProfile:
    """A value for each of the 7 spectral bands.

    Used for both frequency levels (dBFS) and stereo width per band.
    All values are stored as floats; meaning depends on context.
    """

    sub: float
    """20–60 Hz band value."""

    low: float
    """60–200 Hz band value."""

    low_mid: float
    """200–500 Hz band value."""

    mid: float
    """500–2 000 Hz band value."""

    high_mid: float
    """2 000–6 000 Hz band value."""

    high: float
    """6 000–12 000 Hz band value."""

    air: float
    """12 000–20 000 Hz band value."""

    def as_dict(self) -> dict[str, float]:
        """Return band values as an ordered dict keyed by band name."""
        return {
            "sub": self.sub,
            "low": self.low,
            "low_mid": self.low_mid,
            "mid": self.mid,
            "high_mid": self.high_mid,
            "high": self.high,
            "air": self.air,
        }

    def get(self, band: str) -> float:
        """Return value for a named band.

        Raises:
            ValueError: If band name is not one of the 7 canonical bands.
        """
        d = self.as_dict()
        if band not in d:
            raise ValueError(f"Unknown band: {band!r}. Valid: {list(d)}")
        return d[band]


# ---------------------------------------------------------------------------
# FrequencyProfile
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FrequencyProfile:
    """Spectral balance analysis of an audio signal.

    Band levels are expressed in dB *relative to the overall RMS level*,
    so a value of 0.0 means the band has the same energy as the whole mix,
    positive means louder, negative means quieter.

    Invariants:
        spectral_centroid >= 0.0 (Hz)
        0.0 <= spectral_flatness <= 1.0
    """

    bands: BandProfile
    """Per-band RMS level relative to overall RMS (dB)."""

    spectral_centroid: float
    """Center of spectral mass in Hz. Higher = brighter mix."""

    spectral_tilt: float
    """Slope of spectrum in dB/octave (negative = dark, positive = bright).
    Typical well-balanced mix: -3 to -6 dB/octave."""

    spectral_flatness: float
    """0.0 = highly tonal (pitched content), 1.0 = noise-like (white noise)."""

    overall_rms_db: float
    """Overall RMS level of the full signal in dBFS (before band splitting)."""


# ---------------------------------------------------------------------------
# StereoImage
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StereoImage:
    """Stereo field analysis: width, correlation, and mid-side balance.

    Invariants:
        0.0 <= width <= 1.0
        -1.0 <= lr_correlation <= 1.0
        is_mono=True implies width=0.0, lr_correlation=1.0
    """

    width: float
    """Overall stereo width: 0.0 = mono, 1.0 = fully decorrelated.
    Computed as 1 − |L-R Pearson correlation|."""

    lr_correlation: float
    """Pearson correlation between L and R channels.
    +1.0 = identical (mono), 0.0 = uncorrelated, negative = phase problems."""

    mid_side_ratio: float
    """RMS(mid) / RMS(side) in dB. Positive = more mid than side content.
    Large positive values indicate a narrow, center-heavy mix."""

    band_widths: BandProfile
    """Per-band stereo width (0.0–1.0). Lows should be near 0, highs wider."""

    is_mono: bool
    """True if the input was a single-channel (mono) signal."""


# ---------------------------------------------------------------------------
# DynamicProfile
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DynamicProfile:
    """Loudness and dynamics assessment of an audio signal.

    Invariants:
        peak_db >= rms_db  (peak is always >= RMS)
        crest_factor >= 0.0 (peak_db − rms_db)
        dynamic_range >= 0.0
        loudness_range >= 0.0
    """

    rms_db: float
    """Overall RMS level in dBFS. Full scale = 0 dBFS."""

    peak_db: float
    """True peak level in dBFS (maximum absolute sample value)."""

    lufs: float
    """Integrated loudness in LUFS per ITU-R BS.1770 (K-weighted, gated)."""

    crest_factor: float
    """Peak-to-RMS ratio in dB. Higher = more dynamic headroom.
    Over-compressed material: 4–6 dB. Organic house target: 8–12 dB."""

    dynamic_range: float
    """Approximate dynamic range in dB (95th–5th percentile loudness difference)."""

    loudness_range: float
    """LRA in Loudness Units: variation in short-term loudness over the track."""


# ---------------------------------------------------------------------------
# TransientProfile
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransientProfile:
    """Transient characteristics of an audio signal.

    Invariants:
        density >= 0.0 (onsets per second)
        0.0 <= sharpness <= 1.0
        0.0 <= attack_ratio <= 1.0
    """

    density: float
    """Average number of transient onsets per second.
    Busy techno: 4–8/s. Sparse ambient: 0.5–2/s."""

    sharpness: float
    """Attack sharpness 0–1: 1.0 = instantaneous attack, 0.0 = very slow.
    Reflects how quickly energy rises after each onset."""

    attack_ratio: float
    """Fraction of total duration spent in attack phases (0–1).
    High attack_ratio = punchy, percussive material."""


# ---------------------------------------------------------------------------
# MixProblem
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MixProblem:
    """A detected issue in the mix with diagnostic and remediation info.

    Severity 0 = no problem, 10 = severe problem requiring immediate attention.

    Invariants:
        0.0 <= severity <= 10.0
        frequency_range[0] <= frequency_range[1]
    """

    category: str
    """Problem category: one of 'muddiness', 'harshness', 'boominess',
    'thinness', 'narrow_stereo', 'phase_issues', 'over_compression',
    'under_compression'."""

    frequency_range: tuple[float, float]
    """Affected Hz range as (low, high). E.g. (200, 500) for muddiness."""

    severity: float
    """Severity score 0–10 (10 = most severe)."""

    description: str
    """Human-readable diagnosis with measured values.
    E.g. 'low_mid band is +4.2 dB above organic house target (−8.0 dB rel.)'."""

    recommendation: str
    """Specific, actionable fix with frequency and dB values.
    E.g. 'Try a 3 dB cut at 280 Hz on the pad with Q=2.0.'"""


# ---------------------------------------------------------------------------
# MixAnalysis — top-level aggregator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MixAnalysis:
    """Complete mix analysis result: frequency, stereo, dynamics, transients,
    and detected problems.

    The `stereo` field is None when the input signal is mono.

    Invariants:
        duration_sec > 0.0
        sample_rate > 0
    """

    frequency: FrequencyProfile
    """7-band spectral balance, centroid, tilt, and flatness."""

    stereo: StereoImage | None
    """Stereo field analysis. None if the input was mono."""

    dynamics: DynamicProfile
    """Loudness, crest factor, LUFS, and dynamic range."""

    transients: TransientProfile
    """Transient density, attack sharpness, and attack ratio."""

    problems: tuple[MixProblem, ...]
    """Detected mix problems, ordered by severity (highest first)."""

    genre: str
    """Genre used for comparison targets (e.g. 'organic house')."""

    duration_sec: float
    """Duration of the analyzed audio in seconds."""

    sample_rate: int
    """Sample rate of the input signal in Hz."""
