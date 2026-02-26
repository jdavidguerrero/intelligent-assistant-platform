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


# ---------------------------------------------------------------------------
# Signal chain types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProcessorParam:
    """A single (name, value) parameter for a signal processor.

    Values are always stored as strings for YAML-round-trip safety.
    Numeric values can be recovered with float(param.value).
    """

    name: str
    """Parameter name, e.g. 'frequency', 'gain', 'ratio'."""

    value: str
    """Parameter value as string, e.g. '280 Hz', '-3 dB', '4:1'."""


@dataclass(frozen=True)
class Processor:
    """A single stage in a signal processing chain.

    Provides primary (preferred 3rd-party) and fallback (Ableton stock)
    plugin suggestions so users without every plugin can still apply the fix.

    Invariants:
        params is a tuple of ProcessorParam (hashable, serialisable)
    """

    name: str
    """Human-readable processor name, e.g. 'Low-Mid Cleanup EQ'."""

    proc_type: str
    """Processor category: 'eq', 'compressor', 'limiter', 'saturation',
    'stereo_widener', 'de_esser', 'multiband_comp'."""

    plugin_primary: str
    """Recommended 3rd-party plugin, e.g. 'FabFilter Pro-Q 3'."""

    plugin_fallback: str
    """Ableton-stock alternative, e.g. 'Ableton EQ Eight'."""

    params: tuple[ProcessorParam, ...]
    """Ordered processing parameters."""

    def get_param(self, name: str) -> str | None:
        """Return the value of a named parameter, or None if not found."""
        for p in self.params:
            if p.name == name:
                return p.value
        return None


@dataclass(frozen=True)
class SignalChain:
    """An ordered sequence of processors for a specific stage and genre.

    Stages: 'mix_bus', 'master', 'kick', 'bass', 'pads', 'leads', 'drums'.

    Invariants:
        len(processors) >= 1
    """

    genre: str
    """Target genre, e.g. 'organic house'."""

    stage: str
    """Processing stage name."""

    description: str
    """One-sentence description of the chain's character."""

    processors: tuple[Processor, ...]
    """Ordered list of processors — applied left to right."""


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FixStep:
    """A single action step in a mix problem fix procedure.

    Each step addresses one aspect of the problem with a specific processor
    setting, targeting a named bus or track.
    """

    action: str
    """Human-readable action description with specific parameter values.
    E.g. 'Cut 3.0 dB at 280 Hz (Q=2.0) on pad bus'."""

    bus: str
    """Target bus or track, e.g. 'pad bus', 'master bus', 'bass bus'."""

    plugin_primary: str
    """Recommended plugin, e.g. 'FabFilter Pro-Q 3'."""

    plugin_fallback: str
    """Ableton-stock fallback, e.g. 'Ableton EQ Eight'."""

    params: tuple[ProcessorParam, ...]
    """Exact parameter values for this step."""


@dataclass(frozen=True)
class Recommendation:
    """A complete, data-driven fix for a detected mix problem.

    Parameters in `steps` are computed from the actual measured values
    in the analysis (not generic suggestions).

    Invariants:
        0.0 <= severity <= 10.0
    """

    problem_category: str
    """The problem type being addressed, e.g. 'muddiness'."""

    genre: str
    """Genre context used for target values."""

    severity: float
    """Severity of the original problem (0–10), from MixProblem."""

    summary: str
    """One-line prescription: what to do, where, with what values.
    E.g. 'Cut 3.1 dB at 280 Hz Q=2.0 on pad bus'."""

    steps: tuple[FixStep, ...]
    """Ordered steps to execute the fix."""

    rag_query: str
    """Suggested search query for RAG knowledge base.
    Populated by recommend_fix(), used by MixAnalysisEngine for citations."""

    rag_citations: tuple[str, ...]
    """Knowledge base citations (empty until enhanced by RAG)."""


# ---------------------------------------------------------------------------
# Mastering analysis
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SectionDynamics:
    """Dynamic profile for one section of the track (e.g. intro, drop)."""

    label: str
    """Section label: 'intro', 'build', 'drop', 'breakdown'."""

    start_sec: float
    rms_db: float
    peak_db: float
    crest_factor: float


@dataclass(frozen=True)
class MasterAnalysis:
    """Mastering-grade loudness and readiness analysis.

    Includes the three LUFS windows defined in BS.1770 / EBU R128,
    true peak with 4x oversampling, and a 0–100 readiness score.

    Invariants:
        -70.0 <= lufs_integrated <= 0.0
        lufs_momentary_max >= lufs_integrated
        true_peak_db <= 0.0  (should never exceed 0 dBFS)
        0.0 <= readiness_score <= 100.0
    """

    lufs_integrated: float
    """Integrated loudness (BS.1770-4 gated). Genre targets: −9 to −6 LUFS."""

    lufs_short_term_max: float
    """Maximum short-term loudness (3 s window). Identifies loudest section."""

    lufs_momentary_max: float
    """Maximum momentary loudness (400 ms window). Identifies loudest instant."""

    true_peak_db: float
    """True peak with 4x oversampling (ITU-R BS.1770). Ceiling: −1.0 dBTP."""

    inter_sample_peaks: int
    """Count of frames where 4x-upsampled peak exceeds original sample peak.
    >0 means potential inter-sample clipping on D/A conversion."""

    crest_factor: float
    """Overall peak-to-RMS ratio in dB. Genre target: 8–12 dB for organic house."""

    sections: tuple[SectionDynamics, ...]
    """Per-section dynamics (4 equal sections: intro / build / drop / outro)."""

    spectral_balance: str
    """Subjective balance: 'dark', 'slightly dark', 'neutral', 'slightly bright',
    'bright'. Derived from spectral tilt vs genre target."""

    readiness_score: float
    """Master readiness 0–100. 100 = meets all genre targets, 0 = all fail."""

    issues: tuple[str, ...]
    """List of issues reducing the readiness score, ordered by severity."""


# ---------------------------------------------------------------------------
# Top-level reports
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MixReport:
    """Complete mix analysis: frequency + stereo + dynamics + transients
    + detected problems + prescriptive recommendations.

    Produced by MixAnalysisEngine.full_mix_analysis() in ingestion/.
    """

    frequency: FrequencyProfile
    stereo: StereoImage | None
    dynamics: DynamicProfile
    transients: TransientProfile
    problems: tuple[MixProblem, ...]
    recommendations: tuple[Recommendation, ...]
    genre: str
    duration_sec: float
    sample_rate: int


@dataclass(frozen=True)
class MasterReport:
    """Mastering analysis + suggested signal chain.

    Produced by MixAnalysisEngine.master_analysis() in ingestion/.
    """

    master: MasterAnalysis
    suggested_chain: SignalChain
    genre: str
    duration_sec: float
    sample_rate: int


# ---------------------------------------------------------------------------
# Reference comparison types  (Week 18)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BandDelta:
    """Per-band spectral delta between a track and a reference track.

    Positive delta_db means the track has more energy in this band than the
    reference (i.e. the band is too loud relative to the reference style).
    """

    band: str
    """Band name: one of BAND_NAMES ('sub', 'low', …, 'air')."""

    track_db: float
    """Track's band level in dB relative to overall RMS."""

    reference_db: float
    """Reference track's band level in dB relative to overall RMS."""

    delta_db: float
    """Signed difference: track_db − reference_db."""


@dataclass(frozen=True)
class DimensionScore:
    """Similarity score for one of the six comparison dimensions.

    `track_value` and `ref_value` hold the primary metric for the dimension
    (e.g. width for 'stereo', LUFS for 'loudness') so that identify_deltas()
    can generate directional recommendations without re-reading the original
    analysis results.
    """

    name: str
    """Dimension name: 'spectral', 'stereo', 'dynamics', 'tonal',
    'transient', or 'loudness'."""

    score: float
    """Similarity score 0–100 (100 = identical to reference)."""

    track_value: float
    """Track's primary metric value for this dimension."""

    ref_value: float
    """Reference average primary metric value."""

    unit: str
    """Physical unit for track_value / ref_value (e.g. 'dB', 'width', 'LUFS')."""

    description: str
    """One-sentence human-readable comparison summary."""


@dataclass(frozen=True)
class MixDelta:
    """A single actionable improvement derived from reference comparison.

    Each MixDelta maps to a concrete processing action (EQ cut/boost,
    compression, stereo widening, etc.) with signed direction and magnitude.

    Invariants:
        direction in {'increase', 'decrease'}
        0.0 <= priority <= 10.0
        magnitude >= 0.0
    """

    dimension: str
    """Which dimension this delta addresses ('spectral', 'stereo', …)."""

    direction: str
    """'increase' or 'decrease' — which way to move the metric."""

    magnitude: float
    """How much to change (in the dimension's natural unit)."""

    unit: str
    """Unit for magnitude (e.g. 'dB', 'width units', 'LUFS')."""

    recommendation: str
    """Specific, actionable recommendation with concrete values."""

    priority: float
    """Priority 0–10 (10 = most impactful fix). Derived from dimension score."""


@dataclass(frozen=True)
class ReferenceComparison:
    """A/B comparison of a track vs one or more commercial reference tracks.

    Scores are 0–100 similarity (100 = identical to reference).
    Deltas are signed: track − reference (positive = track is higher).

    Produced by core/mix_analysis/reference.py and consumed by:
        - ingestion/mix_engine.py (orchestration)
        - core/mix_analysis/report.py (structured reporting)
        - tools/music/compare_reference.py (MCP tool)
    """

    overall_similarity: float
    """Weighted average of all six dimension scores (0–100)."""

    dimensions: tuple[DimensionScore, ...]
    """Six DimensionScore objects — one per comparison dimension."""

    band_deltas: tuple[BandDelta, ...]
    """Per-band deltas for all 7 spectral bands."""

    # Convenience scalar deltas (track − reference averages)
    width_delta: float
    """Stereo width delta: track.width − ref.width."""

    crest_factor_delta: float
    """Crest factor delta in dB: track.crest_factor − ref.crest_factor."""

    lra_delta: float
    """LRA delta in LU: track.loudness_range − ref.loudness_range."""

    centroid_delta_hz: float
    """Spectral centroid delta in Hz: track.centroid − ref.centroid."""

    tilt_delta: float
    """Spectral tilt delta in dB/oct: track.tilt − ref.tilt."""

    density_delta: float
    """Transient density delta in onsets/s: track.density − ref.density."""

    sharpness_delta: float
    """Attack sharpness delta (0–1): track.sharpness − ref.sharpness."""

    lufs_delta: float
    """Integrated LUFS delta: track.lufs − ref.lufs."""

    deltas: tuple[MixDelta, ...]
    """Actionable improvements, sorted by priority (highest first)."""

    genre: str
    """Genre context used for the comparison."""

    num_references: int
    """Number of reference tracks used (1 for single, N for aggregate)."""

    lufs_normalization_db: float
    """dB gain needed to align track LUFS to reference average (informational)."""


# ---------------------------------------------------------------------------
# Calibration types  (Week 18)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricStats:
    """Mean and standard deviation for a single calibrated metric.

    Used to define the acceptable range for a genre target:
        acceptable = [mean − std, mean + std]
    """

    mean: float
    """Mean value across all reference tracks."""

    std: float
    """Standard deviation across all reference tracks."""

    @property
    def low(self) -> float:
        """Lower acceptance bound: mean − 1σ."""
        return self.mean - self.std

    @property
    def high(self) -> float:
        """Upper acceptance bound: mean + 1σ."""
        return self.mean + self.std


@dataclass(frozen=True)
class GenreTarget:
    """Genre target profile calibrated from real commercial reference analysis.

    Replaces manually authored YAML targets with data-driven statistics.
    Each field is a MetricStats with mean ± 1σ defining the acceptable range.

    Produced by core/mix_analysis/calibration.calibrate_genre_targets().
    """

    genre: str
    """Target genre (e.g. 'organic house')."""

    num_references: int
    """Number of reference tracks used for calibration."""

    # Spectral targets (band levels relative to overall RMS)
    sub_db: MetricStats
    low_db: MetricStats
    low_mid_db: MetricStats
    mid_db: MetricStats
    high_mid_db: MetricStats
    high_db: MetricStats
    air_db: MetricStats
    centroid_hz: MetricStats
    tilt_db_oct: MetricStats

    # Stereo targets
    width: MetricStats

    # Dynamics targets
    lufs: MetricStats
    crest_factor_db: MetricStats
    lra_lu: MetricStats

    # Transient targets
    density: MetricStats
    sharpness: MetricStats


# ---------------------------------------------------------------------------
# Structured report types  (Week 18)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReportSection:
    """One section of a full mix diagnostic report.

    Severity indicates the overall health of this aspect of the mix:
        'ok'       — meets genre targets
        'warning'  — minor issues, not urgent
        'critical' — significant problem needing immediate attention

    Confidence reflects how certain the analysis is:
        'high'   — clear technical issue measured from objective data
        'medium' — likely issue but depends on artistic intent
        'low'    — suggestion based on genre conventions
    """

    title: str
    """Section heading, e.g. 'Frequency Analysis'."""

    severity: str
    """'ok', 'warning', or 'critical'."""

    summary: str
    """One-sentence overview of this section's findings."""

    points: tuple[str, ...]
    """Bullet-point findings (specific values, comparisons, actions)."""

    confidence: str
    """'high', 'medium', or 'low'."""


@dataclass(frozen=True)
class FullMixReport:
    """Complete mix + master diagnostic report, optionally with reference comparison.

    Produced by core/mix_analysis/report.generate_full_report() and consumed
    by ingestion/mix_engine.py and tools/music/mix_master_report.py.

    Invariants:
        0.0 <= overall_health_score <= 100.0
        len(top_priorities) <= 5
    """

    mix_report: MixReport
    """The underlying mix analysis."""

    master_report: MasterReport | None
    """Optional mastering analysis (None if not requested)."""

    reference_comparison: ReferenceComparison | None
    """Optional A/B comparison vs commercial references."""

    # Structured report sections
    executive_summary: ReportSection
    frequency_analysis: ReportSection
    stereo_analysis: ReportSection
    dynamics_analysis: ReportSection
    problems_and_fixes: ReportSection
    reference_section: ReportSection | None
    signal_chain_section: ReportSection
    master_readiness_section: ReportSection | None

    overall_health_score: float
    """Aggregate mix health 0–100. Combines problem severity and reference similarity."""

    top_priorities: tuple[str, ...]
    """Top 3–5 most impactful improvements, ordered by priority."""

    genre: str
    duration_sec: float
