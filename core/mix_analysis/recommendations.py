"""
core/mix_analysis/recommendations.py — Data-driven mix problem prescriptions.

Maps each detected MixProblem to a concrete Recommendation with specific
DSP parameter values computed from the actual analysis measurements.

Key design principle: recommendations are NOT generic.
    - "Muddy mix" → "Cut 3.1 dB at 280 Hz Q=2.0 on pad bus"
      (the 3.1 dB is computed from the excess above genre target,
       the 280 Hz is derived from the sub/low band balance)

Design:
    - Pure: analysis objects + genre string → Recommendation.
    - No I/O, no RAG calls. The `rag_query` field is a prepared query string;
      actual RAG enhancement happens in ingestion/mix_engine.py.
    - All fix generators use a conservative 65-75% of excess for cuts
      (avoid over-processing — leave some for the producer's taste).
"""

from __future__ import annotations

from core.mix_analysis._genre_loader import load_genre_target
from core.mix_analysis.types import (
    DynamicProfile,
    FixStep,
    FrequencyProfile,
    MixProblem,
    ProcessorParam,
    Recommendation,
    StereoImage,
)

_EPS = 1e-10

# How much of the detected excess to cut (conservative — leaves room for taste)
_CUT_FRACTION = 0.70


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _params(*pairs: tuple[str, str]) -> tuple[ProcessorParam, ...]:
    """Convenience: build a tuple of ProcessorParam from (name, value) pairs."""
    return tuple(ProcessorParam(name=n, value=v) for n, v in pairs)


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


# ---------------------------------------------------------------------------
# Per-problem fix generators
# ---------------------------------------------------------------------------


def _fix_muddiness(problem: MixProblem, freq: FrequencyProfile, genre: str) -> Recommendation:
    """Generate EQ cut prescription for low-mid muddiness.

    The cut frequency is derived from the sub/low band balance:
    - High sub energy → mud sits lower (~250 Hz, bass fundamental clash)
    - Normal sub → mud sits higher (~300–320 Hz, pad/chord buildup)
    """
    target = load_genre_target(genre)
    excess = freq.bands.low_mid - float(target["bands"]["low_mid"])
    cut_db = round(_clamp(excess * _CUT_FRACTION, 1.0, 6.0), 1)

    # Derive center frequency from spectral context
    sub_target = float(target["bands"]["sub"])
    sub_excess = freq.bands.sub - sub_target
    center_hz = 250.0 if sub_excess > 2.0 else (300.0 if sub_excess > 0 else 320.0)

    # Q: wider for severe cases (broad mud), narrower for mild (resonance)
    q = round(_clamp(2.5 - excess * 0.12, 1.0, 3.5), 1)

    step1 = FixStep(
        action=(
            f"Cut {cut_db} dB at {center_hz:.0f} Hz (Q={q}) on the muddiest element "
            "(typically pads, chords, or a synth bass)"
        ),
        bus="pad bus / chord bus",
        plugin_primary="FabFilter Pro-Q 3",
        plugin_fallback="Ableton EQ Eight",
        params=_params(
            ("frequency", f"{center_hz:.0f} Hz"),
            ("gain", f"-{cut_db} dB"),
            ("q", str(q)),
            ("filter_type", "bell"),
        ),
    )
    step2 = FixStep(
        action="High-pass filter at 80–100 Hz on all non-bass elements",
        bus="pad bus / synth bus",
        plugin_primary="FabFilter Pro-Q 3",
        plugin_fallback="Ableton EQ Eight",
        params=_params(
            ("frequency", "90 Hz"),
            ("type", "high_pass"),
            ("slope", "24 dB/oct"),
        ),
    )

    return Recommendation(
        problem_category="muddiness",
        genre=genre,
        severity=problem.severity,
        summary=f"Cut {cut_db} dB at {center_hz:.0f} Hz Q={q} on pad/chord bus",
        steps=(step1, step2),
        rag_query=f"{genre} low-mid mud {center_hz:.0f}Hz EQ technique bus processing",
        rag_citations=(),
    )


def _fix_harshness(problem: MixProblem, freq: FrequencyProfile, genre: str) -> Recommendation:
    """Generate de-harshening prescription for high-mid excess.

    Distinguishes two common sources:
    - 2–3 kHz buildup: synthesizer formants, aggressive transients
    - 3–5 kHz buildup: overdriven leads, distorted percussion
    """
    target = load_genre_target(genre)
    excess = freq.bands.high_mid - float(target["bands"]["high_mid"])
    cut_db = round(_clamp(excess * _CUT_FRACTION, 1.0, 5.0), 1)

    # Center depends on spectral centroid
    centroid = freq.spectral_centroid
    center_hz = 3000.0 if centroid > 2500 else 2500.0
    q = round(_clamp(2.0 - excess * 0.1, 1.2, 3.0), 1)

    step1 = FixStep(
        action=(
            f"Bell cut {cut_db} dB at {center_hz:.0f} Hz (Q={q}) on leads and synths. "
            "Solo each element to identify the harshest source first."
        ),
        bus="lead bus / synth bus",
        plugin_primary="FabFilter Pro-Q 3",
        plugin_fallback="Ableton EQ Eight",
        params=_params(
            ("frequency", f"{center_hz:.0f} Hz"),
            ("gain", f"-{cut_db} dB"),
            ("q", str(q)),
            ("filter_type", "bell"),
        ),
    )
    step2 = FixStep(
        action="Optional: Dynamic EQ triggered by high-mid transients (ratio 3:1, fast attack)",
        bus="lead bus",
        plugin_primary="FabFilter Pro-MB",
        plugin_fallback="Ableton Multiband Dynamics",
        params=_params(
            ("frequency", f"{center_hz:.0f} Hz"),
            ("ratio", "3:1"),
            ("attack", "5 ms"),
            ("release", "80 ms"),
            ("threshold", f"{float(target['bands']['high_mid']) + 2:.0f} dBr"),
        ),
    )

    return Recommendation(
        problem_category="harshness",
        genre=genre,
        severity=problem.severity,
        summary=f"Cut {cut_db} dB at {center_hz:.0f} Hz Q={q} on lead/synth bus",
        steps=(step1, step2),
        rag_query=f"{genre} harshness {center_hz:.0f}Hz high-mid cut technique",
        rag_citations=(),
    )


def _fix_boominess(
    problem: MixProblem, freq: FrequencyProfile, dyn: DynamicProfile, genre: str
) -> Recommendation:
    """Generate low-end tightening prescription for boominess.

    Combines EQ notch at resonant frequency with sidechain compression tip.
    """
    target = load_genre_target(genre)
    sub_excess = freq.bands.sub - float(target["bands"]["sub"])
    low_excess = freq.bands.low - float(target["bands"]["low"])
    avg_excess = (sub_excess + low_excess) / 2.0
    cut_db = round(_clamp(avg_excess * _CUT_FRACTION, 1.0, 6.0), 1)

    # Resonant frequency usually around 60–80 Hz for kick/bass clash
    notch_hz = 70.0

    step1 = FixStep(
        action="Apply high-pass filter at 30–35 Hz on all non-bass elements (remove sub rumble)",
        bus="pad bus / synth bus / drum bus (no kick)",
        plugin_primary="FabFilter Pro-Q 3",
        plugin_fallback="Ableton EQ Eight",
        params=_params(("frequency", "32 Hz"), ("type", "high_pass"), ("slope", "24 dB/oct")),
    )
    step2 = FixStep(
        action=(
            f"Narrow notch cut {cut_db} dB at {notch_hz:.0f} Hz (Q=3.0) on bass bus "
            "to reduce resonant buildup"
        ),
        bus="bass bus",
        plugin_primary="FabFilter Pro-Q 3",
        plugin_fallback="Ableton EQ Eight",
        params=_params(
            ("frequency", f"{notch_hz:.0f} Hz"),
            ("gain", f"-{cut_db} dB"),
            ("q", "3.0"),
            ("filter_type", "bell"),
        ),
    )
    step3 = FixStep(
        action=(
            "Sidechain compress bass from kick: ratio 4:1, attack 5 ms, release 120 ms. "
            "This creates breathing space between kick and bass."
        ),
        bus="bass bus (sidechain from kick)",
        plugin_primary="FabFilter Pro-C 2",
        plugin_fallback="Ableton Compressor (sidechain mode)",
        params=_params(
            ("ratio", "4:1"),
            ("attack", "5 ms"),
            ("release", "120 ms"),
            ("threshold", "-18 dBFS"),
            ("sidechain_source", "kick"),
        ),
    )

    return Recommendation(
        problem_category="boominess",
        genre=genre,
        severity=problem.severity,
        summary=f"HP filter non-bass at 32 Hz + notch {cut_db} dB at {notch_hz:.0f} Hz + sidechain bass",
        steps=(step1, step2, step3),
        rag_query=f"{genre} bass sidechain kick boomy low-end tight sub management",
        rag_citations=(),
    )


def _fix_thinness(problem: MixProblem, freq: FrequencyProfile, genre: str) -> Recommendation:
    """Generate low-body enhancement prescription for thin mixes.

    Adds warmth by boosting 150–200 Hz on pads and checking HP filter positions.
    """
    target = load_genre_target(genre)
    deficit = float(target["bands"]["low_mid"]) - freq.bands.low_mid
    boost_db = round(_clamp(deficit * 0.5, 1.0, 4.0), 1)  # conservative boost

    boost_hz = 180.0  # warmth region

    step1 = FixStep(
        action=(
            f"Gentle low-shelf boost {boost_db} dB at {boost_hz:.0f} Hz on pads/chords "
            "(add body and warmth)"
        ),
        bus="pad bus / chord bus",
        plugin_primary="FabFilter Pro-Q 3",
        plugin_fallback="Ableton EQ Eight",
        params=_params(
            ("frequency", f"{boost_hz:.0f} Hz"),
            ("gain", f"+{boost_db} dB"),
            ("type", "low_shelf"),
        ),
    )
    step2 = FixStep(
        action=(
            "Check high-pass filter positions: raise cutoff of any HP above 150 Hz "
            "down to 80–100 Hz on pads to restore body"
        ),
        bus="pad bus / chord bus",
        plugin_primary="FabFilter Pro-Q 3",
        plugin_fallback="Ableton EQ Eight",
        params=_params(
            ("frequency", "90 Hz"),
            ("type", "high_pass"),
            ("slope", "12 dB/oct"),
            ("note", "move cutoff DOWN to restore low-mid body"),
        ),
    )

    return Recommendation(
        problem_category="thinness",
        genre=genre,
        severity=problem.severity,
        summary=f"Low-shelf boost {boost_db} dB at {boost_hz:.0f} Hz on pads + check HP positions",
        steps=(step1, step2),
        rag_query=f"{genre} thin mix add warmth body low-mid 200Hz restoration",
        rag_citations=(),
    )


def _fix_narrow_stereo(problem: MixProblem, stereo: StereoImage, genre: str) -> Recommendation:
    """Generate stereo widening prescription using mid-side techniques."""
    target = load_genre_target(genre)
    target_width = float(target["stereo"]["overall_width_min"])
    current_width = stereo.width
    width_deficit = target_width - current_width

    # Haas delay: 15–35 ms for width without obvious echo
    haas_ms = round(_clamp(15.0 + width_deficit * 50.0, 15.0, 35.0), 0)
    # Stereo utility width: percentage (100% = mono, 200% = very wide)
    utility_pct = round(_clamp(110.0 + width_deficit * 200.0, 110.0, 160.0), 0)

    step1 = FixStep(
        action=(
            f"Apply Haas effect on pads: delay right channel by {haas_ms:.0f} ms "
            "(keeps bass centered, widens mid-high content)"
        ),
        bus="pad bus",
        plugin_primary="Soundtoys MicroShift",
        plugin_fallback="Ableton Utility + Delay (manual Haas setup)",
        params=_params(
            ("delay_r", f"{haas_ms:.0f} ms"),
            ("delay_l", "0 ms"),
        ),
    )
    step2 = FixStep(
        action=(
            f"Ableton Utility: set Width to {utility_pct:.0f}% on pad/lead buses. "
            "Keep bass bus Width at 0% (mono-compatible)"
        ),
        bus="pad bus / lead bus",
        plugin_primary="Ableton Utility",
        plugin_fallback="iZotope Imager",
        params=_params(
            ("width", f"{utility_pct:.0f}%"),
            ("note", "apply ONLY to mid-high frequency content, not bass"),
        ),
    )
    step3 = FixStep(
        action="Mid-side EQ: boost Side channel +2 dB above 8 kHz to add air and width",
        bus="master bus",
        plugin_primary="FabFilter Pro-Q 3 (M/S mode)",
        plugin_fallback="Ableton EQ Eight (L/R mode, approximate)",
        params=_params(
            ("mode", "mid_side"),
            ("channel", "side"),
            ("frequency", "8000 Hz"),
            ("gain", "+2 dB"),
            ("type", "high_shelf"),
        ),
    )

    return Recommendation(
        problem_category="narrow_stereo",
        genre=genre,
        severity=problem.severity,
        summary=(
            f"Haas {haas_ms:.0f} ms on pads + Utility {utility_pct:.0f}% width + M/S air boost"
        ),
        steps=(step1, step2, step3),
        rag_query=f"{genre} stereo widening technique Haas mid-side pad width",
        rag_citations=(),
    )


def _fix_phase_issues(problem: MixProblem, stereo: StereoImage, genre: str) -> Recommendation:
    """Generate phase correction prescription."""
    step1 = FixStep(
        action=(
            "Check mono compatibility: sum to mono and listen. "
            f"L-R correlation is {stereo.lr_correlation:.2f} "
            "(target: > 0). Identify which element disappears in mono."
        ),
        bus="master bus",
        plugin_primary="iZotope Insight 2 (phase correlation meter)",
        plugin_fallback="Ableton Utility (set Width to 0 to audition mono)",
        params=_params(
            ("lr_correlation", f"{stereo.lr_correlation:.2f}"),
            ("action", "listen in mono, identify cancelling element"),
        ),
    )
    step2 = FixStep(
        action=(
            "Flip phase on the problematic element (usually a doubled part or "
            "a stereo reverb return with a delayed L or R channel)"
        ),
        bus="identified element",
        plugin_primary="FabFilter Pro-Q 3 (phase section)",
        plugin_fallback="Ableton Utility (Phase Invert button)",
        params=_params(
            ("phase_invert", "try both — keep the version with higher mono correlation"),
        ),
    )
    step3 = FixStep(
        action=(
            "If phase flip doesn't help: use Mid-Side processing to reduce "
            "extreme side content below 200 Hz (lows should be mono-compatible)"
        ),
        bus="master bus / problematic bus",
        plugin_primary="FabFilter Pro-Q 3 (M/S, Side channel high-pass)",
        plugin_fallback="Ableton EQ Eight (approximate in L/R mode)",
        params=_params(
            ("mode", "mid_side"),
            ("channel", "side"),
            ("frequency", "200 Hz"),
            ("type", "high_pass"),
            ("slope", "24 dB/oct"),
        ),
    )

    return Recommendation(
        problem_category="phase_issues",
        genre=genre,
        severity=problem.severity,
        summary="Check mono compatibility, flip phase on cancelling element, HP side below 200 Hz",
        steps=(step1, step2, step3),
        rag_query=f"{genre} phase cancellation mono compatibility fix stereo correlation",
        rag_citations=(),
    )


def _fix_over_compression(problem: MixProblem, dyn: DynamicProfile, genre: str) -> Recommendation:
    """Generate decompression prescription: restore transient punch."""
    target = load_genre_target(genre)
    crest_target = float(target["dynamics"]["crest_min"])
    crest_deficit = crest_target - dyn.crest_factor  # how many dB of punch to restore

    step1 = FixStep(
        action=(
            f"Reduce master bus compressor ratio from current to 2:1. "
            f"Current crest factor {dyn.crest_factor:.1f} dB, target ≥ {crest_target} dB."
        ),
        bus="master bus",
        plugin_primary="SSL G-Bus Compressor",
        plugin_fallback="Ableton Glue Compressor",
        params=_params(
            ("ratio", "2:1"),
            ("attack", "30 ms"),
            ("release", "auto"),
            ("note", "increase attack to preserve transient punch"),
        ),
    )
    step2 = FixStep(
        action=(
            f"Increase attack time by {crest_deficit * 10:.0f}–{crest_deficit * 20:.0f} ms "
            "to let transients pass uncompressed"
        ),
        bus="master bus",
        plugin_primary="SSL G-Bus Compressor",
        plugin_fallback="Ableton Glue Compressor",
        params=_params(
            ("attack", f"{crest_deficit * 15:.0f} ms"),
            ("release", "auto"),
        ),
    )
    step3 = FixStep(
        action=(
            "Try parallel compression: blend dry (0% make-up) and compressed (100%) "
            "at 30/70 mix. Preserves transients while adding glue."
        ),
        bus="master bus",
        plugin_primary="FabFilter Pro-C 2",
        plugin_fallback="Ableton Compressor (dry/wet knob)",
        params=_params(
            ("ratio", "4:1"),
            ("attack", "10 ms"),
            ("release", "auto"),
            ("mix", "30%"),
            ("technique", "parallel compression"),
        ),
    )

    return Recommendation(
        problem_category="over_compression",
        genre=genre,
        severity=problem.severity,
        summary=f"Reduce ratio to 2:1, increase attack {crest_deficit * 15:.0f} ms, try parallel compression",
        steps=(step1, step2, step3),
        rag_query=f"{genre} over-compression transient punch crest factor bus compressor attack",
        rag_citations=(),
    )


def _fix_under_compression(problem: MixProblem, dyn: DynamicProfile, genre: str) -> Recommendation:
    """Generate glue compression prescription for under-compressed mixes."""
    target = load_genre_target(genre)
    crest_max = float(target["dynamics"]["crest_max"])
    excess_crest = dyn.crest_factor - crest_max

    step1 = FixStep(
        action=(
            f"Add gentle bus compressor: ratio 2:1, slow attack (30 ms), auto release. "
            f"Crest factor {dyn.crest_factor:.1f} dB → target {crest_max:.0f} dB."
        ),
        bus="master bus",
        plugin_primary="SSL G-Bus Compressor",
        plugin_fallback="Ableton Glue Compressor",
        params=_params(
            ("ratio", "2:1"),
            ("attack", "30 ms"),
            ("release", "auto"),
            ("threshold", "-6 dBFS"),
            ("makeup", f"+{min(excess_crest * 0.5, 3.0):.1f} dB"),
        ),
    )
    step2 = FixStep(
        action="Apply gentle saturation for harmonic glue (+2 dB drive, 20% mix)",
        bus="master bus",
        plugin_primary="Soundtoys Decapitator",
        plugin_fallback="Ableton Saturator",
        params=_params(
            ("style", "warm tube"),
            ("drive", "2 dB"),
            ("mix", "20%"),
        ),
    )

    return Recommendation(
        problem_category="under_compression",
        genre=genre,
        severity=problem.severity,
        summary="Add 2:1 glue compressor at -6 dBFS + gentle saturation",
        steps=(step1, step2),
        rag_query=f"{genre} glue compression bus cohesion dynamic range reduction",
        rag_citations=(),
    )


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_FIXERS = {
    "muddiness": _fix_muddiness,
    "harshness": _fix_harshness,
    "boominess": _fix_boominess,
    "thinness": _fix_thinness,
    "narrow_stereo": _fix_narrow_stereo,
    "phase_issues": _fix_phase_issues,
    "over_compression": _fix_over_compression,
    "under_compression": _fix_under_compression,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def recommend_fix(
    problem: MixProblem,
    freq: FrequencyProfile,
    stereo: StereoImage | None,
    dynamics: DynamicProfile,
    genre: str,
) -> Recommendation:
    """Generate a data-driven prescription for a single detected mix problem.

    Parameter values in the returned Recommendation are computed from the
    actual measured analysis values — not generic suggestions.

    Args:
        problem:  The MixProblem to fix (from problems.detect_mix_problems).
        freq:     FrequencyProfile with measured band levels.
        stereo:   StereoImage (None for mono input).
        dynamics: DynamicProfile with measured crest factor and LUFS.
        genre:    Genre name (must be a known genre, case-insensitive).

    Returns:
        Recommendation with ordered fix steps and a prepared RAG query.

    Raises:
        ValueError: If problem.category is not a known problem type.
        ValueError: If genre is not in the known genre list.
    """
    fixer = _FIXERS.get(problem.category)
    if fixer is None:
        raise ValueError(
            f"Unknown problem category: {problem.category!r}. " f"Known: {sorted(_FIXERS.keys())}"
        )

    # Dispatch to specific fixer; pass stereo for stereo-aware fixers
    if problem.category in ("narrow_stereo", "phase_issues"):
        if stereo is None or stereo.is_mono:
            # Can't generate stereo fix for mono input — return empty recommendation
            return Recommendation(
                problem_category=problem.category,
                genre=genre,
                severity=problem.severity,
                summary="Mono input — stereo fix not applicable",
                steps=(),
                rag_query="",
                rag_citations=(),
            )
        return fixer(problem, stereo, genre)  # type: ignore[operator]

    if problem.category == "boominess":
        return _fix_boominess(problem, freq, dynamics, genre)

    if problem.category in ("over_compression", "under_compression"):
        return fixer(problem, dynamics, genre)  # type: ignore[operator]

    return fixer(problem, freq, genre)  # type: ignore[operator]


def recommend_all(
    problems: list[MixProblem],
    freq: FrequencyProfile,
    stereo: StereoImage | None,
    dynamics: DynamicProfile,
    genre: str,
    max_recommendations: int = 5,
) -> list[Recommendation]:
    """Generate recommendations for all detected problems, prioritised by severity.

    Limits output to `max_recommendations` to avoid overwhelming the producer.
    Only problems with severity > 0 receive a recommendation.

    Args:
        problems:            Problems from detect_mix_problems (sorted by severity).
        freq, stereo, dynamics: Analysis objects for parameter computation.
        genre:               Genre name.
        max_recommendations: Maximum recommendations to generate (default 5).

    Returns:
        List of Recommendations ordered by problem severity (highest first).
    """
    recs: list[Recommendation] = []
    for problem in problems[:max_recommendations]:
        if problem.severity <= 0.0:
            continue
        try:
            rec = recommend_fix(problem, freq, stereo, dynamics, genre)
            recs.append(rec)
        except ValueError:
            continue  # skip unknown problem types gracefully
    return recs
