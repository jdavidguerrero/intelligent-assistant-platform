"""
core/mix_analysis/attribution.py — Attribute master-bus problems to source stems.

Pure module: no I/O, no side effects.

Theory
======
When a problem is detected in the master bus (e.g. muddiness at 280 Hz), it
doesn't mean every stem is responsible.  The problem originates in one or more
source stems whose spectral energy overlaps with the problem frequency range.

This module:
  1. Maps each master-bus problem to the frequency band(s) it affects.
  2. Scores each stem's contribution to those bands using its StemFootprint.
  3. Normalises contributions to percentages summing to 100%.
  4. Generates a per-stem recommended fix based on the contribution level.

Masking detection
=================
Two stems mask each other if they both have significant energy (≥ 0.4 relative
energy) in the same frequency band.  The louder stem should EQ the quieter stem
out of that band to create separation.

Volume balance
==============
Genre-typical RMS levels per stem type are defined as rough targets.  Stems
outside the target range receive a volume recommendation.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.mix_analysis.stems import StemFootprint, StemType
from core.mix_analysis.types import BAND_NAMES, MixAnalysis, MixProblem

# ---------------------------------------------------------------------------
# Problem-to-band mapping
# ---------------------------------------------------------------------------

# Which bands are implicated by each mix problem category
_PROBLEM_BANDS: dict[str, tuple[str, ...]] = {
    "muddiness": ("sub", "low", "low_mid"),
    "boominess": ("sub", "low"),
    "harshness": ("high_mid", "high"),
    "thinness": ("low", "low_mid", "mid"),
    "narrow_stereo": ("mid", "high_mid", "high"),  # stereo affected at higher freqs
    "phase_issues": ("sub", "low"),               # phase problems appear at low freqs first
    "over_compression": ("sub", "low", "mid"),    # over-comp squashes dynamics everywhere
    "under_compression": ("mid", "high_mid"),     # under-comp = transients dominate mids
}


def _bands_for_problem(problem: MixProblem) -> tuple[str, ...]:
    """Return the frequency bands most implicated by a detected problem."""
    return _PROBLEM_BANDS.get(problem.category, ("low_mid", "mid"))


# ---------------------------------------------------------------------------
# StemContribution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StemContribution:
    """A single stem's contribution to a master-bus problem.

    Invariants:
        0.0 <= contribution_pct <= 100.0
        contribution_pct values across all stems for a problem sum to 100.0
    """

    track_name: str
    """Name of the contributing track."""

    stem_type: StemType
    """Detected stem type."""

    contribution_pct: float
    """Percentage of the master problem attributable to this stem (0–100)."""

    band_energies: dict[str, float]
    """Relative energy in the problem bands (0–1), keyed by band name."""

    recommended_fix: str
    """Short actionable recommendation for this stem."""

    def as_dict(self) -> dict[str, object]:
        """Serialise to plain dict."""
        return {
            "track_name": self.track_name,
            "stem_type": self.stem_type.value,
            "contribution_pct": round(self.contribution_pct, 1),
            "band_energies": {k: round(v, 3) for k, v in self.band_energies.items()},
            "recommended_fix": self.recommended_fix,
        }


# ---------------------------------------------------------------------------
# Fix recommendation templates
# ---------------------------------------------------------------------------


def _recommend_fix(
    problem_category: str,
    stem_type: StemType,
    contribution_pct: float,
    bands: dict[str, float],
) -> str:
    """Generate a short fix recommendation for a stem's contribution to a problem."""
    if contribution_pct < 10.0:
        return "Minimal contribution — no action required."

    if problem_category == "muddiness":
        worst_band = max(
            (b for b in ("sub", "low", "low_mid") if b in bands),
            key=lambda b: bands.get(b, 0.0),
            default="low_mid",
        )
        band_label = {"sub": "60 Hz", "low": "120 Hz", "low_mid": "300 Hz"}.get(worst_band, "280 Hz")
        if stem_type in (StemType.bass, StemType.kick):
            return f"High-pass or EQ cut around {band_label} on this stem to reduce master mud."
        return f"Cut 2–4 dB at {band_label} on this stem — it contributes {contribution_pct:.0f}% of the muddiness."

    if problem_category == "boominess":
        if stem_type in (StemType.kick, StemType.bass):
            return "Tighten sub with sidechain compression or high-pass at 30–40 Hz."
        return "High-pass at 80 Hz to remove unwanted low-end on this stem."

    if problem_category == "harshness":
        if stem_type == StemType.vocal:
            return "De-ess and apply gentle high-shelf cut at 8 kHz."
        return "Shelve down 2–3 dB above 5 kHz on this stem."

    if problem_category == "thinness":
        if stem_type in (StemType.bass, StemType.pad):
            return "Boost low-mid (200–350 Hz) +2 dB to add body."
        return "Add low-mid presence — try +1.5 dB at 250 Hz, Q=1.5."

    if problem_category == "narrow_stereo":
        if stem_type in (StemType.pad, StemType.fx):
            return "Widen stereo image with mid-side processing or chorus (keep mono below 120 Hz)."
        return "Consider stereo widening on this stem's high frequencies."

    if problem_category == "phase_issues":
        return "Check phase alignment vs kick / bass — flip phase and A/B test."

    if problem_category == "over_compression":
        return "Reduce compressor ratio or increase attack time to restore transient dynamics."

    if problem_category == "under_compression":
        return "Apply light compression (3:1 ratio, fast attack) to control transient peaks."

    return f"Reduce this stem's contribution to {problem_category.replace('_', ' ')} — "  \
           f"start with a 1–2 dB level reduction."


# ---------------------------------------------------------------------------
# Attribution engine
# ---------------------------------------------------------------------------


def attribute_problems(
    master_analysis: MixAnalysis,
    stem_footprints: dict[str, StemFootprint],
) -> dict[str, list[StemContribution]]:
    """Attribute each master-bus problem to the most likely source stems.

    For each detected problem in the master:
      1. Identify the frequency bands implicated by that problem type.
      2. Score each stem by the sum of its relative energies in those bands.
      3. Normalise scores to percentages summing to 100%.
      4. Filter out stems contributing < 5% (noise floor).
      5. Re-normalise the remaining contributions.

    Args:
        master_analysis: MixAnalysis of the master output.
        stem_footprints: Map of track_name → StemFootprint.

    Returns:
        Dict keyed by problem category, each mapping to a list of
        StemContribution objects sorted by contribution_pct descending.
        Empty dict if no problems detected.
    """
    result: dict[str, list[StemContribution]] = {}

    for problem in master_analysis.problems:
        bands = _bands_for_problem(problem)

        # Score each stem in the problem bands
        scores: dict[str, float] = {}
        band_contributions: dict[str, dict[str, float]] = {}

        for name, fp in stem_footprints.items():
            band_vals: dict[str, float] = {}
            total = 0.0
            for band in bands:
                val = fp.band_energy(band)
                band_vals[band] = val
                total += val
            scores[name] = total
            band_contributions[name] = band_vals

        total_score = sum(scores.values())
        if total_score == 0.0:
            continue

        # Raw percentages
        raw_pcts: dict[str, float] = {
            name: (score / total_score) * 100.0
            for name, score in scores.items()
        }

        # Filter out stems with < 5% contribution
        filtered = {name: pct for name, pct in raw_pcts.items() if pct >= 5.0}
        if not filtered:
            # Keep top contributor if all are below threshold
            best = max(raw_pcts, key=lambda n: raw_pcts[n])
            filtered = {best: raw_pcts[best]}

        # Re-normalise filtered contributions to 100%
        filtered_total = sum(filtered.values())
        final_pcts: dict[str, float] = {
            name: (pct / filtered_total) * 100.0
            for name, pct in filtered.items()
        }

        contributions = [
            StemContribution(
                track_name=name,
                stem_type=stem_footprints[name].stem_type,
                contribution_pct=round(pct, 1),
                band_energies={b: round(band_contributions[name].get(b, 0.0), 3) for b in bands},
                recommended_fix=_recommend_fix(
                    problem.category,
                    stem_footprints[name].stem_type,
                    pct,
                    band_contributions[name],
                ),
            )
            for name, pct in final_pcts.items()
        ]

        contributions.sort(key=lambda c: c.contribution_pct, reverse=True)
        result[problem.category] = contributions

    return result


# ---------------------------------------------------------------------------
# Masking detection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MaskingPair:
    """Two stems that compete in the same frequency band.

    Invariants:
        band is one of BAND_NAMES
        louder_track_rms_db >= quieter_track_rms_db
    """

    louder_track: str
    """Track with higher RMS in this band."""

    quieter_track: str
    """Track being masked by the louder track."""

    band: str
    """Band where masking occurs."""

    louder_energy: float
    """Relative energy (0–1) of the louder track in this band."""

    quieter_energy: float
    """Relative energy (0–1) of the quieter track in this band."""

    recommendation: str
    """Fix suggestion to reduce masking."""

    def as_dict(self) -> dict[str, object]:
        """Serialise to plain dict."""
        return {
            "louder_track": self.louder_track,
            "quieter_track": self.quieter_track,
            "band": self.band,
            "louder_energy": round(self.louder_energy, 3),
            "quieter_energy": round(self.quieter_energy, 3),
            "recommendation": self.recommendation,
        }


_MASKING_FREQ_LABELS: dict[str, str] = {
    "sub": "20–60 Hz",
    "low": "60–200 Hz",
    "low_mid": "200–500 Hz",
    "mid": "500–2000 Hz",
    "high_mid": "2–6 kHz",
    "high": "6–12 kHz",
    "air": "12–20 kHz",
}


def detect_masking(
    stem_footprints: dict[str, StemFootprint],
    *,
    threshold: float = 0.4,
) -> list[MaskingPair]:
    """Detect frequency masking between stem pairs.

    Two stems mask each other if both have relative energy >= threshold
    in the same band.  The louder stem (higher RMS) is the masker.

    Args:
        stem_footprints: Map of track_name → StemFootprint.
        threshold: Minimum relative energy (0–1) to count as significant presence.
                   Default 0.4 (40% of the stem's own peak band).

    Returns:
        List of MaskingPair objects sorted by band then by energy difference.
        Empty list if no masking detected.
    """
    names = list(stem_footprints.keys())
    pairs: list[MaskingPair] = []

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a_name, b_name = names[i], names[j]
            a_fp, b_fp = stem_footprints[a_name], stem_footprints[b_name]

            for band in BAND_NAMES:
                a_energy = a_fp.band_energy(band)
                b_energy = b_fp.band_energy(band)

                if a_energy >= threshold and b_energy >= threshold:
                    freq_label = _MASKING_FREQ_LABELS.get(band, band)

                    # Louder stem (higher RMS) is the masker
                    if a_fp.rms_db >= b_fp.rms_db:
                        louder, louder_e = a_name, a_energy
                        quieter, quieter_e = b_name, b_energy
                    else:
                        louder, louder_e = b_name, b_energy
                        quieter, quieter_e = a_name, a_energy

                    recommendation = (
                        f"Cut 2–4 dB at {freq_label} on '{quieter}' "
                        f"or boost it there on '{louder}' to create separation. "
                        f"Sidechain '{quieter}' to '{louder}' if they're rhythmically linked."
                    )

                    pairs.append(
                        MaskingPair(
                            louder_track=louder,
                            quieter_track=quieter,
                            band=band,
                            louder_energy=round(louder_e, 3),
                            quieter_energy=round(quieter_e, 3),
                            recommendation=recommendation,
                        )
                    )

    return pairs


# ---------------------------------------------------------------------------
# Volume balance suggestions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VolumeBalanceSuggestion:
    """Volume balance recommendation for a stem relative to genre targets."""

    track_name: str
    stem_type: StemType
    current_rms_db: float
    target_rms_db: float
    adjustment_db: float
    """Positive = needs gain boost, negative = needs gain reduction."""
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "track_name": self.track_name,
            "stem_type": self.stem_type.value,
            "current_rms_db": round(self.current_rms_db, 1),
            "target_rms_db": round(self.target_rms_db, 1),
            "adjustment_db": round(self.adjustment_db, 1),
            "reason": self.reason,
        }


# Typical RMS dBFS targets per stem type for a well-balanced mix
# (relative to the master output at approx –14 LUFS)
_RMS_TARGETS_DB: dict[StemType, float] = {
    StemType.kick: -18.0,
    StemType.bass: -17.0,
    StemType.percussion: -22.0,
    StemType.pad: -20.0,
    StemType.vocal: -18.0,
    StemType.fx: -24.0,
    StemType.unknown: -20.0,
}

_RMS_TOLERANCE_DB: float = 3.0  # ±3 dB is acceptable


def suggest_volume_balance(
    stem_footprints: dict[str, StemFootprint],
) -> list[VolumeBalanceSuggestion]:
    """Suggest volume adjustments to achieve genre-typical stem balance.

    Args:
        stem_footprints: Map of track_name → StemFootprint.

    Returns:
        List of VolumeBalanceSuggestion objects, one per stem outside targets.
        Empty list if all stems are within ±3 dB of genre targets.
    """
    suggestions: list[VolumeBalanceSuggestion] = []

    for name, fp in stem_footprints.items():
        target = _RMS_TARGETS_DB.get(fp.stem_type, -20.0)
        diff = target - fp.rms_db  # positive = needs boost

        if abs(diff) <= _RMS_TOLERANCE_DB:
            continue

        direction = "too loud" if diff < 0 else "too quiet"
        reason = (
            f"{name} ({fp.stem_type.value}) is {abs(diff):.1f} dB {direction} "
            f"relative to genre target ({target:.0f} dBRMS for {fp.stem_type.value})."
        )

        suggestions.append(
            VolumeBalanceSuggestion(
                track_name=name,
                stem_type=fp.stem_type,
                current_rms_db=fp.rms_db,
                target_rms_db=target,
                adjustment_db=round(diff, 1),
                reason=reason,
            )
        )

    suggestions.sort(key=lambda s: abs(s.adjustment_db), reverse=True)
    return suggestions
