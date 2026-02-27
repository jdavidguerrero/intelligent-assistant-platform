"""
mix_master_report tool — Full diagnostic report: mix + master + optional reference.

Generates a structured, section-by-section mix and master diagnostic report
combining all Week 16–18 analysis modules into a single coherent output:

  1. Executive Summary    — Health score, verdict, top 3–5 priorities
  2. Frequency Analysis   — 7-band balance with specific dB values
  3. Stereo Analysis      — Width, correlation, phase, per-band widths
  4. Dynamics Analysis    — LUFS, crest factor, LRA, dynamic range
  5. Problems & Fixes     — All detected problems with specific DSP parameters
  6. Reference Comparison — Per-dimension deltas vs references (if provided)
  7. Signal Chain         — Genre-specific mix-bus processor chain
  8. Master Readiness     — LUFS, true peak, readiness score, issues

This is the most comprehensive single-call analysis available.
Use when the user wants a complete picture of their mix's technical quality.
"""

from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult

_SUPPORTED_GENRES = (
    "organic house",
    "melodic techno",
    "deep house",
    "progressive house",
    "afro house",
)


class MixMasterReport(MusicalTool):
    """Generate a complete mix + master diagnostic report.

    The most comprehensive analysis tool — runs all analysis modules and
    generates a structured, section-by-section report with an overall health
    score (0–100) and prioritized improvement list.

    Optionally compare against commercial references to enrich the report
    with A/B deltas and a reference similarity score.

    Use when the user asks for:
        - A complete mix analysis and report
        - A full diagnostic of their track
        - Mix + master analysis in one call
        - "What's wrong with my mix and how do I fix it?"
        - "Is my track ready for release?"

    Example:
        tool = MixMasterReport()
        result = tool(
            file_path="/path/to/track.wav",
            genre="organic house",
            reference_paths=["/path/to/ref.wav"]
        )
    """

    @property
    def name(self) -> str:
        return "mix_master_report"

    @property
    def description(self) -> str:
        return (
            "Generate a complete mix + master diagnostic report. "
            "Combines spectral analysis (7 bands), stereo image, dynamics (LUFS/crest/LRA), "
            "transient analysis, problem detection, prescriptive recommendations, mastering "
            "analysis (true peak, readiness score), and optional reference comparison. "
            "Returns a structured report with 6–8 sections, an overall health score (0–100), "
            "and the top 3–5 most impactful improvements. "
            "Use when the user wants a complete picture of their mix's technical quality "
            "or asks if their track is ready for release. "
            f"Supported genres: {', '.join(_SUPPORTED_GENRES)}."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="file_path",
                type=str,
                description=(
                    "Absolute path to the audio file to analyze. "
                    "Must be a real local filesystem path (e.g. /Users/juan/Music/track.wav)."
                ),
                required=True,
            ),
            ToolParameter(
                name="genre",
                type=str,
                description=(
                    f"Genre for target comparison. Options: {', '.join(_SUPPORTED_GENRES)}. "
                    "Default: 'organic house'."
                ),
                required=False,
                default="organic house",
            ),
            ToolParameter(
                name="reference_paths",
                type=list,
                description=(
                    "Optional list of commercial reference track paths. "
                    "If provided, adds a Reference Comparison section to the report."
                ),
                required=False,
                default=None,
            ),
            ToolParameter(
                name="include_master",
                type=bool,
                description=(
                    "Run mastering analysis (adds Master Readiness section). " "Default: True."
                ),
                required=False,
                default=True,
            ),
            ToolParameter(
                name="duration",
                type=float,
                description="Max seconds of audio to load (default 180.0).",
                required=False,
                default=180.0,
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """Generate the full diagnostic report.

        Returns:
            ToolResult.data with keys:
                overall_health_score (float): 0–100
                top_priorities (list[str]): top 3–5 improvement actions
                genre, duration_sec
                sections (dict): each section with title/severity/summary/points
                mix_analysis (dict): full mix analysis data
                master_analysis (dict | None): mastering data if requested
                reference_comparison (dict | None): A/B data if references provided
        """
        file_path: str = (kwargs.get("file_path") or "").strip()
        genre: str = (kwargs.get("genre") or "organic house").strip().lower()
        reference_paths: list[str] | None = kwargs.get("reference_paths") or None
        include_master: bool = bool(kwargs.get("include_master", True))
        duration: float = float(kwargs.get("duration") or 180.0)

        if not file_path:
            return ToolResult(success=False, error="file_path cannot be empty")

        if genre not in _SUPPORTED_GENRES:
            return ToolResult(
                success=False,
                error=f"genre must be one of: {', '.join(_SUPPORTED_GENRES)}. Got: {genre!r}",
            )

        try:
            from ingestion.mix_engine import MixAnalysisEngine

            engine = MixAnalysisEngine()
            full = engine.full_mix_report(
                file_path,
                genre,
                reference_paths=list(reference_paths) if reference_paths else None,
                include_master=include_master,
                duration=duration,
            )
        except FileNotFoundError as exc:
            return ToolResult(success=False, error=f"File not found: {exc}")
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))
        except RuntimeError as exc:
            return ToolResult(success=False, error=f"Report generation failed: {exc}")

        # Serialize sections
        def _sec(s: Any) -> dict[str, Any]:
            return {
                "title": s.title,
                "severity": s.severity,
                "summary": s.summary,
                "points": list(s.points),
                "confidence": s.confidence,
            }

        sections: dict[str, Any] = {
            "executive_summary": _sec(full.executive_summary),
            "frequency_analysis": _sec(full.frequency_analysis),
            "stereo_analysis": _sec(full.stereo_analysis),
            "dynamics_analysis": _sec(full.dynamics_analysis),
            "problems_and_fixes": _sec(full.problems_and_fixes),
            "signal_chain": _sec(full.signal_chain_section),
        }
        if full.reference_section is not None:
            sections["reference_comparison"] = _sec(full.reference_section)
        if full.master_readiness_section is not None:
            sections["master_readiness"] = _sec(full.master_readiness_section)

        # Minimal mix analysis summary (avoid duplicating huge data)
        mix = full.mix_report
        mix_summary = {
            "lufs": round(mix.dynamics.lufs, 2),
            "crest_factor_db": round(mix.dynamics.crest_factor, 2),
            "width": round(mix.stereo.width, 3) if mix.stereo and not mix.stereo.is_mono else None,
            "centroid_hz": round(mix.frequency.spectral_centroid, 0),
            "tilt_db_oct": round(mix.frequency.spectral_tilt, 2),
            "problem_count": len(mix.problems),
            "recommendation_count": len(mix.recommendations),
        }

        data: dict[str, Any] = {
            "overall_health_score": full.overall_health_score,
            "top_priorities": list(full.top_priorities),
            "genre": full.genre,
            "duration_sec": round(full.duration_sec, 2),
            "sections": sections,
            "mix_summary": mix_summary,
        }

        # Reference comparison summary
        if full.reference_comparison is not None:
            rc = full.reference_comparison
            data["reference_similarity"] = rc.overall_similarity
            data["reference_deltas"] = [
                {
                    "dimension": d.dimension,
                    "direction": d.direction,
                    "magnitude": d.magnitude,
                    "unit": d.unit,
                    "recommendation": d.recommendation,
                    "priority": d.priority,
                }
                for d in rc.deltas[:5]
            ]

        # Master analysis summary
        if full.master_report is not None:
            m = full.master_report.master
            data["master_summary"] = {
                "readiness_score": round(m.readiness_score, 1),
                "lufs_integrated": round(m.lufs_integrated, 2),
                "true_peak_db": round(m.true_peak_db, 2),
                "issue_count": len(m.issues),
            }

        return ToolResult(
            success=True,
            data=data,
            metadata={
                "file": file_path,
                "health_score": full.overall_health_score,
                "section_count": len(sections),
                "has_reference_comparison": full.reference_comparison is not None,
                "has_master_analysis": full.master_report is not None,
                "is_healthy": full.overall_health_score >= 75.0,
            },
        )
