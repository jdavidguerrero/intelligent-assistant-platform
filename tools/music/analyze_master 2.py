"""
analyze_master tool — Run mastering-grade loudness and readiness analysis.

Measures:
  - Integrated LUFS (BS.1770-4 gated) — for platform normalization targets
  - Short-term max LUFS (3 s window) — identifies loudest section
  - Momentary max LUFS (400 ms window) — identifies loudest instant
  - True peak with 4x oversampling (ITU-R BS.1770 / BS.1771)
  - Inter-sample peak count — potential D/A clipping detection
  - Section dynamics (intro / build / drop / outro)
  - Spectral balance label (dark → neutral → bright)
  - Master readiness score 0–100 with issue list
  - Suggested mastering chain template for the genre

Requires the audio stack (librosa + soundfile + scipy) to be installed.
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


class AnalyzeMaster(MusicalTool):
    """Run mastering-grade loudness and readiness analysis on an audio file.

    Computes three LUFS windows (integrated/short-term-max/momentary-max),
    true peak with 4x oversampling, inter-sample peak count, per-section
    dynamics, spectral balance, and a readiness score 0–100.

    Also returns the genre-specific mastering chain template.

    Use when the user asks:
        - "Is my track ready to master?"
        - "What's the LUFS of this track?"
        - "Check my true peak level"
        - "Analyse my master for [genre] submission"
        - "What's wrong with my loudness?"

    Example:
        tool = AnalyzeMaster()
        result = tool(file_path="/path/to/master.wav", genre="organic house")
    """

    @property
    def name(self) -> str:
        return "analyze_master"

    @property
    def description(self) -> str:
        return (
            "Run mastering-grade loudness and readiness analysis on an audio file. "
            "Returns integrated LUFS (BS.1770), short-term max LUFS, momentary max LUFS, "
            "true peak (4x oversampling), inter-sample peak count, per-section dynamics, "
            "spectral balance, and a readiness score 0–100 with specific issue descriptions. "
            "Also returns the genre-specific mastering chain template. "
            "Use when the user wants to check if a track is ready to release, "
            "needs LUFS values for platform submission, or wants mastering advice. "
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
                    "Supported: .mp3 .wav .flac .aiff .ogg .m4a — "
                    "must be the REAL absolute path (e.g. /Users/juan/Music/master.wav)."
                ),
                required=True,
            ),
            ToolParameter(
                name="genre",
                type=str,
                description=(
                    "Genre for target comparison and chain template. "
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
                    "Use the full track duration for accurate integrated LUFS."
                ),
                required=False,
                default=180.0,
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """Run mastering analysis pipeline.

        Returns:
            ToolResult.data with keys:
                loudness (dict): lufs_integrated, lufs_short_term_max,
                    lufs_momentary_max, true_peak_db, inter_sample_peaks
                dynamics (dict): crest_factor, sections (list)
                spectral_balance (str): 'dark' / 'neutral' / 'bright' etc.
                readiness_score (float 0-100)
                issues (list[str]): specific issues reducing the score
                mastering_chain (dict): processors for this genre
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
            report = engine.master_analysis(file_path, genre=genre, duration=duration)
        except FileNotFoundError as exc:
            return ToolResult(success=False, error=f"File not found: {exc}")
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))
        except RuntimeError as exc:
            return ToolResult(success=False, error=f"Analysis failed: {exc}")

        master = report.master

        # --- Loudness metrics ---
        loudness_data: dict[str, Any] = {
            "lufs_integrated": round(master.lufs_integrated, 2),
            "lufs_short_term_max": round(master.lufs_short_term_max, 2),
            "lufs_momentary_max": round(master.lufs_momentary_max, 2),
            "true_peak_db": round(master.true_peak_db, 2),
            "inter_sample_peaks": master.inter_sample_peaks,
        }

        # --- Section dynamics ---
        sections_data = [
            {
                "label": s.label,
                "start_sec": round(s.start_sec, 2),
                "rms_db": round(s.rms_db, 2),
                "peak_db": round(s.peak_db, 2),
                "crest_factor_db": round(s.crest_factor, 2),
            }
            for s in master.sections
        ]

        dynamics_data: dict[str, Any] = {
            "crest_factor_db": round(master.crest_factor, 2),
            "sections": sections_data,
        }

        # --- Mastering chain ---
        chain = report.suggested_chain
        processors_data = [
            {
                "name": proc.name,
                "proc_type": proc.proc_type,
                "plugin_primary": proc.plugin_primary,
                "plugin_fallback": proc.plugin_fallback,
                "params": [{"name": p.name, "value": p.value} for p in proc.params],
            }
            for proc in chain.processors
        ]
        chain_data: dict[str, Any] = {
            "genre": chain.genre,
            "stage": chain.stage,
            "description": chain.description,
            "processors": processors_data,
        }

        return ToolResult(
            success=True,
            data={
                "loudness": loudness_data,
                "dynamics": dynamics_data,
                "spectral_balance": master.spectral_balance,
                "readiness_score": master.readiness_score,
                "issues": list(master.issues),
                "mastering_chain": chain_data,
                "genre": report.genre,
                "duration_sec": round(report.duration_sec, 2),
                "sample_rate": report.sample_rate,
            },
            metadata={
                "file": file_path,
                "issue_count": len(master.issues),
                "is_ready": master.readiness_score >= 80.0,
            },
        )
