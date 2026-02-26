"""ableton_apply_mix_fix tool — Apply a MixProblem recommendation to Ableton Live.

This is the bridge between the Week 16/17 mix analysis stack and the
Week 19 Ableton control layer.  Given a :class:`MixProblem` (from the
analysis output) and a track name, it:

  1. Classifies the problem (EQ / dynamics / stereo / level)
  2. Reads the current Ableton session to find the correct device
  3. Translates the recommendation into concrete LOM commands
  4. Applies them to Ableton

This is the "copilot closes the loop" tool: the system hears "your low-mids
are muddy" → generates a MixProblem → calls this tool → Ableton's EQ moves.

Use when Claude says:
  - "I'll apply the EQ fix now"
  - "Fixing the muddiness in Pads track"
  - "Applying the recommended compressor settings"
"""

from __future__ import annotations

import re
from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult

_WS_HOST: str = "localhost"
_WS_PORT: int = 11005

# Frequency ranges referenced in MixProblem descriptions
_FREQ_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(?:k?hz|khz)", re.IGNORECASE)
_GAIN_PATTERN = re.compile(r"([+-]?\d+(?:\.\d+)?)\s*db", re.IGNORECASE)


def _extract_freq(text: str) -> float | None:
    """Extract first frequency mention (Hz) from a string."""
    m = _FREQ_PATTERN.search(text)
    if m:
        val = float(m.group(1))
        if "k" in m.group(0).lower():
            val *= 1000
        return val
    return None


def _extract_gain(text: str) -> float | None:
    """Extract first gain mention (dB) from a string."""
    m = _GAIN_PATTERN.search(text)
    return float(m.group(1)) if m else None


class AbletonApplyMixFix(MusicalTool):
    """Apply a MixProblem recommendation directly in Ableton Live."""

    @property
    def name(self) -> str:
        return "ableton_apply_mix_fix"

    @property
    def description(self) -> str:
        return (
            "Apply a mix analysis recommendation directly in Ableton Live. "
            "Provide the problem category, description, recommendation, and target track. "
            "The tool will determine which device and parameter to adjust. "
            "Requires the ALS Listener M4L device loaded in Ableton."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="track_name",
                type=str,
                description="Ableton track to apply the fix to (e.g. 'Pads', 'Bass', 'Kick').",
            ),
            ToolParameter(
                name="category",
                type=str,
                description=(
                    "Problem category from mix analysis: "
                    "'eq' | 'dynamics' | 'stereo' | 'level' | 'harshness' | 'muddiness' | 'low_end'"
                ),
            ),
            ToolParameter(
                name="recommendation",
                type=str,
                description="The recommendation text from the mix analysis, e.g. 'Cut 3 dB at 280 Hz, Q=2'.",
            ),
            ToolParameter(
                name="freq_hz",
                type=float,
                description="Target frequency in Hz (optional — extracted from recommendation if omitted).",
                required=False,
                default=0.0,
            ),
            ToolParameter(
                name="gain_db",
                type=float,
                description="Gain adjustment in dB (optional — extracted from recommendation if omitted).",
                required=False,
                default=0.0,
            ),
            ToolParameter(
                name="eq_band",
                type=int,
                description="EQ Eight band to use (1-8, default 3 for mid-range fixes).",
                required=False,
                default=3,
            ),
            ToolParameter(
                name="dry_run",
                type=bool,
                description="If True, returns the planned commands without executing them.",
                required=False,
                default=False,
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:  # noqa: PLR0911
        """Parse the recommendation and apply the fix."""
        track_name: str = str(kwargs.get("track_name", "")).strip()
        category: str = str(kwargs.get("category", "")).strip().lower()
        recommendation: str = str(kwargs.get("recommendation", "")).strip()
        freq_hz: float = float(kwargs.get("freq_hz", 0.0))
        gain_db: float = float(kwargs.get("gain_db", 0.0))
        eq_band: int = int(kwargs.get("eq_band", 3))
        dry_run: bool = bool(kwargs.get("dry_run", False))

        if not track_name:
            return ToolResult(success=False, error="track_name is required")
        if not category:
            return ToolResult(success=False, error="category is required")
        if not recommendation:
            return ToolResult(success=False, error="recommendation is required")

        # Extract freq / gain from recommendation text if not provided explicitly
        if freq_hz == 0.0:
            extracted_freq = _extract_freq(recommendation)
            if extracted_freq is not None:
                freq_hz = extracted_freq

        if gain_db == 0.0:
            extracted_gain = _extract_gain(recommendation)
            if extracted_gain is not None:
                gain_db = extracted_gain

        # --- Route to correct device type ---
        if category in ("eq", "muddiness", "harshness", "low_end", "tonal", "frequency"):
            return self._apply_eq_fix(
                track_name, category, recommendation, freq_hz, gain_db, eq_band, dry_run
            )
        if category in ("dynamics", "compression", "transients"):
            return self._apply_dynamics_fix(track_name, recommendation, dry_run)
        if category in ("stereo", "width", "mono"):
            return self._apply_stereo_fix(track_name, recommendation, dry_run)
        if category in ("level", "volume", "gain"):
            return self._apply_level_fix(track_name, recommendation, dry_run)

        return ToolResult(
            success=False,
            error=f"Unknown category {category!r}. Use: eq, dynamics, stereo, level, muddiness, harshness",
        )

    # ── EQ fix ──────────────────────────────────────────────────────────────

    def _apply_eq_fix(
        self,
        track_name: str,
        category: str,
        recommendation: str,
        freq_hz: float,
        gain_db: float,
        eq_band: int,
        dry_run: bool,
    ) -> ToolResult:
        if freq_hz <= 0:
            return ToolResult(
                success=False,
                error=f"Cannot extract frequency from recommendation: {recommendation!r}. "
                "Provide freq_hz explicitly.",
            )
        if gain_db == 0.0:
            # Default cuts for common categories
            defaults: dict[str, float] = {
                "muddiness": -3.0,
                "harshness": -2.5,
                "low_end": -4.0,
            }
            gain_db = defaults.get(category, -3.0)

        # Q defaults by category
        q_defaults: dict[str, float] = {
            "muddiness": 1.4,
            "harshness": 2.0,
            "low_end": 0.7,
        }
        q = q_defaults.get(category, 1.0)

        if dry_run:
            return ToolResult(
                success=True,
                data={
                    "dry_run": True,
                    "planned_action": "apply_eq",
                    "track": track_name,
                    "band": eq_band,
                    "freq_hz": freq_hz,
                    "gain_db": gain_db,
                    "q": q,
                    "recommendation": recommendation,
                },
            )

        try:
            from tools.music.ableton_apply_eq import AbletonApplyEQ

            tool = AbletonApplyEQ()
            result = tool(
                track_name=track_name,
                band=eq_band,
                freq_hz=freq_hz,
                gain_db=gain_db,
                q=q,
            )
            if result.success:
                result_data = dict(result.data or {})
                result_data["category"] = category
                result_data["recommendation"] = recommendation
                return ToolResult(success=True, data=result_data, metadata=result.metadata)
            return result
        except Exception as exc:
            return ToolResult(success=False, error=f"EQ fix failed: {exc}")

    # ── Dynamics fix ────────────────────────────────────────────────────────

    def _apply_dynamics_fix(
        self, track_name: str, recommendation: str, dry_run: bool
    ) -> ToolResult:
        """Apply compressor parameter change from a recommendation string."""
        if dry_run:
            return ToolResult(
                success=True,
                data={
                    "dry_run": True,
                    "planned_action": "set_compressor",
                    "track": track_name,
                    "recommendation": recommendation,
                },
            )

        try:
            from core.ableton.commands import set_compressor
            from core.ableton.session import find_compressor, find_track
            from ingestion.ableton_bridge import AbletonBridge

            bridge = AbletonBridge(host=_WS_HOST, port=_WS_PORT)
            session = bridge.get_session()
            track = find_track(session, track_name)
            comp_device = find_compressor(track)

            # Parse ratio / threshold from recommendation text
            threshold = _extract_gain(recommendation)
            cmds = set_compressor(
                track,
                comp_device,
                threshold_db=threshold if threshold is not None else None,
            )
            acks = bridge.send_commands(cmds)
            return ToolResult(
                success=True,
                data={
                    "track": track.name,
                    "device": comp_device.name,
                    "commands_sent": len(cmds),
                    "acks": acks,
                    "recommendation": recommendation,
                },
                metadata={"ws_host": _WS_HOST, "ws_port": _WS_PORT},
            )
        except (ConnectionError, ValueError) as exc:
            return ToolResult(success=False, error=str(exc))
        except Exception as exc:
            return ToolResult(success=False, error=f"Dynamics fix failed: {exc}")

    # ── Stereo fix ──────────────────────────────────────────────────────────

    def _apply_stereo_fix(self, track_name: str, recommendation: str, dry_run: bool) -> ToolResult:
        """Adjust stereo width via Utility device."""
        # Extract width percentage from recommendation
        width_match = re.search(r"(\d+(?:\.\d+)?)\s*%", recommendation)
        width_pct = float(width_match.group(1)) if width_match else 80.0

        if dry_run:
            return ToolResult(
                success=True,
                data={
                    "dry_run": True,
                    "planned_action": "set_utility_width",
                    "track": track_name,
                    "width_pct": width_pct,
                    "recommendation": recommendation,
                },
            )

        try:
            from core.ableton.commands import set_utility
            from core.ableton.device_maps import CLASS_UTILITY
            from core.ableton.session import find_device, find_track
            from ingestion.ableton_bridge import AbletonBridge

            bridge = AbletonBridge(host=_WS_HOST, port=_WS_PORT)
            session = bridge.get_session()
            track = find_track(session, track_name)
            util_device = find_device(track, class_name=CLASS_UTILITY)

            cmds = set_utility(track, util_device, width_pct=width_pct)
            acks = bridge.send_commands(cmds)
            return ToolResult(
                success=True,
                data={
                    "track": track.name,
                    "device": util_device.name,
                    "width_pct": width_pct,
                    "commands_sent": len(cmds),
                    "acks": acks,
                },
                metadata={"ws_host": _WS_HOST, "ws_port": _WS_PORT},
            )
        except (ConnectionError, ValueError) as exc:
            return ToolResult(success=False, error=str(exc))
        except Exception as exc:
            return ToolResult(success=False, error=f"Stereo fix failed: {exc}")

    # ── Level fix ───────────────────────────────────────────────────────────

    def _apply_level_fix(self, track_name: str, recommendation: str, dry_run: bool) -> ToolResult:
        """Adjust track gain via Utility device."""
        gain_db = _extract_gain(recommendation) or -3.0

        if dry_run:
            return ToolResult(
                success=True,
                data={
                    "dry_run": True,
                    "planned_action": "set_utility_gain",
                    "track": track_name,
                    "gain_db": gain_db,
                    "recommendation": recommendation,
                },
            )

        try:
            from core.ableton.commands import set_utility
            from core.ableton.device_maps import CLASS_UTILITY
            from core.ableton.session import find_device, find_track
            from ingestion.ableton_bridge import AbletonBridge

            bridge = AbletonBridge(host=_WS_HOST, port=_WS_PORT)
            session = bridge.get_session()
            track = find_track(session, track_name)
            util_device = find_device(track, class_name=CLASS_UTILITY)

            cmds = set_utility(track, util_device, gain_db=gain_db)
            acks = bridge.send_commands(cmds)
            return ToolResult(
                success=True,
                data={
                    "track": track.name,
                    "device": util_device.name,
                    "gain_db": gain_db,
                    "commands_sent": len(cmds),
                    "acks": acks,
                },
                metadata={"ws_host": _WS_HOST, "ws_port": _WS_PORT},
            )
        except (ConnectionError, ValueError) as exc:
            return ToolResult(success=False, error=str(exc))
        except Exception as exc:
            return ToolResult(success=False, error=f"Level fix failed: {exc}")
