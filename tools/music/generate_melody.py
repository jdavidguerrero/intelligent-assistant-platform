"""
generate_melody tool — generate diatonic melodic phrases for electronic music.

Pure computation: no LLM, no DB, no I/O.

Given a key, mode, genre, and mood, generates a single-voice melodic line:
  - Built from scale degrees of the given key
  - Rhythmically varied (mix of 8ths, quarters, dotted rhythms)
  - Phrase-aware: contours follow tension/release arc
  - Output: piano roll MIDI events + optional .mid file

Design principles:
  - Every note is a diatonic scale degree — no accidentals
  - Phrase contour follows mood: dark=descending, euphoric=ascending
  - Rhythm is genre-appropriate (staccato for techno, legato for melodic house)
  - Register: melody lives in octave 5 (above chords in octave 4)
"""

from pathlib import Path
from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult
from tools.music.theory import (
    SCALE_FORMULAS,
    build_scale,
    normalize_note,
    note_to_midi,
)

# ---------------------------------------------------------------------------
# Melodic phrase templates per mood
# Each entry: list of (scale_degree_0based, duration_beats, velocity_factor)
# Scale degree 0 = root, 4 = fifth, 6 = seventh, etc.
# Durations: 0.25=16th, 0.5=8th, 1.0=quarter, 2.0=half
# ---------------------------------------------------------------------------

_PHRASES: dict[str, list[tuple[int, float, float]]] = {
    "dark": [
        # Descending minor phrase — starts on 5th, drops to root
        (4, 0.5, 1.0),
        (2, 0.5, 0.85),
        (1, 0.5, 0.8),
        (0, 1.0, 0.9),
        (5, 0.5, 0.75),
        (3, 0.5, 0.7),
        (1, 0.25, 0.65),
        (0, 1.25, 1.0),
    ],
    "melancholic": [
        # Stepwise descent with a longing leap up before resolving
        (0, 1.0, 0.9),
        (2, 0.5, 0.8),
        (1, 0.5, 0.75),
        (5, 0.5, 1.0),
        (4, 0.5, 0.85),
        (2, 0.5, 0.8),
        (0, 2.0, 1.0),
    ],
    "dreamy": [
        # Floating: large leaps, sustained notes, non-linear movement
        (0, 1.0, 0.8),
        (4, 0.5, 1.0),
        (6, 1.0, 0.9),
        (5, 0.5, 0.75),
        (2, 0.5, 0.7),
        (4, 1.5, 0.85),
    ],
    "euphoric": [
        # Ascending phrase — builds energy, peaks on 6th
        (0, 0.5, 0.8),
        (1, 0.5, 0.85),
        (2, 0.5, 0.9),
        (4, 0.5, 0.95),
        (5, 1.0, 1.0),
        (4, 0.5, 0.9),
        (2, 1.5, 0.85),
    ],
    "neutral": [
        # Balanced call-and-response
        (0, 0.5, 0.85),
        (2, 0.5, 0.8),
        (4, 0.5, 0.85),
        (4, 0.5, 0.9),
        (2, 0.5, 0.8),
        (0, 2.0, 1.0),
    ],
    "tense": [
        # Chromatic tension: uses neighbour tones (flat 2nd degree)
        (0, 0.25, 1.0),
        (1, 0.25, 0.9),
        (0, 0.5, 0.85),
        (4, 0.5, 0.95),
        (3, 0.25, 0.8),
        (4, 0.25, 0.85),
        (6, 1.0, 1.0),
        (0, 1.5, 0.9),
    ],
}

VALID_MOODS: frozenset[str] = frozenset(_PHRASES.keys())

# Genre → preferred rhythmic feel (affects note duration scaling)
_GENRE_RHYTHM_SCALE: dict[str, float] = {
    "organic house": 1.0,  # natural durations
    "melodic house": 1.2,  # slightly longer, more legato
    "progressive house": 1.1,
    "deep house": 1.3,  # very legato, sustained
    "melodic techno": 0.85,  # slightly shorter, more articulated
    "techno": 0.7,  # staccato
    "acid": 0.5,  # very short — 303 style
    "default": 1.0,
}

# Register: octave per genre (melody sits above chords)
_GENRE_OCTAVE: dict[str, int] = {
    "organic house": 5,
    "melodic house": 5,
    "progressive house": 5,
    "deep house": 4,  # deep house melody can be lower, darker
    "melodic techno": 5,
    "techno": 5,
    "acid": 3,  # acid 303 bass range
    "default": 5,
}

VALID_MODES: frozenset[str] = frozenset(SCALE_FORMULAS.keys())


class GenerateMelody(MusicalTool):
    """
    Generate a diatonic melodic phrase for electronic music production.

    Builds a single-voice melody from the scale degrees of the given key and mode.
    Phrase contour follows mood: dark phrases descend, euphoric phrases ascend.
    Rhythm is genre-appropriate.

    Works best chained with suggest_scale (to get key + mode)
    and suggest_chord_progression (to harmonize the melody).
    """

    @property
    def name(self) -> str:
        return "generate_melody"

    @property
    def description(self) -> str:
        return (
            "Generate a diatonic melodic phrase in a given key, mode, and mood. "
            "Returns MIDI events (piano roll) for a single-voice melodic line "
            "with genre-appropriate rhythm and phrase contour. "
            "Use when the user asks for a melody, lead line, hook, motif, or "
            "wants to add a melodic element to their track. "
            f"Supported moods: {', '.join(sorted(VALID_MOODS))}."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="key",
                type=str,
                description=("Root note for the melody (e.g. 'A', 'F#', 'Bb'). " "Default: 'A'."),
                required=False,
                default="A",
            ),
            ToolParameter(
                name="mode",
                type=str,
                description=(
                    f"Scale mode. Options: {', '.join(sorted(VALID_MODES))}. "
                    "Default: 'natural minor'."
                ),
                required=False,
                default="natural minor",
            ),
            ToolParameter(
                name="mood",
                type=str,
                description=(
                    f"Phrase mood/contour. Options: {', '.join(sorted(VALID_MOODS))}. "
                    "Default: 'melancholic'."
                ),
                required=False,
                default="melancholic",
            ),
            ToolParameter(
                name="genre",
                type=str,
                description=("Genre for rhythmic style and register. " "Default: 'organic house'."),
                required=False,
                default="organic house",
            ),
            ToolParameter(
                name="bars",
                type=int,
                description="Number of bars to generate (1–8). Default: 2.",
                required=False,
                default=2,
            ),
            ToolParameter(
                name="bpm",
                type=int,
                description="Tempo in BPM (60–220). Default: 124.",
                required=False,
                default=124,
            ),
            ToolParameter(
                name="output_path",
                type=str,
                description="Optional path to write a .mid file (requires midiutil).",
                required=False,
                default="",
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        key_raw: str = (kwargs.get("key") or "A").strip()
        mode: str = (kwargs.get("mode") or "natural minor").strip().lower()
        mood: str = (kwargs.get("mood") or "melancholic").strip().lower()
        genre: str = (kwargs.get("genre") or "organic house").strip().lower()
        bars: int = kwargs.get("bars") or 2
        bpm: int = kwargs.get("bpm") or 124
        output_path: str = (kwargs.get("output_path") or "").strip()

        # Validate
        try:
            root = normalize_note(key_raw)
        except ValueError:
            return ToolResult(success=False, error=f"Unknown root note: {key_raw!r}")

        if mode not in VALID_MODES:
            return ToolResult(
                success=False,
                error=f"mode must be one of: {', '.join(sorted(VALID_MODES))}",
            )
        if mood not in VALID_MOODS:
            return ToolResult(
                success=False,
                error=f"mood must be one of: {', '.join(sorted(VALID_MOODS))}",
            )
        if not (1 <= bars <= 8):
            return ToolResult(success=False, error="bars must be between 1 and 8")
        if not (60 <= bpm <= 220):
            return ToolResult(success=False, error="bpm must be between 60 and 220")

        # Build scale
        scale_notes = build_scale(root, mode)
        octave = _GENRE_OCTAVE.get(genre, _GENRE_OCTAVE["default"])
        rhythm_scale = _GENRE_RHYTHM_SCALE.get(genre, _GENRE_RHYTHM_SCALE["default"])

        phrase = _PHRASES[mood]
        total_bars_beats = float(bars * 4)

        # Build events — repeat/truncate phrase to fill requested bars
        events: list[dict] = []
        current_beat = 0.0
        phrase_idx = 0

        while current_beat < total_bars_beats - 0.01:
            degree, raw_dur, vel_factor = phrase[phrase_idx % len(phrase)]
            dur = raw_dur * rhythm_scale

            # Clamp to remaining space
            remaining = total_bars_beats - current_beat
            if remaining < 0.125:
                break
            dur = min(dur, remaining)

            # Resolve scale degree to MIDI note (wraps if degree >= scale length)
            note_name = scale_notes[degree % len(scale_notes)]
            # Boost octave if wrapping (e.g. degree 7 in a 7-note scale)
            note_octave = octave + (degree // len(scale_notes))
            try:
                midi_note = note_to_midi(note_name, note_octave)
            except ValueError:
                midi_note = note_to_midi(note_name, octave)

            velocity = int(90 * vel_factor)

            events.append(
                {
                    "track": "melody",
                    "note": midi_note,
                    "note_name": f"{note_name}{note_octave}",
                    "start": round(current_beat, 4),
                    "duration": round(max(0.125, dur * 0.9), 4),  # 90% gate
                    "velocity": min(127, max(30, velocity)),
                    "channel": 2,
                    "scale_degree": degree,
                }
            )

            current_beat += dur
            phrase_idx += 1

        duration_seconds = (total_bars_beats / bpm) * 60.0

        # Optional MIDI file
        midi_file_result: dict[str, Any] = {}
        midi_available = _is_midiutil_available()

        if output_path and midi_available:
            write_result = _write_melody_midi(events=events, bpm=bpm, output_path=output_path)
            if write_result.get("error"):
                midi_file_result = {"midi_error": write_result["error"]}
            else:
                midi_file_result = {"midi_file": write_result["path"]}
        elif output_path and not midi_available:
            midi_file_result = {"midi_error": "midiutil not installed. Run: pip install midiutil."}

        return ToolResult(
            success=True,
            data={
                "piano_roll": events,
                "total_beats": total_bars_beats,
                "duration_seconds": round(duration_seconds, 2),
                "note_count": len(events),
                "key": f"{root} {mode}",
                "scale_notes": scale_notes,
                "bpm": bpm,
            },
            metadata={
                "root": root,
                "mode": mode,
                "mood": mood,
                "genre": genre,
                "octave": octave,
                "midi_available": midi_available,
                **midi_file_result,
            },
        )


def _is_midiutil_available() -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec("midiutil") is not None
    except Exception:
        return False


def _write_melody_midi(events: list[dict], bpm: int, output_path: str) -> dict[str, Any]:
    try:
        from midiutil import MIDIFile  # type: ignore[import]
    except ImportError:
        return {"error": "midiutil not installed"}

    try:
        midi = MIDIFile(1, adjust_origin=True)
        midi.addTempo(0, 0, bpm)
        midi.addTrackName(0, 0, "Melody")

        for event in events:
            midi.addNote(
                track=0,
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
