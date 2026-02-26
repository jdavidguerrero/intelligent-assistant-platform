"""
calibrate_genre_targets tool — Derive genre mix targets from reference analysis.

Analyzes N commercial reference tracks from a target genre and computes
mean ± std for 16 mix metrics. The result is a data-driven GenreTarget that
replaces manually authored YAML files with real statistical evidence.

Use-case: "I have 10 Organic House tracks I love. What are their average
spectral balance, stereo width, LUFS, and crest factor? Use that as my target."

The output dict is compatible with the genre_targets/ YAML format, so it can
be used directly as a reference target or saved to update production targets.
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


class CalibrateGenreTargets(MusicalTool):
    """Calibrate genre mix targets from commercial reference tracks.

    Analyzes a set of reference tracks and computes mean ± standard deviation
    for 16 mix metrics. The acceptable range for each metric is [mean − σ, mean + σ].

    The output is a GenreTarget dict that is compatible with the genre_targets/
    YAML format used internally by the problem detection and mastering analysis
    modules.

    Use when the user asks to:
        - Create custom genre targets from reference tracks
        - Calibrate targets from their favorite releases
        - Generate data-driven mixing targets
        - "Analyze 10 Organic House tracks and derive what's typical for the genre"

    Minimum 2 references required; recommend 10+ for statistical validity.

    Example:
        tool = CalibrateGenreTargets()
        result = tool(
            reference_paths=["/path/ref1.wav", "/path/ref2.wav"],
            genre="organic house"
        )
    """

    @property
    def name(self) -> str:
        return "calibrate_genre_targets"

    @property
    def description(self) -> str:
        return (
            "Analyze N commercial reference tracks and derive calibrated genre mix targets. "
            "Computes mean ± standard deviation for 16 mix metrics: 7 spectral bands, "
            "centroid, spectral tilt, stereo width, LUFS, crest factor, LRA, transient "
            "density, and attack sharpness. The output replaces manually authored genre "
            "targets with data-driven statistics from real commercial releases. "
            "Requires minimum 2 references; 10+ recommended for statistical validity. "
            "Use when the user wants to create custom genre targets from their favorite "
            "commercial tracks or calibrate mixing targets from real reference material. "
            f"Supported genres: {', '.join(_SUPPORTED_GENRES)}."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="reference_paths",
                type=list,
                description=(
                    "List of absolute paths to commercial reference tracks. "
                    "Minimum 2 required; 10+ recommended for meaningful statistics. "
                    "All tracks should be from the target genre."
                ),
                required=True,
            ),
            ToolParameter(
                name="genre",
                type=str,
                description=(
                    f"Target genre for the calibrated targets. "
                    f"Options: {', '.join(_SUPPORTED_GENRES)}."
                ),
                required=True,
            ),
            ToolParameter(
                name="duration",
                type=float,
                description="Max seconds of audio to load per reference (default 180.0).",
                required=False,
                default=180.0,
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """Analyze references and return calibrated GenreTarget.

        Returns:
            ToolResult.data with keys matching target_to_dict() output:
                genre (str)
                num_references (int)
                bands (dict): per-band mean/std
                tonal (dict): centroid_hz and tilt_db_oct mean/std
                stereo (dict): width mean/std
                dynamics (dict): lufs, crest_factor_db, lra_lu mean/std
                transients (dict): density and sharpness mean/std
        """
        reference_paths: list[str] = kwargs.get("reference_paths") or []
        genre: str = (kwargs.get("genre") or "").strip().lower()
        duration: float = float(kwargs.get("duration") or 180.0)

        if not reference_paths:
            return ToolResult(
                success=False,
                error="reference_paths must not be empty",
            )

        if len(reference_paths) < 2:
            return ToolResult(
                success=False,
                error=(
                    f"calibrate_genre_targets requires at least 2 reference paths, "
                    f"got {len(reference_paths)}. Provide at least 5 for meaningful targets."
                ),
            )

        if not genre:
            return ToolResult(success=False, error="genre cannot be empty")

        if genre not in _SUPPORTED_GENRES:
            return ToolResult(
                success=False,
                error=f"genre must be one of: {', '.join(_SUPPORTED_GENRES)}. Got: {genre!r}",
            )

        try:
            from ingestion.mix_engine import MixAnalysisEngine

            engine = MixAnalysisEngine()
            target = engine.calibrate_targets(
                list(reference_paths),
                genre,
                duration=duration,
            )
        except FileNotFoundError as exc:
            return ToolResult(success=False, error=f"File not found: {exc}")
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))
        except RuntimeError as exc:
            return ToolResult(success=False, error=f"Calibration failed: {exc}")

        # Serialize via calibration module
        from core.mix_analysis.calibration import target_to_dict

        target_dict = target_to_dict(target)

        return ToolResult(
            success=True,
            data=target_dict,
            metadata={
                "genre": genre,
                "num_references": len(reference_paths),
                "reference_paths": reference_paths,
                "metrics_calibrated": 16,
            },
        )
