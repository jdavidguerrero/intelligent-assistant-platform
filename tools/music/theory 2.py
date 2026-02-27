"""
Music theory constants and pure functions.

Pure module — no I/O, no side effects, no randomness.
Used by suggest_chord_progression and generate_midi_pattern.
Can be compiled for embedded targets (OpenDock Brain / Teensy).

Conventions:
  - Notes are referenced by MIDI pitch class: C=0, C#=1, ..., B=11
  - Octave 4 anchor: C4 = MIDI 60, A4 = MIDI 69
  - Chord names use sharps (#) except for enharmonic minor keys (Bb, Eb, Ab)
  - Roman numeral analysis uses uppercase for major, lowercase for minor, ° for dim
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Chromatic pitch classes
# ---------------------------------------------------------------------------

# Canonical note names (sharps)
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

# Enharmonic equivalents — flat spellings for common notes
ENHARMONIC: dict[str, str] = {
    "C#": "Db",
    "D#": "Eb",
    "F#": "Gb",
    "G#": "Ab",
    "A#": "Bb",
}

# Reverse map: flat → sharp (for input normalization)
FLAT_TO_SHARP: dict[str, str] = {v: k for k, v in ENHARMONIC.items()}

# ---------------------------------------------------------------------------
# Scale formulas (semitone intervals from root)
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
    # Seventh chords
    "maj7": (0, 4, 7, 11),
    "min7": (0, 3, 7, 10),
    "dom7": (0, 4, 7, 10),
    "dim7": (0, 3, 6, 9),
    "halfdim7": (0, 3, 6, 10),
    "minmaj7": (0, 3, 7, 11),
    # Extended (for organic/melodic house)
    "maj9": (0, 4, 7, 11, 14),
    "min9": (0, 3, 7, 10, 14),
    "dom9": (0, 4, 7, 10, 14),
    "add9": (0, 4, 7, 14),
    "minadd9": (0, 3, 7, 14),
}

# Chord suffix → interval key (for name parsing)
CHORD_SUFFIX_MAP: dict[str, str] = {
    "maj7": "maj7",
    "m7": "min7",
    "min7": "min7",
    "7": "dom7",
    "dim7": "dim7",
    "ø7": "halfdim7",
    "m7b5": "halfdim7",
    "aug": "aug",
    "sus2": "sus2",
    "sus4": "sus4",
    "maj9": "maj9",
    "m9": "min9",
    "9": "dom9",
    "add9": "add9",
    "madd9": "minadd9",
    "m": "minor",
    "min": "minor",
    "dim": "dim",
    "": "major",  # bare root = major
}

# ---------------------------------------------------------------------------
# Diatonic chord qualities per scale degree (1-indexed)
# Index 0 = degree I, index 6 = degree VII
# ---------------------------------------------------------------------------

DIATONIC_QUALITIES: dict[str, tuple[str, ...]] = {
    "major": ("major", "minor", "minor", "major", "major", "minor", "dim"),
    "natural minor": ("minor", "dim", "major", "minor", "minor", "major", "major"),
    "harmonic minor": ("minor", "dim", "aug", "minor", "major", "major", "dim"),
    "dorian": ("minor", "minor", "major", "major", "minor", "dim", "major"),
}

# Roman numeral labels per degree, per mode
# uppercase = major, lowercase = minor, °  = diminished
ROMAN_NUMERALS: dict[str, tuple[str, ...]] = {
    "major": ("I", "ii", "iii", "IV", "V", "vi", "vii°"),
    "natural minor": ("i", "ii°", "III", "iv", "v", "VI", "VII"),
    "harmonic minor": ("i", "ii°", "III+", "iv", "V", "VI", "vii°"),
    "dorian": ("i", "ii", "III", "IV", "v", "vi°", "VII"),
}

# ---------------------------------------------------------------------------
# Mood → preferred scale degrees (weights, higher = more likely to appear)
# ---------------------------------------------------------------------------

MOOD_DEGREE_WEIGHTS: dict[str, dict[int, int]] = {
    "dark": {0: 3, 3: 2, 5: 2, 6: 1},  # i, iv, VI, VII
    "euphoric": {0: 3, 3: 2, 4: 2, 5: 1},  # I, IV, V, vi (in major)
    "tense": {0: 2, 1: 2, 4: 3, 6: 2},  # i, ii°, V, vii° (leading tension)
    "dreamy": {0: 2, 2: 2, 5: 3, 3: 1},  # i, III, VI, iv (floating)
    "neutral": {0: 2, 2: 1, 3: 2, 5: 2},  # balanced
}

# ---------------------------------------------------------------------------
# Genre → canonical progressions (as scale degree indices, 0-based)
# ---------------------------------------------------------------------------

GENRE_PROGRESSIONS: dict[str, list[list[int]]] = {
    "organic house": [
        [0, 5, 2, 6],  # i - VI - III - VII (most common)
        [0, 3, 6, 2],  # i - iv - VII - III
        [0, 5, 3, 6],  # i - VI - iv - VII
        [0, 2, 5, 3],  # i - III - VI - iv
    ],
    "melodic house": [
        [0, 5, 2, 6],  # i - VI - III - VII
        [0, 3, 2, 6],  # i - iv - III - VII
        [5, 0, 3, 4],  # VI - i - iv - v
    ],
    "progressive house": [
        [0, 4, 5, 3],  # i - v - VI - iv
        [0, 5, 3, 4],  # i - VI - iv - v
        [0, 2, 5, 4],  # i - III - VI - v
    ],
    "deep house": [
        [0, 5, 3, 6],  # i - VI - iv - VII
        [0, 3, 5, 4],  # i - iv - VI - v
    ],
    "techno": [
        [0, 6, 0, 5],  # i - VII - i - VI  (repetitive, hypnotic)
        [0, 3, 0, 4],  # i - iv - i - v
    ],
    "acid": [
        [0, 0, 5, 6],  # i - i - VI - VII (minimal, two bar loop)
        [0, 6, 5, 0],  # i - VII - VI - i
    ],
}

# Voicing styles per genre (which chord types to use)
GENRE_VOICING: dict[str, str] = {
    "organic house": "extended",  # maj7, min7, add9 preferred
    "melodic house": "extended",
    "progressive house": "seventh",  # 7th chords, some extensions
    "deep house": "seventh",
    "techno": "triads",  # raw triads, sometimes power chords
    "acid": "triads",
}

# Upgrade triads to extended versions by quality
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

# ---------------------------------------------------------------------------
# MIDI constants
# ---------------------------------------------------------------------------

# MIDI note 60 = C4 (middle C)
MIDI_C4: int = 60

# Octave anchor for chord voicing (left hand / pads range)
DEFAULT_VOICING_OCTAVE: int = 4

# Velocity defaults by role
VELOCITY_DEFAULTS: dict[str, int] = {
    "chord": 80,
    "bass": 95,
    "melody": 100,
    "pad": 65,
}

# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------


def normalize_note(note: str) -> str:
    """
    Normalize a note name to sharp notation (canonical form).

    Converts flat spellings to sharps: "Bb" → "A#", "Eb" → "D#".
    Returns the note capitalized.

    Args:
        note: Note name string (e.g., "Bb", "C#", "g")

    Returns:
        Normalized note name in sharp notation (e.g., "A#", "C#", "G")

    Raises:
        ValueError: If note is not a recognized pitch class name
    """
    note = note.strip().capitalize()
    # Handle double-char flats: Bb → A#
    if note in FLAT_TO_SHARP:
        note = FLAT_TO_SHARP[note]
    if note not in NOTE_NAMES:
        raise ValueError(f"Unknown note: {note!r}. Valid: {list(NOTE_NAMES)}")
    return note


def note_to_midi(note: str, octave: int = DEFAULT_VOICING_OCTAVE) -> int:
    """
    Convert a note name + octave to a MIDI pitch number.

    Args:
        note: Note name (e.g., "A#", "Bb", "C")
        octave: Octave number (4 = middle C octave)

    Returns:
        MIDI pitch number (0-127)

    Raises:
        ValueError: If note is unrecognized or resulting MIDI pitch is out of range
    """
    note = normalize_note(note)
    pitch_class = NOTE_NAMES.index(note)
    midi = (octave + 1) * 12 + pitch_class
    if not (0 <= midi <= 127):
        raise ValueError(f"MIDI pitch {midi} out of range [0, 127]")
    return midi


def midi_to_note(midi: int) -> tuple[str, int]:
    """
    Convert a MIDI pitch number to (note_name, octave).

    Args:
        midi: MIDI pitch number (0-127)

    Returns:
        Tuple of (note_name_sharp, octave)

    Raises:
        ValueError: If midi is out of range [0, 127]
    """
    if not (0 <= midi <= 127):
        raise ValueError(f"MIDI pitch {midi} out of range [0, 127]")
    octave = (midi // 12) - 1
    pitch_class = midi % 12
    return NOTE_NAMES[pitch_class], octave


def build_scale(root: str, mode: str = "natural minor") -> list[str]:
    """
    Build a diatonic scale from root + mode.

    Args:
        root: Root note name (e.g., "A", "C#", "Bb")
        mode: Scale mode name (see SCALE_FORMULAS keys)

    Returns:
        List of note names (length = number of scale degrees, e.g., 7 for major)

    Raises:
        ValueError: If root or mode is unrecognized
    """
    root_norm = normalize_note(root)
    if mode not in SCALE_FORMULAS:
        valid = list(SCALE_FORMULAS.keys())
        raise ValueError(f"Unknown mode: {mode!r}. Valid modes: {valid}")

    root_idx = NOTE_NAMES.index(root_norm)
    formula = SCALE_FORMULAS[mode]
    return [NOTE_NAMES[(root_idx + interval) % 12] for interval in formula]


def build_chord_midi(root: str, quality: str, octave: int = DEFAULT_VOICING_OCTAVE) -> list[int]:
    """
    Build MIDI note list for a chord.

    Args:
        root: Root note name (e.g., "A", "C#")
        quality: Chord quality key from CHORD_INTERVALS (e.g., "minor", "maj7")
        octave: Base octave for voicing (default: 4)

    Returns:
        List of MIDI pitch numbers for the chord

    Raises:
        ValueError: If root or quality is unrecognized
    """
    root_norm = normalize_note(root)
    if quality not in CHORD_INTERVALS:
        raise ValueError(f"Unknown chord quality: {quality!r}")

    root_midi = note_to_midi(root_norm, octave)
    return [root_midi + interval for interval in CHORD_INTERVALS[quality]]


def build_diatonic_chords(
    root: str,
    mode: str = "natural minor",
    voicing: str = "triads",
) -> list[dict]:
    """
    Build the full set of diatonic chords for a key.

    Args:
        root: Root note of the key (e.g., "A", "C#")
        mode: Scale mode (see SCALE_FORMULAS keys)
        voicing: Voicing style: "triads", "seventh", or "extended"

    Returns:
        List of dicts, one per scale degree:
        {
            "degree": int (0-based),
            "roman": str,
            "root": str,
            "quality": str,
            "name": str,       # e.g. "Am7", "Fmaj7"
            "midi_notes": list[int]
        }

    Raises:
        ValueError: If root, mode, or voicing is unrecognized
    """
    scale = build_scale(root, mode)
    qualities = DIATONIC_QUALITIES.get(mode, DIATONIC_QUALITIES["natural minor"])
    romans = ROMAN_NUMERALS.get(mode, ROMAN_NUMERALS["natural minor"])
    upgrades = VOICING_UPGRADES.get(voicing, VOICING_UPGRADES["triads"])

    chords = []
    for i, (note, base_quality) in enumerate(zip(scale, qualities, strict=False)):
        quality = upgrades.get(base_quality, base_quality)
        name = _chord_name(note, quality)
        midi_notes = build_chord_midi(note, quality)
        chords.append(
            {
                "degree": i,
                "roman": romans[i] if i < len(romans) else str(i + 1),
                "root": note,
                "quality": quality,
                "name": name,
                "midi_notes": midi_notes,
            }
        )
    return chords


def parse_chord_name(chord_name: str) -> tuple[str, str]:
    """
    Parse a chord name string into (root, quality_key).

    Recognizes common suffixes: m, min, maj7, m7, 7, dim, aug, sus2, sus4,
    maj9, m9, 9, add9, madd9.

    Args:
        chord_name: Chord name string (e.g., "Am", "Cmaj7", "Bb7", "F#m9")

    Returns:
        Tuple of (root_note_normalized, quality_key) where quality_key
        is a key in CHORD_INTERVALS.

    Raises:
        ValueError: If the chord name cannot be parsed
    """
    name = chord_name.strip()
    if not name:
        raise ValueError("Empty chord name")

    # Extract root (1 or 2 chars: note + optional accidental)
    if len(name) >= 2 and name[1] in ("#", "b"):
        root_raw = name[:2]
        suffix = name[2:]
    else:
        root_raw = name[:1]
        suffix = name[1:]

    root = normalize_note(root_raw)

    # Match suffix longest-first to avoid partial matches
    sorted_suffixes = sorted(CHORD_SUFFIX_MAP.keys(), key=len, reverse=True)
    for s in sorted_suffixes:
        if suffix == s:
            return root, CHORD_SUFFIX_MAP[s]

    raise ValueError(f"Unrecognized chord suffix {suffix!r} in {chord_name!r}")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _chord_name(root: str, quality: str) -> str:
    """
    Build a human-readable chord name from root + quality key.

    Args:
        root: Root note in sharp notation
        quality: Quality key from CHORD_INTERVALS

    Returns:
        Chord name string (e.g., "Am7", "Fmaj7", "C")
    """
    # Use flat spelling for roots that are commonly written with flats
    display_root = ENHARMONIC.get(root, root)

    suffix_map = {
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
    suffix = suffix_map.get(quality, quality)
    return f"{display_root}{suffix}"
