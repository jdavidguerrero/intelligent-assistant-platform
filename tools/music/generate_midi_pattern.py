"""
generate_midi_pattern tool — convert chord progressions to MIDI events.

Hybrid output strategy:
  - Piano roll JSON: always available (no extra deps). Ideal for OpenDock Brain,
    web apps, and any frontend that renders its own MIDI view.
  - MIDI file (.mid): available when `midiutil` is installed (optional dep).
    Ideal for DAW import (Ableton, Logic, Bitwig).

The tool generates two tracks:
  1. Chords  — full voicing, held for specified duration
  2. Bass    — root note only, one octave lower, rhythmic pattern

MIDI event format (piano roll):
  {
    "track":     "chords" | "bass",
    "note":      int,          # MIDI pitch (0-127)
    "note_name": str,          # e.g. "A4"
    "start":     float,        # beat position (0.0 = bar 1 beat 1)
    "duration":  float,        # in beats
    "velocity":  int,          # 0-127
    "channel":   int           # MIDI channel (0-indexed)
  }
"""

from pathlib import Path
from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult
from tools.music.theory import (
    VELOCITY_DEFAULTS,
    build_chord_midi,
    midi_to_note,
    parse_chord_name,
)

# ---------------------------------------------------------------------------
# Domain constants
# ---------------------------------------------------------------------------

MIN_BPM: int = 60
MAX_BPM: int = 220
MIN_BARS_PER_CHORD: int = 1
MAX_BARS_PER_CHORD: int = 8
MAX_CHORDS: int = 32

# Bass rhythm patterns (as beat offsets within a bar, for 4/4 time)
# Values are (beat_offset, duration_in_beats, velocity_factor)
_BASS_PATTERNS: dict[str, list[tuple[float, float, float]]] = {
    "organic house": [
        (0.0, 0.75, 1.0),
        (1.0, 0.5, 0.85),
        (2.0, 0.75, 0.9),
        (3.0, 0.5, 0.85),
    ],
    "melodic house": [
        (0.0, 1.0, 1.0),
        (2.0, 0.75, 0.9),
        (3.5, 0.5, 0.75),
    ],
    "deep house": [
        (0.0, 1.5, 1.0),
        (2.0, 1.5, 0.9),
    ],
    "techno": [
        (0.0, 0.5, 1.0),
        (1.0, 0.5, 0.9),
        (2.0, 0.5, 1.0),
        (3.0, 0.5, 0.9),
    ],
    "acid": [
        (0.0, 0.25, 1.0),
        (0.5, 0.25, 0.8),
        (1.0, 0.5, 0.9),
        (2.0, 0.25, 1.0),
        (2.75, 0.25, 0.75),
        (3.0, 0.5, 0.9),
    ],
    "default": [
        (0.0, 1.0, 1.0),
        (2.0, 1.0, 0.9),
    ],
}

# Chord voicing style → how chord notes are laid out in time
_CHORD_STYLES: dict[str, str] = {
    "block": "block",  # all notes at once
    "arpeggiated": "arp",  # notes in sequence, ascending
    "shell": "shell",  # root + 7th only (3-voice voicing)
}


class GenerateMidiPattern(MusicalTool):
    """
    Generate MIDI events from a chord progression.

    Produces two outputs simultaneously:
    1. Piano roll JSON — portable list of MIDI events, always returned.
       Ideal for OpenDock Brain (send events via MIDI DIN), web display,
       or any frontend rendering its own piano roll.
    2. MIDI file (.mid) — written to disk when output_path is provided
       and midiutil is installed. Imports directly into Ableton / Logic.

    Tracks generated:
      - Chords: full chord voicing (triads, 7ths, or extended)
      - Bass: root note one octave lower with genre-appropriate rhythm

    Example:
        tool = GenerateMidiPattern()
        result = tool(
            chord_names=["Am", "F", "C", "G"],
            bpm=124,
            bars_per_chord=2,
            style="organic house",
            chord_style="block",
            output_path="/tmp/progression.mid"
        )
    """

    @property
    def name(self) -> str:
        return "generate_midi_pattern"

    @property
    def description(self) -> str:
        return (
            "Generate MIDI events from a list of chord names. "
            "Returns a piano roll JSON (portable, works with OpenDock Brain and web apps) "
            "and optionally writes a .mid file for DAW import (Ableton, Logic, Bitwig). "
            "Generates chord and bass tracks with genre-appropriate rhythm. "
            "Use after suggest_chord_progression to turn a progression into playable MIDI."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="chord_names",
                type=list,
                description=(
                    "List of chord name strings to convert to MIDI. "
                    "Examples: ['Am', 'F', 'C', 'G'], ['Amaj7', 'Dm9', 'Gsus4']. "
                    "Accepts any chord names parseable by the theory module."
                ),
                required=True,
            ),
            ToolParameter(
                name="bpm",
                type=int,
                description=f"Tempo in beats per minute ({MIN_BPM}–{MAX_BPM}).",
                required=True,
            ),
            ToolParameter(
                name="bars_per_chord",
                type=int,
                description=(
                    f"How many bars each chord lasts ({MIN_BARS_PER_CHORD}–{MAX_BARS_PER_CHORD}). "
                    f"Default: 2."
                ),
                required=False,
                default=2,
            ),
            ToolParameter(
                name="style",
                type=str,
                description=(
                    "Genre style for bass rhythm pattern. "
                    f"Options: {', '.join(_BASS_PATTERNS.keys() - {'default'})}. "
                    "Default: 'organic house'."
                ),
                required=False,
                default="organic house",
            ),
            ToolParameter(
                name="chord_style",
                type=str,
                description=(
                    "How chord notes are voiced in time. "
                    "'block': all notes simultaneously. "
                    "'arpeggiated': notes in ascending sequence. "
                    "'shell': root + 7th only (sparse, pad-style). "
                    "Default: 'block'."
                ),
                required=False,
                default="block",
            ),
            ToolParameter(
                name="output_path",
                type=str,
                description=(
                    "Optional path to write a .mid MIDI file for DAW import. "
                    "If omitted, only the piano roll JSON is returned. "
                    "Requires midiutil to be installed (pip install midiutil)."
                ),
                required=False,
                default="",
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """
        Generate piano roll + optional MIDI file from chord names.

        Returns:
            ToolResult with piano_roll list, total_beats, duration_seconds,
            and optionally midi_file path and midi_available flag.
        """
        chord_names: list = kwargs.get("chord_names") or []
        bpm: int = kwargs.get("bpm") or 120
        bars_per_chord: int = (
            kwargs.get("bars_per_chord") if kwargs.get("bars_per_chord") is not None else 2
        )
        style: str = (kwargs.get("style") or "organic house").strip().lower()
        chord_style: str = (kwargs.get("chord_style") or "block").strip().lower()
        output_path: str = (kwargs.get("output_path") or "").strip()

        # -------------------------------------------------------------------
        # Domain validation
        # -------------------------------------------------------------------
        if not chord_names:
            return ToolResult(success=False, error="chord_names cannot be empty")
        if not isinstance(chord_names, list):
            return ToolResult(success=False, error="chord_names must be a list of strings")
        if len(chord_names) > MAX_CHORDS:
            return ToolResult(
                success=False,
                error=f"chord_names too long (max {MAX_CHORDS} chords)",
            )
        if not (MIN_BPM <= bpm <= MAX_BPM):
            return ToolResult(
                success=False,
                error=f"bpm must be between {MIN_BPM} and {MAX_BPM}",
            )
        if not (MIN_BARS_PER_CHORD <= bars_per_chord <= MAX_BARS_PER_CHORD):
            return ToolResult(
                success=False,
                error=f"bars_per_chord must be between {MIN_BARS_PER_CHORD} and {MAX_BARS_PER_CHORD}",
            )
        if chord_style not in _CHORD_STYLES:
            return ToolResult(
                success=False,
                error=f"chord_style must be one of: {', '.join(_CHORD_STYLES.keys())}",
            )

        # Parse all chord names upfront — fail fast on any bad name
        parsed_chords: list[tuple[str, str]] = []
        for name in chord_names:
            if not isinstance(name, str) or not name.strip():
                return ToolResult(
                    success=False,
                    error=f"Invalid chord name: {name!r} — must be a non-empty string",
                )
            try:
                parsed_chords.append(parse_chord_name(name.strip()))
            except ValueError as e:
                return ToolResult(success=False, error=str(e))

        # -------------------------------------------------------------------
        # Build piano roll events
        # -------------------------------------------------------------------
        beats_per_bar: int = 4  # 4/4 time
        chord_duration_beats: float = float(bars_per_chord * beats_per_bar)
        bass_pattern = _BASS_PATTERNS.get(style, _BASS_PATTERNS["default"])

        chord_events: list[dict] = []
        bass_events: list[dict] = []

        for chord_idx, (root, quality) in enumerate(parsed_chords):
            bar_start = chord_idx * chord_duration_beats

            # Chord track
            chord_notes = build_chord_midi(root, quality, octave=4)
            chord_events.extend(
                _make_chord_events(
                    notes=chord_notes,
                    start_beat=bar_start,
                    duration_beats=chord_duration_beats,
                    style=_CHORD_STYLES[chord_style],  # map "arpeggiated"→"arp" etc.
                    velocity=VELOCITY_DEFAULTS["chord"],
                    channel=0,
                )
            )

            # Bass track — root note, one octave lower, rhythmic pattern
            bass_root_midi = build_chord_midi(root, quality, octave=3)[0]  # root only, oct 3
            for beat_offset, dur, vel_factor in bass_pattern:
                # Repeat pattern across all bars for this chord
                for bar in range(bars_per_chord):
                    event_start = bar_start + bar * beats_per_bar + beat_offset
                    bass_events.append(
                        _make_note_event(
                            note=bass_root_midi,
                            start=event_start,
                            duration=dur,
                            velocity=int(VELOCITY_DEFAULTS["bass"] * vel_factor),
                            channel=1,
                            track="bass",
                        )
                    )

        all_events = chord_events + bass_events
        total_beats = len(parsed_chords) * chord_duration_beats
        duration_seconds = (total_beats / bpm) * 60.0

        # -------------------------------------------------------------------
        # Optional: write MIDI file
        # -------------------------------------------------------------------
        midi_file_result: dict[str, Any] = {}
        midi_available = _is_midiutil_available()

        if output_path and midi_available:
            write_result = _write_midi_file(
                chord_events=chord_events,
                bass_events=bass_events,
                bpm=bpm,
                output_path=output_path,
            )
            if write_result.get("error"):
                # Non-fatal: piano roll still returned
                midi_file_result = {"midi_error": write_result["error"]}
            else:
                midi_file_result = {"midi_file": write_result["path"]}
        elif output_path and not midi_available:
            midi_file_result = {
                "midi_error": (
                    "midiutil not installed. "
                    "Run: pip install midiutil. "
                    "Piano roll JSON is still returned."
                )
            }

        return ToolResult(
            success=True,
            data={
                "piano_roll": all_events,
                "total_beats": total_beats,
                "duration_seconds": round(duration_seconds, 2),
                "chord_count": len(parsed_chords),
                "bars_per_chord": bars_per_chord,
                "bpm": bpm,
            },
            metadata={
                "style": style,
                "chord_style": chord_style,
                "midi_available": midi_available,
                "tracks": ["chords", "bass"],
                **midi_file_result,
            },
        )


# ---------------------------------------------------------------------------
# Pure event builders
# ---------------------------------------------------------------------------


def _make_note_event(
    note: int,
    start: float,
    duration: float,
    velocity: int,
    channel: int,
    track: str,
) -> dict[str, Any]:
    """Build a single piano roll MIDI event dict."""
    note_name, octave = midi_to_note(note)
    return {
        "track": track,
        "note": note,
        "note_name": f"{note_name}{octave}",
        "start": round(start, 4),
        "duration": round(duration, 4),
        "velocity": min(127, max(0, velocity)),
        "channel": channel,
    }


def _make_chord_events(
    notes: list[int],
    start_beat: float,
    duration_beats: float,
    style: str,
    velocity: int,
    channel: int,
) -> list[dict[str, Any]]:
    """
    Build chord events according to the given chord_style.

    Styles:
        block:       all notes start simultaneously
        arp:         notes staggered by 0.125 beats (1/32 note at 4/4)
        shell:       only root + last note (7th or 5th)
    """
    events = []

    if style == "shell":
        # Use only root and top note (7th / 5th)
        play_notes = [notes[0], notes[-1]] if len(notes) > 1 else [notes[0]]
    else:
        play_notes = notes

    stagger = 0.125  # 32nd note stagger for arpeggiation

    for i, note in enumerate(play_notes):
        if style == "arp":
            note_start = start_beat + i * stagger
            note_dur = duration_beats - i * stagger
        else:
            note_start = start_beat
            note_dur = duration_beats

        # Slight velocity variation for naturalness
        vel = max(60, velocity - i * 3)

        events.append(
            _make_note_event(
                note=note,
                start=note_start,
                duration=max(0.25, note_dur),
                velocity=vel,
                channel=channel,
                track="chords",
            )
        )

    return events


# ---------------------------------------------------------------------------
# MIDI file writer (optional — requires midiutil)
# ---------------------------------------------------------------------------


def _is_midiutil_available() -> bool:
    """Check if midiutil is installed without importing it at module level."""
    try:
        import importlib.util

        return importlib.util.find_spec("midiutil") is not None
    except Exception:
        return False


def _write_midi_file(
    chord_events: list[dict],
    bass_events: list[dict],
    bpm: int,
    output_path: str,
) -> dict[str, Any]:
    """
    Write chord + bass events to a standard MIDI Type 1 file.

    Args:
        chord_events: List of piano roll event dicts for chord track
        bass_events: List of piano roll event dicts for bass track
        bpm: Tempo in BPM
        output_path: Absolute or relative file path for the .mid file

    Returns:
        Dict with 'path' on success or 'error' on failure
    """
    try:
        from midiutil import MIDIFile  # type: ignore[import]
    except ImportError:
        return {"error": "midiutil not installed (pip install midiutil)"}

    try:
        # 2 tracks: 0=chords, 1=bass
        midi = MIDIFile(2, adjust_origin=True)
        midi.addTempo(0, 0, bpm)
        midi.addTempo(1, 0, bpm)

        # Track names
        midi.addTrackName(0, 0, "Chords")
        midi.addTrackName(1, 0, "Bass")

        for event in chord_events:
            midi.addNote(
                track=0,
                channel=event["channel"],
                pitch=event["note"],
                time=event["start"],
                duration=event["duration"],
                volume=event["velocity"],
            )

        for event in bass_events:
            midi.addNote(
                track=1,
                channel=event["channel"],
                pitch=event["note"],
                time=event["start"],
                duration=event["duration"],
                volume=event["velocity"],
            )

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            midi.writeFile(f)

        return {"path": str(path.resolve())}

    except Exception as e:
        return {"error": f"Failed to write MIDI file: {e}"}
