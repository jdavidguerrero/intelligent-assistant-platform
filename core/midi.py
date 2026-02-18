"""
core/midi.py — Pure MIDI note resolution for chord names.

Converts chord name strings (e.g. "Am", "Fmaj7", "C#m7") into lists of
MIDI note numbers. No I/O, no side effects — pure deterministic functions.

Design:
    - Root note + quality → intervals → MIDI pitches
    - Voicing: root position, up to 4 notes, octave 4 (middle C = 60)
    - Supports: major, minor, maj7, m7, 7, dim, sus2, sus4, add9
    - All 12 chromatic roots including enharmonic equivalents

Used by:
    ingestion/ableton.py  — OSC payload construction
    tools/music/suggest_chord_progression.py — chord name source
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# MIDI constants
# ---------------------------------------------------------------------------

_MIDDLE_C = 60  # C4
_OCTAVE = 12

# Root note name → semitone offset from C
_NOTE_SEMITONES: dict[str, int] = {
    "C": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
}

# Chord quality → intervals in semitones from root
_CHORD_INTERVALS: dict[str, list[int]] = {
    # Triads
    "maj": [0, 4, 7],
    "m": [0, 3, 7],
    "dim": [0, 3, 6],
    "aug": [0, 4, 8],
    "sus2": [0, 2, 7],
    "sus4": [0, 5, 7],
    # Seventh chords
    "maj7": [0, 4, 7, 11],
    "m7": [0, 3, 7, 10],
    "7": [0, 4, 7, 10],
    "m7b5": [0, 3, 6, 10],
    "dim7": [0, 3, 6, 9],
    "mM7": [0, 3, 7, 11],
    # Extended / add
    "add9": [0, 4, 7, 14],
    "madd9": [0, 3, 7, 14],
    "9": [0, 4, 7, 10, 14],
    "m9": [0, 3, 7, 10, 14],
}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MidiNote:
    """A single MIDI note with pitch, velocity, and duration in beats."""

    pitch: int  # 0-127
    velocity: int  # 0-127
    start_beat: float  # beat position in the clip
    duration_beats: float  # note duration in beats


@dataclass(frozen=True)
class ChordVoicing:
    """A chord resolved to MIDI pitches."""

    name: str  # original chord name e.g. "Am7"
    root: str  # e.g. "A"
    quality: str  # e.g. "m7"
    pitches: tuple[int, ...]  # MIDI note numbers, ascending


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_chord_name(chord_name: str) -> tuple[str, str]:
    """
    Parse a chord name string into (root, quality).

    Args:
        chord_name: e.g. "Am7", "Fmaj7", "C#", "Bb7", "Gsus4"

    Returns:
        (root, quality) — root is canonical (e.g. "C#"), quality is suffix

    Raises:
        ValueError: if root note is not recognized
    """
    name = chord_name.strip()
    # Try 2-char root first (e.g. "C#", "Bb", "F#")
    if len(name) >= 2 and name[:2] in _NOTE_SEMITONES:
        root = name[:2]
        quality = name[2:] or "maj"
    elif name[:1] in _NOTE_SEMITONES:
        root = name[:1]
        quality = name[1:] or "maj"
    else:
        raise ValueError(f"Cannot parse chord name {chord_name!r} — unknown root note")

    # Normalize bare minor shorthand: "m" prefix without other quality
    if quality == "":
        quality = "maj"

    return root, quality


def resolve_chord(chord_name: str, octave: int = 4) -> ChordVoicing:
    """
    Resolve a chord name to MIDI pitches.

    Args:
        chord_name: e.g. "Am7", "Fmaj7", "C#m", "Bbsus2"
        octave: MIDI octave for root note (default 4 = middle octave)

    Returns:
        ChordVoicing with pitches in ascending order

    Raises:
        ValueError: for unrecognized root or quality
    """
    root, quality = parse_chord_name(chord_name)

    if root not in _NOTE_SEMITONES:
        raise ValueError(f"Unknown root note {root!r} in chord {chord_name!r}")

    # Default unknown quality to major triad
    intervals = _CHORD_INTERVALS.get(quality, _CHORD_INTERVALS["maj"])

    root_midi = _MIDDLE_C + (octave - 4) * _OCTAVE + _NOTE_SEMITONES[root]

    # Build pitches, capping at 127
    pitches = tuple(
        min(root_midi + interval, 127) for interval in intervals if root_midi + interval <= 127
    )

    return ChordVoicing(
        name=chord_name,
        root=root,
        quality=quality,
        pitches=pitches,
    )


# ---------------------------------------------------------------------------
# Chord sequence → MidiNote list
# ---------------------------------------------------------------------------


def chords_to_midi_notes(
    chord_names: list[str],
    beats_per_chord: float = 4.0,
    velocity: int = 90,
    octave: int = 4,
    note_duration_ratio: float = 0.9,
) -> list[MidiNote]:
    """
    Convert a list of chord names to a flat list of MidiNote objects.

    Each chord occupies `beats_per_chord` beats. Notes within a chord
    all share the same start_beat and duration.

    Args:
        chord_names: e.g. ["Am", "F", "C", "G"]
        beats_per_chord: how many beats each chord lasts (default 4 = 1 bar at 4/4)
        velocity: MIDI velocity for all notes (0-127, default 90)
        octave: root octave for voicings (default 4)
        note_duration_ratio: note length as fraction of beats_per_chord (0.9 = legato)

    Returns:
        Flat list of MidiNote objects, sorted by start_beat then pitch

    Raises:
        ValueError: if chord_names is empty or any chord cannot be resolved
    """
    if not chord_names:
        raise ValueError("chord_names must not be empty")
    if not 0 < note_duration_ratio <= 1.0:
        raise ValueError("note_duration_ratio must be in (0, 1]")
    if not 0 < velocity <= 127:
        raise ValueError("velocity must be in (1, 127]")

    notes: list[MidiNote] = []
    note_duration = beats_per_chord * note_duration_ratio

    for i, chord_name in enumerate(chord_names):
        start_beat = i * beats_per_chord
        voicing = resolve_chord(chord_name, octave=octave)
        for pitch in voicing.pitches:
            notes.append(
                MidiNote(
                    pitch=pitch,
                    velocity=velocity,
                    start_beat=start_beat,
                    duration_beats=note_duration,
                )
            )

    return sorted(notes, key=lambda n: (n.start_beat, n.pitch))


def total_clip_beats(chord_names: list[str], beats_per_chord: float = 4.0) -> float:
    """Return total clip length in beats for a given chord sequence."""
    return len(chord_names) * beats_per_chord
