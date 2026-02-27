"""
core/mix_analysis/arrangement.py — Section detection and energy flow analysis.

Pure module: no file I/O, no env vars.  Takes pre-loaded audio arrays and an
injected librosa module so the module itself has no hard dependency on the
audio stack at import time.

Theory
======
Arrangement structure is detected via energy envelope segmentation:
  1. Compute RMS energy in short frames (~500ms windows).
  2. Compute onset density (events/sec) per frame.
  3. Segment the timeline where both energy AND onset density change significantly.
  4. Classify each segment (intro / buildup / drop / breakdown / outro / transition)
     using energy level + onset density heuristics relative to the track's own
     median and peak.

Energy flow analysis checks:
  - Drop-to-breakdown contrast: target 3–6 dB for organic house / melodic techno.
  - Buildup energy curve: should be monotonically ascending.
  - Abrupt transitions: energy jumps > 6 dB within < 1 bar.
  - Section proportion conventions per genre (e.g. breakdown < 8 bars = too short).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Section types
# ---------------------------------------------------------------------------

SECTION_TYPES = ("intro", "buildup", "drop", "breakdown", "outro", "transition", "unknown")

# Genre-specific minimum bar lengths (at 4/4 time, quarter-note beats)
_MIN_BARS: dict[str, dict[str, int]] = {
    "organic house": {
        "intro": 8,
        "buildup": 4,
        "drop": 16,
        "breakdown": 16,
        "outro": 8,
        "transition": 2,
    },
    "melodic techno": {
        "intro": 8,
        "buildup": 8,
        "drop": 16,
        "breakdown": 8,
        "outro": 8,
        "transition": 2,
    },
    "deep house": {
        "intro": 16,
        "buildup": 4,
        "drop": 16,
        "breakdown": 16,
        "outro": 16,
        "transition": 2,
    },
    "progressive house": {
        "intro": 16,
        "buildup": 8,
        "drop": 32,
        "breakdown": 16,
        "outro": 16,
        "transition": 2,
    },
    "afro house": {
        "intro": 8,
        "buildup": 4,
        "drop": 16,
        "breakdown": 8,
        "outro": 8,
        "transition": 2,
    },
}

_DROP_BREAKDOWN_TARGET_DB: dict[str, tuple[float, float]] = {
    "organic house": (3.0, 6.0),
    "melodic techno": (4.0, 8.0),
    "deep house": (2.0, 5.0),
    "progressive house": (4.0, 8.0),
    "afro house": (3.0, 6.0),
}


# ---------------------------------------------------------------------------
# Frozen dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Section:
    """A detected arrangement section.

    Invariants:
        start_sec >= 0.0
        end_sec > start_sec
        section_type in SECTION_TYPES
        energy_db is the mean RMS in dBFS over the section
        bars >= 0 (0 if bpm not provided)
    """

    start_sec: float
    end_sec: float
    section_type: str
    energy_db: float
    onset_density: float
    """Average onsets per second in this section."""
    bars: int
    """Number of 4/4 bars in this section (0 if bpm not supplied)."""
    energy_relative: float
    """Energy relative to track peak (0–1). 1.0 = loudest section."""

    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec

    def as_dict(self) -> dict[str, Any]:
        return {
            "start_sec": round(self.start_sec, 2),
            "end_sec": round(self.end_sec, 2),
            "duration_sec": round(self.duration_sec(), 2),
            "section_type": self.section_type,
            "energy_db": round(self.energy_db, 2),
            "onset_density": round(self.onset_density, 3),
            "bars": self.bars,
            "energy_relative": round(self.energy_relative, 3),
        }


@dataclass(frozen=True)
class EnergyTransition:
    """Energy jump at a section boundary."""

    from_type: str
    to_type: str
    boundary_sec: float
    delta_db: float
    """Positive = energy increases."""
    is_abrupt: bool
    """True if delta > 6 dB and section < 1 bar long."""


@dataclass(frozen=True)
class EnergyFlow:
    """Aggregate energy flow analysis across the full arrangement.

    Invariants:
        drop_breakdown_ratio_db >= 0 (drop is always >= breakdown in well-mixed track)
        0.0 <= buildup_ascent_ratio <= 1.0 (fraction of buildup sections with ascending energy)
    """

    sections: tuple[Section, ...]
    drop_count: int
    breakdown_count: int
    buildup_count: int

    drop_energy_db: float | None
    """Mean RMS of all drop sections, or None if no drops detected."""
    breakdown_energy_db: float | None
    """Mean RMS of all breakdown sections, or None if no breakdowns detected."""

    drop_breakdown_ratio_db: float | None
    """Drop − breakdown energy in dB. Target: 3–6 dB for most genres."""

    buildup_ascending: bool
    """True if buildups have monotonically increasing energy (as they should)."""

    max_transition_jump_db: float
    """Largest energy jump at any section boundary."""

    abrupt_transitions: tuple[EnergyTransition, ...]
    """Transitions where energy jumps > 6 dB."""

    energy_contrast_score: float
    """0–100 score for energy contrast between drops and breakdowns."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "drop_count": self.drop_count,
            "breakdown_count": self.breakdown_count,
            "buildup_count": self.buildup_count,
            "drop_energy_db": (
                round(self.drop_energy_db, 2) if self.drop_energy_db is not None else None
            ),
            "breakdown_energy_db": (
                round(self.breakdown_energy_db, 2)
                if self.breakdown_energy_db is not None
                else None
            ),
            "drop_breakdown_ratio_db": (
                round(self.drop_breakdown_ratio_db, 2)
                if self.drop_breakdown_ratio_db is not None
                else None
            ),
            "buildup_ascending": self.buildup_ascending,
            "max_transition_jump_db": round(self.max_transition_jump_db, 2),
            "abrupt_transitions": [
                {
                    "from": t.from_type,
                    "to": t.to_type,
                    "at_sec": round(t.boundary_sec, 2),
                    "delta_db": round(t.delta_db, 2),
                    "is_abrupt": t.is_abrupt,
                }
                for t in self.abrupt_transitions
            ],
            "energy_contrast_score": round(self.energy_contrast_score, 1),
        }


@dataclass(frozen=True)
class ArrangementProblem:
    """A detected arrangement structure problem.

    Invariants:
        0.0 <= severity <= 10.0
        problem_type describes a specific structural issue
    """

    problem_type: str
    """short identifier: 'short_breakdown', 'no_contrast', 'abrupt_transition', etc."""
    severity: float
    description: str
    suggestion: str
    affected_section: str | None
    """Section type where the problem occurs, or None if global."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "problem_type": self.problem_type,
            "severity": round(self.severity, 1),
            "description": self.description,
            "suggestion": self.suggestion,
            "affected_section": self.affected_section,
        }


# ---------------------------------------------------------------------------
# Section detection (requires injected librosa + numpy)
# ---------------------------------------------------------------------------


def detect_sections(
    y: Any,
    sr: int,
    librosa: Any,
    *,
    bpm: float = 0.0,
    hop_length: int = 512,
) -> list[Section]:
    """Detect arrangement sections in an audio signal.

    Uses energy envelope + onset density segmentation.  Section boundaries are
    found where both metrics change significantly.  Sections are then classified
    by their energy level relative to the track's own peak and breakdown.

    Args:
        y:          Audio array (mono or stereo — will be mixed to mono).
        sr:         Sample rate in Hz.
        librosa:    Injected librosa module (avoids import-time dependency).
        bpm:        BPM for bar-length calculation. 0 = skip bar counting.
        hop_length: STFT hop in samples.  Smaller = finer time resolution.

    Returns:
        List of Section objects sorted by start_sec.
        Returns a single 'unknown' section if detection fails.
    """
    import numpy as np  # noqa: PLC0415

    try:
        # Mix to mono
        if y.ndim > 1:
            y_mono = librosa.to_mono(y)
        else:
            y_mono = y

        duration = librosa.get_duration(y=y_mono, sr=sr)

        # --- RMS energy envelope ---
        frame_len = int(sr * 0.5)  # 500 ms frames
        hop = max(hop_length, frame_len // 4)
        rms = librosa.feature.rms(y=y_mono, frame_length=frame_len, hop_length=hop)[0]
        rms_db = librosa.amplitude_to_db(rms + 1e-9, ref=np.max)
        times = librosa.frames_to_time(np.arange(len(rms_db)), sr=sr, hop_length=hop)

        # --- Onset density envelope ---
        onset_frames = librosa.onset.onset_detect(y=y_mono, sr=sr, hop_length=hop_length)
        onset_times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=hop_length)

        # Compute onset density per RMS frame
        density_arr = np.zeros(len(times))
        window_sec = 2.0
        for i, t in enumerate(times):
            in_window = (onset_times >= t - window_sec) & (onset_times < t + window_sec)
            density_arr[i] = np.sum(in_window) / (2.0 * window_sec)

        # --- Find boundaries via novelty / significant energy changes ---
        min_section_sec = 8.0  # minimum 8 seconds per section
        boundaries: list[float] = [0.0]

        energy_threshold_db = 3.0  # minimum dB change to count as boundary
        density_threshold = 1.5    # minimum density change

        i = 1
        while i < len(rms_db) - 1:
            t = float(times[i])
            if t - boundaries[-1] < min_section_sec:
                i += 1
                continue

            # Look-ahead / look-back windows (5 frames each side)
            look = 5
            before_e = float(np.mean(rms_db[max(0, i - look):i]))
            after_e = float(np.mean(rms_db[i:min(len(rms_db), i + look)]))
            before_d = float(np.mean(density_arr[max(0, i - look):i]))
            after_d = float(np.mean(density_arr[i:min(len(density_arr), i + look)]))

            e_jump = abs(after_e - before_e)
            d_jump = abs(after_d - before_d)

            if e_jump >= energy_threshold_db or d_jump >= density_threshold:
                boundaries.append(t)
            i += 1

        boundaries.append(duration)

        # --- Classify each segment ---
        peak_rms_db = float(np.max(rms_db))
        median_rms_db = float(np.median(rms_db))

        sections: list[Section] = []

        for idx in range(len(boundaries) - 1):
            seg_start = boundaries[idx]
            seg_end = boundaries[idx + 1]
            seg_dur = seg_end - seg_start

            # Find frames within this segment
            mask = (times >= seg_start) & (times < seg_end)
            if not np.any(mask):
                continue

            seg_energy_db = float(np.mean(rms_db[mask]))
            seg_density = float(np.mean(density_arr[mask]))
            energy_rel = float(
                10.0 ** ((seg_energy_db - peak_rms_db) / 20.0)
            )  # normalised 0–1

            # Classification heuristics
            is_loud = seg_energy_db >= peak_rms_db - 3.0
            is_medium = median_rms_db - 2.0 <= seg_energy_db < peak_rms_db - 3.0
            is_quiet = seg_energy_db < median_rms_db - 2.0
            is_high_density = seg_density >= 3.0
            is_low_density = seg_density < 1.5
            is_start = seg_start < 30.0
            is_end = seg_end > duration - 30.0
            is_building = (
                idx > 0
                and seg_energy_db > float(np.mean(rms_db[(times >= boundaries[idx - 1]) & (times < seg_start)]))
            ) if idx > 0 else False

            if is_start and is_quiet:
                stype = "intro"
            elif is_end and is_quiet:
                stype = "outro"
            elif is_loud and is_high_density:
                stype = "drop"
            elif is_quiet and is_low_density:
                stype = "breakdown"
            elif is_medium and is_building and is_high_density:
                stype = "buildup"
            elif seg_dur < 8.0:
                stype = "transition"
            elif is_quiet:
                stype = "breakdown"
            elif is_loud:
                stype = "drop"
            else:
                stype = "unknown"

            # Bar count
            bars = 0
            if bpm > 0.0:
                bars_float = (seg_dur * bpm) / (60.0 * 4.0)
                bars = max(0, round(bars_float))

            sections.append(
                Section(
                    start_sec=round(seg_start, 2),
                    end_sec=round(seg_end, 2),
                    section_type=stype,
                    energy_db=round(seg_energy_db, 2),
                    onset_density=round(seg_density, 3),
                    bars=bars,
                    energy_relative=round(energy_rel, 3),
                )
            )

        return sections if sections else _fallback_section(duration)

    except Exception:
        try:

            dur = librosa.get_duration(y=y, sr=sr)
        except Exception:
            dur = 0.0
        return _fallback_section(dur)


def _fallback_section(duration: float) -> list[Section]:
    """Return a single 'unknown' section covering the full track."""
    return [
        Section(
            start_sec=0.0,
            end_sec=duration,
            section_type="unknown",
            energy_db=-20.0,
            onset_density=0.0,
            bars=0,
            energy_relative=1.0,
        )
    ]


# ---------------------------------------------------------------------------
# Energy flow analysis (pure)
# ---------------------------------------------------------------------------


def analyze_energy_flow(sections: list[Section]) -> EnergyFlow:
    """Analyse energy contrast and transitions across arrangement sections.

    Args:
        sections: Ordered list of Section objects.

    Returns:
        EnergyFlow with drop/breakdown contrast, buildup analysis, transitions.
    """
    drops = [s for s in sections if s.section_type == "drop"]
    breakdowns = [s for s in sections if s.section_type == "breakdown"]
    buildups = [s for s in sections if s.section_type == "buildup"]

    drop_energy = float(sum(s.energy_db for s in drops) / len(drops)) if drops else None
    bd_energy = float(sum(s.energy_db for s in breakdowns) / len(breakdowns)) if breakdowns else None

    ratio = None
    contrast_score = 50.0
    if drop_energy is not None and bd_energy is not None:
        ratio = round(drop_energy - bd_energy, 2)
        # Score 0–100: 0=no contrast, 100=ideal (3–6 dB contrast)
        if 3.0 <= ratio <= 6.0:
            contrast_score = 100.0
        elif ratio < 3.0:
            contrast_score = max(0.0, (ratio / 3.0) * 100.0)
        else:  # > 6 dB (too much contrast)
            contrast_score = max(40.0, 100.0 - (ratio - 6.0) * 10.0)

    # Buildup ascending check
    buildup_ascending = True
    if len(buildups) >= 2:
        energies = [s.energy_db for s in buildups]
        buildup_ascending = all(
            energies[i] <= energies[i + 1] for i in range(len(energies) - 1)
        )

    # Transition analysis
    abrupt: list[EnergyTransition] = []
    max_jump = 0.0

    for i in range(1, len(sections)):
        prev = sections[i - 1]
        curr = sections[i]
        delta = curr.energy_db - prev.energy_db
        abs_delta = abs(delta)
        if abs_delta > max_jump:
            max_jump = abs_delta

        is_abrupt = abs_delta > 6.0 and curr.bars <= 1
        if is_abrupt:
            abrupt.append(
                EnergyTransition(
                    from_type=prev.section_type,
                    to_type=curr.section_type,
                    boundary_sec=curr.start_sec,
                    delta_db=round(delta, 2),
                    is_abrupt=True,
                )
            )

    return EnergyFlow(
        sections=tuple(sections),
        drop_count=len(drops),
        breakdown_count=len(breakdowns),
        buildup_count=len(buildups),
        drop_energy_db=round(drop_energy, 2) if drop_energy is not None else None,
        breakdown_energy_db=round(bd_energy, 2) if bd_energy is not None else None,
        drop_breakdown_ratio_db=ratio,
        buildup_ascending=buildup_ascending,
        max_transition_jump_db=round(max_jump, 2),
        abrupt_transitions=tuple(abrupt),
        energy_contrast_score=round(contrast_score, 1),
    )


# ---------------------------------------------------------------------------
# Arrangement proportion check (pure)
# ---------------------------------------------------------------------------


def check_arrangement_proportions(
    sections: list[Section],
    genre: str,
    bpm: float = 0.0,
) -> list[ArrangementProblem]:
    """Check arrangement section lengths against genre conventions.

    Args:
        sections: Detected sections.
        genre:    Genre key (e.g. 'organic house').
        bpm:      BPM for bar-length calculation. 0 = skip bar checks.

    Returns:
        List of ArrangementProblem objects sorted by severity descending.
    """
    problems: list[ArrangementProblem] = []
    genre_lower = genre.lower()
    min_bars = _MIN_BARS.get(genre_lower, _MIN_BARS["organic house"])
    target_db_range = _DROP_BREAKDOWN_TARGET_DB.get(genre_lower, (3.0, 6.0))

    flow = analyze_energy_flow(sections)

    # 1. No energy contrast
    if flow.drop_breakdown_ratio_db is not None:
        ratio = flow.drop_breakdown_ratio_db
        lo, hi = target_db_range
        if ratio < lo:
            sev = min(10.0, (lo - ratio) * 2.0)
            problems.append(
                ArrangementProblem(
                    problem_type="insufficient_energy_contrast",
                    severity=sev,
                    description=(
                        f"Drop is only {ratio:.1f} dB louder than breakdown "
                        f"(target {lo:.0f}–{hi:.0f} dB for {genre})."
                    ),
                    suggestion=(
                        f"Boost drop energy by {lo - ratio:.1f}–{hi - ratio:.1f} dB "
                        "or reduce breakdown level to create more impact."
                    ),
                    affected_section="drop",
                )
            )
        elif ratio > hi + 4.0:
            problems.append(
                ArrangementProblem(
                    problem_type="excessive_energy_contrast",
                    severity=3.0,
                    description=(
                        f"Drop is {ratio:.1f} dB louder than breakdown — "
                        "contrast may feel too jarring."
                    ),
                    suggestion="Consider raising the breakdown level slightly.",
                    affected_section="breakdown",
                )
            )

    # 2. No drops detected
    if flow.drop_count == 0:
        problems.append(
            ArrangementProblem(
                problem_type="no_drop_detected",
                severity=7.0,
                description="No drop section detected in the arrangement.",
                suggestion="Add a high-energy drop section with full drums and bass.",
                affected_section=None,
            )
        )

    # 3. Short sections (only if bpm provided)
    if bpm > 0.0:
        by_type: dict[str, list[Section]] = {}
        for s in sections:
            by_type.setdefault(s.section_type, []).append(s)

        for stype, slist in by_type.items():
            target_bars = min_bars.get(stype, 0)
            if target_bars == 0:
                continue
            for s in slist:
                if s.bars > 0 and s.bars < target_bars:
                    sev = min(8.0, (target_bars - s.bars) * 0.5)
                    problems.append(
                        ArrangementProblem(
                            problem_type=f"short_{stype}",
                            severity=sev,
                            description=(
                                f"{stype.capitalize()} is {s.bars} bars — "
                                f"typical {genre} {stype} uses {target_bars}+ bars."
                            ),
                            suggestion=(
                                f"Extend the {stype} to at least {target_bars} bars "
                                "to meet genre conventions."
                            ),
                            affected_section=stype,
                        )
                    )

    # 4. Abrupt transitions
    for t in flow.abrupt_transitions:
        problems.append(
            ArrangementProblem(
                problem_type="abrupt_transition",
                severity=min(8.0, abs(t.delta_db) - 4.0),
                description=(
                    f"Abrupt energy jump of {abs(t.delta_db):.1f} dB at "
                    f"{t.boundary_sec:.0f}s ({t.from_type} → {t.to_type})."
                ),
                suggestion=(
                    "Add a 1–2 bar transition: filter sweep, white noise riser, "
                    "or gradual volume automation."
                ),
                affected_section="transition",
            )
        )

    # 5. No breakdown
    if flow.breakdown_count == 0 and flow.drop_count > 0:
        problems.append(
            ArrangementProblem(
                problem_type="no_breakdown",
                severity=5.0,
                description="No breakdown section detected — drops may feel relentless.",
                suggestion=(
                    "Add at least one breakdown to create tension before the drop."
                ),
                affected_section=None,
            )
        )

    # 6. Buildup not ascending
    if flow.buildup_count > 0 and not flow.buildup_ascending:
        problems.append(
            ArrangementProblem(
                problem_type="buildup_not_ascending",
                severity=4.0,
                description="Buildup energy is not consistently increasing.",
                suggestion=(
                    "Layer elements progressively: add hi-hats, percussion, "
                    "and filter-open pads bar by bar."
                ),
                affected_section="buildup",
            )
        )

    problems.sort(key=lambda p: p.severity, reverse=True)
    return problems
