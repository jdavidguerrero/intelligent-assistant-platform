"""
ableton_insert_drums tool — send drum patterns to Ableton via OSC.

Sends a DrumPattern (from generate_full_arrangement or generate_drums)
directly into an Ableton Live MIDI clip via OSC messages.

Requires the "Claude Drums" Max for Live device (.amxd) loaded on
a MIDI track with a drum rack in Ableton Live.
The device listens on localhost:11003.

GM drum note mapping (same as midi_export.py):
    kick=36, snare=38, clap=39, hihat_c=42, hihat_o=46

OSC message format (per hit):
    /drum/hit  gm_note  step  velocity  bar

End-of-batch signal:
    /drums/commit  bpm  bars  steps_per_bar

How to use in Ableton:
    1. Create a MIDI track with a Drum Rack
    2. Drag 'Claude Drums' M4L device onto the track
    3. Select an empty clip slot
    4. Call this tool with the drum_hits from generate_full_arrangement
    5. Drum pattern appears in the piano roll instantly

Typical workflow:
    1. generate_full_arrangement(file_path, genre="organic house") → drum_hits
    2. ableton_insert_drums(hits=drum_hits, bpm=128.0, bars=4)
"""

from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult

_OSC_HOST: str = "127.0.0.1"
_OSC_PORT: int = 11003

# GM drum note mapping (mirrors ingestion/midi_export.py)
_GM_DRUM_NOTES: dict[str, int] = {
    "kick": 36,
    "snare": 38,
    "clap": 39,
    "hihat_c": 42,
    "hihat_o": 46,
}


class AbletonInsertDrums(MusicalTool):
    """Send a drum pattern to Ableton Live via OSC.

    Requires the 'Claude Drums' Max for Live device on a MIDI track
    with a Drum Rack, listening on localhost:11003.

    Converts the 16-step grid pattern to MIDI beat positions using the
    provided BPM, maps instrument names to GM drum notes (kick=36,
    snare=38, clap=39, hihat_c=42, hihat_o=46), and sends each hit
    as an OSC message.

    Example:
        hits = [
            {"instrument": "kick", "step": 0, "velocity": 100, "bar": 0},
            {"instrument": "snare", "step": 4, "velocity": 90, "bar": 0},
            {"instrument": "hihat_c", "step": 2, "velocity": 70, "bar": 0},
        ]
        tool = AbletonInsertDrums()
        result = tool(hits=hits, bpm=128.0, bars=1)
    """

    @property
    def name(self) -> str:
        return "ableton_insert_drums"

    @property
    def description(self) -> str:
        return (
            "Insert a drum pattern into the selected Ableton Live MIDI clip via OSC. "
            "REQUIRES: 'Claude Drums' Max for Live device on a MIDI track with a Drum Rack. "
            "Maps instrument names to GM drum notes: "
            "kick=36, snare=38, clap=39, hihat_c=42, hihat_o=46. "
            "Use after generate_full_arrangement or generate_drums to send the drum pattern "
            "directly to Ableton. Pattern appears instantly in the piano roll. "
            "OSC target: localhost:11003."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="hits",
                type=list,
                description=(
                    "List of drum hit dicts, each with: "
                    "instrument (str: kick/snare/clap/hihat_c/hihat_o), "
                    "step (int 0-15), velocity (int 1-127), bar (int >= 0). "
                    "Use output from generate_full_arrangement.drum_hits or generate_drums."
                ),
                required=True,
            ),
            ToolParameter(
                name="bpm",
                type=float,
                description="Session BPM for timing. Default: 120.0.",
                required=False,
                default=120.0,
            ),
            ToolParameter(
                name="bars",
                type=int,
                description="Number of bars in the pattern (1–16). Default: 4.",
                required=False,
                default=4,
            ),
            ToolParameter(
                name="steps_per_bar",
                type=int,
                description="Grid resolution (default 16 = 16th notes).",
                required=False,
                default=16,
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """Send drum hits to Ableton via OSC.

        Returns:
            ToolResult.data with hit_count and confirmation string.
        """
        hits_raw: list[dict] = kwargs.get("hits") or []
        bpm: float = float(kwargs.get("bpm") or 120.0)
        bars: int = int(kwargs.get("bars") or 4)
        steps_per_bar: int = int(kwargs.get("steps_per_bar") or 16)

        if not hits_raw:
            return ToolResult(success=False, error="hits list cannot be empty")
        if bpm <= 0:
            return ToolResult(success=False, error="bpm must be > 0")
        if not (1 <= bars <= 16):
            return ToolResult(success=False, error="bars must be between 1 and 16")

        # Validate and normalise hits
        validated: list[dict] = []
        for i, h in enumerate(hits_raw):
            if not isinstance(h, dict):
                return ToolResult(
                    success=False, error=f"hits[{i}] must be a dict, got {type(h).__name__}"
                )
            instrument = str(h.get("instrument", ""))
            step = int(h.get("step", 0))
            velocity = int(h.get("velocity", 80))
            bar = int(h.get("bar", 0))

            if instrument not in _GM_DRUM_NOTES:
                return ToolResult(
                    success=False,
                    error=(
                        f"hits[{i}].instrument {instrument!r} not recognised. "
                        f"Valid: {', '.join(sorted(_GM_DRUM_NOTES))}"
                    ),
                )
            if not (0 <= step <= 15):
                return ToolResult(success=False, error=f"hits[{i}].step {step} out of range [0,15]")
            if bar < 0:
                return ToolResult(success=False, error=f"hits[{i}].bar {bar} must be >= 0")

            validated.append(
                {
                    "gm_note": _GM_DRUM_NOTES[instrument],
                    "instrument": instrument,
                    "step": step,
                    "velocity": max(1, min(127, velocity)),
                    "bar": bar,
                }
            )

        try:
            from pythonosc.udp_client import SimpleUDPClient  # type: ignore[import]

            client = SimpleUDPClient(_OSC_HOST, _OSC_PORT)

            # Clear current clip
            client.send_message("/drums/clear", [])

            # ticks_per_step for beat calculation: each step = 1/16th note = 0.25 beats
            beats_per_step = 4.0 / float(steps_per_bar)  # 4 beats per bar ÷ steps

            for hit in validated:
                # Absolute beat position: bar * 4 beats + step * beats_per_step
                beat_pos = float(hit["bar"]) * 4.0 + float(hit["step"]) * beats_per_step
                client.send_message(
                    "/drum/hit",
                    [
                        hit["gm_note"],
                        round(beat_pos, 4),
                        hit["velocity"],
                        hit["instrument"],
                    ],
                )

            # Commit: pass metadata for M4L device to set clip length
            client.send_message(
                "/drums/commit",
                [float(bpm), bars, steps_per_bar],
            )

        except ImportError:
            return ToolResult(
                success=False,
                error=("python-osc is not installed. " "Install with: pip install python-osc"),
            )
        except OSError as exc:
            return ToolResult(
                success=False,
                error=(
                    f"Cannot connect to Ableton on localhost:{_OSC_PORT}. "
                    f"Is the 'Claude Drums' M4L device running? ({exc})"
                ),
            )

        return ToolResult(
            success=True,
            data={
                "hit_count": len(validated),
                "bpm": bpm,
                "bars": bars,
                "message": (
                    f"Sent {len(validated)} drum hits to Ableton "
                    f"({bars} bars at {bpm} BPM, localhost:{_OSC_PORT})."
                ),
            },
            metadata={
                "osc_host": _OSC_HOST,
                "osc_port": _OSC_PORT,
                "gm_drum_notes": _GM_DRUM_NOTES,
            },
        )
