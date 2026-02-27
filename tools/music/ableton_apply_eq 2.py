"""ableton_apply_eq tool — Apply an EQ Eight band adjustment in Ableton Live.

High-level EQ tool: given a track name and band parameters in musical units
(Hz, dB), it:
  1. Reads the session to locate the track and its EQ Eight device
  2. Converts human values (Hz, dB, Q) to Ableton raw values
  3. Sends up to 3 LOM commands (frequency, gain, Q) in a single batch

Use when the user or copilot says:
  - "Cut 3 dB at 280 Hz on the Pads track"
  - "Add a high shelf boost at 10 kHz on the master"
  - "Notch out the resonance at 800 Hz on the synth track"
  - "Apply the EQ fix: band 3, -4 dB at 320 Hz, Q=1.5"
"""

from __future__ import annotations

from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult

_WS_HOST: str = "localhost"
_WS_PORT: int = 11005

_SUPPORTED_FILTER_TYPES: dict[str, int] = {
    "lp48": 0,
    "lp12": 1,
    "lowpass": 0,
    "low_shelf": 2,
    "lowshelf": 2,
    "ls": 2,
    "bell": 3,
    "peak": 3,
    "notch": 4,
    "high_shelf": 5,
    "highshelf": 5,
    "hs": 5,
    "hp12": 6,
    "highpass": 6,
    "hp48": 7,
}


class AbletonApplyEQ(MusicalTool):
    """Apply a band adjustment to the EQ Eight on a track in Ableton Live."""

    @property
    def name(self) -> str:
        return "ableton_apply_eq"

    @property
    def description(self) -> str:
        return (
            "Apply an EQ Eight band adjustment on a specific Ableton track. "
            "Specify the track, band number (1-8), frequency (Hz), gain (dB), "
            "and optional Q factor. "
            "Requires the ALS Listener M4L device loaded in Ableton."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="track_name",
                type=str,
                description="Track name (case-insensitive, e.g. 'Pads', 'Bass', 'Master').",
            ),
            ToolParameter(
                name="band",
                type=int,
                description="EQ Eight band number, 1–8 (Band A–H). Band 1 = lowest, Band 8 = highest.",
            ),
            ToolParameter(
                name="freq_hz",
                type=float,
                description="Centre frequency in Hz (20–20000). E.g. 280.0 for low-mid mud range.",
            ),
            ToolParameter(
                name="gain_db",
                type=float,
                description="Gain adjustment in dB (–15 to +15). Negative = cut, positive = boost.",
            ),
            ToolParameter(
                name="q",
                type=float,
                description="Q factor (bandwidth) — 0.1 (wide) to 10 (narrow). Default: 1.0",
                required=False,
                default=1.0,
            ),
            ToolParameter(
                name="filter_type",
                type=str,
                description=(
                    "Filter type: bell (default), low_shelf, high_shelf, notch, lp12, lp48, hp12, hp48. "
                    "Leave empty to keep current type."
                ),
                required=False,
                default="",
            ),
            ToolParameter(
                name="enabled",
                type=bool,
                description="Enable or disable this band. Default: True (enable).",
                required=False,
                default=True,
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """Locate EQ Eight on track and apply the band adjustment."""
        track_name: str = str(kwargs.get("track_name", "")).strip()
        band: int = int(kwargs.get("band", 3))
        freq_hz: float = float(kwargs.get("freq_hz", 1000.0))
        gain_db: float = float(kwargs.get("gain_db", 0.0))
        q: float = float(kwargs.get("q", 1.0))
        filter_type_str: str = str(kwargs.get("filter_type", "") or "").strip().lower()
        enabled: bool = bool(kwargs.get("enabled", True))

        # Validate
        if not track_name:
            return ToolResult(success=False, error="track_name is required")
        if not 1 <= band <= 8:
            return ToolResult(success=False, error=f"band must be 1–8, got {band}")
        if not 20 <= freq_hz <= 20_000:
            return ToolResult(success=False, error=f"freq_hz must be 20–20000, got {freq_hz}")
        if not -15 <= gain_db <= 15:
            return ToolResult(success=False, error=f"gain_db must be –15 to +15, got {gain_db}")
        if not 0.1 <= q <= 10:
            return ToolResult(success=False, error=f"q must be 0.1–10, got {q}")

        filter_type_int: int | None = None
        if filter_type_str:
            if filter_type_str not in _SUPPORTED_FILTER_TYPES:
                return ToolResult(
                    success=False,
                    error=f"Unknown filter type {filter_type_str!r}. Valid: {sorted(_SUPPORTED_FILTER_TYPES)}",
                )
            filter_type_int = _SUPPORTED_FILTER_TYPES[filter_type_str]

        try:
            from ingestion.ableton_bridge import AbletonBridge
        except ImportError as exc:
            return ToolResult(success=False, error=f"Import error: {exc}")

        try:
            bridge = AbletonBridge(host=_WS_HOST, port=_WS_PORT)
            session = bridge.get_session()
        except ConnectionError as exc:
            return ToolResult(success=False, error=str(exc))

        try:
            from core.ableton.commands import set_eq_band
            from core.ableton.session import find_eq, find_track

            track = find_track(session, track_name)
            eq_device = find_eq(track)

            cmds = set_eq_band(
                track,
                eq_device,
                band=band,
                freq_hz=freq_hz,
                gain_db=gain_db,
                q=q,
                filter_type=filter_type_int,
                enabled=enabled,
            )
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))

        try:
            acks = bridge.send_commands(cmds)
        except (ConnectionError, ValueError) as exc:
            return ToolResult(success=False, error=str(exc))
        except Exception as exc:
            return ToolResult(success=False, error=f"Failed to send EQ commands: {exc}")

        return ToolResult(
            success=True,
            data={
                "track": track.name,
                "device": eq_device.name,
                "band": band,
                "freq_hz": freq_hz,
                "gain_db": gain_db,
                "q": q,
                "filter_type": filter_type_str or "unchanged",
                "enabled": enabled,
                "commands_sent": len(cmds),
                "acks": acks,
            },
            metadata={
                "ws_host": _WS_HOST,
                "ws_port": _WS_PORT,
                "lom_path": eq_device.lom_path,
            },
        )
