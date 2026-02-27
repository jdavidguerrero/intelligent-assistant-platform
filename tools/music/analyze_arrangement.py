"""
analyze_arrangement tool — Detect sections and analyse energy flow in an audio file.

Uses librosa-based section detection to identify intro, buildup, drop, breakdown,
outro, and transition segments.  Checks genre conventions for section lengths,
energy contrast, buildup shape, and transition abruptness.

Returns:
    - List of detected sections with start/end time, type, energy, onset density.
    - EnergyFlow summary (drop/breakdown ratio, buildup ascending, abrupt transitions).
    - List of ArrangementProblems with severity and fix suggestions.
"""

from __future__ import annotations

from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult

_SUPPORTED_GENRES = (
    "organic house",
    "melodic techno",
    "deep house",
    "progressive house",
    "afro house",
)


class AnalyzeArrangement(MusicalTool):
    """Detect arrangement sections and analyse energy flow in a mix.

    Identifies intro, buildup, drop, breakdown, outro, and transition sections
    using energy envelope segmentation and onset density.  Checks genre
    conventions (section lengths, energy contrast, buildup shape) and returns
    actionable arrangement problems.

    Use when the user asks to:
        - Analyse the arrangement or structure of a track
        - Check if the arrangement follows genre conventions
        - Find energy contrast issues between sections
        - Identify if sections are too short or transitions are abrupt
        - Get an arrangement score

    Example:
        tool = AnalyzeArrangement()
        result = tool(file_path="/path/to/track.wav", genre="organic house", bpm=124.0)
    """

    @property
    def name(self) -> str:
        return "analyze_arrangement"

    @property
    def description(self) -> str:
        return (
            "Detect arrangement sections (intro, buildup, drop, breakdown, outro, transition) "
            "in an audio file and analyse energy flow. "
            "Checks genre conventions for section lengths, drop-to-breakdown energy contrast, "
            "buildup shape, and transition smoothness. "
            "Returns sections, energy flow summary, arrangement problems, and an arrangement score. "
            "Use when the user asks about track structure, energy flow, or arrangement issues. "
            f"Supported genres: {', '.join(_SUPPORTED_GENRES)}."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="file_path",
                type=str,
                description=(
                    "Absolute path to audio file (mp3, wav, flac, aiff, ogg). "
                    "Must be the real local path."
                ),
                required=True,
            ),
            ToolParameter(
                name="genre",
                type=str,
                description=(
                    f"Genre for convention checking. Options: {', '.join(_SUPPORTED_GENRES)}."
                ),
                required=False,
                default="organic house",
            ),
            ToolParameter(
                name="bpm",
                type=float,
                description=(
                    "Track BPM for bar-length calculation. "
                    "0 = skip bar counting (section lengths in seconds only)."
                ),
                required=False,
                default=0.0,
            ),
            ToolParameter(
                name="duration",
                type=float,
                description="Max seconds of audio to load (default 300.0 for full track).",
                required=False,
                default=300.0,
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """Run the full arrangement analysis pipeline."""
        file_path: str = str(kwargs.get("file_path") or "").strip()
        genre: str = str(kwargs.get("genre") or "organic house").strip().lower()
        bpm: float = float(kwargs.get("bpm") or 0.0)
        duration: float = float(kwargs.get("duration") or 300.0)

        if not file_path:
            return ToolResult(success=False, error="file_path cannot be empty")

        if genre not in _SUPPORTED_GENRES:
            return ToolResult(
                success=False,
                error=f"genre must be one of: {', '.join(_SUPPORTED_GENRES)}",
            )

        # Load audio
        try:
            import librosa  # type: ignore

            y, sr = librosa.load(file_path, sr=None, mono=False, duration=duration)
        except FileNotFoundError:
            return ToolResult(success=False, error=f"File not found: {file_path}")
        except Exception as exc:
            return ToolResult(success=False, error=f"Audio load failed: {exc}")

        # Detect sections
        try:
            from core.mix_analysis.arrangement import (
                analyze_energy_flow,
                check_arrangement_proportions,
                detect_sections,
            )

            sections = detect_sections(y, sr, librosa, bpm=bpm)
            flow = analyze_energy_flow(sections)
            problems = check_arrangement_proportions(sections, genre, bpm=bpm)

        except Exception as exc:
            return ToolResult(success=False, error=f"Arrangement analysis failed: {exc}")

        # Compute arrangement score (0–100)
        # Base: energy_contrast_score (60%) + no-problems penalty (40%)
        problem_penalty = sum(min(10.0, p.severity) * 2.0 for p in problems)
        arrangement_score = max(
            0.0,
            min(100.0, flow.energy_contrast_score * 0.6 + 40.0 - problem_penalty),
        )

        return ToolResult(
            success=True,
            data={
                "sections": [s.as_dict() for s in sections],
                "energy_flow": flow.as_dict(),
                "problems": [p.as_dict() for p in problems],
                "arrangement_score": round(arrangement_score, 1),
                "section_count": len(sections),
                "problem_count": len(problems),
                "genre": genre,
                "bpm": bpm,
                "summary": (
                    f"{len(sections)} sections detected — "
                    f"{flow.drop_count} drop(s), {flow.breakdown_count} breakdown(s), "
                    f"{flow.buildup_count} buildup(s). "
                    f"Energy contrast score: {flow.energy_contrast_score:.0f}/100. "
                    f"Arrangement score: {arrangement_score:.0f}/100."
                ),
            },
            metadata={
                "file": file_path,
                "duration_analysed_sec": duration,
                "section_types": [s.section_type for s in sections],
                "has_regressions": bool(problems),
            },
        )
