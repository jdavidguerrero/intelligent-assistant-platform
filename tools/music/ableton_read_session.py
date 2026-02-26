"""ableton_read_session tool — Read the current Ableton Live session state.

Returns a structured summary of all tracks, their devices, and key parameters.
Uses the ALS Listener M4L device (WebSocket port 11005).

Use when the user asks:
  - "What tracks do I have in my session?"
  - "What plugins are on the Pads track?"
  - "Show me the session overview"
  - "Which tracks have a compressor?"
"""

from __future__ import annotations

from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult

_WS_HOST: str = "localhost"
_WS_PORT: int = 11005


class AbletonReadSession(MusicalTool):
    """Read the current Ableton Live session state via ALS Listener."""

    @property
    def name(self) -> str:
        return "ableton_read_session"

    @property
    def description(self) -> str:
        return (
            "Read the current Ableton Live session state. "
            "Returns tracks, devices, parameters, and playback status. "
            "Requires the ALS Listener M4L device loaded in Ableton."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="track_filter",
                type=str,
                description="Optional: filter results to a specific track name (case-insensitive substring match). Leave empty for full session.",
                required=False,
                default="",
            ),
            ToolParameter(
                name="include_parameters",
                type=bool,
                description="Include full parameter lists for each device (default False — only device names).",
                required=False,
                default=False,
            ),
            ToolParameter(
                name="force_refresh",
                type=bool,
                description="Bypass the session cache and fetch live data from Ableton.",
                required=False,
                default=False,
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """Fetch and return the session state summary."""
        track_filter: str = str(kwargs.get("track_filter", "") or "").strip()
        include_parameters: bool = bool(kwargs.get("include_parameters", False))
        force_refresh: bool = bool(kwargs.get("force_refresh", False))

        try:
            from ingestion.ableton_bridge import AbletonBridge
        except ImportError as exc:
            return ToolResult(success=False, error=f"Import error: {exc}")

        try:
            bridge = AbletonBridge(host=_WS_HOST, port=_WS_PORT)
            session = bridge.get_session(force_refresh=force_refresh)
        except ConnectionError as exc:
            return ToolResult(success=False, error=str(exc))
        except Exception as exc:
            return ToolResult(success=False, error=f"Unexpected error reading session: {exc}")

        # Build response
        from core.ableton.session import session_summary

        summary = session_summary(session)

        if track_filter:
            needle = track_filter.lower()
            summary["tracks"] = [t for t in summary["tracks"] if needle in t["name"].lower()]
            summary["return_tracks"] = [
                t for t in summary["return_tracks"] if needle in t["name"].lower()
            ]

        if include_parameters:
            # Enrich with per-device parameter details
            for track_info in summary["tracks"]:
                track_idx = track_info["index"]
                if track_idx < len(session.tracks):
                    track = session.tracks[track_idx]
                    track_info["devices"] = [
                        {
                            "name": d.name,
                            "class_name": d.class_name,
                            "is_active": d.is_active,
                            "parameters": [
                                {"name": p.name, "value": p.value, "display": p.display_value}
                                for p in d.parameters[:30]  # cap at 30 for readability
                            ],
                        }
                        for d in track.devices
                    ]

        return ToolResult(
            success=True,
            data=summary,
            metadata={
                "ws_host": _WS_HOST,
                "ws_port": _WS_PORT,
                "track_count": len(session.tracks),
                "tempo": session.tempo,
            },
        )
