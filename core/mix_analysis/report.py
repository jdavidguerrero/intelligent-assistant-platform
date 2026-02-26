"""
core/mix_analysis/report.py — Unified mix + master diagnostic report generation.

Aggregates all Week 16–18 analysis modules into a single FullMixReport with
structured, human-readable sections ordered by severity.

Report structure
================
1. Executive Summary    — Health score, top priorities, one-line verdict.
2. Frequency Analysis   — 7-band breakdown, centroid, tilt.
3. Stereo Analysis      — Width, correlation, phase, mid-side balance.
4. Dynamics Analysis    — LUFS, crest factor, LRA, dynamic range.
5. Problems & Fixes     — All detected problems with DSP parameter fixes.
6. Reference Comparison — Per-dimension deltas vs commercial references (optional).
7. Signal Chain         — Genre-specific mix-bus chain recommendation.
8. Master Readiness     — Mastering analysis, true peak, issues (optional).

Severity labeling
=================
    'ok'       — No significant issues in this section.
    'warning'  — Minor issues; won't prevent release but worth addressing.
    'critical' — Significant problem; fix before mastering/release.

Confidence labeling
===================
    'high'   — Objective measurement, clear deviation from genre targets.
    'medium' — Measurement-based but interpretation depends on artistic intent.
    'low'    — Stylistic suggestion based on genre conventions.

Health score formula
====================
Without reference comparison:
    base = 100 − Σ(problem.severity × 2.0), clamped to [20, 100]

With reference comparison:
    score = 0.55 × base + 0.45 × reference.overall_similarity

Design
======
- Pure module: no I/O, no env vars, no timestamps.
- Chains loaded from chains.get_chain() — already cached at module level.
- All string formatting is deterministic (no f-string randomness).
"""

from __future__ import annotations

from core.mix_analysis.chains import get_chain
from core.mix_analysis.types import (
    FullMixReport,
    MasterReport,
    MixReport,
    ReferenceComparison,
    ReportSection,
)

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _severity_label(score: float) -> str:
    """Map a 0–100 score to a severity label."""
    if score >= 80.0:
        return "ok"
    if score >= 55.0:
        return "warning"
    return "critical"


def _problem_severity_label(max_severity: float) -> str:
    """Map a max problem severity (0–10) to a section severity label."""
    if max_severity < 3.0:
        return "ok"
    if max_severity < 6.5:
        return "warning"
    return "critical"


def _compute_health_score(
    mix: MixReport,
    reference: ReferenceComparison | None,
) -> float:
    """Compute an aggregate 0–100 mix health score.

    Without reference comparison: deducts points for each detected problem
    proportional to severity (2 pts × severity per problem, max 10 pts each).

    With reference comparison: blends the problem-based score (55%) with the
    reference similarity score (45%) to reward mixes that sound like the genre.
    """
    deductions = sum(min(10.0, p.severity * 2.0) for p in mix.problems)
    base = max(20.0, 100.0 - deductions)

    if reference is None:
        return round(base, 1)

    blended = 0.55 * base + 0.45 * reference.overall_similarity
    return round(max(0.0, min(100.0, blended)), 1)


def _top_priorities(
    mix: MixReport,
    reference: ReferenceComparison | None,
) -> tuple[str, ...]:
    """Collect the top 3–5 most impactful improvement actions."""
    priorities: list[tuple[float, str]] = []

    # From problem recommendations
    for rec in mix.recommendations[:5]:
        if rec.steps:
            priorities.append((rec.severity, rec.summary))

    # From reference deltas
    if reference is not None:
        for delta in reference.deltas[:3]:
            priorities.append((delta.priority, delta.recommendation[:120]))

    # Sort by priority/severity descending, deduplicate, take top 5
    priorities.sort(key=lambda x: x[0], reverse=True)
    seen: set[str] = set()
    result: list[str] = []
    for _, text in priorities:
        if text not in seen and len(result) < 5:
            seen.add(text)
            result.append(text)

    return tuple(result)


# ---------------------------------------------------------------------------
# Section generators
# ---------------------------------------------------------------------------


def _executive_summary(
    mix: MixReport,
    master: MasterReport | None,
    reference: ReferenceComparison | None,
    health_score: float,
) -> ReportSection:
    """Generate the executive summary section."""
    points: list[str] = [
        f"Overall health score: {health_score:.0f}/100",
        f"Genre: {mix.genre} | Duration: {mix.duration_sec:.0f}s | "
        f"Sample rate: {mix.sample_rate} Hz",
        f"Problems detected: {len(mix.problems)} | " f"Recommendations: {len(mix.recommendations)}",
    ]

    if reference is not None:
        points.append(
            f"Reference similarity: {reference.overall_similarity:.0f}% "
            f"(vs {reference.num_references} commercial reference"
            f"{'s' if reference.num_references != 1 else ''})"
        )

    if master is not None:
        points.append(
            f"Master readiness: {master.master.readiness_score:.0f}/100 — "
            f"LUFS {master.master.lufs_integrated:.1f} | "
            f"True peak {master.master.true_peak_db:.1f} dBTP"
        )

    if not mix.problems:
        verdict = "No significant technical issues detected."
    elif health_score >= 75:
        worst = mix.problems[0]
        verdict = f"Mix is in good shape. Primary focus: {worst.category.replace('_', ' ')}."
    else:
        top3 = [p.category.replace("_", " ") for p in mix.problems[:3]]
        verdict = f"Mix needs attention: {', '.join(top3)}."

    severity = _severity_label(health_score)
    return ReportSection(
        title="Executive Summary",
        severity=severity,
        summary=verdict,
        points=tuple(points),
        confidence="high",
    )


def _frequency_section(mix: MixReport) -> ReportSection:
    """Generate the frequency analysis section."""
    bands = mix.frequency.bands
    points: list[str] = [
        f"Sub (20–60 Hz):      {bands.sub:+.1f} dB",
        f"Low (60–200 Hz):     {bands.low:+.1f} dB",
        f"Low-mid (200–500 Hz): {bands.low_mid:+.1f} dB",
        f"Mid (500–2k Hz):     {bands.mid:+.1f} dB",
        f"High-mid (2–6k Hz):  {bands.high_mid:+.1f} dB",
        f"High (6–12k Hz):     {bands.high:+.1f} dB",
        f"Air (12–20k Hz):     {bands.air:+.1f} dB",
        f"Spectral centroid: {mix.frequency.spectral_centroid:.0f} Hz "
        f"({'bright' if mix.frequency.spectral_centroid > 2000 else 'balanced' if mix.frequency.spectral_centroid > 1200 else 'dark'})",
        f"Spectral tilt: {mix.frequency.spectral_tilt:.2f} dB/oct " f"(typical: −3 to −6 dB/oct)",
    ]

    freq_problems = [
        p for p in mix.problems if p.category in {"muddiness", "harshness", "boominess", "thinness"}
    ]
    if freq_problems:
        for p in freq_problems:
            points.append(f"⚠ {p.description}")
    else:
        points.append("✓ No frequency balance issues detected")

    max_sev = max((p.severity for p in freq_problems), default=0.0)
    return ReportSection(
        title="Frequency Analysis",
        severity=_problem_severity_label(max_sev),
        summary=(
            f"7-band spectral profile | centroid {mix.frequency.spectral_centroid:.0f} Hz | "
            f"tilt {mix.frequency.spectral_tilt:.1f} dB/oct"
        ),
        points=tuple(points),
        confidence="high",
    )


def _stereo_section(mix: MixReport) -> ReportSection:
    """Generate the stereo image analysis section."""
    if mix.stereo is None or mix.stereo.is_mono:
        return ReportSection(
            title="Stereo Analysis",
            severity="warning",
            summary="Mono input — no stereo analysis available",
            points=("Input signal is mono. Consider stereo enhancement tools.",),
            confidence="high",
        )

    st = mix.stereo
    points: list[str] = [
        f"Overall width: {st.width:.3f} (0=mono, 1=fully decorrelated)",
        f"L-R correlation: {st.lr_correlation:.3f} "
        f"({'narrow/mono' if st.lr_correlation > 0.8 else 'balanced' if st.lr_correlation > 0.3 else 'wide/check phase'})",
        f"Mid/side ratio: {st.mid_side_ratio:.1f} dB (positive = mid-heavy)",
        f"Per-band widths: sub {st.band_widths.sub:.2f} | low {st.band_widths.low:.2f} | low-mid {st.band_widths.low_mid:.2f} | "
        f"mid {st.band_widths.mid:.2f} | high-mid {st.band_widths.high_mid:.2f} | high {st.band_widths.high:.2f} | air {st.band_widths.air:.2f}",
    ]

    stereo_problems = [p for p in mix.problems if p.category in {"narrow_stereo", "phase_issues"}]
    if stereo_problems:
        for p in stereo_problems:
            points.append(f"⚠ {p.description}")
    else:
        points.append("✓ Stereo image within genre targets")

    max_sev = max((p.severity for p in stereo_problems), default=0.0)
    return ReportSection(
        title="Stereo Analysis",
        severity=_problem_severity_label(max_sev),
        summary=(
            f"Width {st.width:.2f} | L-R correlation {st.lr_correlation:.2f} | "
            f"mid-side ratio {st.mid_side_ratio:.1f} dB"
        ),
        points=tuple(points),
        confidence="high",
    )


def _dynamics_section(mix: MixReport) -> ReportSection:
    """Generate the dynamics analysis section."""
    dyn = mix.dynamics
    points: list[str] = [
        f"Integrated LUFS: {dyn.lufs:.1f} LUFS",
        f"RMS level: {dyn.rms_db:.1f} dBFS | Peak: {dyn.peak_db:.1f} dBFS",
        f"Crest factor: {dyn.crest_factor:.1f} dB " f"(target 8–12 dB for {mix.genre})",
        f"Dynamic range: {dyn.dynamic_range:.1f} dB | LRA: {dyn.loudness_range:.1f} LU",
    ]

    dyn_problems = [
        p for p in mix.problems if p.category in {"over_compression", "under_compression"}
    ]
    if dyn_problems:
        for p in dyn_problems:
            points.append(f"⚠ {p.description}")
    else:
        points.append("✓ Dynamics within genre targets")

    max_sev = max((p.severity for p in dyn_problems), default=0.0)
    return ReportSection(
        title="Dynamics Analysis",
        severity=_problem_severity_label(max_sev),
        summary=(
            f"{dyn.lufs:.1f} LUFS | crest {dyn.crest_factor:.1f} dB | "
            f"LRA {dyn.loudness_range:.1f} LU"
        ),
        points=tuple(points),
        confidence="high",
    )


def _problems_section(mix: MixReport) -> ReportSection:
    """Generate the problems + fixes section."""
    if not mix.problems:
        return ReportSection(
            title="Problems & Fixes",
            severity="ok",
            summary="No significant mix problems detected",
            points=("Mix meets genre targets across all checked dimensions.",),
            confidence="high",
        )

    points: list[str] = []
    for i, p in enumerate(mix.problems, 1):
        points.append(
            f"{i}. [{p.category.upper()} | severity {p.severity:.1f}/10] " f"{p.description}"
        )
        # Add first fix step if available
        for rec in mix.recommendations:
            if rec.problem_category == p.category and rec.steps:
                points.append(f"   → Fix: {rec.steps[0].action}")
                break

    max_sev = max(p.severity for p in mix.problems)
    return ReportSection(
        title="Problems & Fixes",
        severity=_problem_severity_label(max_sev),
        summary=(f"{len(mix.problems)} problem(s) detected | " f"worst severity: {max_sev:.1f}/10"),
        points=tuple(points),
        confidence="high",
    )


def _reference_section(reference: ReferenceComparison) -> ReportSection:
    """Generate the reference comparison section."""
    points: list[str] = [
        f"Overall similarity: {reference.overall_similarity:.0f}% "
        f"(vs {reference.num_references} reference track"
        f"{'s' if reference.num_references != 1 else ''})",
    ]

    for dim in reference.dimensions:
        bar = "█" * int(dim.score / 10) + "░" * (10 - int(dim.score / 10))
        points.append(f"{dim.name.capitalize():12s} [{bar}] {dim.score:.0f}% — {dim.description}")

    if reference.lufs_delta != 0.0:
        action = "boost" if reference.lufs_delta < 0 else "attenuate"
        points.append(
            f"Loudness align: {action} by {abs(reference.lufs_delta):.1f} dB "
            f"to match reference level ({reference.lufs_normalization_db:+.1f} dB)"
        )

    if reference.deltas:
        points.append("Top improvements:")
        for d in reference.deltas[:3]:
            points.append(f"  • [{d.dimension}] {d.recommendation[:100]}")

    severity = _severity_label(reference.overall_similarity)
    return ReportSection(
        title="Reference Comparison",
        severity=severity,
        summary=(
            f"{reference.overall_similarity:.0f}% similarity to commercial references — "
            f"{len(reference.deltas)} improvement delta(s) identified"
        ),
        points=tuple(points),
        confidence="medium",
    )


def _chain_section(mix: MixReport) -> ReportSection:
    """Generate the signal chain recommendation section."""
    try:
        chain = get_chain(mix.genre, "mix_bus")
        points: list[str] = [
            f"Genre: {chain.genre} | Stage: {chain.stage}",
            f"Description: {chain.description}",
        ]
        for i, proc in enumerate(chain.processors, 1):
            params_str = ", ".join(f"{p.name}: {p.value}" for p in proc.params[:3])
            points.append(
                f"{i}. {proc.name} ({proc.proc_type}) — "
                f"Primary: {proc.plugin_primary} | "
                f"Fallback: {proc.plugin_fallback}" + (f" | {params_str}" if params_str else "")
            )
        return ReportSection(
            title="Signal Chain Recommendation",
            severity="ok",
            summary=f"{mix.genre} mix-bus chain: {len(chain.processors)} processor(s)",
            points=tuple(points),
            confidence="medium",
        )
    except (ValueError, KeyError):
        return ReportSection(
            title="Signal Chain Recommendation",
            severity="ok",
            summary="No chain template available for this genre",
            points=("Use a standard mix-bus chain: EQ → Compressor → Limiter.",),
            confidence="low",
        )


def _master_section(master: MasterReport) -> ReportSection:
    """Generate the master readiness section."""
    m = master.master
    points: list[str] = [
        f"Readiness score: {m.readiness_score:.0f}/100",
        f"Integrated LUFS: {m.lufs_integrated:.1f} | "
        f"Short-term max: {m.lufs_short_term_max:.1f} | "
        f"Momentary max: {m.lufs_momentary_max:.1f}",
        f"True peak: {m.true_peak_db:.2f} dBTP "
        f"({'OK' if m.true_peak_db <= -1.0 else '⚠ EXCEEDS -1 dBTP ceiling'})",
        f"Crest factor: {m.crest_factor:.1f} dB | " f"Spectral balance: {m.spectral_balance}",
        f"Inter-sample peaks: {m.inter_sample_peaks} "
        f"({'none' if m.inter_sample_peaks == 0 else 'may clip on D/A conversion'})",
    ]

    if m.sections:
        section_summary = " | ".join(f"{s.label}: {s.rms_db:.1f} dBRMS" for s in m.sections)
        points.append(f"Section dynamics: {section_summary}")

    for issue in m.issues:
        points.append(f"⚠ {issue}")

    if not m.issues:
        points.append("✓ Master meets release targets")

    return ReportSection(
        title="Master Readiness",
        severity=_severity_label(m.readiness_score),
        summary=(
            f"Readiness {m.readiness_score:.0f}/100 | "
            f"LUFS {m.lufs_integrated:.1f} | "
            f"True peak {m.true_peak_db:.1f} dBTP"
        ),
        points=tuple(points),
        confidence="high",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_full_report(
    mix_report: MixReport,
    *,
    master_report: MasterReport | None = None,
    reference_comparison: ReferenceComparison | None = None,
) -> FullMixReport:
    """Generate a complete structured diagnostic report.

    Combines mix analysis, optional mastering analysis, and optional reference
    comparison into a single FullMixReport with 6–8 structured sections.

    Args:
        mix_report:           Output of MixAnalysisEngine.full_mix_analysis().
        master_report:        Optional MasterReport from master_analysis().
                              Adds the 'Master Readiness' section if provided.
        reference_comparison: Optional ReferenceComparison from reference.py.
                              Adds the 'Reference Comparison' section if provided.

    Returns:
        FullMixReport with all sections, health score, and top priorities.
    """
    health = _compute_health_score(mix_report, reference_comparison)
    top = _top_priorities(mix_report, reference_comparison)

    ref_section = (
        _reference_section(reference_comparison) if reference_comparison is not None else None
    )
    master_section = _master_section(master_report) if master_report is not None else None

    return FullMixReport(
        mix_report=mix_report,
        master_report=master_report,
        reference_comparison=reference_comparison,
        executive_summary=_executive_summary(
            mix_report, master_report, reference_comparison, health
        ),
        frequency_analysis=_frequency_section(mix_report),
        stereo_analysis=_stereo_section(mix_report),
        dynamics_analysis=_dynamics_section(mix_report),
        problems_and_fixes=_problems_section(mix_report),
        reference_section=ref_section,
        signal_chain_section=_chain_section(mix_report),
        master_readiness_section=master_section,
        overall_health_score=health,
        top_priorities=top,
        genre=mix_report.genre,
        duration_sec=mix_report.duration_sec,
    )
