"""get_my_patterns tool — Show the user's learned mixing patterns.

Returns the per-instrument pattern history used by Layer 2 of the audit system.

Use when the user says:
  - "What are my mixing habits?"
  - "Show me my patterns"
  - "How do I usually mix pads?"
"""

from __future__ import annotations

from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult

try:
    from ingestion.pattern_store import PatternStore
except ImportError:
    PatternStore = None  # type: ignore[assignment,misc]


class GetMyPatterns(MusicalTool):
    """Show the user's learned mixing patterns for Layer 2 anomaly detection."""

    @property
    def name(self) -> str:
        return "get_my_patterns"

    @property
    def description(self) -> str:
        return (
            "Show your learned mixing patterns — the historical data used by the Session Audit "
            "to detect anomalies (Layer 2). Shows per-instrument-type distributions of volume, "
            "HP filter presence, and compression ratio across your saved sessions. "
            "Layer 2 activates after 3+ saved sessions."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="instrument_type",
                type=str,
                description="Filter to a specific instrument type (e.g. 'pad', 'kick', 'bass'). Leave empty for all.",
                required=False,
                default="",
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """Return the stored pattern history."""
        instrument_filter: str = str(kwargs.get("instrument_type", "") or "").strip().lower()

        if PatternStore is None:
            return ToolResult(success=False, error="PatternStore not available")

        try:
            store = PatternStore()
            data = store.load()
        except Exception as exc:
            return ToolResult(success=False, error=f"Failed to load patterns: {exc}")

        sessions_saved: int = data.get("sessions_saved", 0)
        patterns: dict[str, Any] = data.get("patterns", {})

        if instrument_filter:
            patterns = {k: v for k, v in patterns.items() if instrument_filter in k}

        if sessions_saved < 3:
            status_msg = (
                f"Layer 2 not yet active. {sessions_saved}/3 sessions saved. "
                "Use save_session_patterns to build your pattern history."
            )
        else:
            status_msg = (
                f"Layer 2 active. {sessions_saved} sessions saved. "
                f"{len(patterns)} instrument types tracked."
            )

        return ToolResult(
            success=True,
            data={
                "sessions_saved": sessions_saved,
                "layer_2_active": sessions_saved >= 3,
                "status": status_msg,
                "patterns": patterns,
                "instrument_types": list(patterns.keys()),
            },
            metadata={"instrument_filter": instrument_filter or None},
        )
