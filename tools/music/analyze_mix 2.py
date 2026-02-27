"""
analyze_mix tool — Run a complete mix analysis on an audio file.

Performs mastering-grade mix diagnostics:
  - 7-band spectral balance (sub / low / low-mid / mid / high-mid / high / air)
  - Stereo image (width, L-R correlation, mid-side ratio, per-band width)
  - Dynamics (LUFS, crest factor, LRA, dynamic range)
  - Transient analysis (onset density, attack sharpness)
  - Genre-aware problem detection (muddiness, harshness, boominess, etc.)
  - Prescriptive recommendations with specific DSP parameters

Requires the audio stack (librosa + soundfile + scipy) to be installed.
The file must be a real absolute path on the local filesystem.
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


class AnalyzeMix(MusicalTool):
    """Run a complete mix analysis on an audio file.

    Analyses the mix across four dimensions:
        1. Spectral balance — 7 frequency bands + centroid + tilt
        2. Stereo image — width, correlation, mid-side ratio
        3. Dynamics — LUFS (BS.1770), crest factor, LRA, dynamic range
        4. Transients — onset density, attack sharpness

    Then runs genre-aware problem detection and generates prescriptive
    recommendations with specific DSP parameter values (e.g.
    "Cut 3.1 dB at 280 Hz Q=2.0 on pad bus — FabFilter Pro-Q 3").

    Use when the user asks to:
        - Analyse a mix or audio file
        - Find what's wrong with a mix
        - Get mixing advice for a track
        - Check if a mix is ready for mastering

    Example:
        tool = AnalyzeMix()
        result = tool(file_path="/path/to/track.wav", genre="organic house")
    """

    @property
    def name(self) -> str:
        return "analyze_mix"

    @property
    def description(self) -> str:
        return (
            "Analyse an audio file for mix quality across spectral balance, stereo image, "
            "dynamics, and transients. Detects mix problems (muddiness, harshness, boominess, "
            "thinness, narrow stereo, phase issues, over/under compression) and returns "
            "prescriptive recommendations with specific DSP parameter values. "
            "Use when the user provides an audio file and asks for mixing advice, mix diagnostics, "
            "or wants to know what to fix in their mix. "
            f"Supported genres: {', '.join(_SUPPORTED_GENRES)}."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="file_path",
                type=str,
                description=(
                    "Absolute path to audio file on local filesystem. "
                    "Supported formats: .mp3 .wav .flac .aiff .ogg .m4a — "
                    "must be the REAL absolute path (e.g. /Users/juan/Music/track.wav)."
                ),
                required=True,
            ),
            ToolParameter(
                name="genre",
                type=str,
                description=(
                    "Genre for target comparison. "
                    f"Options: {', '.join(_SUPPORTED_GENRES)}. "
                    "Default: 'organic house'."
                ),
                required=False,
                default="organic house",
            ),
            ToolParameter(
                name="duration",
                type=float,
                description=(
                    "Max seconds of audio to load (default 180.0). "
                    "Use higher values for longer tracks."
                ),
                required=False,
                default=180.0,
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """Run the complete mix analysis pipeline.

        Returns:
            ToolResult.data with keys:
                spectral (dict): band levels + centroid + tilt + flatness
                stereo  (dict | None): width, correlation, mid-side ratio
                dynamics (dict): LUFS, crest factor, LRA, dynamic range
                transients (dict): density, sharpness, attack_ratio
                problems (list[dict]): detected issues sorted by severity
                recommendations (list[dict]): prescriptive fixes with params
                genre, duration_sec, sample_rate
        """
        file_path: str = (kwargs.get("file_path") or "").strip()
        genre: str = (kwargs.get("genre") or "organic house").strip().lower()
        duration: float = float(kwargs.get("duration") or 180.0)

        if not file_path:
            return ToolResult(success=False, error="file_path cannot be empty")

        if genre not in _SUPPORTED_GENRES:
            return ToolResult(
                success=False,
                error=(f"genre must be one of: {', '.join(_SUPPORTED_GENRES)}. " f"Got: {genre!r}"),
            )

        try:
            from ingestion.mix_engine import MixAnalysisEngine

            engine = MixAnalysisEngine()
            report = engine.full_mix_analysis(file_path, genre=genre, duration=duration)
        except FileNotFoundError as exc:
            return ToolResult(success=False, error=f"File not found: {exc}")
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))
        except RuntimeError as exc:
            return ToolResult(success=False, error=f"Analysis failed: {exc}")

        # --- Serialize spectral ---
        spectral_data: dict[str, Any] = {
            "bands": report.frequency.bands.as_dict(),
            "spectral_centroid_hz": round(report.frequency.spectral_centroid, 1),
            "spectral_tilt_db_oct": round(report.frequency.spectral_tilt, 2),
            "spectral_flatness": round(report.frequency.spectral_flatness, 4),
            "overall_rms_db": round(report.frequency.overall_rms_db, 2),
        }

        # --- Serialize stereo ---
        stereo_data: dict[str, Any] | None = None
        if report.stereo is not None and not report.stereo.is_mono:
            stereo_data = {
                "width": round(report.stereo.width, 3),
                "lr_correlation": round(report.stereo.lr_correlation, 3),
                "mid_side_ratio_db": round(report.stereo.mid_side_ratio, 2),
                "band_widths": report.stereo.band_widths.as_dict(),
            }

        # --- Serialize dynamics ---
        dynamics_data: dict[str, Any] = {
            "lufs": round(report.dynamics.lufs, 2),
            "rms_db": round(report.dynamics.rms_db, 2),
            "peak_db": round(report.dynamics.peak_db, 2),
            "crest_factor_db": round(report.dynamics.crest_factor, 2),
            "dynamic_range_db": round(report.dynamics.dynamic_range, 2),
            "loudness_range_lu": round(report.dynamics.loudness_range, 2),
        }

        # --- Serialize transients ---
        transients_data: dict[str, Any] = {
            "onset_density_per_sec": round(report.transients.density, 3),
            "attack_sharpness": round(report.transients.sharpness, 3),
            "attack_ratio": round(report.transients.attack_ratio, 3),
        }

        # --- Serialize problems ---
        problems_data = [
            {
                "category": p.category,
                "severity": p.severity,
                "frequency_range_hz": list(p.frequency_range),
                "description": p.description,
                "recommendation": p.recommendation,
            }
            for p in report.problems
        ]

        # --- Serialize recommendations ---
        recs_data = []
        for r in report.recommendations:
            steps_data = []
            for step in r.steps:
                steps_data.append(
                    {
                        "action": step.action,
                        "bus": step.bus,
                        "plugin_primary": step.plugin_primary,
                        "plugin_fallback": step.plugin_fallback,
                        "params": [{"name": p.name, "value": p.value} for p in step.params],
                    }
                )
            rec_dict: dict[str, Any] = {
                "problem_category": r.problem_category,
                "severity": r.severity,
                "summary": r.summary,
                "steps": steps_data,
                "rag_query": r.rag_query,
            }
            if r.rag_citations:
                rec_dict["citations"] = list(r.rag_citations)
            recs_data.append(rec_dict)

        return ToolResult(
            success=True,
            data={
                "spectral": spectral_data,
                "stereo": stereo_data,
                "dynamics": dynamics_data,
                "transients": transients_data,
                "problems": problems_data,
                "recommendations": recs_data,
                "genre": report.genre,
                "duration_sec": round(report.duration_sec, 2),
                "sample_rate": report.sample_rate,
            },
            metadata={
                "file": file_path,
                "problem_count": len(problems_data),
                "recommendation_count": len(recs_data),
                "is_mono": report.stereo is None or report.stereo.is_mono,
            },
        )
