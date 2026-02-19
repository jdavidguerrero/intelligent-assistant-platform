"""
generate_bassline tool — generate MIDI bassline patterns for electronic music.

Pure computation: no LLM, no DB, no I/O.

Generates genre-specific bass patterns:
  - House: root-fifth walking pattern (inspired by Larry Heard)
  - Deep house: jazz-influenced walking bass with chromatic passing tones
  - Techno: one-note hypnotic root-only pump
  - Acid: 303-style squelch with glide, slides, and rhythmic density
  - Organic house: syncopated root movement with occasional 3rds
  - Progressive house: flowing root-fifth-octave pattern

Output:
  - Piano roll MIDI events (same format as generate_midi_pattern)
  - Step grid showing which steps fire
  - Optional .mid file

Technical approach:
  All notes are derived from the chord root — no chord parsing needed.
  Genre styles encode rhythmic patterns (16 steps) and pitch offsets
  from the root (in semitones). Combined with the input key, the tool
  resolves actual MIDI note numbers.
"""

from pathlib import Path
from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult
from tools.music.theory import normalize_note, note_to_midi

# ---------------------------------------------------------------------------
# Bassline pattern definitions
# Each step: (semitone_offset_from_root, velocity, duration_beats)
# semitone_offset: 0=root, 7=fifth, 12=octave, -1=leading tone below, etc.
# 0 velocity = rest
# ---------------------------------------------------------------------------

# 16-step format: (semitone, velocity, duration_multiplier)
# duration_multiplier is relative to 1/16th note (0.25 beats)
# 1.0 = 16th note, 2.0 = 8th note, 4.0 = quarter note

_BASSLINE_PATTERNS: dict[str, list[tuple[int, int, float]]] = {
    # Classic house bass: root + fifth, 8th note groove
    "house": [
        (0, 95, 2.0),
        (0, 0, 0.0),
        (0, 80, 2.0),
        (0, 0, 0.0),
        (7, 85, 1.0),
        (0, 0, 0.0),
        (7, 75, 1.0),
        (0, 75, 1.0),
        (0, 90, 2.0),
        (0, 0, 0.0),
        (0, 80, 1.0),
        (7, 70, 1.0),
        (7, 85, 1.0),
        (5, 75, 1.0),
        (0, 90, 2.0),
        (0, 0, 0.0),
    ],
    # Deep house: walking bass — stepwise, jazz-influenced
    # Uses chromatic passing tones (semitone offsets like 11 = major 7th below octave)
    "deep house": [
        (0, 85, 2.0),
        (0, 0, 0.0),
        (2, 75, 1.0),
        (3, 70, 1.0),
        (5, 80, 2.0),
        (0, 0, 0.0),
        (3, 70, 1.0),
        (2, 75, 1.0),
        (0, 90, 2.0),
        (10, 65, 1.0),
        (0, 75, 1.0),
        (2, 70, 1.0),
        (3, 80, 1.0),
        (5, 75, 1.0),
        (7, 85, 2.0),
        (5, 70, 0.0),
    ],
    # Techno: hypnotic root-only pump — rhythm is everything
    "techno": [
        (0, 100, 1.0),
        (0, 65, 1.0),
        (0, 85, 1.0),
        (0, 60, 1.0),
        (0, 95, 1.0),
        (0, 60, 1.0),
        (0, 80, 1.0),
        (0, 0, 0.0),
        (0, 100, 1.0),
        (0, 65, 1.0),
        (0, 85, 1.0),
        (0, 60, 1.0),
        (0, 95, 1.0),
        (0, 60, 1.0),
        (0, 80, 1.0),
        (0, 75, 1.0),
    ],
    # Acid: dense 303-style with slides and fast rhythmic activity
    # Semitone variations simulate pitch slides and note choice
    "acid": [
        (0, 100, 1.0),
        (0, 85, 0.5),
        (7, 90, 0.5),
        (0, 80, 1.0),
        (5, 95, 1.0),
        (3, 80, 0.5),
        (5, 85, 0.5),
        (7, 75, 1.0),
        (0, 100, 1.0),
        (0, 90, 0.5),
        (0, 80, 0.5),
        (12, 95, 1.0),
        (10, 85, 0.5),
        (7, 90, 0.5),
        (5, 80, 1.0),
        (0, 100, 1.0),
    ],
    # Organic house: syncopated, sparse, modal feel
    "organic house": [
        (0, 90, 2.0),
        (0, 0, 0.0),
        (0, 75, 1.0),
        (0, 0, 0.0),
        (0, 85, 1.0),
        (3, 70, 1.0),
        (0, 0, 0.0),
        (0, 80, 2.0),
        (0, 90, 1.0),
        (0, 0, 0.0),
        (7, 75, 1.0),
        (5, 70, 1.0),
        (3, 80, 1.0),
        (0, 0, 0.0),
        (0, 85, 2.0),
        (0, 0, 0.0),
    ],
    # Progressive house: flowing root-fifth-octave
    "progressive house": [
        (0, 90, 2.0),
        (0, 0, 0.0),
        (7, 80, 1.0),
        (7, 75, 1.0),
        (0, 85, 1.0),
        (0, 0, 0.0),
        (5, 75, 1.0),
        (0, 0, 0.0),
        (0, 95, 2.0),
        (7, 75, 1.0),
        (0, 0, 0.0),
        (12, 70, 1.0),
        (7, 80, 1.0),
        (5, 75, 1.0),
        (0, 90, 1.0),
        (0, 80, 1.0),
    ],
    # Melodic house: mid-range bass, melodic movement, minor thirds
    "melodic house": [
        (0, 85, 2.0),
        (0, 0, 0.0),
        (3, 75, 1.0),
        (5, 70, 1.0),
        (7, 80, 2.0),
        (0, 0, 0.0),
        (5, 70, 1.0),
        (3, 75, 1.0),
        (0, 90, 2.0),
        (3, 70, 1.0),
        (5, 75, 1.0),
        (7, 80, 1.0),
        (5, 75, 1.0),
        (3, 70, 1.0),
        (0, 85, 2.0),
        (0, 0, 0.0),
    ],
}

VALID_GENRES: frozenset[str] = frozenset(_BASSLINE_PATTERNS.keys())

# Default bass octave per genre
_GENRE_OCTAVE: dict[str, int] = {
    "house": 2,
    "deep house": 2,
    "techno": 2,
    "acid": 1,  # 303 sits in octave 1–2
    "organic house": 2,
    "progressive house": 2,
    "melodic house": 2,
}


class GenerateBassline(MusicalTool):
    """
    Generate a MIDI bassline pattern for electronic music genres.

    Produces genre-specific bass patterns:
    - House: root + fifth walking pattern
    - Deep house: jazz-influenced chromatic walking bass
    - Techno: hypnotic root-only pump with ghost notes
    - Acid: dense 303-style with slides and rhythmic density
    - Organic house: syncopated, sparse, modal
    - Progressive/Melodic house: flowing melodic movement

    Returns piano roll MIDI events compatible with other generate_* tools.
    """

    @property
    def name(self) -> str:
        return "generate_bassline"

    @property
    def description(self) -> str:
        return (
            "Generate a MIDI bassline pattern for electronic music. "
            "Produces genre-specific bass patterns: house root+fifth groove, "
            "deep house jazz walking bass, techno root pump, acid 303-style squelch, "
            "organic house syncopated groove, progressive/melodic house melodic movement. "
            "Returns piano roll MIDI events. "
            "Use when the user asks for a bassline, bass pattern, 303 line, or "
            "wants to add a bass track to their production. "
            f"Supported genres: {', '.join(sorted(VALID_GENRES))}."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="root",
                type=str,
                description=("Root note for the bassline (e.g. 'A', 'F#', 'Bb'). " "Default: 'A'."),
                required=False,
                default="A",
            ),
            ToolParameter(
                name="genre",
                type=str,
                description=(
                    f"Genre style for the bass pattern. "
                    f"Options: {', '.join(sorted(VALID_GENRES))}. "
                    "Default: 'house'."
                ),
                required=False,
                default="house",
            ),
            ToolParameter(
                name="bpm",
                type=int,
                description="Tempo in BPM (60–180). Default: 124.",
                required=False,
                default=124,
            ),
            ToolParameter(
                name="bars",
                type=int,
                description="Number of bars to generate (1–8). Default: 2.",
                required=False,
                default=2,
            ),
            ToolParameter(
                name="octave",
                type=int,
                description=(
                    "Base octave for the bass (1–3). " "Default depends on genre: acid=1, others=2."
                ),
                required=False,
                default=0,  # 0 = auto-detect from genre
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
        root_raw: str = (kwargs.get("root") or "A").strip()
        genre: str = (kwargs.get("genre") or "house").strip().lower()
        bpm: int = kwargs.get("bpm") or 124
        bars: int = kwargs.get("bars") or 2
        octave_raw: int = kwargs.get("octave") or 0
        output_path: str = (kwargs.get("output_path") or "").strip()

        try:
            root = normalize_note(root_raw)
        except ValueError:
            return ToolResult(success=False, error=f"Unknown root note: {root_raw!r}")

        if genre not in VALID_GENRES:
            return ToolResult(
                success=False,
                error=f"genre must be one of: {', '.join(sorted(VALID_GENRES))}. Got: {genre!r}",
            )
        if not (60 <= bpm <= 180):
            return ToolResult(success=False, error="bpm must be between 60 and 180")
        if not (1 <= bars <= 8):
            return ToolResult(success=False, error="bars must be between 1 and 8")

        octave = octave_raw if 1 <= octave_raw <= 3 else _GENRE_OCTAVE.get(genre, 2)
        pattern = _BASSLINE_PATTERNS[genre]
        beat_per_step = 0.25  # 16th note

        events: list[dict] = []
        step_grid: list[int] = []

        for bar in range(bars):
            bar_beat_offset = bar * 4.0
            for step_idx, (semitone, velocity, _dur_mult) in enumerate(pattern):
                step_grid.append(velocity)
                if velocity == 0:
                    continue

                dur_beats = beat_per_step * max(1.0, _dur_mult)
                beat_pos = bar_beat_offset + step_idx * beat_per_step

                try:
                    midi_note = note_to_midi(root, octave) + semitone
                except ValueError:
                    continue

                # Clamp to valid MIDI range
                if not (0 <= midi_note <= 127):
                    continue

                events.append(
                    {
                        "track": "bass",
                        "note": midi_note,
                        "note_name": f"bass_{semitone:+d}st",
                        "start": round(beat_pos, 4),
                        "duration": round(dur_beats * 0.9, 4),  # 90% gate
                        "velocity": min(127, max(30, velocity)),
                        "channel": 1,
                        "semitone_offset": semitone,
                    }
                )

        events.sort(key=lambda e: e["start"])
        total_beats = bars * 4.0
        duration_seconds = (total_beats / bpm) * 60.0

        midi_file_result: dict[str, Any] = {}
        midi_available = _is_midiutil_available()

        if output_path and midi_available:
            write_result = _write_bass_midi(events=events, bpm=bpm, output_path=output_path)
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
                "step_grid": step_grid,
                "total_beats": total_beats,
                "duration_seconds": round(duration_seconds, 2),
                "note_count": len(events),
                "root": root,
                "octave": octave,
                "genre": genre,
                "bpm": bpm,
            },
            metadata={
                "steps_per_bar": 16,
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


def _write_bass_midi(events: list[dict], bpm: int, output_path: str) -> dict[str, Any]:
    try:
        from midiutil import MIDIFile  # type: ignore[import]
    except ImportError:
        return {"error": "midiutil not installed"}

    try:
        midi = MIDIFile(1, adjust_origin=True)
        midi.addTempo(0, 0, bpm)
        midi.addTrackName(0, 0, "Bass")

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
