"""
core/mix_analysis/stems.py — Stem type detection and per-stem frequency footprint.

Pure module: no I/O, no side effects.  Takes pre-computed MixAnalysis objects
(produced by MixAnalysisEngine) and classifies each stem by type, then computes
a spectral footprint describing where each stem lives in the frequency spectrum.

Stem type detection heuristics
================================
Based on the spectral and dynamic profile of each stem:

    kick        Strong sub/low transient, high crest factor, low mid content
    bass        Dominant sub/low energy, sustained (low crest), low-mid present
    pad         Broad frequency content, low transient density, wide stereo
    percussion  High transient density, energy above 1kHz, low sustained content
    vocal       Mid/high-mid dominant (300Hz–5kHz), high spectral flatness variance
    fx          Sparse transients, very wide stereo, often air band present
    unknown     Cannot be classified with confidence

Frequency footprint
====================
A StemFootprint records which of the 7 canonical bands each stem dominates
(i.e., has energy above a threshold relative to the stem's own overall level).
This is used by attribution.py to correlate master problems with source stems.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.mix_analysis.types import BAND_NAMES, MixAnalysis

# ---------------------------------------------------------------------------
# StemType enum
# ---------------------------------------------------------------------------


class StemType(str, Enum):
    """Detected type of an audio stem based on spectral + dynamic profile."""

    kick = "kick"
    bass = "bass"
    pad = "pad"
    percussion = "percussion"
    vocal = "vocal"
    fx = "fx"
    unknown = "unknown"


# ---------------------------------------------------------------------------
# StemFootprint frozen dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StemFootprint:
    """Spectral presence summary for a single stem.

    Records which frequency bands the stem occupies and how much energy it
    contributes to each.  Used for cross-stem masking and attribution analysis.

    Invariants:
        0.0 <= band energy values <= 1.0 (normalised relative to peak band)
        dominant_bands is a subset of BAND_NAMES
    """

    track_name: str
    """Name of the track this footprint belongs to."""

    stem_type: StemType
    """Detected stem type."""

    # Per-band relative energy: 1.0 = most energetic band for this stem
    sub: float
    low: float
    low_mid: float
    mid: float
    high_mid: float
    high: float
    air: float

    dominant_bands: tuple[str, ...]
    """Bands where this stem has significant energy (relative energy >= 0.5)."""

    rms_db: float
    """Overall RMS level of this stem in dBFS."""

    crest_factor_db: float
    """Crest factor (dynamics) of this stem in dB."""

    onset_density: float
    """Onset density (transients per second)."""

    def band_energy(self, band: str) -> float:
        """Return relative energy (0–1) for the named band.

        Raises:
            ValueError: If band is not one of the 7 canonical names.
        """
        mapping = {
            "sub": self.sub,
            "low": self.low,
            "low_mid": self.low_mid,
            "mid": self.mid,
            "high_mid": self.high_mid,
            "high": self.high,
            "air": self.air,
        }
        if band not in mapping:
            raise ValueError(f"Unknown band: {band!r}. Valid: {list(mapping)}")
        return mapping[band]

    def as_dict(self) -> dict[str, object]:
        """Serialise to a plain dict for JSON output."""
        return {
            "track_name": self.track_name,
            "stem_type": self.stem_type.value,
            "bands": {
                "sub": round(self.sub, 3),
                "low": round(self.low, 3),
                "low_mid": round(self.low_mid, 3),
                "mid": round(self.mid, 3),
                "high_mid": round(self.high_mid, 3),
                "high": round(self.high, 3),
                "air": round(self.air, 3),
            },
            "dominant_bands": list(self.dominant_bands),
            "rms_db": round(self.rms_db, 2),
            "crest_factor_db": round(self.crest_factor_db, 2),
            "onset_density": round(self.onset_density, 3),
        }


# ---------------------------------------------------------------------------
# Stem type detection
# ---------------------------------------------------------------------------


def detect_stem_type(analysis: MixAnalysis) -> StemType:
    """Classify a stem based on its MixAnalysis profile.

    Uses a rule-based classifier operating on spectral bands, dynamics,
    and transient characteristics.  Rules are ordered from most specific
    (kick) to least specific (unknown).

    Args:
        analysis: Pre-computed MixAnalysis for the stem.

    Returns:
        StemType enum value.
    """
    bands = analysis.frequency.bands
    dyn = analysis.dynamics
    trans = analysis.transients

    sub_energy = bands.sub      # relative to overall RMS (dB)
    low_energy = bands.low
    low_mid_energy = bands.low_mid
    mid_energy = bands.mid
    high_mid_energy = bands.high_mid
    high_energy = bands.high
    air_energy = bands.air

    crest = dyn.crest_factor
    density = trans.density      # onsets/sec
    sharpness = trans.sharpness  # 0–1

    # ---- Kick detection ----
    # Strong sub+low, high crest (punchy), very sharp attack, sparse density
    if (
        sub_energy > -3.0  # sub is near or above overall RMS
        and low_energy > -4.0
        and crest >= 10.0  # very dynamic (punchiness)
        and sharpness >= 0.6
        and density < 4.0   # not a busy percussion part
        and low_mid_energy < 1.0  # not much mid content
        and mid_energy < 0.0
    ):
        return StemType.kick

    # ---- Bass detection ----
    # Dominant sub/low, sustained (lower crest than kick), not much high content
    if (
        sub_energy > -2.0
        and low_energy > -3.0
        and crest < 12.0
        and high_energy < -3.0
        and air_energy < -4.0
        and density < 6.0
    ):
        return StemType.bass

    # ---- Percussion detection ----
    # High transient density, most energy above low-mid, sparse low content
    if (
        density >= 5.0
        and sharpness >= 0.5
        and (high_mid_energy > -2.0 or high_energy > -2.0 or mid_energy > -1.0)
        and sub_energy < -4.0
        and low_energy < -2.0
    ):
        return StemType.percussion

    # ---- Vocal detection ----
    # Energy concentrated in mid / high-mid (300Hz–5kHz range)
    # Low transient density, moderate crest factor
    if (
        mid_energy > -1.0
        and high_mid_energy > -2.0
        and sub_energy < -5.0
        and low_energy < -3.0
        and density < 6.0
        and 4.0 <= crest <= 14.0
    ):
        return StemType.vocal

    # ---- Pad detection ----
    # Broad spectrum but not kick-like, very low transient density, sustained
    if (
        density < 2.0
        and sharpness < 0.5
        and crest < 8.0  # very sustained/compressed
        and (
            (low_mid_energy > -3.0 and mid_energy > -3.0)
            or (mid_energy > -2.0 and high_mid_energy > -2.0)
        )
    ):
        return StemType.pad

    # ---- FX detection ----
    # Very sparse transients OR air-band dominant, unusual spectral shape
    if density < 1.0 or air_energy > high_mid_energy + 3.0:
        return StemType.fx

    return StemType.unknown


# ---------------------------------------------------------------------------
# Footprint computation
# ---------------------------------------------------------------------------


def compute_stem_footprint(track_name: str, analysis: MixAnalysis) -> StemFootprint:
    """Compute a normalised frequency footprint for a stem.

    Normalises band energies so the most energetic band = 1.0.
    Identifies dominant bands (relative energy >= 0.5 after normalisation).

    Args:
        track_name: Human-readable track name.
        analysis: Pre-computed MixAnalysis for this stem.

    Returns:
        StemFootprint with per-band relative energies and detected stem type.
    """
    bands = analysis.frequency.bands

    # Raw band dB values relative to overall RMS
    raw: dict[str, float] = bands.as_dict()

    # Shift so the maximum band = 0 dB, then normalise to [0, 1] range.
    # We use the formula: relative = 10^((band_db - max_db) / 20)
    # This gives 1.0 for the loudest band and < 1.0 for others.
    max_db = max(raw.values())
    normalised: dict[str, float] = {}
    for band in BAND_NAMES:
        delta_db = raw[band] - max_db
        # Clamp to [-40, 0] dB range before converting, so very quiet bands → 0.01
        clamped = max(-40.0, delta_db)
        normalised[band] = 10.0 ** (clamped / 20.0)

    dominant_bands = tuple(
        band for band in BAND_NAMES if normalised[band] >= 0.5
    )

    stem_type = detect_stem_type(analysis)

    return StemFootprint(
        track_name=track_name,
        stem_type=stem_type,
        sub=normalised["sub"],
        low=normalised["low"],
        low_mid=normalised["low_mid"],
        mid=normalised["mid"],
        high_mid=normalised["high_mid"],
        high=normalised["high"],
        air=normalised["air"],
        dominant_bands=dominant_bands,
        rms_db=round(analysis.dynamics.rms_db, 2),
        crest_factor_db=round(analysis.dynamics.crest_factor, 2),
        onset_density=round(analysis.transients.density, 3),
    )


# ---------------------------------------------------------------------------
# Multi-stem orchestration (pure — takes pre-computed analyses)
# ---------------------------------------------------------------------------


def classify_stems(
    stem_analyses: dict[str, MixAnalysis],
) -> dict[str, StemType]:
    """Detect stem type for each track in the stem map.

    Args:
        stem_analyses: Map of track_name → MixAnalysis.

    Returns:
        Map of track_name → StemType.
    """
    return {name: detect_stem_type(analysis) for name, analysis in stem_analyses.items()}


def compute_all_footprints(
    stem_analyses: dict[str, MixAnalysis],
) -> dict[str, StemFootprint]:
    """Compute spectral footprints for every stem.

    Args:
        stem_analyses: Map of track_name → MixAnalysis.

    Returns:
        Map of track_name → StemFootprint.
    """
    return {
        name: compute_stem_footprint(name, analysis)
        for name, analysis in stem_analyses.items()
    }
