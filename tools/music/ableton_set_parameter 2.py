"""ableton_set_parameter tool — Set a device parameter in Ableton Live.

Low-level tool for direct parameter writes via LOM path or by name.
Prefer the higher-level ableton_apply_eq and ableton_apply_mix_fix tools
for common operations; use this when you need precise control over any
device parameter.

Use when the user asks:
  - "Set the reverb wet/dry to 40% on the Pads track"
  - "Change the delay feedback to 65"
  - "Set the filter cutoff on the bass to 2 kHz"
"""

from __future__ import annotations

from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult

_WS_HOST: str = "localhost"
_WS_PORT: int = 11005


class AbletonSetParameter(MusicalTool):
    """Set a device parameter on a specific track in Ableton Live."""

    @property
    def name(self) -> str:
        return "ableton_set_parameter"

    @property
    def description(self) -> str:
        return (
            "Set a specific device parameter in Ableton Live. "
            "Specify the track name, device name or class, parameter name, and new value. "
            "Requires the ALS Listener M4L device loaded in Ableton."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="track_name",
                type=str,
                description="Track name (case-insensitive substring match, e.g. 'Pads', 'Kick').",
            ),
            ToolParameter(
                name="device_name",
                type=str,
                description="Device name or class_name (e.g. 'EQ Eight', 'Compressor2', 'Utility').",
            ),
            ToolParameter(
                name="parameter_name",
                type=str,
                description="Parameter display name (e.g. 'Threshold', 'EqFrequency3', 'Stereo Width').",
            ),
            ToolParameter(
                name="value",
                type=float,
                description="New raw parameter value (0.0–1.0 for most parameters, or integer for quantized).",
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """Find the parameter and send the set_parameter command."""
        track_name: str = str(kwargs.get("track_name", "")).strip()
        device_name: str = str(kwargs.get("device_name", "")).strip()
        param_name: str = str(kwargs.get("parameter_name", "")).strip()
        raw_value: float = float(kwargs.get("value", 0.0))

        if not track_name:
            return ToolResult(success=False, error="track_name is required")
        if not device_name:
            return ToolResult(success=False, error="device_name is required")
        if not param_name:
            return ToolResult(success=False, error="parameter_name is required")

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
            from core.ableton.commands import set_parameter
            from core.ableton.session import find_device, find_parameter, find_track

            track = find_track(session, track_name)
            device = find_device(track, name=device_name)
            param = find_parameter(device, param_name)
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))

        try:
            cmd = set_parameter(param, raw_value)
            ack = bridge.send_command(cmd)
        except (ConnectionError, ValueError) as exc:
            return ToolResult(success=False, error=str(exc))
        except Exception as exc:
            return ToolResult(success=False, error=f"Failed to send command: {exc}")

        return ToolResult(
            success=True,
            data={
                "track": track.name,
                "device": device.name,
                "parameter": param.name,
                "old_value": param.value,
                "new_value": raw_value,
                "lom_path": param.lom_path,
                "ack": ack,
            },
            metadata={
                "ws_host": _WS_HOST,
                "ws_port": _WS_PORT,
            },
        )
