"""
core/music_theory/scales.py — Pure scale and diatonic chord functions.

Constants replicated from tools/music/theory.py so that core/ remains
independent of tools/ (dependency direction: core/ ← tools/, never →).

Exports:
    NOTE_NAMES              12-element tuple of chromatic note names (sharps)
    SCALE_FORMULAS          semitone intervals for each mode
    CHORD_INTERVALS         semitone intervals for each chord quality
    DIATONIC_QUALITIES      chord qualities per scale degree, per mode
    ROMAN_NUMERALS          roman numeral labels per degree, per mode
    VOICING_UPGRADES        triad → seventh/extended upgrades per voicing style

    get_scale_notes(root, mode) → tuple[str, ...]
    get_diatonic_chords(root, mode, voicing) → tuple[Chord, ...]
    get_pitch_classes(root, mode) → frozenset[int]
    note_to_pitch_class(note) → int
    pitch_class_to_note(pc) → str
    build_chord_midi(root, quality, octave) → tuple[int, ...]
"""

from __future__ import annotations

from core.music_theory.types import Chord

# ---------------------------------------------------------------------------
# Chromatic pitch classes
# ---------------------------------------------------------------------------

NOTE_NAMES: tuple[str, ...] = (
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "A#",
    "B",
)

# Preferred flat spellings for display
ENHARMONIC: dict[str, str] = {
    "C#": "Db",
    "D#": "Eb",
    "F#": "Gb",
    "G#": "Ab",
    "A#": "Bb",
}

# Input normalisation: flat → sharp
FLAT_TO_SHARP: dict[str, str] = {v: k for k, v in ENHARMONIC.items()}

# ---------------------------------------------------------------------------
# Scale formulas (semitone intervals from root)
# Replicated from tools/music/theory.py — core/ cannot import from tools/
# ---------------------------------------------------------------------------

SCALE_FORMULAS: dict[str, tuple[int, ...]] = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "natural minor": (0, 2, 3, 5, 7, 8, 10),
    "harmonic minor": (0, 2, 3, 5, 7, 8, 11),
    "melodic minor": (0, 2, 3, 5, 7, 9, 11),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "pentatonic minor": (0, 3, 5, 7, 10),
    "pentatonic major": (0, 2, 4, 7, 9),
}

# ---------------------------------------------------------------------------
# Chord interval formulas (semitones from root)
# ---------------------------------------------------------------------------

CHORD_INTERVALS: dict[str, tuple[int, ...]] = {
    # Triads
    "major": (0, 4, 7),
    "minor": (0, 3, 7),
    "dim": (0, 3, 6),
    "aug": (0, 4, 8),
    "sus2": (0, 2, 7),
    "sus4": (0, 5, 7),
    # Sevenths
    "maj7": (0, 4, 7, 11),
    "min7": (0, 3, 7, 10),
    "dom7": (0, 4, 7, 10),
    "dim7": (0, 3, 6, 9),
    "halfdim7": (0, 3, 6, 10),
    "minmaj7": (0, 3, 7, 11),
    # Extended
    "maj9": (0, 4, 7, 11, 14),
    "min9": (0, 3, 7, 10, 14),
    "dom9": (0, 4, 7, 10, 14),
    "add9": (0, 4, 7, 14),
    "minadd9": (0, 3, 7, 14),
}

# ---------------------------------------------------------------------------
# Diatonic chord qualities per scale degree (0-indexed)
# ---------------------------------------------------------------------------

DIATONIC_QUALITIES: dict[str, tuple[str, ...]] = {
    "major": ("major", "minor", "minor", "major", "major", "minor", "dim"),
    "natural minor": ("minor", "dim", "major", "minor", "minor", "major", "major"),
    "harmonic minor": ("minor", "dim", "aug", "minor", "major", "major", "dim"),
    "dorian": ("minor", "minor", "major", "major", "minor", "dim", "major"),
}

ROMAN_NUMERALS: dict[str, tuple[str, ...]] = {
    "major": ("I", "ii", "iii", "IV", "V", "vi", "vii°"),
    "natural minor": ("i", "ii°", "III", "iv", "v", "VI", "VII"),
    "harmonic minor": ("i", "ii°", "III+", "iv", "V", "VI", "vii°"),
    "dorian": ("i", "ii", "III", "IV", "v", "vi°", "VII"),
}

# ---------------------------------------------------------------------------
# Voicing upgrades: triad quality → seventh/extended chord quality
# ---------------------------------------------------------------------------

VOICING_UPGRADES: dict[str, dict[str, str]] = {
    "extended": {
        "major": "maj7",
        "minor": "min7",
        "dim": "halfdim7",
    },
    "seventh": {
        "major": "maj7",
        "minor": "min7",
        "dim": "dim7",
    },
    "triads": {
        "major": "major",
        "minor": "minor",
        "dim": "dim",
    },
}

# Human-readable chord name suffixes
_CHORD_SUFFIX: dict[str, str] = {
    "major": "",
    "minor": "m",
    "dim": "dim",
    "aug": "aug",
    "sus2": "sus2",
    "sus4": "sus4",
    "maj7": "maj7",
    "min7": "m7",
    "dom7": "7",
    "dim7": "dim7",
    "halfdim7": "m7b5",
    "minmaj7": "mMaj7",
    "maj9": "maj9",
    "min9": "m9",
    "dom9": "9",
    "add9": "add9",
    "minadd9": "madd9",
}


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def normalize_note(note: str) -> str:
    """Normalize a note name to sharp notation.

    Args:
        note: Note name, e.g. "Bb", "C#", "g"

    Returns:
        Canonical sharp-notation name, e.g. "A#", "C#", "G"

    Raises:
        ValueError: If note is not a recognized pitch class
    """
    note = note.strip().capitalize()
    if note in FLAT_TO_SHARP:
        note = FLAT_TO_SHARP[note]
    if note not in NOTE_NAMES:
        raise ValueError(f"Unknown note {note!r}. Valid: {list(NOTE_NAMES)}")
    return note


def note_to_pitch_class(note: str) -> int:
    """Return the MIDI pitch class (0–11) of a note name.

    Args:
        note: Note name, e.g. "A", "C#", "Bb"

    Returns:
        Pitch class integer 0 (C) through 11 (B)

    Raises:
        ValueError: If note is unrecognized
    """
    return NOTE_NAMES.index(normalize_note(note))


def pitch_class_to_note(pc: int) -> str:
    """Return the canonical (sharp) note name for a pitch class.

    Args:
        pc: Pitch class integer 0–11

    Returns:
        Note name string

    Raises:
        ValueError: If pc is out of range
    """
    if not (0 <= pc <= 11):
        raise ValueError(f"Pitch class must be in [0, 11], got {pc}")
    return NOTE_NAMES[pc]


def build_chord_midi(
    root: str,
    quality: str,
    octave: int = 4,
) -> tuple[int, ...]:
    """Build MIDI pitch numbers for a chord (root position).

    Args:
        root:    Root note name, e.g. "A", "C#"
        quality: Chord quality from CHORD_INTERVALS
        octave:  Base octave (4 = middle C octave)

    Returns:
        Tuple of MIDI pitch numbers

    Raises:
        ValueError: If root or quality is unrecognized
    """
    root_norm = normalize_note(root)
    if quality not in CHORD_INTERVALS:
        raise ValueError(f"Unknown chord quality {quality!r}. Valid: {sorted(CHORD_INTERVALS)}")
    root_pc = NOTE_NAMES.index(root_norm)
    root_midi = (octave + 1) * 12 + root_pc
    return tuple(min(root_midi + interval, 127) for interval in CHORD_INTERVALS[quality])


def _chord_display_name(root: str, quality: str) -> str:
    """Build a human-readable chord name, using flat notation where conventional."""
    display_root = ENHARMONIC.get(root, root)
    suffix = _CHORD_SUFFIX.get(quality, quality)
    return f"{display_root}{suffix}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_scale_notes(root: str, mode: str = "natural minor") -> tuple[str, ...]:
    """Return ordered note names for a diatonic scale.

    Args:
        root: Root note, e.g. "A", "C#", "Bb"
        mode: Mode name — must be a key in SCALE_FORMULAS

    Returns:
        Tuple of note name strings (7 elements for diatonic modes)

    Raises:
        ValueError: If root or mode is unrecognized

    Examples:
        >>> get_scale_notes("A", "natural minor")
        ('A', 'B', 'C', 'D', 'E', 'F', 'G')
        >>> get_scale_notes("C", "major")
        ('C', 'D', 'E', 'F', 'G', 'A', 'B')
    """
    root_norm = normalize_note(root)
    if mode not in SCALE_FORMULAS:
        raise ValueError(f"Unknown mode {mode!r}. Valid: {sorted(SCALE_FORMULAS)}")
    root_idx = NOTE_NAMES.index(root_norm)
    formula = SCALE_FORMULAS[mode]
    return tuple(NOTE_NAMES[(root_idx + interval) % 12] for interval in formula)


def get_pitch_classes(root: str, mode: str = "natural minor") -> frozenset[int]:
    """Return the set of MIDI pitch classes (0–11) in a scale.

    Args:
        root: Root note, e.g. "A"
        mode: Mode name

    Returns:
        Frozenset of pitch class integers

    Examples:
        >>> get_pitch_classes("C", "major")
        frozenset({0, 2, 4, 5, 7, 9, 11})
    """
    notes = get_scale_notes(root, mode)
    return frozenset(NOTE_NAMES.index(n) for n in notes)


def get_diatonic_chords(
    root: str,
    mode: str = "natural minor",
    voicing: str = "triads",
) -> tuple[Chord, ...]:
    """Return all 7 diatonic chords for a key as Chord objects.

    Args:
        root:    Root note of the key, e.g. "A", "C#"
        mode:    Scale mode — must be a key in DIATONIC_QUALITIES
        voicing: Voicing style: "triads", "seventh", or "extended"

    Returns:
        Tuple of 7 Chord objects, one per scale degree (I through VII)

    Raises:
        ValueError: If root, mode, or voicing is unrecognized

    Examples:
        >>> chords = get_diatonic_chords("A", "natural minor")
        >>> [c.name for c in chords]
        ['Am', 'Bdim', 'C', 'Dm', 'Em', 'F', 'G']
    """
    if voicing not in VOICING_UPGRADES:
        raise ValueError(f"Unknown voicing {voicing!r}. Valid: {sorted(VOICING_UPGRADES)}")
    if mode not in DIATONIC_QUALITIES:
        valid = sorted(DIATONIC_QUALITIES)
        raise ValueError(f"Unknown mode for diatonic chords {mode!r}. Valid: {valid}")

    scale_notes = get_scale_notes(root, mode)
    base_qualities = DIATONIC_QUALITIES[mode]
    romans = ROMAN_NUMERALS.get(mode, ROMAN_NUMERALS["natural minor"])
    upgrades = VOICING_UPGRADES[voicing]

    chords: list[Chord] = []
    for degree, (note, base_quality) in enumerate(zip(scale_notes, base_qualities, strict=False)):
        quality = upgrades.get(base_quality, base_quality)
        name = _chord_display_name(note, quality)
        midi_notes = build_chord_midi(note, quality)
        roman = romans[degree] if degree < len(romans) else str(degree + 1)
        chords.append(
            Chord(
                root=note,
                quality=quality,
                name=name,
                roman=roman,
                degree=degree,
                midi_notes=midi_notes,
            )
        )
    return tuple(chords)
