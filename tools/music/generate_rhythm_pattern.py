"""
generate_rhythm_pattern tool — African and Latin percussion rhythm patterns.

Pure computation: no LLM, no DB, no I/O.

Provides authentic rhythmic patterns from:
  - Afrobeat (James Brown / Fela Kuti lineage)
  - Cuban son clave (3-2 and 2-3)
  - Bossanova (Brazilian clave + surdo)
  - Baião (Forró, northeastern Brazil)
  - Songo (Cuban jazz-fusion)
  - Cumbia (Colombian)
  - Candombe (Uruguayan)

Each pattern is encoded as a 16-step (or 32-step for complex patterns)
velocity grid per instrument, same format as generate_drum_pattern.

Musical rationale:
  - Clave patterns are the rhythmic backbone of Cuban music — all
    other instruments are arranged relative to the clave.
  - Baião uses the triangle as timekeeper, zabumba (bass drum) on
    beats 2 and 4 (opposite of house music), and pandeiro for color.
  - Afrobeat is polyrhythmic: each instrument locks to a different
    rhythmic layer, creating interlocking grooves.
"""

from pathlib import Path
from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult

# ---------------------------------------------------------------------------
# MIDI drum map for ethnic percussion
# Using GM equivalents where possible
# ---------------------------------------------------------------------------

PERCUSSION_MIDI: dict[str, int] = {
    # Standard kit
    "kick": 36,
    "snare": 38,
    "clap": 39,
    "closed_hat": 42,
    "open_hat": 46,
    "ride": 51,
    # Latin / Afro percussion (GM equivalents)
    "clave": 75,  # Claves
    "cowbell": 56,  # Cowbell
    "conga_low": 64,  # Low Conga
    "conga_mid": 63,  # Open High Conga
    "conga_high": 62,  # Mute High Conga
    "bongo_low": 61,  # Low Bongo
    "bongo_high": 60,  # High Bongo
    "shaker": 70,  # Maracas
    "agogo_low": 68,  # Low Agogo
    "agogo_high": 67,  # High Agogo
    "triangle": 80,  # Triangle
    "tambourine": 54,  # Tambourine
    "surdo": 36,  # Bass drum (mapped to kick)
    "zabumba": 36,  # Brazilian bass drum
    "pandeiro": 54,  # Brazilian frame drum → tambourine
    "talking_drum": 64,  # Mapped to low conga
    "djembe": 63,
    "dundun": 36,
}

DRUM_CHANNEL: int = 9
STEPS_PER_BAR: int = 16

_F, _M, _P, _G = 100, 80, 65, 45

# ---------------------------------------------------------------------------
# Rhythm patterns — 16 steps = 1 bar in 4/4
# ---------------------------------------------------------------------------

_RHYTHM_PATTERNS: dict[str, dict[str, list[int]]] = {
    # -----------------------------------------------------------------------
    # Son Clave 3-2 (the most common clave in Cuban music)
    # "3" side: beats on 1, 2.5, 4 (steps 0, 4, 6, 11)
    # "2" side: beats on 1, 3 (steps 0, 8, 12)
    # This is ONE bar — the full clave spans 2 bars in practice
    # -----------------------------------------------------------------------
    "son_clave_3_2": {
        # Clave itself: the defining pattern
        "clave": [_F, 0, 0, 0, _F, 0, _F, 0, 0, 0, 0, _F, _F, 0, 0, 0],
        # Congas: tumbao pattern
        "conga_low": [0, 0, 0, _M, 0, 0, 0, _M, 0, 0, 0, _M, 0, 0, 0, _M],
        "conga_mid": [_P, 0, _M, 0, 0, _P, 0, _F, 0, _P, 0, 0, _M, 0, _P, 0],
        # Bongo: martillo (hammer) pattern — driving 8th notes
        "bongo_high": [_M, 0, _G, 0, _M, 0, _G, 0, _M, 0, _G, 0, _M, 0, _G, 0],
        # Cowbell: marking clave-adjacent accents
        "cowbell": [_M, 0, 0, 0, 0, 0, _P, 0, _M, 0, 0, 0, 0, 0, _M, 0],
        # Shaker/maracas: driving 8th notes
        "shaker": [_G, 0, _G, 0, _G, 0, _G, 0, _G, 0, _G, 0, _G, 0, _G, 0],
    },
    # -----------------------------------------------------------------------
    # Son Clave 2-3 (reverse of 3-2 — resolves differently)
    # -----------------------------------------------------------------------
    "son_clave_2_3": {
        "clave": [_F, 0, 0, 0, _F, 0, 0, 0, 0, 0, 0, _F, 0, _F, 0, _F],
        "conga_low": [0, 0, 0, _M, 0, 0, 0, _M, 0, 0, 0, _M, 0, 0, 0, _M],
        "conga_mid": [_P, 0, _M, 0, 0, _P, 0, _F, 0, _P, 0, 0, _M, 0, _P, 0],
        "bongo_high": [_M, 0, _G, 0, _M, 0, _G, 0, _M, 0, _G, 0, _M, 0, _G, 0],
        "cowbell": [_M, 0, 0, _P, 0, 0, _M, 0, 0, 0, _P, 0, _M, 0, 0, 0],
        "shaker": [_G, 0, _G, 0, _G, 0, _G, 0, _G, 0, _G, 0, _G, 0, _G, 0],
    },
    # -----------------------------------------------------------------------
    # Afrobeat (inspired by Tony Allen / Fela Kuti)
    # Polyrhythmic interlocking layers — no single instrument dominates
    # -----------------------------------------------------------------------
    "afrobeat": {
        # Kick: syncopated — avoids beats 1 and 3 (anti-house)
        "kick": [0, 0, _M, 0, 0, _F, 0, 0, 0, _M, 0, 0, _F, 0, 0, _M],
        # Snare: ghost-heavy, African 3-against-4 feel
        "snare": [0, _G, 0, 0, _M, 0, _G, 0, 0, _G, 0, _M, 0, 0, _G, 0],
        # Hi-hat: straight 16ths as timekeeper (unlike house)
        "closed_hat": [_M, _G, _M, _G, _M, _G, _M, _G, _M, _G, _M, _G, _M, _G, _M, _G],
        # Conga: low provides the bass anchor
        "conga_low": [_F, 0, 0, _M, 0, 0, _F, 0, _M, 0, 0, _F, 0, _M, 0, 0],
        # Conga: high counterpoint
        "conga_mid": [0, _M, _G, 0, _M, _G, 0, _F, _G, 0, _M, 0, _G, _F, 0, _G],
        # Agogo: the clave equivalent in afrobeat
        "agogo_high": [_M, 0, 0, _M, 0, _M, 0, 0, _M, 0, _M, 0, 0, _M, 0, 0],
        # Shaker: fills in the 8th-note groove
        "shaker": [_G, 0, _G, 0, _G, 0, _G, 0, _G, 0, _G, 0, _G, 0, _G, 0],
    },
    # -----------------------------------------------------------------------
    # Bossanova (Brazilian samba + jazz fusion)
    # Surdo on beat 3 (not 1), pandeiro drives 8ths
    # -----------------------------------------------------------------------
    "bossanova": {
        # Surdo (bass drum): on beat 2 (step 4) and beat 4 (step 12)
        # Classic bossanova doesn't have four-on-floor
        "surdo": [0, 0, 0, 0, _F, 0, 0, 0, 0, 0, 0, 0, _F, 0, 0, 0],
        # Snare: rim click on beats 2 and 4 — very light
        "snare": [0, 0, 0, 0, _P, 0, 0, 0, 0, 0, 0, 0, _P, 0, 0, 0],
        # Pandeiro: continuous 8th note groove
        "pandeiro": [_M, 0, _M, 0, _M, 0, _M, 0, _M, 0, _M, 0, _M, 0, _M, 0],
        # Agogo (or triangle): clave-derived accent
        "agogo_high": [_P, 0, 0, _M, 0, _P, 0, _M, _P, 0, 0, _M, 0, _P, 0, 0],
        # Shaker: subtle 16ths
        "shaker": [_G, _G, _G, _G, _G, _G, _G, _G, _G, _G, _G, _G, _G, _G, _G, _G],
    },
    # -----------------------------------------------------------------------
    # Baião (northeastern Brazilian — forró rhythm)
    # Triangle is the timekeeper, zabumba on beats 2 and 4
    # -----------------------------------------------------------------------
    "baiao": {
        # Zabumba (large bass drum): beat 2 and beat 4 — OFF the 1
        "zabumba": [0, 0, 0, 0, _F, 0, 0, 0, 0, 0, 0, 0, _F, 0, 0, 0],
        # Triangle: continuous driving 8th notes — the heartbeat of baião
        "triangle": [_M, 0, _M, 0, _M, 0, _M, 0, _M, 0, _M, 0, _M, 0, _M, 0],
        # Pandeiro: syncopated, adds the swing
        "pandeiro": [_M, _G, 0, _M, _G, _M, _G, 0, _M, _G, 0, _M, _G, _M, _G, 0],
        # Snare: xote variation — occasional accent
        "snare": [0, 0, 0, _G, 0, 0, _P, 0, 0, 0, 0, _G, 0, 0, _P, 0],
    },
    # -----------------------------------------------------------------------
    # Songo (Cuban jazz-fusion — developed by Los Van Van in the 1970s)
    # Blends clave with jazz drumkit
    # -----------------------------------------------------------------------
    "songo": {
        # Kick: syncopated, doesn't follow four-on-floor
        "kick": [_F, 0, 0, 0, 0, _M, 0, 0, _F, 0, 0, _G, 0, _F, 0, 0],
        # Snare: ghost-heavy, jazz-influenced
        "snare": [0, _G, 0, _M, _G, 0, _G, _F, 0, _G, _M, 0, _G, 0, _G, _M],
        # Hi-hat: driving 8ths (jazz ride pattern adapted to hi-hat)
        "closed_hat": [_M, 0, _M, 0, _M, 0, _M, 0, _M, 0, _M, 0, _M, 0, _M, 0],
        # Conga: tumbao adapted
        "conga_low": [0, 0, 0, _M, 0, 0, _M, 0, 0, 0, 0, _F, 0, 0, _M, 0],
        "conga_mid": [_P, 0, _M, 0, _P, _M, 0, _F, _P, 0, _M, 0, _P, _F, 0, _M],
        # Cowbell: marking the clave
        "cowbell": [_M, 0, 0, 0, _P, 0, _M, 0, 0, _P, 0, _M, 0, 0, _P, 0],
    },
    # -----------------------------------------------------------------------
    # Cumbia (Colombian — the most African-influenced Colombian rhythm)
    # -----------------------------------------------------------------------
    "cumbia": {
        # Kick: on beats 1 and 3
        "kick": [_F, 0, 0, 0, 0, 0, 0, 0, _F, 0, 0, 0, 0, 0, 0, 0],
        # Snare: anticipates beat 2 (classic cumbia accent)
        "snare": [0, 0, 0, _M, _F, 0, 0, 0, 0, 0, 0, _M, _F, 0, 0, 0],
        # Maracas: continuous 8ths, the defining timekeeping instrument
        "shaker": [_M, _G, _M, _G, _M, _G, _M, _G, _M, _G, _M, _G, _M, _G, _M, _G],
        # Tambora (similar to conga low): bass accent
        "conga_low": [_F, 0, 0, _M, 0, 0, _F, 0, _F, 0, 0, _M, 0, 0, _F, 0],
        # Llamador: the high-pitched calling drum
        "conga_high": [0, _M, 0, _P, _M, 0, _P, 0, 0, _M, 0, _P, _M, 0, _P, 0],
    },
    # -----------------------------------------------------------------------
    # Candombe (Uruguayan — three drum ensemble: chico, repique, piano)
    # The foundation of Afro-Uruguayan music
    # -----------------------------------------------------------------------
    "candombe": {
        # Chico (high drum): constant 8th-note pulse — the timekeeper
        "conga_high": [_F, 0, _F, 0, _F, 0, _F, 0, _F, 0, _F, 0, _F, 0, _F, 0],
        # Repique (mid drum): improvised but follows this base pattern
        "conga_mid": [_F, 0, 0, _M, _F, 0, 0, _M, _F, 0, _M, 0, 0, _F, 0, _M],
        # Piano (low drum — lowest, rhythmic bass voice)
        "conga_low": [_F, 0, 0, 0, 0, _M, 0, 0, _F, 0, 0, 0, _M, 0, 0, _F],
        # Tambourine: shaker role
        "tambourine": [_G, 0, _G, 0, _G, 0, _G, 0, _G, 0, _G, 0, _G, 0, _G, 0],
    },
}

VALID_RHYTHMS: frozenset[str] = frozenset(_RHYTHM_PATTERNS.keys())


class GenerateRhythmPattern(MusicalTool):
    """
    Generate African and Latin percussion rhythm patterns as MIDI events.

    Provides authentic patterns from afrobeat, Cuban son clave (3-2 and 2-3),
    bossanova, baião, songo, cumbia, and candombe.

    Returns a 16-step grid and piano roll MIDI events for all percussion
    instruments in the pattern. Use for adding authentic world rhythm
    to electronic productions.
    """

    @property
    def name(self) -> str:
        return "generate_rhythm_pattern"

    @property
    def description(self) -> str:
        return (
            "Generate authentic African and Latin percussion rhythm patterns as MIDI. "
            "Patterns include: Afrobeat, Cuban Son Clave (3-2 and 2-3), Bossanova, "
            "Baião, Songo, Cumbia, and Candombe. "
            "Returns step grid and piano roll MIDI events with congas, bongos, clave, "
            "cowbell, shaker, triangle, and other ethnic percussion. "
            "Use when the user asks for African, Latin, or world percussion patterns, "
            "or wants to add polyrhythmic groove to an electronic production. "
            f"Available rhythms: {', '.join(sorted(VALID_RHYTHMS))}."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="rhythm",
                type=str,
                description=(
                    f"Rhythm style. Options: {', '.join(sorted(VALID_RHYTHMS))}. "
                    "Default: 'afrobeat'."
                ),
                required=False,
                default="afrobeat",
            ),
            ToolParameter(
                name="bpm",
                type=int,
                description=(
                    "Tempo in BPM (60–160). Default: 120. "
                    "Note: baião typically runs 80–110, afrobeat 90–105, cumbia 80–100."
                ),
                required=False,
                default=120,
            ),
            ToolParameter(
                name="bars",
                type=int,
                description="Number of bars to generate (1–8). Default: 2.",
                required=False,
                default=2,
            ),
            ToolParameter(
                name="instruments",
                type=list,
                description=(
                    "Optional list of instruments to include. "
                    f"Available: {', '.join(sorted(PERCUSSION_MIDI.keys()))}. "
                    "If omitted, all instruments in the rhythm pattern are used."
                ),
                required=False,
                default=None,
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
        rhythm: str = (kwargs.get("rhythm") or "afrobeat").strip().lower()
        bpm: int = kwargs.get("bpm") or 120
        bars: int = kwargs.get("bars") or 2
        instruments: list | None = kwargs.get("instruments")
        output_path: str = (kwargs.get("output_path") or "").strip()

        if rhythm not in VALID_RHYTHMS:
            return ToolResult(
                success=False,
                error=f"rhythm must be one of: {', '.join(sorted(VALID_RHYTHMS))}. Got: {rhythm!r}",
            )
        if not (60 <= bpm <= 160):
            return ToolResult(success=False, error=f"bpm must be between 60 and 160. Got: {bpm}")
        if not (1 <= bars <= 8):
            return ToolResult(success=False, error=f"bars must be between 1 and 8. Got: {bars}")

        pattern = _RHYTHM_PATTERNS[rhythm]

        if instruments:
            invalid = [i for i in instruments if i not in PERCUSSION_MIDI]
            if invalid:
                return ToolResult(
                    success=False,
                    error=f"Unknown instruments: {invalid}. Available: {list(PERCUSSION_MIDI.keys())}",
                )
            pattern = {k: v for k, v in pattern.items() if k in instruments}

        beat_per_step = 1.0 / 4.0
        events: list[dict] = []
        step_grid: dict[str, list[int]] = {}

        for instrument, steps in pattern.items():
            midi_note = PERCUSSION_MIDI[instrument]
            full_steps: list[int] = []

            for bar in range(bars):
                bar_beat_offset = bar * 4.0
                for step_idx, velocity in enumerate(steps):
                    full_steps.append(velocity)
                    if velocity == 0:
                        continue
                    beat_pos = bar_beat_offset + step_idx * beat_per_step
                    events.append(
                        {
                            "track": "rhythm",
                            "instrument": instrument,
                            "note": midi_note,
                            "note_name": instrument,
                            "start": round(beat_pos, 4),
                            "duration": round(beat_per_step * 0.85, 4),
                            "velocity": velocity,
                            "channel": DRUM_CHANNEL,
                        }
                    )
            step_grid[instrument] = full_steps

        events.sort(key=lambda e: e["start"])
        total_beats = bars * 4.0
        duration_seconds = (total_beats / bpm) * 60.0

        midi_file_result: dict[str, Any] = {}
        midi_available = _is_midiutil_available()

        if output_path and midi_available:
            write_result = _write_percussion_midi(events=events, bpm=bpm, output_path=output_path)
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
                "rhythm": rhythm,
            },
            metadata={
                "instruments": list(pattern.keys()),
                "instrument_count": len(pattern),
                "event_count": len(events),
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


def _write_percussion_midi(events: list[dict], bpm: int, output_path: str) -> dict[str, Any]:
    try:
        from midiutil import MIDIFile  # type: ignore[import]
    except ImportError:
        return {"error": "midiutil not installed"}

    try:
        midi = MIDIFile(1, adjust_origin=True)
        midi.addTempo(0, 0, bpm)
        midi.addTrackName(0, 0, "Rhythm")

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
