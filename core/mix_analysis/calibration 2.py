"""
core/mix_analysis/calibration.py — Genre target calibration from reference analysis.

Theory
======
Manually authored genre_targets/ YAML files are educated guesses.
This module replaces guesswork with data: analyze N commercial tracks from a
genre, compute mean ± 1σ for every relevant metric, and output a GenreTarget
that reflects what "good" actually sounds like in that genre.

Use-case: "I have 20 Organic House releases I love. Tell me what they have in
common, spectrally and dynamically, so I can target those numbers."

Statistical approach
====================
- Mean (μ): centre of the distribution — the "target" value.
- Std dev (σ): spread of the distribution — how much variation is typical.
- Acceptable range = [μ − σ, μ + σ]. Values inside this range score well;
  values outside this range trigger problem detection.
- Minimum 2 references required (single-track std dev is meaningless).
- update_genre_targets() implements an online mean update so you can add new
  references to an existing target without storing all the raw data.

Serialization
=============
target_to_dict() / target_from_dict() produce YAML-compatible dicts that
are structurally identical to the existing manually authored YAML files
(so they can be drop-in replacements in the genre_targets/ package data).

Design
======
- Pure module: no I/O, no env vars, no timestamps.
- All inputs are frozen dataclasses (MixReport, GenreTarget).
- Uses only stdlib math (no numpy) to keep the dependency graph clean.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from core.mix_analysis.types import (
    BAND_NAMES,
    GenreTarget,
    MetricStats,
    MixReport,
)

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _stats(values: list[float]) -> MetricStats:
    """Compute mean and population standard deviation from a list of floats.

    Args:
        values: Non-empty list of float measurements.

    Returns:
        MetricStats with mean and std (population std dev).

    Raises:
        ValueError: If values is empty.
    """
    if not values:
        raise ValueError("Cannot compute stats from an empty list")
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    std = math.sqrt(variance)
    return MetricStats(mean=round(mean, 4), std=round(std, 4))


def _extract_track_width(report: MixReport) -> float:
    """Return stereo width (0 for mono inputs)."""
    if report.stereo is not None and not report.stereo.is_mono:
        return report.stereo.width
    return 0.0


def _weighted_stats_update(
    existing: MetricStats,
    existing_n: int,
    new_values: list[float],
) -> MetricStats:
    """Online mean + variance update (Welford-style pooled update).

    Combines an existing MetricStats (from n_existing samples) with a new
    batch of values to produce an updated MetricStats without storing all
    historical raw data.

    Uses the pooled variance formula:
        combined_mean = (n_old * mean_old + n_new * mean_new) / n_total
        combined_var  = pooled variance of both groups

    Args:
        existing:   Existing MetricStats (from prior calibration run).
        existing_n: Number of samples that produced `existing`.
        new_values: New raw values to incorporate.

    Returns:
        Updated MetricStats reflecting all samples combined.
    """
    if not new_values:
        return existing

    n_new = len(new_values)
    new_mean = sum(new_values) / n_new
    new_var = sum((v - new_mean) ** 2 for v in new_values) / n_new

    n_total = existing_n + n_new
    old_mean = existing.mean
    old_var = existing.std**2

    combined_mean = (existing_n * old_mean + n_new * new_mean) / n_total
    # Pooled variance: each group's within-group variance + between-group variance
    combined_var = (
        existing_n * (old_var + (old_mean - combined_mean) ** 2)
        + n_new * (new_var + (new_mean - combined_mean) ** 2)
    ) / n_total
    return MetricStats(
        mean=round(combined_mean, 4),
        std=round(math.sqrt(combined_var), 4),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def calibrate_genre_targets(
    analyses: Sequence[MixReport],
    genre: str,
) -> GenreTarget:
    """Compute a GenreTarget from N reference track analyses.

    Extracts every relevant metric from each MixReport and computes
    mean ± std for each. The resulting GenreTarget's acceptable ranges
    [mean − std, mean + std] define what "sounds right" for this genre.

    Args:
        analyses: Sequence of MixReport objects from MixAnalysisEngine.
                  All tracks should be from the target genre.
        genre:    Genre name (e.g. 'organic house').

    Returns:
        GenreTarget with per-metric MetricStats for all 16 metrics.

    Raises:
        ValueError: If fewer than 2 analyses are provided (std dev requires ≥ 2).
    """
    if len(analyses) < 2:
        raise ValueError(
            f"calibrate_genre_targets() requires at least 2 reference tracks, "
            f"got {len(analyses)}. Use at least 5 for meaningful calibration."
        )

    # --- Extract per-metric lists ---
    band_vals: dict[str, list[float]] = {b: [] for b in BAND_NAMES}
    centroid_vals: list[float] = []
    tilt_vals: list[float] = []
    width_vals: list[float] = []
    lufs_vals: list[float] = []
    crest_vals: list[float] = []
    lra_vals: list[float] = []
    density_vals: list[float] = []
    sharpness_vals: list[float] = []

    for report in analyses:
        for band in BAND_NAMES:
            band_vals[band].append(report.frequency.bands.get(band))
        centroid_vals.append(report.frequency.spectral_centroid)
        tilt_vals.append(report.frequency.spectral_tilt)
        width_vals.append(_extract_track_width(report))
        lufs_vals.append(report.dynamics.lufs)
        crest_vals.append(report.dynamics.crest_factor)
        lra_vals.append(report.dynamics.loudness_range)
        density_vals.append(report.transients.density)
        sharpness_vals.append(report.transients.sharpness)

    return GenreTarget(
        genre=genre,
        num_references=len(analyses),
        sub_db=_stats(band_vals["sub"]),
        low_db=_stats(band_vals["low"]),
        low_mid_db=_stats(band_vals["low_mid"]),
        mid_db=_stats(band_vals["mid"]),
        high_mid_db=_stats(band_vals["high_mid"]),
        high_db=_stats(band_vals["high"]),
        air_db=_stats(band_vals["air"]),
        centroid_hz=_stats(centroid_vals),
        tilt_db_oct=_stats(tilt_vals),
        width=_stats(width_vals),
        lufs=_stats(lufs_vals),
        crest_factor_db=_stats(crest_vals),
        lra_lu=_stats(lra_vals),
        density=_stats(density_vals),
        sharpness=_stats(sharpness_vals),
    )


def update_genre_targets(
    new_analyses: Sequence[MixReport],
    existing_target: GenreTarget,
) -> GenreTarget:
    """Extend an existing GenreTarget with new reference tracks.

    Uses a pooled variance formula to incorporate new data without
    requiring the original raw measurements (online update).

    Args:
        new_analyses:     New MixReport objects to incorporate.
        existing_target:  Previously calibrated GenreTarget.

    Returns:
        Updated GenreTarget reflecting all samples (old + new).

    Raises:
        ValueError: If new_analyses is empty.
    """
    if not new_analyses:
        raise ValueError("new_analyses must not be empty")

    n_old = existing_target.num_references

    def _new_vals(band: str | None = None, attr: str | None = None) -> list[float]:
        if band is not None:
            return [r.frequency.bands.get(band) for r in new_analyses]
        if attr == "centroid":
            return [r.frequency.spectral_centroid for r in new_analyses]
        if attr == "tilt":
            return [r.frequency.spectral_tilt for r in new_analyses]
        if attr == "width":
            return [_extract_track_width(r) for r in new_analyses]
        if attr == "lufs":
            return [r.dynamics.lufs for r in new_analyses]
        if attr == "crest":
            return [r.dynamics.crest_factor for r in new_analyses]
        if attr == "lra":
            return [r.dynamics.loudness_range for r in new_analyses]
        if attr == "density":
            return [r.transients.density for r in new_analyses]
        if attr == "sharpness":
            return [r.transients.sharpness for r in new_analyses]
        return []

    def upd(existing: MetricStats, vals: list[float]) -> MetricStats:
        return _weighted_stats_update(existing, n_old, vals)

    return GenreTarget(
        genre=existing_target.genre,
        num_references=n_old + len(new_analyses),
        sub_db=upd(existing_target.sub_db, _new_vals(band="sub")),
        low_db=upd(existing_target.low_db, _new_vals(band="low")),
        low_mid_db=upd(existing_target.low_mid_db, _new_vals(band="low_mid")),
        mid_db=upd(existing_target.mid_db, _new_vals(band="mid")),
        high_mid_db=upd(existing_target.high_mid_db, _new_vals(band="high_mid")),
        high_db=upd(existing_target.high_db, _new_vals(band="high")),
        air_db=upd(existing_target.air_db, _new_vals(band="air")),
        centroid_hz=upd(existing_target.centroid_hz, _new_vals(attr="centroid")),
        tilt_db_oct=upd(existing_target.tilt_db_oct, _new_vals(attr="tilt")),
        width=upd(existing_target.width, _new_vals(attr="width")),
        lufs=upd(existing_target.lufs, _new_vals(attr="lufs")),
        crest_factor_db=upd(existing_target.crest_factor_db, _new_vals(attr="crest")),
        lra_lu=upd(existing_target.lra_lu, _new_vals(attr="lra")),
        density=upd(existing_target.density, _new_vals(attr="density")),
        sharpness=upd(existing_target.sharpness, _new_vals(attr="sharpness")),
    )


def target_to_dict(target: GenreTarget) -> dict[str, Any]:
    """Serialize a GenreTarget to a YAML-compatible nested dict.

    The output format matches the existing manually authored genre_targets/
    YAML files so calibrated targets can be used as drop-in replacements.

    Returns:
        Nested dict with keys: genre, num_references, bands, stereo,
        dynamics, transients. Each leaf is {mean, std}.
    """

    def _s(ms: MetricStats) -> dict[str, float]:
        return {"mean": ms.mean, "std": ms.std}

    return {
        "genre": target.genre,
        "num_references": target.num_references,
        "bands": {
            "sub_db": _s(target.sub_db),
            "low_db": _s(target.low_db),
            "low_mid_db": _s(target.low_mid_db),
            "mid_db": _s(target.mid_db),
            "high_mid_db": _s(target.high_mid_db),
            "high_db": _s(target.high_db),
            "air_db": _s(target.air_db),
        },
        "tonal": {
            "centroid_hz": _s(target.centroid_hz),
            "tilt_db_oct": _s(target.tilt_db_oct),
        },
        "stereo": {
            "width": _s(target.width),
        },
        "dynamics": {
            "lufs": _s(target.lufs),
            "crest_factor_db": _s(target.crest_factor_db),
            "lra_lu": _s(target.lra_lu),
        },
        "transients": {
            "density": _s(target.density),
            "sharpness": _s(target.sharpness),
        },
    }


def target_from_dict(data: dict[str, Any]) -> GenreTarget:
    """Deserialize a GenreTarget from a dict (e.g. loaded from YAML).

    Args:
        data: Dict in the format produced by target_to_dict().

    Returns:
        GenreTarget frozen dataclass.

    Raises:
        KeyError:   If required keys are missing.
        ValueError: If mean/std values are not numeric.
    """

    def _ms(d: dict[str, float]) -> MetricStats:
        return MetricStats(mean=float(d["mean"]), std=float(d["std"]))

    bands = data["bands"]
    tonal = data["tonal"]
    stereo = data["stereo"]
    dynamics = data["dynamics"]
    transients = data["transients"]

    return GenreTarget(
        genre=str(data["genre"]),
        num_references=int(data.get("num_references", 0)),
        sub_db=_ms(bands["sub_db"]),
        low_db=_ms(bands["low_db"]),
        low_mid_db=_ms(bands["low_mid_db"]),
        mid_db=_ms(bands["mid_db"]),
        high_mid_db=_ms(bands["high_mid_db"]),
        high_db=_ms(bands["high_db"]),
        air_db=_ms(bands["air_db"]),
        centroid_hz=_ms(tonal["centroid_hz"]),
        tilt_db_oct=_ms(tonal["tilt_db_oct"]),
        width=_ms(stereo["width"]),
        lufs=_ms(dynamics["lufs"]),
        crest_factor_db=_ms(dynamics["crest_factor_db"]),
        lra_lu=_ms(dynamics["lra_lu"]),
        density=_ms(transients["density"]),
        sharpness=_ms(transients["sharpness"]),
    )
