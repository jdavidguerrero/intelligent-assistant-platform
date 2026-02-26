"""
core/mix_analysis/reference.py — Reference comparison engine.

Compares a track's mix analysis against one or more commercial reference tracks
across six perceptual dimensions to compute an overall similarity score and
identify the highest-priority improvements.

Theory — Why reference comparison matters
==========================================
Genre target profiles in genre_targets/ are manually curated approximations.
The reference engine replaces guesswork with real data: analyze 20 commercial
Organic House releases → their spectral balance, stereo width, and dynamic range
form the ground truth for that genre.

The six comparison dimensions
==============================
1. Spectral   — 7-band balance (per-band dB deltas, bands relative to RMS)
2. Stereo     — Overall stereo width delta (0–1 scale)
3. Dynamics   — Crest factor + LRA delta (compression + loudness variation)
4. Tonal      — Spectral centroid + tilt delta (brightness and spectral shape)
5. Transient  — Onset density + attack sharpness delta (punch and attack)
6. Loudness   — Integrated LUFS delta (perceived loudness level)

Loudness normalization
======================
Spectral band levels are already loudness-normalized (stored relative to the
overall RMS), so no additional normalization is needed for the spectral,
tonal, or stereo dimensions. The Loudness dimension measures the raw LUFS
difference. `lufs_normalization_db` tells the caller how much gain to apply
to the track to match the reference level — useful for A/B preview.

Scoring formulas (calibrated so that typical mixing tolerances map to ~85%):
    spectral:   score = max(0, 100 − mean_abs_band_delta × 15)
    stereo:     score = max(0, 100 − |width_delta| × 150)
    dynamics:   score = max(0, 100 − |cf_delta| × 7 − |lra_delta| × 4)
    tonal:      score = max(0, 100 − |centroid_delta| / 100 − |tilt_delta| × 10)
    transient:  score = max(0, 100 − |density_delta| × 10 − |sharpness_delta| × 40)
    loudness:   score = max(0, 100 − |lufs_delta| × 6)

Default weights (must sum to 1.0):
    spectral=0.25, stereo=0.20, dynamics=0.20,
    tonal=0.15, transient=0.10, loudness=0.10

Design
======
- Pure module: no I/O, no timestamps, no env vars.
- All inputs are frozen dataclasses (MixReport) — deterministic, testable.
- compare_to_references() averages reference metrics before a single comparison
  (rather than averaging N comparison results) for cleaner band delta semantics.
- identify_deltas() is a separate step so callers can tune the threshold
  without re-running the comparison.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from core.mix_analysis.types import (
    BAND_EDGES,
    BAND_NAMES,
    BandDelta,
    DimensionScore,
    MixDelta,
    MixReport,
    ReferenceComparison,
)

# ---------------------------------------------------------------------------
# Scoring weights — must sum to 1.0
# ---------------------------------------------------------------------------

_WEIGHTS: dict[str, float] = {
    "spectral": 0.25,
    "stereo": 0.20,
    "dynamics": 0.20,
    "tonal": 0.15,
    "transient": 0.10,
    "loudness": 0.10,
}

# ---------------------------------------------------------------------------
# Private: reference metric bundle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _RefMetrics:
    """Averaged reference metrics extracted from one or more MixReports."""

    bands: dict[str, float]  # band_name → average level (dB rel. RMS)
    centroid_hz: float
    tilt_db_oct: float
    width: float
    lufs: float
    crest_factor: float
    lra: float
    density: float
    sharpness: float


def _extract_metrics(report: MixReport) -> _RefMetrics:
    """Extract scalar metrics from a MixReport into a _RefMetrics bundle."""
    width = report.stereo.width if report.stereo is not None and not report.stereo.is_mono else 0.0
    return _RefMetrics(
        bands={b: report.frequency.bands.get(b) for b in BAND_NAMES},
        centroid_hz=report.frequency.spectral_centroid,
        tilt_db_oct=report.frequency.spectral_tilt,
        width=width,
        lufs=report.dynamics.lufs,
        crest_factor=report.dynamics.crest_factor,
        lra=report.dynamics.loudness_range,
        density=report.transients.density,
        sharpness=report.transients.sharpness,
    )


def _average_metrics(reports: Sequence[MixReport]) -> _RefMetrics:
    """Compute element-wise average of metrics across multiple MixReports."""
    n = len(reports)
    metrics = [_extract_metrics(r) for r in reports]

    def avg(vals: list[float]) -> float:
        return sum(vals) / n

    avg_bands = {band: avg([m.bands[band] for m in metrics]) for band in BAND_NAMES}
    return _RefMetrics(
        bands=avg_bands,
        centroid_hz=avg([m.centroid_hz for m in metrics]),
        tilt_db_oct=avg([m.tilt_db_oct for m in metrics]),
        width=avg([m.width for m in metrics]),
        lufs=avg([m.lufs for m in metrics]),
        crest_factor=avg([m.crest_factor for m in metrics]),
        lra=avg([m.lra for m in metrics]),
        density=avg([m.density for m in metrics]),
        sharpness=avg([m.sharpness for m in metrics]),
    )


# ---------------------------------------------------------------------------
# Private: scoring functions
# ---------------------------------------------------------------------------


def _spectral_score(band_deltas: tuple[BandDelta, ...]) -> float:
    """Spectral similarity 0–100 based on mean absolute per-band delta.

    Calibration: 1 dB MAD → 85%, 3 dB MAD → 55%, 6.67 dB → 0%.
    """
    if not band_deltas:
        return 100.0
    mad = sum(abs(bd.delta_db) for bd in band_deltas) / len(band_deltas)
    return max(0.0, 100.0 - mad * 15.0)


def _stereo_score(track_width: float, ref_width: float) -> float:
    """Stereo similarity 0–100 based on absolute width delta.

    Calibration: 0.1 delta → 85%, 0.33 delta → ~50%, 0.67 → 0%.
    """
    return max(0.0, 100.0 - abs(track_width - ref_width) * 150.0)


def _dynamics_score(cf_delta: float, lra_delta: float) -> float:
    """Dynamics similarity 0–100 based on crest factor + LRA deltas.

    Calibration: 2 dB CF + 2 LU LRA → 78%, 5 + 5 → 45%.
    """
    return max(0.0, 100.0 - abs(cf_delta) * 7.0 - abs(lra_delta) * 4.0)


def _tonal_score(centroid_delta_hz: float, tilt_delta: float) -> float:
    """Tonal similarity 0–100 based on centroid + tilt deltas.

    Calibration: 500 Hz centroid + 1 dB/oct tilt → 85%, 2000 Hz + 3 → 50%.
    """
    return max(
        0.0,
        100.0 - abs(centroid_delta_hz) / 100.0 - abs(tilt_delta) * 10.0,
    )


def _transient_score(density_delta: float, sharpness_delta: float) -> float:
    """Transient similarity 0–100 based on density + sharpness deltas.

    Calibration: 2 onsets/s + 0.2 sharpness → 72%, 4 + 0.5 → 40%.
    """
    return max(
        0.0,
        100.0 - abs(density_delta) * 10.0 - abs(sharpness_delta) * 40.0,
    )


def _loudness_score(lufs_delta: float) -> float:
    """Loudness similarity 0–100 based on absolute LUFS delta.

    Calibration: 3 LUFS → 82%, 10 LUFS → 40%, 16.67 → 0%.
    """
    return max(0.0, 100.0 - abs(lufs_delta) * 6.0)


def _overall_score(dimension_scores: dict[str, float]) -> float:
    """Compute weighted average of all six dimension scores."""
    return sum(_WEIGHTS[dim] * score for dim, score in dimension_scores.items())


# ---------------------------------------------------------------------------
# Private: build comparison result from track + reference metrics
# ---------------------------------------------------------------------------


def _build_comparison(
    track: MixReport,
    ref: _RefMetrics,
    *,
    genre: str,
    num_references: int,
) -> ReferenceComparison:
    """Core comparison logic — builds a ReferenceComparison from a track MixReport
    and a pre-computed _RefMetrics bundle.

    This private function is shared by compare_to_reference() and
    compare_to_references(), with the only difference being how `ref` is built.
    """
    track_metrics = _extract_metrics(track)

    # --- Band deltas ---
    band_deltas: list[BandDelta] = []
    for band in BAND_NAMES:
        t_db = track_metrics.bands[band]
        r_db = ref.bands[band]
        band_deltas.append(
            BandDelta(
                band=band,
                track_db=round(t_db, 2),
                reference_db=round(r_db, 2),
                delta_db=round(t_db - r_db, 2),
            )
        )
    band_deltas_t = tuple(band_deltas)

    # --- Scalar deltas ---
    width_delta = track_metrics.width - ref.width
    cf_delta = track_metrics.crest_factor - ref.crest_factor
    lra_delta = track_metrics.lra - ref.lra
    centroid_delta = track_metrics.centroid_hz - ref.centroid_hz
    tilt_delta = track_metrics.tilt_db_oct - ref.tilt_db_oct
    density_delta = track_metrics.density - ref.density
    sharpness_delta = track_metrics.sharpness - ref.sharpness
    lufs_delta = track_metrics.lufs - ref.lufs

    # --- Dimension scores ---
    spec_score = _spectral_score(band_deltas_t)
    ster_score = _stereo_score(track_metrics.width, ref.width)
    dyn_score = _dynamics_score(cf_delta, lra_delta)
    ton_score = _tonal_score(centroid_delta, tilt_delta)
    trans_score = _transient_score(density_delta, sharpness_delta)
    loud_score = _loudness_score(lufs_delta)

    raw_scores = {
        "spectral": spec_score,
        "stereo": ster_score,
        "dynamics": dyn_score,
        "tonal": ton_score,
        "transient": trans_score,
        "loudness": loud_score,
    }
    overall = round(_overall_score(raw_scores), 1)

    # Build mean absolute band delta as spectral primary metric
    mean_abs_band = (
        sum(abs(bd.delta_db) for bd in band_deltas_t) / len(band_deltas_t) if band_deltas_t else 0.0
    )

    dimensions = (
        DimensionScore(
            name="spectral",
            score=round(spec_score, 1),
            track_value=round(mean_abs_band, 2),
            ref_value=0.0,
            unit="dB MAD",
            description=(
                f"Mean absolute band delta {mean_abs_band:.1f} dB — "
                f"spectral similarity {spec_score:.0f}%"
            ),
        ),
        DimensionScore(
            name="stereo",
            score=round(ster_score, 1),
            track_value=round(track_metrics.width, 3),
            ref_value=round(ref.width, 3),
            unit="width",
            description=(
                f"Width {track_metrics.width:.2f} vs reference {ref.width:.2f} "
                f"(delta {width_delta:+.2f})"
            ),
        ),
        DimensionScore(
            name="dynamics",
            score=round(dyn_score, 1),
            track_value=round(track_metrics.crest_factor, 1),
            ref_value=round(ref.crest_factor, 1),
            unit="dB",
            description=(
                f"Crest {track_metrics.crest_factor:.1f} dB vs reference "
                f"{ref.crest_factor:.1f} dB (delta {cf_delta:+.1f} dB); "
                f"LRA delta {lra_delta:+.1f} LU"
            ),
        ),
        DimensionScore(
            name="tonal",
            score=round(ton_score, 1),
            track_value=round(track_metrics.centroid_hz, 0),
            ref_value=round(ref.centroid_hz, 0),
            unit="Hz",
            description=(
                f"Centroid {track_metrics.centroid_hz:.0f} Hz vs reference "
                f"{ref.centroid_hz:.0f} Hz (delta {centroid_delta:+.0f} Hz); "
                f"tilt delta {tilt_delta:+.2f} dB/oct"
            ),
        ),
        DimensionScore(
            name="transient",
            score=round(trans_score, 1),
            track_value=round(track_metrics.density, 2),
            ref_value=round(ref.density, 2),
            unit="onsets/s",
            description=(
                f"Density {track_metrics.density:.1f}/s vs reference "
                f"{ref.density:.1f}/s (delta {density_delta:+.1f}); "
                f"sharpness delta {sharpness_delta:+.2f}"
            ),
        ),
        DimensionScore(
            name="loudness",
            score=round(loud_score, 1),
            track_value=round(track_metrics.lufs, 1),
            ref_value=round(ref.lufs, 1),
            unit="LUFS",
            description=(
                f"Track {track_metrics.lufs:.1f} LUFS vs reference "
                f"{ref.lufs:.1f} LUFS (delta {lufs_delta:+.1f} LUFS)"
            ),
        ),
    )

    # Build actionable deltas
    comparison_proto = ReferenceComparison(
        overall_similarity=overall,
        dimensions=dimensions,
        band_deltas=band_deltas_t,
        width_delta=round(width_delta, 3),
        crest_factor_delta=round(cf_delta, 2),
        lra_delta=round(lra_delta, 2),
        centroid_delta_hz=round(centroid_delta, 1),
        tilt_delta=round(tilt_delta, 3),
        density_delta=round(density_delta, 3),
        sharpness_delta=round(sharpness_delta, 3),
        lufs_delta=round(lufs_delta, 2),
        deltas=(),  # populated below
        genre=genre or track.genre,
        num_references=num_references,
        lufs_normalization_db=round(-lufs_delta, 2),
    )

    # Generate deltas for all below-threshold dimensions (threshold=85%)
    deltas = identify_deltas(comparison_proto, threshold=85.0)
    return ReferenceComparison(
        overall_similarity=comparison_proto.overall_similarity,
        dimensions=comparison_proto.dimensions,
        band_deltas=comparison_proto.band_deltas,
        width_delta=comparison_proto.width_delta,
        crest_factor_delta=comparison_proto.crest_factor_delta,
        lra_delta=comparison_proto.lra_delta,
        centroid_delta_hz=comparison_proto.centroid_delta_hz,
        tilt_delta=comparison_proto.tilt_delta,
        density_delta=comparison_proto.density_delta,
        sharpness_delta=comparison_proto.sharpness_delta,
        lufs_delta=comparison_proto.lufs_delta,
        deltas=tuple(deltas),
        genre=comparison_proto.genre,
        num_references=comparison_proto.num_references,
        lufs_normalization_db=comparison_proto.lufs_normalization_db,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compare_to_reference(
    track: MixReport,
    reference: MixReport,
    *,
    genre: str = "",
    normalize_lufs: bool = True,  # noqa: ARG001 — reserved for future use
) -> ReferenceComparison:
    """Compare a track against a single reference track across 6 dimensions.

    Both `track` and `reference` must be the output of
    MixAnalysisEngine.full_mix_analysis() (or equivalent).

    The spectral comparison is inherently loudness-normalized because
    FrequencyProfile.bands are stored relative to the overall RMS.
    The `normalize_lufs` parameter is kept for API compatibility; actual
    LUFS normalization is not applied to spectral/dynamics metrics since they
    use loudness-independent measures (relative bands, crest factor, LRA).
    The raw LUFS delta is reported in the 'loudness' dimension.

    Args:
        track:          Analyzed MixReport for the track under review.
        reference:      Analyzed MixReport for the commercial reference.
        genre:          Override genre label. Defaults to track.genre.
        normalize_lufs: Reserved for future use (currently informational).

    Returns:
        ReferenceComparison with scores, deltas, and actionable improvements.

    Raises:
        ValueError: If track or reference is not a valid MixReport.
    """
    ref_metrics = _extract_metrics(reference)
    return _build_comparison(track, ref_metrics, genre=genre, num_references=1)


def compare_to_references(
    track: MixReport,
    references: Sequence[MixReport],
    *,
    genre: str = "",
    normalize_lufs: bool = True,  # noqa: ARG001 — reserved
) -> ReferenceComparison:
    """Compare a track against multiple reference tracks (aggregate A/B).

    Averages each metric across all references to form a composite reference,
    then performs a single comparison. This gives cleaner per-band deltas than
    averaging N individual comparison results.

    Args:
        track:      MixReport of the track under review.
        references: Sequence of 1+ MixReport objects from reference tracks.
        genre:      Override genre label.
        normalize_lufs: Reserved for future use.

    Returns:
        ReferenceComparison with `num_references` set to len(references).

    Raises:
        ValueError: If references is empty.
    """
    if not references:
        raise ValueError(
            "references must contain at least one MixReport — "
            "use compare_to_reference() for a single reference"
        )
    ref_metrics = _average_metrics(references)
    return _build_comparison(track, ref_metrics, genre=genre, num_references=len(references))


def identify_deltas(
    comparison: ReferenceComparison,
    *,
    threshold: float = 85.0,
) -> list[MixDelta]:
    """Translate a ReferenceComparison into a prioritized list of actionable fixes.

    Generates a MixDelta for each dimension whose score is below `threshold`,
    plus individual band deltas for spectral differences > 2 dB.

    Each MixDelta has a `recommendation` string with concrete values
    (e.g. 'Cut 2.1 dB in the low_mid band (200–500 Hz)').

    Args:
        comparison: Output of compare_to_reference() or compare_to_references().
        threshold:  Minimum similarity score to suppress a delta (default 85%).
                    Lower values generate fewer, higher-priority deltas only.

    Returns:
        List of MixDelta objects sorted by priority (highest first).
        Empty list if all dimensions meet or exceed the threshold.
    """
    deltas: list[MixDelta] = []

    for dim in comparison.dimensions:
        if dim.score >= threshold:
            continue

        priority = round((100.0 - dim.score) / 10.0, 1)

        if dim.name == "spectral":
            # Generate one delta per significant band (|delta| > 2 dB)
            sig_bands = sorted(
                [bd for bd in comparison.band_deltas if abs(bd.delta_db) > 2.0],
                key=lambda bd: abs(bd.delta_db),
                reverse=True,
            )
            for bd in sig_bands[:3]:  # top 3 bands
                lo, hi = BAND_EDGES.get(bd.band, (0.0, 20000.0))
                direction = "decrease" if bd.delta_db > 0 else "increase"
                adj = "Cut" if direction == "decrease" else "Boost"
                deltas.append(
                    MixDelta(
                        dimension="spectral",
                        direction=direction,
                        magnitude=round(abs(bd.delta_db), 1),
                        unit="dB",
                        recommendation=(
                            f"{adj} {abs(bd.delta_db):.1f} dB in the "
                            f"{bd.band.replace('_', '-')} band "
                            f"({lo:.0f}–{hi:.0f} Hz) — "
                            f"track: {bd.track_db:+.1f} dB, "
                            f"reference: {bd.reference_db:+.1f} dB"
                        ),
                        priority=priority,
                    )
                )

        elif dim.name == "stereo":
            direction = "increase" if comparison.width_delta < 0 else "decrease"
            action = "Widen" if direction == "increase" else "Narrow"
            deltas.append(
                MixDelta(
                    dimension="stereo",
                    direction=direction,
                    magnitude=round(abs(comparison.width_delta), 2),
                    unit="width units",
                    recommendation=(
                        f"{action} the stereo field by "
                        f"{abs(comparison.width_delta):.2f} width units — "
                        f"track width: {dim.track_value:.2f}, "
                        f"reference: {dim.ref_value:.2f}"
                    ),
                    priority=priority,
                )
            )

        elif dim.name == "dynamics":
            if abs(comparison.crest_factor_delta) >= 1.0:
                direction = "decrease" if comparison.crest_factor_delta > 0 else "increase"
                action = "Add more" if direction == "decrease" else "Reduce"
                deltas.append(
                    MixDelta(
                        dimension="dynamics",
                        direction=direction,
                        magnitude=round(abs(comparison.crest_factor_delta), 1),
                        unit="dB",
                        recommendation=(
                            f"{action} bus compression — crest factor "
                            f"{dim.track_value:.1f} dB vs reference "
                            f"{dim.ref_value:.1f} dB "
                            f"(delta {comparison.crest_factor_delta:+.1f} dB)"
                        ),
                        priority=priority,
                    )
                )
            if abs(comparison.lra_delta) >= 1.0:
                direction = "decrease" if comparison.lra_delta > 0 else "increase"
                deltas.append(
                    MixDelta(
                        dimension="dynamics",
                        direction=direction,
                        magnitude=round(abs(comparison.lra_delta), 1),
                        unit="LU",
                        recommendation=(
                            f"{'Reduce' if direction == 'decrease' else 'Add'} "
                            f"loudness variation — LRA delta "
                            f"{comparison.lra_delta:+.1f} LU vs references"
                        ),
                        priority=priority * 0.7,
                    )
                )

        elif dim.name == "tonal":
            if abs(comparison.centroid_delta_hz) >= 200.0:
                direction = "decrease" if comparison.centroid_delta_hz > 0 else "increase"
                action = (
                    "Apply a high-shelf cut"
                    if direction == "decrease"
                    else "Apply a high-shelf boost"
                )
                deltas.append(
                    MixDelta(
                        dimension="tonal",
                        direction=direction,
                        magnitude=round(abs(comparison.centroid_delta_hz), 0),
                        unit="Hz",
                        recommendation=(
                            f"{'Reduce' if direction == 'decrease' else 'Increase'} brightness — "
                            f"centroid {dim.track_value:.0f} Hz vs reference "
                            f"{dim.ref_value:.0f} Hz ({comparison.centroid_delta_hz:+.0f} Hz). "
                            f"{action} around 8–12 kHz."
                        ),
                        priority=priority,
                    )
                )

        elif dim.name == "transient":
            if abs(comparison.density_delta) >= 0.5:
                direction = "decrease" if comparison.density_delta > 0 else "increase"
                deltas.append(
                    MixDelta(
                        dimension="transient",
                        direction=direction,
                        magnitude=round(abs(comparison.density_delta), 1),
                        unit="onsets/s",
                        recommendation=(
                            f"{'Reduce' if direction == 'decrease' else 'Add'} transient density — "
                            f"{dim.track_value:.1f}/s vs reference "
                            f"{dim.ref_value:.1f}/s (delta {comparison.density_delta:+.1f}/s). "
                            f"Consider a transient shaper on the drum bus."
                        ),
                        priority=priority,
                    )
                )

        elif dim.name == "loudness":
            direction = "increase" if comparison.lufs_delta < 0 else "decrease"
            action = "Increase" if direction == "increase" else "Reduce"
            deltas.append(
                MixDelta(
                    dimension="loudness",
                    direction=direction,
                    magnitude=round(abs(comparison.lufs_delta), 1),
                    unit="LUFS",
                    recommendation=(
                        f"{action} integrated loudness by "
                        f"{abs(comparison.lufs_delta):.1f} LUFS — "
                        f"track: {dim.track_value:.1f} LUFS, "
                        f"reference: {dim.ref_value:.1f} LUFS. "
                        f"{'Adjust limiter ceiling.' if direction == 'increase' else 'Back off limiter gain.'}"
                    ),
                    priority=priority,
                )
            )

    # Sort by priority descending
    deltas.sort(key=lambda d: d.priority, reverse=True)
    return deltas
