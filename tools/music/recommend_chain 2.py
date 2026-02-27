"""
recommend_chain tool — Return a genre-specific signal chain template.

Returns an ordered list of processors for mix bus or mastering, with:
  - Processor name and type (eq, compressor, limiter, saturation, etc.)
  - Primary plugin recommendation (e.g. FabFilter Pro-Q 3)
  - Fallback Ableton-stock plugin (e.g. Ableton EQ Eight)
  - Concrete parameter values (e.g. threshold -8 dBFS, ratio 4:1)

No audio file needed — chain templates are genre-specific defaults loaded
from YAML. Use analyze_mix + recommend_chain together for a full workflow.
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

_SUPPORTED_STAGES = ("mix_bus", "master")


class RecommendChain(MusicalTool):
    """Return a genre-specific signal chain template for mix bus or mastering.

    Each chain is an ordered list of processors with primary (3rd-party) and
    fallback (Ableton-stock) plugin suggestions and concrete parameter values
    that can be dialed in immediately.

    Use when the user asks:
        - "What plugins should I use on my mix bus?"
        - "How should I set up my mastering chain for organic house?"
        - "Give me a signal chain template for [genre]"
        - "What processors should I put on my master?"

    Example:
        tool = RecommendChain()
        result = tool(genre="organic house", stage="mix_bus")
    """

    @property
    def name(self) -> str:
        return "recommend_chain"

    @property
    def description(self) -> str:
        return (
            "Return a genre-specific signal chain template for mix bus or mastering. "
            "Each chain has an ordered list of processors with primary + fallback plugin "
            "suggestions and concrete parameter values (e.g. 'Glue Compressor: ratio 4:1, "
            "attack 30ms, release auto, threshold -8 dBFS'). "
            "Use when the user asks what plugins to use on their mix bus or master chain, "
            "or wants a signal processing starting point for a specific genre. "
            f"Stages: {', '.join(_SUPPORTED_STAGES)}. "
            f"Genres: {', '.join(_SUPPORTED_GENRES)}."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="genre",
                type=str,
                description=(
                    "Genre for the chain template. "
                    f"Options: {', '.join(_SUPPORTED_GENRES)}. "
                    "Default: 'organic house'."
                ),
                required=False,
                default="organic house",
            ),
            ToolParameter(
                name="stage",
                type=str,
                description=(
                    "Processing stage: 'mix_bus' (for the main stereo bus during mixing) "
                    "or 'master' (for the mastering chain). "
                    "Default: 'mix_bus'."
                ),
                required=False,
                default="mix_bus",
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """Load and return the signal chain template.

        Returns:
            ToolResult.data with keys:
                genre (str), stage (str), description (str),
                processors (list[dict]) — ordered list with name, type,
                    plugin_primary, plugin_fallback, params (list[{name, value}])
        """
        genre: str = (kwargs.get("genre") or "organic house").strip().lower()
        stage: str = (kwargs.get("stage") or "mix_bus").strip().lower()

        if genre not in _SUPPORTED_GENRES:
            return ToolResult(
                success=False,
                error=(f"genre must be one of: {', '.join(_SUPPORTED_GENRES)}. " f"Got: {genre!r}"),
            )

        if stage not in _SUPPORTED_STAGES:
            return ToolResult(
                success=False,
                error=(f"stage must be one of: {', '.join(_SUPPORTED_STAGES)}. " f"Got: {stage!r}"),
            )

        try:
            from core.mix_analysis.chains import get_chain

            chain = get_chain(genre, stage)
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))

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

        return ToolResult(
            success=True,
            data={
                "genre": chain.genre,
                "stage": chain.stage,
                "description": chain.description,
                "processors": processors_data,
            },
            metadata={
                "processor_count": len(processors_data),
                "requested_genre": genre,
                "requested_stage": stage,
            },
        )
