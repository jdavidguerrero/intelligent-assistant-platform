"""
core/mix_analysis/automation.py — Per-section automation suggestions.

Pure module: no I/O, no side effects.

Theory
======
Mix automation is arrangement-aware processing: the same track should sound
different in a drop versus a breakdown.  The platform generates concrete
automation suggestions (which parameter, which value, over which bars) based on:

  1. Section energy contrast goals: drops need clarity → shorter reverb sends.
  2. Tension building: buildups should have filter sweeps, rises, transient boosts.
  3. Intimacy in breakdowns: slight vocal/lead boost, longer reverb on pads.
  4. Energy management: bus compressor threshold automation for pumping effect.

Output
======
Each AutomationSuggestion specifies:
    - track:       which track or bus to automate
    - parameter:   the Ableton parameter path or label
    - start_bar:   when to start the automation (bar number from track start)
    - end_bar:     when to reach the target value
    - start_value: automation start value (normalised 0–1 where applicable)
    - end_value:   automation end value
    - reason:      plain-English explanation
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.mix_analysis.arrangement import Section
from core.mix_analysis.stems import StemFootprint, StemType

# ---------------------------------------------------------------------------
# AutomationSuggestion
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AutomationSuggestion:
    """A concrete automation change recommended for a mix section.

    Invariants:
        start_bar >= 0
        end_bar >= start_bar
        Values are in native units for the named parameter (not always 0–1)
    """

    track: str
    """Track or bus name (e.g. 'Pads', 'Drum Bus', 'Master')."""

    parameter: str
    """Parameter label (e.g. 'Filter Cutoff', 'Reverb Send', 'Volume', 'Threshold')."""

    start_bar: int
    end_bar: int

    start_value: float
    end_value: float

    unit: str
    """Value unit: '%', 'dB', 'Hz', 'norm' (0–1), 'ms'."""

    section_type: str
    """Which section this automation belongs to."""

    priority: float
    """0–10. Higher = more impactful. Use for UI ordering."""

    reason: str
    """Plain-English explanation of why this automation helps."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "track": self.track,
            "parameter": self.parameter,
            "start_bar": self.start_bar,
            "end_bar": self.end_bar,
            "start_value": round(self.start_value, 3),
            "end_value": round(self.end_value, 3),
            "unit": self.unit,
            "section_type": self.section_type,
            "priority": round(self.priority, 1),
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _sec_to_bar(sec: float, bpm: float) -> int:
    """Convert a time in seconds to the nearest bar number (1-indexed)."""
    if bpm <= 0.0:
        return 1
    beats_per_sec = bpm / 60.0
    bars = (sec * beats_per_sec) / 4.0
    return max(1, round(bars))


def _find_stems_by_type(
    footprints: dict[str, StemFootprint], *types: StemType
) -> list[str]:
    """Return track names whose stem_type is in types."""
    return [name for name, fp in footprints.items() if fp.stem_type in types]


# ---------------------------------------------------------------------------
# Section-specific automation generators (pure)
# ---------------------------------------------------------------------------


def _drop_automations(
    section: Section,
    footprints: dict[str, StemFootprint],
    bpm: float,
    genre: str,
) -> list[AutomationSuggestion]:
    """Generate automation suggestions for drop sections."""
    suggestions: list[AutomationSuggestion] = []
    start_bar = _sec_to_bar(section.start_sec, bpm)
    end_bar = _sec_to_bar(section.end_sec, bpm)
    # 2 bars before drop end to set reverb tail
    max(start_bar, end_bar - 2)

    pads = _find_stems_by_type(footprints, StemType.pad)
    fx_tracks = _find_stems_by_type(footprints, StemType.fx)
    leads = _find_stems_by_type(footprints, StemType.vocal)

    # Reduce reverb on pads in drop for clarity
    for pad in pads[:2]:
        suggestions.append(
            AutomationSuggestion(
                track=pad,
                parameter="Reverb Send",
                start_bar=start_bar,
                end_bar=start_bar + 1,
                start_value=-6.0,
                end_value=-12.0,
                unit="dB",
                section_type="drop",
                priority=7.0,
                reason=(
                    f"Reduce reverb on '{pad}' during drop — shorter tail = more clarity "
                    "and punch. Too much reverb muddies the low-mid."
                ),
            )
        )

    # Reduce lead/vocal -1 dB in drop for balance (kick/bass dominate)
    for lead in leads[:1]:
        suggestions.append(
            AutomationSuggestion(
                track=lead,
                parameter="Volume",
                start_bar=start_bar,
                end_bar=start_bar + 1,
                start_value=0.0,
                end_value=-1.5,
                unit="dB",
                section_type="drop",
                priority=5.0,
                reason=(
                    f"Ride '{lead}' down 1.5 dB in the drop — kick and bass should "
                    "dominate energy; leads support rather than compete."
                ),
            )
        )

    # FX swell: open a filter on FX tracks at start of drop
    for fx in fx_tracks[:1]:
        suggestions.append(
            AutomationSuggestion(
                track=fx,
                parameter="Filter Cutoff",
                start_bar=start_bar - 2,
                end_bar=start_bar,
                start_value=200.0,
                end_value=8000.0,
                unit="Hz",
                section_type="drop",
                priority=6.0,
                reason=(
                    f"Open filter cutoff on '{fx}' 2 bars before drop peak "
                    "for a classic tension-release sweep."
                ),
            )
        )

    # Bus compressor threshold: tighten for pumping effect on genre == organic house / techno
    if genre.lower() in ("organic house", "melodic techno", "progressive house"):
        suggestions.append(
            AutomationSuggestion(
                track="Drum Bus",
                parameter="Compressor Threshold",
                start_bar=start_bar,
                end_bar=start_bar + 1,
                start_value=-12.0,
                end_value=-18.0,
                unit="dB",
                section_type="drop",
                priority=8.0,
                reason=(
                    "Tighten drum bus compressor threshold in drop for controlled pumping — "
                    "sidechain to kick. Release 2 dB before drop for impact."
                ),
            )
        )

    return suggestions


def _breakdown_automations(
    section: Section,
    footprints: dict[str, StemFootprint],
    bpm: float,
    genre: str,
) -> list[AutomationSuggestion]:
    """Generate automation suggestions for breakdown sections."""
    suggestions: list[AutomationSuggestion] = []
    start_bar = _sec_to_bar(section.start_sec, bpm)
    _sec_to_bar(section.end_sec, bpm)

    pads = _find_stems_by_type(footprints, StemType.pad)
    leads = _find_stems_by_type(footprints, StemType.vocal)

    # More reverb on pads for atmosphere / spaciousness
    for pad in pads[:2]:
        suggestions.append(
            AutomationSuggestion(
                track=pad,
                parameter="Reverb Send",
                start_bar=start_bar,
                end_bar=start_bar + 2,
                start_value=-12.0,
                end_value=-6.0,
                unit="dB",
                section_type="breakdown",
                priority=6.0,
                reason=(
                    f"Open reverb on '{pad}' in breakdown for depth and atmosphere. "
                    "Longer tails signal 'space to breathe'."
                ),
            )
        )

    # Boost lead/vocal +1 dB in breakdown for intimacy
    for lead in leads[:1]:
        suggestions.append(
            AutomationSuggestion(
                track=lead,
                parameter="Volume",
                start_bar=start_bar,
                end_bar=start_bar + 2,
                start_value=0.0,
                end_value=1.0,
                unit="dB",
                section_type="breakdown",
                priority=7.0,
                reason=(
                    f"Boost '{lead}' +1 dB in breakdown — intimate, close feeling. "
                    "Contrast with the drop where it sits back."
                ),
            )
        )

    # Release bus compressor in breakdown
    suggestions.append(
        AutomationSuggestion(
            track="Drum Bus",
            parameter="Compressor Threshold",
            start_bar=start_bar,
            end_bar=start_bar + 1,
            start_value=-18.0,
            end_value=-10.0,
            unit="dB",
            section_type="breakdown",
            priority=5.0,
            reason=(
                "Release drum bus compressor in breakdown — less pumping "
                "creates contrast with the tight drop dynamics."
            ),
        )
    )

    return suggestions


def _buildup_automations(
    section: Section,
    footprints: dict[str, StemFootprint],
    bpm: float,
    genre: str,
) -> list[AutomationSuggestion]:
    """Generate automation suggestions for buildup sections."""
    suggestions: list[AutomationSuggestion] = []
    start_bar = _sec_to_bar(section.start_sec, bpm)
    end_bar = _sec_to_bar(section.end_sec, bpm)
    n_bars = max(1, end_bar - start_bar)

    pads = _find_stems_by_type(footprints, StemType.pad)
    percs = _find_stems_by_type(footprints, StemType.percussion)

    # Filter sweep on pads — gradually open over buildup
    for pad in pads[:1]:
        suggestions.append(
            AutomationSuggestion(
                track=pad,
                parameter="Filter Cutoff",
                start_bar=start_bar,
                end_bar=end_bar,
                start_value=400.0,
                end_value=12000.0,
                unit="Hz",
                section_type="buildup",
                priority=9.0,
                reason=(
                    f"Gradually open filter cutoff on '{pad}' from 400 Hz → 12 kHz "
                    f"over {n_bars} bars — classic buildup tension builder."
                ),
            )
        )

    # Percussion volume ramp up
    for perc in percs[:1]:
        suggestions.append(
            AutomationSuggestion(
                track=perc,
                parameter="Volume",
                start_bar=start_bar,
                end_bar=end_bar,
                start_value=-6.0,
                end_value=0.0,
                unit="dB",
                section_type="buildup",
                priority=7.0,
                reason=(
                    f"Ramp percussion '{perc}' from -6 dB to 0 dB over the buildup — "
                    "adds density and rising energy toward the drop."
                ),
            )
        )

    # Master/mix bus high-pass filter bleed-in: cut sub in early buildup
    suggestions.append(
        AutomationSuggestion(
            track="Mix Bus",
            parameter="High-Pass Cutoff",
            start_bar=start_bar,
            end_bar=end_bar - 1,
            start_value=80.0,
            end_value=20.0,
            unit="Hz",
            section_type="buildup",
            priority=6.0,
            reason=(
                "Sweep the mix bus high-pass from 80 Hz down to 20 Hz before "
                "the drop — releasing sub energy at the peak for maximum impact."
            ),
        )
    )

    return suggestions


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def suggest_automations(
    sections: list[Section],
    stem_footprints: dict[str, StemFootprint],
    genre: str,
    bpm: float = 0.0,
) -> list[AutomationSuggestion]:
    """Generate per-section automation suggestions.

    Args:
        sections:       Detected arrangement sections (from arrangement.detect_sections).
        stem_footprints: Map of track_name → StemFootprint.
        genre:          Genre key for genre-specific suggestions.
        bpm:            Session BPM for bar-accurate start/end bars.
                        If 0, bar numbers will be approximate.

    Returns:
        List of AutomationSuggestion objects sorted by priority descending.
        Empty list if no sections provided.
    """
    if not sections or not stem_footprints:
        return []

    suggestions: list[AutomationSuggestion] = []

    for section in sections:
        stype = section.section_type

        if stype == "drop":
            suggestions.extend(_drop_automations(section, stem_footprints, bpm, genre))
        elif stype == "breakdown":
            suggestions.extend(_breakdown_automations(section, stem_footprints, bpm, genre))
        elif stype == "buildup":
            suggestions.extend(_buildup_automations(section, stem_footprints, bpm, genre))

    suggestions.sort(key=lambda s: s.priority, reverse=True)
    return suggestions
