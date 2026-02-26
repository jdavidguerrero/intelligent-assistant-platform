"""
core/mix_analysis/problems.py — Mix problem detection with genre-aware targets.

Implements 8 detectors, each comparing measured analysis values against the
genre target profile and emitting a MixProblem when a threshold is exceeded.

Detectors:
    1. muddiness      — low_mid band excess (200–500 Hz)
    2. harshness      — high_mid band excess (2 k–6 kHz)
    3. boominess      — sub+low excess with low crest (compressed lows)
    4. thinness       — low_mid deficit
    5. narrow_stereo  — overall or high-band width too narrow
    6. phase_issues   — L-R correlation negative or low-band cancellation
    7. over_compression — crest factor below genre minimum
    8. under_compression — crest factor far above genre maximum (optional)

Design:
    - Pure: structured analysis objects + genre string → list[MixProblem].
    - Each detector returns Optional[MixProblem]; None means no problem.
    - Problems are sorted by severity descending before returning.
"""

from __future__ import annotations

from typing import Any

from core.mix_analysis._genre_loader import load_genre_target
from core.mix_analysis.types import (
    DynamicProfile,
    FrequencyProfile,
    MixProblem,
    StereoImage,
)

_EPS = 1e-10


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _severity_from_excess(excess_db: float, threshold_db: float, max_db: float = 8.0) -> float:
    """Map how far above a threshold we are to a 0–10 severity score.

    Args:
        excess_db:   How many dB above (or below) the target the value is.
        threshold_db: The dB excess that triggers the problem.
        max_db:       The excess (beyond threshold) that maps to severity 10.

    Returns:
        Severity 0–10.
    """
    above = excess_db - threshold_db
    if above <= 0.0:
        return 0.0
    return float(min(10.0, (above / max_db) * 10.0))


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------


def _detect_muddiness(freq: FrequencyProfile, targets: dict[str, Any]) -> MixProblem | None:
    """Detect muddiness: low_mid band above genre target by > threshold."""
    target_db = float(targets["bands"]["low_mid"])
    threshold = float(targets["thresholds"]["muddiness_db"])
    actual_db = freq.bands.low_mid
    excess = actual_db - target_db  # positive = louder than target

    severity = _severity_from_excess(excess, threshold)
    if severity <= 0.0:
        return None

    return MixProblem(
        category="muddiness",
        frequency_range=(200.0, 500.0),
        severity=round(severity, 1),
        description=(
            f"low_mid band is {excess:+.1f} dB relative to {targets['genre']} target "
            f"({target_db:.1f} dB). Measured: {actual_db:.1f} dB."
        ),
        recommendation=(
            f"Try a {min(excess, 6.0):.0f} dB cut at 250–350 Hz on the muddiest element "
            f"(often pads or bass) with Q=1.5–2.5."
        ),
    )


def _detect_harshness(freq: FrequencyProfile, targets: dict[str, Any]) -> MixProblem | None:
    """Detect harshness: high_mid band above genre target."""
    target_db = float(targets["bands"]["high_mid"])
    threshold = float(targets["thresholds"]["harshness_db"])
    actual_db = freq.bands.high_mid
    excess = actual_db - target_db

    severity = _severity_from_excess(excess, threshold)
    if severity <= 0.0:
        return None

    return MixProblem(
        category="harshness",
        frequency_range=(2000.0, 6000.0),
        severity=round(severity, 1),
        description=(
            f"high_mid band is {excess:+.1f} dB above {targets['genre']} target "
            f"({target_db:.1f} dB). This can cause ear fatigue on extended listening."
        ),
        recommendation=(
            f"Apply a {min(excess, 4.0):.0f} dB cut at 2–4 kHz with Q=2.0 on leads "
            f"or synths. Check for resonances in the 3–3.5 kHz range first."
        ),
    )


def _detect_boominess(
    freq: FrequencyProfile, dyn: DynamicProfile, targets: dict[str, Any]
) -> MixProblem | None:
    """Detect boominess: excess sub/low energy combined with low crest factor."""
    sub_excess = freq.bands.sub - float(targets["bands"]["sub"])
    low_excess = freq.bands.low - float(targets["bands"]["low"])
    avg_excess = (sub_excess + low_excess) / 2.0
    threshold = float(targets["thresholds"]["boominess_db"])
    crest_min = float(targets["dynamics"]["crest_min"])

    # Boomy = excess lows AND compressed (low crest = sustained boom, not punchy)
    low_crest = dyn.crest_factor < crest_min
    combined_excess = avg_excess + (2.0 if low_crest else 0.0)
    severity = _severity_from_excess(combined_excess, threshold)
    if severity <= 0.0:
        return None

    crest_note = (
        f" Crest factor ({dyn.crest_factor:.1f} dB) below target minimum ({crest_min} dB)"
        " — lows are sustained rather than punchy."
        if low_crest
        else ""
    )

    return MixProblem(
        category="boominess",
        frequency_range=(20.0, 200.0),
        severity=round(severity, 1),
        description=(f"Sub/low bands are {avg_excess:+.1f} dB above target.{crest_note}"),
        recommendation=(
            "Use a high-pass filter at 30–40 Hz on non-bass elements. "
            "Apply sidechained compression on bass triggered by kick. "
            "Try a narrow notch at the resonant frequency (often 60–80 Hz)."
        ),
    )


def _detect_thinness(freq: FrequencyProfile, targets: dict[str, Any]) -> MixProblem | None:
    """Detect thinness: low_mid band significantly below genre target."""
    target_db = float(targets["bands"]["low_mid"])
    threshold = float(targets["thresholds"]["thinness_db"])
    actual_db = freq.bands.low_mid
    deficit = target_db - actual_db  # positive = thinner than target

    severity = _severity_from_excess(deficit, threshold)
    if severity <= 0.0:
        return None

    return MixProblem(
        category="thinness",
        frequency_range=(100.0, 500.0),
        severity=round(severity, 1),
        description=(
            f"low_mid band is {deficit:.1f} dB below {targets['genre']} target. "
            f"The mix lacks body and warmth (measured: {actual_db:.1f} dB)."
        ),
        recommendation=(
            "Add a gentle shelf or bell boost at 150–300 Hz on pads or bass. "
            "Check that high-pass filters on instruments are not cutting too high."
        ),
    )


def _detect_narrow_stereo(stereo: StereoImage | None, targets: dict[str, Any]) -> MixProblem | None:
    """Detect narrow stereo: overall width or high-band width below genre minimum."""
    if stereo is None or stereo.is_mono:
        # Mono files are not "problems" — just a different format
        return None

    stereo_cfg = targets.get("stereo", {})
    width_min = float(stereo_cfg.get("overall_width_min", 0.3))
    high_min = float(stereo_cfg.get("high_width_min", 0.35))

    # Choose the larger violation
    width_deficit = width_min - stereo.width
    high_deficit = high_min - stereo.band_widths.high

    max_deficit = max(width_deficit, high_deficit)
    if max_deficit <= 0.0:
        return None

    severity = float(min(10.0, (max_deficit / 0.5) * 10.0))

    if width_deficit >= high_deficit:
        detail = (
            f"Overall stereo width {stereo.width:.2f} is below the "
            f"{targets['genre']} minimum ({width_min})."
        )
        fix = (
            "Try stereo widening on pads and leads using Haas effect (L/R delay) "
            "or mid-side processing. Ensure lows remain centered."
        )
    else:
        detail = (
            f"High-band stereo width {stereo.band_widths.high:.2f} is below "
            f"{targets['genre']} minimum ({high_min})."
        )
        fix = (
            "Widen high frequencies using M/S EQ: boost Side in the 8–15 kHz range. "
            "Or use stereo chorus on hi-hats and cymbals."
        )

    return MixProblem(
        category="narrow_stereo",
        frequency_range=(0.0, 20000.0),
        severity=round(severity, 1),
        description=detail,
        recommendation=fix,
    )


def _detect_phase_issues(
    stereo: StereoImage | None,
) -> MixProblem | None:
    """Detect phase cancellation: negative overall or low-band L-R correlation."""
    if stereo is None or stereo.is_mono:
        return None

    # Check per-band correlations (negative correlation = phase cancellation)
    band_correlations = {
        "sub": 1.0 - stereo.band_widths.sub * 2.0,  # approximate from width
        "low": 1.0 - stereo.band_widths.low * 2.0,
        "low_mid": 1.0 - stereo.band_widths.low_mid * 2.0,
    }
    # Also check overall correlation
    worst = stereo.lr_correlation
    worst_band = "overall"
    for band, corr in band_correlations.items():
        if corr < worst:
            worst = corr
            worst_band = band

    threshold = -0.2
    if worst >= threshold:
        return None

    severity = float(min(10.0, abs(worst - threshold) / 0.8 * 10.0))

    return MixProblem(
        category="phase_issues",
        frequency_range=(20.0, 500.0),
        severity=round(severity, 1),
        description=(
            f"Phase cancellation detected in {worst_band} band "
            f"(L-R correlation: {worst:.2f}). Mono compatibility is compromised."
        ),
        recommendation=(
            "Use a phase correlation meter and check mono compatibility. "
            "Flip phase on one microphone if recording. "
            "Use a multiband correlation tool to identify the problem frequency range."
        ),
    )


def _detect_over_compression(dyn: DynamicProfile, targets: dict[str, Any]) -> MixProblem | None:
    """Detect over-compression: crest factor below genre minimum."""
    crest_min = float(targets["dynamics"]["crest_min"])
    deficit = crest_min - dyn.crest_factor  # positive = worse than target

    if deficit <= 0.0:
        return None

    severity = _severity_from_excess(deficit, 0.0, max_db=6.0)

    return MixProblem(
        category="over_compression",
        frequency_range=(20.0, 20000.0),
        severity=round(severity, 1),
        description=(
            f"Crest factor {dyn.crest_factor:.1f} dB is below the "
            f"{targets['genre']} minimum ({crest_min} dB). "
            f"The mix sounds squashed and fatiguing."
        ),
        recommendation=(
            "Reduce makeup gain on the master bus compressor. "
            "Increase attack time to preserve transient punch. "
            f"Target crest factor: {crest_min}–{targets['dynamics']['crest_max']} dB."
        ),
    )


def _detect_under_compression(dyn: DynamicProfile, targets: dict[str, Any]) -> MixProblem | None:
    """Detect under-compression: crest factor far above genre maximum (optional check)."""
    crest_max = float(targets["dynamics"]["crest_max"])
    # Only flag if significantly above maximum (add 4 dB tolerance)
    excess = dyn.crest_factor - (crest_max + 4.0)
    if excess <= 0.0:
        return None

    severity = _severity_from_excess(excess, 0.0, max_db=8.0)

    return MixProblem(
        category="under_compression",
        frequency_range=(20.0, 20000.0),
        severity=round(severity, 1),
        description=(
            f"Crest factor {dyn.crest_factor:.1f} dB is very high for "
            f"{targets['genre']} (target max: {crest_max} dB). "
            "The mix may sound inconsistent in a live DJ context."
        ),
        recommendation=(
            "Add gentle master bus compression (2:1 ratio, slow attack, fast release). "
            "Or apply parallel compression to add glue without killing transients."
        ),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_mix_problems(
    freq: FrequencyProfile,
    stereo: StereoImage | None,
    dynamics: DynamicProfile,
    genre: str = "organic house",
) -> list[MixProblem]:
    """Run all mix problem detectors and return detected issues sorted by severity.

    Args:
        freq:     FrequencyProfile from spectral.analyze_frequency_balance().
        stereo:   StereoImage from stereo.analyze_stereo_image(), or None for mono.
        dynamics: DynamicProfile from dynamics.analyze_dynamics().
        genre:    Genre name for target comparison (default: 'organic house').

    Returns:
        List of MixProblem objects, sorted by severity descending (worst first).
        Empty list = no problems detected for this genre target.

    Raises:
        ValueError: If genre is not in the known genre list.
    """
    targets = load_genre_target(genre)

    candidates: list[MixProblem | None] = [
        _detect_muddiness(freq, targets),
        _detect_harshness(freq, targets),
        _detect_boominess(freq, dynamics, targets),
        _detect_thinness(freq, targets),
        _detect_narrow_stereo(stereo, targets),
        _detect_phase_issues(stereo),
        _detect_over_compression(dynamics, targets),
        _detect_under_compression(dynamics, targets),
    ]

    problems = [p for p in candidates if p is not None]
    problems.sort(key=lambda p: p.severity, reverse=True)
    return problems
