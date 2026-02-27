"""
ableton_insert_notes tool — send melody notes to Ableton via OSC.

Sends a list of Note objects (from extract_melody or full_arrangement)
directly into an Ableton Live MIDI clip via OSC messages.

Requires the "Claude Notes" Max for Live device (.amxd) loaded on
a MIDI track in Ableton Live. The device listens on localhost:11002.

OSC message format (per note):
    /note/add  pitch_midi  onset_sec  duration_sec  velocity

End-of-batch signal:
    /notes/commit

How to use in Ableton:
    1. Create a MIDI track
    2. Drag 'Claude Notes' M4L device onto the track
    3. Select an empty clip slot (click on it)
    4. Call this tool with the notes from extract_melody
    5. Notes appear in the piano roll instantly

Typical workflow:
    1. extract_melody(file_path) → notes list
    2. ableton_insert_notes(notes=notes, bpm=128.0)
"""

from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult

_OSC_HOST: str = "127.0.0.1"
_OSC_PORT: int = 11002


class AbletonInsertNotes(MusicalTool):
    """Send melody notes extracted from audio to Ableton Live via OSC.

    Requires the 'Claude Notes' Max for Live device on a MIDI track
    listening on localhost:11002.

    Converts onset/duration times (in seconds) to MIDI beat positions
    using the provided BPM, then sends each note as an OSC message.

    Example:
        notes = [
            {"pitch_midi": 69, "onset_sec": 0.0, "duration_sec": 0.5, "velocity": 80},
            {"pitch_midi": 72, "onset_sec": 0.5, "duration_sec": 0.5, "velocity": 75},
        ]
        tool = AbletonInsertNotes()
        result = tool(notes=notes, bpm=128.0)
    """

    @property
    def name(self) -> str:
        return "ableton_insert_notes"

    @property
    def description(self) -> str:
        return (
            "Insert melody notes into the selected Ableton Live MIDI clip via OSC. "
            "REQUIRES: 'Claude Notes' Max for Live device loaded on a MIDI track. "
            "Converts note onset times (seconds) to beat positions using the given BPM. "
            "Use after extract_melody to send detected melody notes directly to Ableton. "
            "Notes appear instantly in the piano roll. "
            "OSC target: localhost:11002."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="notes",
                type=list,
                description=(
                    "List of note dicts, each with: pitch_midi (int 0-127), "
                    "onset_sec (float >= 0), duration_sec (float > 0), velocity (int 1-127). "
                    "Use output from extract_melody or analyze_sample."
                ),
                required=True,
            ),
            ToolParameter(
                name="bpm",
                type=float,
                description="Session BPM for converting seconds → beat positions. Default: 120.0.",
                required=False,
                default=120.0,
            ),
            ToolParameter(
                name="velocity",
                type=int,
                description="Override velocity for all notes (1–127). 0 = use per-note velocity.",
                required=False,
                default=0,
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """Send note list to Ableton via OSC.

        Returns:
            ToolResult.data with note_count and confirmation string.
        """
        notes_raw: list[dict] = kwargs.get("notes") or []
        bpm: float = float(kwargs.get("bpm") or 120.0)
        vel_override: int = int(kwargs.get("velocity") or 0)

        if not notes_raw:
            return ToolResult(success=False, error="notes list cannot be empty")
        if bpm <= 0:
            return ToolResult(success=False, error="bpm must be > 0")

        # Validate and normalise notes
        validated: list[dict] = []
        for i, n in enumerate(notes_raw):
            if not isinstance(n, dict):
                return ToolResult(
                    success=False, error=f"notes[{i}] must be a dict, got {type(n).__name__}"
                )
            pitch_midi = int(n.get("pitch_midi", 0))
            onset_sec = float(n.get("onset_sec", 0.0))
            duration_sec = float(n.get("duration_sec", 0.25))
            velocity = int(n.get("velocity", 80))

            if not (0 <= pitch_midi <= 127):
                return ToolResult(
                    success=False, error=f"notes[{i}].pitch_midi {pitch_midi} out of range [0,127]"
                )
            if duration_sec <= 0:
                return ToolResult(success=False, error=f"notes[{i}].duration_sec must be > 0")

            if vel_override > 0:
                velocity = max(1, min(127, vel_override))

            validated.append(
                {
                    "pitch_midi": pitch_midi,
                    "onset_sec": onset_sec,
                    "duration_sec": duration_sec,
                    "velocity": max(1, min(127, velocity)),
                }
            )

        try:
            from pythonosc.udp_client import SimpleUDPClient  # type: ignore[import]

            client = SimpleUDPClient(_OSC_HOST, _OSC_PORT)

            # Send /notes/clear to reset the current clip
            client.send_message("/notes/clear", [])

            # Send each note: /note/add pitch_midi onset_beat duration_beat velocity
            beats_per_sec = bpm / 60.0
            for note in validated:
                onset_beat = float(note["onset_sec"]) * beats_per_sec
                duration_beat = float(note["duration_sec"]) * beats_per_sec
                client.send_message(
                    "/note/add",
                    [
                        note["pitch_midi"],
                        round(onset_beat, 4),
                        round(duration_beat, 4),
                        note["velocity"],
                    ],
                )

            # Commit: trigger M4L device to write notes to clip
            client.send_message("/notes/commit", [])

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
                    f"Is the 'Claude Notes' M4L device running? ({exc})"
                ),
            )

        return ToolResult(
            success=True,
            data={
                "note_count": len(validated),
                "bpm": bpm,
                "message": (
                    f"Sent {len(validated)} notes to Ableton "
                    f"(localhost:{_OSC_PORT}, {bpm} BPM)."
                ),
            },
            metadata={
                "osc_host": _OSC_HOST,
                "osc_port": _OSC_PORT,
            },
        )
