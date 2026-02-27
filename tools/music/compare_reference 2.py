"""
compare_reference tool — A/B comparison of a mix vs commercial reference tracks.

Compares your track against one or more commercial references across 6 dimensions:
  - Spectral balance (7 bands: sub through air)
  - Stereo image (width delta)
  - Dynamics (crest factor + LRA delta)
  - Tonal character (spectral centroid + tilt delta)
  - Transient character (onset density + sharpness delta)
  - Loudness (integrated LUFS delta)

All spectral comparisons are loudness-normalized (bands relative to overall RMS).
Returns an overall similarity score (0–100%) and a prioritized list of specific
improvements to close the gap between your mix and the reference material.

Use when the user provides a track and reference file(s) and asks:
  - "How does my mix compare to this reference?"
  - "What's different between my track and Nora En Pure's style?"
  - "Compare my mix vs these 3 commercial tracks"
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


class CompareReference(MusicalTool):
    """A/B comparison of your mix against commercial reference tracks.

    Analyzes both your track and the reference(s), then computes 6-dimension
    similarity scores and generates specific improvement recommendations
    (EQ adjustments, stereo widening, compression changes, etc.)

    Use when the user asks to:
        - Compare their mix against a reference track
        - See how their track differs from commercial releases
        - Get a numerical similarity score vs reference material
        - Find what spectral/stereo/dynamic differences exist vs references

    Example:
        tool = CompareReference()
        result = tool(
            file_path="/path/to/my_mix.wav",
            reference_paths=["/path/to/ref1.wav", "/path/to/ref2.wav"],
            genre="organic house"
        )
    """

    @property
    def name(self) -> str:
        return "compare_reference"

    @property
    def description(self) -> str:
        return (
            "Compare a mix against one or more commercial reference tracks across 6 dimensions: "
            "spectral balance, stereo image, dynamics, tonal character, transient character, "
            "and loudness. Returns an overall similarity score (0–100%) and specific "
            "improvement recommendations with concrete values (e.g. 'Cut 2.3 dB in low-mid "
            "band', 'Widen stereo field by 0.12 width units'). "
            "All spectral comparisons are loudness-normalized. "
            "Use when the user provides reference files and asks what to change in their mix. "
            f"Supported genres: {', '.join(_SUPPORTED_GENRES)}."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="file_path",
                type=str,
                description=(
                    "Absolute path to the track under review. "
                    "Must be a real local filesystem path (e.g. /Users/juan/Music/mix.wav)."
                ),
                required=True,
            ),
            ToolParameter(
                name="reference_paths",
                type=list,
                description=(
                    "List of absolute paths to commercial reference tracks. "
                    "Provide 1+ references; 3–5 is recommended for genre-accurate comparison."
                ),
                required=True,
            ),
            ToolParameter(
                name="genre",
                type=str,
                description=(
                    f"Genre for context. Options: {', '.join(_SUPPORTED_GENRES)}. "
                    "Default: 'organic house'."
                ),
                required=False,
                default="organic house",
            ),
            ToolParameter(
                name="duration",
                type=float,
                description="Max seconds of audio to load per file (default 180.0).",
                required=False,
                default=180.0,
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """Run A/B reference comparison and return per-dimension scores + deltas.

        Returns:
            ToolResult.data with keys:
                overall_similarity (float): 0–100% weighted score
                dimensions (list[dict]): 6 dimension scores with descriptions
                band_deltas (list[dict]): per-band spectral deltas
                deltas (list[dict]): prioritized improvement recommendations
                lufs_delta, width_delta, crest_factor_delta (floats)
                num_references, genre
        """
        file_path: str = (kwargs.get("file_path") or "").strip()
        reference_paths: list[str] = kwargs.get("reference_paths") or []
        genre: str = (kwargs.get("genre") or "organic house").strip().lower()
        duration: float = float(kwargs.get("duration") or 180.0)

        if not file_path:
            return ToolResult(success=False, error="file_path cannot be empty")

        if not reference_paths:
            return ToolResult(
                success=False,
                error="reference_paths must contain at least one path",
            )

        if genre not in _SUPPORTED_GENRES:
            return ToolResult(
                success=False,
                error=f"genre must be one of: {', '.join(_SUPPORTED_GENRES)}. Got: {genre!r}",
            )

        try:
            from ingestion.mix_engine import MixAnalysisEngine

            engine = MixAnalysisEngine()
            comparison = engine.compare_to_references_batch(
                file_path,
                list(reference_paths),
                genre,
                duration=duration,
            )
        except FileNotFoundError as exc:
            return ToolResult(success=False, error=f"File not found: {exc}")
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))
        except RuntimeError as exc:
            return ToolResult(success=False, error=f"Analysis failed: {exc}")

        # Serialize dimensions
        dims_out = [
            {
                "name": d.name,
                "score": round(d.score, 1),
                "track_value": d.track_value,
                "ref_value": d.ref_value,
                "unit": d.unit,
                "description": d.description,
            }
            for d in comparison.dimensions
        ]

        # Serialize band deltas (sorted by abs delta descending)
        bands_out = sorted(
            [
                {
                    "band": bd.band,
                    "track_db": round(bd.track_db, 2),
                    "reference_db": round(bd.reference_db, 2),
                    "delta_db": round(bd.delta_db, 2),
                }
                for bd in comparison.band_deltas
            ],
            key=lambda b: abs(b["delta_db"]),
            reverse=True,
        )

        # Serialize deltas
        deltas_out = [
            {
                "dimension": d.dimension,
                "direction": d.direction,
                "magnitude": d.magnitude,
                "unit": d.unit,
                "recommendation": d.recommendation,
                "priority": d.priority,
            }
            for d in comparison.deltas
        ]

        return ToolResult(
            success=True,
            data={
                "overall_similarity": comparison.overall_similarity,
                "dimensions": dims_out,
                "band_deltas": bands_out,
                "deltas": deltas_out,
                "width_delta": comparison.width_delta,
                "crest_factor_delta": comparison.crest_factor_delta,
                "lra_delta": comparison.lra_delta,
                "centroid_delta_hz": comparison.centroid_delta_hz,
                "tilt_delta": comparison.tilt_delta,
                "density_delta": comparison.density_delta,
                "sharpness_delta": comparison.sharpness_delta,
                "lufs_delta": comparison.lufs_delta,
                "lufs_normalization_db": comparison.lufs_normalization_db,
                "genre": comparison.genre,
                "num_references": comparison.num_references,
            },
            metadata={
                "file": file_path,
                "reference_count": len(reference_paths),
                "overall_similarity_pct": comparison.overall_similarity,
                "delta_count": len(deltas_out),
                "needs_attention": comparison.overall_similarity < 70.0,
            },
        )
