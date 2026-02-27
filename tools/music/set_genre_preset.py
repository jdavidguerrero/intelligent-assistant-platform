"""set_genre_preset tool — List available genre presets or validate a preset name.

The genre presets are YAML files in core/session_intelligence/genre_presets/.
Pass the preset name to audit_session to activate Layer 3 suggestions.

Use when the user says:
  - "What genre presets are available?"
  - "I want to audit for organic house"
  - "Show me the techno preset"
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult

_PRESETS_DIR: Path = (
    Path(__file__).parent.parent.parent
    / "core"
    / "session_intelligence"
    / "genre_presets"
)


class SetGenrePreset(MusicalTool):
    """List or validate genre presets for the Session Intelligence audit."""

    @property
    def name(self) -> str:
        return "set_genre_preset"

    @property
    def description(self) -> str:
        return (
            "List available genre presets for Session Intelligence Layer 3 (genre suggestions). "
            "Optionally validate a specific genre name and preview its rules. "
            "Pass the returned preset name to audit_session as genre_preset to activate Layer 3."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="genre",
                type=str,
                description=(
                    "Genre preset name to preview (e.g. 'organic_house', 'techno'). "
                    "Leave empty to list all available presets."
                ),
                required=False,
                default="",
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """List presets or preview a specific preset."""
        genre: str = str(kwargs.get("genre", "") or "").strip().lower().replace(" ", "_")

        # Discover available presets
        available: list[str] = []
        if _PRESETS_DIR.exists():
            available = [
                p.stem
                for p in sorted(_PRESETS_DIR.glob("*.yaml"))
                if not p.stem.startswith("_")
            ]

        if not genre:
            return ToolResult(
                success=True,
                data={
                    "available_presets": available,
                    "usage": "Pass one of these names as genre_preset to audit_session or apply_audit_fix.",
                },
            )

        # Preview a specific preset
        normalized = genre.replace(" ", "_")
        preset_path = _PRESETS_DIR / f"{normalized}.yaml"
        if not preset_path.exists():
            return ToolResult(
                success=False,
                error=(
                    f"Preset '{genre}' not found. "
                    f"Available: {', '.join(available) or 'none'}"
                ),
            )

        try:
            import yaml

            with open(preset_path) as f:
                preset = yaml.safe_load(f) or {}
        except Exception as exc:
            return ToolResult(success=False, error=f"Failed to load preset: {exc}")

        return ToolResult(
            success=True,
            data={
                "preset_name": normalized,
                "preset": preset,
                "usage": f"Pass preset_name='{normalized}' to audit_session for Layer 3 suggestions.",
            },
        )
