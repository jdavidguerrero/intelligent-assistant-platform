"""save_session_patterns tool — Save the current Ableton session as a pattern reference.

Each saved session teaches Layer 2 what your "normal" looks like.
After 3+ sessions, the audit can detect anomalies in your mixing style.

Use when the user says:
  - "Save this session as reference"
  - "Learn from this session"
  - "Remember how this session is mixed"
"""

from __future__ import annotations

from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult

try:
    from ingestion.ableton_bridge import AbletonBridge
except ImportError:
    AbletonBridge = None  # type: ignore[assignment,misc]

try:
    from ingestion.pattern_store import PatternStore
except ImportError:
    PatternStore = None  # type: ignore[assignment,misc]

try:
    from ingestion.session_auditor import SessionAuditor
except ImportError:
    SessionAuditor = None  # type: ignore[assignment,misc]

_WS_HOST: str = "localhost"
_WS_PORT: int = 11005


class SaveSessionPatterns(MusicalTool):
    """Save the current Ableton session as a mixing pattern reference."""

    @property
    def name(self) -> str:
        return "save_session_patterns"

    @property
    def description(self) -> str:
        return (
            "Save the current Ableton Live session as a mixing pattern reference. "
            "Extracts per-channel mixing data (volume levels, HP filter presence, "
            "compression ratios) and appends it to your pattern history. "
            "Layer 2 anomaly detection activates after 3+ saved sessions. "
            "Requires the ALS Listener M4L device loaded in Ableton."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return []  # No parameters needed — reads live session automatically

    def execute(self, **kwargs: Any) -> ToolResult:
        """Read the live session and save patterns."""
        if AbletonBridge is None:
            return ToolResult(success=False, error="AbletonBridge not available")

        try:
            bridge = AbletonBridge(host=_WS_HOST, port=_WS_PORT)
            session = bridge.get_session()
        except ConnectionError as exc:
            return ToolResult(success=False, error=str(exc))
        except Exception as exc:
            return ToolResult(success=False, error=f"Error reading session: {exc}")

        if PatternStore is None or SessionAuditor is None:
            return ToolResult(success=False, error="SessionAuditor or PatternStore not available")

        try:
            store = PatternStore()
            auditor = SessionAuditor(pattern_store=store)
            channels_learned = auditor.save_session_patterns(session)
            sessions_saved = store.get_sessions_saved()
        except Exception as exc:
            return ToolResult(success=False, error=f"Failed to save patterns: {exc}")

        layer2_active = sessions_saved >= 3
        if layer2_active:
            status = "Layer 2 now active — anomaly detection enabled!"
        else:
            remaining = 3 - sessions_saved
            status = f"{sessions_saved}/3 sessions saved. {remaining} more needed for Layer 2."

        return ToolResult(
            success=True,
            data={
                "channels_learned": channels_learned,
                "sessions_saved": sessions_saved,
                "layer_2_active": layer2_active,
                "status": status,
            },
            metadata={"ws_host": _WS_HOST, "ws_port": _WS_PORT},
        )
