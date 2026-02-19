"""
generate_drum_pattern tool — generate MIDI drum patterns for house and electronic music.

Pure computation: no LLM, no DB, no I/O.

Generates a 16-step (one bar in 4/4 at 1/16th note resolution) drum pattern for:
  - Kick drum (808 / house / TR-909 style)
  - Snare / clap
  - Closed hi-hat
  - Open hi-hat
  - Ride cymbal
  - Percussion accent (shaker, rim, cowbell)

Output formats:
  - Step grid: list of 16 booleans per instrument
  - Piano roll events: MIDI events with beat positions (compatible with generate_midi_pattern)
  - Optional .mid file (requires midiutil)

GM Drum Map (channel 9, 0-indexed):
  Kick:        MIDI 36 (Bass Drum 1)
  Snare:       MIDI 38 (Acoustic Snare)
  Clap:        MIDI 39 (Hand Clap)
  Closed Hat:  MIDI 42 (Closed Hi-Hat)
  Open Hat:    MIDI 46 (Open Hi-Hat)
  Ride:        MIDI 51 (Ride Cymbal 1)
  Shaker:      MIDI 70 (Maracas)
  Rim:         MIDI 37 (Side Stick)
  Cowbell:     MIDI 56 (Cowbell)
  Tom:         MIDI 45 (Low Tom)
"""

from pathlib import Path
from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult

# ---------------------------------------------------------------------------
# MIDI drum map — GM standard, channel 9 (0-indexed)
# ---------------------------------------------------------------------------

DRUM_MIDI: dict[str, int] = {
    "kick": 36,
    "snare": 38,
    "clap": 39,
    "closed_hat": 42,
    "open_hat": 46,
    "ride": 51,
    "shaker": 70,
    "rim": 37,
    "cowbell": 56,
    "tom_low": 45,
    "tom_mid": 47,
    "tom_high": 50,
    "crash": 49,
}

DRUM_CHANNEL: int = 9  # GM standard drum channel (0-indexed)
STEPS_PER_BAR: int = 16  # 16 steps = 16th note grid in 4/4

# ---------------------------------------------------------------------------
# Genre patterns — 16 steps per instrument
# 1 = hit, 0 = rest. Velocity overrides per step encoded separately.
# ---------------------------------------------------------------------------

# Velocity layers: F=forte(100), M=mezzo(80), P=piano(65), G=ghost(45)
_F, _M, _P, _G = 100, 80, 65, 45

# Pattern format:
#   steps: list[int] of length 16 (0=rest, else=velocity)
#   instrument: drum map key

_PATTERNS: dict[str, dict[str, list[int]]] = {
    "house": {
        # Four-on-the-floor: kick on every beat (steps 0,4,8,12)
        "kick": [_F, 0, 0, 0, _F, 0, 0, 0, _F, 0, 0, 0, _F, 0, 0, 0],
        # Snare on beats 2 and 4 (steps 4,12) — classic house backbeat
        "snare": [0, 0, 0, 0, _F, 0, 0, 0, 0, 0, 0, 0, _F, 0, 0, 0],
        # Clap layered on beats 2 and 4, slightly softer
        "clap": [0, 0, 0, 0, _M, 0, 0, 0, 0, 0, 0, 0, _M, 0, 0, 0],
        # Closed hat on every 8th note (steps 0,2,4,6,8,10,12,14)
        "closed_hat": [_M, 0, _M, 0, _M, 0, _M, 0, _M, 0, _M, 0, _M, 0, _M, 0],
        # Open hat offbeat — on step 9 (the "and" of beat 3)
        "open_hat": [0, 0, 0, 0, 0, 0, 0, 0, 0, _M, 0, 0, 0, 0, 0, 0],
        # Shaker adds shuffle — 8th note pattern with accents
        "shaker": [_G, 0, _G, 0, _G, 0, _G, 0, _G, 0, _G, 0, _G, 0, _G, 0],
    },
    "deep house": {
        # Kick: four-on-floor with an extra ghost on step 2
        "kick": [_F, 0, _G, 0, _F, 0, 0, 0, _F, 0, _G, 0, _F, 0, 0, 0],
        # Snare: beats 2 & 4, softer and roomy
        "snare": [0, 0, 0, 0, _M, 0, 0, 0, 0, 0, 0, 0, _M, 0, 0, 0],
        # Ride: swinging 8ths (typical deep house ride comping)
        "ride": [_M, 0, _P, 0, _M, 0, _P, 0, _M, 0, _P, 0, _M, 0, _P, 0],
        # Closed hat: sparser, on upbeats only (steps 2,6,10,14)
        "closed_hat": [0, 0, _M, 0, 0, 0, _M, 0, 0, 0, _M, 0, 0, 0, _M, 0],
        # Shaker: light accent on step 9
        "shaker": [0, 0, 0, 0, 0, 0, 0, 0, 0, _P, 0, 0, 0, 0, 0, 0],
        # Rim: replaces snare in sparse sections
        "rim": [0, 0, 0, 0, _P, 0, 0, 0, 0, 0, 0, 0, _P, 0, 0, 0],
    },
    "organic house": {
        # Kick: four-on-floor with anticipation on step 14 (creates forward momentum)
        "kick": [_F, 0, 0, 0, _F, 0, 0, 0, _F, 0, 0, 0, _F, 0, _G, 0],
        # Snare: beats 2 & 4 with ghost on step 10
        "snare": [0, 0, 0, 0, _M, 0, 0, 0, 0, 0, _G, 0, _M, 0, 0, 0],
        # Clap: layered on beat 4 only for organic sparseness
        "clap": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, _P, 0, 0, 0],
        # Hat: sparse, swinging pattern
        "closed_hat": [_M, 0, 0, _G, _M, 0, _G, 0, _M, 0, 0, _G, _M, 0, _G, 0],
        # Open hat: accent on step 7 (upbeat of beat 2)
        "open_hat": [0, 0, 0, 0, 0, 0, 0, _M, 0, 0, 0, 0, 0, 0, 0, 0],
        # Shaker: 16th note groove, softer
        "shaker": [_G, _G, _G, _G, _G, _G, _G, _G, _G, _G, _G, _G, _G, _G, _G, _G],
    },
    "techno": {
        # Kick: driving four-on-floor, hard
        "kick": [_F, 0, 0, 0, _F, 0, 0, 0, _F, 0, 0, 0, _F, 0, 0, 0],
        # Snare: beats 2 & 4, industrial
        "snare": [0, 0, 0, 0, _F, 0, 0, 0, 0, 0, 0, 0, _F, 0, 0, 0],
        # Closed hat: straight 16ths (relentless)
        "closed_hat": [_M, _G, _M, _G, _M, _G, _M, _G, _M, _G, _M, _G, _M, _G, _M, _G],
        # Open hat: step 8 (halfway) for industrial accent
        "open_hat": [0, 0, 0, 0, 0, 0, 0, 0, _M, 0, 0, 0, 0, 0, 0, 0],
        # Ride: off-beat driving pattern
        "ride": [0, 0, _P, 0, 0, 0, _P, 0, 0, 0, _P, 0, 0, 0, _P, 0],
    },
    "melodic techno": {
        # Kick: four-on-floor but slightly softer, more musical
        "kick": [_M, 0, 0, 0, _F, 0, 0, 0, _M, 0, 0, 0, _F, 0, 0, 0],
        # Snare: beats 2 & 4 with ghost anticipations
        "snare": [0, 0, 0, 0, _F, 0, 0, _G, 0, 0, 0, 0, _F, 0, 0, 0],
        # Closed hat: syncopated, not straight
        "closed_hat": [_M, 0, _G, _M, 0, _G, _M, 0, _M, 0, _G, _M, 0, _G, _M, 0],
        # Open hat: two open hats per bar for drama
        "open_hat": [0, 0, 0, 0, 0, 0, 0, _P, 0, 0, 0, 0, 0, 0, _P, 0],
        # Ride: melodic techno often uses ride as main hat
        "ride": [0, _G, 0, _G, 0, _G, 0, _G, 0, _G, 0, _G, 0, _G, 0, _G],
    },
    "afro house": {
        # Kick: offbeat and syncopated — not four-on-floor
        "kick": [_F, 0, 0, _M, 0, 0, _F, 0, 0, _M, 0, 0, _F, 0, 0, 0],
        # Snare: sparse, on beat 3 and anticipated beat 4
        "snare": [0, 0, 0, 0, 0, 0, 0, 0, _M, 0, 0, 0, 0, 0, _M, 0],
        # Clap: call-response with snare
        "clap": [0, 0, 0, 0, _P, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, _P],
        # Closed hat: driving 16ths with accents on African downbeats
        "closed_hat": [_M, _G, _F, _G, _M, _G, _M, _G, _F, _G, _M, _G, _M, _G, _F, _G],
        # Shaker: traditional African groove (emphasizes cross-rhythm)
        "shaker": [_M, 0, _M, 0, 0, _M, 0, _M, _M, 0, _M, 0, 0, _M, 0, _M],
        # Cowbell: classic afro element
        "cowbell": [_P, 0, 0, _P, 0, 0, _P, 0, _P, 0, 0, _P, 0, 0, _P, 0],
    },
    "minimal techno": {
        # Kick: four-on-floor, minimal
        "kick": [_F, 0, 0, 0, _F, 0, 0, 0, _F, 0, 0, 0, _F, 0, 0, 0],
        # Snare: only on beat 4 (very sparse)
        "snare": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, _M, 0, 0, 0],
        # Closed hat: only on upbeats (steps 2,6,10,14)
        "closed_hat": [0, 0, _M, 0, 0, 0, _M, 0, 0, 0, _M, 0, 0, 0, _M, 0],
        # Rim: carries the groove instead of snare
        "rim": [0, _G, 0, _G, _M, _G, 0, _G, 0, _G, 0, _G, _M, _G, 0, _G],
    },
}

VALID_GENRES: frozenset[str] = frozenset(_PATTERNS.keys())

# Humanization offsets in beats (adds subtle timing imperfections)
# Positive = slightly late, negative = slightly early
_HUMANIZE_OFFSETS: dict[str, float] = {
    "kick": 0.0,  # kick stays tight on grid
    "snare": 0.005,  # snare slightly late for natural feel
    "clap": 0.008,
    "closed_hat": 0.003,
    "open_hat": 0.006,
    "ride": 0.004,
    "shaker": 0.002,
    "rim": 0.003,
    "cowbell": 0.001,
    "tom_low": 0.005,
    "tom_mid": 0.005,
    "tom_high": 0.005,
}


class GenerateDrumPattern(MusicalTool):
    """
    Generate a MIDI drum pattern for house and electronic music genres.

    Produces a 16-step (one bar, 4/4, 16th note grid) drum pattern for:
    kick, snare, clap, hi-hats, ride, shaker, and percussion accents.

    Returns a step grid (which steps fire per instrument) and piano roll
    MIDI events. Optionally writes a .mid file.

    Works standalone or chained after suggest_chord_progression + generate_midi_pattern
    to produce a full arrangement.
    """

    @property
    def name(self) -> str:
        return "generate_drum_pattern"

    @property
    def description(self) -> str:
        return (
            "Generate a MIDI drum pattern (kick, snare, hats, clap, ride, percussion) "
            "for house and electronic music genres. "
            "Returns a 16-step grid and piano roll MIDI events ready for DAW import. "
            "Use when the user asks for a drum beat, rhythm pattern, 808 groove, "
            "or wants to add a drum track to their production. "
            f"Supported genres: {', '.join(sorted(VALID_GENRES))}."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="genre",
                type=str,
                description=(
                    f"Music genre for drum pattern style. "
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
                name="humanize",
                type=bool,
                description=(
                    "Apply subtle timing humanization to avoid a robotic feel. " "Default: True."
                ),
                required=False,
                default=True,
            ),
            ToolParameter(
                name="instruments",
                type=list,
                description=(
                    "Optional list of instruments to include. "
                    f"Available: {', '.join(sorted(DRUM_MIDI.keys()))}. "
                    "If omitted, all instruments in the genre pattern are used."
                ),
                required=False,
                default=None,
            ),
            ToolParameter(
                name="output_path",
                type=str,
                description=(
                    "Optional path to write a .mid file (requires midiutil). "
                    "If omitted, only the piano roll JSON is returned."
                ),
                required=False,
                default="",
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        genre: str = (kwargs.get("genre") or "house").strip().lower()
        bpm: int = kwargs.get("bpm") or 124
        bars: int = kwargs.get("bars") or 2
        humanize: bool = kwargs.get("humanize") if kwargs.get("humanize") is not None else True
        instruments: list | None = kwargs.get("instruments")
        output_path: str = (kwargs.get("output_path") or "").strip()

        if genre not in VALID_GENRES:
            return ToolResult(
                success=False,
                error=f"genre must be one of: {', '.join(sorted(VALID_GENRES))}. Got: {genre!r}",
            )
        if not (60 <= bpm <= 180):
            return ToolResult(success=False, error=f"bpm must be between 60 and 180. Got: {bpm}")
        if not (1 <= bars <= 8):
            return ToolResult(success=False, error=f"bars must be between 1 and 8. Got: {bars}")

        pattern = _PATTERNS[genre]

        # Filter to requested instruments
        if instruments:
            invalid = [i for i in instruments if i not in DRUM_MIDI]
            if invalid:
                return ToolResult(
                    success=False,
                    error=f"Unknown instruments: {invalid}. Available: {list(DRUM_MIDI.keys())}",
                )
            pattern = {k: v for k, v in pattern.items() if k in instruments}

        # Build piano roll events across all bars
        beat_per_step = 1.0 / 4.0  # 16th note = 0.25 beats
        events: list[dict] = []
        step_grid: dict[str, list[int]] = {}

        for instrument, steps in pattern.items():
            midi_note = DRUM_MIDI[instrument]
            human_offset = _HUMANIZE_OFFSETS.get(instrument, 0.0) if humanize else 0.0
            full_steps: list[int] = []

            for bar in range(bars):
                bar_beat_offset = bar * 4.0  # 4 beats per bar
                for step_idx, velocity in enumerate(steps):
                    full_steps.append(velocity)
                    if velocity == 0:
                        continue
                    beat_pos = bar_beat_offset + step_idx * beat_per_step + human_offset
                    events.append(
                        {
                            "track": "drums",
                            "instrument": instrument,
                            "note": midi_note,
                            "note_name": instrument,
                            "start": round(beat_pos, 4),
                            "duration": round(beat_per_step * 0.9, 4),  # 90% gate
                            "velocity": velocity,
                            "channel": DRUM_CHANNEL,
                        }
                    )
            step_grid[instrument] = full_steps

        # Sort by start time
        events.sort(key=lambda e: e["start"])

        total_beats = bars * 4.0
        duration_seconds = (total_beats / bpm) * 60.0

        # Optional MIDI file
        midi_file_result: dict[str, Any] = {}
        midi_available = _is_midiutil_available()

        if output_path and midi_available:
            write_result = _write_drum_midi(events=events, bpm=bpm, output_path=output_path)
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
                "bpm": bpm,
                "bars": bars,
                "steps_per_bar": STEPS_PER_BAR,
                "genre": genre,
            },
            metadata={
                "instruments": list(pattern.keys()),
                "instrument_count": len(pattern),
                "event_count": len(events),
                "midi_available": midi_available,
                "humanized": humanize,
                **midi_file_result,
            },
        )


# ---------------------------------------------------------------------------
# MIDI file writer
# ---------------------------------------------------------------------------


def _is_midiutil_available() -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec("midiutil") is not None
    except Exception:
        return False


def _write_drum_midi(events: list[dict], bpm: int, output_path: str) -> dict[str, Any]:
    try:
        from midiutil import MIDIFile  # type: ignore[import]
    except ImportError:
        return {"error": "midiutil not installed (pip install midiutil)"}

    try:
        midi = MIDIFile(1, adjust_origin=True)
        midi.addTempo(0, 0, bpm)
        midi.addTrackName(0, 0, "Drums")

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
