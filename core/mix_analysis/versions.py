"""
core/mix_analysis/versions.py — Mix version tracking and before/after comparison.

Pure module: no I/O, no side effects.  All file operations (save/load JSON) are
handled by the tool or ingestion layer.

Design
======
A MixVersion is a frozen snapshot of a mix analysis at a point in time.
Multiple versions of the same project are tracked as a sequence.

VersionDiff captures the delta between two versions:
    - Which problems were resolved (disappeared in v2)
    - Which problems are new (appeared in v2)
    - Per-band spectral changes (improved / regressed)
    - Overall health score delta
    - Regression flags (dimension that got worse)

Serialisation
=============
MixVersion and VersionDiff both serialise to plain dicts for JSON storage.
The inverse (from dict) is handled by from_dict() class methods.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# MixVersion
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MixVersion:
    """Frozen snapshot of a mix analysis at a specific point in time.

    Invariants:
        health_score is 0–100
        problems_count >= 0
    """

    version_id: str
    """Unique identifier for this version (UUID or incrementing integer as str)."""

    timestamp: str
    """ISO 8601 timestamp when this snapshot was captured (e.g. '2025-03-01T14:22:00')."""

    genre: str
    """Genre used for analysis."""

    file_path: str
    """Absolute path to the audio file analysed."""

    health_score: float
    """Overall mix health score 0–100."""

    reference_score: float | None
    """Reference similarity score 0–100, or None if no reference was used."""

    problems_count: int
    """Number of mix problems detected."""

    problems: tuple[dict[str, Any], ...]
    """Serialised MixProblem list (category, severity, description, recommendation)."""

    spectral_bands: dict[str, float]
    """Per-band RMS values (dB) for all 7 bands."""

    dynamics: dict[str, float]
    """Serialised DynamicProfile (lufs, rms_db, peak_db, crest_factor, etc.)."""

    stereo_width: float | None
    """Overall stereo width 0–1, or None if mono."""

    label: str = ""
    """Optional human-readable label (e.g. 'After kick EQ pass')."""

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict suitable for JSON storage."""
        return {
            "version_id": self.version_id,
            "timestamp": self.timestamp,
            "genre": self.genre,
            "file_path": self.file_path,
            "health_score": round(self.health_score, 1),
            "reference_score": (
                round(self.reference_score, 1) if self.reference_score is not None else None
            ),
            "problems_count": self.problems_count,
            "problems": list(self.problems),
            "spectral_bands": {k: round(v, 2) for k, v in self.spectral_bands.items()},
            "dynamics": {k: round(v, 2) for k, v in self.dynamics.items()},
            "stereo_width": (
                round(self.stereo_width, 3) if self.stereo_width is not None else None
            ),
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MixVersion:
        """Reconstruct a MixVersion from a serialised dict."""
        return cls(
            version_id=str(d["version_id"]),
            timestamp=str(d["timestamp"]),
            genre=str(d["genre"]),
            file_path=str(d["file_path"]),
            health_score=float(d["health_score"]),
            reference_score=(
                float(d["reference_score"]) if d.get("reference_score") is not None else None
            ),
            problems_count=int(d["problems_count"]),
            problems=tuple(d.get("problems", [])),
            spectral_bands=dict(d.get("spectral_bands", {})),
            dynamics=dict(d.get("dynamics", {})),
            stereo_width=(
                float(d["stereo_width"]) if d.get("stereo_width") is not None else None
            ),
            label=str(d.get("label", "")),
        )


# ---------------------------------------------------------------------------
# VersionDiff
# ---------------------------------------------------------------------------

_BAND_IMPROVEMENT_THRESHOLD_DB: float = 1.0   # dB change to count as improved
_SCORE_REGRESSION_THRESHOLD: float = 3.0       # score points drop to flag regression


@dataclass(frozen=True)
class BandDelta:
    """Per-band change between two mix versions."""

    band: str
    v1_db: float
    v2_db: float
    delta_db: float
    """v2 − v1. Positive = v2 has more energy, negative = less energy."""
    direction: str
    """'improved', 'regressed', or 'unchanged'."""
    description: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "band": self.band,
            "v1_db": round(self.v1_db, 2),
            "v2_db": round(self.v2_db, 2),
            "delta_db": round(self.delta_db, 2),
            "direction": self.direction,
            "description": self.description,
        }


@dataclass(frozen=True)
class VersionDiff:
    """Delta between two mix versions.

    v1 = earlier version (before), v2 = later version (after).

    Invariants:
        health_delta = v2.health_score − v1.health_score
        All problem sets are disjoint (resolved ∩ new = ∅)
    """

    v1_id: str
    v2_id: str
    v1_label: str
    v2_label: str

    health_delta: float
    """v2 health − v1 health. Positive = improved."""

    v1_health: float
    v2_health: float

    v1_problems_count: int
    v2_problems_count: int

    resolved_problems: tuple[str, ...]
    """Problem categories that disappeared from v1 → v2."""

    new_problems: tuple[str, ...]
    """Problem categories that appeared in v2 but not v1."""

    improved_problems: tuple[str, ...]
    """Problem categories that decreased in severity."""

    regressed_problems: tuple[str, ...]
    """Problem categories that increased in severity."""

    band_deltas: tuple[BandDelta, ...]
    """Per-band spectral changes."""

    stereo_delta: float | None
    """v2 stereo width − v1 stereo width, or None if either is mono."""

    reference_score_delta: float | None
    """v2 reference score − v1 reference score, or None if not applicable."""

    has_regressions: bool
    """True if any metric got significantly worse (drops > threshold)."""

    summary: str
    """Human-readable one-line summary of the diff."""

    def as_dict(self) -> dict[str, Any]:
        """Serialise to plain dict."""
        return {
            "v1_id": self.v1_id,
            "v2_id": self.v2_id,
            "v1_label": self.v1_label,
            "v2_label": self.v2_label,
            "health_delta": round(self.health_delta, 1),
            "v1_health": round(self.v1_health, 1),
            "v2_health": round(self.v2_health, 1),
            "v1_problems_count": self.v1_problems_count,
            "v2_problems_count": self.v2_problems_count,
            "resolved_problems": list(self.resolved_problems),
            "new_problems": list(self.new_problems),
            "improved_problems": list(self.improved_problems),
            "regressed_problems": list(self.regressed_problems),
            "band_deltas": [d.as_dict() for d in self.band_deltas],
            "stereo_delta": (
                round(self.stereo_delta, 3) if self.stereo_delta is not None else None
            ),
            "reference_score_delta": (
                round(self.reference_score_delta, 1)
                if self.reference_score_delta is not None
                else None
            ),
            "has_regressions": self.has_regressions,
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
# compare_versions (pure function)
# ---------------------------------------------------------------------------


def _band_direction(delta_db: float, band: str) -> str:
    """Determine whether a band change is an improvement, regression, or unchanged.

    Convention: for bass/low bands, having MORE energy is often a regression
    (adds muddiness), while LESS is an improvement.  For high/air, the opposite.
    This is a heuristic — the actual genre targets would refine this.
    """
    if abs(delta_db) < _BAND_IMPROVEMENT_THRESHOLD_DB:
        return "unchanged"

    # Bands that tend to be too heavy in rough mixes
    heavy_bands = {"sub", "low", "low_mid"}
    if band in heavy_bands:
        return "improved" if delta_db < 0 else "regressed"
    # Bands that tend to need more presence
    return "improved" if delta_db > 0 else "regressed"


def compare_versions(v1: MixVersion, v2: MixVersion) -> VersionDiff:
    """Compare two mix versions and produce a structured diff.

    Args:
        v1: Earlier version (before).
        v2: Later version (after).

    Returns:
        VersionDiff with all deltas computed.

    Raises:
        ValueError: If v1 or v2 are invalid (negative health scores, etc.).
    """
    if not (0.0 <= v1.health_score <= 100.0):
        raise ValueError(f"v1.health_score must be 0–100, got {v1.health_score}")
    if not (0.0 <= v2.health_score <= 100.0):
        raise ValueError(f"v2.health_score must be 0–100, got {v2.health_score}")

    health_delta = v2.health_score - v1.health_score

    # Problem sets
    v1_categories: set[str] = {p["category"] for p in v1.problems}
    v2_categories: set[str] = {p["category"] for p in v2.problems}

    resolved = tuple(sorted(v1_categories - v2_categories))
    new_probs = tuple(sorted(v2_categories - v1_categories))

    # Severity changes for shared problems
    v1_severity: dict[str, float] = {p["category"]: float(p.get("severity", 0)) for p in v1.problems}
    v2_severity: dict[str, float] = {p["category"]: float(p.get("severity", 0)) for p in v2.problems}
    shared = v1_categories & v2_categories
    improved_probs = tuple(
        sorted(cat for cat in shared if v2_severity.get(cat, 0) < v1_severity.get(cat, 0) - 0.5)
    )
    regressed_probs = tuple(
        sorted(cat for cat in shared if v2_severity.get(cat, 0) > v1_severity.get(cat, 0) + 0.5)
    )

    # Band deltas
    band_deltas_list: list[BandDelta] = []
    all_bands = ("sub", "low", "low_mid", "mid", "high_mid", "high", "air")
    for band in all_bands:
        v1_val = v1.spectral_bands.get(band, 0.0)
        v2_val = v2.spectral_bands.get(band, 0.0)
        delta = v2_val - v1_val
        direction = _band_direction(delta, band)

        desc_parts: list[str] = []
        if direction == "improved":
            desc_parts.append(f"{band}: {delta:+.1f} dB (better)")
        elif direction == "regressed":
            desc_parts.append(f"{band}: {delta:+.1f} dB (worse)")
        else:
            desc_parts.append(f"{band}: no significant change")

        band_deltas_list.append(
            BandDelta(
                band=band,
                v1_db=round(v1_val, 2),
                v2_db=round(v2_val, 2),
                delta_db=round(delta, 2),
                direction=direction,
                description=desc_parts[0],
            )
        )

    # Stereo delta
    stereo_delta: float | None = None
    if v1.stereo_width is not None and v2.stereo_width is not None:
        stereo_delta = round(v2.stereo_width - v1.stereo_width, 3)

    # Reference score delta
    ref_delta: float | None = None
    if v1.reference_score is not None and v2.reference_score is not None:
        ref_delta = round(v2.reference_score - v1.reference_score, 1)

    # Regression detection
    has_regressions = (
        health_delta < -_SCORE_REGRESSION_THRESHOLD
        or bool(new_probs)
        or bool(regressed_probs)
        or any(d.direction == "regressed" for d in band_deltas_list)
        or (stereo_delta is not None and stereo_delta < -0.05)
    )

    # Human-readable summary
    if health_delta >= 5.0 and not has_regressions:
        summary = (
            f"Clear improvement: health score +{health_delta:.0f} pts "
            f"({v1.health_score:.0f} → {v2.health_score:.0f}). "
            f"{len(resolved)} problem(s) resolved."
        )
    elif health_delta > 0 and has_regressions:
        summary = (
            f"Mixed results: health +{health_delta:.0f} pts but regressions detected. "
            f"Check: {', '.join(regressed_probs or new_probs) or 'band regressions'}."
        )
    elif health_delta < -_SCORE_REGRESSION_THRESHOLD:
        summary = (
            f"Regression: health score {health_delta:.0f} pts "
            f"({v1.health_score:.0f} → {v2.health_score:.0f}). "
            f"{len(new_probs)} new problem(s) appeared."
        )
    else:
        summary = (
            f"Minimal change: health delta {health_delta:+.0f} pts. "
            f"{v1.problems_count} → {v2.problems_count} problems."
        )

    return VersionDiff(
        v1_id=v1.version_id,
        v2_id=v2.version_id,
        v1_label=v1.label or f"v{v1.version_id}",
        v2_label=v2.label or f"v{v2.version_id}",
        health_delta=round(health_delta, 1),
        v1_health=v1.health_score,
        v2_health=v2.health_score,
        v1_problems_count=v1.problems_count,
        v2_problems_count=v2.problems_count,
        resolved_problems=resolved,
        new_problems=new_probs,
        improved_problems=improved_probs,
        regressed_problems=regressed_probs,
        band_deltas=tuple(band_deltas_list),
        stereo_delta=stereo_delta,
        reference_score_delta=ref_delta,
        has_regressions=has_regressions,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Version store helpers (pure serialisation only — no file I/O)
# ---------------------------------------------------------------------------


def sort_versions_chronologically(versions: list[MixVersion]) -> list[MixVersion]:
    """Return versions sorted from oldest to newest by timestamp."""
    return sorted(versions, key=lambda v: v.timestamp)


def find_regressions(versions: list[MixVersion]) -> list[VersionDiff]:
    """Find any version-to-version regressions in a sorted history.

    Args:
        versions: List of MixVersion objects (any order — will be sorted).

    Returns:
        List of VersionDiff objects where has_regressions is True.
    """
    sorted_vs = sort_versions_chronologically(versions)
    diffs: list[VersionDiff] = []
    for i in range(1, len(sorted_vs)):
        diff = compare_versions(sorted_vs[i - 1], sorted_vs[i])
        if diff.has_regressions:
            diffs.append(diff)
    return diffs
